"""Event bus for streaming to the UI: in-process asyncio fan-out, or Redis pub/sub when REDIS_URL is set
(worker and API are separate processes in docker compose)."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

_local: dict[str, set[asyncio.Queue]] = defaultdict(set)
_redis = None


def _r():
    global _redis
    if _redis is None and os.getenv("REDIS_URL"):
        import redis.asyncio as aioredis

        _redis = aioredis.Redis.from_url(os.environ["REDIS_URL"])
    return _redis


def channel(user_id: str) -> str:
    return f"gigbid:events:{user_id}"


async def publish(user_id: str, event: dict[str, Any]) -> None:
    r = _r()
    if r is not None:
        try:
            await r.publish(channel(user_id), json.dumps(event, default=str))
            return
        except Exception:  # noqa: BLE001 - fall back to local delivery
            pass
    for q in list(_local[channel(user_id)]):
        q.put_nowait(event)


def publish_health(server: str, ok: bool, detail: str) -> None:
    ev = {"type": "health", "server": server, "ok": ok, "detail": detail}
    for ch, qs in list(_local.items()):
        for q in list(qs):
            q.put_nowait(ev)


async def subscribe(user_id: str) -> AsyncIterator[dict[str, Any]]:
    r = _r()
    if r is not None:
        pubsub = r.pubsub()
        await pubsub.subscribe(channel(user_id))
        try:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    yield json.loads(msg["data"])
        finally:
            await pubsub.unsubscribe(channel(user_id))
            await pubsub.aclose()
    else:
        q: asyncio.Queue = asyncio.Queue()
        _local[channel(user_id)].add(q)
        try:
            while True:
                yield await q.get()
        finally:
            _local[channel(user_id)].discard(q)
