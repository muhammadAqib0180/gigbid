"""Arq worker (E1): long agent runs and schedules execute here, never inside web requests.

    arq worker.main.WorkerSettings

Jobs are idempotent: one bid thread per (user, job) with a deterministic thread id + Arq `_job_id`, a
checkpointed graph that resumes rather than restarts, and idempotency keys on every marketplace write - so a
worker restart never double-analyses or double-submits.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from agent.persistence import persistence
from worker import scheduler
from worker.runner import GraphRunner

log = logging.getLogger("gigbid.worker")


async def startup(ctx: dict[str, Any]) -> None:
    from apps.api.db import init_db

    await init_db()
    ctx["_pers"] = persistence()
    cp, store = await ctx["_pers"].__aenter__()

    async def defer(user_id: str, thread_id: str, delay_s: float) -> None:
        await ctx["redis"].enqueue_job("resume_after_outage", user_id, thread_id, _defer_by=delay_s,
                                       _job_id=f"retry:{thread_id}:{int(delay_s)}")

    ctx["runner"] = GraphRunner(cp, store, defer=defer)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["_pers"].__aexit__(None, None, None)


async def run_bid(ctx: dict[str, Any], user_id: str, job_id: str, job: dict | None = None) -> str:
    return await ctx["runner"].start_bid(user_id, job_id, job)


async def resume_thread(ctx: dict[str, Any], user_id: str, thread_id: str, decision: dict) -> None:
    await ctx["runner"].resume(user_id, thread_id, decision)


async def resume_after_outage(ctx: dict[str, Any], user_id: str, thread_id: str) -> None:
    r: GraphRunner = ctx["runner"]
    graph = r.bid if thread_id.startswith("bid:") else r.conv
    await r._execute(user_id, graph, "bid" if graph is r.bid else "conversation", thread_id, None, None)


async def run_conversation(ctx: dict[str, Any], user_id: str, mthread: str, proposal_id: str | None, job_id: str | None) -> str:
    return await ctx["runner"].start_conversation(user_id, mthread, proposal_id, job_id)


async def replay(ctx: dict[str, Any], user_id: str, thread_id: str, checkpoint_id: str) -> None:
    await ctx["runner"].replay(user_id, thread_id, checkpoint_id)


async def scout_tick(ctx: dict[str, Any]) -> None:
    async def enqueue_bid(user_id: str, job_id: str, job: dict) -> None:
        await ctx["redis"].enqueue_job("run_bid", user_id, job_id, job, _job_id=f"bid:{user_id}:{job_id}")

    for search, user in await scheduler.due_searches():
        await scheduler.run_search(ctx["runner"], search, user, enqueue_bid)


async def sync_tick(ctx: dict[str, Any]) -> None:
    async def enqueue_conv(user_id: str, mthread: str, pid: str | None, job_id: str | None) -> None:
        await ctx["redis"].enqueue_job("run_conversation", user_id, mthread, pid, job_id)

    for user in await scheduler.all_users():
        await scheduler.sync_user(ctx["runner"], user, enqueue_conv)


class WorkerSettings:
    functions = [run_bid, resume_thread, resume_after_outage, run_conversation, replay]
    cron_jobs = [cron(scout_tick, second=0), cron(sync_tick, second={15, 45})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = int(os.getenv("WORKER_CONCURRENCY", "4"))
    job_timeout = 900
    keep_result = 3600
