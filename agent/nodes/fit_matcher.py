"""Fit Matcher: map every requirement to portfolio evidence (Portfolio MCP `match_requirements`, which runs
the measured RAG pipeline) and produce a fit score with reasons."""

from __future__ import annotations

from agent.handoffs import EvidenceItem, FitReport, RequirementMatch
from agent.nodes.common import gateway, node
from agent.profile import merged_profile
from agent.requirements import extract_requirements
from agent.settings import cfg


def score_fit(job: dict, reqs: list, result: dict, profile: dict) -> FitReport:
    thr = float(cfg("thresholds.evidence_cover_score", 0.30))
    weak = set(result.get("weak_requirements") or [])
    per = {p["requirement_id"]: p["items"] for p in result.get("per_requirement", [])}
    matches: list[RequirementMatch] = []
    num = den = 0.0
    matched_sk: list[str] = []
    missing_sk: list[str] = []
    for r in reqs:
        items = per.get(r.id, [])
        best = max((float(i.get("score", 0)) for i in items), default=0.0)
        text = " ".join((i.get("snippet") or "") + " " + " ".join(i.get("skills") or []) for i in items).lower()
        skill_hit = bool(r.skills) and all(s.lower() in text for s in r.skills)
        covered = r.id not in weak and (best >= thr or skill_hit)
        w = 1.0 if r.must_have else 0.5
        den += w
        num += w * (1.0 if covered else (0.4 if best >= thr * 0.6 and r.id not in weak else 0.0))
        for s in r.skills:
            (matched_sk if covered else missing_sk).append(s)
        matches.append(RequirementMatch(requirement_id=r.id, requirement=r.text, evidence_ids=[i["evidence_id"] for i in items[:3]],
                                        item_ids=[i["item_id"] for i in items[:3]], best_score=round(best, 3), covered=covered))
    coverage = num / den if den else 0.0
    cats = set(profile.get("categories") or [])
    domain = 1.0 if (not cats or job.get("category") in cats) else (0.85 if matched_sk else 0.6)
    score = max(0.0, min(1.0, coverage * domain))
    reasons = [f"{sum(m.covered for m in matches)}/{len(matches)} requirements proven by portfolio evidence"]
    if domain < 1.0:
        reasons.append(f"job category '{job.get('category')}' is outside the profile's focus ({', '.join(cats)})")
    if weak:
        reasons.append(f"no evidence for: {', '.join(m.requirement[:50] for m in matches if m.requirement_id in weak)[:200]}")
    return FitReport(score=round(score, 3), matched_skills=list(dict.fromkeys(matched_sk)), missing_skills=list(dict.fromkeys(missing_sk)),
                     evidence_ids=[i["evidence_id"] for i in result.get("items", [])], matches=matches, reasons=reasons,
                     retrieval_variant=result.get("variant", ""))


@node("matcher")
async def fit_matcher(state, config, store):
    job = state["job"]
    reqs = extract_requirements(job)
    profile = merged_profile(state.get("persona_id", "ai_ml_engineer"), state.get("user_profile"))
    result = await gateway(state).call("matcher", "portfolio", "match_requirements", {
        "job_title": job.get("title", "")[:300], "job_text": (job.get("description") or "")[:8000],
        "requirements": [{"id": r.id, "text": r.text[:300], "skills": r.skills[:10], "must_have": r.must_have} for r in reqs[:12]],
        "k": int(cfg("rag.k", 8))})
    fit = score_fit(job, reqs, result, profile)
    evidence = [EvidenceItem.model_validate(i).model_dump() for i in result.get("items", [])]
    for p in result.get("per_requirement", []):
        evidence += [EvidenceItem.model_validate(i).model_dump() for i in p["items"]]
    return {"fit": fit.model_dump(), "evidence": evidence,
            "_summary": f"fit {fit.score:.2f} via {fit.retrieval_variant}; {fit.reasons[0]}"}
