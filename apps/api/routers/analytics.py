"""Analytics: reply and hire rate by category and strategy, Connects spent vs outcomes, cost and latency per
proposal, top rejection reasons, decision mix."""

from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.users import current_user
from apps.api.db import ApprovalLog, JobRecord, ProposalCard, Run, User, get_session
from apps.api.schemas import AnalyticsOut

router = APIRouter(prefix="/api", tags=["analytics"])
REPLIED = {"replied", "interview", "hired"}


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))], 3)


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> AnalyticsOut:
    cards = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user.id))).scalars().all()
    sent = [c for c in cards if c.proposal_id]
    by_cat: dict[str, list] = defaultdict(list)
    by_strat: dict[str, list] = defaultdict(list)
    for c in sent:
        by_cat[c.category or "other"].append(c)
        by_strat[c.strategy].append(c)

    def agg(groups: dict[str, list]) -> list[dict]:
        return [{"key": k, "sent": len(v), "replied": sum(c.stage in REPLIED for c in v), "hired": sum(c.stage == "hired" for c in v),
                 "reply_rate": round(sum(c.stage in REPLIED for c in v) / len(v), 3) if v else 0.0,
                 "hire_rate": round(sum(c.stage == "hired" for c in v) / len(v), 3) if v else 0.0} for k, v in sorted(groups.items())]

    spent = sum(c.connects_spent for c in sent)
    replies = sum(c.stage in REPLIED for c in sent)
    runs = (await s.execute(select(Run).where(Run.user_id == user.id))).scalars().all()
    bid_runs = [r for r in runs if r.kind == "bid" and r.status not in {"running", "error"}]
    prop_cost = [c.cost_usd for c in sent]
    prop_lat = [c.latency_s for c in sent]
    rejects = (await s.execute(select(ApprovalLog).where(ApprovalLog.user_id == user.id, ApprovalLog.action == "reject"))).scalars().all()
    reasons = Counter((r.reason or "no reason").strip().lower()[:80] for r in rejects)
    jobs = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id))).scalars().all()
    stages = Counter(c.stage for c in cards)
    return AnalyticsOut(
        by_category=agg(by_cat), by_strategy=agg(by_strat),
        connects={"spent": spent, "proposals_sent": len(sent), "replies": replies,
                  "connects_per_reply": round(spent / replies, 2) if replies else None},
        cost_latency={"runs": len(bid_runs), "p50_latency_s_per_job": _pct([r.latency_s for r in bid_runs], 0.5),
                      "p95_latency_s_per_job": _pct([r.latency_s for r in bid_runs], 0.95),
                      "usd_per_job_p50": _pct([r.cost_usd for r in bid_runs], 0.5),
                      "p95_latency_s_per_proposal": _pct(prop_lat, 0.95), "usd_per_proposal_mean": round(sum(prop_cost) / len(prop_cost), 6) if prop_cost else 0.0,
                      "tokens_total": sum(r.tokens for r in runs)},
        rejection_reasons=[{"reason": k, "count": v} for k, v in reasons.most_common(8)],
        funnel={st: stages.get(st, 0) for st in ("drafted", "submitted", "viewed", "replied", "interview", "hired", "lost")},
        decisions=dict(Counter(j.action or j.status for j in jobs)),
    )
