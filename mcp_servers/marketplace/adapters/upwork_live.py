"""Live Upwork adapter (A4): the official Upwork MCP server over Streamable HTTP, OAuth 2.1 (PKCE) via
the MCP SDK's OAuthClientProvider, tokens stored encrypted per user (apps/api/auth/token_store.py).

Rules enforced here (and in docs/RUNBOOK.md):
* Only the official MCP endpoint (https://mcp.upwork.com/mcp). No browser automation, cookies or scraping.
* Writes are DRAFTS only. `submit_proposal` maps to Upwork's draft tool; the user confirms on Upwork.
* Tool names come from config marketplace.upwork.tool_map, so a rename upstream is a config edit.
* Reads are rate-limited by the server-wide limiter and the scheduler's live interval (120 min default).

This adapter is unit-tested against a fake MCP server with Upwork-shaped tools
(mcp_servers/marketplace/tests/test_upwork_adapter.py). It has NOT been exercised against a real
Upwork account in this repository (no account available to the author at submission time).
"""

from __future__ import annotations

import json
import os
from typing import Any

from agent.settings import cfg
from mcp_servers.marketplace.adapters.base import MarketplaceError


class EncryptedTokenStorage:
    """mcp.client.auth.TokenStorage backed by the API's encrypted per-user token table."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        from apps.api.auth.token_store import load_secret

        raw = await load_secret(self.user_id, "upwork_tokens")
        return OAuthToken.model_validate_json(raw) if raw else None

    async def set_tokens(self, tokens) -> None:
        from apps.api.auth.token_store import save_secret

        await save_secret(self.user_id, "upwork_tokens", tokens.model_dump_json())

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        from apps.api.auth.token_store import load_secret

        raw = await load_secret(self.user_id, "upwork_client")
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def set_client_info(self, info) -> None:
        from apps.api.auth.token_store import save_secret

        await save_secret(self.user_id, "upwork_client", info.model_dump_json())


def oauth_provider(user_id: str, redirect_handler=None, callback_handler=None):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    redirect_uri = os.getenv("UPWORK_REDIRECT_URI", "http://localhost:8000/api/accounts/upwork/callback")
    return OAuthClientProvider(
        server_url=cfg("marketplace.upwork.url"),
        client_metadata=OAuthClientMetadata(client_name="GigBid", redirect_uris=[redirect_uri],
                                            grant_types=["authorization_code", "refresh_token"], response_types=["code"]),
        storage=EncryptedTokenStorage(user_id), redirect_handler=redirect_handler, callback_handler=callback_handler)


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, user_id: str, client: Any | None = None) -> None:
        self.user_id = user_id
        self.tool_map: dict[str, str] = cfg("marketplace.upwork.tool_map", {}) or {}
        self._client = client       # injected in tests (a MultiServerMCPClient pointing at a fake server)

    def _mcp(self):
        if self._client is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            self._client = MultiServerMCPClient({"upwork": {
                "transport": "streamable_http", "url": cfg("marketplace.upwork.url"), "auth": oauth_provider(self.user_id)}})
        return self._client

    async def _call(self, port_method: str, args: dict[str, Any]) -> Any:
        tool = self.tool_map.get(port_method)
        if not tool:
            raise MarketplaceError("invalid", f"no Upwork tool mapped for {port_method}")
        try:
            async with self._mcp().session("upwork") as s:
                res = await s.call_tool(tool, args)
        except MarketplaceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MarketplaceError("unavailable", f"Upwork MCP: {type(exc).__name__}: {str(exc)[:160]}") from exc
        if res.isError:
            raise MarketplaceError("invalid", " ".join(getattr(c, "text", "") for c in res.content)[:300])
        if res.structuredContent is not None:
            return res.structuredContent
        text = " ".join(getattr(c, "text", "") for c in res.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    @staticmethod
    def _norm_job(j: dict) -> dict:
        return {
            "job_id": str(j.get("id") or j.get("job_id") or j.get("ciphertext") or ""),
            "title": j.get("title", ""), "description": j.get("description") or j.get("snippet") or "",
            "skills": [s.get("name", s) if isinstance(s, dict) else s for s in j.get("skills", [])],
            "category": j.get("category"), "is_hourly": str(j.get("type", j.get("job_type", ""))).lower().startswith("hour"),
            "budget": (j.get("budget") or {}).get("amount") if isinstance(j.get("budget"), dict) else j.get("budget"),
            "hourly_low": j.get("hourly_min") or j.get("hourlyBudgetMin"), "hourly_high": j.get("hourly_max") or j.get("hourlyBudgetMax"),
            "experience_level": j.get("experience_level") or j.get("contractorTier"),
            "connects_cost": j.get("connects_cost") or j.get("connectPrice"), "client_id": str(j.get("client_id") or (j.get("client") or {}).get("id") or ""),
            "posted_at": j.get("posted_at") or j.get("createdDateTime"), "source": "upwork_live", "synthetic": False,
        }

    async def search_jobs(self, query: str = "", category: str | None = None, skills: list[str] | None = None,
                          min_budget: float | None = None, since_minutes: int | None = None, limit: int = 20) -> list[dict]:
        out = await self._call("search_jobs", {"query": query, "limit": limit, **({"category": category} if category else {})})
        jobs = out.get("jobs", out if isinstance(out, list) else []) if isinstance(out, (dict, list)) else []
        return [self._norm_job(j) for j in jobs][:limit]

    async def get_job(self, job_id: str) -> dict:
        return self._norm_job(await self._call("get_job", {"job_id": job_id}))

    async def get_client_history(self, client_id: str) -> dict:
        c = await self._call("get_client_history", {"client_id": client_id})
        return {"client_id": client_id, "country": c.get("country"), "payment_verified": bool(c.get("payment_verified") or c.get("paymentVerified")),
                "total_spent": float(c.get("total_spent") or c.get("totalSpent") or 0), "rating": c.get("rating"),
                "reviews_count": int(c.get("reviews_count") or c.get("feedbackCount") or 0), "jobs_posted": int(c.get("jobs_posted") or 0),
                "hires": int(c.get("hires") or 0), "hire_rate": float(c.get("hire_rate") or 0)}

    async def get_connects_balance(self) -> dict:
        c = await self._call("get_connects_balance", {})
        return {"balance": int(c.get("balance") or c.get("connects") or 0), "spent": 0}

    async def get_market_stats(self, category: str) -> dict:
        return {"category": category}   # Upwork exposes no market statistics; pricing falls back to GigSim/Kaggle stats

    async def get_policy(self) -> dict:
        return {"version": "upwork-live", "required_disclosures": cfg("bidding_rules.proposal.required_disclosures", [])}

    async def list_threads(self) -> list[dict]:
        out = await self._call("list_messages", {})
        return out.get("threads", []) if isinstance(out, dict) else []

    async def list_messages(self, thread_id: str) -> list[dict]:
        out = await self._call("list_messages", {"thread_id": thread_id})
        return out.get("messages", []) if isinstance(out, dict) else []

    async def list_events(self, since: int = 0) -> list[dict]:
        return []

    async def list_proposals(self) -> list[dict]:
        return []

    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        out = await self._call("create_proposal_draft", {"job_id": payload["job_id"], "cover_letter": payload["cover_letter"],
                                                         "bid_amount": payload.get("bid_amount")})
        return {"proposal_id": str(out.get("id") or out.get("proposal_id") or idempotency_key), "status": "draft_on_upwork",
                "connects_cost": int(out.get("connects_cost") or 0)}

    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict:
        # Never submits. The draft already exists on Upwork; the user must confirm it there.
        return {"proposal_id": proposal_id, "status": "awaiting_confirmation_on_upwork", "connects_spent": 0,
                "note": "Live mode creates drafts only. Open Upwork to confirm and submit."}

    async def send_message(self, thread_id: str, text: str, slots: list[dict] | None, idempotency_key: str) -> dict:
        out = await self._call("send_message", {"thread_id": thread_id, "text": text})
        return {"message_id": str(out.get("id") or idempotency_key), "thread_id": thread_id, "status": "draft_on_upwork"}

    async def health(self) -> dict:
        try:
            await self._call("get_connects_balance", {})
            return {"ok": True}
        except MarketplaceError as exc:
            return {"ok": False, "error": exc.kind}
