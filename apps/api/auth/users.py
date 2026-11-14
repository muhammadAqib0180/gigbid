"""Users and sessions: argon2 password hashes, signed httpOnly session cookie (JWT, APP_SECRET_KEY)."""

from __future__ import annotations

import os
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import User, UserSettings, get_session

SECRET = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")
COOKIE = "gigbid_session"
_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, h: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except VerifyMismatchError:
        return False


def session_token(user_id: str, ttl_s: int = 7 * 86400) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + ttl_s}, SECRET, algorithm="HS256")


async def current_user(session: AsyncSession = Depends(get_session), gigbid_session: str | None = Cookie(default=None),
                       authorization: str | None = Header(default=None)) -> User:
    token = gigbid_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "not signed in")
    try:
        uid = jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "invalid session") from exc
    user = await session.get(User, uid)
    if not user:
        raise HTTPException(401, "unknown user")
    return user


async def create_user(session: AsyncSession, email: str, password: str, display_name: str = "", persona_id: str = "ai_ml_engineer",
                      onboarded: bool = False) -> User:
    if (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none():
        raise HTTPException(409, "email already registered")
    u = User(email=email.lower(), password_hash=hash_password(password), display_name=display_name or email.split("@")[0],
             persona_id=persona_id, account_id=persona_id if not persona_id.startswith("user_") else "ai_ml_engineer", onboarded=onboarded)
    session.add(u)
    await session.flush()
    session.add(UserSettings(user_id=u.id))
    await session.commit()
    return u
