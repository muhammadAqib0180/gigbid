"""Change-request check: activate GigSim policy 2026-11-02, run a fixed set of bids end to end, and record
whether submissions are accepted and whether GigBid's Connects estimate matches GigSim's charge.

Run once BEFORE the config update (expect policy_violation rejections and wrong Connects estimates) and once
AFTER it (expect 100% accepted, estimates match):
    python -m evals.runners.change_request --label before
    python -m evals.runners.change_request --label after
"""

from __future__ import annotations

import argparse
import asyncio

from evals.runners.common import PERSONAS, load_dev, sample, save, setup_env


async def main_async(args) -> None:
    setup_env("test")
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command

    from agent.graphs.bid_graph import build_bid_graph
    from agent.settings import cfg
    from gigsim import app as gs
    from gigsim.policy import POLICIES, connects_cost

    gs.kv_set("policy_version", "2026-11-02")
    pol = POLICIES["2026-11-02"]
    g = build_bid_graph(InMemorySaver(), InMemoryStore())
    rows = []
    for persona in PERSONAS:
        cands = [r for r in load_dev(persona) if r["gold_bid"] and (gs.DATA.jobs[r["job_id"]].get("budget") or 0) > 1000]
        for gold in sample(cands, args.n, seed=21):
            tid = f"bid:cr:{args.label}:{gold['job_id']}"
            cfgd = {"configurable": {"thread_id": tid}}
            async for _ in g.astream({"thread_id": tid, "user_id": "cr", "persona_id": persona, "job_id": gold["job_id"],
                                      "trace_id": "cr", "steps": 0}, cfgd, stream_mode=["custom"]):
                pass
            st = await g.aget_state(cfgd)
            if not any(t.interrupts for t in st.tasks):
                rows.append({"job_id": gold["job_id"], "status": st.values.get("status"), "reached_approval": False})
                continue
            est = st.values["price"]["connects_cost"]
            out = await g.ainvoke(Command(resume={"action": "approve"}), cfgd)
            job = gs.DATA.jobs[gold["job_id"]]
            rows.append({"job_id": gold["job_id"], "reached_approval": True, "status": out.get("status"),
                         "error": (out.get("errors") or [""])[-1][:200], "budget": job.get("budget"),
                         "connects_estimated": est, "connects_charged_by_gigsim": connects_cost(job, pol),
                         "disclosure_in_text": pol["required_disclosures"][0].lower() in (out.get("drafts") or [{}])[-1].get("cover_letter", "").lower()})
    sent = [r for r in rows if r.get("reached_approval")]
    res = {"label": args.label, "policy_active": "2026-11-02", "config_policy_version": cfg("bidding_rules.policy_version"),
           "n_reached_approval": len(sent),
           "accepted_rate": round(sum(r["status"] == "submitted" for r in sent) / len(sent), 4) if sent else None,
           "connects_estimate_correct_rate": round(sum(r["connects_estimated"] == r["connects_charged_by_gigsim"] for r in sent) / len(sent), 4) if sent else None,
           "disclosure_present_rate": round(sum(r["disclosure_in_text"] for r in sent) / len(sent), 4) if sent else None,
           "rows": rows}
    save(f"change_request_{args.label}", res)
    print({k: v for k, v in res.items() if k != "rows"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=3)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
