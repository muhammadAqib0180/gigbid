"""Portfolio MCP server (A1, read-only), built with the official MCP Python SDK.

Standalone (published as `portfolio-evidence-mcp`):
    uvx portfolio-evidence-mcp --corpus ./my-portfolio            # stdio, for Claude Desktop / Cursor
Inside GigBid (HTTP, tenant from the bearer token):
    python -m mcp_servers.portfolio.server --http --port 8101
"""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import prompts, resources, tools

mcp = FastMCP(
    "portfolio-evidence",
    instructions=("Read-only access to a freelancer's portfolio: case studies, repos, code, reviews and past proposals "
                  "with outcomes. Use search_evidence for each requirement and cite evidence ids; never claim experience "
                  "the portfolio does not contain."),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
tools.register(mcp)
resources.register(mcp)
prompts.register(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "portfolio"})


def http_app():
    app = mcp.streamable_http_app()
    if os.getenv("GIGBID_MCP_AUTH", "1") == "1":
        try:
            from mcp_servers._shared import BearerAuthMiddleware

            return BearerAuthMiddleware(app)
        except ImportError:
            return app
    return app


def main() -> None:
    ap = argparse.ArgumentParser(prog="portfolio-evidence-mcp")
    ap.add_argument("--corpus", help="folder of Markdown/text/code files (standalone mode)")
    ap.add_argument("--persona", help="GigBid persona id (monorepo mode)")
    ap.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8101")))
    ns = ap.parse_args()
    if ns.corpus:
        os.environ["PORTFOLIO_CORPUS"] = ns.corpus
    if ns.persona:
        os.environ["PORTFOLIO_PERSONA"] = ns.persona
    if ns.http:
        import uvicorn

        uvicorn.run(http_app(), host=ns.host, port=ns.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
