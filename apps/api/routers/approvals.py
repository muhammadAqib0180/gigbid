"""Pending approvals (read from the checkpointer, so a page refresh or API restart never loses one) and the
approve / edit / reject action, which resumes the interrupted LangGraph thread."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.users import current_user
from apps.api.db import Conversation, JobRecord, User, get_session
from apps.api.deps import dispatcher, runner
from apps.api.dispatch import Dispatcher
from apps.api.schemas import ApprovalIn, ApprovalOut, OkOut
from worker.runner import GraphRunner

router = APIRouter(prefix="/api", tags=["approvals"])


async def pending_for(r: GraphRunner, thread_id: str) -> dict | None:
    graph = r.bid if thread_id.startswith("bid:") else r.conv
    st = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    for t in st.tasks:
        if t.interrupts:
            return t.interrupts[0].value
    return None


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(user: User = Depends(current_user), s: AsyncSession = Depends(get_session),
                         r: GraphRunner = Depends(runner)) -> list[ApprovalOut]:
    out: list[ApprovalOut] = []
    jobs = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id,
                                                    JobRecord.status.in_(["awaiting_approval", "resuming"])))).scalars().all()
    for j in jobs:
        p = await pending_for(r, j.thread_id)
        if p:
            out.append(ApprovalOut(thread_id=j.thread_id, kind="proposal", job_id=j.job_id, title=j.title, payload=p))
    convs = (await s.execute(select(Conversation).where(Conversation.user_id == user.id,
                                                        Conversation.status.in_(["awaiting_approval", "resuming"])))).scalars().all()
    for c in convs:
        p = await pending_for(r, c.graph_thread_id)
        if p:
            out.append(ApprovalOut(thread_id=c.graph_thread_id, kind="message", job_id=c.job_id, title=f"Reply in {c.marketplace_thread_id}", payload=p))
    return out


@router.get("/approvals/{thread_id:path}", response_model=ApprovalOut)
async def get_approval(thread_id: str, user: User = Depends(current_user), r: GraphRunner = Depends(runner)) -> ApprovalOut:
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    p = await pending_for(r, thread_id)
    if not p:
        raise HTTPException(404, "no pending approval on this thread")
    return ApprovalOut(thread_id=thread_id, kind="proposal" if thread_id.startswith("bid:") else "message",
                       job_id=p.get("job_id"), title=p.get("job_title") or "", payload=p)


@router.post("/approvals/{thread_id:path}", response_model=OkOut)
async def decide(thread_id: str, body: ApprovalIn, user: User = Depends(current_user), d: Dispatcher = Depends(dispatcher),
                 r: GraphRunner = Depends(runner), s: AsyncSession = Depends(get_session)) -> OkOut:
    if f":{user.id}:" not in thread_id:
        raise HTTPException(404, "not found")
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edited_text required for edit")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    if not await pending_for(r, thread_id):
        raise HTTPException(409, "nothing to approve (already decided?)")
    if thread_id.startswith("bid:"):
        j = (await s.execute(select(JobRecord).where(JobRecord.user_id == user.id, JobRecord.thread_id == thread_id))).scalar_one_or_none()
        if j:
            j.status = "resuming"
    else:
        c = (await s.execute(select(Conversation).where(Conversation.user_id == user.id, Conversation.graph_thread_id == thread_id))).scalar_one_or_none()
        if c:
            c.status = "resuming"
    await s.commit()
    await d.resume(user.id, thread_id, {**body.model_dump(), "approved_by": user.email})
    return OkOut(detail=f"{body.action} sent; the graph resumes from its checkpoint")
