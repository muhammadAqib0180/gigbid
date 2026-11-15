"""Claim verification (B3, required).

1. Split the draft into atomic claims (sentences; long compound sentences split on '; ' and ' and I ').
2. Keep only experience claims (first-person past work, numbers, named tools/clients). Plans, questions
   and pleasantries are `not_a_claim`.
3. Ground each claim against the evidence the Writer was given (+ the retriever's top items):
   support = 0.6 * semantic similarity (embedding cosine to best evidence chunk)
           + 0.4 * key-term coverage (tools, numbers, industries must appear in that evidence)
   Any number in the claim must appear verbatim in the evidence, else the claim is at most partly supported.
4. supported >= verification.supported_threshold; partly >= partly_threshold; else unsupported.
5. Unsupported claims are removed (or the sentence is softened by dropping the unsupported clause) BEFORE
   the Critic sees the draft. Rates before/after are recorded in VerificationReport.

Mode `llm` (config verification.mode) asks the verifier model for the label instead of the score blend.
"""

from __future__ import annotations

import re

import numpy as np

from agent.handoffs import Claim, EvidenceItem, VerificationReport
from agent.settings import cfg
from agent.skills import extract_skills
from rag.index.models import embed_queries

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_FIRST_PERSON_WORK = re.compile(
    r"\b(I|I've|I have|I had|my|we|our team)\b[^.]{0,80}\b(built|shipped|delivered|designed|developed|created|led|"
    r"implemented|migrated|automated|trained|deployed|reduced|increased|improved|cut|raised|launched|worked|"
    r"rebuilt|wrote|set up|analysed|analyzed|modelled|integrated|helped|managed|ran|have done|did)\b", re.I)
_EXPERIENCE = re.compile(r"\b(\d+\+? years|years of experience|experienced in|expert in|specialis(e|ed) in|certified|"
                         r"my experience (with|in)|I have (successfully )?(completed|done|worked on|delivered|handled)|"
                         r"proven track record|extensive experience|verified through my portfolio)\b", re.I)
_NUM = re.compile(r"\$?\d[\d,.]*\s?(%|ms|s|x|k|m|hours?|minutes?|weeks?|days?|fps)?", re.I)
_NOT_CLAIM = re.compile(r"^(could|would|can|do|does|what|how|when|happy to|let me know|best|thanks|cheers|looking forward)\b", re.I)


