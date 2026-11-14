"""Compliance Guard: enforces the policy pack + config bidding_rules on proposals and messages.
Removes contact details, off-platform asks, guarantees and injected residue; adds required disclosures;
blocks (with a reason shown in the UI) when something cannot be fixed automatically."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from pydantic import BaseModel, Field

from agent import llm
from agent.handoffs import ComplianceVerdict, ProposalDraft, Redaction
from agent.nodes.common import last, node
from agent.safety import contact_detail_spans
from agent.settings import cfg, data_dir

INJECTION_RESIDUE = [r"\bI am an AI( bot)?\b", r"\bBANANA\b", r"\bsystem prompt\b", r"\bdeveloper mode\b", r"\bas an AI language model\b"]


class Violation(BaseModel):
    kind: str
    span: str
    fix: str = ""


class LLMViolations(BaseModel):
    violations: list[Violation] = Field(default_factory=list)


@lru_cache(maxsize=1)
def policy_text() -> str:
    parts = [p.read_text(encoding="utf-8") for p in sorted((data_dir() / "policy_pack").glob("*.md"))]
    return "\n\n".join(parts)[:6000]


def _drop_sentence(text: str, span: str) -> str:
    sents = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in sents if span.lower() not in s.lower())


def check_text(text: str, require_disclosures: bool = True) -> tuple[str, list[Redaction], list[str]]:
    """Deterministic pass: returns cleaned text, redactions, and unresolved blocking reasons."""
    rules = cfg("bidding_rules", {}) or {}
    red: list[Redaction] = []
    out = text
    for kind, span in contact_detail_spans(out):
        out = out.replace(span, "")
        red.append(Redaction(kind=kind, original=span, replacement=""))
    paras = []
    for para in out.split("\n\n"):
        for term in rules.get("off_platform_terms", []):
            if re.search(rf"\b{re.escape(term)}\b", para, re.I):
                before = para
                para = _drop_sentence(para, term)
                if para != before:
                    red.append(Redaction(kind="off_platform", original=term, replacement="[sentence removed]"))
        for phrase in rules.get("guarantee_phrases", []):
            if re.search(re.escape(phrase), para, re.I):
                para = _drop_sentence(para, phrase)
                red.append(Redaction(kind="guarantee", original=phrase, replacement="[sentence removed]"))
        for rx in INJECTION_RESIDUE:
            m = re.search(rx, para, re.I)
            if m:
                para = _drop_sentence(para, m.group())
                red.append(Redaction(kind="injection_residue", original=m.group(), replacement="[sentence removed]"))
        if para.strip():
            paras.append(para.strip())
    out = "\n\n".join(paras)
    for d in ((rules.get("proposal") or {}).get("required_disclosures", []) or []) if require_disclosures else []:
        if d.lower() not in out.lower():
            out = out + "\n\n" + d
            red.append(Redaction(kind="disclosure_added", original="", replacement=d))
    blocked: list[str] = []
    max_words = int((rules.get("proposal") or {}).get("max_words", 320))
    if len(out.split()) > max_words + 40:
        blocked.append(f"proposal exceeds platform limit of {max_words} words")
    if contact_detail_spans(out):
        blocked.append("contact details remain after redaction")
    if len(out.split()) < (25 if require_disclosures else 5):
        blocked.append("too little text left after removing policy violations")
    return out, red, blocked


async def run_compliance(text: str, node_name: str = "compliance", proposal: bool = True) -> tuple[ComplianceVerdict, dict]:
    cleaned, red, blocked = check_text(text, proposal)
    usage: dict = {}
    if cfg("node_modes.compliance", "hybrid") != "rules":
        res = await llm.structured(node_name, "compliance", LLMViolations,
                                   {"policy": policy_text(), "text": cleaned,
                                    "rule_findings": json.dumps([r.model_dump() for r in red])[:1500]},
                                   heuristic=lambda: LLMViolations())
        usage = res.usage
        for v in res.value.violations:
            if v.span and v.span in cleaned and v.kind.lower() not in {"none", "ok"}:
                cleaned = _drop_sentence(cleaned, v.span) if len(v.span) < 200 else cleaned
                red.append(Redaction(kind=f"llm:{v.kind}"[:40], original=v.span[:200], replacement="[sentence removed]"))
        cleaned2, _, blocked2 = check_text(cleaned, proposal)
        cleaned, blocked = cleaned2, blocked2
    v = ComplianceVerdict(allowed=not blocked, blocked_reasons=blocked, redactions=red, cleaned_text=cleaned,
                          policy_version=str(cfg("bidding_rules.policy_version", "")))
    return v, usage


@node("compliance")
async def compliance(state, config, store):
    d = ProposalDraft.model_validate(last(state, "drafts"))
    verdict, usage = await run_compliance(d.cover_letter)
    out = {"compliance": verdict.model_dump(), "usage": usage,
           "drafts": [d.model_copy(update={"cover_letter": verdict.cleaned_text, "status": "compliant" if verdict.allowed else "blocked"}).model_dump()],
           "_summary": ("allowed" if verdict.allowed else "BLOCKED: " + "; ".join(verdict.blocked_reasons)) + f", {len(verdict.redactions)} fixes"}
    if not verdict.allowed:
        out.update({"status": "blocked", "status_reason": "Compliance Guard: " + "; ".join(verdict.blocked_reasons)})
    return out
