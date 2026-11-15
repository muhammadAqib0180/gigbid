"""R&D question C: is the multi-agent design worth it?

Same jobs, same model profile, three systems:
  (a) single  - one ReAct agent holding all read tools (marketplace + portfolio), prompt agent/prompts/single_agent.md
  (b) supervisor - langgraph-supervisor with a marketplace researcher, a portfolio researcher and a writer
  (c) graph   - GigBid's hand-built bid graph (parallel analysis, verifier, critic, compliance)
Metrics: bid-or-skip accuracy, scam recall, unsupported claims per proposal (same verifier for all), compliance
violations remaining in the final text, GigSim reply rate on submitted letters, tokens and latency per job.

    python -m evals.runners.multiagent_compare --n 10 --profile open_local
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from evals.runners.common import PERSONAS, load_dev, mean, pct, sample, save, setup_env, tool_text

JSON_RX = re.compile(r"\{.*\}", re.S)


def parse_final(text: str) -> dict:
    m = JSON_RX.search(text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {}


def usage_of(messages) -> int:
    tot = 0
    for m in messages:
        um = getattr(m, "usage_metadata", None) or {}
        tot += int(um.get("input_tokens", 0)) + int(um.get("output_tokens", 0))
    return tot


def evidence_from(messages) -> list[dict]:
    ev = []
    for m in messages:
        if getattr(m, "type", "") == "tool":
            try:
                data = json.loads(tool_text(m.content))
            except (json.JSONDecodeError, TypeError):
                data = {}
            for it in (data.get("items") or []):
                ev.append(it)
    return ev


async def run_single(job: dict, persona: str, tools, model) -> dict:
    from langgraph.prebuilt import create_react_agent

    from agent.prompting import load_prompt

    sysm, user = load_prompt("single_agent").render(job_id=job["job_id"], persona=persona)
    agent = create_react_agent(model, tools, prompt=sysm)
    out = await agent.ainvoke({"messages": [("user", user)]}, {"recursion_limit": 16})
    msgs = out["messages"]
    return {"final": parse_final(str(msgs[-1].content)), "tokens": usage_of(msgs), "evidence": evidence_from(msgs)}


async def run_supervisor(job: dict, persona: str, tools, model) -> dict:
    from langgraph.prebuilt import create_react_agent
    from langgraph_supervisor import create_supervisor

    from agent.prompting import load_prompt

    mk = [t for t in tools if t.name in {"get_job", "get_client_history", "get_market_stats"}]
    pf = [t for t in tools if t.name in {"search_evidence", "get_case_study"}]
    a1 = create_react_agent(model, mk, name="marketplace_researcher", prompt="Fetch the job and the client's history; report facts and scam signals.")
    a2 = create_react_agent(model, pf, name="portfolio_researcher", prompt="Find portfolio evidence for each requirement of the job.")
    a3 = create_react_agent(model, [], name="writer", prompt="Write a grounded cover letter using only evidence you are given.")
    sysm, user = load_prompt("single_agent").render(job_id=job["job_id"], persona=persona)
    sup = create_supervisor([a1, a2, a3], model=model, prompt=sysm, output_mode="last_message").compile()
    out = await sup.ainvoke({"messages": [("user", user)]}, {"recursion_limit": 30})
    msgs = out["messages"]
    return {"final": parse_final(str(msgs[-1].content)), "tokens": usage_of(msgs), "evidence": evidence_from(msgs)}


async def run_graph(job: dict, persona: str, bid_graph) -> dict:
    from agent.llm import total_tokens

    tid = f"bid:cmp:{persona}:{job['job_id']}"
    cfg = {"configurable": {"thread_id": tid}}
    async for _ in bid_graph.astream({"thread_id": tid, "user_id": "cmp", "persona_id": persona, "job_id": job["job_id"],
                                      "trace_id": "cmp", "steps": 0}, cfg, stream_mode=["custom"]):
        pass
    v = (await bid_graph.aget_state(cfg)).values
    d = (v.get("decision") or {}).get("action", "skip")
    drafts = v.get("drafts") or []
    return {"final": {"decision": "bid" if d == "bid" else "skip", "is_scam": bool((v.get("risk") or {}).get("is_scam")),
                      "cover_letter": drafts[-1]["cover_letter"] if drafts else None},
            "tokens": total_tokens(v.get("usage") or {}), "evidence": v.get("evidence") or [],
            "redactions": len((v.get("compliance") or {}).get("redactions") or [])}


async def main_async(args) -> None:
    setup_env(args.profile)
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from agent.llm import chat_model_for
    from agent.mcp_client import ToolGateway

    jobs = []
    for persona in PERSONAS:
        rows = load_dev(persona)
        n_bid, n_skip = (args.n + 1) // 2, args.n // 2  # sample(rows, 0) means "all rows", so never pass 0
        mix = (sample([r for r in rows if r["gold_bid"]], n_bid, seed=5) if n_bid else []) +               (sample([r for r in rows if not r["gold_bid"]], n_skip, seed=5) if n_skip else [])
        jobs += [(persona, r) for r in mix]
    model = chat_model_for("writer")
    bid_graph = build_bid_graph(InMemorySaver(), InMemoryStore())
    systems = args.systems.split(",")
    results: dict[str, list[dict]] = {s: [] for s in systems}
    from langchain_mcp_adapters.tools import load_mcp_tools

    for persona, gold in jobs:
        gw = ToolGateway("cmp", persona)
        async with gw.session("marketplace") as ms, gw.session("portfolio") as ps:
            tools = (await load_mcp_tools(ms)) + (await load_mcp_tools(ps))
            tools = [t for t in tools if t.name in {"get_job", "get_client_history", "get_market_stats", "search_evidence", "get_case_study"}]
            await _run_job(systems, persona, gold, tools, model, bid_graph, results, args)
        await _summarise(results, systems, args, final=False)  # save after every job: a stopped run keeps its rows
    await _summarise(results, systems, args)


async def _run_job(systems, persona, gold, tools, model, bid_graph, results, args) -> None:
    from agent.nodes.compliance import check_text
    from gigsim import app as gs
    from gigsim import sim
    from rag.verify import verify_claims

    job = {"job_id": gold["job_id"]}
    if True:
        for s in systems:
            t0 = time.perf_counter()
            try:
                if s == "single":
                    r = await asyncio.wait_for(run_single(job, persona, tools, model), timeout=args.timeout)
                elif s == "supervisor":
                    r = await asyncio.wait_for(run_supervisor(job, persona, tools, model), timeout=args.timeout)
                else:
                    r = await asyncio.wait_for(run_graph(job, persona, bid_graph), timeout=args.timeout)
                err = None
            except Exception as exc:  # noqa: BLE001
                r, err = {"final": {}, "tokens": 0, "evidence": []}, f"{type(exc).__name__}: {str(exc)[:160]}"
            lat = time.perf_counter() - t0
            f = r["final"]
            letter = f.get("cover_letter") or ""
            pred_bid = str(f.get("decision", "skip")).lower() == "bid"
            unsupported = None
            violations = None
            replied = None
            if pred_bid and letter:
                _, rep = verify_claims(letter, r["evidence"][:12] or [{"evidence_id": "none", "item_id": "none", "type": "none", "snippet": ""}])
                unsupported = rep.unsupported_before if s != "graph" else rep.unsupported_after
                _, red, _ = check_text(letter, require_disclosures=False)
                violations = sum(1 for x in red if x.kind not in {"disclosure_added"})
                jfull = gs.DATA.jobs[gold["job_id"]]
                dec = sim.decide(jfull, gs.DATA.hidden.get(gold["job_id"], {}), {"cover_letter": letter, "bid_amount": f.get("price") or jfull.get("budget") or 0})
                replied = bool(dec["replied"])
            results[s].append({"persona": persona, "job_id": gold["job_id"], "gold_bid": gold["gold_bid"], "gold_scam": gold["gold_scam"],
                               "pred_bid": pred_bid, "pred_scam": bool(f.get("is_scam")), "unsupported": unsupported, "violations_in_final": violations,
                               "compliance_caught": r.get("redactions"), "replied": replied, "tokens": r["tokens"], "latency_s": lat, "error": err})
            print(s, gold["job_id"], "bid" if pred_bid else "skip", "err" if err else "", f"{lat:.0f}s")


async def _summarise(results, systems, args, final: bool = True) -> None:
    summary = {}
    for s, rows in results.items():
        bids = [x for x in rows if x["pred_bid"] and x["unsupported"] is not None]
        summary[s] = {"n": len(rows), "errors": sum(1 for x in rows if x["error"]),
                      "bid_skip_accuracy": mean([float(x["pred_bid"] == x["gold_bid"]) for x in rows]),
                      "scam_recall": mean([float(x["pred_scam"]) for x in rows if x["gold_scam"]]) if any(x["gold_scam"] for x in rows) else None,
                      "unsupported_per_proposal": mean([x["unsupported"] for x in bids]),
                      "violations_in_final_text": sum(x["violations_in_final"] or 0 for x in bids),
                      "simulated_reply_rate": mean([float(x["replied"]) for x in bids]) if bids else None,
                      "tokens_per_job": mean([x["tokens"] for x in rows]), "p50_latency_s": pct([x["latency_s"] for x in rows], 0.5),
                      "p95_latency_s": pct([x["latency_s"] for x in rows], 0.95)}
    save(args.out or "multiagent_compare", {"systems": systems, "summary": summary, "rows": results, "complete": final})
    if final:
        print(json.dumps(summary, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4, help="jobs per persona (half gold bid, half not)")
    ap.add_argument("--profile", default="open_local")
    ap.add_argument("--systems", default="graph,single,supervisor")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--out")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
