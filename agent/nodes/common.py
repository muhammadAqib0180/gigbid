"""Node plumbing shared by both graphs: budgets (C4), timeouts + bounded retries + dead-letter (C7),
progress events for the UI stream, and per-run tool gateways."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

from agent.llm import total_tokens
from agent.mcp_client import ToolFailed, ToolGateway, ToolUnavailable
from agent.settings import cfg

log = logging.getLogger("gigbid.nodes")
HALT_STATUSES = {"needs_attention", "dead_letter", "blocked"}


class MarketplaceDown(RuntimeError):
    """Raised (not dead-lettered) so the worker defers the thread and resumes from the last checkpoint."""


def gateway(state: dict[str, Any]) -> ToolGateway:
    return ToolGateway(state.get("user_id", "local"), state.get("persona_id", "ai_ml_engineer"), state.get("trace_id"))


def emit(event: dict[str, Any]) -> None:
    try:
        get_stream_writer()(event)
    except Exception:  # noqa: BLE001 - not inside a streaming run
        pass


def over_budget(state: dict[str, Any], kind: str = "job") -> str | None:
    steps = int(state.get("steps", 0) or 0)
    if steps >= int(cfg("budgets.max_graph_steps", 40)):
        return f"step budget exceeded ({steps} steps)"
    limit = int(cfg("budgets.max_tokens_per_job" if kind == "job" else "budgets.max_tokens_per_conversation", 24000))
    used = total_tokens(state.get("usage") or {})
    if used >= limit:
        return f"token budget exceeded ({used} >= {limit} tokens)"
    return None


def node(name: str, kind: str = "job", retries: int | None = None) -> Callable:
    """Decorator: budget gate, timeout, bounded retries with backoff, dead-letter, stream events.

    Transient marketplace outages raise MarketplaceDown so the run stops at the last checkpoint and the
    worker re-queues it (degraded mode); other repeated failures send the thread to dead_letter.
    """

    def deco(fn: Callable[..., Awaitable[dict[str, Any]]]) -> Callable[..., Awaitable[dict[str, Any]]]:
        @functools.wraps(fn)
        async def wrapped(state: dict[str, Any], config: Any = None, store: Any = None) -> dict[str, Any]:
            reason = over_budget(state, kind)
            if reason:
                emit({"node": name, "event": "halted", "reason": reason})
                return {"status": "needs_attention", "status_reason": reason}
            emit({"node": name, "event": "started", "ts": time.time()})
            n = cfg("budgets.node_retries", 2) if retries is None else retries
            t0 = time.perf_counter()
            last: Exception | None = None
            for attempt in range(int(n) + 1):
                try:
                    out = await asyncio.wait_for(fn(state, config, store), timeout=float(cfg("budgets.node_timeout_s", 120)) * 2)
                    out = dict(out or {})
                    out["steps"] = out.get("steps", 0) + 1
                    emit({"node": name, "event": "finished", "latency_s": round(time.perf_counter() - t0, 3),
                          "summary": out.pop("_summary", None), "status": out.get("status")})
                    out.pop("_summary", None)
                    return out
                except GraphBubbleUp:
                    raise
                except ToolUnavailable as exc:
                    last = exc
                    if exc.server == "marketplace":
                        emit({"node": name, "event": "degraded", "reason": str(exc)})
                        raise MarketplaceDown(str(exc)) from exc
                except ToolFailed as exc:
                    last = exc
                    if exc.kind not in {"rate_limited", "unavailable"}:
                        break
                except (TimeoutError, asyncio.TimeoutError) as exc:
                    last = exc
                except MarketplaceDown:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    log.exception("node %s failed (attempt %s)", name, attempt + 1)
                if attempt < int(n):
                    await asyncio.sleep(0.5 * 2 ** attempt)
            emit({"node": name, "event": "failed", "error": f"{type(last).__name__}: {str(last)[:200]}"})
            return {"status": "dead_letter", "status_reason": f"{name} failed after retries: {type(last).__name__}: {str(last)[:200]}",
                    "errors": [f"{name}: {type(last).__name__}: {str(last)[:300]}"], "steps": 1}

        return wrapped

    return deco


def halted(state: dict[str, Any]) -> str | None:
    s = state.get("status")
    if s == "dead_letter":
        return "dead_letter"
    if s in {"needs_attention", "blocked"}:
        return "needs_attention"
    return None


def last(state: dict[str, Any], key: str) -> dict[str, Any] | None:
    v = state.get(key) or []
    return v[-1] if v else None
