"""Regression: a scheduled scout and a "Scout now" click can process the same job at the same moment. Before the fix the
second insert raised IntegrityError (UNIQUE jobs.user_id, jobs.job_id) and /api/scout returned 500."""

from __future__ import annotations

import asyncio

import pytest

from apps.api.db import JobRecord, SessionLocal, init_db


@pytest.mark.asyncio
async def test_concurrent_scouts_create_one_row_and_queue_once():
    from sqlalchemy import func, select

    from apps.api.auth.users import create_user
    from worker import scheduler

    await init_db()
    async with SessionLocal() as s:
        user = await create_user(s, "race@example.test", "race-test-password", persona_id="ai_ml_engineer")
    job = {"job_id": "race_job_1", "title": "Same job seen twice", "category": "ml_ai", "description": "x"}

    async def one_scout() -> bool:
        async with SessionLocal() as s:
            created = await scheduler._insert_job_once(s, user.id, job, status="queued")
            await s.commit()
            return created

    results = await asyncio.gather(*(one_scout() for _ in range(4)))
    assert results.count(True) == 1                      # exactly one caller queues the analysis
    async with SessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(JobRecord).where(JobRecord.user_id == user.id,
                                                                              JobRecord.job_id == "race_job_1"))).scalar_one()
    assert n == 1
