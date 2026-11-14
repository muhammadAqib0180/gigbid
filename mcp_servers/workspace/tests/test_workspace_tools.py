from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.workspace.server import mcp


async def test_slots_hold_and_draft_are_idempotent():
    async with connect(mcp._mcp_server) as s:
        slots = (await s.call_tool("free_slots", {"days": 5, "max_slots": 3})).structuredContent["slots"]
        assert len(slots) == 3
        args = {"start": slots[0]["start"], "end": slots[0]["end"], "title": "Interview", "idempotency_key": "hold-key-000000001"}
        h1 = (await s.call_tool("create_interview_hold", args)).structuredContent
        h2 = (await s.call_tool("create_interview_hold", args)).structuredContent
        assert h1["hold_id"] == h2["hold_id"] and h2["idempotent_replay"]
        again = (await s.call_tool("free_slots", {"days": 5, "max_slots": 3})).structuredContent["slots"]
        assert slots[0]["start"] not in [x["start"] for x in again]
        d = (await s.call_tool("create_email_draft", {"to": "client@example.com", "subject": "Follow-up", "body": "Hi",
                                                      "idempotency_key": "draft-key-00000001"})).structuredContent
        assert d["status"] == "draft"
