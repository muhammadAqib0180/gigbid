"""Marketplace MCP tools through an in-memory MCP client (A7): schemas, dry run, idempotency, audit log."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from sqlalchemy import text

from mcp_servers._shared import engine
from mcp_servers.marketplace.server import mcp


async def call(s, name, args):
    r = await s.call_tool(name, args)
    return r


async def first_job(s):
    r = await call(s, "search_jobs", {"query": "", "limit": 3})
    assert not r.isError
    return r.structuredContent["jobs"][0]


async def test_read_tools_return_typed_results(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        job = await first_job(session)
        r = await call(session, "get_job", {"job_id": job["job_id"]})
        assert r.structuredContent["job_id"] == job["job_id"]
        r = await call(session, "get_client_history", {"client_id": job["client_id"]})
        assert "payment_verified" in r.structuredContent
        r = await call(session, "get_connects_balance", {})
        assert r.structuredContent["balance"] > 0


async def test_dry_run_previews_without_writing(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        job = await first_job(session)
        bal = (await call(session, "get_connects_balance", {})).structuredContent["balance"]
        r = await call(session, "create_proposal_draft", {"job_id": job["job_id"], "cover_letter": "x" * 80, "bid_amount": 300,
                                                          "idempotency_key": "dryrun-key-0000001", "dry_run": True})
        prev = r.structuredContent["preview"]
        assert r.structuredContent["dry_run"] is True and prev["connects_cost"] == job["connects_cost"] and prev["balance_before"] == bal
        from gigsim import app as g
        assert g.CONN.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 0


async def test_idempotent_create_and_submit_spend_once(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        job = await first_job(session)
        args = {"job_id": job["job_id"], "cover_letter": "A grounded cover letter " * 5, "bid_amount": 400, "idempotency_key": "create-key-00000001"}
        a = (await call(session, "create_proposal_draft", args)).structuredContent
        b = (await call(session, "create_proposal_draft", args)).structuredContent
        assert a["proposal_id"] == b["proposal_id"] and b["idempotent_replay"] is True
        bal0 = (await call(session, "get_connects_balance", {})).structuredContent["balance"]
        s1 = (await call(session, "submit_proposal", {"proposal_id": a["proposal_id"], "idempotency_key": "submit-key-00000001"})).structuredContent
        s2 = (await call(session, "submit_proposal", {"proposal_id": a["proposal_id"], "idempotency_key": "submit-key-00000001"})).structuredContent
        bal1 = (await call(session, "get_connects_balance", {})).structuredContent["balance"]
        assert s1["status"] == "submitted" and s2["idempotent_replay"] is True
        assert bal0 - bal1 == job["connects_cost"]


async def test_schema_constraints_reject_bad_input(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        r = await call(session, "create_proposal_draft", {"job_id": "kg_1", "cover_letter": "short", "bid_amount": -5, "idempotency_key": "short"})
        assert r.isError


async def test_audit_log_is_append_only(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        await first_job(session)
        with engine().begin() as c:
            n = c.execute(text("SELECT COUNT(*) FROM mcp_audit_log")).scalar()
        assert n >= 1
        with pytest.raises(Exception):
            with engine().begin() as c:
                c.execute(text("UPDATE mcp_audit_log SET tool='x'"))
        with pytest.raises(Exception):
            with engine().begin() as c:
                c.execute(text("DELETE FROM mcp_audit_log"))


async def test_policy_update_enforced_by_marketplace(reset_gigsim):
    async with connect(mcp._mcp_server) as session:
        from gigsim import app as g

        g.kv_set("policy_version", "2026-11-02")
        try:
            job = await first_job(session)
            d = (await call(session, "create_proposal_draft", {"job_id": job["job_id"], "cover_letter": "No disclosure here " * 5,
                                                               "bid_amount": 400, "idempotency_key": "policy-key-0000001"})).structuredContent
            r = await call(session, "submit_proposal", {"proposal_id": d["proposal_id"], "idempotency_key": "policy-key-0000002"})
            assert r.isError and "policy" in r.content[0].text
        finally:
            g.kv_set("policy_version", "2026-10")
