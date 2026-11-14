"""GigSim platform policy versions. v2 is the 2026-11-02 "platform policy update" (change request)."""

from __future__ import annotations

import math
import os

POLICIES: dict[str, dict] = {
    "2026-10": {
        "version": "2026-10",
        "summary": "Baseline rules: no off-platform contact or payment, no fabricated experience, no guarantees, fair automation.",
        "connects": {"per_budget_step": 0, "step_from_usd": 0, "step_usd": 1000},
        "required_disclosures": [],
        "max_proposals_per_client_per_week": 99,
    },
    "2026-11-02": {
        "version": "2026-11-02",
        "summary": (
            "Platform policy update: (1) AI-assisted proposals must carry the disclosure line "
            "'Disclosure: drafted with AI assistance and reviewed by me.'; (2) jobs with a budget above $1,000 "
            "cost 2 extra Connects per started $1,000 above that threshold."
        ),
        "connects": {"per_budget_step": 2, "step_from_usd": 1000, "step_usd": 1000},
        "required_disclosures": ["Disclosure: drafted with AI assistance and reviewed by me."],
        "max_proposals_per_client_per_week": 99,
    },
}


def active_version(override: str | None = None) -> str:
    v = override or os.getenv("GIGSIM_POLICY_VERSION", "2026-10")
    return v if v in POLICIES else "2026-10"


def connects_cost(job: dict, policy: dict) -> int:
    base = int(job.get("connects") or 6)
    rule = policy["connects"]
    budget = float(job.get("budget") or 0)
    if rule["per_budget_step"] and budget > rule["step_from_usd"]:
        steps = math.ceil((budget - rule["step_from_usd"]) / rule["step_usd"])
        base += rule["per_budget_step"] * steps
    return base
