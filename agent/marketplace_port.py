"""The single marketplace interface used by the graphs (R1).

`MarketplacePort` is the protocol; `McpMarketplacePort` is the only implementation the agents use: it calls
the Marketplace MCP server, which in turn selects the GigSim or live-Upwork adapter from config
(`marketplace.mode`). Switching to live mode therefore changes config only - no graph or node code.
"""

from __future__ import annotations

from typing import Any, Protocol

from agent.mcp_client import ToolGateway


class MarketplacePort(Protocol):
    async def search_jobs(self, query: str, **filters: Any) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def get_market_stats(self, category: str) -> dict[str, Any]: ...
    async def list_threads(self) -> list[dict[str, Any]]: ...
    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]: ...
    async def list_events(self, since: int) -> list[dict[str, Any]]: ...
    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str, dry_run: bool = False) -> dict[str, Any]: ...
    async def submit_proposal(self, proposal_id: str, idempotency_key: str, dry_run: bool = False) -> dict[str, Any]: ...
    async def send_message(self, thread_id: str, text: str, idempotency_key: str, slots: list[dict] | None = None,
                           dry_run: bool = False) -> dict[str, Any]: ...


class McpMarketplacePort:
    """Calls go through the agent's allowlist: e.g. the Writer cannot reach `submit_proposal`."""

    def __init__(self, gateway: ToolGateway, agent: str) -> None:
        self.gw = gateway
        self.agent = agent

    async def _c(self, tool: str, **args: Any) -> dict[str, Any]:
        return await self.gw.call(self.agent, "marketplace", tool, args)

    async def search_jobs(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return (await self._c("search_jobs", query=query, **filters))["jobs"]

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self._c("get_job", job_id=job_id)

    async def get_client_history(self, client_id: str) -> dict[str, Any]:
        return await self._c("get_client_history", client_id=client_id)

    async def get_connects_balance(self) -> dict[str, Any]:
        return await self._c("get_connects_balance")

    async def get_market_stats(self, category: str) -> dict[str, Any]:
        return await self._c("get_market_stats", category=category or "other")

    async def list_threads(self) -> list[dict[str, Any]]:
        return (await self._c("list_threads"))["threads"]

    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return (await self._c("list_messages", thread_id=thread_id))["messages"]

    async def list_events(self, since: int = 0) -> list[dict[str, Any]]:
        return (await self._c("list_events", since=since))["events"]

    async def create_proposal_draft(self, payload: dict[str, Any], idempotency_key: str, dry_run: bool = False) -> dict[str, Any]:
        return await self._c("create_proposal_draft", **payload, idempotency_key=idempotency_key, dry_run=dry_run)

    async def submit_proposal(self, proposal_id: str, idempotency_key: str, dry_run: bool = False) -> dict[str, Any]:
        return await self._c("submit_proposal", proposal_id=proposal_id, idempotency_key=idempotency_key, dry_run=dry_run)

    async def send_message(self, thread_id: str, text: str, idempotency_key: str, slots: list[dict] | None = None,
                           dry_run: bool = False) -> dict[str, Any]:
        return await self._c("send_message", thread_id=thread_id, text=text, slots=slots, idempotency_key=idempotency_key,
                             dry_run=dry_run)
