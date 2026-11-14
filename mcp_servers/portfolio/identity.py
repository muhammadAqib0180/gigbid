"""Tenant resolution: inside GigBid the persona comes from the verified bearer token; standalone it comes
from PORTFOLIO_PERSONA / --corpus."""

from __future__ import annotations

import os
from typing import Any


def persona_from_ctx(ctx: Any) -> str | None:
    try:  # in-process (tests / laptop demo): identity set by the agent's ToolGateway
        from mcp_servers._shared import _current_caller

        c = _current_caller.get()
        if c is not None:
            return c.persona
    except ImportError:
        pass
    try:
        req = ctx.request_context.request
    except Exception:  # noqa: BLE001
        req = None
    if req is not None:
        auth = req.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                from mcp_servers._shared import verify_token

                return verify_token(auth.split(" ", 1)[1]).persona
            except Exception:  # noqa: BLE001
                return None
    return os.getenv("PORTFOLIO_PERSONA")
