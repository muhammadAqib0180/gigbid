"""GigSim adapter: REST client with timeouts, bounded exponential backoff + jitter on 429/5xx/network
errors, Retry-After support, and idempotency keys forwarded on every write."""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import httpx

from agent.settings import cfg
from mcp_servers.marketplace.adapters.base import MarketplaceError


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, freelancer_id: str, base_url: str | None = None, token: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.freelancer_id = freelancer_id
        self.base_url = (base_url or os.getenv("GIGSIM_BASE_URL", "http://localhost:8081")).rstrip("/")
        self.token = token or os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
        self.timeout = float(cfg("marketplace.request_timeout_s", 10))
        self.retries = int(cfg("marketplace.retries", 3))
        self.backoff = float(cfg("marketplace.backoff_base_s", 0.5))
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport,
                                 headers={"Authorization": f"Bearer {self.token}", "X-Freelancer-Id": self.freelancer_id})

    async def _req(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        last: MarketplaceError | None = None
        for attempt in range(self.retries + 1):
            try:
                async with self._client() as c:
                    r = await c.request(method, path, **kw)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
                last = MarketplaceError("unavailable", f"GigSim unreachable: {type(exc).__name__}")
            else:
                if r.status_code < 400:
                    return r.json()
                detail = (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else r.text) or ""
                if r.status_code == 429:
                    ra = float(r.headers.get("Retry-After", "2"))
                    last = MarketplaceError("rate_limited", str(detail), retry_after=ra, status=429)
                    await asyncio.sleep(min(ra, 8.0))
                    continue
                if r.status_code >= 500:
                    last = MarketplaceError("unavailable", str(detail), status=r.status_code)
                elif r.status_code == 404:
                    raise MarketplaceError("not_found", str(detail), status=404)
                elif r.status_code == 402:
                    raise MarketplaceError("insufficient_connects", str(detail), status=402)
                elif r.status_code == 422 and "policy" in str(detail):
                    raise MarketplaceError("policy", str(detail), status=422)
                elif r.status_code in (401, 403):
                    raise MarketplaceError("auth", str(detail), status=r.status_code)
                else:
                    raise MarketplaceError("invalid", str(detail), status=r.status_code)
            if attempt < self.retries:
                await asyncio.sleep(self.backoff * (2 ** attempt) * (0.5 + random.random()))
        assert last is not None
        raise last

    # ---------------------------------------------------------------- reads
    async def search_jobs(self, query: str = "", category: str | None = None, skills: list[str] | None = None,
                          min_budget: float | None = None, since_minutes: int | None = None, limit: int = 20) -> list[dict]:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        if skills:
            params["skills"] = ",".join(skills)
        if min_budget:
            params["min_budget"] = min_budget
        if since_minutes is not None:
            params["since_minutes"] = since_minutes
        return (await self._req("GET", "/v1/jobs/search", params=params))["jobs"]

    async def get_job(self, job_id: str) -> dict:
        return await self._req("GET", f"/v1/jobs/{job_id}")

    async def get_client_history(self, client_id: str) -> dict:
        return await self._req("GET", f"/v1/clients/{client_id}")

    async def get_connects_balance(self) -> dict:
        return await self._req("GET", "/v1/connects")

    async def get_market_stats(self, category: str) -> dict:
        return await self._req("GET", "/v1/market/stats", params={"category": category})

    async def get_policy(self) -> dict:
        return await self._req("GET", "/v1/policy")

    async def list_threads(self) -> list[dict]:
        return (await self._req("GET", "/v1/threads"))["threads"]

    async def list_messages(self, thread_id: str) -> list[dict]:
        return (await self._req("GET", f"/v1/threads/{thread_id}/messages"))["messages"]

    async def list_events(self, since: int = 0) -> list[dict]:
        return (await self._req("GET", "/v1/events", params={"since": since}))["events"]

    async def list_proposals(self) -> list[dict]:
        return (await self._req("GET", "/v1/proposals"))["proposals"]

    # ---------------------------------------------------------------- writes (idempotent)
    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        return await self._req("POST", "/v1/proposals", json={**payload, "idempotency_key": idempotency_key})

    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict:
        return await self._req("POST", f"/v1/proposals/{proposal_id}/submit", json={"idempotency_key": idempotency_key})

    async def send_message(self, thread_id: str, text: str, slots: list[dict] | None, idempotency_key: str) -> dict:
        return await self._req("POST", f"/v1/threads/{thread_id}/messages",
                               json={"text": text, "slots": slots or [], "idempotency_key": idempotency_key})

    async def health(self) -> dict:
        try:
            async with self._client() as c:
                r = await c.get("/health", timeout=3)
            return {"ok": r.status_code == 200, **(r.json() if r.status_code == 200 else {})}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": type(exc).__name__}
