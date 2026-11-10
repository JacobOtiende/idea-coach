import json

import pytest

import settings
from llm import FakeProvider, LLMTimeout, RunContext, Usage, compute_cost
from pipeline import handle_explore_message, run_stress_test
from research import FakeSearcher

EXPLORE = {
    "problem": "Neighbors buy tools they rarely use.",
    "proposed_solution": "Tool library",
    "coach_message": "Here are three directions.",
    "approaches": [
        {"title": "Tool library", "description": "Shared shed", "assumption_changed": "ownership",
         "why_it_might_work": "low use", "disadvantages": ["upkeep"], "epistemic_status": "HYPOTHESIS"},
    ],
}

GOOD_RESULTS = [
    {"url": "https://a.org/study", "title": "Tool use study", "content": "Average drill is used 13 minutes.",
     "published_date": "2025-01-01"},
    {"url": "https://b.com/news", "title": "Rental market", "content": "Rental shops report flat demand.",
     "published_date": ""},
]


def stress_replies(evaluator=None, verifier="supported", coach=None, researcher=None):
    ev = evaluator or {
        "verdict": "PROCEED_WITH_VALIDATION", "reasons": ["credible problem"],
        "unresolved_blockers": ["Willingness to pay is untested"], "research_requests": [],
        "still_addresses_problem": True, "distinctive_value_lost": "None", "decisive_unresolved": False,
    }
    return {
        "claim_extractor": {"claims": [
            {"text": "Neighbors rarely use tools", "critical": True, "reasoning": "core"},
            {"text": "Neighbors will share", "critical": True, "reasoning": "core"},
            {"text": "Insurance is cheap", "critical": False, "reasoning": ""},
        ]},
        "researcher_plan": lambda m: {"queries": [
            {"claim_id": _first_claim_id(m), "direction": "supporting", "query": "how often are power drills used"},
            {"claim_id": _first_claim_id(m), "direction": "contradicting", "query": "tool library failures"},
        ]},
        "researcher": researcher or (lambda m: {
            "evidence": [
                {"claim_id": _first_claim_id(m), "source_id": "S1", "direction": "supporting",
                 "summary": "Drills are used 13 minutes on average."},
                {"claim_id": _first_claim_id(m), "source_id": "S9", "direction": "supporting",
                 "summary": "Fabricated source."},
            ],
            "claim_status": [{"claim_id": _first_claim_id(m), "proposed_status": "FACT", "reasoning": "study"}],
        }),
        "source_verifier": {"verdict": verifier, "note": "checked"},
        "challenger": {"objections": [{"id": "O1", "claim_ids": [], "objection": "Trust", "why_it_matters": "x"}]},
        "counter_challenger": {"assessments": [{"objection_id": "O1", "strength": "moderate"}]},
        "evaluator": ev,
        "coach": coach or {"surviving_concept": "A street-level tool shed", "summary": "Mixed.",
                           "smallest_test": "Flyer 40 houses", "success_criteria": ">= 5 signups",
                           "failure_criteria": "< 2 signups"},
        "reconsider": {"continue_run": False, "reason": "needs a real test"},
    }


def _first_claim_id(messages):
    import re
    return int(re.search(r"C(\d+) \[critical\]", messages[-1]["content"]).group(1))


# --- Explore ----------------------------------------------------------------------
def test_blocked_message_makes_no_call_and_saves_nothing(db):
    p = FakeProvider({})
    sid = db.new_session("explore")
    r = handle_explore_message(db, p, sid, "my server is 192.168.1.20", [])
    assert r.kind == "blocked" and p.calls == []
    assert db.messages(sid) == [] and db.all("SELECT * FROM runs") == []


def test_out_of_scope_runs_no_agent_and_saves_no_message(db):
    p = FakeProvider({"scope_gate": {"classification": "out_of_scope", "reason": "trivia"}})
    sid = db.new_session("explore")
    r = handle_explore_message(db, p, sid, "capital of Australia?", [])
    assert r.kind == "rejected"
    assert [c["agent"] for c in p.calls] == ["scope_gate"]
    assert db.messages(sid) == []
    assert db.all("SELECT input_text FROM llm_calls")[0]["input_text"] == "[not stored]"


