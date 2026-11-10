"""Keeps CHANGELOG.md and ROADMAP.md up to date automatically.

Runs when the app starts, after each Stress Test, after baseline scoring, after
`eval_gate.py`, and on demand with `python update_docs.py`. Each run:

1. Compares every project file, every setting, and the prompt fingerprint with the
   last recorded state. Any difference becomes a new versioned CHANGELOG entry,
   described in plain words by Haiku when an API key is available.
2. Records milestones from real use (first live Stress Test, gate checks, phase
   status changes, baseline pass or fail) as dated CHANGELOG entries.
3. Rewrites the generated blocks in ROADMAP.md: live phase status, usage numbers,
   and improvements suggested by the data.

Hand-written text outside the generated blocks is never changed.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import settings

ENTRY_MARKER = "<!-- AUTO-ENTRIES: new entries are inserted below this line -->"
TRACKED_GLOBS = ["*.py", "prompts/*.txt", "schema.sql", "requirements.txt", "Dockerfile",
                 "docker-compose.yml", ".dockerignore", "README.md", "CLAUDE.md", "constraints.md",
                 "tests/*.py", "tests/*.jsonl"]
NO_CONTENT_TO_MODEL = {"constraints.md"}  # your own text: logged as changed, never sent anywhere
SETTING_SKIP = {"ANTHROPIC_API_KEY", "TAVILY_API_KEY", "BASE_DIR", "DATA_DIR", "DB_PATH", "BACKUP_DIR",
                "PROMPT_DIR", "CONSTRAINTS_PATH", "CHANGELOG_PATH", "ROADMAP_PATH", "DOC_STATE_DIR"}
MAX_DIFF_CHARS = 15_000
VERDICT_DOMINANCE = 0.7
MIN_RUNS_FOR_SIGNALS = 5


# =============================================================================
# State
# =============================================================================
def _state_path() -> Path:
    return settings.DOC_STATE_DIR / "state.json"


def _snapshot_dir() -> Path:
    return settings.DOC_STATE_DIR / "snapshot"


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    settings.DOC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state, indent=1, sort_keys=True))


def tracked_files(base: Path = settings.BASE_DIR) -> dict[str, Path]:
    files = {}
    for pattern in TRACKED_GLOBS:
        for p in base.glob(pattern):
            if p.is_file():
                files[p.relative_to(base).as_posix()] = p
    return files


def fingerprint(files: dict[str, Path]) -> dict[str, str]:
    return {rel: hashlib.sha256(p.read_bytes()).hexdigest() for rel, p in sorted(files.items())}


def settings_snapshot() -> dict[str, str]:
    snap = {}
    for k in dir(settings):
        if k.isupper() and k not in SETTING_SKIP:
            v = getattr(settings, k)
            if isinstance(v, (int, float, str, bool, dict, list, tuple)):
                snap[k] = json.dumps(v, sort_keys=True, default=str)
    return snap


def _save_snapshot(files: dict[str, Path]) -> None:
    root = _snapshot_dir()
    for rel, p in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    for old in root.rglob("*"):
        if old.is_file() and old.relative_to(root).as_posix() not in files:
            old.unlink()


def _old_text(rel: str) -> str:
    try:
        return (_snapshot_dir() / rel).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


# =============================================================================
# Change detection
# =============================================================================
def detect_changes(state: dict, files: dict[str, Path]) -> dict:
    old_fp, new_fp = state.get("files", {}), fingerprint(files)
    old_set, new_set = state.get("settings", {}), settings_snapshot()
    from prompts_loader import prompt_version
    return {
        "added": sorted(set(new_fp) - set(old_fp)),
        "changed": sorted(k for k in set(new_fp) & set(old_fp) if new_fp[k] != old_fp[k]),
        "removed": sorted(set(old_fp) - set(new_fp)),
        "settings": [(k, old_set.get(k), new_set.get(k)) for k in sorted(set(old_set) | set(new_set))
                     if old_set.get(k) != new_set.get(k) and k != "PROMPT_VERSION"],
        "prompt_version": (state.get("prompt_version"), prompt_version()),
        "fingerprint": new_fp,
        "settings_snapshot": new_set,
    }


def _has_changes(ch: dict) -> bool:
    return bool(ch["added"] or ch["changed"] or ch["removed"] or ch["settings"])


def build_diff(ch: dict, files: dict[str, Path]) -> str:
    parts = []
    for rel in ch["changed"] + ch["added"]:
        if rel in NO_CONTENT_TO_MODEL:
            parts.append(f"--- {rel}: content changed (not shown)")
            continue
        try:
            new = files[rel].read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        diff = difflib.unified_diff(_old_text(rel).splitlines(), new.splitlines(),
                                    fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="", n=2)
        parts.append("\n".join(diff))
    for rel in ch["removed"]:
        parts.append(f"--- {rel}: file removed")
    text = "\n\n".join(p for p in parts if p)
    return text[:MAX_DIFF_CHARS] + ("\n... (diff truncated)" if len(text) > MAX_DIFF_CHARS else "")


def summarize(diff_text: str, db, provider) -> list[tuple[str, str]] | None:
    """Plain-language bullets from Haiku, or None when no model is available or the diff is unsafe to send."""
    if not (provider and settings.AUTO_DOC_AI_SUMMARY and diff_text.strip()):
        return None
    from agents import DocSummary
    from gates import security_filter
    from llm import RunContext
    if security_filter(diff_text).blocked:
        return None
    run_id = db.start_run("docs")
    ctx = RunContext(db=db, provider=provider, run_id=run_id, store_inputs=False)
    try:
        out = ctx.call("doc_summarizer", diff_text, DocSummary)
        db.end_run(run_id, "ok", ctx.cost, ctx.elapsed)
        return [(e.kind, e.text) for e in out.entries]
    except Exception as exc:  # documentation must never break the app
        db.end_run(run_id, "error", ctx.cost, ctx.elapsed, notes=str(exc)[:300])
        return None


# =============================================================================
# CHANGELOG
# =============================================================================
_VERSION = re.compile(r"^## (\d+)\.(\d+)\.(\d+)\b", re.M)


def next_version(changelog: str) -> str:
    versions = [tuple(map(int, m)) for m in _VERSION.findall(changelog)]
    major, minor, patch = max(versions) if versions else (0, 0, 0)
    return f"{major}.{minor}.{patch + 1}"


def insert_entry(changelog: str, entry: str) -> str:
    if ENTRY_MARKER not in changelog:
        changelog = changelog.rstrip() + f"\n\n{ENTRY_MARKER}\n"
    head, tail = changelog.split(ENTRY_MARKER, 1)
    tail = tail.lstrip("\n")
    return f"{head}{ENTRY_MARKER}\n\n{entry.strip()}\n" + (f"\n{tail}" if tail else "")


def change_entry(version: str, when: str, ch: dict, bullets: list[tuple[str, str]] | None) -> str:
    lines = [f"## {version} · {when} · Recorded automatically", ""]
    if bullets:
        for kind in ("Added", "Changed", "Fixed", "Removed"):
            items = [t for k, t in bullets if k == kind]
            if items:
                lines += [f"### {kind}"] + [f"- {t}" for t in items] + [""]
    else:
        lines += ["### Changed", "- Project files changed; see the file list below.", ""]
    files = ([f"- Added: `{f}`" for f in ch["added"]] + [f"- Changed: `{f}`" for f in ch["changed"]]
             + [f"- Removed: `{f}`" for f in ch["removed"]])
    if files:
        lines += ["### Files"] + files + [""]
    if ch["settings"]:
        lines += ["### Settings"]
        for k, old, new in ch["settings"]:
            lines.append(f"- `{k}`: {_fmt(old)} → {_fmt(new)}")
        lines.append("")
    old_pv, new_pv = ch["prompt_version"]
    if old_pv and old_pv != new_pv:
        lines += ["### Prompts", f"- Prompt version `{old_pv}` → `{new_pv}`. Runs on each version are "
                  "listed separately on the Runs & costs page.", ""]
    return "\n".join(lines)


def _fmt(v: str | None) -> str:
    if v is None:
        return "(none)"
    s = json.loads(v) if v else v
    text = json.dumps(s) if isinstance(s, (dict, list)) else str(s)
    return f"`{text if len(text) <= 120 else text[:117] + '...'}`"


def milestone_entry(when: str, title: str, details: list[str]) -> str:
    return "\n".join([f"## {when} · Milestone: {title}", ""] + [f"- {d}" for d in details]) + "\n"


# =============================================================================
# Usage data -> phase status, metrics, suggestions
# =============================================================================
def collect(db) -> dict:
    stress = db.all("SELECT * FROM runs WHERE mode = 'stress_test'")
    ok = [r for r in stress if r["status"] == "ok"]
    verdicts = Counter(r["verdict"] for r in ok if r["verdict"])
    opus_runs = db.one(
        "SELECT COUNT(DISTINCT c.run_id) AS n FROM llm_calls c JOIN runs r ON r.id = c.run_id "
        "WHERE r.mode = 'stress_test' AND c.model = ?", (settings.MODELS["opus"],))["n"]
    gate = db.one("SELECT * FROM gate_evals ORDER BY id DESC LIMIT 1")
    import baseline
    stuck = db.one("SELECT COUNT(*) AS n FROM ideas WHERE status = 'exploring' "
                   "AND updated_at < datetime('now', '-14 days')")["n"]
    return {
        "ideas": Counter(r["status"] for r in db.all("SELECT status FROM ideas")),
        "explore_ideas": db.one("SELECT COUNT(*) AS n FROM ideas WHERE session_id IS NOT NULL")["n"],
        "stress_ok": len(ok),
        "stress_paused": sum(1 for r in stress if r["status"] == "paused"),
        "stress_error": sum(1 for r in stress if r["status"] == "error"),
        "first_stress": min((r["started_at"] for r in ok), default=None),
        "avg_cost": sum(r["total_cost"] for r in ok) / len(ok) if ok else None,
        "avg_time": sum(r["duration_s"] or 0 for r in ok) / len(ok) if ok else None,
        "checkpoint_stops": sum(1 for r in ok if (r["notes"] or "").startswith("Stopped at the cost")),
        "verdicts": verdicts,
        "opus_runs": opus_runs,
        "spend": db.one("SELECT COALESCE(SUM(total_cost), 0) AS c FROM runs")["c"],
        "gate": gate,
        "baseline": baseline.summary(db),
        "experiments": db.one("SELECT COUNT(*) AS n FROM experiments")["n"],
        "concepts": db.one("SELECT COUNT(*) AS n FROM concepts WHERE approved = 1")["n"],
        "stuck": stuck,
    }


def _gate_passed(g: dict | None) -> bool:
    return bool(g) and g["seeds_rejected"] == 0 and g["correct"] / g["total"] >= 0.9


def phase_status(d: dict) -> dict[int, str]:
    b = d["baseline"]
    s = {
        1: "Done" if _gate_passed(d["gate"]) and d["explore_ideas"] else "Built; checks pending",
        2: "Done" if d["stress_ok"] else "Built; first live run pending",
        3: ("Passed" if b["passed"] else "Failed") if b["complete"] else f"In progress ({b['ideas']} of 10 ideas)",
    }
    if b["complete"] and not b["passed"]:
        s[4] = "Rescope per Phase 3 failure plan"
    elif d["experiments"]:
        s[4] = "In progress"
    else:
        s[4] = "Ready to start" if b["passed"] else "Blocked on Phase 3"
    s[5] = "In progress" if d["concepts"] else ("Ready to start" if s[4] == "Done" else "Blocked on Phase 4")
    return s


def signals(d: dict) -> list[str]:
    """Improvements suggested by the data. Each one names the evidence that triggered it."""
    out = []
    n = d["stress_ok"]
    if n >= MIN_RUNS_FOR_SIGNALS and d["verdicts"]:
        verdict, count = d["verdicts"].most_common(1)[0]
        if count / n >= VERDICT_DOMINANCE:
            out.append(f"**Evaluator calibration.** `{verdict}` is {count} of {n} verdicts. Retune the early "
                       "and later bars in `prompts/evaluator.txt`.")
    if d["avg_cost"] and d["avg_cost"] > settings.RECONSIDER_COST_USD:
        out.append(f"**Cost tuning.** Average Stress Test cost is ${d['avg_cost']:.2f}, above the "
                   f"${settings.RECONSIDER_COST_USD:.2f} checkpoint. Lower effort or move agents to Haiku "
                   "where baseline cases show quality holds.")
    if n >= MIN_RUNS_FOR_SIGNALS and d["checkpoint_stops"] / n >= 0.3:
        out.append(f"**Checkpoint tuning.** {d['checkpoint_stops']} of {n} runs stopped at the checkpoint. "
                   "Raise `RECONSIDER_COST_USD` or `RECONSIDER_SECONDS`, or cut research per cycle.")
    if n >= MIN_RUNS_FOR_SIGNALS and d["opus_runs"] / n >= 0.3:
        out.append(f"**Escalation review.** {d['opus_runs']} of {n} runs escalated to Opus. Check whether "
                   "verdicts are unstable or `decisive_unresolved` is set too often.")
    if d["stress_paused"] >= 2:
        out.append(f"**Resume paused runs.** {d['stress_paused']} runs hit the runaway pause; build resume "
                   "instead of restart.")
    if d["stress_error"] >= 2:
        out.append(f"**Error review.** {d['stress_error']} Stress Tests failed. See the notes column on the "
                   "Runs & costs page.")
    g = d["gate"]
    if g and not _gate_passed(g):
        misses = json.loads(g["misses_json"] or "[]")
        kinds = Counter(m[0] for m in misses)
        out.append(f"**Scope gate tuning.** Latest check: {g['correct']}/{g['total']} correct, "
                   f"{g['seeds_rejected']} vague seeds rejected. Misses by kind: "
                   + ", ".join(f"{k} {v}" for k, v in kinds.items()) + ". Adjust `prompts/scope_gate.txt`.")
    if d["stuck"]:
        out.append(f"**Weekly review.** {d['stuck']} ideas have sat in `exploring` for over 14 days.")
    return out


def status_block(d: dict, when: str) -> str:
    s = phase_status(d)
    g = d["gate"]
    b = d["baseline"]
    checks = {
        1: [("Explore session saved an idea", bool(d["explore_ideas"])),
            ("Live gate check passed (`python eval_gate.py`)", _gate_passed(g))],
        2: [("No `FACT` without verified evidence (unit tests)", True),
            ("A run ends with one small test (unit tests)", True),
            ("First live Stress Test completed", bool(d["stress_ok"]))],
        3: [(f"10 real ideas scored ({b['ideas']} so far)", b["complete"]),
            (f"At least 6 prototype wins ({b['prototype_wins']} so far)", b["prototype_wins"] >= 6),
            (f"At least 3 changed decisions or caught flaws ({b['impact']} so far)", b["impact"] >= 3)],
    }
    names = {1: "Gates, Explore, idea pipeline", 2: "Stress Test and claim ledger", 3: "Baseline comparison",
             4: "Experiment log", 5: "Memory"}
    lines = [f"_Generated {when} from the app's data. Edits inside this block are overwritten._", "",
             "| Phase | Name | Status |", "| --- | --- | --- |"]
    lines += [f"| {p} | {names[p]} | {s[p]} |" for p in range(1, 6)]
    lines.append("")
    for p, items in checks.items():
        lines.append(f"**Phase {p} checks**")
        lines += [f"- [{'x' if done else ' '}] {text}" for text, done in items]
        lines.append("")
    lines += ["**Usage**", ""]
    ideas = d["ideas"]
    lines.append("- Ideas: " + (", ".join(f"{k} {v}" for k, v in sorted(ideas.items())) or "none yet"))
    lines.append(f"- Stress Tests: {d['stress_ok']} completed, {d['stress_paused']} paused, {d['stress_error']} failed")
    if d["avg_cost"] is not None:
        lines.append(f"- Average Stress Test: ${d['avg_cost']:.3f}, {d['avg_time']:.0f} s")
    if d["verdicts"]:
        lines.append("- Verdicts: " + ", ".join(f"`{k}` {v}" for k, v in d["verdicts"].most_common()))
    if g:
        lines.append(f"- Latest gate check ({g['created_at'][:10]}): {g['correct']}/{g['total']} correct, "
                     f"{g['seeds_rejected']} vague seeds rejected")
    lines.append(f"- API spend to date: ${d['spend']:.2f}")
    lines += ["", "**Suggested by usage data**", ""]
    sig = signals(d)
    lines += [f"- {x}" for x in sig] if sig else ["- Nothing yet. Suggestions appear as real runs accumulate."]
    return "\n".join(lines)


def replace_block(text: str, name: str, content: str) -> str:
    start, end = f"<!-- AUTO:{name}:start -->", f"<!-- AUTO:{name}:end -->"
    block = f"{start}\n{content.strip()}\n{end}"
    if start in text and end in text:
        return text[: text.index(start)] + block + text[text.index(end) + len(end):]
    return text.rstrip() + f"\n\n{block}\n"


# =============================================================================
# Milestones
# =============================================================================
def milestones(d: dict, db, state: dict) -> list[tuple[str, list[str]]]:
    found = []
    seen = state.setdefault("milestones", {})
    if d["stress_ok"] and not seen.get("first_stress"):
        found.append(("first live Stress Test", [
            f"Completed {d['first_stress']}.",
            f"Cost ${d['avg_cost']:.3f}, {d['avg_time']:.0f} s." if d["avg_cost"] is not None else ""]))
        seen["first_stress"] = True
    last_gate = seen.get("gate_eval_id", 0)
    for g in db.all("SELECT * FROM gate_evals WHERE id > ? ORDER BY id", (last_gate,)):
        result = "passed" if _gate_passed(g) else "did not pass"
        found.append((f"scope gate check {result}", [
            f"{g['correct']}/{g['total']} correct, {g['seeds_rejected']} vague seeds wrongly rejected, "
            f"cost ${g['cost'] or 0:.4f}."]))
        seen["gate_eval_id"] = g["id"]
    b = d["baseline"]
    if b["complete"] and not seen.get("baseline_done"):
        verdict = "passed" if b["passed"] else "did not pass"
        nxt = "Phase 4 is ready to start." if b["passed"] else \
            "Keep the Claude Project and rescope Phases 4 and 5 in ROADMAP.md."
        found.append((f"baseline comparison {verdict}", [
            f"{b['prototype_wins']} prototype wins, {b['impact']} changed decisions or caught flaws, "
            f"{b['ties']} ties over {b['ideas']} ideas.", nxt]))
        seen["baseline_done"] = True
    old = state.get("phase_status", {})
    new = {str(k): v for k, v in phase_status(d).items()}
    for p, status in new.items():
        if old and old.get(p) != status:
            found.append((f"Phase {p} status changed", [f"{old.get(p, 'unknown')} → {status}"]))
    state["phase_status"] = new
    return [(t, [x for x in det if x]) for t, det in found]


# =============================================================================
# Entry point
# =============================================================================
def sync_docs(db, provider=None, now: datetime | None = None) -> dict:
    """Update both docs. Safe to call often; does nothing when nothing changed."""
    when = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    state = load_state()
    files = tracked_files()
    report = {"entries": 0, "milestones": 0}
    try:
        changelog = settings.CHANGELOG_PATH.read_text(encoding="utf-8")
        roadmap = settings.ROADMAP_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return report

    ch = detect_changes(state, files)
    if not state.get("files"):
        changelog = insert_entry(changelog, milestone_entry(when, "automatic documentation started", [
            f"Tracking {len(files)} project files and {len(ch['settings_snapshot'])} settings.",
            f"Prompt version `{ch['prompt_version'][1]}`."]))
        report["milestones"] += 1
    elif _has_changes(ch):
        bullets = summarize(build_diff(ch, files), db, provider)
        changelog = insert_entry(changelog, change_entry(next_version(changelog), when, ch, bullets))
        report["entries"] += 1

    data = collect(db)
    for title, details in milestones(data, db, state):
        changelog = insert_entry(changelog, milestone_entry(when, title, details))
        report["milestones"] += 1

    roadmap = replace_block(roadmap, "status", status_block(data, when))
    # Write in place (not rename) so Docker bind-mounted files update on the host.
    settings.CHANGELOG_PATH.write_text(changelog, encoding="utf-8")
    settings.ROADMAP_PATH.write_text(roadmap, encoding="utf-8")

    _save_snapshot(files)
    state.update(files=ch["fingerprint"], settings=ch["settings_snapshot"], prompt_version=ch["prompt_version"][1],
                 last_sync=when)
    save_state(state)
    return report


def safe_sync(db, provider=None) -> dict:
    """sync_docs that never raises; documentation must not break the app."""
    try:
        return sync_docs(db, provider)
    except Exception as exc:
        return {"error": str(exc)}
