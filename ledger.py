"""Claim ledger. Models propose epistemic labels; this module decides which are allowed.

Rules (enforced in code, not prompts):
- FACT needs at least one supporting source that verification marked "supported",
  and no verified ("supported") contradicting source.
- EVIDENCE_BASED_INFERENCE needs at least one supporting or analogous source that
  verification marked "supported" or "partial", plus recorded reasoning.
- Anything else falls back to HYPOTHESIS. SPECULATION is always allowed.
Every change, including a refused label, is written to claim_events.
"""
from __future__ import annotations

from datetime import date

STATUSES = ("FACT", "EVIDENCE_BASED_INFERENCE", "HYPOTHESIS", "SPECULATION")


def allowed_status(proposed: str, evidence: list[dict], reasoning: str = "") -> str:
    if proposed not in STATUSES:
        return "HYPOTHESIS"
    verified_support = [e for e in evidence if e["direction"] == "supporting" and e["verification"] == "supported"]
    verified_contra = [e for e in evidence if e["direction"] == "contradicting" and e["verification"] == "supported"]
    usable = [e for e in evidence
              if e["direction"] in ("supporting", "analogous") and e["verification"] in ("supported", "partial")]

    if proposed == "FACT":
        if verified_support and not verified_contra:
            return "FACT"
        proposed = "EVIDENCE_BASED_INFERENCE"
    if proposed == "EVIDENCE_BASED_INFERENCE":
        return "EVIDENCE_BASED_INFERENCE" if usable and reasoning.strip() else "HYPOTHESIS"
    return proposed


def add_claims(db, idea_id: int, run_id: int, extracted: list) -> list[dict]:
    rows = []
    for c in extracted:
        cid = db.insert("claims", idea_id=idea_id, run_id=run_id, text=c.text, critical=int(c.critical),
                        status="HYPOTHESIS", reasoning=c.reasoning)
        db.insert("claim_events", claim_id=cid, run_id=run_id, from_status=None, to_status="HYPOTHESIS",
                  cause="extracted from idea")
        rows.append(db.one("SELECT * FROM claims WHERE id = ?", (cid,)))
    return rows


def set_status(db, claim_id: int, proposed: str, cause: str, run_id: int | None = None,
               reasoning: str = "") -> str:
    """Apply a proposed label after enforcing the rules. Returns the status actually stored."""
    claim = db.one("SELECT * FROM claims WHERE id = ?", (claim_id,))
    if claim is None:
        raise KeyError(claim_id)
    evidence = db.evidence_for_claim(claim_id)
    final = allowed_status(proposed, evidence, reasoning)
    attempted = proposed if final != proposed else None
    if final != claim["status"] or attempted:
        db.update("claims", claim_id, status=final, reasoning=reasoning or claim["reasoning"])
        db.insert("claim_events", claim_id=claim_id, run_id=run_id, from_status=claim["status"],
                  to_status=final, attempted_status=attempted,
                  cause=cause + (f" (requested {proposed}; not allowed by evidence)" if attempted else ""))
    return final


def recheck(db, claim_id: int, run_id: int | None = None) -> str:
    """Re-apply the rules to the current label, e.g. after new contradicting evidence."""
    claim = db.one("SELECT * FROM claims WHERE id = ?", (claim_id,))
    return set_status(db, claim_id, claim["status"], "rechecked after new evidence", run_id, claim["reasoning"] or "")


def add_evidence(db, claim_id: int, run_id: int, *, url: str, title: str, summary: str, direction: str,
                 organization: str = "", published_date: str = "", source_type: str = "web",
                 verification: str = "pending") -> int:
    return db.insert("evidence", claim_id=claim_id, run_id=run_id, source_type=source_type, url=url,
                     title=title, organization=organization, published_date=published_date,
                     retrieved_date=date.today().isoformat(), summary=summary, direction=direction,
                     verification=verification)


def ledger_text(db, claims: list[dict], include_evidence: bool = True) -> str:
    """Compact text form of the ledger, passed between agents instead of chat history."""
    lines = []
    for c in claims:
        c = db.one("SELECT * FROM claims WHERE id = ?", (c["id"],))
        tag = "critical" if c["critical"] else "minor"
        lines.append(f"C{c['id']} [{tag}] {c['status']}: {c['text']}")
        if include_evidence:
            for e in db.evidence_for_claim(c["id"]):
                lines.append(
                    f"    E{e['id']} {e['direction']} (verification: {e['verification']}) "
                    f"{e['summary']} [{e['title'] or e['url']}]"
                )
    return "\n".join(lines) if lines else "(no claims)"
