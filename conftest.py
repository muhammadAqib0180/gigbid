"""Test fixtures: deterministic `test` model profile, in-process MCP servers, GigSim served in-process through
httpx's ASGI transport (no network, no ports), and isolated SQLite files per test session."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="gigbid-tests-"))
os.environ.setdefault("MODEL_PROFILE", "test")
os.environ.setdefault("GIGBID_MCP_INPROCESS", "1")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'app.db').as_posix()}"
os.environ["MCP_DATABASE_URL"] = f"sqlite:///{(_TMP / 'mcp.db').as_posix()}"
os.environ["GIGSIM_DB"] = str(_TMP / "gigsim.db")
os.environ["GIGSIM_ERROR_RATE"] = "0"
os.environ["GIGSIM_RATE_PER_MIN"] = "100000"
os.environ.setdefault("LANGSMITH_TRACING", "false")


@pytest.fixture(scope="session")
def gigsim_app():
    from gigsim.app import app

    return app


@pytest.fixture(autouse=True)
def gigsim_transport(monkeypatch, gigsim_app):
    """Route every GigSim adapter to the in-process GigSim app."""
    import httpx

    from mcp_servers.marketplace import adapters as adapters_mod
    from mcp_servers.marketplace import server as server_mod
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

    def patched(user_id: str, persona: str, mode: str | None = None):
        return GigSimAdapter(freelancer_id=persona, base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim_app))

    monkeypatch.setattr(adapters_mod, "get_adapter", patched)
    monkeypatch.setattr(server_mod, "get_adapter", patched)
    yield


@pytest.fixture
def reset_gigsim(gigsim_app):
    from gigsim import app as g

    with g._lock:
        for t in ("proposals", "threads", "messages", "events", "idem", "connects", "kv"):
            g.CONN.execute(f"DELETE FROM {t}")
    yield
