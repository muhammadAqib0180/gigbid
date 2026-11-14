"""Bid graph (one thread per job), hand-written StateGraph (R3, C1).

scout -> [analyst || risk || matcher] (Send) -> decide -> pricing -> writer -> verifier -> critic
      -> (revise, max 2) writer | compliance -> prepare_approval -> approval (interrupt) -> submit
Every router first checks for a halt (budget exceeded -> needs_attention, repeated failure -> dead_letter).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, finalize, prepare_approval, submit
from agent.nodes.common import halted, last
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import scout_intake
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

PARALLEL = ("analyst", "risk", "matcher")


def _fan_out(state: BidState) -> Any:
    h = halted(state)
    if h:
        return h
    return [Send(n, state) for n in PARALLEL]


def _after_decide(state: BidState) -> str:
    h = halted(state)
    if h:
        return h
    return "pricing" if (state.get("decision") or {}).get("action") == "bid" else "finalize"


def _after_pricing(state: BidState) -> str:
    h = halted(state)
    if h:
        return h
    return "finalize" if state.get("status") == "watching" else "writer"


def _next(target: str):
    def route(state: BidState) -> str:
        return halted(state) or target

    route.__name__ = f"to_{target}"
    return route


def _after_critic(state: BidState) -> str:
    h = halted(state)
    if h:
        return h
    c = last(state, "critiques") or {}
    return "writer" if c.get("verdict") == "revise" else "compliance"


def _after_compliance(state: BidState) -> str:
    h = halted(state)
    if h:
        return h
    return "prepare_approval"


def _after_approval(state: BidState) -> str:
    h = halted(state)
    if h:
        return h
    s = state.get("status")
    return {"approved": "submit", "rejected": "finalize", "recheck": "compliance"}.get(s, "finalize")


async def needs_attention(state, config=None, store=None):
    return {"status": state.get("status") if state.get("status") in {"blocked", "needs_attention"} else "needs_attention"}


async def dead_letter(state, config=None, store=None):
    return {"status": "dead_letter"}


def build_bid_graph(checkpointer: Any = None, store: Any = None):
    g = StateGraph(BidState)
    g.add_node("scout", scout_intake)
    g.add_node("analyst", analyst)
    g.add_node("risk", risk_assessor)
    g.add_node("matcher", fit_matcher)
    g.add_node("decide", decide)
    g.add_node("pricing", pricing)
    g.add_node("writer", writer)
    g.add_node("verifier", verifier)
    g.add_node("critic", critic)
    g.add_node("compliance", compliance)
    g.add_node("prepare_approval", prepare_approval)
    g.add_node("approval", approval)
    g.add_node("submit", submit)
    g.add_node("finalize", finalize)
    g.add_node("needs_attention", needs_attention)
    g.add_node("dead_letter", dead_letter)

    halts = {"needs_attention": "needs_attention", "dead_letter": "dead_letter"}
    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", _fan_out, ["analyst", "risk", "matcher", "needs_attention", "dead_letter"])
    for n in PARALLEL:
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", _after_decide, {"pricing": "pricing", "finalize": "finalize", **halts})
    g.add_conditional_edges("pricing", _after_pricing, {"writer": "writer", "finalize": "finalize", **halts})
    g.add_conditional_edges("writer", _next("verifier"), {"verifier": "verifier", **halts})
    g.add_conditional_edges("verifier", _next("critic"), {"critic": "critic", **halts})
    g.add_conditional_edges("critic", _after_critic, {"writer": "writer", "compliance": "compliance", **halts})
    g.add_conditional_edges("compliance", _after_compliance, {"prepare_approval": "prepare_approval", **halts})
    g.add_conditional_edges("prepare_approval", _next("approval"), {"approval": "approval", **halts})
    g.add_conditional_edges("approval", _after_approval, {"submit": "submit", "finalize": "finalize", "compliance": "compliance", **halts})
    g.add_conditional_edges("submit", _next("finalize"), {"finalize": "finalize", **halts})
    g.add_edge("finalize", END)
    g.add_edge("needs_attention", END)
    g.add_edge("dead_letter", END)
    return g.compile(checkpointer=checkpointer, store=store, name="bid_graph")
