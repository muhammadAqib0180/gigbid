"""Deterministic requirement extraction from a job post.

Used by the Fit Matcher (which runs in parallel with the Job Analyst, so it cannot wait for the LLM
JobSpec) and by RAG variant V1 (requirement decomposition). The Analyst's LLM JobSpec refines these
for the Writer later.
"""

from __future__ import annotations

import re

from agent.handoffs import Requirement
from agent.safety import neutralize, scan_injection
from agent.skills import BROAD, canon, extract_skills

_REQ_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.{8,200})$", re.MULTILINE)
# a "character" inside a sentence: anything but a terminator, or a '.'/'!'/'?' glued to the next word
# ("Next.js", "4.7") - so tool names and decimals do not end a sentence.
_C = r"(?:[^.!?\n]|[.!?](?=\w))"
_NEED_SENT = re.compile(
    rf"({_C}{{0,160}}?\b(need|must|require|required|looking for|should|experience (with|in)|familiar with|"
    rf"ability to|we want|responsible for|deliver)\b{_C}{{4,200}})(?:[.!?](?=\s|$)|\n|$)", re.IGNORECASE)


def _clean(text: str) -> str:
    text = neutralize(text)
    # drop sentences that look like injected instructions so they never become "requirements"
    bad = {f.span[:60] for f in scan_injection(text)}
    if bad:
        sents = re.split(r"(?<=[.!?\n])\s+", text)
        text = " ".join(s for s in sents if not any(b[:30].lower() in s.lower() for b in bad))
    return text


def extract_requirements(job: dict, max_reqs: int = 8) -> list[Requirement]:
    title = job.get("title", "")
    desc = _clean(job.get("description", ""))
    reqs: list[Requirement] = []
    seen: set[str] = set()

    def add(text: str, kind: str, skills: list[str], must: bool = True) -> None:
        key = re.sub(r"\W+", " ", text.lower()).strip()[:80]
        if not key or key in seen or len(reqs) >= max_reqs:
            return
        seen.add(key)
        reqs.append(Requirement(id=f"r{len(reqs) + 1}", text=text.strip()[:220], kind=kind, skills=skills, must_have=must))

    for m in _REQ_LINE.finditer(desc):
        line = m.group(1)
        add(line, "skill" if extract_skills(line) else "deliverable", extract_skills(line))
    for m in _NEED_SENT.finditer(desc):
        sent = m.group(1)
        if len(sent.split()) >= 4:
            add(sent, "skill" if extract_skills(sent) else "deliverable", extract_skills(sent))
    listed = [canon(s) for s in job.get("skills", []) if s]
    mentioned = extract_skills(title + "\n" + desc)
    specific = [s for s in dict.fromkeys(listed + mentioned) if s not in BROAD]
    covered = {s for r in reqs for s in r.skills}
    for s in specific:
        if s not in covered:
            add(f"Experience with {s}", "skill", [s], must=s in listed[:4] or s in mentioned[:3])
    if not reqs:
        add(title or desc[:160], "deliverable", extract_skills(title))
    return reqs


def screening_questions(job: dict) -> list[str]:
    desc = neutralize(job.get("description", ""))
    qs = [q.strip() for q in re.findall(r"([^.!?\n]{10,200}\?)", desc)]
    explicit = job.get("screening_questions") or []
    return list(dict.fromkeys(explicit + [q for q in qs if not scan_injection(q)]))[:5]
