"""Human approval (C5, R4): interrupt() before any proposal is created/submitted or Connects are spent.

`prepare_approval` builds the payload (draft, evidence behind every claim, risk report, price rationale and
the marketplace dry_run preview) in its own node so the preview is not re-fetched when the interrupted
`approval` node re-executes on resume. `submit` is a separate node AFTER approval and uses idempotency keys,
so a crash between approval and submission still submits exactly once.
"""

from __future__ import annotations

import difflib

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision, EvidenceItem, PriceQuote, ProposalDraft
from agent.marketplace_port import McpMarketplacePort
from agent.memory.store import record_edit
from agent.nodes.common import gateway, last, node


def idem(state: dict, version: int, action: str) -> str:
    return f"{state['thread_id']}:v{version}:{action}".replace("/", "_")[:120]


@node("prepare_approval")
async def prepare_approval(state, config, store):
    d = ProposalDraft.model_validate(last(state, "drafts"))
    price = PriceQuote.model_validate(state["price"])
    port = McpMarketplacePort(gateway(state), "approval")
    preview = await port.create_proposal_draft(
        {"job_id": state["job"]["job_id"], "cover_letter": d.cover_letter, "bid_amount": price.amount, "bid_unit": price.unit,
         "screening_answers": [{"question": a.question, "answer": a.answer} for a in d.screening_answers]},
        idempotency_key=idem(state, d.version, "preview"), dry_run=True)
    p = preview.get("preview") or {}
    p["connects_cost"] = max(int(p.get("connects_cost") or 0), price.connects_cost)
    return {"preview": p, "status": "awaiting_approval", "status_reason": "waiting for your approval",
            "_summary": f"dry run: {p.get('connects_cost')} Connects, balance after submit {int(p.get('balance_before') or 0) - int(p.get('connects_cost') or 0)}"}


def approval_payload(state: dict) -> dict:
    d = ProposalDraft.model_validate(last(state, "drafts"))
    ev = {e["evidence_id"]: EvidenceItem.model_validate(e) for e in state.get("evidence") or []}
    claims = [{"claim_id": c.claim_id, "text": c.text, "label": c.label, "score": c.support_score, "note": c.note,
               "evidence": [{"evidence_id": i, "title": ev[i].title, "type": ev[i].type, "source": ev[i].source,
                             "snippet": ev[i].snippet[:400]} for i in c.evidence_ids if i in ev]}
              for c in d.claims if c.label != "not_a_claim"]
    return {"type": "proposal_approval", "thread_id": state["thread_id"], "job_id": state["job"]["job_id"],
            "job_title": state["job"].get("title"), "draft": d.model_dump(), "claims": claims, "risk": state.get("risk"),
            "fit": state.get("fit"), "price": state.get("price"), "preview": state.get("preview"),
            "compliance": state.get("compliance"), "critiques": state.get("critiques", [])[-2:],
            "verification": (state.get("verifications") or [{}])[-1], "actions": ["approve", "edit", "reject"]}


@node("approval", retries=0)
async def approval(state, config, store):
    raw = interrupt(approval_payload(state))
    dec = ApprovalDecision.model_validate(raw if isinstance(raw, dict) else {"action": str(raw)})
    d = ProposalDraft.model_validate(last(state, "drafts"))
    rec = {"action": dec.action, "version": d.version, "reason": dec.reason, "by": dec.approved_by}
    if dec.action == "approve":
        return {"approvals": [rec], "status": "approved", "_summary": "approved by user"}
    if dec.action == "reject":
        return {"approvals": [rec], "status": "rejected", "status_reason": dec.reason or "rejected by user",
                "_summary": f"rejected: {dec.reason or '-'}"}
    edited = (dec.edited_text or "").strip()
    diff = "\n".join(difflib.unified_diff(d.cover_letter.splitlines(), edited.splitlines(), "draft", "edited", lineterm=""))
    promoted = await record_edit(store, state.get("user_id", "local"), state["thread_id"], d.cover_letter, edited)
    rec.update({"diff": diff[:4000], "promoted_rules": promoted})
    nd = d.model_copy(update={"version": d.version + 1, "cover_letter": edited, "status": "edited"})
    return {"approvals": [rec], "drafts": [nd.model_dump()], "status": "recheck",
            "_summary": f"edited by user; {len(promoted)} style rule(s) promoted; re-checking compliance"}


@node("submit")
async def submit(state, config, store):
    d = ProposalDraft.model_validate(last(state, "drafts"))
    price = PriceQuote.model_validate(state["price"])
    port = McpMarketplacePort(gateway(state), "submit")
    created = await port.create_proposal_draft(
        {"job_id": state["job"]["job_id"], "cover_letter": d.cover_letter, "bid_amount": price.amount, "bid_unit": price.unit,
         "screening_answers": [{"question": a.question, "answer": a.answer} for a in d.screening_answers]},
        idempotency_key=idem(state, d.version, "create"))
    sub = await port.submit_proposal(created["proposal_id"], idempotency_key=idem(state, d.version, "submit"))
    return {"submission": {"proposal_id": created["proposal_id"], "status": sub.get("status"), "connects_spent": sub.get("connects_spent", 0),
                           "balance": sub.get("balance"), "idempotent_replay": bool(sub.get("idempotent_replay")),
                           "marketplace": sub.get("marketplace"), "note": sub.get("note"), "version": d.version},
            "status": "submitted" if sub.get("status") == "submitted" else str(sub.get("status")),
            "_summary": f"proposal {created['proposal_id']} -> {sub.get('status')} ({sub.get('connects_spent', 0)} Connects)"}


async def finalize(state, config=None, store=None):
    return {"steps": 0}
