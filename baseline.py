"""Blind A/B comparison between the prototype and a Claude Project."""
from __future__ import annotations

import random
from datetime import datetime

PASS_IDEAS = 10
PASS_WINS = 6
PASS_IMPACT = 3


def result_markdown(result: dict) -> str:
    """Render a Stress Test result as plain markdown, with nothing that reveals its source."""
    lines = [f"**Concept:** {result['surviving_concept']}", "", result["summary"], "", "**Claims**"]
    for c in result["claims"]:
        lines.append(f"- {'(critical) ' if c['critical'] else ''}{c['status']}: {c['text']}")
    lines += ["", "**Unresolved blockers**"]
    lines += [f"- {b}" for b in result["unresolved_blockers"]] or ["- None"]
    lines += ["", f"**Distinctive value lost:** {result['distinctive_value_lost']}",
              "", f"**Smallest test:** {result['smallest_test']}",
              f"**Success:** {result['success_criteria']}",
              f"**Failure:** {result['failure_criteria']}"]
    return "\n".join(lines)


def create(db, idea_id: int, stress_result_id: int, project_output: str, rng: random.Random | None = None) -> int:
    label = (rng or random.SystemRandom()).choice(["A", "B"])
    return db.insert("baseline_comparisons", idea_id=idea_id, stress_result_id=stress_result_id,
                     project_output=project_output, prototype_label=label)


def score(db, comparison_id: int, winner: str, changed_decision: bool, caught_flaw: bool, notes: str = "") -> None:
    db.update("baseline_comparisons", comparison_id, winner=winner, changed_decision=int(changed_decision),
              caught_flaw=int(caught_flaw), notes=notes, scored_at=datetime.now().isoformat(timespec="seconds"))


def summary(db) -> dict:
    rows = db.all("SELECT * FROM baseline_comparisons WHERE winner IS NOT NULL")
    ideas = {r["idea_id"] for r in rows}
    wins = sum(1 for r in rows if r["winner"] == r["prototype_label"])
    # Impact counts only when the prototype's output is the one that changed a decision or caught a flaw.
    impact = sum(1 for r in rows if r["winner"] == r["prototype_label"] and (r["changed_decision"] or r["caught_flaw"]))
    scored = len(rows)
    done = len(ideas) >= PASS_IDEAS
    return {
        "scored": scored, "ideas": len(ideas), "prototype_wins": wins,
        "ties": sum(1 for r in rows if r["winner"] == "tie"), "impact": impact,
        "complete": done,
        "passed": done and wins >= PASS_WINS and impact >= PASS_IMPACT,
    }
