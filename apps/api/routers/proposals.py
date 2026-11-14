"""Proposal studio helpers (regenerate one paragraph) and the pipeline board."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent import llm
from agent.settings import cfg
from apps.api.auth.users import current_user
from apps.api.db import ProposalCard, User, get_session
from apps.api.deps import iso, runner
from apps.api.routers.approvals import pending_for
from apps.api.schemas import PipelineCard, PipelineOut, RegenerateIn, RegenerateOut
from worker.runner import GraphRunner

router = APIRouter(prefix="/api", tags=["proposals"])


@router.post("/proposals/{thread_id:path}/regenerate", response_model=RegenerateOut)
async def regenerate_paragraph(thread_id: str, body: RegenerateIn, user: User = Depends(current_user),
                               r: GraphRunner = Depends(runner)) -> RegenerateOut:
    """Rewrite one paragraph with the Writer's model. Nothing changes in the graph until the user submits the
    edited draft (which is then diffed for style memory and re-checked by Compliance)."""
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    p = await pending_for(r, thread_id)
    if not p:
        raise HTTPException(409, "no draft awaiting approval")
    paras = [x for x in re.split(r"\n\s*\n", body.text) if x.strip()]
    if body.paragraph_index >= len(paras):
        raise HTTPException(422, "paragraph index out of range")
    para = paras[body.paragraph_index]
    ev = "\n".join(f"[{e['evidence_id']}] {e['snippet'][:300]}" for c in p.get("claims", []) for e in c.get("evidence", []))

    def heuristic() -> str:
        sents = re.split(r"(?<=[.!?])\s+", para)
        return " ".join(sents[:2]) if len(sents) > 2 else para

    res = await llm.text("writer", "regenerate_paragraph", {"proposal": body.text[:4000], "paragraph": para, "index": body.paragraph_index,
                                                            "instruction": body.instruction or "make it more specific and concise",
                                                            "evidence": ev or "none"}, heuristic=heuristic)
    return RegenerateOut(paragraph_index=body.paragraph_index, text=str(res.value).strip(), model=res.model)


@router.get("/pipeline", response_model=PipelineOut)
async def pipeline(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> PipelineOut:
    rows = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user.id).order_by(ProposalCard.updated_at.desc()))).scalars().all()
    cards = [PipelineCard(id=c.id, job_id=c.job_id, thread_id=c.thread_id, proposal_id=c.proposal_id, marketplace_thread_id=c.marketplace_thread_id,
                          stage=c.stage, title=c.title, category=c.category, strategy=c.strategy, bid_amount=c.bid_amount,
                          connects_spent=c.connects_spent, updated_at=iso(c.updated_at) or "") for c in rows]
    return PipelineOut(stages=list(cfg("pipeline_stages", [])), cards=cards)
