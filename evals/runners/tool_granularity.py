"""R&D question A: does tool granularity change agent behaviour?

40 tasks with known correct calls (10 intents x 4 instances built from real dev-set ids), three tool sets:
  fine    - 16 narrow tools (one per field / per evidence type)
  coarse  - 3 tools with an `action` argument (marketplace / portfolio / workspace)
  best    - GigBid's MCP tool set with rewritten, task-oriented descriptions (the deployed design)
We bind each set to the same model, take the FIRST tool call, and score tool-selection accuracy, argument
accuracy and tokens per task. Tools are never executed.

    python -m evals.runners.tool_granularity --n 40 --profile open_local
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from evals.runners.common import PERSONAS, jobs_by_id, load_dev, mean, save, setup_env


def _noop(**kw: Any) -> str:
    return "ok"


def tool(name: str, desc: str, fields: dict[str, tuple[type, str]]) -> StructuredTool:
    model = type(f"{name}_args", (BaseModel,), {"__annotations__": {k: v[0] for k, v in fields.items()},
                                                **{k: Field(description=v[1]) for k, v in fields.items()}})
    return StructuredTool.from_function(func=_noop, name=name, description=desc, args_schema=model)


S = (str, "")
FINE = [
    tool("search_jobs_by_keyword", "Search jobs by keyword.", {"keyword": (str, "keyword")}),
    tool("search_jobs_by_category", "Search jobs by category.", {"category": (str, "category")}),
    tool("search_jobs_by_skill", "Search jobs by skill.", {"skill": (str, "skill")}),
    tool("get_job_title", "Get a job's title.", {"job_id": (str, "job id")}),
    tool("get_job_description", "Get a job's description.", {"job_id": (str, "job id")}),
    tool("get_job_budget", "Get a job's budget.", {"job_id": (str, "job id")}),
    tool("get_client_rating", "Get a client's rating.", {"client_id": (str, "client id")}),
    tool("get_client_spend", "Get a client's total spend.", {"client_id": (str, "client id")}),
    tool("get_connects_balance", "Get Connects balance.", {}),
    tool("get_market_rates", "Get market rates for a category.", {"category": (str, "category")}),
    tool("search_case_studies", "Search case studies.", {"query": (str, "query")}),
    tool("search_code", "Search code.", {"query": (str, "query")}),
    tool("search_reviews", "Search reviews.", {"query": (str, "query")}),
    tool("get_case_study", "Get a case study.", {"id": (str, "id")}),
    tool("list_free_slots", "List free calendar slots.", {"days": (int, "days")}),
    tool("list_messages", "List messages of a thread.", {"thread_id": (str, "thread id")}),
    tool("preview_proposal", "Preview a proposal.", {"job_id": (str, "job id"), "amount": (float, "bid")}),
]
COARSE = [
    tool("marketplace", "Marketplace operations. action: search_jobs | get_job | get_client_history | get_connects_balance | "
         "get_market_stats | list_messages | create_proposal_draft.",
         {"action": (str, "operation"), "query": (str, "search text or empty"), "job_id": (str, "job id or empty"),
          "client_id": (str, "client id or empty"), "category": (str, "category or empty"), "thread_id": (str, "thread id or empty"),
          "amount": (float, "bid amount or 0"), "dry_run": (bool, "preview only")}),
    tool("portfolio", "Portfolio operations. action: search | get.", {"action": (str, "search|get"), "query": (str, "text or id")}),
    tool("workspace", "Workspace operations. action: free_slots | hold | email_draft.", {"action": (str, "operation"), "days": (int, "days")}),
]
BEST = [
    tool("search_jobs", "Search OPEN jobs on the marketplace with saved-search keywords. Use for 'find jobs about X'.",
         {"query": (str, "keywords, e.g. 'power bi dashboard'")}),
    tool("get_job", "Fetch one job post (title, description, budget, skills, client id) by job_id.", {"job_id": (str, "job id")}),
    tool("get_client_history", "Check whether a client is trustworthy: payment verification, spend, rating, hire rate, reviews.",
         {"client_id": (str, "client id")}),
    tool("get_connects_balance", "How many Connects the freelancer has left this week.", {}),
    tool("get_market_stats", "What similar jobs in a category usually pay (fixed budgets and hourly rates).",
         {"category": (str, "ml_ai | web_dev | data_analytics | marketing | design_3d | other")}),
    tool("search_evidence", "Find proof in MY portfolio (case studies, repos, code, reviews, past proposals) for one requirement or skill.",
         {"requirement": (str, "the requirement or skill to prove")}),
    tool("get_case_study", "Open the full text of one portfolio item by id (e.g. 'case-churn-predictor').", {"id": (str, "item id")}),
    tool("free_slots", "My free interview slots in the next days (calendar).", {"days": (int, "how many days ahead")}),
    tool("list_messages", "Read the messages in one client conversation thread.", {"thread_id": (str, "thread id")}),
    tool("create_proposal_draft", "Create (or with dry_run=true, PREVIEW without sending) a proposal for a job at a bid amount.",
         {"job_id": (str, "job id"), "bid_amount": (float, "USD"), "dry_run": (bool, "true = preview only")}),
]
TOOLSETS = {"fine": FINE, "coarse": COARSE, "best": BEST}


def tasks(n: int) -> list[dict]:
    jobs = jobs_by_id()
    dev = [r for p in PERSONAS for r in load_dev(p)]
    rng = random.Random(40)
    picks = rng.sample(dev, 8)
    kws = ["power bi dashboard", "langchain rag chatbot", "next.js saas", "dbt snowflake"]
    cats = ["ml_ai", "web_dev", "data_analytics", "ml_ai"]
    skills = ["Celery", "Pinecone", "dbt", "row-level security"]
    out = []
    for i in range(4):
        j = jobs[picks[i]["job_id"]]
        out += [
            {"intent": "search", "task": f"Find new jobs about '{kws[i]}'.",
             "ok": {"best": ("search_jobs", {"query": kws[i]}), "fine": ("search_jobs_by_keyword", {"keyword": kws[i]}),
                    "coarse": ("marketplace", {"action": "search_jobs", "query": kws[i]})}},
            {"intent": "get_job", "task": f"Show me the full post for job {j['job_id']}.",
             "ok": {"best": ("get_job", {"job_id": j["job_id"]}), "fine": ("get_job_description", {"job_id": j["job_id"]}),
                    "coarse": ("marketplace", {"action": "get_job", "job_id": j["job_id"]})}},
            {"intent": "client", "task": f"Is client {j['client_id']} trustworthy? Check their history.",
             "ok": {"best": ("get_client_history", {"client_id": j["client_id"]}), "fine": (["get_client_rating", "get_client_spend"], {"client_id": j["client_id"]}),
                    "coarse": ("marketplace", {"action": "get_client_history", "client_id": j["client_id"]})}},
            {"intent": "connects", "task": "How many Connects do I have left?",
             "ok": {"best": ("get_connects_balance", {}), "fine": ("get_connects_balance", {}), "coarse": ("marketplace", {"action": "get_connects_balance"})}},
            {"intent": "market", "task": f"What do similar {cats[i]} jobs usually pay?",
             "ok": {"best": ("get_market_stats", {"category": cats[i]}), "fine": ("get_market_rates", {"category": cats[i]}),
                    "coarse": ("marketplace", {"action": "get_market_stats", "category": cats[i]})}},
            {"intent": "evidence", "task": f"Find evidence in my portfolio that I have used {skills[i]}.",
             "ok": {"best": ("search_evidence", {"requirement": skills[i]}), "fine": (["search_case_studies", "search_code", "search_reviews"], {"query": skills[i]}),
                    "coarse": ("portfolio", {"action": "search", "query": skills[i]})}},
            {"intent": "case", "task": "Open my case study case-churn-predictor.",
             "ok": {"best": ("get_case_study", {"id": "case-churn-predictor"}), "fine": ("get_case_study", {"id": "case-churn-predictor"}),
                    "coarse": ("portfolio", {"action": "get", "query": "case-churn-predictor"})}},
            {"intent": "slots", "task": "When am I free for a 30-minute call in the next 5 days?",
             "ok": {"best": ("free_slots", {"days": 5}), "fine": ("list_free_slots", {"days": 5}), "coarse": ("workspace", {"action": "free_slots"})}},
            {"intent": "messages", "task": f"Read the messages in thread th_{picks[4 + i]['job_id'][-6:]}.",
             "ok": {"best": ("list_messages", {"thread_id": f"th_{picks[4 + i]['job_id'][-6:]}"}),
                    "fine": ("list_messages", {"thread_id": f"th_{picks[4 + i]['job_id'][-6:]}"}),
                    "coarse": ("marketplace", {"action": "list_messages", "thread_id": f"th_{picks[4 + i]['job_id'][-6:]}"})}},
            {"intent": "preview", "task": f"Preview, without sending, a proposal for job {j['job_id']} at $450.",
             "ok": {"best": ("create_proposal_draft", {"job_id": j["job_id"], "bid_amount": 450, "dry_run": True}),
                    "fine": ("preview_proposal", {"job_id": j["job_id"], "amount": 450}),
                    "coarse": ("marketplace", {"action": "create_proposal_draft", "job_id": j["job_id"], "dry_run": True})}},
        ]
    return out[:n]


def arg_ok(expected: dict, got: dict) -> bool:
    for k, v in expected.items():
        g = got.get(k)
        if isinstance(v, str):
            if not isinstance(g, str) or (v.lower() not in g.lower() and g.lower() not in v.lower()):
                return False
        elif isinstance(v, bool):
            if bool(g) != v:
                return False
        elif isinstance(v, (int, float)):
            try:
                if abs(float(g) - float(v)) > 0.01:
                    return False
            except (TypeError, ValueError):
                return False
    return True


async def main_async(args) -> None:
    setup_env(args.profile)
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.llm import chat_model_for
    from agent.prompting import load_prompt

    model = chat_model_for("intent")
    p = load_prompt("tool_task")
    ts = tasks(args.n)
    results = {}
    for name, tools in TOOLSETS.items():
        bound = model.bind_tools(tools)
        rows = []
        for t in ts:
            sysm, user = p.render(task=t["task"])
            t0 = time.perf_counter()
            try:
                msg = await asyncio.wait_for(bound.ainvoke([SystemMessage(sysm), HumanMessage(user)]), timeout=300)
                calls = msg.tool_calls or []
                um = msg.usage_metadata or {}
            except Exception as exc:  # noqa: BLE001
                calls, um = [], {}
                print("error", name, exc)
            exp_tool, exp_args = t["ok"][name]
            names = exp_tool if isinstance(exp_tool, list) else [exp_tool]
            first = calls[0] if calls else None
            sel = bool(first and first["name"] in names)
            rows.append({"intent": t["intent"], "selected": first["name"] if first else None, "selection_ok": sel,
                         "args_ok": bool(sel and arg_ok(exp_args, first.get("args") or {})),
                         "tokens": int(um.get("input_tokens", 0)) + int(um.get("output_tokens", 0)), "latency_s": time.perf_counter() - t0})
        results[name] = {"n": len(rows), "tool_selection_accuracy": mean([float(r["selection_ok"]) for r in rows]),
                         "argument_accuracy": mean([float(r["args_ok"]) for r in rows]), "tokens_per_task": mean([r["tokens"] for r in rows]),
                         "p50_latency_s": sorted(r["latency_s"] for r in rows)[len(rows) // 2], "n_tools": len(tools), "rows": rows}
        print(name, {k: v for k, v in results[name].items() if k != "rows"})
    save(args.out or "tool_granularity", {"model": getattr(model, "model", getattr(model, "model_name", "")), "results": results})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--profile", default="open_local")
    ap.add_argument("--out")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
