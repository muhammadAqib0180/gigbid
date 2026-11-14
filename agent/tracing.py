"""Trace-id propagation + LangSmith configuration with PII masking (E3, E4).

One trace id is created per UI request (or accepted from X-Trace-Id), stored in a contextvar, written into
graph config metadata, sent to every MCP server (X-Trace-Id header + JWT claim) and into the audit log.
"""

from __future__ import annotations

import os
import uuid
from contextvars import ContextVar
from typing import Any

from agent.safety import mask_obj

_trace: ContextVar[str | None] = ContextVar("gigbid_trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    t = _trace.get()
    if not t:
        t = new_trace_id()
        _trace.set(t)
    return t


def set_trace_id(trace_id: str | None) -> str:
    t = trace_id or new_trace_id()
    _trace.set(t)
    return t


def tracing_enabled() -> bool:
    return bool(os.getenv("LANGSMITH_API_KEY")) and os.getenv("LANGSMITH_TRACING", "true").lower() == "true"


def _mask(inputs: dict[str, Any]) -> dict[str, Any]:
    return mask_obj(inputs)


_client = None


def callbacks() -> list[Any]:
    """LangSmith tracer whose client masks emails/phones/payment details in every input and output."""
    global _client
    if not tracing_enabled():
        return []
    from langchain_core.tracers import LangChainTracer
    from langsmith import Client

    if _client is None:
        _client = Client(hide_inputs=_mask, hide_outputs=_mask)
    return [LangChainTracer(client=_client, project_name=os.getenv("LANGSMITH_PROJECT", "gigbid"))]


def run_config(thread_id: str, trace_id: str, user_id: str, kind: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": thread_id, "user_id": user_id},
        "metadata": {"trace_id": trace_id, "user_id": user_id, "graph": kind, **(extra or {})},
        "tags": [kind, f"trace:{trace_id}"],
        "run_name": f"{kind}:{thread_id}",
        "callbacks": callbacks(),
        "recursion_limit": 80,
    }


def langsmith_url(trace_id: str) -> str | None:
    base = os.getenv("LANGSMITH_PROJECT_URL")
    return f"{base}?searchModel=%7B%22filter%22%3A%22has(tags%2C%20%5C%22trace%3A{trace_id}%5C%22)%22%7D" if base else None
