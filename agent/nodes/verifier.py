"""Claim verification node (B3): split -> ground against evidence -> remove/soften unsupported claims, BEFORE
the Critic sees the draft. Records the unsupported-claim rate before and after."""

from __future__ import annotations

import asyncio

from agent.handoffs import ProposalDraft
from agent.nodes.common import last, node
from rag.verify import verify_claims


@node("verifier")
async def verifier(state, config, store):
    d = ProposalDraft.model_validate(last(state, "drafts"))
    evidence = state.get("evidence") or []
    fixed, report = await asyncio.to_thread(verify_claims, d.cover_letter, evidence, d.version)
    d2 = d.model_copy(update={"cover_letter": fixed, "claims": report.claims, "status": "verified"})
    return {"drafts": [d2.model_dump()], "verifications": [report.model_dump()],
            "_summary": f"{report.total_claims} claims; unsupported {report.unsupported_before} -> {report.unsupported_after}"}
