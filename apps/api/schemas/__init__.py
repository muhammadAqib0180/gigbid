"""Request / response models. The web client's TypeScript types are generated from these via OpenAPI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    persona_id: str
    account_id: str
    marketplace_mode: str
    onboarded: bool


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = ""
    category: str | None = None
    skills: list[str] = Field(default_factory=list)
    min_budget: float | None = None
    interval_minutes: int = Field(default=30, ge=1, le=1440)
    enabled: bool = True


class SavedSearchOut(SavedSearchIn):
    id: str
    last_run_at: str | None = None
    next_run_at: str | None = None


class OnboardingIn(BaseModel):
    profile: Literal["persona", "own"] = "persona"
    persona_id: str = "ai_ml_engineer"
    marketplace_mode: Literal["gigsim", "upwork_live"] = "gigsim"
    account_id: str = "ai_ml_engineer"
    hourly_rate_usd: float = Field(default=40, gt=0)
    min_hourly_usd: float = Field(default=30, gt=0)
    min_fixed_usd: float = Field(default=250, ge=0)
    weekly_connects: int = Field(default=80, ge=0, le=1000)
    saved_searches: list[SavedSearchIn] = Field(default_factory=list)


class SettingsOut(BaseModel):
    hourly_rate_usd: float
    min_hourly_usd: float
    min_fixed_usd: float
    weekly_connects: int
    autonomy: Literal["suggest", "auto_skip_low_fit"]
    max_tokens_per_job: int
    proposal_strategy: str
    marketplace_mode: str
    persona_id: str
    account_id: str


class SettingsIn(BaseModel):
    hourly_rate_usd: float | None = None
    min_hourly_usd: float | None = None
    min_fixed_usd: float | None = None
    weekly_connects: int | None = None
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    max_tokens_per_job: int | None = None
    proposal_strategy: Literal["evidence_first", "question_first", "ab"] | None = None


class JobSummary(BaseModel):
    job_id: str
    thread_id: str
    title: str
    category: str | None = None
    fit_score: float | None = None
    risk_score: float | None = None
    is_scam: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    action: str | None = None
    price: float | None = None
    price_unit: str | None = None
    connects_cost: int | None = None
    status: str
    status_reason: str = ""
    duplicate_of: str | None = None
    budget: float | None = None
    is_hourly: bool = False
    source: str | None = None
    updated_at: str


class JobDetail(JobSummary):
    job: dict[str, Any]
    job_spec: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    fit: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    price_quote: dict[str, Any] | None = None
    evidence_matrix: list[dict[str, Any]] = Field(default_factory=list)
    submission: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class ApprovalOut(BaseModel):
    thread_id: str
    kind: Literal["proposal", "message"]
    job_id: str | None = None
    title: str = ""
    payload: dict[str, Any]


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=8000)
    reason: str | None = Field(default=None, max_length=500)


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0, le=20)
    text: str = Field(min_length=1, max_length=8000)
    instruction: str = Field(default="", max_length=300)


class RegenerateOut(BaseModel):
    paragraph_index: int
    text: str
    model: str


class PipelineCard(BaseModel):
    id: str
    job_id: str
    thread_id: str
    proposal_id: str | None = None
    marketplace_thread_id: str | None = None
    stage: str
    title: str
    category: str | None = None
    strategy: str
    bid_amount: float | None = None
    connects_spent: int = 0
    updated_at: str


class PipelineOut(BaseModel):
    stages: list[str]
    cards: list[PipelineCard]


class ConversationOut(BaseModel):
    marketplace_thread_id: str
    graph_thread_id: str
    job_id: str | None = None
    proposal_id: str | None = None
    status: str
    intent: str | None = None
    title: str = ""
    updated_at: str


class ThreadDetail(BaseModel):
    conversation: ConversationOut | None
    messages: list[dict[str, Any]]
    pending: dict[str, Any] | None = None


class RunOut(BaseModel):
    id: str
    thread_id: str
    kind: str
    job_id: str | None = None
    trace_id: str
    status: str
    tokens: int
    cost_usd: float
    latency_s: float
    error: str = ""
    started_at: str
    finished_at: str | None = None
    trace_url: str | None = None


class RunEventOut(BaseModel):
    id: int
    run_id: str
    ts: str
    node: str
    event: str
    payload: dict[str, Any]


class CheckpointOut(BaseModel):
    checkpoint_id: str
    step: int | None = None
    node: str | None = None
    next: list[str]
    created_at: str | None = None


class RunDetail(BaseModel):
    thread_id: str
    runs: list[RunOut]
    events: list[RunEventOut]
    checkpoints: list[CheckpointOut]
    graph_mermaid: str


class ReplayIn(BaseModel):
    checkpoint_id: str


class AnalyticsOut(BaseModel):
    by_category: list[dict[str, Any]]
    by_strategy: list[dict[str, Any]]
    connects: dict[str, Any]
    cost_latency: dict[str, Any]
    rejection_reasons: list[dict[str, Any]]
    funnel: dict[str, int]
    decisions: dict[str, int]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    marketplace: dict[str, Any]
    servers: dict[str, Any]
    worker_mode: str
    model_profile: str
    marketplace_mode: str


class MemoryOut(BaseModel):
    style: list[dict[str, Any]]
    style_candidates: list[dict[str, Any]]
    outcome: list[dict[str, Any]]


class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""
