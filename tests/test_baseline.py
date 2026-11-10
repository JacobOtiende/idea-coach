import random

import baseline


def _setup(db, n):
    ids = []
    for i in range(n):
        idea = db.add_idea(f"idea {i}", "d")
        run = db.start_run("stress_test", idea_id=idea)
        sr = db.save_stress_result(idea, run, {"x": 1})
        ids.append(baseline.create(db, idea, sr, "project answer", rng=random.Random(i)))
    return ids


def test_pass_bar(db):
    comps = _setup(db, 10)
    for k, cid in enumerate(comps):
        row = db.one("SELECT * FROM baseline_comparisons WHERE id = ?", (cid,))
        proto = row["prototype_label"]
        other = "B" if proto == "A" else "A"
        winner = proto if k < 6 else other
        baseline.score(db, cid, winner, changed_decision=k < 3, caught_flaw=False)
    s = baseline.summary(db)
    assert s["complete"] and s["prototype_wins"] == 6 and s["impact"] == 3 and s["passed"]


def test_incomplete_does_not_pass(db):
    comps = _setup(db, 3)
    for cid in comps:
        row = db.one("SELECT * FROM baseline_comparisons WHERE id = ?", (cid,))
        baseline.score(db, cid, row["prototype_label"], True, True)
    s = baseline.summary(db)
    assert not s["complete"] and not s["passed"]


def test_result_markdown_hides_source():
    md = baseline.result_markdown({
        "surviving_concept": "c", "summary": "s", "claims": [{"critical": True, "status": "FACT", "text": "t"}],
        "unresolved_blockers": [], "distinctive_value_lost": "None", "smallest_test": "x",
        "success_criteria": "a", "failure_criteria": "b"})
    assert "Idea Coach" not in md and "prototype" not in md.lower()
