"""Settings: autonomy, budgets, rates, saved searches, memory viewer (see and delete what GigBid learned),
and the dependency health used by the degraded-mode banner."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm import active_profile
from agent.mcp_client import health_snapshot, probe
from agent.memory.store import delete_memory, list_memory
from agent.settings import cfg
from apps.api.auth.users import current_user
from apps.api.db import SavedSearch, User, UserSettings, get_session
from apps.api.deps import iso
from apps.api.dispatch import worker_mode
from apps.api.schemas import HealthOut, MemoryOut, OkOut, SavedSearchIn, SavedSearchOut, SettingsIn, SettingsOut

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
async def get_settings(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> SettingsOut:
    st = await s.get(UserSettings, user.id)
    return SettingsOut(hourly_rate_usd=st.hourly_rate_usd, min_hourly_usd=st.min_hourly_usd, min_fixed_usd=st.min_fixed_usd,
                       weekly_connects=st.weekly_connects, autonomy=st.autonomy, max_tokens_per_job=st.max_tokens_per_job,
                       proposal_strategy=st.proposal_strategy, marketplace_mode=user.marketplace_mode, persona_id=user.persona_id,
                       account_id=user.account_id)


@router.put("/settings", response_model=SettingsOut)
async def put_settings(body: SettingsIn, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> SettingsOut:
    st = await s.get(UserSettings, user.id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(st, k, v)
    await s.commit()
    return await get_settings(user, s)


@router.get("/saved-searches", response_model=list[SavedSearchOut])
async def list_searches(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> list[SavedSearchOut]:
    rows = (await s.execute(select(SavedSearch).where(SavedSearch.user_id == user.id))).scalars().all()
    return [SavedSearchOut(id=r.id, name=r.name, query=r.query, category=r.category, skills=r.skills or [], min_budget=r.min_budget,
                           interval_minutes=r.interval_minutes, enabled=r.enabled, last_run_at=iso(r.last_run_at), next_run_at=iso(r.next_run_at))
            for r in rows]


@router.post("/saved-searches", response_model=OkOut)
async def add_search(body: SavedSearchIn, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> OkOut:
    s.add(SavedSearch(user_id=user.id, **body.model_dump()))
    await s.commit()
    return OkOut()


@router.delete("/saved-searches/{search_id}", response_model=OkOut)
async def delete_search(search_id: str, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> OkOut:
    r = await s.get(SavedSearch, search_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "not found")
    await s.delete(r)
    await s.commit()
    return OkOut()


@router.get("/memory", response_model=MemoryOut)
async def memory(request: Request, user: User = Depends(current_user)) -> MemoryOut:
    m = await list_memory(request.app.state.store, user.id)
    return MemoryOut(style=m.get("style", []), style_candidates=m.get("style_candidates", []), outcome=m.get("outcome", []))


@router.delete("/memory/{namespace}/{key:path}", response_model=OkOut)
async def forget(namespace: str, key: str, request: Request, user: User = Depends(current_user)) -> OkOut:
    if namespace not in {"style", "style_candidates", "outcome"}:
        raise HTTPException(422, "unknown namespace")
    await delete_memory(request.app.state.store, user.id, namespace, key)
    return OkOut(detail=f"deleted {namespace}/{key}")


@router.get("/health/dependencies", response_model=HealthOut)
async def dependencies() -> HealthOut:
    snap = health_snapshot()
    if "marketplace" not in snap:
        await probe("marketplace")
        snap = health_snapshot()
    mk = snap.get("marketplace", {"ok": True})
    return HealthOut(status="ok" if mk.get("ok", True) else "degraded", marketplace=mk, servers=snap, worker_mode=worker_mode(),
                     model_profile=active_profile(), marketplace_mode=str(cfg("marketplace.mode")))


@router.get("/health", response_model=dict)
async def health() -> dict:
    return {"status": "ok", "service": "gigbid-api", "version": os.getenv("GIT_SHA", "dev")}
