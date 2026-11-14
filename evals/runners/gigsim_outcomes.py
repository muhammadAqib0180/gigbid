"""End-to-end outcome evaluation (B4 "Outcome", X2): run the full bid graph on a FIXED job set, auto-approve
every draft (evaluation only - the product never auto-sends), submit to GigSim, let simulated clients decide,
answer replies through the conversation graph, and measure reply / hire rate plus unsupported claims per
proposal (before / after claim verification), revisions, compliance fixes, latency and cost per proposal.

    python -m evals.runners.gigsim_outcomes --n 25 --variant v8_corrective --strategy evidence_first --out outcomes_v8
    python -m evals.runners.gigsim_outcomes --n 25 --variant v0_naive --out outcomes_v0
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import time

from evals.runners.common import PERSONAS, RESULTS, load_dev, mean, pct, sample, save, setup_env


async def run(args) -> None:
    os.environ["RAG_VARIANT"] = args.variant
    os.environ["PROPOSAL_STRATEGY"] = args.strategy
    setup_env(args.profile)
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command

    from agent.graphs.bid_graph import build_bid_graph
    from agent.graphs.conversation_graph import build_conversation_graph
    from agent.llm import total_tokens, total_usd
    from gigsim import app as gs

    saver, store = InMemorySaver(), InMemoryStore()
    bid = build_bid_graph(saver, store)
    conv = build_conversation_graph(saver, store)
    jobs = []
    for persona in PERSONAS:
        rows = [r for r in load_dev(persona) if r["gold_bid"]]
        jobs += [(persona, r) for r in sample(rows, args.n, seed=11)]
    print(f"{len(jobs)} fixed jobs, variant={args.variant}, strategy={args.strategy}, profile={os.environ['MODEL_PROFILE']}")
    records = []
    sem = asyncio.Semaphore(args.concurrency)

    async def one(persona: str, gold: dict) -> None:
        async with sem:
            tid = f"bid:eval:{persona}:{gold['job_id']}"
            cfg = {"configurable": {"thread_id": tid}}
            t0 = time.perf_counter()
            try:
                async for _ in bid.astream({"thread_id": tid, "user_id": "eval", "persona_id": persona, "job_id": gold["job_id"],
                                            "trace_id": "eval", "steps": 0}, cfg, stream_mode=["custom"]):
                    pass
                st = await bid.aget_state(cfg)
                interrupted = any(t.interrupts for t in st.tasks)
                if interrupted:
                    await bid.ainvoke(Command(resume={"action": "approve"}), cfg)
                    st = await bid.aget_state(cfg)
            except Exception as exc:  # noqa: BLE001
                records.append({"persona": persona, "job_id": gold["job_id"], "status": "error", "error": str(exc)[:200]})
                return
            v = st.values
            ver = v.get("verifications") or []
            drafts = v.get("drafts") or []
            records.append({
                "persona": persona, "job_id": gold["job_id"], "tags": gold["tags"], "status": v.get("status"),
                "proposal_id": (v.get("submission") or {}).get("proposal_id"), "latency_s": time.perf_counter() - t0,
                "unsupported_first_draft": ver[0]["unsupported_before"] if ver else None,
                "unsupported_final": ver[-1]["unsupported_after"] if ver else None,
                "claims_first_draft": ver[0]["total_claims"] if ver else None,
                "revisions": max(0, sum(1 for d in drafts if d.get("status") == "drafted") - 1),
                "compliance_fixes": len((v.get("compliance") or {}).get("redactions") or []),
                "tokens": total_tokens(v.get("usage") or {}), "usd": total_usd(v.get("usage") or {}),
                "text": drafts[-1]["cover_letter"] if drafts else "", "strategy": drafts[-1].get("strategy") if drafts else None,
                "title": (v.get("job") or {}).get("title", ""),
            })

    t0 = time.time()
    await asyncio.gather(*(one(p, g) for p, g in jobs))
    print(f"bid phase {time.time() - t0:.0f}s")
    # simulated clients decide
    gs.tick(60)
    replied_threads = {}
    for r in gs.CONN.execute("SELECT proposal_id, status, decision FROM proposals").fetchall():
        replied_threads[r["proposal_id"]] = r["status"]
    # answer client replies through the conversation graph (auto-approved), then let clients respond again
    threads = gs.CONN.execute("SELECT thread_id, proposal_id, freelancer_id FROM threads").fetchall()
    for th in threads:
        ctid = f"conv:eval:{th['thread_id']}"
        cfg = {"configurable": {"thread_id": ctid}}
        try:
            async for _ in conv.astream({"thread_id": ctid, "marketplace_thread_id": th["thread_id"], "user_id": "eval",
                                         "persona_id": th["freelancer_id"], "trace_id": "eval", "steps": 0}, cfg, stream_mode=["custom"]):
                pass
            st = await conv.aget_state(cfg)
            if any(t.interrupts for t in st.tasks):
                await conv.ainvoke(Command(resume={"action": "approve"}), cfg)
        except Exception as exc:  # noqa: BLE001
            print("conversation error", th["thread_id"], exc)
    gs.tick(60)
    gs.tick(60)
    final = {r["proposal_id"]: r["status"] for r in gs.CONN.execute("SELECT proposal_id, status FROM proposals").fetchall()}
    stages = {r["proposal_id"]: r["stage"] for r in gs.CONN.execute("SELECT proposal_id, stage FROM threads").fetchall()}
    for rec in records:
        pid = rec.get("proposal_id")
        rec["replied"] = bool(pid and (final.get(pid) in {"replied", "hired"} or pid in stages))
        rec["interview"] = bool(pid and stages.get(pid) in {"interview", "hired"})
        rec["hired"] = bool(pid and (final.get(pid) == "hired" or stages.get(pid) == "hired"))
    sub = [r for r in records if r.get("proposal_id")]

    def agg(rs: list[dict]) -> dict:
        s = [r for r in rs if r.get("proposal_id")]
        return {"jobs": len(rs), "submitted": len(s),
                "reply_rate": round(sum(r["replied"] for r in s) / len(s), 4) if s else None,
                "interview_rate": round(sum(r["interview"] for r in s) / len(s), 4) if s else None,
                "hire_rate": round(sum(r["hired"] for r in s) / len(s), 4) if s else None,
                "unsupported_per_proposal_first_draft": mean([r["unsupported_first_draft"] for r in s if r.get("unsupported_first_draft") is not None]),
                "unsupported_per_proposal_final": mean([r["unsupported_final"] for r in s if r.get("unsupported_final") is not None]),
                "claims_per_proposal": mean([r["claims_first_draft"] for r in s if r.get("claims_first_draft") is not None]),
                "mean_revisions": mean([r["revisions"] for r in s]), "mean_compliance_fixes": mean([r["compliance_fixes"] for r in s]),
                "p50_latency_s_per_proposal": pct([r["latency_s"] for r in s], 0.5), "p95_latency_s_per_proposal": pct([r["latency_s"] for r in s], 0.95),
                "tokens_per_proposal": mean([r["tokens"] for r in s]), "usd_per_proposal": mean([r["usd"] for r in s])}

    name = args.out or f"outcomes_{args.variant}_{args.strategy}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / f"{name}_proposals.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["persona", "job_id", "title", "status", "proposal_id", "replied", "hired", "unsupported_first_draft", "unsupported_final",
                    "revisions", "strategy", "text"])
        for r in records:
            w.writerow([r.get("persona"), r.get("job_id"), r.get("title"), r.get("status"), r.get("proposal_id"), r.get("replied"),
                        r.get("hired"), r.get("unsupported_first_draft"), r.get("unsupported_final"), r.get("revisions"), r.get("strategy"),
                        (r.get("text") or "").replace("\r", "")])
    by_persona = {p: agg([r for r in records if r.get("persona") == p]) for p in PERSONAS}
    save(name, {"variant": args.variant, "strategy": args.strategy, "overall": agg(records), "by_persona": by_persona,
                "status_counts": {s: sum(1 for r in records if r.get("status") == s) for s in {r.get("status") for r in records}},
                "replied_ids": [r["proposal_id"] for r in sub if r["replied"]],
                "notes": "Drafts auto-approved for evaluation only. Writer = model profile above (test = deterministic heuristic writer)."})
    o = agg(records)
    print(f"submitted {o['submitted']}/{o['jobs']}  reply {o['reply_rate']}  hire {o['hire_rate']}  unsupported first/final "
          f"{o['unsupported_per_proposal_first_draft']}/{o['unsupported_per_proposal_final']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25, help="fixed jobs per persona (gold bid)")
    ap.add_argument("--variant", default="v8_corrective")
    ap.add_argument("--strategy", default="evidence_first", choices=["evidence_first", "question_first", "ab"])
    ap.add_argument("--profile", default=None)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--out")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
