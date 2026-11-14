"""Job inbox (ranked by fit, risk badges, action, price, Connects) and job detail (JobSpec, risk report,
requirement-to-evidence matrix, price rationale, bid/skip reasoning)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.users import current_user
from apps.api.db import JobRecord, User, get_session
from apps.api.deps import dispatcher, iso
from apps.api.dispatch import Dispatcher
from apps.api.schemas import JobDetail, JobSummary, OkOut

router = APIRouter(prefix="/api", tags=["jobs"])


def summary(r: JobRecord) -> JobSummary:
    snap = r.snapshot or {}
    return JobSummary(job_id=r.job_id, thread_id=r.thread_id, title=r.title, category=r.category, fit_score=r.fit_score,
                      risk_score=r.risk_score, is_scam=r.is_scam, risk_flags=((snap.get("risk") or {}).get("flags") or [])[:6],
                      action=r.action, price=r.price, price_unit=(snap.get("price") or {}).get("unit"), connects_cost=r.connects_cost,
                      status=r.status, status_reason=r.status_reason or "", duplicate_of=r.duplicate_of,
                      budget=(r.job or {}).get("budget"), is_hourly=bool((r.job or {}).get("is_hourly")), source=(r.job or {}).get("source"),
                      updated_at=iso(r.updated_at) or "")


@router.get("/jobs", response_model=list[JobSummary])
async def inbox(action: str | None = None, status: str | None = None, q: str | None = None, min_fit: float | None = Query(None, ge=0, le=1),
                include_skipped: bool = True, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> list[JobSummary]:
    stmt = select(JobRecord).where(JobRecord.user_id == user.id)
    if action:
        stmt = stmt.where(JobRecord.action == action)
    if status:
        stmt = stmt.where(JobRecord.status == status)
    if not include_skipped:
        stmt = stmt.where(JobRecord.status.not_in(["skipped", "duplicate"]))
    rows = (await s.execute(stmt.limit(500))).scalars().all()
    out = [summary(r) for r in rows if (not q or q.lower() in r.title.lower()) and (min_fit is None or (r.fit_score or 0) >= min_fit)]
    pri = {"awaiting_approval": 0, "drafting": 1, "analysing": 1, "running": 1, "queued": 2, "watching": 3, "submitted": 4}
    out.sort(key=lambda j: (pri.get(j.status, 5), -(j.fit_score or 0)))
    return out


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> JobDetail:
    r = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id, JobRecord.job_id == job_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "job not found")
    snap = r.snapshot or {}
    fit = snap.get("fit") or {}
    matrix = [{"requirement_id": m.get("requirement_id"), "requirement": m.get("requirement"), "covered": m.get("covered"),
               "best_score": m.get("best_score"), "evidence_ids": m.get("evidence_ids"), "item_ids": m.get("item_ids")}
              for m in fit.get("matches", [])]
    return JobDetail(**summary(r).model_dump(), job=r.job or {}, job_spec=snap.get("job_spec"), risk=snap.get("risk"), fit=fit or None,
                     decision=snap.get("decision"), price_quote=snap.get("price"), evidence_matrix=matrix, submission=snap.get("submission"),
                     errors=snap.get("errors") or [])


@router.post("/jobs/{job_id}/analyze", response_model=OkOut)
async def analyze(job_id: str, force: bool = False, user: User = Depends(current_user), d: Dispatcher = Depends(dispatcher),
                  s: AsyncSession = Depends(get_session)) -> OkOut:
    r = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id, JobRecord.job_id == job_id))).scalar_one_or_none()
    if r is None:
        s.add(JobRecord(user_id=user.id, job_id=job_id, thread_id=f"bid:{user.id}:{job_id}", status="queued"))
    else:
        r.status = "queued"
    await s.commit()
    await d.run_bid(user.id, job_id, (r.job if r and r.job else None), force=force)
    return OkOut(detail="queued")


@router.post("/jobs/{job_id}/skip", response_model=OkOut)
async def skip(job_id: str, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> OkOut:
    r = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id, JobRecord.job_id == job_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "job not found")
    r.status, r.action, r.status_reason = "skipped", "skip", "skipped by you"
    await s.commit()
    return OkOut()


@router.post("/scout", response_model=dict)
async def scout_now(user: User = Depends(current_user), d: Dispatcher = Depends(dispatcher)) -> dict:
    """Run every saved search now (normally they run on their own schedule in the worker)."""
    from sqlalchemy import update

    from apps.api.db import SavedSearch, SessionLocal

    async with SessionLocal() as s:
        await s.execute(update(SavedSearch).where(SavedSearch.user_id == user.id).values(next_run_at=None))
        await s.commit()
    return await d.scout_now(user.id)
