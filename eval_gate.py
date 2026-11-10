"""Run the labeled gate test set against the real scope gate (costs a few cents on Haiku).

Usage:  python eval_gate.py
"""
from __future__ import annotations

import json
from pathlib import Path

import db as dbmod
from agents import ScopeDecision
from gates import security_filter
from llm import AnthropicProvider, RunContext

CASES = Path(__file__).resolve().parent / "tests" / "gate_cases.jsonl"


def classify(ctx: RunContext, message: str) -> str:
    if security_filter(message).blocked:
        return "blocked"
    d = ctx.call("scope_gate", f"RECENT CONVERSATION:\n(none)\n\nMESSAGE TO CLASSIFY:\n{message}", ScopeDecision)
    return d.classification


def main() -> None:
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    db = dbmod.DB()
    run_id = db.start_run("gate_eval")
    ctx = RunContext(db=db, provider=AnthropicProvider(), run_id=run_id, store_inputs=False)
    correct, rejected_seeds, misses = 0, 0, []
    for c in cases:
        got = classify(ctx, c["message"])
        # A vague seed counts as correct if the gate keeps it alive (in_scope or unclear).
        ok = got == c["expected"] or (c["kind"] == "vague seed" and got in ("in_scope", "unclear"))
        correct += ok
        if c["kind"] == "vague seed" and got == "out_of_scope":
            rejected_seeds += 1
        if not ok:
            misses.append((c["kind"], c["expected"], got, c["message"]))
    db.end_run(run_id, "ok", ctx.cost, ctx.elapsed)
    db.insert("gate_evals", correct=correct, total=len(cases), seeds_rejected=rejected_seeds,
              cost=round(ctx.cost, 6), misses_json=json.dumps([[k, e, g] for k, e, g, _ in misses]))
    import devlog
    devlog.safe_sync(db, ctx.provider)
    print(f"Correct: {correct}/{len(cases)}   Vague seeds wrongly rejected: {rejected_seeds}   Cost: ${ctx.cost:.4f}")
    for kind, exp, got, msg in misses:
        print(f"  MISS [{kind}] expected {exp}, got {got}: {msg}")


if __name__ == "__main__":
    main()
