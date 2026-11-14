"""Where long work runs: the Arq worker when REDIS_URL is set (docker compose), otherwise an in-process
background loop in the API (`WORKER_MODE=inline`, for single-container hosts and laptops). Either way the
web request only enqueues and returns."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from worker import scheduler
from worker.runner import GraphRunner

log = logging.getLogger("gigbid.dispatch")


def worker_mode() -> str:
    m = os.getenv("WORKER_MODE")
    if m:
        return m
    return "arq" if os.getenv("REDIS_URL") else "inline"


class Dispatcher:
    def __init__(self, runner: GraphRunner) -> None:
        self.runner = runner
        self.mode = worker_mode()
        self._arq = None
        self._tasks: set[asyncio.Task] = set()
        self._stop = asyncio.Event()

    async def _pool(self):
        if self._arq is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            self._arq = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
        return self._arq

    def _bg(self, coro, limited: bool = False) -> None:
        """Background task. Bulk analysis runs are capped (INLINE_CONCURRENCY); human-triggered resumes are not,
        so an approval never waits behind a queue of new jobs."""
        if not hasattr(self, "_sem"):
            self._sem = asyncio.Semaphore(int(os.getenv("INLINE_CONCURRENCY", "2")))

        async def guarded():
            try:
                if limited:
                    async with self._sem:
                        await coro
                else:
                    await coro
            except Exception:  # noqa: BLE001
                log.exception("background run failed")

        t = asyncio.create_task(guarded())
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def run_bid(self, user_id: str, job_id: str, job: dict | None = None, force: bool = False) -> None:
        if self.mode == "arq":
            await (await self._pool()).enqueue_job("run_bid", user_id, job_id, job, _job_id=f"bid:{user_id}:{job_id}")
        else:
            self._bg(self.runner.start_bid(user_id, job_id, job, force=force), limited=True)

    async def resume(self, user_id: str, thread_id: str, decision: dict[str, Any]) -> None:
        if self.mode == "arq":
            await (await self._pool()).enqueue_job("resume_thread", user_id, thread_id, decision)
        else:
            self._bg(self.runner.resume(user_id, thread_id, decision))

    async def run_conversation(self, user_id: str, mthread: str, pid: str | None, job_id: str | None) -> None:
        if self.mode == "arq":
            await (await self._pool()).enqueue_job("run_conversation", user_id, mthread, pid, job_id)
        else:
            self._bg(self.runner.start_conversation(user_id, mthread, pid, job_id))

    async def replay(self, user_id: str, thread_id: str, checkpoint_id: str) -> None:
        if self.mode == "arq":
            await (await self._pool()).enqueue_job("replay", user_id, thread_id, checkpoint_id)
        else:
            self._bg(self.runner.replay(user_id, thread_id, checkpoint_id))

    async def scout_now(self, user_id: str) -> dict[str, int]:
        total = {"new": 0, "duplicates": 0}
        for search, user in await scheduler.due_searches(now=None):
            if user.id != user_id:
                continue
            r = await scheduler.run_search(self.runner, search, user, lambda u, j, job: self.run_bid(u, j, job))
            total["new"] += r.get("new", 0)
            total["duplicates"] += r.get("duplicates", 0)
        return total

    async def recover(self) -> int:
        """After a crash/restart (inline mode): re-queue jobs whose in-memory task was lost. Threads that were
        mid-run continue from their last checkpoint (start_bid never restarts an existing thread)."""
        from sqlalchemy import select

        from apps.api.db import JobRecord, SessionLocal

        async with SessionLocal() as s:
            rows = (await s.execute(select(JobRecord).where(JobRecord.status.in_(
                ["queued", "running", "analysing", "drafting", "waiting_marketplace"])))).scalars().all()
        for r in rows:
            await self.run_bid(r.user_id, r.job_id, r.job or None)
        return len(rows)

    # ---------------------------------------------------------------- inline background loop
    async def inline_loop(self) -> None:
        tick = int(os.getenv("SCHEDULER_TICK_SECONDS", "60"))
        while not self._stop.is_set():
            try:
                for search, user in await scheduler.due_searches():
                    await scheduler.run_search(self.runner, search, user, lambda u, j, job: self.run_bid(u, j, job))
                for user in await scheduler.all_users():
                    await scheduler.sync_user(self.runner, user, self.run_conversation)
            except Exception:  # noqa: BLE001
                log.exception("inline scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=tick)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
