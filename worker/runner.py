"""GraphRunner: executes the bid / conversation graphs for a user, streams node events to the UI bus and the
run_events table, mirrors final state into the app tables, and handles degraded mode (marketplace down ->
run parked as `waiting_marketplace`, retried from its last checkpoint with backoff).

Used by the Arq worker (docker compose) and by the API's inline mode (single-process deployments)."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from collections import defaultdict
from typing import Any

from langgraph.types import Command
from sqlalchemy import select

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.llm import total_tokens, total_usd
from agent.nodes.common import MarketplaceDown
from agent.profile import merged_profile
from agent.tracing import run_config, set_trace_id
from apps.api import events
from apps.api.db import (
    ApprovalLog,
    Conversation,
    JobRecord,
    ProposalCard,
    Run,
    RunEvent,
    SessionLocal,
    User,
    UserSettings,
)

log = logging.getLogger("gigbid.runner")
RETRY_BACKOFF_S = [20, 60, 180, 600]


def bid_thread_id(user_id: str, job_id: str) -> str:
    return f"bid:{user_id}:{job_id}"


def conv_thread_id(user_id: str, mthread: str) -> str:
    return f"conv:{user_id}:{mthread}"


async def user_profile(user_id: str) -> tuple[User, dict[str, Any]]:
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        st = await s.get(UserSettings, user_id)
    overrides = {}
    if st:
        overrides = {"hourly_rate_usd": st.hourly_rate_usd, "min_hourly_usd": st.min_hourly_usd, "min_fixed_usd": st.min_fixed_usd,
                     "weekly_connects": st.weekly_connects, "autonomy": st.autonomy, "proposal_strategy": st.proposal_strategy}
    return u, merged_profile(u.persona_id, overrides)


class GraphRunner:
    def __init__(self, checkpointer: Any, store: Any, defer: Any = None) -> None:
        self.checkpointer = checkpointer
        self.store = store
        self.bid = build_bid_graph(checkpointer, store)
        self.conv = build_conversation_graph(checkpointer, store)
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.defer = defer or self._inline_defer
        self.retries: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------ public API
    async def start_bid(self, user_id: str, job_id: str, job: dict | None = None, force: bool = False) -> str:
        tid = bid_thread_id(user_id, job_id)
        cfg = {"configurable": {"thread_id": tid}}
        existing = await self.bid.aget_state(cfg)
        if existing.values and not force:
            if existing.next:          # interrupted or crashed mid-run: continue, never restart (idempotent processing)
                if any(t.interrupts for t in existing.tasks):
                    return tid
                await self._execute(user_id, self.bid, "bid", tid, None, job_id)
            return tid
        u, prof = await user_profile(user_id)
        inp = {"thread_id": tid, "user_id": user_id, "persona_id": u.persona_id, "account_id": u.account_id, "job_id": job_id,
               "user_profile": prof, "steps": 0}
        if job:
            inp["job"] = job
        await self._execute(user_id, self.bid, "bid", tid, inp, job_id)
        return tid

    async def resume(self, user_id: str, thread_id: str, decision: dict[str, Any]) -> None:
        graph = self.bid if thread_id.startswith("bid:") else self.conv
        st = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        if not any(t.interrupts for t in st.tasks):
            if st.next:     # crashed after approval but before finishing: continue from checkpoint
                await self._execute(user_id, graph, "bid" if graph is self.bid else "conversation", thread_id, None,
                                    st.values.get("job_id"))
            return
        async with SessionLocal() as s:
            s.add(ApprovalLog(user_id=user_id, thread_id=thread_id, kind="proposal" if graph is self.bid else "message",
                              action=decision.get("action", ""), reason=decision.get("reason") or "",
                              diff=(decision.get("edited_text") or "")[:4000] if decision.get("action") == "edit" else ""))
            await s.commit()
        await self._execute(user_id, graph, "bid" if graph is self.bid else "conversation", thread_id, Command(resume=decision),
                            st.values.get("job_id"))

    async def start_conversation(self, user_id: str, mthread: str, proposal_id: str | None = None, job_id: str | None = None) -> str:
        tid = conv_thread_id(user_id, mthread)
        cfg = {"configurable": {"thread_id": tid}}
        st = await self.conv.aget_state(cfg)
        if st.values and any(t.interrupts for t in st.tasks):
            return tid                 # a reply is already waiting for approval
        u, _ = await user_profile(user_id)
        if st.values:                  # new client message on an existing thread: fresh run on a new thread id suffix
            tid = f"{tid}:{int(time.time())}"
        inp = {"thread_id": tid, "marketplace_thread_id": mthread, "user_id": user_id, "persona_id": u.persona_id,
               "account_id": u.account_id, "proposal_id": proposal_id, "job_id": job_id, "steps": 0}
        async with SessionLocal() as s:
            row = (await s.execute(select(Conversation).where(Conversation.user_id == user_id,
                                                              Conversation.marketplace_thread_id == mthread))).scalar_one_or_none()
            if row is None:
                row = Conversation(user_id=user_id, marketplace_thread_id=mthread, proposal_id=proposal_id, job_id=job_id, graph_thread_id=tid)
                s.add(row)
            row.graph_thread_id = tid
            row.status = "drafting"
            await s.commit()
        await self._execute(user_id, self.conv, "conversation", tid, inp, job_id)
        return tid

    async def replay(self, user_id: str, thread_id: str, checkpoint_id: str) -> None:
        graph = self.bid if thread_id.startswith("bid:") else self.conv
        cfg = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
        await self._execute(user_id, graph, "replay", thread_id, None, None, base_config=cfg)

    # ------------------------------------------------------------------ execution
    async def _execute(self, user_id: str, graph: Any, kind: str, thread_id: str, inp: Any, job_id: str | None,
                       base_config: dict | None = None) -> None:
        async with self.locks[thread_id]:
            trace_id = set_trace_id(None)
            if isinstance(inp, dict):
                inp["trace_id"] = trace_id
            async with SessionLocal() as s:
                run = Run(user_id=user_id, thread_id=thread_id, kind=kind, job_id=job_id, trace_id=trace_id, status="running")
                s.add(run)
                await s.commit()
                run_id = run.id
            config = run_config(thread_id, trace_id, user_id, kind, {"job_id": job_id})
            if base_config:
                config["configurable"].update(base_config["configurable"])
            await events.publish(user_id, {"type": "run_started", "thread_id": thread_id, "run_id": run_id, "kind": kind, "trace_id": trace_id})
            t0 = time.perf_counter()
            status, error = "finished", ""
            try:
                async for _mode, chunk in graph.astream(inp, config, stream_mode=["custom"]):
                    await self._record_event(user_id, thread_id, run_id, chunk)
            except MarketplaceDown as exc:
                status, error = "waiting_marketplace", str(exc)
                await events.publish(user_id, {"type": "degraded", "server": "marketplace", "thread_id": thread_id, "detail": str(exc)})
                n = self.retries[thread_id]
                self.retries[thread_id] += 1
                if n < len(RETRY_BACKOFF_S):
                    await self.defer(user_id, thread_id, RETRY_BACKOFF_S[n])
            except Exception as exc:  # noqa: BLE001
                log.exception("run %s failed", thread_id)
                status, error = "error", f"{type(exc).__name__}: {str(exc)[:400]}"
            latency = time.perf_counter() - t0
            st = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            values = st.values or {}
            interrupted = any(t.interrupts for t in st.tasks)
            if status == "finished":
                status = "awaiting_approval" if interrupted else (values.get("status") or "finished")
                self.retries.pop(thread_id, None)
            usage = values.get("usage") or {}
            async with SessionLocal() as s:
                run = await s.get(Run, run_id)
                run.status, run.error, run.latency_s = status, error, round(latency, 3)
                run.usage, run.tokens, run.cost_usd = usage, total_tokens(usage), round(total_usd(usage), 6)
                run.finished_at = dt.datetime.now(dt.UTC)
                await s.commit()
            if graph is self.bid:
                await self._sync_bid(user_id, thread_id, values, status, interrupted, latency)
            else:
                await self._sync_conversation(user_id, values, status, interrupted)
            await events.publish(user_id, {"type": "run_finished", "thread_id": thread_id, "run_id": run_id, "status": status,
                                           "job_id": job_id, "latency_s": round(latency, 2)})

    async def _record_event(self, user_id: str, thread_id: str, run_id: str, chunk: dict[str, Any]) -> None:
        async with SessionLocal() as s:
            s.add(RunEvent(user_id=user_id, thread_id=thread_id, run_id=run_id, node=str(chunk.get("node", "")),
                           event=str(chunk.get("event", "")), payload={k: v for k, v in chunk.items() if k not in {"node", "event"}}))
            await s.commit()
        await events.publish(user_id, {"type": "run_event", "thread_id": thread_id, "run_id": run_id, **chunk})

    async def _inline_defer(self, user_id: str, thread_id: str, delay_s: float) -> None:
        async def later() -> None:
            await asyncio.sleep(delay_s)
            graph = self.bid if thread_id.startswith("bid:") else self.conv
            await self._execute(user_id, graph, "bid" if graph is self.bid else "conversation", thread_id, None, None)

        asyncio.create_task(later())

    # ------------------------------------------------------------------ mirrors
    async def _sync_bid(self, user_id: str, thread_id: str, v: dict, status: str, interrupted: bool, latency: float) -> None:
        job = v.get("job") or {}
        job_id = v.get("job_id") or job.get("job_id")
        if not job_id:
            return
        async with SessionLocal() as s:
            row = (await s.execute(select(JobRecord).where(JobRecord.user_id == user_id, JobRecord.job_id == job_id))).scalar_one_or_none()
            if row is None:
                row = JobRecord(user_id=user_id, job_id=job_id, thread_id=thread_id)
                s.add(row)
            row.thread_id = thread_id
            row.title = (job.get("title") or row.title or "")[:300]
            row.category = job.get("category")
            if job:
                row.job = {k: job.get(k) for k in ("job_id", "title", "description", "skills", "category", "is_hourly", "budget",
                                                   "hourly_low", "hourly_high", "experience_level", "connects_cost", "client_id",
                                                   "posted_at", "source", "synthetic")}
            fit, risk, dec, price = v.get("fit") or {}, v.get("risk") or {}, v.get("decision") or {}, v.get("price") or {}
            row.fit_score = fit.get("score", row.fit_score)
            row.risk_score = risk.get("score", row.risk_score)
            row.is_scam = bool(risk.get("is_scam", row.is_scam))
            row.action = dec.get("action", row.action)
            row.price = price.get("amount", row.price)
            row.connects_cost = price.get("connects_cost") or job.get("connects_cost") or row.connects_cost
            row.status = status
            row.status_reason = v.get("status_reason") or ""
            row.snapshot = {k: v.get(k) for k in ("job_spec", "risk", "fit", "decision", "price", "critiques", "verifications",
                                                  "compliance", "preview", "approvals", "submission", "errors", "usage")}
            drafts = v.get("drafts") or []
            if drafts or v.get("submission"):
                card = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user_id, ProposalCard.job_id == job_id))).scalar_one_or_none()
                if card is None:
                    card = ProposalCard(user_id=user_id, job_id=job_id, thread_id=thread_id, title=row.title, category=row.category)
                    s.add(card)
                sub = v.get("submission") or {}
                if sub.get("proposal_id"):
                    card.proposal_id = sub["proposal_id"]
                    card.connects_spent = int(sub.get("connects_spent") or 0)
                    if card.stage in {"drafted", None}:
                        card.stage = "submitted"
                elif status == "rejected":
                    card.stage = "lost"
                card.strategy = drafts[-1].get("strategy", card.strategy) if drafts else card.strategy
                card.bid_amount = price.get("amount")
                card.cost_usd = round(total_usd(v.get("usage") or {}), 6)
                card.latency_s = round((card.latency_s or 0) + latency, 3)
            await s.commit()

    async def _sync_conversation(self, user_id: str, v: dict, status: str, interrupted: bool) -> None:
        mthread = v.get("marketplace_thread_id")
        if not mthread:
            return
        async with SessionLocal() as s:
            row = (await s.execute(select(Conversation).where(Conversation.user_id == user_id,
                                                              Conversation.marketplace_thread_id == mthread))).scalar_one_or_none()
            if row is None:
                return
            row.status = status
            row.intent = (v.get("intent") or {}).get("intent", row.intent)
            row.last_message_count = len(v.get("messages") or []) + (1 if v.get("sent") else 0)
            stage = v.get("pipeline_stage")
            if stage and row.proposal_id:
                card = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user_id,
                                                                   ProposalCard.proposal_id == row.proposal_id))).scalar_one_or_none()
                if card and stage in {"interview", "replied"}:
                    card.stage = stage
                    card.marketplace_thread_id = mthread
            await s.commit()
