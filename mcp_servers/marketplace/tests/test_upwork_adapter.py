"""Live Upwork adapter against a FAKE Upwork-shaped MCP server (no real account in CI): tool-name mapping,
normalisation onto the port, and the rule that live mode never submits."""

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

fake = FastMCP("fake-upwork")
CALLS: list[str] = []


@fake.tool()
def search_jobs(query: str = "", limit: int = 10) -> dict:
    CALLS.append("search_jobs")
    return {"jobs": [{"id": "~01abc", "title": "RAG chatbot", "description": "Need LangChain", "skills": [{"name": "LangChain"}],
                      "type": "HOURLY", "hourlyBudgetMin": 30, "hourlyBudgetMax": 60, "client": {"id": "c1"}}]}


@fake.tool()
def create_proposal_draft(job_id: str, cover_letter: str, bid_amount: float | None = None) -> dict:
    CALLS.append("create_proposal_draft")
    return {"id": "draft-1", "connects_cost": 8}


@fake.tool()
def get_connects_balance() -> dict:
    return {"connects": 42}


class FakeClient:
    @asynccontextmanager
    async def session(self, name):
        async with connect(fake._mcp_server) as s:
            yield s


async def test_live_adapter_maps_tools_and_never_submits():
    a = UpworkLiveAdapter("u1", client=FakeClient())
    jobs = await a.search_jobs("rag", limit=5)
    assert jobs[0]["job_id"] == "~01abc" and jobs[0]["is_hourly"] and jobs[0]["skills"] == ["LangChain"]
    d = await a.create_proposal_draft({"job_id": "~01abc", "cover_letter": "hello", "bid_amount": 40}, "k" * 16)
    assert d["status"] == "draft_on_upwork"
    s = await a.submit_proposal(d["proposal_id"], "k" * 16)
    assert s["status"] == "awaiting_confirmation_on_upwork" and s["connects_spent"] == 0
    assert CALLS.count("create_proposal_draft") == 1          # submit did NOT call any write tool
    assert (await a.get_connects_balance())["balance"] == 42
