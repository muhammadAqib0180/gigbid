"""Typed hand-offs between agents (C3).

Every object a later step decides on is one of these Pydantic models, never free text.
State stores them as plain dicts (model_dump) so checkpoints stay portable; nodes re-validate
on read with `Model.model_validate(state[...])`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    id: str
    text: str
    kind: Literal["skill", "deliverable", "constraint", "question"] = "skill"
    skills: list[str] = Field(default_factory=list)
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    summary: str = ""
    category: str = ""
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    is_hourly: bool = False
    timeline_days: int | None = None
    experience_level: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    connects_cost: int | None = None


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    explanation: str
    is_scam: bool = False
    injection_detected: bool = False
    injection_spans: list[str] = Field(default_factory=list)
    client_quality: float | None = Field(default=None, ge=0, le=1)
    signals: dict[str, float] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    evidence_id: str            # chunk id
    item_id: str                # portfolio item (case study, repo, review, proposal)
    type: str
    title: str = ""
    source: str = ""
    date: str | None = None
    outcome: str | None = None
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    snippet: str = ""
    score: float = 0.0


class RequirementMatch(BaseModel):
    requirement_id: str
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    best_score: float = 0.0
    covered: bool = False


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    matches: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    retrieval_variant: str = ""


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    auto: bool = False


class PriceQuote(BaseModel):
    amount: float
    unit: Literal["fixed", "hourly"] = "fixed"
    low: float
    high: float
    currency: str = "USD"
    rationale: list[str] = Field(default_factory=list)
    connects_cost: int = 0
    connects_balance: int | None = None
    connects_worth_it: bool = True
    expected_value_usd: float | None = None


class Claim(BaseModel):
    claim_id: str
    text: str
    paragraph: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    label: Literal["supported", "partly_supported", "unsupported", "not_a_claim"] = "unsupported"
    support_score: float = 0.0
    note: str = ""


class ScreeningAnswer(BaseModel):
    question: str
    answer: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    job_id: str
    version: int = 1
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    strategy: str = "evidence_first"
    status: str = "pending_review"

    @property
    def word_count(self) -> int:
        return len(self.cover_letter.split())


class VerificationReport(BaseModel):
    version: int
    claims: list[Claim] = Field(default_factory=list)
    total_claims: int = 0
    unsupported_before: int = 0
    unsupported_after: int = 0
    removed: list[str] = Field(default_factory=list)
    softened: list[str] = Field(default_factory=list)

    @property
    def rate_before(self) -> float:
        return self.unsupported_before / self.total_claims if self.total_claims else 0.0

    @property
    def rate_after(self) -> float:
        return self.unsupported_after / self.total_claims if self.total_claims else 0.0


class Critique(BaseModel):
    verdict: Literal["pass", "revise"]
    reasons: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    revision: int = 0


class Redaction(BaseModel):
    kind: str
    original: str
    replacement: str


class ComplianceVerdict(BaseModel):
    allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    redactions: list[Redaction] = Field(default_factory=list)
    cleaned_text: str = ""
    policy_version: str = ""


class DryRunPreview(BaseModel):
    payload: dict = Field(default_factory=dict)
    connects_cost: int = 0
    balance_before: int | None = None
    balance_after: int | None = None
    warnings: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None
    approved_by: str | None = None


class ClientIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""


class Slot(BaseModel):
    start: str
    end: str


class LiaisonDraft(BaseModel):
    thread_id: str
    intent: ClientIntent
    reply_text: str
    proposed_slots: list[Slot] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
