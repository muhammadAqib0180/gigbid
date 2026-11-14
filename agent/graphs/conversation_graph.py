"""Conversation graph (one thread per client conversation): load -> classify -> draft -> compliance ->
approval (interrupt) -> send. Edits loop back through compliance."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes.client_liaison import classify, draft_reply, load_thread, message_approval, message_compliance, send_reply
from agent.nodes.common import halted
from agent.state import ConversationState


def _r(target: str, idle_to_end: bool = False):
    def route(state: ConversationState) -> str:
        h = halted(state)
        if h:
            return h
        if idle_to_end and state.get("status") == "idle":
            return "end"
        return target

    route.__name__ = f"to_{target}"
    return route


def _after_approval(state: ConversationState) -> str:
    h = halted(state)
    if h:
        return h
    return {"approved": "send_reply", "recheck": "message_compliance"}.get(state.get("status", ""), "end")


async def needs_attention(state, config=None, store=None):
    return {"status": "needs_attention" if state.get("status") != "blocked" else "blocked"}


async def dead_letter(state, config=None, store=None):
    return {"status": "dead_letter"}


def build_conversation_graph(checkpointer: Any = None, store: Any = None):
    g = StateGraph(ConversationState)
    for name, fn in (("load_thread", load_thread), ("classify", classify), ("draft_reply", draft_reply),
                     ("message_compliance", message_compliance), ("message_approval", message_approval), ("send_reply", send_reply),
                     ("needs_attention", needs_attention), ("dead_letter", dead_letter)):
        g.add_node(name, fn)
    halts = {"needs_attention": "needs_attention", "dead_letter": "dead_letter"}
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _r("classify", idle_to_end=True), {"classify": "classify", "end": END, **halts})
    g.add_conditional_edges("classify", _r("draft_reply"), {"draft_reply": "draft_reply", **halts})
    g.add_conditional_edges("draft_reply", _r("message_compliance"), {"message_compliance": "message_compliance", **halts})
    g.add_conditional_edges("message_compliance", _r("message_approval"), {"message_approval": "message_approval", **halts})
    g.add_conditional_edges("message_approval", _after_approval, {"send_reply": "send_reply", "message_compliance": "message_compliance",
                                                                  "end": END, **halts})
    g.add_conditional_edges("send_reply", _r("end"), {"end": END, **halts})
    g.add_edge("needs_attention", END)
    g.add_edge("dead_letter", END)
    return g.compile(checkpointer=checkpointer, store=store, name="conversation_graph")
