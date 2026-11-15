"""Part A deliverable: a SINGLE agent drafting one grounded proposal for a GigSim job, using only MCP tools
(marketplace read + portfolio read). Saves the transcript to evals/results/single_agent_demo.json.

    python -m scripts.demo_single_agent --job dv_ai__exac_000 --persona ai_ml_engineer --profile open
"""

from __future__ import annotations

import argparse
import asyncio
import json

from evals.runners.common import save, setup_env


async def main_async(args) -> None:
    setup_env(args.profile)
    from langchain_mcp_adapters.tools import load_mcp_tools
    from langgraph.prebuilt import create_react_agent

    from agent.llm import chat_model_for
    from agent.mcp_client import ToolGateway
    from agent.prompting import load_prompt
    from rag.verify import verify_claims

    gw = ToolGateway("demo", args.persona)
    async with gw.session("marketplace") as ms, gw.session("portfolio") as ps:
        tools = [t for t in (await load_mcp_tools(ms)) + (await load_mcp_tools(ps))
                 if t.name in {"get_job", "get_client_history", "search_evidence", "get_case_study"}]
        agent = create_react_agent(chat_model_for("writer"), tools, prompt=load_prompt("single_agent").render(job_id=args.job, persona=args.persona)[0])
        user = load_prompt("single_agent").render(job_id=args.job, persona=args.persona)[1]
        out = await agent.ainvoke({"messages": [("user", user)]}, {"recursion_limit": 16})
    msgs = out["messages"]
    transcript = [{"type": m.type, "content": str(m.content)[:1500], "tool_calls": [{"name": c["name"], "args": c["args"]} for c in getattr(m, "tool_calls", []) or []]}
                  for m in msgs]
    evidence = []
    for m in msgs:
        if m.type == "tool":
            try:
                evidence += json.loads(m.content).get("items", [])
            except (json.JSONDecodeError, AttributeError):
                pass
    final = str(msgs[-1].content)
    letter = final
    try:
        letter = json.loads(final[final.find("{"): final.rfind("}") + 1]).get("cover_letter") or final
    except json.JSONDecodeError:
        pass
    _, rep = verify_claims(letter, evidence or [{"evidence_id": "none", "item_id": "none", "type": "none", "snippet": ""}])
    save("single_agent_demo", {"job_id": args.job, "persona": args.persona, "tool_calls": [c for t in transcript for c in t["tool_calls"]],
                               "final": final[:4000], "claims": rep.total_claims, "unsupported": rep.unsupported_before, "transcript": transcript})
    print(final[:2000])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="dv_ai__exac_000")
    ap.add_argument("--persona", default="ai_ml_engineer")
    ap.add_argument("--profile", default="open")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
