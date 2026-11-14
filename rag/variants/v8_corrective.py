"""V8 (agentic, required one of V8/V9): corrective RAG loop as a LangGraph StateGraph.

grade -> (re-query weak requirements with expanded terms) -> grade -> finalize.
A requirement whose best evidence stays below `rag.corrective.weak_score` is marked weak: the Writer is
told it has NO evidence and must not claim it (refuse to claim when none). This is what lets the persona
skip jobs it cannot prove fit for.

Full stack: decomposition + hybrid + rerank + outcome boost + structured multi-vector + corrective.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent.handoffs import Requirement
from agent.settings import cfg
from agent.skills import BROAD, canon
from rag.variants.base import PipelineConfig

VARIANT = PipelineConfig(name="v8_corrective", query="decompose", retriever="hybrid", rerank=True, outcome_boost=True,
                         chunking="structured", group_projects=True, corrective=True,
                         description="Corrective RAG loop: grade evidence, re-query when weak, refuse to claim when none")

SYNONYMS = {
    "dashboard": "dashboards Power BI Tableau Looker Studio reporting KPI",
    "chatbot": "assistant RAG retrieval LLM support bot",
    "scrape": "data collection ETL ingestion",
    "website": "web app Next.js React landing pages",
    "payments": "Stripe billing subscriptions payouts",
    "forecast": "forecasting demand time series",
    "automation": "automated pipeline scheduled jobs scripts",
    "api": "REST APIs FastAPI endpoints integration",
}


class CRAGState(TypedDict, total=False):
    queries: dict[str, str]
    per_query: dict[str, list[tuple[int, float]]]
    weak: list[str]
    round: int


def _expand(text: str, req: Requirement | None) -> str:
    extra = []
    for s in (req.skills if req else []):
        extra += BROAD.get(canon(s), [])
    low = text.lower()
    for k, v in SYNONYMS.items():
        if k in low:
            extra.append(v)
    return text + " " + " ".join(dict.fromkeys(extra))


def corrective_loop(pipeline: Any, corpus: Any, queries: dict[str, str], per_query: dict, mask: Any,
                    reqs: list[Requirement]) -> tuple[dict, list[str]]:
    weak_thr = float(cfg("rag.corrective.weak_score", 0.15))
    max_rounds = int(cfg("rag.corrective.max_requery", 1))
    req_by_id = {r.id: r for r in reqs}

    def grade(state: CRAGState) -> CRAGState:
        weak = [qid for qid, lst in state["per_query"].items() if not lst or lst[0][1] < weak_thr]
        return {"weak": weak}

    def route(state: CRAGState) -> str:
        return "requery" if state["weak"] and state.get("round", 0) < max_rounds else "finalize"

    def requery(state: CRAGState) -> CRAGState:
        pq = dict(state["per_query"])
        for qid in state["weak"]:
            q = _expand(state["queries"][qid], req_by_id.get(qid))
            new = pipeline.candidates(corpus, q, mask, rerank=True)
            if new and (not pq.get(qid) or new[0][1] > pq[qid][0][1]):
                pq[qid] = new
        return {"per_query": pq, "round": state.get("round", 0) + 1}

    def finalize(state: CRAGState) -> CRAGState:
        pq = dict(state["per_query"])
        for qid in state["weak"]:
            pq[qid] = []          # refuse to claim: no evidence returned for this requirement
        return {"per_query": pq}

    g = StateGraph(CRAGState)
    g.add_node("grade", grade)
    g.add_node("requery", requery)
    g.add_node("finalize", finalize)
    g.add_edge(START, "grade")
    g.add_conditional_edges("grade", route, {"requery": "requery", "finalize": "finalize"})
    g.add_edge("requery", "grade")
    g.add_edge("finalize", END)
    out = g.compile().invoke({"queries": queries, "per_query": per_query, "round": 0})
    return out["per_query"], out.get("weak", [])
