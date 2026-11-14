"""Application database (SQLAlchemy 2 async). Postgres in compose, SQLite locally. Every query in the
routers filters by `user_id` (tenant scoping, E4)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agent.settings import database_url


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _id() -> str:
    return uuid.uuid4().hex[:16]


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    persona_id: Mapped[str] = mapped_column(String(64), default="ai_ml_engineer")
    account_id: Mapped[str] = mapped_column(String(64), default="ai_ml_engineer")     # GigSim freelancer / marketplace account
    marketplace_mode: Mapped[str] = mapped_column(String(20), default="gigsim")
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    hourly_rate_usd: Mapped[float] = mapped_column(Float, default=40)
    min_hourly_usd: Mapped[float] = mapped_column(Float, default=30)
    min_fixed_usd: Mapped[float] = mapped_column(Float, default=250)
    weekly_connects: Mapped[int] = mapped_column(Integer, default=80)
    autonomy: Mapped[str] = mapped_column(String(30), default="suggest")
    max_tokens_per_job: Mapped[int] = mapped_column(Integer, default=24000)
    proposal_strategy: Mapped[str] = mapped_column(String(30), default="evidence_first")
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    query: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skills: Mapped[list[Any]] = mapped_column(JSON, default=list)
    min_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRecord(Base):
    """One row per (user, job): what the inbox and job detail show. Mirrors the bid thread's final state."""
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_scam: Mapped[bool] = mapped_column(Boolean, default=False)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)   # bid | watch | skip
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    connects_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    status_reason: Mapped[str] = mapped_column(Text, default="")
    duplicate_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)     # risk/fit/spec/decision/price for job detail
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProposalCard(Base):
    """Pipeline board card: drafted -> submitted -> viewed -> replied -> interview -> hired / lost."""
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(160))
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    marketplace_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), default="drafted")
    title: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    strategy: Mapped[str] = mapped_column(String(30), default="evidence_first")
    bid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    connects_spent: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(160), index=True)
    kind: Mapped[str] = mapped_column(String(20))           # bid | conversation | replay
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="running")
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    thread_id: Mapped[str] = mapped_column(String(160), index=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    node: Mapped[str] = mapped_column(String(60), default="")
    event: Mapped[str] = mapped_column(String(30), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApprovalLog(Base):
    __tablename__ = "approval_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    thread_id: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))           # proposal | message
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    diff: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("user_id", "marketplace_thread_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    marketplace_thread_id: Mapped[str] = mapped_column(String(64))
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    graph_thread_id: Mapped[str] = mapped_column(String(160))
    last_message_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="idle")
    intent: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Secret(Base):
    """Encrypted per-user secrets (OAuth tokens). Never logged; Fernet with TOKEN_ENCRYPTION_KEY."""
    __tablename__ = "secrets"
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KV(Base):
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _make_engine():
    url = database_url()
    if url.startswith("sqlite"):
        from sqlalchemy import event

        eng = create_async_engine(url, future=True, connect_args={"timeout": 30})

        @event.listens_for(eng.sync_engine, "connect")
        def _pragmas(dbapi_conn, _rec):  # WAL + busy timeout: concurrent runs on a laptop without "database is locked"
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return eng
    return create_async_engine(url, future=True, pool_pre_ping=True, pool_size=10, max_overflow=10)


_engine = _make_engine()
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        yield s
