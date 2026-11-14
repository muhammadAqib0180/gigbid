"""SSE bridge from LangGraph streams to the browser.

The worker (or inline runner) consumes `graph.astream(stream_mode=["custom"])`, stores every node event in
`run_events` and publishes it on the user's channel. `/api/runs/{thread}/stream` first replays stored events
(so a refresh never loses progress), then forwards live ones. `/api/events/stream` carries user-level events
(run started/finished, pipeline updates, degraded mode)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy import select

from apps.api import events
from apps.api.db import RunEvent, SessionLocal


async def run_stream(user_id: str, thread_id: str, after_id: int = 0) -> AsyncIterator[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(RunEvent).where(RunEvent.user_id == user_id, RunEvent.thread_id == thread_id,
                                                       RunEvent.id > after_id).order_by(RunEvent.id))).scalars().all()
    for r in rows:
        yield {"id": str(r.id), "event": "run_event",
               "data": json.dumps({"node": r.node, "event": r.event, "run_id": r.run_id, "ts": r.ts.isoformat(), **(r.payload or {})}, default=str)}
    async for ev in _with_heartbeat(events.subscribe(user_id)):
        if ev.get("type") == "heartbeat":
            yield {"event": "heartbeat", "data": "{}"}
        elif ev.get("thread_id") == thread_id or ev.get("type") in {"degraded", "health"}:
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev, default=str)}


async def user_stream(user_id: str) -> AsyncIterator[dict]:
    async for ev in _with_heartbeat(events.subscribe(user_id)):
        yield {"event": ev.get("type", "message"), "data": json.dumps(ev, default=str)}


async def _with_heartbeat(source: AsyncIterator[dict], every: float = 15.0) -> AsyncIterator[dict]:
    it = source.__aiter__()
    nxt = asyncio.ensure_future(it.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({nxt}, timeout=every)
            if nxt in done:
                try:
                    yield nxt.result()
                except StopAsyncIteration:
                    return
                nxt = asyncio.ensure_future(it.__anext__())
            else:
                yield {"type": "heartbeat"}
    finally:
        nxt.cancel()
