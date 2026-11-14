"""Typed graph state + reducers (C2).

Three things are kept apart:
* State (this file): what one job / conversation needs right now. Hand-off objects as dicts.
* Execution trace: tool names, arguments, results -> MCP audit log + LangSmith + run_events table.
  Never stored here.
* Long-term memory: only promoted knowledge in the LangGraph store (agent/memory/).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    out = dict(a or {})
    out.update(b or {})
    return out


def merge_usage(a: dict | None, b: dict | None) -> dict:
    """Sum per-node usage written by parallel branches: {node: {calls, in, out, usd, latency_s}}."""
    out: dict[str, dict[str, float]] = {k: dict(v) for k, v in (a or {}).items()}
    for node, u in (b or {}).items():
        cur = out.setdefault(node, {})
        for key, val in u.items():
            if key == "latency_max_s":
                cur[key] = max(cur.get(key, 0.0), val)
            else:
                cur[key] = cur.get(key, 0) + val
    return out


def merge_evidence(a: list | None, b: list | None) -> list:
    seen: dict[str, dict] = {e["evidence_id"]: e for e in (a or [])}
    for e in b or []:
        if e["evidence_id"] not in seen or e.get("score", 0) > seen[e["evidence_id"]].get("score", 0):
            seen[e["evidence_id"]] = e
    return list(seen.values())


def last_value(a: Any, b: Any) -> Any:
    return b if b is not None else a


_SEVERITY = {"dead_letter": 3, "needs_attention": 2, "blocked": 2}


def merge_status(a: str | None, b: str | None) -> str | None:
    """Parallel branches may both write a status; keep the most severe halt, otherwise the latest value."""
    if b is None:
        return a
    if a is not None and _SEVERITY.get(a, 0) > _SEVERITY.get(b, 0):
        return a
    return b


class BidState(TypedDict, total=False):
    # identity
    thread_id: str
    user_id: str
    persona_id: str
    job_id: str
    trace_id: str
    # inputs
    job: dict[str, Any]
    user_profile: dict[str, Any]
    # analyses (written by the three parallel branches -> separate keys, no conflicts)
    job_spec: dict[str, Any]
    risk: dict[str, Any]
    fit: dict[str, Any]
    evidence: Annotated[list[dict[str, Any]], merge_evidence]
    # decision + price
    decision: dict[str, Any]
    price: dict[str, Any]
    # drafting loop
    drafts: Annotated[list[dict[str, Any]], operator.add]
    verifications: Annotated[list[dict[str, Any]], operator.add]
    critiques: Annotated[list[dict[str, Any]], operator.add]
    revision: int
    compliance: dict[str, Any]
    preview: dict[str, Any]
    # human
    approvals: Annotated[list[dict[str, Any]], operator.add]
    submission: dict[str, Any]
    outcome: dict[str, Any]
    # control
    status: Annotated[str, merge_status]
    status_reason: Annotated[str, last_value]
    usage: Annotated[dict[str, dict[str, float]], merge_usage]
    steps: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]


class ConversationState(TypedDict, total=False):
    thread_id: str              # graph thread id: conv:{user}:{marketplace_thread}
    marketplace_thread_id: str
    user_id: str
    persona_id: str
    job_id: str
    proposal_id: str
    trace_id: str
    messages: list[dict[str, Any]]
    last_client_message: dict[str, Any]
    intent: dict[str, Any]
    slots: list[dict[str, Any]]
    draft: dict[str, Any]
    compliance: dict[str, Any]
    approvals: Annotated[list[dict[str, Any]], operator.add]
    sent: dict[str, Any]
    pipeline_stage: str
    status: Annotated[str, merge_status]
    status_reason: Annotated[str, last_value]
    usage: Annotated[dict[str, dict[str, float]], merge_usage]
    steps: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]
