"""Pricing Strategist: bid from market statistics (Kaggle-derived), client spend and the user's floor; decides
whether the Connects cost is worth it. Connects formula comes from config bidding_rules (change request)."""

from __future__ import annotations

import math

from agent.handoffs import FitReport, PriceQuote, RiskReport
from agent.mcp_client import ToolFailed
from agent.nodes.common import gateway, node
from agent.profile import merged_profile
from agent.settings import cfg


def connects_cost(job: dict) -> int:
    """The marketplace's own price (already under its current policy) is authoritative. The config formula
    (bidding_rules.connects) is only used to ESTIMATE when no price is reported. Before the change request this
    added the surcharge on top of GigSim's surcharged price - double counting (report section 6)."""
    if job.get("connects_cost") is not None:
        return int(job["connects_cost"])
    rule = cfg("bidding_rules.connects", {}) or {}
    base = int(job.get("connects") or 6)
    budget = float(job.get("budget") or 0)
    step = float(rule.get("step_usd", 1000) or 1000)
    if rule.get("per_budget_step") and budget > float(rule.get("step_from_usd", 0)):
        return base + int(rule["per_budget_step"]) * math.ceil((budget - float(rule["step_from_usd"])) / step)
    return base


def quote(job: dict, fit: FitReport, risk: RiskReport, profile: dict, stats: dict, client: dict | None, balance: dict | None) -> PriceQuote:
    rationale: list[str] = []
    if job.get("is_hourly"):
        rate = float(profile.get("hourly_rate_usd", 30))
        paid = (stats.get("hourly_paid") or {})
        p50 = paid.get("p50")
        if p50:
            rationale.append(f"market paid hourly p50 ${p50:.0f} (n={stats.get('hourly_paid_n', 0)})")
        lo_job, hi_job = job.get("hourly_low"), job.get("hourly_high")
        amount = rate * (0.9 + 0.2 * fit.score)
        if hi_job:
            amount = min(amount, float(hi_job))
            rationale.append(f"client range ${lo_job or '?'}-${hi_job}/h")
        floor = float(profile.get("min_hourly_usd", rate * 0.7))
        amount = max(floor, amount)
        rationale.append(f"your rate ${rate:.0f}/h, floor ${floor:.0f}/h, fit {fit.score:.2f}")
        low, high = floor, max(amount, float(hi_job or amount))
        unit = "hourly"
    else:
        budget = float(job.get("budget") or 0)
        fb = stats.get("fixed_budget") or {}
        floor = float(profile.get("min_fixed_usd", 150))
        if budget > 0:
            amount = budget * (0.92 + 0.08 * fit.score)
            rationale.append(f"client budget ${budget:,.0f}; bid {amount / budget:.0%} of it given fit {fit.score:.2f}")
        else:
            amount = float(fb.get("p50") or floor * 2)
            rationale.append(f"no budget stated: market fixed-price p50 ${amount:,.0f} for {stats.get('category')}")
        if client and client.get("avg_hourly_paid"):
            rationale.append(f"client historically paid ~${client['avg_hourly_paid']:.0f}/h")
        amount = max(floor, amount)
        low, high = max(floor, amount * 0.85), max(amount, budget * 1.05 if budget else amount * 1.2)
        unit = "fixed"
        if fb.get("p25") and fb.get("p75"):
            rationale.append(f"market fixed p25-p75 ${fb['p25']:,.0f}-${fb['p75']:,.0f}")
    cost = connects_cost(job)
    bal = int(balance.get("balance")) if balance and balance.get("balance") is not None else None
    p_reply = max(0.02, min(0.6, 0.06 + 0.4 * fit.score - 0.3 * risk.score))
    value = amount if unit == "fixed" else amount * 10
    ev_per_connect = p_reply * 0.35 * value / max(1, cost)
    worth = ev_per_connect >= float(cfg("bidding_rules.connects.min_expected_value_per_connect_usd", 1.0)) and (bal is None or bal >= cost)
    rationale.append(f"{cost} Connects; est. reply chance {p_reply:.0%}; expected value ${ev_per_connect:,.2f} per Connect")
    if bal is not None and bal < cost:
        rationale.append(f"only {bal} Connects left")
    return PriceQuote(amount=round(amount, 2), unit=unit, low=round(low, 2), high=round(high, 2), rationale=rationale,
                      connects_cost=cost, connects_balance=bal, connects_worth_it=worth, expected_value_usd=round(ev_per_connect, 2))


@node("pricing")
async def pricing(state, config, store):
    job = state["job"]
    gw = gateway(state)
    profile = merged_profile(state.get("persona_id", "ai_ml_engineer"), state.get("user_profile"))
    stats = await gw.call("pricing", "marketplace", "get_market_stats", {"category": job.get("category") or "other"})
    client = None
    if job.get("client_id"):
        try:
            client = await gw.call("pricing", "marketplace", "get_client_history", {"client_id": job["client_id"]})
        except ToolFailed:
            pass
    balance = await gw.call("pricing", "marketplace", "get_connects_balance", {})
    q = quote(job, FitReport.model_validate(state["fit"]), RiskReport.model_validate(state["risk"]), profile, stats, client, balance)
    out = {"price": q.model_dump(), "_summary": f"${q.amount:,.0f} {q.unit}; {q.connects_cost} Connects; worth it: {q.connects_worth_it}"}
    if not q.connects_worth_it:
        out.update({"status": "watching", "status_reason": "Connects cost not worth it: " + q.rationale[-1]})
    return out
