import ledger
from agents import ExtractedClaim


def _claim(db):
    idea = db.add_idea("t", "d")
    run = db.start_run("stress_test", idea_id=idea)
    rows = ledger.add_claims(db, idea, run, [ExtractedClaim(text="People will pay", critical=True)])
    return rows[0]["id"], run


def _ev(db, cid, run, direction, verification):
    ledger.add_evidence(db, cid, run, url="https://x.org", title="x", summary="s", direction=direction,
                        verification=verification)


def test_fact_without_evidence_is_downgraded_and_logged(db):
    cid, run = _claim(db)
    assert ledger.set_status(db, cid, "FACT", "test", run, "because") == "HYPOTHESIS"
    ev = db.claim_events(cid)[-1]
    assert ev["attempted_status"] == "FACT" and ev["to_status"] == "HYPOTHESIS"


def test_fact_with_unverified_support_is_downgraded(db):
    cid, run = _claim(db)
    _ev(db, cid, run, "supporting", "pending")
    _ev(db, cid, run, "supporting", "unsupported")
    assert ledger.set_status(db, cid, "FACT", "test", run, "r") == "HYPOTHESIS"


def test_fact_with_verified_support(db):
    cid, run = _claim(db)
    _ev(db, cid, run, "supporting", "supported")
    assert ledger.set_status(db, cid, "FACT", "test", run) == "FACT"


def test_verified_contradiction_blocks_fact(db):
    cid, run = _claim(db)
    _ev(db, cid, run, "supporting", "supported")
    _ev(db, cid, run, "contradicting", "supported")
    assert ledger.set_status(db, cid, "FACT", "test", run, "mixed") == "EVIDENCE_BASED_INFERENCE"


def test_recheck_downgrades_fact_after_new_contradiction(db):
    cid, run = _claim(db)
    _ev(db, cid, run, "supporting", "supported")
    assert ledger.set_status(db, cid, "FACT", "test", run) == "FACT"
    _ev(db, cid, run, "contradicting", "supported")
    assert ledger.recheck(db, cid, run) == "HYPOTHESIS"  # no reasoning recorded for inference


def test_inference_needs_reasoning(db):
    cid, run = _claim(db)
    _ev(db, cid, run, "analogous", "partial")
    assert ledger.set_status(db, cid, "EVIDENCE_BASED_INFERENCE", "t", run, "") == "HYPOTHESIS"
    assert ledger.set_status(db, cid, "EVIDENCE_BASED_INFERENCE", "t", run, "analogy holds") == "EVIDENCE_BASED_INFERENCE"


def test_speculation_and_invalid_labels(db):
    cid, run = _claim(db)
    assert ledger.set_status(db, cid, "SPECULATION", "t", run) == "SPECULATION"
    assert ledger.allowed_status("CERTAIN", []) == "HYPOTHESIS"


def test_user_experiment_counts_as_evidence(db):
    cid, run = _claim(db)
    ledger.add_evidence(db, cid, run, url="", title="flyer test", summary="9 of 40 signed up",
                        direction="supporting", source_type="user_experiment", verification="supported")
    assert ledger.set_status(db, cid, "FACT", "user test", run) == "FACT"
