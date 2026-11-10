"""Output schemas for every agent. Pydantic validates each reply before code uses it."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["FACT", "EVIDENCE_BASED_INFERENCE", "HYPOTHESIS", "SPECULATION"]
Direction = Literal["supporting", "contradicting", "analogous"]
Verdict = Literal["PROCEED", "PROCEED_WITH_VALIDATION", "RESEARCH_REQUIRED", "REVISE", "RECONSIDER"]


def _cap(n: int):
    def validator(v: list) -> list:
        return v[:n]
    return validator


# --- Gate 2 -----------------------------------------------------------------------
class ScopeDecision(BaseModel):
    classification: Literal["in_scope", "unclear", "out_of_scope"]
    reason: str
    clarifying_question: str = ""


# --- Explore: uploaded documents ---------------------------------------------------
class DocBrief(BaseModel):
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    ideas_mentioned: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    _cap_points = field_validator("key_points", "problems", "ideas_mentioned", "open_questions")(_cap(10))


# --- Explore --------------------------------------------------------------------
class Approach(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    assumption_changed: str = Field(min_length=1)
    why_it_might_work: str
    disadvantages: list[str] = Field(default_factory=list)
    epistemic_status: Status
    constraints_note: str = ""


class ExploreOutput(BaseModel):
    problem: str
    proposed_solution: str = ""
    coach_message: str = Field(min_length=1)
    approaches: list[Approach] = Field(default_factory=list)
    question: str = ""

    _cap_approaches = field_validator("approaches")(_cap(3))


# --- Stress Test: claims ------------------------------------------------------------
class ExtractedClaim(BaseModel):
    text: str = Field(min_length=1)
    critical: bool
    reasoning: str = ""


class ClaimExtraction(BaseModel):
    claims: list[ExtractedClaim] = Field(min_length=1)

    _cap_claims = field_validator("claims")(_cap(8))


# --- Stress Test: research ------------------------------------------------------------
class PlannedQuery(BaseModel):
    claim_id: int
    direction: Direction
    query: str = Field(min_length=3, max_length=200)


class ResearchPlan(BaseModel):
    queries: list[PlannedQuery] = Field(default_factory=list)


class EvidenceDraft(BaseModel):
    claim_id: int
    source_id: str = Field(description="The [S#] label of the search result this evidence comes from.")
    direction: Direction
    summary: str = Field(min_length=1)
    organization: str = ""
    published_date: str = ""


class ClaimStatusProposal(BaseModel):
    claim_id: int
    proposed_status: Status
    reasoning: str = ""


class ResearchFindings(BaseModel):
    evidence: list[EvidenceDraft] = Field(default_factory=list)
    claim_status: list[ClaimStatusProposal] = Field(default_factory=list)


class Verification(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    note: str = ""


# --- Stress Test: challenge loop ------------------------------------------------------------
class Objection(BaseModel):
    id: str
    claim_ids: list[int] = Field(default_factory=list)
    objection: str = Field(min_length=1)
    why_it_matters: str
    evidence_needed: str = ""


class ChallengeOutput(BaseModel):
    objections: list[Objection] = Field(default_factory=list)
    resolved_issues: list[str] = Field(default_factory=list)

    _cap_objections = field_validator("objections")(_cap(3))


class Assessment(BaseModel):
    objection_id: str
    strength: Literal["strong", "moderate", "weak"]
    weaknesses: str = ""
    mitigation: str = ""
    revised_interpretation: str = ""
    unresolved_issue: str = ""


class CounterOutput(BaseModel):
    assessments: list[Assessment] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    claim_id: int
    what_to_establish: str
    decision_affected: str = ""


class EvaluatorOutput(BaseModel):
    verdict: Verdict
    reasons: list[str] = Field(min_length=1)
    unresolved_blockers: list[str] = Field(default_factory=list)
    research_requests: list[ResearchRequest] = Field(default_factory=list)
    still_addresses_problem: bool
    distinctive_value_lost: str = Field(description="What narrowing removed, or 'None'.")
    decisive_unresolved: bool = Field(
        description="True if a critical claim is still unresolved and could decide the verdict.")


class CoachResult(BaseModel):
    surviving_concept: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    smallest_test: str = Field(min_length=1)
    success_criteria: str = Field(min_length=1)
    failure_criteria: str = Field(min_length=1)


class DocEntry(BaseModel):
    kind: Literal["Added", "Changed", "Fixed", "Removed"]
    text: str = Field(min_length=1)


class DocSummary(BaseModel):
    entries: list[DocEntry] = Field(min_length=1)

    _cap_entries = field_validator("entries")(_cap(5))


class ReconsiderDecision(BaseModel):
    continue_run: bool
    reason: str
