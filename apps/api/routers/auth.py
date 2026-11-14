"""Sign-in, sign-up, onboarding (persona or own profile, marketplace, rates, Connects budget, saved searches),
portfolio upload (incremental re-index) and connected accounts (Upwork OAuth)."""

from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.settings import data_dir
from apps.api.auth.token_store import has_secret
from apps.api.auth.users import COOKIE, create_user, current_user, session_token, verify_password
from apps.api.db import SavedSearch, User, UserSettings, get_session
from apps.api.schemas import LoginIn, OkOut, OnboardingIn, SignupIn, UserOut

router = APIRouter(prefix="/api", tags=["auth"])
PERSONAS = ["ai_ml_engineer", "fullstack_web", "data_analyst"]


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, persona_id=u.persona_id, account_id=u.account_id,
                   marketplace_mode=u.marketplace_mode, onboarded=u.onboarded)


def _set_cookie(resp: Response, user_id: str) -> None:
    resp.set_cookie(COOKIE, session_token(user_id), httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "0") == "1",
                    max_age=7 * 86400, path="/")


@router.post("/auth/signup", response_model=UserOut)
async def signup(body: SignupIn, response: Response, s: AsyncSession = Depends(get_session)) -> UserOut:
    if os.getenv("ALLOW_SIGNUP", "1") != "1":
        raise HTTPException(403, "sign-up is disabled on this deployment")
    u = await create_user(s, body.email, body.password, body.display_name)
    _set_cookie(response, u.id)
    return user_out(u)


@router.post("/auth/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, s: AsyncSession = Depends(get_session)) -> UserOut:
    u = (await s.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "wrong email or password")
    _set_cookie(response, u.id)
    return user_out(u)


@router.post("/auth/logout", response_model=OkOut)
async def logout(response: Response) -> OkOut:
    response.delete_cookie(COOKIE, path="/")
    return OkOut()


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post("/onboarding", response_model=UserOut)
async def onboarding(body: OnboardingIn, user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> UserOut:
    u = await s.get(User, user.id)
    if body.profile == "persona":
        if body.persona_id not in PERSONAS:
            raise HTTPException(422, "unknown persona")
        u.persona_id = body.persona_id
        u.account_id = body.persona_id
    else:
        u.persona_id = f"user_{u.id}"
        u.account_id = body.account_id if body.account_id in PERSONAS else "ai_ml_engineer"
        d = data_dir() / "personas" / u.persona_id
        (d / "uploads").mkdir(parents=True, exist_ok=True)
        import json

        (d / "profile.json").write_text(json.dumps({"persona_id": u.persona_id, "display_name": u.display_name,
                                                    "hourly_rate_usd": body.hourly_rate_usd, "min_hourly_usd": body.min_hourly_usd,
                                                    "min_fixed_usd": body.min_fixed_usd, "weekly_connects": body.weekly_connects,
                                                    "categories": []}), encoding="utf-8")
    u.marketplace_mode = body.marketplace_mode
    u.onboarded = True
    st = await s.get(UserSettings, u.id)
    st.hourly_rate_usd, st.min_hourly_usd, st.min_fixed_usd = body.hourly_rate_usd, body.min_hourly_usd, body.min_fixed_usd
    st.weekly_connects = body.weekly_connects
    for ss in body.saved_searches:
        s.add(SavedSearch(user_id=u.id, **ss.model_dump()))
    await s.commit()
    return user_out(u)


@router.post("/portfolio/upload", response_model=OkOut)
async def upload_portfolio(file: UploadFile = File(...), user: User = Depends(current_user)) -> OkOut:
    """Add work to the portfolio (Markdown / text / PDF). The persona index is invalidated and rebuilt
    incrementally (unchanged chunks reuse cached embeddings)."""
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "file too large (2 MB max)")
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", (file.filename or "upload").rsplit(".", 1)[0])[:60] or uuid.uuid4().hex[:8]
    if (file.filename or "").lower().endswith(".pdf"):
        import pymupdf

        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            text = "\n".join(p.get_text() for p in pdf)
    else:
        text = raw.decode("utf-8", errors="replace")
    d = data_dir() / "personas" / user.persona_id / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(f"---\ntitle: {name}\ntype: user_upload\nproject: {name}\n---\n\n{text}", encoding="utf-8")
    from rag.index.corpus import invalidate

    invalidate(user.persona_id)
    return OkOut(detail=f"added {name}; index will refresh on next retrieval")


@router.get("/accounts", response_model=dict)
async def accounts(user: User = Depends(current_user)) -> dict:
    return {"gigsim": {"connected": True, "account": user.account_id},
            "upwork": {"connected": await has_secret(user.id, "upwork_tokens"), "mode": user.marketplace_mode},
            "github": {"connected": bool(os.getenv("GITHUB_PAT"))}}


_PENDING_OAUTH: dict[str, dict] = {}


@router.post("/accounts/upwork/connect", response_model=dict)
async def upwork_connect(user: User = Depends(current_user)) -> dict:
    """Starts the OAuth 2.1 flow with the official Upwork MCP server; returns the authorisation URL to open."""
    import asyncio

    from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter, oauth_provider

    loop = asyncio.get_running_loop()
    url_fut: asyncio.Future = loop.create_future()
    code_fut: asyncio.Future = loop.create_future()

    async def redirect_handler(url: str) -> None:
        if not url_fut.done():
            url_fut.set_result(url)

    async def callback_handler() -> tuple[str, str | None]:
        return await code_fut

    state_key = uuid.uuid4().hex
    _PENDING_OAUTH[state_key] = {"user": user.id, "code": code_fut}
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from agent.settings import cfg

    client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": cfg("marketplace.upwork.url"),
                                              "auth": oauth_provider(user.id, redirect_handler, callback_handler)}})
    task = asyncio.create_task(UpworkLiveAdapter(user.id, client).health())
    try:
        url = await asyncio.wait_for(url_fut, timeout=20)
    except TimeoutError as exc:
        task.cancel()
        raise HTTPException(502, "Upwork MCP did not start an OAuth flow (check network / registration)") from exc
    _PENDING_OAUTH[state_key]["task"] = task
    return {"authorization_url": url, "pending": state_key}


@router.get("/accounts/upwork/callback")
async def upwork_callback(request: Request, code: str, state: str | None = None):
    for _k, p in list(_PENDING_OAUTH.items()):
        if not p["code"].done():
            p["code"].set_result((code, state))
            break
    return RedirectResponse(url=os.getenv("WEB_URL", "/") + "/settings?upwork=connected")