def split_claims(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for pi, para in enumerate(p for p in re.split(r"\n\s*\n", text) if p.strip()):
        for sent in _SENT.split(para.strip()):
            for part in re.split(r";\s+|\s+and I\s+", sent):
                part = part.strip()
                if len(part.split()) >= 3:
                    out.append((pi, part))
    return out


def is_experience_claim(sentence: str) -> bool:
    s = sentence.strip()
    if s.endswith("?") or _NOT_CLAIM.match(s):
        return False
    if re.match(r"^(For this job|I would|I will|I'd|My plan|First,|Then|Next,|I can|I propose|I'll)", s, re.I):
        return False
    first_person = re.search(r"\b(I|I've|my|we|our)\b", s)
    has_num = bool(re.search(r"\d", s))
    return bool(_FIRST_PERSON_WORK.search(s) or _EXPERIENCE.search(s)
                or (has_num and (first_person or re.search(r"\b(project|client)\b", s, re.I)))
                or (first_person and re.search(r"\b(fine-tuned|tuned|rose|grew|saved|processed|handled|served|reached)\b", s, re.I)))


def _key_terms(sentence: str) -> set[str]:
    terms = {s.lower() for s in extract_skills(sentence)}
    terms |= {m.group().strip().lower().rstrip(".") for m in _NUM.finditer(sentence) if re.search(r"\d", m.group())}
    return {t for t in terms if t}


def _numbers(sentence: str) -> set[str]:
    return {re.sub(r"[^\d.]", "", m.group()) for m in _NUM.finditer(sentence) if re.search(r"\d", m.group())} - {""}


def ground(claims: list[tuple[int, str]], evidence: list[EvidenceItem]) -> list[Claim]:
    sup_t = float(cfg("verification.supported_threshold", 0.55))
    part_t = float(cfg("verification.partly_threshold", 0.35))
    ev_texts = [e.snippet for e in evidence]
    ev_mat = embed_queries(ev_texts) if ev_texts else np.zeros((0, 384), dtype=np.float32)
    out: list[Claim] = []
    exp = [(pi, s) for pi, s in claims if is_experience_claim(s)]
    claim_mat = embed_queries([s for _, s in exp]) if exp else None
    j = 0
    for n, (pi, s) in enumerate(claims):
        cid = f"c{n + 1}"
        if not is_experience_claim(s):
            out.append(Claim(claim_id=cid, text=s, paragraph=pi, label="not_a_claim", support_score=1.0))
            continue
        vec = claim_mat[j]
        j += 1
        if not len(ev_texts):
            out.append(Claim(claim_id=cid, text=s, paragraph=pi, label="unsupported", note="no evidence available"))
            continue
        sims = ev_mat @ vec
        order = np.argsort(-sims)[:3]
        best = int(order[0])
        terms = _key_terms(s)
        best_cov, best_idx = 0.0, best
        for i in order:
            low = ev_texts[int(i)].lower()
            cov = (sum(1 for t in terms if t in low) / len(terms)) if terms else 1.0
            if cov > best_cov:
                best_cov, best_idx = cov, int(i)
        sem = float(sims[best_idx])
        score = 0.6 * max(0.0, (sem - 0.3) / 0.6) + 0.4 * best_cov
        nums = _numbers(s)
        ev_nums = _numbers(" ".join(ev_texts[int(i)] for i in order))
        missing_nums = sorted(x for x in nums if x not in ev_nums)
        label = "supported" if score >= sup_t else ("partly_supported" if score >= part_t else "unsupported")
        note = ""
        if missing_nums:
            note = f"numbers not in evidence: {missing_nums}"
            if label == "supported":
                label = "partly_supported"
            if len(missing_nums) == len(nums) and best_cov < 0.5:
                label = "unsupported"
        out.append(Claim(claim_id=cid, text=s, paragraph=pi, evidence_ids=[evidence[best_idx].evidence_id],
                         label=label, support_score=round(score, 3), note=note))
    return out


def repair(text: str, claims: list[Claim]) -> tuple[str, list[str], list[str]]:
    """Remove unsupported claims; strip unverifiable numbers from partly supported ones."""
    removed, softened = [], []
    new = text
    for c in claims:
        if c.label == "unsupported":
            new = new.replace(c.text, "")
            removed.append(c.text)
        elif c.label == "partly_supported" and c.note.startswith("numbers not in evidence"):
            soft = re.sub(r"\s*(by|to|from|of)?\s*\$?\d[\d,.]*\s?(%|ms|s|x|k|m|hours?|minutes?|weeks?|days?|fps)?", " ", c.text)
            soft = re.sub(r"\s{2,}", " ", soft).strip()
            if soft and soft != c.text and len(soft.split()) >= 4:
                new = new.replace(c.text, soft)
                softened.append(c.text)
    new = re.sub(r"[ \t]{2,}", " ", new)
    new = re.sub(r"\s+([.,;])", r"\1", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip()
    return new, removed, softened


def verify_claims(draft: str, evidence: list[dict] | list[EvidenceItem], version: int = 1) -> tuple[str, VerificationReport]:
    ev = [e if isinstance(e, EvidenceItem) else EvidenceItem.model_validate(e) for e in evidence]
    claims = ground(split_claims(draft), ev)
    exp = [c for c in claims if c.label != "not_a_claim"]
    unsupported_before = sum(1 for c in exp if c.label == "unsupported")
    fixed, removed, softened = repair(draft, claims)
    after = ground(split_claims(fixed), ev)
    exp_after = [c for c in after if c.label != "not_a_claim"]
    report = VerificationReport(version=version, claims=after, total_claims=len(exp), unsupported_before=unsupported_before,
                                unsupported_after=sum(1 for c in exp_after if c.label == "unsupported"),
                                removed=removed, softened=softened)
    return fixed, report
