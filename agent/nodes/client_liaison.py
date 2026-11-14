"""Client Liaison (conversation graph): read the thread, classify intent, draft a reply or interview slots,
check compliance, interrupt for approval, then send (idempotent) and update the pipeline."""

from __future__ import annotations

import difflib
import re

from langgraph.types import interrupt

from agent import llm
from agent.handoffs import ApprovalDecision, ClientIntent, LiaisonDraft, Slot
from agent.marketplace_port import McpMarketplacePort
from agent.mcp_client import ToolFailed
from agent.memory.store import record_edit, style_rules
from agent.nodes.common import gateway, node
from agent.nodes.compliance import run_compliance
from agent.nodes.risk_assessor import SCAM_RULES
from agent.profile import merged_profile
from agent.safety import scan_injection, wrap_untrusted
from agent.settings import cfg

INTERVIEW = re.compile(r"\b(call|meet|meeting|interview|available|availability|schedule|zoom|video|chat live|times? that work)\b", re.I)
NEGOTIATE = re.compile(r"\b(budget|price|rate|cheaper|lower|discount|flexib|afford|counter|\$\s?\d)", re.I)


def rule_intent(text: str) -> ClientIntent:
    for flag, rx, _w in SCAM_RULES:
        if flag in {"off_platform_contact", "off_platform_payment", "unpaid_work", "credential_request"} and re.search(rx, text, re.I):
            return ClientIntent(intent="scam_signal", confidence=0.9, rationale=f"rule: {flag}")
    if INTERVIEW.search(text):
        return ClientIntent(intent="interview_request", confidence=0.75, rationale="rule: scheduling words")
    if NEGOTIATE.search(text):
        return ClientIntent(intent="negotiation", confidence=0.7, rationale="rule: price words")
    if "?" in text:
        return ClientIntent(intent="question", confidence=0.6, rationale="rule: question mark")
    return ClientIntent(intent="other", confidence=0.4, rationale="rule: default")


@node("load_thread", kind="conversation")
async def load_thread(state, config, store):
    msgs = await McpMarketplacePort(gateway(state), "liaison").list_messages(state["marketplace_thread_id"])
    client_msgs = [m for m in msgs if m.get("sender") == "client"]
    if not msgs or msgs[-1].get("sender") != "client":
        return {"messages": msgs, "status": "idle", "status_reason": "no unanswered client message", "_summary": "nothing to reply to"}
    return {"messages": msgs, "last_client_message": client_msgs[-1], "status": "drafting",
            "_summary": f"{len(msgs)} messages; latest from client"}


@node("classify", kind="conversation")
async def classify(state, config, store):
    text = state["last_client_message"]["text"]
    base = rule_intent(text)
    usage: dict = {}
    intent = base
    if cfg("node_modes.intent", "hybrid") != "rules" and base.intent != "scam_signal":
        res = await llm.structured("intent", "intent", ClientIntent, {"message": wrap_untrusted("client_message", text)},
                                   heuristic=lambda: base)
        usage = res.usage
        if res.value.intent == "scam_signal" or res.value.confidence >= base.confidence:
            intent = res.value
    if scan_injection(text):
        intent = ClientIntent(intent=intent.intent, confidence=intent.confidence, rationale=intent.rationale + " (+ injection text ignored)")
    return {"intent": intent.model_dump(), "usage": usage, "_summary": f"intent: {intent.intent} ({intent.confidence:.2f})"}


def heuristic_reply(intent: str, msg: str, slots: list[dict], floor: float | None, evidence: list[dict], name: str) -> str:
    if intent == "scam_signal":
        return ("Thanks for getting back to me. To keep us both protected I keep all communication, files and payments here on the "
                "platform, and I don't do unpaid trial work. Happy to continue in this thread whenever you're ready.")
    if intent == "interview_request" and slots:
        import datetime as _dt

        times = "; ".join(_dt.datetime.fromisoformat(s["start"]).strftime("%a %d %b, %H:%M") for s in slots[:3])
        return f"Thanks, happy to talk. I'm free at these times (my local time): {times}. Pick whichever suits you and I'll be there - we can use the platform's call feature."
    if intent == "negotiation":
        f = f"${floor:,.0f}" if floor else "my minimum"
        return (f"Thanks for being upfront about budget. I can't go below {f} for the full scope, but I could reduce scope to fit "
                "your number - for example by delivering the core piece first and the rest as a follow-up. Would that work?")
    if evidence:
        e = evidence[0]
        return (f"Good question. In a similar project ({e.get('title') or e.get('project')}), "
                f"{(e.get('snippet') or '')[:160].strip()}... I'd take the same approach here and confirm details with you first. "
                "Does that answer it?")
    return "Thanks for the message. Could you share a bit more detail so I can give you a precise answer?"


