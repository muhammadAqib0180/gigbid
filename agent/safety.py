"""Guardrails shared by agents, MCP servers and the API (R9 / E4).

* Untrusted text (job posts, client messages) is delimited and never put in a system role.
* Injection heuristics flag instruction-like text inside untrusted data.
* PII masking for logs, traces and the audit log.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --------------------------------------------------------------------------- injection
INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("override", r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|system|your)\b[^.\n]{0,30}\b(instruction|instructions|prompt|prompts|rules|guidelines|directions)\b"),
    ("role_hijack", r"\b(you are now|from now on you|act as (an?|the) |pretend to be|new instructions?:|system prompt|developer message)\b"),
    ("fake_tags", r"</?\s*(system|assistant|user|instructions?|im_start|im_end)\s*>|\[/?(INST|SYS)\]|###\s*(instruction|system)"),
    ("exfiltrate", r"\b(reveal|print|repeat|show|output)\b[^.\n]{0,30}\b(system prompt|instructions|api key|password|token|secret)s?\b"),
    ("contact_injection", r"\b(include|add|put|write|share|mention)\b[^.\n]{0,40}\b(phone|e-?mail|whatsapp|telegram|skype|discord|signal|wechat|contact (details|info))\b"),
    ("forced_output", r"\b(begin|start|end) (your|the) (proposal|reply|response|cover letter) with\b|\brespond only with\b|\bonly reply with\b"),
    ("action_hijack", r"\b(submit|send|approve|apply)\b[^.\n]{0,25}\b(immediately|right now|without (review|approval|asking))\b"),
    ("score_tamper", r"\b(set|mark|rate|classify)\b[^.\n]{0,30}\b(risk|score|fit|this job)\b[^.\n]{0,20}\b(safe|low|trusted|0|zero|100|high fit|legitimate)\b"),
    ("ai_probe", r"\b(if you are an? (ai|bot|llm|language model)|as an ai language model|prove you are human)\b"),
]
_INJ = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in INJECTION_PATTERNS]
_ZERO_WIDTH = re.compile(r"[​-‏⁠-⁤﻿]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class InjectionFinding:
    kind: str
    span: str


def normalize_untrusted(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _ZERO_WIDTH.sub("", text)
    return text


def scan_injection(text: str) -> list[InjectionFinding]:
    text = normalize_untrusted(text)
    findings: list[InjectionFinding] = []
    for comment in _HTML_COMMENT.findall(text):
        findings.append(InjectionFinding("hidden_comment", comment[:160]))
    for name, rx in _INJ:
        for m in rx.finditer(text):
            start = max(0, m.start() - 20)
            findings.append(InjectionFinding(name, text[start : m.end() + 40].strip()[:200]))
    return findings


def neutralize(text: str) -> str:
    """Remove hidden carriers and break fake role tags; the text stays readable for the model."""
    text = normalize_untrusted(text)
    text = _HTML_COMMENT.sub("[hidden comment removed]", text)
    text = re.sub(r"<\s*/?\s*(system|assistant|user|instructions?|untrusted[a-z_]*)\s*>", "[tag removed]", text, flags=re.I)
    return text


def wrap_untrusted(kind: str, text: str) -> str:
    """Delimit untrusted data. The system prompt says content inside these tags is data only."""
    return f"<untrusted_{kind}>\n{neutralize(text)}\n</untrusted_{kind}>"


# --------------------------------------------------------------------------- PII
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w$])(?:\+?\d[\d\s().-]{7,}\d)(?![\w%])")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
MSG_LINK_RE = re.compile(r"\b(?:https?://)?(?:wa\.me|t\.me|telegram\.me|discord\.gg|join\.skype\.com)/\S+", re.I)
URL_RE = re.compile(r"\bhttps?://[^\s)>\]]+", re.I)
_DATEISH = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}")


def _is_phone(span: str) -> bool:
    """9+ digits and not a date/time (ISO timestamps look like phone numbers to a naive regex)."""
    return len(re.sub(r"\D", "", span)) >= 9 and not _DATEISH.search(span)


def mask_pii(text: str) -> str:
    if not text:
        return text
    text = MSG_LINK_RE.sub("[link]", text)
    text = EMAIL_RE.sub("[email]", text)
    text = IBAN_RE.sub("[iban]", text)
    text = CARD_RE.sub(lambda m: "[card]" if len(re.sub(r"\D", "", m.group())) >= 13 else m.group(), text)
    text = PHONE_RE.sub(lambda m: "[phone]" if _is_phone(m.group()) else m.group(), text)
    return text


def mask_obj(obj):
    """Recursively mask strings inside dicts/lists (for traces and audit logs)."""
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: ("[redacted]" if k.lower() in {"token", "access_token", "refresh_token", "authorization", "password", "api_key"} else mask_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v) for v in obj]
    return obj


def contact_detail_spans(text: str) -> list[tuple[str, str]]:
    """(kind, span) for any contact detail a proposal/message must not contain."""
    spans: list[tuple[str, str]] = []
    for m in EMAIL_RE.finditer(text):
        spans.append(("email", m.group()))
    for m in MSG_LINK_RE.finditer(text):
        spans.append(("messaging_link", m.group()))
    for m in PHONE_RE.finditer(text):
        if _is_phone(m.group()):
            spans.append(("phone", m.group()))
    for m in URL_RE.finditer(text):
        u = m.group()
        if not re.search(r"(github\.com|upwork\.com|gitlab\.com)", u, re.I):
            spans.append(("external_url", u))
    return spans
