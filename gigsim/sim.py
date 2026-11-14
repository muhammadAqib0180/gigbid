"""Simulated clients. Each job has hidden preferences (gigsim/seed/hidden.json): must-have skills,
budget ceiling, dislike of generic openings, preference for short proposals, responsiveness.

The decision model is rule-based and seeded, so a fixed job set gives a reproducible reply/hire rate
(graders and CI need determinism and no API cost). Optional LLM mode is documented in gigsim/README.md.
"""

from __future__ import annotations

import hashlib
import math
import random
import re

GENERIC_OPENINGS = [
    "dear hiring manager", "i am writing to apply", "i am excited to apply", "i hope this message finds you well",
    "i am the perfect fit", "hi there! i am a hard-working", "i have read your job description", "to whom it may concern",
]
VIOLATION_RX = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s().-]{8,}\d|whatsapp|telegram|skype|wechat|paypal|payoneer|"
    r"\bguarantee|money back|100% satisfaction", re.I)
STOP = {"need", "needed", "looking", "expert", "developer", "project", "freelancer", "with", "for", "and", "the", "our", "help"}


def _rng(*parts: object) -> random.Random:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def features(job: dict, hidden: dict, proposal: dict) -> dict:
    text = proposal.get("cover_letter", "")
    low = text.lower()
    musts = hidden.get("must_have_skills") or []
    cov = sum(1 for s in musts if s.lower() in low) / len(musts) if musts else 0.5
    first = " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:2]).lower()
    title_terms = {w for w in re.findall(r"[a-z][a-z0-9.+#-]{4,}", job.get("title", "").lower()) if w not in STOP}
    skill_terms = {s.lower() for s in job.get("skills", [])}
    personal = any(t in first for t in title_terms | skill_terms)
    generic = any(g in low[:200] for g in GENERIC_OPENINGS)
    specific = bool(re.search(r"\d", text)) and bool(re.search(r"\b(project|client|built|shipped|delivered)\b", low))
    words = len(text.split())
    bid = float(proposal.get("bid_amount") or 0)
    ceiling = hidden.get("budget_ceiling")
    if job.get("is_hourly"):
        price_ok = not job.get("hourly_high") or bid <= float(job["hourly_high"]) * 1.1
    else:
        price_ok = not ceiling or bid <= ceiling
    return {
        "coverage": round(cov, 3), "personal": personal, "generic": generic, "specific": specific,
        "words": words, "price_ok": price_ok, "violation": bool(VIOLATION_RX.search(text)),
    }


def reply_probability(f: dict, hidden: dict) -> float:
    logit = -1.4 + 1.8 * f["coverage"] + 0.9 * f["personal"] + 0.6 * f["specific"]
    if f["generic"]:
        logit -= 1.1 if hidden.get("dislikes_generic") else 0.3
    if hidden.get("prefers_short") and f["words"] > 220:
        logit -= 0.6
    if f["words"] < 60:
        logit -= 0.5
    if not f["price_ok"]:
        logit -= 1.5
    p = 1 / (1 + math.exp(-logit))
    return max(0.0, min(1.0, p * (0.6 + 0.6 * float(hidden.get("responsiveness", 0.6)))))


def decide(job: dict, hidden: dict, proposal: dict) -> dict:
    """Returns {"viewed", "replied", "intent", "p_reply", "features"} deterministically."""
    f = features(job, hidden, proposal)
    rng = _rng(job["job_id"], proposal.get("cover_letter", ""), proposal.get("bid_amount"))
    if hidden.get("scam"):
        return {"viewed": True, "replied": True, "intent": "scam_signal", "p_reply": 1.0, "features": f}
    if f["violation"]:
        return {"viewed": True, "replied": False, "intent": None, "p_reply": 0.0, "features": f, "flagged": True}
    p = reply_probability(f, hidden)
    replied = rng.random() < p
    intent = None
    if replied:
        r = rng.random()
        if not f["price_ok"] and r < 0.6:
            intent = "negotiation"
        elif f["coverage"] >= 0.5 and r < 0.55:
            intent = "interview_request"
        else:
            intent = "question"
    return {"viewed": rng.random() < 0.9, "replied": replied, "intent": intent, "p_reply": round(p, 4), "features": f}


def hire_probability(f: dict, interviewed: bool) -> float:
    base = 0.15 + 0.35 * f.get("coverage", 0) + 0.15 * f.get("specific", False)
    return min(0.9, base + (0.25 if interviewed else 0.0))


CLIENT_MESSAGES = {
    "question": [
        "Thanks for applying. Can you tell me more about how you would handle {skill} in our setup?",
        "Interesting proposal. Have you worked with a team our size before, and how do you usually communicate progress?",
        "Could you explain how you would test this before delivery?",
    ],
    "interview_request": [
        "Your experience looks relevant. Are you available for a 30-minute call this week?",
        "I'd like to talk before deciding. Could you share a few times that work for a short video call?",
    ],
    "negotiation": [
        "Your proposal is good but the price is above our budget. Could you do it for {counter}?",
        "We like your approach. Is there any flexibility on the rate? We were thinking around {counter}.",
    ],
    "scam_signal": [
        "Great! Please add me on Telegram @hr_fastpay so we can continue there, the platform is slow.",
        "You are selected. Send your WhatsApp number and we will pay you directly in crypto to avoid fees.",
        "Before we start, complete a free trial task and send it to my personal email. Payment after approval.",
    ],
    "after_slots": [
        "Thanks, {slot} works for me. Talk then.",
        "Booked for {slot}. Looking forward to it.",
    ],
    "after_answer": [
        "Thanks, that answers my question. I'll get back to you soon.",
        "Makes sense. Let me discuss with my team.",
    ],
    "hired": ["Happy to move forward - I've sent the offer."],
    "lost": ["Thank you for your time; we went with another freelancer."],
}


def client_message(intent: str, job: dict, proposal: dict, seed: str, **kw: str) -> str:
    rng = _rng(seed, intent)
    tmpl = rng.choice(CLIENT_MESSAGES[intent])
    skill = (job.get("skills") or ["this"])[0]
    bid = float(proposal.get("bid_amount") or 0)
    counter = f"${bid * 0.8:,.0f}" if bid else "a lower amount"
    return tmpl.format(skill=skill, counter=counter, **kw)
