"""Long-term memory in a LangGraph store (two stores/namespaces required by C2):

  ("style", user_id)              promoted style rules           <- promotion_rules.promote_style
  ("style_candidates", user_id)   candidates waiting for evidence
  ("outcome", user_id)            per-category outcome stats + promoted insight

Postgres (AsyncPostgresStore) in compose, SQLite (AsyncSqliteStore) locally - same API.
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.store.base import BaseStore

from agent.memory import promotion_rules as rules


async def style_rules(store: BaseStore | None, user_id: str) -> list[str]:
    if store is None:
        return []
    items = await store.asearch(("style", user_id), limit=50)
    return [i.value["rule"] for i in items]


async def outcome_insights(store: BaseStore | None, user_id: str, category: str | None) -> list[str]:
    if store is None:
        return []
    out = []
    items = await store.asearch(("outcome", user_id), limit=50)
    for i in items:
        if i.value.get("insight") and (not category or i.key == category):
            out.append(i.value["insight"])
    return out


async def record_edit(store: BaseStore | None, user_id: str, proposal_id: str, original: str, edited: str,
                      remember: bool = False) -> list[str]:
    """Apply the style promotion rule to one approved edit. Returns rules promoted by this edit."""
    if store is None or original.strip() == edited.strip():
        return []
    promoted = []
    for pat in rules.extract_edit_patterns(original, edited):
        ns = ("style_candidates", user_id)
        cur = await store.aget(ns, pat["key"])
        cand = rules.update_style_candidate(cur.value if cur else None, pat, proposal_id)
        await store.aput(ns, pat["key"], cand)
        if not cand.get("promoted") and rules.promote_style(cand, explicit=remember):
            cand["promoted"] = True
            await store.aput(ns, pat["key"], cand)
            await store.aput(("style", user_id), pat["key"], {
                "rule": cand["rule"], "promoted_at": time.time(), "evidence_proposals": sorted(cand["proposals"]),
                "promotion_rule": "explicit" if remember else f">= {len(cand['proposals'])} distinct proposals"})
            promoted.append(cand["rule"])
    return promoted


async def record_outcome(store: BaseStore | None, user_id: str, event: dict[str, Any]) -> str | None:
    if store is None:
        return None
    cat = event.get("category") or "other"
    cur = await store.aget(("outcome", user_id), cat)
    stats = rules.update_outcome_stats(cur.value.get("stats") if cur else None, event)
    insight = rules.promote_outcome_insight(cat, stats)
    await store.aput(("outcome", user_id), cat, {"stats": stats, "insight": insight, "updated_at": time.time()})
    return insight


async def list_memory(store: BaseStore, user_id: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for ns in ("style", "style_candidates", "outcome"):
        items = await store.asearch((ns, user_id), limit=200)
        out[ns] = [{"key": i.key, "value": i.value, "updated_at": str(i.updated_at)} for i in items]
    return out


async def delete_memory(store: BaseStore, user_id: str, namespace: str, key: str) -> None:
    await store.adelete((namespace, user_id), key)
    if namespace == "style":
        await store.adelete(("style_candidates", user_id), key)