def test_unclear_asks_then_answer_keeps_seed_alive(db):
    p = FakeProvider({"scope_gate": [
        {"classification": "unclear", "reason": "maybe", "clarifying_question": "What problem?"},
        {"classification": "unclear", "reason": "still vague"},
    ], "explorer": EXPLORE})
    sid = db.new_session("explore")
    r1 = handle_explore_message(db, p, sid, "Why is HOA management so bad?", [])
    assert r1.kind == "clarify" and r1.text == "What problem?"
    r2 = handle_explore_message(db, p, sid, "I'm a homeowner", [], pending_question=r1.text)
    assert r2.kind == "explore" and r2.explore.approaches[0].title == "Tool library"
    assert [m["role"] for m in db.messages(sid)] == ["assistant", "user", "assistant"]


def test_explore_repairs_bad_json_once(db):
    p = FakeProvider({"scope_gate": {"classification": "in_scope", "reason": "idea"},
                      "explorer": ["not json at all", EXPLORE]})
    sid = db.new_session("explore")
    r = handle_explore_message(db, p, sid, "tool sharing idea", [])
    assert r.kind == "explore"
    assert [c["agent"] for c in p.calls] == ["scope_gate", "explorer", "explorer"]


# --- Stress Test ------------------------------------------------------------------
def _idea(db):
    return db.add_idea("Tool shed", "Shared tools for a street", problem="Waste")


def test_stress_test_happy_path(db):
    p = FakeProvider(stress_replies())
    s = FakeSearcher(GOOD_RESULTS)
    out = run_stress_test(db, p, s, _idea(db))
    assert out.status == "ok", out.message
    res = out.result
    first = res["claims"][0]
    assert first["status"] == "FACT"
    assert len(first["evidence"]) == 1  # fabricated S9 dropped
    assert res["unresolved_blockers"] == ["Willingness to pay is untested"]
    assert res["smallest_test"] and res["distinctive_value_lost"] == "None"
    assert len(s.queries) <= settings.MAX_SEARCHES_PER_RUN
    run = db.one("SELECT * FROM runs WHERE id = ?", (out.run_id,))
    assert run["verdict"] == "PROCEED_WITH_VALIDATION" and run["total_cost"] > 0
    assert db.get_idea(1)["status"] == "exploring"


def test_unverified_source_cannot_make_fact(db):
    p = FakeProvider(stress_replies(verifier="unsupported"))
    out = run_stress_test(db, p, FakeSearcher(GOOD_RESULTS), _idea(db))
    first = out.result["claims"][0]
    assert first["status"] == "HYPOTHESIS"
    events = db.claim_events(first["id"])
    assert any(e["attempted_status"] == "FACT" for e in events)


def test_coach_cannot_drop_blockers(db):
    ev = {"verdict": "REVISE", "reasons": ["r"], "unresolved_blockers": ["B1", "B2"], "research_requests": [],
          "still_addresses_problem": False, "distinctive_value_lost": "Neighborhood feel",
          "decisive_unresolved": False}
    out = run_stress_test(db, FakeProvider(stress_replies(evaluator=ev)), FakeSearcher(GOOD_RESULTS), _idea(db))
    assert out.result["unresolved_blockers"] == ["B1", "B2"]
    assert out.result["still_addresses_problem"] is False


def test_research_required_loops_at_most_two_cycles_and_flip_escalates(db):
    evs = [
        {"verdict": "RESEARCH_REQUIRED", "reasons": ["need data"], "unresolved_blockers": ["x"],
         "research_requests": [{"claim_id": 1, "what_to_establish": "usage"}],
         "still_addresses_problem": True, "distinctive_value_lost": "None", "decisive_unresolved": False},
        {"verdict": "REVISE", "reasons": ["r"], "unresolved_blockers": ["y"], "research_requests": [],
         "still_addresses_problem": True, "distinctive_value_lost": "None", "decisive_unresolved": False},
    ]
    replies = stress_replies()
    replies["evaluator"] = evs + [evs[1]]
    p = FakeProvider(replies)
    out = run_stress_test(db, p, FakeSearcher(GOOD_RESULTS), _idea(db))
    agents = [c["agent"] for c in p.calls]
    assert agents.count("challenger") == 2
    opus_calls = [c for c in p.calls if c["model"] == settings.MODELS["opus"]]
    assert len(opus_calls) == 1 and opus_calls[0]["agent"] == "evaluator"
    assert out.result["evaluator"]["history"] == ["RESEARCH_REQUIRED", "REVISE"]


