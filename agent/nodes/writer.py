"""Proposal Writer: cover letter + screening answers, every claim tied to evidence ids.

The deterministic `heuristic_draft` (used by profile `test`, and as the last-resort fallback) composes a
grounded proposal by quoting results that literally appear in the evidence snippets.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from agent import llm
from agent.handoffs import Critique, EvidenceItem, JobSpec, PriceQuote, ProposalDraft, ScreeningAnswer
from agent.memory.store import outcome_insights, style_rules
from agent.nodes.common import last, node
from agent.safety import wrap_untrusted
from agent.settings import cfg


class WriterOut(BaseModel):
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_INDUSTRY = re.compile(r"Client:\*\*\s+an?\s+([\w\- /&]+?)\s+company", re.I)
_SKIP = ("date", "year", "id:", "skills", "client review (", "type:", "project:", "synthetic")


def _sentences(text: str) -> list[str]:
    text = re.sub(r"^---.*?---", "", text, flags=re.S)
    text = re.sub(r"^#+\s.*$", "", text, flags=re.M)
    text = re.sub(r"\*\*[^*]+:\*\*[^\n]*", "", text)
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip(" -*\t>")
        if line:
            out += [p.strip().rstrip(".") for p in _SENT_SPLIT.split(line)]
    return [s for s in out if len(s.split()) >= 4 and not s.lower().startswith(_SKIP)]


def _results_from(snippet: str) -> list[str]:
    """Result sentences (with numbers), preferring the case study's '## Results' section over its problem statement."""
    m = re.search(r"##\s*Results\s*\n(.*?)(\n##|\Z)", snippet, re.S)
    results = [s for s in _sentences(m.group(1)) if re.search(r"\d", s)] if m else []
    if m:
        snippet = snippet.replace(m.group(1), "")
    snippet = re.sub(r"##\s*The problem\s*\n.*?(\n##|\Z)", r"\1", snippet, flags=re.S)
    rest = [s for s in _sentences(snippet) if re.search(r"\d", s)]
    return [s for s in results + rest if 4 <= len(s.split()) <= 32]


def _project_name(e: EvidenceItem) -> str:
    if e.type == "case_study" and e.title:
        return e.title
    if e.project:
        return e.project.split(",")[0].replace("-", " ")
    return e.title or "a past project"


def _industry(e: EvidenceItem) -> str | None:
    m = _INDUSTRY.search(e.snippet)
    return m.group(1) if m else None


def _lc(s: str) -> str:
    return s[0].lower() + s[1:] if s and not s[:2].isupper() else s


def _req_short(text: str) -> str:
    t = re.sub(r"^(experience (with|in)|(we are |we're |i am )?looking (for|to)( someone| a [a-z]+)?( with| who can| to)?|we need( to)?|we want to|"
               r"need( to)?|must have|hands-on|ability to)\s+", "", text.strip(), flags=re.I).rstrip(".")
    if len(t) > 90:
        t = t[:90].rsplit(" ", 1)[0]
    return t


def select_evidence(evidence: list[dict], k: int = 6) -> list[EvidenceItem]:
    items = [EvidenceItem.model_validate(e) for e in evidence]
    pri = {"case_study": 0, "review": 1, "readme": 2, "code": 3, "proposal": 4, "cv": 5}
    items.sort(key=lambda e: (-e.score, pri.get(e.type, 6)))
    seen_proj: set[str] = set()
    out: list[EvidenceItem] = []
    for e in items:
        key = e.project or e.item_id
        if key in seen_proj:
            continue
        seen_proj.add(key)
        out.append(e)
        if len(out) >= k:
            break
    return out


