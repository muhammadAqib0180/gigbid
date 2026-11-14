"""Risk Assessor: client quality from history + scam / free-work / off-platform / injection flags.

Rules give a calibrated floor (cheap, deterministic); the small LLM adds judgement on top (hybrid).
A hard rule (e.g. off-platform payment + unverified payment) can mark a scam even if the LLM disagrees -
injected text cannot talk the system out of a red flag.
"""

from __future__ import annotations

import re

from agent import llm
from agent.handoffs import RiskReport
from agent.mcp_client import ToolFailed
from agent.nodes.common import gateway, node
from agent.safety import normalize_untrusted, scan_injection, wrap_untrusted
from agent.settings import cfg

SCAM_RULES: list[tuple[str, str, float]] = [
    ("unpaid_work", r"\b(unpaid|for free|free (sample|trial|test)|without pay|payment only if|no pay(ment)? (until|unless))\b", 0.45),
    ("unpaid_work", r"\b(test task|trial task)\b[^.]{0,80}\b(complete|full|entire|finished)\b", 0.35),
    ("off_platform_contact", r"\b(whatsapp|telegram|skype|wechat|signal app|discord|text me|my personal email|contact me (on|at|via))\b", 0.40),
    ("off_platform_payment", r"\b(usdt|crypto|bitcoin|btc|gift ?cards?|western union|wire (the|transfer)|cash ?app|zelle|venmo|outside the platform|avoid (the )?(platform )?fees)\b", 0.50),
    ("check_overpayment", r"\b(send you a check|deposit (it|the check)|keep your fee|wire the rest)\b", 0.60),
    ("credential_request", r"\b(bank (login|details|account)|password|verify your identity at|ssn|social security|id card photo)\b", 0.55),
    ("pay_upfront", r"\b(buy|purchase)\b[^.]{0,40}\b(license|software|kit|equipment)\b[^.]{0,40}\b(reimburse|refund)\b", 0.55),
    ("too_good_to_be_true", r"\$\s?\d{3,5}[^.]{0,30}\b(for|in)\s+(\d+|a few|thirty|30)\s*(minutes?|mins?)\b|\beasy money\b", 0.40),
    ("account_farming", r"\bcreate \d+ accounts\b|\bwith your own phone number\b", 0.50),
    ("external_link", r"\b[a-z0-9-]+\.(com|net|io|xyz|top)/?\S*\b[^.]{0,30}\b(verify|register|sign up|pay)\b|\bverify[^.]{0,40}\.(com|net|io|xyz)\b", 0.35),
]


def rule_signals(job: dict, client: dict | None) -> tuple[float, list[str], dict[str, float], list[str]]:
    text = normalize_untrusted(f"{job.get('title', '')}\n{job.get('description', '')}")
    flags: list[str] = []
    signals: dict[str, float] = {}
    score = 0.0
    for flag, rx, w in SCAM_RULES:
        if re.search(rx, text, re.I) and flag not in flags:
            flags.append(flag)
            signals[flag] = w
            score += w
    inj = scan_injection(text)
    inj_spans = [f.span for f in inj]
    if inj:
        flags.append("prompt_injection")
        signals["prompt_injection"] = 0.25
        score += 0.25
    cq = 0.5
    if client:
        cq = 0.2
        cq += 0.25 if client.get("payment_verified") else 0.0
        cq += min(0.25, float(client.get("total_spent") or 0) / 20000)
        cq += 0.15 if (client.get("rating") or 0) >= 4.5 else (0.05 if client.get("rating") else 0.0)
        cq += min(0.15, float(client.get("hire_rate") or 0) * 0.15)
        cq = max(0.0, min(1.0, cq))
        if not client.get("payment_verified"):
            flags.append("payment_unverified")
            signals["payment_unverified"] = 0.15
            score += 0.15
        if float(client.get("total_spent") or 0) == 0 and int(client.get("reviews_count") or 0) == 0:
            flags.append("no_history")
            signals["no_history"] = 0.10
            score += 0.10
    budget = float(job.get("budget") or 0)
    if not job.get("is_hourly") and budget == 0 and "unpaid_work" not in flags:
        flags.append("no_budget")
        signals["no_budget"] = 0.05
        score += 0.05
    return min(1.0, score), flags, {**signals, "client_quality": round(cq, 3)}, inj_spans


def hard_scam(flags: list[str]) -> bool:
    f = set(flags)
    return bool(
        {"check_overpayment", "credential_request", "account_farming"} & f
        or ("off_platform_payment" in f)
        or ("unpaid_work" in f and ({"payment_unverified", "no_history", "off_platform_contact"} & f))
        or ("off_platform_contact" in f and "payment_unverified" in f)
    )


@node("risk")
async def risk_assessor(state, config, store):
    job = state["job"]
    client = None
    if job.get("client_id"):
        try:
            client = await gateway(state).call("risk", "marketplace", "get_client_history", {"client_id": job["client_id"]})
        except ToolFailed:
            client = None
    rscore, flags, signals, inj = rule_signals(job, client)
    cq = signals.get("client_quality", 0.5)
    base = RiskReport(score=round(rscore, 3), flags=flags, explanation="rule-based signals: " + (", ".join(flags) or "none"),
                      is_scam=hard_scam(flags) or rscore >= float(cfg("thresholds.scam_risk_score", 0.75)),
                      injection_detected=bool(inj), injection_spans=inj[:5], client_quality=cq, signals=signals)
    usage: dict = {}
    report = base
    if cfg("node_modes.risk", "hybrid") != "rules":
        res = await llm.structured(
            "risk", "risk", RiskReport,
            {"job": wrap_untrusted("job_post", f"{job.get('title')}\n\n{job.get('description', '')}"),
             "client": {k: client.get(k) for k in ("payment_verified", "total_spent", "rating", "reviews_count", "hire_rate",
                                                   "member_since", "country")} if client else "unknown",
             "signals": signals}, heuristic=lambda: base)
        usage = res.usage
        lr = res.value
        if res.fallback_used != "heuristic" and lr is not base:
            score = max(base.score, 0.5 * base.score + 0.5 * lr.score)
            report = RiskReport(
                score=round(min(1.0, score), 3), flags=list(dict.fromkeys(base.flags + [f for f in lr.flags if len(f) < 40]))[:12],
                explanation=lr.explanation[:500], is_scam=base.is_scam or (lr.is_scam and score >= 0.5),
                injection_detected=base.injection_detected or lr.injection_detected, injection_spans=base.injection_spans,
                client_quality=cq, signals=signals)
    return {"risk": report.model_dump(), "usage": usage,
            "_summary": f"risk {report.score:.2f}{' SCAM' if report.is_scam else ''}; flags: {', '.join(report.flags[:4]) or 'none'}"}
