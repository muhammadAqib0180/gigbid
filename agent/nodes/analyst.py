"""Job Analyst: structured JobSpec from a job post (deterministic pre-extraction + LLM refinement)."""

from __future__ import annotations

import json

from agent import llm
from agent.handoffs import JobSpec
from agent.nodes.common import node
from agent.requirements import extract_requirements, screening_questions
from agent.safety import wrap_untrusted
from agent.settings import cfg
from agent.skills import BROAD, canon, extract_skills


def heuristic_spec(job: dict) -> JobSpec:
    reqs = extract_requirements(job)
    listed = [canon(s) for s in job.get("skills", []) if s]
    mentioned = extract_skills(job.get("title", "") + " " + job.get("description", ""))
    skills = list(dict.fromkeys(listed + mentioned))
    desc = job.get("description", "")
    hidden = []
    low = desc.lower()
    if any(w in low for w in ("health", "patient", "medical", "clinic")):
        hidden.append("handles sensitive health data: privacy and access control matter")
    if any(w in low for w in ("maintain", "handover", "document", "team will")):
        hidden.append("expects documentation / handover so their team can maintain it")
    if any(w in low for w in ("asap", "urgent", "today", "tomorrow")):
        hidden.append("tight deadline: needs fast, reliable delivery")
    if not hidden:
        hidden.append("wants evidence the freelancer has solved this exact problem before")
    return JobSpec(
        job_id=job["job_id"], title=job.get("title", ""), summary=desc[:240], category=job.get("category") or "",
        deliverables=[r.text for r in reqs if r.kind == "deliverable"][:5],
        required_skills=[s for s in skills if s not in BROAD][:10], nice_to_have_skills=[s for s in skills if s in BROAD][:5],
        requirements=reqs, budget_min=job.get("budget") if not job.get("is_hourly") else job.get("hourly_low"),
        budget_max=job.get("budget") if not job.get("is_hourly") else job.get("hourly_high"),
        is_hourly=bool(job.get("is_hourly")), experience_level=job.get("experience_level"),
        screening_questions=screening_questions(job), hidden_needs=hidden, connects_cost=job.get("connects_cost"),
    )


@node("analyst")
async def analyst(state, config, store):
    job = state["job"]
    base = heuristic_spec(job)
    if cfg("node_modes.analyst", "llm") == "rules":
        spec, usage = base, {}
    else:
        res = await llm.structured(
            "analyst", "analyst", JobSpec,
            {"job": wrap_untrusted("job_post", f"{job.get('title')}\n\n{job.get('description', '')}"),
             "skills": ", ".join(job.get("skills", [])), "job_id": job["job_id"],
             "budget": f"{'hourly' if job.get('is_hourly') else 'fixed'} {job.get('budget') or ''} {job.get('hourly_low') or ''}-{job.get('hourly_high') or ''}",
             "pre_requirements": json.dumps([r.model_dump() for r in base.requirements])[:2000]},
            heuristic=lambda: base)
        spec, usage = res.value, res.usage
        # never let the LLM drop the deterministic requirements or invent a budget
        spec.job_id = job["job_id"]
        spec.budget_min, spec.budget_max, spec.is_hourly = base.budget_min, base.budget_max, base.is_hourly
        spec.connects_cost = base.connects_cost
        if not spec.requirements:
            spec.requirements = base.requirements
        spec.screening_questions = list(dict.fromkeys(base.screening_questions + spec.screening_questions))[:5]
    return {"job_spec": spec.model_dump(), "usage": usage,
            "_summary": f"{len(spec.requirements)} requirements, {len(spec.screening_questions)} screening questions"}
