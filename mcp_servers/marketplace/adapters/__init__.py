"""Adapter selection by config (`marketplace.mode`): gigsim | upwork_live. Nothing else changes."""

from __future__ import annotations

from agent.settings import cfg
from mcp_servers.marketplace.adapters.base import MarketplaceAdapter, MarketplaceError
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

__all__ = ["MarketplaceAdapter", "MarketplaceError", "GigSimAdapter", "get_adapter"]


def get_adapter(user_id: str, persona: str, mode: str | None = None) -> MarketplaceAdapter:
    mode = mode or cfg("marketplace.mode", "gigsim")
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

        return UpworkLiveAdapter(user_id)
    return GigSimAdapter(freelancer_id=persona)
