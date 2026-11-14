"""Freelancer profile used by the graphs: persona defaults (data/personas/<id>/profile.json) overlaid with the
user's own settings from the database (rates, floor, connects budget, autonomy, saved searches)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from agent.settings import cfg, data_dir


@lru_cache(maxsize=16)
def persona_profile(persona_id: str) -> dict[str, Any]:
    p = data_dir() / "personas" / persona_id / "profile.json"
    prof = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"persona_id": persona_id}
    prof.setdefault("categories", (cfg(f"personas.{persona_id}", {}) or {}).get("categories", []))
    return prof


def merged_profile(persona_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    prof = dict(persona_profile(persona_id))
    prof.update({k: v for k, v in (overrides or {}).items() if v is not None})
    prof.setdefault("autonomy", cfg("autonomy.default", "suggest"))
    prof.setdefault("weekly_connects", int(cfg("bidding_rules.connects.weekly_budget_default", 80)))
    return prof
