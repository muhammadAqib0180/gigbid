"""Agent run viewer: live node-by-node progress (SSE), stored events, checkpoint history (replay any job from
any node), the graph rendered from code, and the trace link."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from agent.tracing import langsmith_url
from apps.api.auth.users import current_user
from apps.api.db import Run, RunEvent, User, get_session
from apps.api.deps import dispatcher, iso, runner
from apps.api.dispatch import Dispatcher
from apps.api.schemas import CheckpointOut, OkOut, ReplayIn, RunDetail, RunEventOut, RunOut
from apps.api.streaming import run_stream, user_stream
from worker.runner import GraphRunner

router = APIRouter(prefix="/api", tags=["runs"])


def run_out(r: Run) -> RunOut:
    return RunOut(id=r.id, thread_id=r.thread_id, kind=r.kind, job_id=r.job_id, trace_id=r.trace_id, status=r.status, tokens=r.tokens,
                  cost_usd=r.cost_usd, latency_s=r.latency_s, error=r.error or "", started_at=iso(r.started_at) or "",
                  finished_at=iso(r.finished_at), trace_url=langsmith_url(r.trace_id))


@router.get("/runs", response_model=list[RunOut])
async def recent_runs(limit: int = 50, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> list[RunOut]:
    rows = (await s.execute(select(Run).where(Run.user_id == user.id).order_by(Run.started_at.desc()).limit(min(limit, 200)))).scalars().all()
    return [run_out(r) for r in rows]


@router.get("/events/stream")
async def stream_user_events(user: User = Depends(current_user)):
    return EventSourceResponse(user_stream(user.id), ping=20)


@router.get("/runs/{thread_id:path}/stream")
async def stream_run(thread_id: str, after: int = 0, user: User = Depends(current_user)):
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    return EventSourceResponse(run_stream(user.id, thread_id, after), ping=20)


@router.post("/runs/{thread_id:path}/replay", response_model=OkOut)
async def replay(thread_id: str, body: ReplayIn, user: User = Depends(current_user), d: Dispatcher = Depends(dispatcher)) -> OkOut:
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    await d.replay(user.id, thread_id, body.checkpoint_id)
    return OkOut(detail="replaying from checkpoint")


@router.get("/runs/{thread_id:path}", response_model=RunDetail)
async def run_detail(thread_id: str, user: User = Depends(current_user), s: AsyncSession = Depends(get_session),
                     r: GraphRunner = Depends(runner)) -> RunDetail:
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    runs = (await s.execute(select(Run).where(Run.user_id == user.id, Run.thread_id == thread_id).order_by(Run.started_at))).scalars().all()
    evs = (await s.execute(select(RunEvent).where(RunEvent.user_id == user.id, RunEvent.thread_id == thread_id).order_by(RunEvent.id))).scalars().all()
    graph = r.bid if thread_id.startswith("bid:") else r.conv
    cps: list[CheckpointOut] = []
    async for snap in graph.aget_state_history({"configurable": {"thread_id": thread_id}}, limit=60):
        md = snap.metadata or {}
        writes = md.get("writes") or {}
        cps.append(CheckpointOut(checkpoint_id=snap.config["configurable"]["checkpoint_id"], step=md.get("step"),
                                 node=", ".join(writes.keys()) if isinstance(writes, dict) and writes else md.get("source"),
                                 next=list(snap.next), created_at=snap.created_at))
    # newest first: the node(s) that produced checkpoint i are the `next` of the older checkpoint i+1
    for i in range(len(cps) - 1):
        if cps[i + 1].next:
            cps[i].node = ", ".join(cps[i + 1].next)
    return RunDetail(thread_id=thread_id, runs=[run_out(x) for x in runs],
                     events=[RunEventOut(id=e.id, run_id=e.run_id, ts=iso(e.ts) or "", node=e.node, event=e.event, payload=e.payload or {}) for e in evs],
                     checkpoints=cps, graph_mermaid=graph.get_graph().draw_mermaid())
