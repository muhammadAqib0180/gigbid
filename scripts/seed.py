"""Seed the reviewer account (preloaded with a persona + saved searches).

Credentials come from REVIEWER_EMAIL / REVIEWER_PASSWORD (never committed). If REVIEWER_PASSWORD is unset,
a random one is generated and written to data/processed/reviewer_credentials.txt (git-ignored).

    python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import os
import secrets

from sqlalchemy import select

from agent.settings import processed_dir
from apps.api.auth.users import create_user, hash_password, verify_password
from apps.api.db import SavedSearch, SessionLocal, User, init_db

SEARCHES = {
    "ai_ml_engineer": [("LLM / RAG work", "llm", "ml_ai"), ("Machine learning models", "machine learning", "ml_ai"), ("AI chatbots", "chatbot", "ml_ai")],
    "fullstack_web": [("Next.js / React apps", "react", "web_dev"), ("Node APIs", "api", "web_dev"), ("SaaS builds", "saas", "web_dev")],
    "data_analyst": [("Dashboards", "dashboard", "data_analytics"), ("SQL analysis", "sql", "data_analytics"), ("Excel automation", "excel", "data_analytics")],
}


async def seed() -> dict:
    await init_db()
    email = os.getenv("REVIEWER_EMAIL", "reviewer@gigbid.app").lower()
    password = os.getenv("REVIEWER_PASSWORD")
    persona = os.getenv("REVIEWER_PERSONA", "ai_ml_engineer")
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if u:
            # a changed REVIEWER_PASSWORD takes effect on restart, also on persistent databases
            if password and not verify_password(password, u.password_hash):
                u.password_hash = hash_password(password)
                await s.commit()
                return {"email": email, "created": False, "password_updated": True}
            return {"email": email, "created": False}
        if password and len(password) < 8:
            print("WARNING: REVIEWER_PASSWORD is shorter than 8 characters; use 8+ for a public deployment")
        if not password:
            password = secrets.token_urlsafe(12)
            p = processed_dir() / "reviewer_credentials.txt"
            p.write_text(f"{email}\n{password}\n", encoding="utf-8")
            print(f"reviewer password written to {p}")
        u = await create_user(s, email, password, "Reviewer", persona, onboarded=True)
        for name, q, cat in SEARCHES[persona]:
            s.add(SavedSearch(user_id=u.id, name=name, query=q, category=cat, interval_minutes=30))
        await s.commit()
    return {"email": email, "created": True}


if __name__ == "__main__":
    print(asyncio.run(seed()))