def heuristic_draft(job: dict, spec: JobSpec, ev: list[EvidenceItem], price: PriceQuote | None, strategy: str,
                    weak: list[str], disclosures: list[str]) -> WriterOut:
    title = job.get("title", "your project").strip().rstrip(".")
    reqs = [r for r in spec.requirements if r.text not in weak] or spec.requirements
    need = _req_short(reqs[0].text) if reqs else (", ".join(spec.required_skills[:3]) or title)
    used: list[str] = []
    with_res = [(e, _results_from(e.snippet)) for e in ev if e.type in {"case_study", "review", "readme"}]
    with_res = [(e, r) for e, r in with_res if r]
    with_res.sort(key=lambda t: ({"case_study": 0, "review": 1, "readme": 2}.get(t[0].type, 3)))
    paras: list[str] = []
    lead = with_res[0] if with_res else None
    if lead:
        e, res = lead
        ind = _industry(e)
        where = f"for {'an' if ind and ind[0] in 'aeiou' else 'a'} {ind} client" if ind else "in a recent project"
        if strategy == "question_first":
            paras.append(f"Before anything else: what would a good result for \"{need}\" look like for you in the first two weeks? "
                         f"I ask because on my {_project_name(e).lower()} work {where}, {_lc(res[0])}.")
        else:
            paras.append(f"For your \"{title}\" project, the closest thing I have shipped is my "
                         f"{_project_name(e).lower()} work {where}: {_lc(res[0])}.")
        used.append(e.evidence_id)
    else:
        paras.append(f"For your \"{title}\" project I would like to understand the details before promising anything; "
                     f"the core of it seems to be {_lc(need)}.")
    more = []
    for e, res in with_res[1:3]:
        if (e.project or e.item_id) == (lead[0].project if lead else None):
            pick = res[1] if len(res) > 1 else None
        else:
            pick = res[0]
        if pick:
            more.append(f"On my {_project_name(e).lower()} work, {_lc(pick)}.")
            used.append(e.evidence_id)
    if more:
        paras.append(" ".join(more))
    steps = []
    for r in reqs[1:3]:
        s = _req_short(r.text)
        steps.append(f"set up {s}" if (r.text.lower().startswith("experience with") and len(s.split()) <= 4) else f"tackle \"{s}\"")
    steps = steps or ["deliver the core piece"]
    paras.append("How I would run it: agree the success metric and get access in a first short call, then "
                 + ", then ".join(steps) + ", with a working demo every week so you can steer early.")
    if weak:
        paras.append(f"To be transparent: {_lc(_req_short(weak[0]))} is outside my documented work, so I would scope that part with you first.")
    close = []
    if price:
        close.append(f"My proposed price is ${price.amount:,.0f}{'/hour' if price.unit == 'hourly' else ' fixed'}.")
    close.append("Which part of this matters most to you right now?")
    paras.append(" ".join(close))
    paras += list(disclosures)
    answers = []
    for q in spec.screening_questions[:3]:
        if with_res:
            e, res = with_res[0]
            answers.append(ScreeningAnswer(question=q, answer=f"In my {_project_name(e).lower()} work, {_lc(res[0])}; I would apply the same approach here.",
                                           evidence_ids=[e.evidence_id]))
        else:
            answers.append(ScreeningAnswer(question=q, answer="I would confirm the details with you first and follow the plan above."))
    return WriterOut(cover_letter="\n\n".join(paras), screening_answers=answers, evidence_ids=list(dict.fromkeys(used)))


async def project_case_studies(state: dict, limit: int = 3) -> list[dict]:
    """Retrieval often surfaces a project through its code, README or a past proposal. Pull the full case
    study of the top-matched projects (Portfolio MCP `get_case_study`) so claims can cite concrete results."""
    from agent.mcp_client import ToolFailed
    from agent.nodes.common import gateway

    have = {e.get("project") for e in state.get("evidence") or [] if e.get("type") == "case_study"}
    ranked: list[str] = []
    for e in sorted(state.get("evidence") or [], key=lambda x: -float(x.get("score") or 0)):
        for p in (e.get("project") or "").split(","):
            if p and p not in ranked and p not in have:
                ranked.append(p)
    out: list[dict] = []
    gw = gateway(state)
    for slug in ranked[:limit]:
        try:
            cs = await gw.call("writer", "portfolio", "get_case_study", {"id": f"case-{slug}"})
        except ToolFailed:
            continue
        body = cs.get("text", "")
        out.append(EvidenceItem(evidence_id=f"{state.get('persona_id')}:case-{slug}#full", item_id=cs.get("item_id", f"case-{slug}"),
                                type="case_study", title=cs.get("title", slug), source=cs.get("source", ""), date=cs.get("date"),
                                project=slug, snippet=body[:1400], score=0.5).model_dump())
    return out


