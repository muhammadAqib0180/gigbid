"""Critic: grounding, personalisation, length, screening answers. Sends a draft back at most
`budgets.max_revisions` (2) times; rule checks are deterministic, the LLM adds judgement (hybrid)."""

from __future__ import annotations

import json
import re

from agent import llm
from agent.handoffs import Critique, JobSpec, ProposalDraft
from agent.nodes.common import last, node
from agent.settings import cfg

STOP = {"need", "needed", "looking", "expert", "developer", "project", "freelancer", "with", "for", "and", "the", "our", "help", "your"}


def rule_checks(draft: ProposalDraft, spec: JobSpec) -> tuple[list[str], dict[str, float]]:
    t = cfg("thresholds.critic", {}) or {}
    text = draft.cover_letter
    words = len(text.split())
    problems: list[str] = []
    first = " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:2]).lower()
    generic = [g for g in t.get("generic_openings", []) if g in text.lower()[:220]]
    if generic:
        problems.append(f"generic opening ('{generic[0]}'): open with this client's problem")
    terms = {w for w in re.findall(r"[a-z][a-z0-9.+#-]{3,}", spec.title.lower()) if w not in STOP} | {s.lower() for s in spec.required_skills}
    hits = sum(1 for w in terms if w in text.lower())
    personal = min(1.0, hits / max(3, len(terms) * 0.6)) if terms else 0.5
    if not any(w in first for w in terms) and terms:
        problems.append("first two sentences do not mention anything specific to this job")
    if words < int(t.get("min_words", 90)):
        problems.append(f"too short ({words} words; aim for {t.get('min_words', 90)}+)")
    if words > int(t.get("max_words", 320)):
        problems.append(f"too long ({words} words; cut to {t.get('max_words', 320)})")
    unsupported = [c for c in draft.claims if c.label == "unsupported"]
    if len(unsupported) > int(t.get("max_unsupported_claims", 0)):
        problems.append(f"{len(unsupported)} claim(s) still unsupported: remove or back with evidence")
    if spec.screening_questions and len(draft.screening_answers) < min(len(spec.screening_questions), 3):
        problems.append("answer every screening question")
    if not text.rstrip().split("\n")[-1].strip().endswith("?") and "?" not in text[-400:]:
        problems.append("end with one concrete question for the client")
    exp = [c for c in draft.claims if c.label != "not_a_claim"]
    grounding = (sum(c.label == "supported" for c in exp) + 0.5 * sum(c.label == "partly_supported" for c in exp)) / len(exp) if exp else 0.5
    length = 1.0 if int(t.get("min_words", 90)) <= words <= int(t.get("max_words", 320)) else 0.5
    return problems, {"grounding": round(grounding, 3), "personalisation": round(personal, 3), "length": length}


@node("critic")
async def critic(state, config, store):
    d = ProposalDraft.model_validate(last(state, "drafts"))
    spec = JobSpec.model_validate(state["job_spec"])
    problems, scores = rule_checks(d, spec)
    revision = int(state.get("revision") or 0)
    usage: dict = {}
    if cfg("node_modes.critic", "hybrid") != "rules":
        t = cfg("thresholds.critic", {}) or {}
        base = Critique(verdict="revise" if problems else "pass", reasons=problems, scores=scores, revision=revision)
        res = await llm.structured("critic", "critic", Critique, {
            "min_words": t.get("min_words", 90), "max_words": t.get("max_words", 320), "job_title": spec.title,
            "requirements": json.dumps([r.text for r in spec.requirements][:8]), "version": d.version, "draft": d.cover_letter,
            "claims": json.dumps([{"text": c.text[:160], "label": c.label} for c in d.claims if c.label != "not_a_claim"])[:3000],
            "rule_checks": json.dumps(problems)}, heuristic=lambda: base)
        usage = res.usage
        llm_c: Critique = res.value
        if llm_c is not base:
            problems = list(dict.fromkeys(problems + [r for r in llm_c.reasons if llm_c.verdict == "revise"]))[:6]
            scores = {**scores, **{k: v for k, v in llm_c.scores.items() if isinstance(v, (int, float))}}
    verdict = "revise" if problems and revision < int(cfg("budgets.max_revisions", 2)) else "pass"
    c = Critique(verdict=verdict, reasons=problems, scores=scores, revision=revision)
    return {"critiques": [c.model_dump()], "usage": usage,
            "_summary": f"{verdict}" + (f": {problems[0]}" if problems else "") + f" (revision {revision})"}
