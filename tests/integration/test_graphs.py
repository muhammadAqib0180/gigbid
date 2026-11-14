"""Graph runs against GigSim (in-process) with the deterministic `test` model profile.

Covers: parallel analysis, scam skip, approval interrupt + resume, crash-and-resume submitting exactly once,
bounded critic loop, edit -> compliance re-check, conversation graph."""

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph

DEV = Path(__file__).resolve().parents[2] / "evals" / "datasets"


def dev(persona, pred):
    rows = [json.loads(line) for line in (DEV / f"dev_{persona}.jsonl").read_text().splitlines()]
    return next(r for r in rows if pred(r))


def inp(tid, persona, job_id):
    return {"thread_id": tid, "user_id": "u-test", "persona_id": persona, "job_id": job_id, "trace_id": "t-test", "steps": 0}


async def run_until_pause(g, tid, payload):
    cfg = {"configurable": {"thread_id": tid}}
    nodes = []
    async for _m, ch in g.astream(payload, cfg, stream_mode=["custom"]):
        if ch.get("event") == "finished":
            nodes.append(ch["node"])
    return await g.aget_state(cfg), nodes


async def test_scam_is_skipped_and_parallel_branches_ran(reset_gigsim):
    g = build_bid_graph(InMemorySaver(), InMemoryStore())
    job = dev("fullstack_web", lambda r: r["gold_scam"] and "obvious" in r["tags"])
    st, nodes = await run_until_pause(g, "bid:t:scam", inp("bid:t:scam", "fullstack_web", job["job_id"]))
    assert {"analyst", "risk", "matcher"} <= set(nodes) and "writer" not in nodes
    assert st.values["status"] == "skipped" and st.values["risk"]["is_scam"]


async def test_bid_interrupts_then_crash_resume_submits_exactly_once(reset_gigsim):
    saver, store = InMemorySaver(), InMemoryStore()
    job = dev("ai_ml_engineer", lambda r: r["gold_bid"] and "exact_tool" in r["tags"])
    tid = "bid:t:resume"
    g1 = build_bid_graph(saver, store)
    st, nodes = await run_until_pause(g1, tid, inp(tid, "ai_ml_engineer", job["job_id"]))
    assert st.next == ("approval",) and st.tasks[0].interrupts
    payload = st.tasks[0].interrupts[0].value
    assert payload["preview"]["connects_cost"] > 0 and payload["draft"]["cover_letter"]
    assert nodes.count("writer") <= 3                     # critic loop bounded: first draft + max 2 revisions
    # "crash": throw away the graph object, rebuild from the same checkpointer, approve
    g2 = build_bid_graph(saver, store)
    out = await g2.ainvoke(Command(resume={"action": "approve"}), {"configurable": {"thread_id": tid}})
    assert out["status"] == "submitted"
    # resuming the finished thread again does nothing; GigSim has exactly one submitted proposal for the job
    await g2.ainvoke(None, {"configurable": {"thread_id": tid}})
    from gigsim import app as gs
    n = gs.CONN.execute("SELECT COUNT(*) FROM proposals WHERE job_id=? AND status='submitted'", (job["job_id"],)).fetchone()[0]
    assert n == 1


async def test_edit_is_rechecked_by_compliance(reset_gigsim):
    saver, store = InMemorySaver(), InMemoryStore()
    job = dev("data_analyst", lambda r: r["gold_bid"] and "exact_tool" in r["tags"])
    tid = "bid:t:edit"
    g = build_bid_graph(saver, store)
    st, _ = await run_until_pause(g, tid, inp(tid, "data_analyst", job["job_id"]))
    text = st.tasks[0].interrupts[0].value["draft"]["cover_letter"] + "\n\nPing me on WhatsApp +1 415 555 0199 to go faster."
    st2, nodes = await run_until_pause(g, tid, Command(resume={"action": "edit", "edited_text": text}))
    assert "compliance" in nodes and st2.next == ("approval",)
    new = st2.tasks[0].interrupts[0].value["draft"]["cover_letter"]
    assert "WhatsApp" not in new and "415" not in new


async def test_conversation_graph_interview_slots(reset_gigsim):
    from gigsim import app as gs

    saver, store = InMemorySaver(), InMemoryStore()
    job = dev("ai_ml_engineer", lambda r: r["gold_bid"] and "exact_tool" in r["tags"])
    g = build_bid_graph(saver, store)
    tid = "bid:t:conv"
    await run_until_pause(g, tid, inp(tid, "ai_ml_engineer", job["job_id"]))
    out = await g.ainvoke(Command(resume={"action": "approve"}), {"configurable": {"thread_id": tid}})
    pid = out["submission"]["proposal_id"]
    gs.kv_set("sim_minutes", gs.now_min())
    with gs._lock:   # force a client reply with an interview request
        gs.CONN.execute("INSERT OR IGNORE INTO threads VALUES(?,?,?,?,?,?,?)", ("th_test", pid, "ai_ml_engineer", job["job_id"], "c", "replied", 1))
        gs.CONN.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,1)", ("m_t1", "th_test", "client", "Are you available for a 30-minute call this week?", 1, "{}"))
    cg = build_conversation_graph(saver, store)
    ctid = "conv:u-test:th_test"
    st, nodes = await run_until_pause(cg, ctid, {"thread_id": ctid, "marketplace_thread_id": "th_test", "user_id": "u-test",
                                                 "persona_id": "ai_ml_engineer", "trace_id": "t", "steps": 0})
    p = st.tasks[0].interrupts[0].value
    assert p["intent"]["intent"] == "interview_request" and len(p["slots"]) >= 1
    done = await cg.ainvoke(Command(resume={"action": "approve"}), {"configurable": {"thread_id": ctid}})
    assert done["status"] == "sent" and done["pipeline_stage"] == "interview"
