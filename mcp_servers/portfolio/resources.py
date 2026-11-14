"""Resource templates so a host (Claude Desktop, Cursor) can load full portfolio items."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .backends import backend_for, dumps


def register(mcp: FastMCP) -> None:
    @mcp.resource("portfolio://case/{id}", mime_type="text/markdown")
    def case(id: str) -> str:
        """A case study by id or project slug."""
        b = backend_for(None)
        item = b.get_item(id) or b.get_item(f"case-{id}")
        return item["text"] if item else f"case {id} not found"

    @mcp.resource("portfolio://proposal/{id}", mime_type="text/markdown")
    def proposal(id: str) -> str:
        """A past proposal with its outcome (won / replied / ignored)."""
        item = backend_for(None).get_item(id)
        return item["text"] if item else f"proposal {id} not found"

    @mcp.resource("portfolio://repo/{slug}", mime_type="text/markdown")
    def repo(slug: str) -> str:
        """A repository README."""
        b = backend_for(None)
        item = b.get_item(f"repo-{slug}") or b.get_item(slug)
        return item["text"] if item else f"repo {slug} not found"

    @mcp.resource("portfolio://index", mime_type="application/json")
    def index() -> str:
        """Every item in the portfolio (id, type, title, source)."""
        return dumps(backend_for(None).list_items())
