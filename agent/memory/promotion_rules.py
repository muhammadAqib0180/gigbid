"""Explicit promotion rules for long-term memory (R7, C2).

Nothing reaches long-term memory except through these functions, and they only accept typed inputs
(an approved edit diff, or a marketplace outcome event) - never raw tool output.

STYLE memory (learned from the user's edits to drafts)
  1. Every approved edit is diffed; deterministic extractors produce candidate rules:
       - banned_word:<w>       a word/phrase the user deleted and never added back
       - cut_greeting          the user removed a greeting / generic first sentence
       - shorter               the user cut >= 20% of the words
       - no_exclamations       the user removed exclamation marks
  2. A candidate is PROMOTED to a style rule when it was observed in >= `memory.style.min_distinct_proposals`
     DIFFERENT proposals within `memory.style.window_days` days, or the user clicked "Remember this".
  3. A rule that conflicts with platform policy (e.g. "always add my email") is never promoted.

OUTCOME memory (what won or got replies per job category)
  - Each outcome event (submitted -> replied / interview / hired / lost) increments per-category counters
    keyed by proposal strategy and opening style.
  - An insight is PROMOTED only when the category has >= `memory.outcome.min_outcomes` outcomes and the reply
    rate of one strategy beats the other by >= `memory.outcome.min_reply_rate_lift`.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

from agent.safety import contact_detail_spans
from agent.settings import cfg

GREETING = re.compile(r"^(dear|hi|hello|hey|greetings|good (morning|afternoon|evening)|i hope|i am writing|i am excited)\b", re.I)
STOPWORDS = set("a an the and or of to in for on with is are was were be been i my me you your we our it this that as at by from".split())


def should_promote_style_edit(edit_count: int, consistent_pattern: bool) -> bool:
    """Kept from the starter kit; the rule below is the one used by the graph."""
    return edit_count >= int(cfg("memory.style.min_distinct_proposals", 3)) and consistent_pattern


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'\-]+", text.lower())


def extract_edit_patterns(original: str, edited: str) -> list[dict[str, str]]:
    """Deterministic candidate rules from one (original, edited) pair."""
    out: list[dict[str, str]] = []
    o_first = re.split(r"(?<=[.!?])\s+", original.strip())[0] if original.strip() else ""
    e_first = re.split(r"(?<=[.!?])\s+", edited.strip())[0] if edited.strip() else ""
    if o_first and GREETING.match(o_first) and o_first not in edited:
        out.append({"key": "cut_greeting", "rule": "Do not open with a greeting or generic first sentence; start with the client's problem."})
    elif o_first and o_first != e_first and o_first not in edited:
        out.append({"key": "cut_first_sentence", "rule": "Cut the first sentence of the draft; open with the most specific line."})
    ow, ew = _words(original), _words(edited)
    if ow and len(ew) <= 0.8 * len(ow):
        out.append({"key": "shorter", "rule": f"Keep proposals short (about {max(80, len(ew))} words or fewer)."})
    if original.count("!") > edited.count("!") and edited.count("!") == 0:
        out.append({"key": "no_exclamations", "rule": "Do not use exclamation marks."})
    removed = set()
    dropped_first = set(_words(o_first)) if any(p["key"] in {"cut_greeting", "cut_first_sentence"} for p in out) else set()
    sm = difflib.SequenceMatcher(a=ow, b=ew)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in {"delete", "replace"}:
            for w in ow[i1:i2]:
                if w not in STOPWORDS and len(w) > 3 and w not in ew:
                    removed.add(w)
    # words that only disappeared because the whole greeting sentence was cut are covered by that rule,
    # except obviously-styled words the user also removed elsewhere
    removed = {w for w in removed if w not in dropped_first or w in ow[len(_words(o_first)):]}
    for w in sorted(removed)[:5]:
        out.append({"key": f"banned_word:{w}", "rule": f"Never use the word '{w}'."})
    return out


def conflicts_with_policy(rule: str) -> bool:
    low = rule.lower()
    if contact_detail_spans(rule):
        return True
    return any(t in low for t in (cfg("bidding_rules.off_platform_terms", []) or [])) or "guarantee" in low


def update_style_candidate(candidate: dict[str, Any] | None, pattern: dict[str, str], proposal_id: str,
                           now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    window = float(cfg("memory.style.window_days", 30)) * 86400
    c = dict(candidate or {"key": pattern["key"], "rule": pattern["rule"], "proposals": {}, "promoted": False})
    seen = {pid: ts for pid, ts in c.get("proposals", {}).items() if now - ts <= window}
    seen[proposal_id] = now
    c["proposals"] = seen
    c["rule"] = pattern["rule"]
    return c


def promote_style(candidate: dict[str, Any], explicit: bool = False) -> bool:
    """THE style promotion rule."""
    if conflicts_with_policy(candidate["rule"]):
        return False
    if explicit:
        return True
    return len(candidate.get("proposals", {})) >= int(cfg("memory.style.min_distinct_proposals", 3))


def update_outcome_stats(stats: dict[str, Any] | None, event: dict[str, Any]) -> dict[str, Any]:
    """event: {proposal_id, category, strategy, opening, outcome in submitted|replied|interview|hired|lost}"""
    s = dict(stats or {"by_strategy": {}, "proposals": {}})
    pid = event["proposal_id"]
    prev = s["proposals"].get(pid, {})
    rank = {"submitted": 0, "lost": 0, "replied": 1, "interview": 2, "hired": 3}
    if prev and rank.get(event["outcome"], 0) <= rank.get(prev.get("outcome", "submitted"), 0) and event["outcome"] != "lost":
        return s
    s["proposals"][pid] = {"strategy": event.get("strategy", "evidence_first"), "outcome": event["outcome"]}
    agg: dict[str, dict[str, int]] = {}
    for p in s["proposals"].values():
        a = agg.setdefault(p["strategy"], {"sent": 0, "replied": 0, "hired": 0})
        a["sent"] += 1
        a["replied"] += int(rank.get(p["outcome"], 0) >= 1)
        a["hired"] += int(p["outcome"] == "hired")
    s["by_strategy"] = agg
    return s


def promote_outcome_insight(category: str, stats: dict[str, Any]) -> str | None:
    """THE outcome promotion rule: enough outcomes AND a real difference between strategies."""
    agg = stats.get("by_strategy", {})
    total = sum(a["sent"] for a in agg.values())
    if total < int(cfg("memory.outcome.min_outcomes", 5)):
        return None
    rates = {k: a["replied"] / a["sent"] for k, a in agg.items() if a["sent"] >= 2}
    if not rates:
        return None
    best = max(rates, key=rates.get)
    others = [v for k, v in rates.items() if k != best]
    lift = rates[best] - (max(others) if others else 0.0)
    if others and lift < float(cfg("memory.outcome.min_reply_rate_lift", 0.10)):
        return None
    return (f"In {category} jobs, '{best}' proposals got replies {rates[best]:.0%} of the time "
            f"(n={agg[best]['sent']}{', ' + f'{lift:+.0%} vs the alternative' if others else ''}).")
