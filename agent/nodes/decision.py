"""Bid / watch / skip decision. Deterministic and explainable: thresholds live in config; the reasons are shown
in the job detail screen. Autonomy may auto-skip low-fit jobs but never auto-sends anything."""

from __future__ import annotations

from agent.handoffs import BidDecision, FitReport, RiskReport
from agent.nodes.common import node
from agent.profile import merged_profile
from agent.settings import cfg


def decide_rules(job: dict, risk: RiskReport, fit: FitReport, profile: dict) -> BidDecision:
    t = cfg("thresholds", {}) or {}
    reasons: list[str] = []
    if risk.is_scam:
        return BidDecision(action="skip", reasons=[f"likely scam: {', '.join(risk.flags[:4])}"], confidence=0.9,
                           auto=profile.get("autonomy") == "auto_skip_low_fit")
    if risk.score >= float(t.get("maximum_risk_score", 0.6)):
        return BidDecision(action="skip", reasons=[f"risk {risk.score:.2f} above limit ({', '.join(risk.flags[:3])})"], confidence=0.75)
    if (risk.client_quality or 0.5) < float(t.get("min_client_quality", 0.25)):
        reasons.append(f"weak client history (quality {risk.client_quality:.2f})")
    minimum = float(t.get("minimum_fit_score", 0.55))
    band = float(t.get("watch_band", 0.10))
    if fit.score < minimum - band:
        return BidDecision(action="skip", reasons=[f"fit {fit.score:.2f} below {minimum:.2f}"] + fit.reasons[1:2],
                           confidence=0.7, auto=profile.get("autonomy") == "auto_skip_low_fit")
    if job.get("is_hourly"):
        hi = job.get("hourly_high")
        if hi and float(hi) < float(profile.get("min_hourly_usd", 0)):
            return BidDecision(action="skip", reasons=[f"hourly max ${hi} below your floor ${profile.get('min_hourly_usd')}"], confidence=0.8)
    else:
        b = job.get("budget")
        if b and float(b) < float(profile.get("min_fixed_usd", 0)):
            return BidDecision(action="skip", reasons=[f"budget ${b} below your minimum ${profile.get('min_fixed_usd')}"], confidence=0.8)
    if fit.score < minimum:
        return BidDecision(action="watch", reasons=[f"fit {fit.score:.2f} just under {minimum:.2f}: watch for more details"] + reasons,
                           confidence=0.5)
    return BidDecision(action="bid", reasons=[f"fit {fit.score:.2f}, risk {risk.score:.2f}"] + fit.reasons[:1] + reasons,
                       confidence=min(0.95, 0.5 + fit.score / 2))


@node("decide")
async def decide(state, config, store):
    if state.get("status") in {"dead_letter", "needs_attention"} or not all(k in state for k in ("risk", "fit")):
        # a parallel branch failed; the router sends the thread to dead_letter / needs_attention
        return {"status": state.get("status") if state.get("status") in {"dead_letter", "needs_attention"} else "dead_letter",
                "status_reason": state.get("status_reason") or "an analysis branch did not complete"}
    profile = merged_profile(state.get("persona_id", "ai_ml_engineer"), state.get("user_profile"))
    d = decide_rules(state["job"], RiskReport.model_validate(state["risk"]), FitReport.model_validate(state["fit"]), profile)
    status = {"bid": "drafting", "watch": "watching", "skip": "skipped"}[d.action]
    return {"decision": d.model_dump(), "status": status, "status_reason": "; ".join(d.reasons)[:300],
            "_summary": f"{d.action.upper()}: {d.reasons[0]}"}
