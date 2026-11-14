"""Agent-side MCP access (A6 client discipline).

* One `MultiServerMCPClient` per run, carrying the user's short-lived JWT and the trace id as headers, so
  the same trace id reaches every MCP server and its audit log (E3).
* Per-agent allowlists (config `tool_allowlists`): an agent can only call tools it is given.
* Timeouts, bounded retries with exponential backoff, and a health registry that drives degraded mode:
  if the marketplace server is down the UI shows a banner, the worker defers work and retries.
* `GIGBID_MCP_INPROCESS=1` runs the same servers in-process over in-memory streams (tests, laptop demo
  without extra processes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx

from agent.settings import cfg
from agent.tracing import current_trace_id

log = logging.getLogger("gigbid.mcp")


class ToolUnavailable(RuntimeError):
    """The MCP server (or the marketplace behind it) is unreachable -> degraded mode."""

    def __init__(self, server: str, detail: str) -> None:
        super().__init__(f"{server} unavailable: {detail}")
        self.server = server


class ToolFailed(RuntimeError):
    def __init__(self, server: str, tool: str, kind: str, detail: str) -> None:
        super().__init__(f"{server}.{tool} failed ({kind}): {detail}")
        self.server, self.tool, self.kind, self.detail = server, tool, kind, detail


class ToolNotAllowed(PermissionError):
    pass


# --------------------------------------------------------------------------- health registry
_HEALTH: dict[str, tuple[bool, float, str]] = {}


def mark_health(server: str, ok: bool, detail: str = "") -> None:
    _HEALTH[server] = (ok, time.time(), detail)
    try:
        from apps.api.events import publish_health  # lazy: worker/API share Redis when configured

        publish_health(server, ok, detail)
    except Exception:  # noqa: BLE001
        pass


def health_snapshot() -> dict[str, dict[str, Any]]:
    ttl = float(cfg("mcp_servers.health_ttl_s", 15)) * 20
    now = time.time()
    return {s: {"ok": ok, "checked_at": t, "detail": d} for s, (ok, t, d) in _HEALTH.items() if now - t < ttl}


def _server_url(server: str) -> str:
    return str(cfg(f"mcp_servers.{server}.url"))


async def probe(server: str) -> bool:
    if os.getenv("GIGBID_MCP_INPROCESS") == "1":
        ok = True
        if server == "marketplace":
            try:
                async with httpx.AsyncClient(timeout=3) as c:
                    ok = (await c.get(os.getenv("GIGSIM_BASE_URL", "http://localhost:8081") + "/health")).status_code == 200
            except Exception:  # noqa: BLE001
                ok = False
        mark_health(server, ok, "" if ok else "upstream unreachable")
        return ok
    url = _server_url(server).rsplit("/mcp", 1)[0] + "/health"
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(url)
        ok = r.status_code == 200
        mark_health(server, ok, "" if ok else f"HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        mark_health(server, False, type(exc).__name__)
    return ok


# --------------------------------------------------------------------------- gateway
def _inprocess_server(server: str):
    if server == "marketplace":
        from mcp_servers.marketplace.server import mcp
    elif server == "portfolio":
        from mcp_servers.portfolio.server import mcp
    elif server == "workspace":
        from mcp_servers.workspace.server import mcp
    else:
        raise ToolUnavailable(server, "not available in-process")
    return mcp._mcp_server


class ToolGateway:
    def __init__(self, user_id: str, persona: str, trace_id: str | None = None) -> None:
        self.user_id = user_id
        self.persona = persona
        self.trace_id = trace_id or current_trace_id()
        self.inprocess = os.getenv("GIGBID_MCP_INPROCESS") == "1"
        self.timeout = float(cfg("mcp_servers.call_timeout_s", 20))
        self._client = None

    # -------------------------------------------------------------- connections
    def _headers(self) -> dict[str, str]:
        from mcp_servers._shared import mint_token

        return {"Authorization": f"Bearer {mint_token(self.user_id, self.persona, self.trace_id)}", "X-Trace-Id": self.trace_id}

    def client(self):
        if self._client is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            conns: dict[str, Any] = {}
            for name in ("portfolio", "marketplace", "workspace"):
                conns[name] = {"transport": "streamable_http", "url": _server_url(name), "headers": self._headers(),
                               "timeout": self.timeout}
            gh_token = os.getenv(str(cfg("mcp_servers.github.token_env", "GITHUB_PAT")))
            if gh_token:
                conns["github"] = {"transport": "streamable_http", "url": _server_url("github"),
                                   "headers": {"Authorization": f"Bearer {gh_token}", "X-MCP-Readonly": "true"}}
            self._client = MultiServerMCPClient(conns)
        return self._client

    @asynccontextmanager
    async def session(self, server: str):
        if self.inprocess and server != "github":
            from mcp.shared.memory import create_connected_server_and_client_session

            from mcp_servers._shared import Caller, _current_caller

            token = _current_caller.set(Caller(self.user_id, self.persona, self.trace_id))
            try:
                async with create_connected_server_and_client_session(_inprocess_server(server)) as s:
                    yield s
            finally:
                _current_caller.reset(token)
        else:
            async with self.client().session(server) as s:
                yield s

    # -------------------------------------------------------------- calls
    @staticmethod
    def allowed(agent: str, server: str, tool: str) -> bool:
        allow = cfg(f"tool_allowlists.{agent}")
        return allow is not None and f"{server}.{tool}" in allow

    async def call(self, agent: str, server: str, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.allowed(agent, server, tool):
            raise ToolNotAllowed(f"agent '{agent}' may not call {server}.{tool}")
        args = {k: v for k, v in (args or {}).items() if v is not None}
        retries = int(cfg("marketplace.retries", 3))
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with self.session(server) as s:
                    res = await asyncio.wait_for(s.call_tool(tool, args), timeout=self.timeout)
                mark_health(server, True)
                if res.isError:
                    text = " ".join(getattr(c, "text", "") for c in res.content)
                    kind = text.split(":", 1)[0].replace("Error executing tool " + tool, "").strip() or "error"
                    for k in ("unavailable", "rate_limited", "not_found", "policy", "insufficient_connects", "invalid", "auth"):
                        if k in text:
                            kind = k
                            break
                    if kind in {"unavailable", "rate_limited"}:
                        last = ToolFailed(server, tool, kind, text[:300])
                        if kind == "unavailable":
                            mark_health(server, False, "upstream marketplace unavailable")
                    else:
                        raise ToolFailed(server, tool, kind, text[:300])
                else:
                    if res.structuredContent is not None:
                        out = res.structuredContent
                        return out.get("result", out) if set(out) == {"result"} else out
                    import json

                    txt = " ".join(getattr(c, "text", "") for c in res.content)
                    try:
                        return json.loads(txt)
                    except json.JSONDecodeError:
                        return {"text": txt}
            except ToolFailed:
                raise
            except (TimeoutError, asyncio.TimeoutError, httpx.HTTPError, ConnectionError, OSError) as exc:
                last = ToolUnavailable(server, type(exc).__name__)
                mark_health(server, False, type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 - anyio ExceptionGroup from a dead server, etc.
                if "ExceptionGroup" in type(exc).__name__ or "connect" in str(exc).lower():
                    last = ToolUnavailable(server, str(exc)[:120])
                    mark_health(server, False, "connection failed")
                else:
                    raise
            if attempt < retries:
                await asyncio.sleep(float(cfg("marketplace.backoff_base_s", 0.5)) * (2 ** attempt) * (0.5 + random.random()))
        if isinstance(last, ToolFailed) and last.kind == "unavailable":
            raise ToolUnavailable(server, last.detail)
        raise last or ToolUnavailable(server, "unknown")

    async def langchain_tools(self, agent: str, servers: tuple[str, ...] = ("marketplace", "portfolio", "workspace")):
        """LangChain tools filtered by the agent's allowlist (used by the ReAct baseline and R&D A)."""
        from langchain_mcp_adapters.tools import load_mcp_tools

        out = []
        for server in servers:
            async with self.session(server) as s:
                tools = await load_mcp_tools(s)
            allow = set(cfg(f"tool_allowlists.{agent}") or [])
            out += [t for t in tools if f"{server}.{t.name}" in allow or agent == "*"]
        return out
