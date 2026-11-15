"""Scheduled work (E1): scouting saved searches and syncing marketplace events into the pipeline board and
conversation graph. Called by Arq cron jobs (compose) or the API's inline loop (single process)."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import select

from agent.mcp_client import ToolGateway, ToolUnavailable
from agent.memory.store import record_outcome
from agent.nodes.scout import fingerprint, scout_search
from agent.settings import cfg
from apps.api import events
from apps.api.db import KV, Conversation, JobRecord, ProposalCard, SavedSearch, SessionLocal, User

log = logging.getLogger("gigbid.scheduler")
STAGE_FROM_EVENT = {"proposal_viewed": "viewed", "client_replied": "replied", "interview_scheduled": "interview", "hired": "hired"}


def _interval(search: SavedSearch, user: User) -> int:
    floor = int(cfg("scheduler.live_interval_minutes", 120)) if user.marketplace_mode == "upwork_live" else 1
    return max(floor, int(search.interval_minutes or cfg("scheduler.gigsim_interval_minutes", 30)))


async def due_searches(now: dt.datetime | None = None) -> list[tuple[SavedSearch, User]]:
    now = now or dt.datetime.now(dt.UTC)
    async with SessionLocal() as s:
        rows = (await s.execute(select(SavedSearch, User).join(User, User.id == SavedSearch.user_id).where(SavedSearch.enabled))).all()
    out = []
    for search, user in rows:
        nxt = search.next_run_at
        if nxt is not None and nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=dt.UTC)
        if nxt is None or nxt <= now:
            out.append((search, user))
    return out


async def _insert_job_once(s: Any, user_id: str, j: dict[str, Any], **cols: Any) -> bool:
    """Insert the JobRecord unless (user_id, job_id) already exists. True if this call created it."""
    conn = await s.connection()
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    values = {"user_id": user_id, "job_id": j["job_id"], "thread_id": f"bid:{user_id}:{j['job_id']}", "title": j["title"][:300],
              "category": j.get("category"), "job": j, **cols}
    res = await s.execute(insert(JobRecord).values(**values).on_conflict_do_nothing(index_elements=["user_id", "job_id"]))
    return bool(res.rowcount)


async def run_search(runner: Any, search: SavedSearch, user: User, enqueue_bid) -> dict[str, int]:
    """Scout one saved search; queue new jobs for analysis (idempotent: one JobRecord per user+job)."""
    gw = ToolGateway(user.id, user.persona_id, account=user.account_id)
    async with SessionLocal() as s:
        recent_rows = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id).order_by(JobRecord.created_at.desc()).limit(300))).scalars().all()
    recent = [{"job_id": r.job_id, "title": r.title, "description": (r.job or {}).get("description", ""),
               "_fp": fingerprint({"title": r.title, "description": (r.job or {}).get("description", "")})} for r in recent_rows]
    try:
        new, dups = await scout_search(gw, {"query": search.query, "category": search.category, "skills": search.skills,
                                            "min_budget": search.min_budget, "limit": int(cfg("scheduler.max_jobs_per_scout", 25))}, recent)
    except ToolUnavailable as exc:
        await events.publish(user.id, {"type": "degraded", "server": "marketplace", "detail": str(exc)})
        return {"new": 0, "duplicates": 0, "error": 1}
    queued: list[dict[str, Any]] = []
    async with SessionLocal() as s:
        # INSERT ... ON CONFLICT DO NOTHING: a scheduled scout and a "Scout now" click (or two workers) can see the same
        # job at the same moment; only one of them creates the row and queues the analysis.
        for j in dups:
            await _insert_job_once(s, user.id, j, status="duplicate", duplicate_of=j.get("duplicate_of"),
                                   status_reason=f"duplicate of {j.get('duplicate_of')}")
        for j in new:
            if await _insert_job_once(s, user.id, j, status="queued"):
                queued.append(j)
        db_search = await s.get(SavedSearch, search.id)
        now = dt.datetime.now(dt.UTC)
        db_search.last_run_at = now
        db_search.next_run_at = now + dt.timedelta(minutes=_interval(search, user))
        await s.commit()
    for j in queued:
        await enqueue_bid(user.id, j["job_id"], j)
    await events.publish(user.id, {"type": "scout_finished", "search": search.name, "new": len(queued), "duplicates": len(dups)})
    return {"new": len(queued), "duplicates": len(dups)}


async def sync_user(runner: Any, user: User, enqueue_conversation) -> dict[str, int]:
    """Marketplace events -> pipeline stages + outcome memory; new client messages -> conversation graph."""
    gw = ToolGateway(user.id, user.persona_id, account=user.account_id)
    key = f"events_cursor:{user.id}"
    async with SessionLocal() as s:
        kv = await s.get(KV, key)
        cursor = int((kv.value or {}).get("seq", 0)) if kv else 0
    try:
        evs = (await gw.call("sync", "marketplace", "list_events", {"since": cursor}))["events"]
    except ToolUnavailable as exc:
        await events.publish(user.id, {"type": "degraded", "server": "marketplace", "detail": str(exc)})
        return {"events": 0, "error": 1}
    changed = 0
    to_converse: list[tuple[str, str | None, str | None]] = []
    async with SessionLocal() as s:
        for e in evs:
            cursor = max(cursor, int(e["seq"]))
            card = None
            if e.get("proposal_id"):
                card = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user.id,
                                                                   ProposalCard.proposal_id == e["proposal_id"]))).scalar_one_or_none()
            stage = STAGE_FROM_EVENT.get(e["type"])
            order = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
            if card and stage and order.index(stage) > order.index(card.stage if card.stage in order else "drafted"):
                card.stage = stage
                if e.get("thread_id"):
                    card.marketplace_thread_id = e["thread_id"]
                changed += 1
                if stage in {"replied", "interview", "hired"}:
                    await record_outcome(runner.store, user.id, {"proposal_id": card.proposal_id, "category": card.category or "other",
                                                                 "strategy": card.strategy, "outcome": stage})
            if e["type"] in {"client_replied", "message"} and e.get("thread_id"):
                to_converse.append((e["thread_id"], e.get("proposal_id"), card.job_id if card else None))
        kv = await s.get(KV, key)
        if kv:
            kv.value = {"seq": cursor}
        else:
            s.add(KV(key=key, value={"seq": cursor}))
        await s.commit()
    for mthread, pid, job_id in dict.fromkeys(to_converse):
        async with SessionLocal() as s:
            conv = (await s.execute(select(Conversation).where(Conversation.user_id == user.id,
                                                               Conversation.marketplace_thread_id == mthread))).scalar_one_or_none()
        if conv and conv.status == "awaiting_approval":
            continue
        await enqueue_conversation(user.id, mthread, pid, job_id)
    if changed or to_converse:
        await events.publish(user.id, {"type": "pipeline_updated", "changed": changed})
    return {"events": len(evs), "changed": changed}


async def all_users() -> list[User]:
    async with SessionLocal() as s:
        return list((await s.execute(select(User).where(User.onboarded))).scalars().all())
