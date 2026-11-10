import json
from datetime import datetime

import pytest

import devlog
import settings
from llm import FakeProvider

CHANGELOG = f"# Changelog\n\nIntro.\n\n{devlog.ENTRY_MARKER}\n\n## 0.3.0 · 2026-11-09 · Old\n\n- old entry\n"
ROADMAP = "# Roadmap\n\n<!-- AUTO:status:start -->\nold\n<!-- AUTO:status:end -->\n\n## Guardrails\n\nKeep me.\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway project folder with its own docs and state."""
    base = tmp_path / "proj"
    (base / "prompts").mkdir(parents=True)
    (base / "app.py").write_text("print('v1')\n")
    (base / "prompts" / "coach.txt").write_text("coach v1\n")
    (base / "constraints.md").write_text("secret plans\n")
    cl, rm = base / "CHANGELOG.md", base / "ROADMAP.md"
    cl.write_text(CHANGELOG, encoding="utf-8")
    rm.write_text(ROADMAP, encoding="utf-8")
    monkeypatch.setattr(settings, "BASE_DIR", base)
    monkeypatch.setattr(settings, "CHANGELOG_PATH", cl)
    monkeypatch.setattr(settings, "ROADMAP_PATH", rm)
    monkeypatch.setattr(settings, "DOC_STATE_DIR", base / "data" / "doc_state")
    monkeypatch.setattr(devlog, "tracked_files", lambda base=base: _tracked(base))
    return base


def _tracked(base):
    return {p.relative_to(base).as_posix(): p for p in base.rglob("*")
            if p.is_file() and p.suffix in (".py", ".txt", ".md") and p.name not in ("CHANGELOG.md", "ROADMAP.md")
            and "data" not in p.parts}


def summarizer(entries):
    return FakeProvider({"doc_summarizer": {"entries": entries}})


def test_first_run_starts_tracking_and_fills_roadmap(db, project):
    r = devlog.sync_docs(db, None, now=datetime(2026, 11, 10, 9, 0))
    cl = settings.CHANGELOG_PATH.read_text(encoding="utf-8")
    rm = settings.ROADMAP_PATH.read_text(encoding="utf-8")
    assert r["milestones"] == 1 and "automatic documentation started" in cl
    assert "| 2 | Stress Test and claim ledger | Built; first live run pending |" in rm
    assert "Keep me." in rm and "\nold\n" not in rm
    assert cl.index("automatic documentation started") < cl.index("0.3.0")  # newest first


def test_no_change_means_no_entry(db, project):
    devlog.sync_docs(db, None)
    before = settings.CHANGELOG_PATH.read_text(encoding="utf-8")
    assert devlog.sync_docs(db, None)["entries"] == 0
    assert settings.CHANGELOG_PATH.read_text(encoding="utf-8") == before


def test_code_change_creates_versioned_entry_with_ai_summary(db, project):
    devlog.sync_docs(db, None)
    (project / "app.py").write_text("print('v2')\n")
    (project / "new_feature.py").write_text("x = 1\n")
    p = summarizer([{"kind": "Added", "text": "Stress Test now exports results."}])
    devlog.sync_docs(db, p, now=datetime(2026, 11, 11, 10, 0))
    cl = settings.CHANGELOG_PATH.read_text(encoding="utf-8")
    assert "## 0.3.1 · 2026-11-11 10:00 · Recorded automatically" in cl
    assert "### Added\n- Stress Test now exports results." in cl
    assert "- Changed: `app.py`" in cl and "- Added: `new_feature.py`" in cl
    diff_sent = p.calls[0]["messages"][0]["content"]
    assert "print('v2')" in diff_sent


def test_constraints_content_never_sent(db, project):
    devlog.sync_docs(db, None)
    (project / "constraints.md").write_text("new private plans\n")
    p = summarizer([{"kind": "Changed", "text": "Constraints updated."}])
    devlog.sync_docs(db, p)
    sent = p.calls[0]["messages"][0]["content"]
    assert "private plans" not in sent and "constraints.md" in sent


def test_unsafe_diff_not_sent_but_still_logged(db, project):
    devlog.sync_docs(db, None)
    (project / "app.py").write_text("HOST = '10.1.2.3'\n")
    p = summarizer([{"kind": "Changed", "text": "x"}])
    devlog.sync_docs(db, p)
    assert p.calls == []
    assert "- Changed: `app.py`" in settings.CHANGELOG_PATH.read_text(encoding="utf-8")


def test_setting_change_logged_with_values(db, project, monkeypatch):
    devlog.sync_docs(db, None)
    monkeypatch.setattr(settings, "MAX_SEARCHES_PER_RUN", 7)
    devlog.sync_docs(db, None)
    assert "- `MAX_SEARCHES_PER_RUN`: `5` → `7`" in settings.CHANGELOG_PATH.read_text(encoding="utf-8")


def test_milestones_and_suggestions_from_usage(db, project):
    devlog.sync_docs(db, None)
    idea = db.add_idea("t", "d")
    for _ in range(5):
        run = db.start_run("stress_test", idea_id=idea)
        db.end_run(run, "ok", 1.5, 120, verdict="RECONSIDER")
    db.insert("gate_evals", correct=30, total=40, seeds_rejected=2, cost=0.01,
              misses_json=json.dumps([["vague seed", "unclear", "out_of_scope"]]))
    devlog.sync_docs(db, None)
    cl = settings.CHANGELOG_PATH.read_text(encoding="utf-8")
    rm = settings.ROADMAP_PATH.read_text(encoding="utf-8")
    assert "Milestone: first live Stress Test" in cl
    assert "Milestone: scope gate check did not pass" in cl
    assert "Milestone: Phase 2 status changed" in cl
    assert "| 2 | Stress Test and claim ledger | Done |" in rm
    assert "- [x] First live Stress Test completed" in rm
    assert "**Evaluator calibration.**" in rm and "**Cost tuning.**" in rm and "**Scope gate tuning.**" in rm
    # Milestones are recorded once.
    devlog.sync_docs(db, None)
    assert settings.CHANGELOG_PATH.read_text(encoding="utf-8").count("first live Stress Test") == 1


def test_safe_sync_never_raises(db, project, monkeypatch):
    monkeypatch.setattr(devlog, "collect", lambda db: 1 / 0)
    assert "error" in devlog.safe_sync(db, None)


def test_next_version():
    assert devlog.next_version("## 0.3.0 · x\n## 0.10.2 · y\n") == "0.10.3"
    assert devlog.next_version("nothing") == "0.0.1"
