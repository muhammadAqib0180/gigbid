"""Declared output schemas for the Marketplace MCP tools (inputs are constrained in the tool signatures)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Job(BaseModel):
    job_id: str
    title: str
    description: str
    skills: list[str] = Field(default_factory=list)
    category: str | None = None
    is_hourly: bool = False
    budget: float | None = None
    hourly_low: float | None = None
    hourly_high: float | None = None
    experience_level: str | None = None
    connects_cost: int | None = None
    client_id: str | None = None
    posted_at: str | None = None
    source: str | None = None
    synthetic: bool | None = None


class JobList(BaseModel):
    jobs: list[Job]
    total: int
    marketplace: str


class ClientHistory(BaseModel):
    client_id: str
    country: str | None = None
    payment_verified: bool = False
    total_spent: float = 0.0
    rating: float | None = None
    reviews_count: int = 0
    jobs_posted: int = 0
    hires: int = 0
    hire_rate: float = 0.0
    avg_hourly_paid: float | None = None
    member_since: str | None = None
    industry: str | None = None
    recent_reviews: list[str] = Field(default_factory=list)


class ConnectsBalance(BaseModel):
    balance: int
    spent: int = 0
    weekly_allowance: int | None = None


class MarketStats(BaseModel):
    category: str
    fixed_budget: dict[str, float | None] = Field(default_factory=dict)
    hourly_paid: dict[str, float | None] = Field(default_factory=dict)
    hourly_posted_low_p50: float | None = None
    hourly_posted_high_p50: float | None = None
    fixed_n: int = 0
    hourly_paid_n: int = 0


class Thread(BaseModel):
    thread_id: str
    proposal_id: str | None = None
    job_id: str | None = None
    client_id: str | None = None
    stage: str | None = None


class ThreadList(BaseModel):
    threads: list[Thread]


class Message(BaseModel):
    message_id: str
    sender: str
    text: str
    at_min: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MessageList(BaseModel):
    thread_id: str
    messages: list[Message]


class MarketEvent(BaseModel):
    seq: int
    type: str
    proposal_id: str | None = None
    thread_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventList(BaseModel):
    events: list[MarketEvent]


class WritePreview(BaseModel):
    dry_run: bool = True
    action: str
    payload: dict[str, Any]
    connects_cost: int = 0
    balance_before: int | None = None
    balance_after: int | None = None
    warnings: list[str] = Field(default_factory=list)


class WriteResult(BaseModel):
    dry_run: bool = False
    action: str
    status: str
    proposal_id: str | None = None
    message_id: str | None = None
    connects_spent: int = 0
    balance: int | None = None
    idempotent_replay: bool = False
    marketplace: str = "gigsim"
    note: str | None = None
    preview: WritePreview | None = None
