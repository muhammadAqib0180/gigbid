"""Client threads with suggested replies and interview slots; approval happens through /api/approvals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.marketplace_port import McpMarketplacePort
from agent.mcp_client import ToolGateway, ToolUnavailable
from apps.api.auth.users import current_user
from apps.api.db import Conversation, ProposalCard, User, get_session
from apps.api.deps import dispatcher, iso, runner
from apps.api.dispatch import Dispatcher
from apps.api.routers.approvals import pending_for
from apps.api.schemas import ConversationOut, OkOut, ThreadDetail
from worker.runner import GraphRunner

router = APIRouter(prefix="/api", tags=["messages"])


def conv_out(c: Conversation, title: str = "") -> ConversationOut:
    return ConversationOut(marketplace_thread_id=c.marketplace_thread_id, graph_thread_id=c.graph_thread_id, job_id=c.job_id,
                           proposal_id=c.proposal_id, status=c.status, intent=c.intent, title=title, updated_at=iso(c.updated_at) or "")


@router.get("/messages", response_model=list[ConversationOut])
async def threads(user: User = Depends(current_user), s: AsyncSession = Depends(get_session)) -> list[ConversationOut]:
    rows = (await s.execute(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()))).scalars().all()
    titles = {c.job_id: c.title for c in (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user.id))).scalars().all()}
    return [conv_out(c, titles.get(c.job_id, "")) for c in rows]


@router.get("/messages/{mthread}", response_model=ThreadDetail)
async def thread(mthread: str, user: User = Depends(current_user), s: AsyncSession = Depends(get_session),
                 r: GraphRunner = Depends(runner)) -> ThreadDetail:
    c = (await s.execute(select(Conversation).where(Conversation.user_id == user.id, Conversation.marketplace_thread_id == mthread))).scalar_one_or_none()
    try:
        msgs = await McpMarketplacePort(ToolGateway(user.id, user.persona_id, account=user.account_id), "liaison").list_messages(mthread)
    except ToolUnavailable as exc:
        raise HTTPException(503, "marketplace unavailable") from exc
    pending = await pending_for(r, c.graph_thread_id) if c else None
    return ThreadDetail(conversation=conv_out(c) if c else None, messages=msgs, pending=pending)


@router.post("/messages/{mthread}/draft", response_model=OkOut)
async def draft(mthread: str, user: User = Depends(current_user), d: Dispatcher = Depends(dispatcher),
                s: AsyncSession = Depends(get_session)) -> OkOut:
    card = (await s.execute(select(ProposalCard).where(ProposalCard.user_id == user.id, ProposalCard.marketplace_thread_id == mthread))).scalar_one_or_none()
    await d.run_conversation(user.id, mthread, card.proposal_id if card else None, card.job_id if card else None)
    return OkOut(detail="drafting a reply")
