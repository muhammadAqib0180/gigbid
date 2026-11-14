"""Contract test (A7): MCP tool signatures are snapshotted; CI fails if a schema changes unintentionally.
Regenerate intentionally with:  UPDATE_SNAPSHOTS=1 pytest tests/contract"""

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

SNAP = Path(__file__).parent / "snapshots"


async def _tools(server) -> list[dict]:
    async with connect(server._mcp_server) as s:
        res = await s.list_tools()
    return sorted(({"name": t.name, "input": t.inputSchema, "output": t.outputSchema,
                    "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None} for t in res.tools),
                  key=lambda d: d["name"])


@pytest.mark.parametrize("name", ["portfolio", "marketplace", "workspace"])
async def test_tool_schema_snapshot(name):
    mod = __import__(f"mcp_servers.{name}.server", fromlist=["mcp"])
    current = await _tools(mod.mcp)
    path = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(current, sort_keys=True)) == expected, f"{name} tool schemas changed; review and UPDATE_SNAPSHOTS=1"


async def test_write_tools_have_correct_annotations():
    from mcp_servers.marketplace.server import mcp

    tools = {t["name"]: t for t in await _tools(mcp)}
    for name in ("search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_messages"):
        assert tools[name]["annotations"]["readOnlyHint"] is True
    for name in ("submit_proposal", "send_message"):
        a = tools[name]["annotations"]
        assert a["readOnlyHint"] is False and a["destructiveHint"] is True and a["idempotentHint"] is True
    assert tools["create_proposal_draft"]["annotations"]["destructiveHint"] is False
    for name in ("create_proposal_draft", "submit_proposal", "send_message"):
        props = tools[name]["input"]["properties"]
        assert "idempotency_key" in props and "dry_run" in props
        assert props["idempotency_key"]["minLength"] == 16
        assert tools[name]["output"] is not None