def strategy_for(state: dict) -> str:
    """X2 A/B: deterministic assignment by job id when the experiment is on, otherwise config default."""
    strategies = cfg("experiments.strategies", ["evidence_first"]) or ["evidence_first"]
    fixed = (state.get("user_profile") or {}).get("proposal_strategy") or cfg("experiments.proposal_strategy", "evidence_first")
    if fixed == "ab":
        import hashlib

        return strategies[int(hashlib.md5(state["job"]["job_id"].encode()).hexdigest(), 16) % len(strategies)]
    return fixed


@node("writer")
async def writer(state, config, store):
    job = state["job"]
    spec = JobSpec.model_validate(state["job_spec"])
    price = PriceQuote.model_validate(state["price"]) if state.get("price") else None
    extra_ev = await project_case_studies(state)
    ev = select_evidence((state.get("evidence") or []) + extra_ev)
    fit = state.get("fit") or {}
    weak = [m["requirement"] for m in fit.get("matches", []) if not m.get("covered")]
    crit = last(state, "critiques")
    strategy = strategy_for(state)
    disclosures = cfg("bidding_rules.proposal.required_disclosures", []) or []
    user_id = state.get("user_id", "local")
    rules = await style_rules(store, user_id)
    insights = await outcome_insights(store, user_id, job.get("category"))
    ev_text = "\n".join(f"[{e.evidence_id}] ({e.type}, {e.title}, outcome={e.outcome or '-'}): {e.snippet[:500]}" for e in ev)
    res = await llm.structured(
        "writer", "writer", WriterOut,
        {"strategy": strategy, "style_rules": json.dumps(rules) if rules else "none yet",
         "outcome_insights": " ".join(insights) or "none yet", "job_spec": spec.model_dump_json(exclude={"requirements"})[:1500],
         "job": wrap_untrusted("job_post", f"{job.get('title')}\n\n{(job.get('description') or '')[:2500]}"),
         "evidence": ev_text or "NO EVIDENCE", "weak_requirements": "; ".join(weak) or "none",
         "price": f"{price.amount} {price.unit}" if price else "n/a", "screening_questions": json.dumps(spec.screening_questions),
         "critique": "; ".join(Critique.model_validate(crit).reasons) if crit else "none (first draft)",
         "disclosures": json.dumps(disclosures)},
        heuristic=lambda: heuristic_draft(job, spec, ev, price, strategy, weak, disclosures))
    out: WriterOut = res.value
    text = out.cover_letter.strip()
    for d in disclosures:  # platform-required lines are enforced deterministically, not left to the model
        if d.lower() not in text.lower():
            text += "\n\n" + d
    version = max((int(x.get("version", 0)) for x in state.get("drafts") or []), default=0) + 1
    valid_ids = {e.evidence_id for e in ev} | {e["evidence_id"] for e in state.get("evidence") or []}
    draft = ProposalDraft(job_id=job["job_id"], version=version, cover_letter=text, screening_answers=out.screening_answers,
                          evidence_ids=[i for i in out.evidence_ids if i in valid_ids] or [e.evidence_id for e in ev[:3]],
                          strategy=strategy, status="drafted")
    return {"drafts": [draft.model_dump()], "evidence": extra_ev, "revision": (state.get("revision") or 0) + (1 if crit else 0), "usage": res.usage,
            "_summary": f"draft v{version} ({draft.word_count} words, strategy {strategy}{', fallback ' + res.fallback_used if res.fallback_used else ''})"}