def test_runaway_pause(db, monkeypatch):
    monkeypatch.setattr(settings, "RUNAWAY_PAUSE_USD", 0.0001)
    p = FakeProvider(stress_replies(), usage=Usage(input_tokens=100_000, output_tokens=10_000))
    out = run_stress_test(db, p, FakeSearcher(GOOD_RESULTS), _idea(db))
    assert out.status == "paused"
    assert db.one("SELECT status FROM runs WHERE id = ?", (out.run_id,))["status"] == "paused"
    out2 = run_stress_test(db, FakeProvider(stress_replies()), FakeSearcher(GOOD_RESULTS), 1, allow_runaway=True)
    assert out2.status == "ok"


def test_checkpoint_stop_still_runs_final_evaluator_and_reports(db, monkeypatch):
    evs = {"verdict": "RESEARCH_REQUIRED", "reasons": ["need data"], "unresolved_blockers": ["x"],
           "research_requests": [{"claim_id": 1, "what_to_establish": "usage"}],
           "still_addresses_problem": True, "distinctive_value_lost": "None", "decisive_unresolved": False}
    monkeypatch.setattr(settings, "RECONSIDER_COST_USD", 0.00001)
    p = FakeProvider(stress_replies(evaluator=evs))
    out = run_stress_test(db, p, FakeSearcher(GOOD_RESULTS), _idea(db))
    agents = [c["agent"] for c in p.calls]
    assert "reconsider" in agents and agents.count("challenger") == 1
    assert "source_verifier" in agents and "evaluator" in agents and agents[-1] == "coach"
    assert any("checkpoint" in b for b in out.result["unresolved_blockers"])


def test_stress_test_requires_search(db):
    out = run_stress_test(db, FakeProvider({}), None, _idea(db))
    assert out.status == "error" and "search" in out.message.lower()


def test_missing_required_field_rejected_then_repaired(db):
    bad = {"surviving_concept": "x", "summary": "y", "smallest_test": "", "success_criteria": "a",
           "failure_criteria": "b"}
    good = {"surviving_concept": "x", "summary": "y", "smallest_test": "flyer", "success_criteria": "a",
            "failure_criteria": "b"}
    replies = stress_replies()
    replies["coach"] = [bad, good]
    out = run_stress_test(db, FakeProvider(replies), FakeSearcher(GOOD_RESULTS), _idea(db))
    assert out.status == "ok" and out.result["smallest_test"] == "flyer"


# --- LLM layer -----------------------------------------------------------------------
def test_timeout_retries_once_with_less_context(db):
    p = FakeProvider({"coach": [LLMTimeout("slow"), json.dumps({"x": 1})]})
    run = db.start_run("test")
    ctx = RunContext(db=db, provider=p, run_id=run)
    assert ctx.call("coach", "long " * 2000, compact_user="short") == '{"x": 1}'
    assert p.calls[1]["messages"][0]["content"] == "short"
    statuses = [r["status"] for r in db.all("SELECT status FROM llm_calls")]
    assert statuses == ["timeout", "ok"]


def test_cost_math():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert compute_cost("claude-sonnet-5-5", u) == pytest.approx(12.0)
    assert compute_cost("claude-haiku-5-5", Usage(input_tokens=1000, output_tokens=1000)) == pytest.approx(0.0006)
    long = Usage(input_tokens=200_000)
    assert compute_cost("claude-haiku-5-5", long) == pytest.approx(0.1)


def test_system_blocks_have_cache_and_schema():
    from agents import ScopeDecision
    from prompts_loader import system_blocks
    blocks = system_blocks("scope_gate", ScopeDecision)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "classification" in blocks[1]["text"]