@node("draft_reply", kind="conversation")
async def draft_reply(state, config, store):
    gw = gateway(state)
    intent = ClientIntent.model_validate(state["intent"])
    msg = state["last_client_message"]["text"]
    profile = merged_profile(state.get("persona_id", "ai_ml_engineer"), None)
    slots: list[dict] = []
    evidence: list[dict] = []
    if intent.intent == "interview_request":
        slots = (await gw.call("liaison", "workspace", "free_slots", {"days": 5, "duration_minutes": 30, "max_slots": 3}))["slots"]
    elif intent.intent in {"question", "other"}:
        try:
            evidence = (await gw.call("liaison", "portfolio", "search_evidence", {"requirement": msg[:400], "k": 3}))["items"]
        except ToolFailed:
            evidence = []
    floor = float(profile.get("min_fixed_usd", 0)) if intent.intent == "negotiation" else None
    history = "\n".join(f"{m['sender']}: {m['text'][:300]}" for m in (state.get("messages") or [])[-6:])
    rules = await style_rules(store, state.get("user_id", "local"))
    res = await llm.text("liaison", "liaison", {
        "floor": f"${floor:,.0f}" if floor else "n/a", "job_title": state.get("job_id", ""), "intent": intent.intent,
        "history": wrap_untrusted("thread", history), "message": wrap_untrusted("client_message", msg),
        "slots": "; ".join(s["start"] for s in slots) or "none", "evidence": "\n".join(f"[{e['evidence_id']}] {e['snippet'][:300]}" for e in evidence) or "none",
        "style_rules": "; ".join(rules) or "none"},
        heuristic=lambda: heuristic_reply(intent.intent, msg, slots, floor, evidence, profile.get("display_name", "")))
    d = LiaisonDraft(thread_id=state["marketplace_thread_id"], intent=intent, reply_text=str(res.value).strip(),
                     proposed_slots=[Slot.model_validate(s) for s in slots], evidence_ids=[e["evidence_id"] for e in evidence])
    return {"draft": d.model_dump(), "slots": slots, "usage": res.usage, "_summary": f"reply drafted ({len(d.reply_text.split())} words)"}


@node("message_compliance", kind="conversation")
async def message_compliance(state, config, store):
    d = LiaisonDraft.model_validate(state["draft"])
    verdict, usage = await run_compliance(d.reply_text, node_name="compliance", proposal=False)
    out = {"compliance": verdict.model_dump(), "draft": d.model_copy(update={"reply_text": verdict.cleaned_text}).model_dump(),
           "usage": usage, "_summary": "allowed" if verdict.allowed else "BLOCKED: " + "; ".join(verdict.blocked_reasons)}
    if not verdict.allowed:
        out.update({"status": "blocked", "status_reason": "Compliance Guard: " + "; ".join(verdict.blocked_reasons)})
    return out


@node("message_approval", kind="conversation", retries=0)
async def message_approval(state, config, store):
    raw = interrupt({"type": "message_approval", "thread_id": state["thread_id"], "marketplace_thread_id": state["marketplace_thread_id"],
                     "client_message": state["last_client_message"], "intent": state["intent"], "draft": state["draft"],
                     "slots": state.get("slots", []), "compliance": state.get("compliance"), "actions": ["approve", "edit", "reject"]})
    dec = ApprovalDecision.model_validate(raw if isinstance(raw, dict) else {"action": str(raw)})
    d = LiaisonDraft.model_validate(state["draft"])
    rec = {"action": dec.action, "reason": dec.reason}
    if dec.action == "approve":
        return {"approvals": [rec], "status": "approved", "_summary": "approved"}
    if dec.action == "reject":
        return {"approvals": [rec], "status": "rejected", "status_reason": dec.reason or "rejected", "_summary": "rejected"}
    edited = (dec.edited_text or "").strip()
    rec["diff"] = "\n".join(difflib.unified_diff(d.reply_text.splitlines(), edited.splitlines(), lineterm=""))[:3000]
    rec["promoted_rules"] = await record_edit(store, state.get("user_id", "local"), state["thread_id"] + ":" + str(len(state.get("approvals") or [])),
                                              d.reply_text, edited)
    return {"approvals": [rec], "draft": d.model_copy(update={"reply_text": edited}).model_dump(), "status": "recheck",
            "_summary": "edited; re-checking compliance"}


@node("send_reply", kind="conversation")
async def send_reply(state, config, store):
    gw = gateway(state)
    d = LiaisonDraft.model_validate(state["draft"])
    n = len(state.get("messages") or [])
    key = f"{state['thread_id']}:m{n}:send".replace("/", "_")[:120]
    slots = [s.model_dump() for s in d.proposed_slots] if d.intent.intent == "interview_request" else None
    sent = await McpMarketplacePort(gw, "liaison").send_message(state["marketplace_thread_id"], d.reply_text, key, slots=slots)
    stage = {"interview_request": "interview", "scam_signal": "flagged"}.get(d.intent.intent, "replied")
    if slots:
        s = slots[0]
        await gw.call("liaison", "workspace", "create_interview_hold",
                      {"start": s["start"], "end": s["end"], "title": f"Tentative interview ({state['marketplace_thread_id']})",
                       "idempotency_key": key.replace(":send", ":hold")})
    return {"sent": sent, "pipeline_stage": stage, "status": "sent", "_summary": f"sent {sent.get('message_id')} ({stage})"}
