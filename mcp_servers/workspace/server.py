"""Workspace MCP server (A3): free calendar slots, tentative interview holds, email drafts.

Backed by a documented LOCAL MOCK (tables in the GigBid database) instead of Google Calendar/Gmail, so no
Google OAuth app review is needed; the agent only ever sees these MCP tools, so swapping in the Google APIs
is a backend change here. Working hours and busy blocks are seeded per user.

Run:  python -m mcp_servers.workspace.server --port 8103
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import uuid
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers._shared import BearerAuthMiddleware, audit, caller_from_ctx, engine, idem_get, idem_put

SERVER = "workspace"
mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative interview holds and email drafts (mock backend).",
              stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
WORK_START, WORK_END = int(os.getenv("WORK_START_HOUR", "9")), int(os.getenv("WORK_END_HOUR", "17"))


class SlotOut(BaseModel):
    start: str
    end: str


class SlotList(BaseModel):
    timezone: str
    slots: list[SlotOut]


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = "tentative"
    idempotent_replay: bool = False


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    status: str = "draft"
    idempotent_replay: bool = False


def _init() -> None:
    with engine().begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS ws_events (id TEXT PRIMARY KEY, user_id TEXT, start TEXT, end_ TEXT, "
                       "title TEXT, status TEXT, meta TEXT)"))
        c.execute(text("CREATE TABLE IF NOT EXISTS ws_drafts (id TEXT PRIMARY KEY, user_id TEXT, to_ TEXT, subject TEXT, "
                       "body TEXT, created TEXT)"))


_init()


def _busy(user_id: str) -> list[tuple[dt.datetime, dt.datetime]]:
    with engine().begin() as c:
        rows = c.execute(text("SELECT start, end_ FROM ws_events WHERE user_id=:u"), {"u": user_id}).all()
    out = [(dt.datetime.fromisoformat(s), dt.datetime.fromisoformat(e)) for s, e in rows]
    return out


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
async def free_slots(
    ctx: Context,
    days: Annotated[int, Field(ge=1, le=14)] = 5,
    duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
    max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
    start_date: Annotated[str | None, Field(description="ISO date; default tomorrow")] = None,
) -> SlotList:
    """Free interview slots in working hours (Mon-Fri), skipping existing holds."""
    caller = caller_from_ctx(ctx)
    day = dt.date.fromisoformat(start_date) if start_date else dt.date.today() + dt.timedelta(days=1)
    busy = _busy(caller.user_id)
    slots: list[SlotOut] = []
    for _ in range(days * 2):
        if day.weekday() < 5:
            for hour in range(WORK_START, WORK_END):
                for minute in (0, 30):
                    s = dt.datetime.combine(day, dt.time(hour, minute))
                    e = s + dt.timedelta(minutes=duration_minutes)
                    if e.hour > WORK_END or (e.hour == WORK_END and e.minute > 0):
                        continue
                    if any(s < be and e > bs for bs, be in busy):
                        continue
                    if hour in (10, 14) and minute == 0:     # offer spread-out slots, not the whole day
                        slots.append(SlotOut(start=s.isoformat(timespec="minutes"), end=e.isoformat(timespec="minutes")))
        if len(slots) >= max_slots:
            break
        day += dt.timedelta(days=1)
    res = SlotList(timezone=os.getenv("WORKSPACE_TZ", "Asia/Karachi"), slots=slots[:max_slots])
    audit(SERVER, caller, "free_slots", {"days": days, "duration_minutes": duration_minutes}, res.model_dump())
    return res


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def create_interview_hold(
    ctx: Context,
    start: Annotated[str, Field(description="ISO datetime")],
    end: Annotated[str, Field(description="ISO datetime")],
    title: Annotated[str, Field(min_length=3, max_length=200)],
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128)],
) -> Hold:
    """Create a TENTATIVE calendar hold for an interview the user approved."""
    caller = caller_from_ctx(ctx)
    if hit := idem_get(caller.user_id, "create_interview_hold", idempotency_key):
        return Hold.model_validate(hit | {"idempotent_replay": True})
    hid = "hold_" + uuid.uuid4().hex[:10]
    with engine().begin() as c:
        c.execute(text("INSERT INTO ws_events VALUES (:id,:u,:s,:e,:t,'tentative','{}')"),
                  {"id": hid, "u": caller.user_id, "s": dt.datetime.fromisoformat(start).isoformat(),
                   "e": dt.datetime.fromisoformat(end).isoformat(), "t": title})
    res = Hold(hold_id=hid, start=start, end=end, title=title)
    idem_put(caller.user_id, "create_interview_hold", idempotency_key, res.model_dump())
    audit(SERVER, caller, "create_interview_hold", {"start": start, "end": end, "title": title}, res.model_dump())
    return res


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def create_email_draft(
    ctx: Context,
    to: Annotated[str, Field(min_length=3, max_length=200)],
    subject: Annotated[str, Field(min_length=1, max_length=200)],
    body: Annotated[str, Field(min_length=1, max_length=8000)],
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128)],
) -> EmailDraft:
    """Save an email DRAFT (never sends)."""
    caller = caller_from_ctx(ctx)
    if hit := idem_get(caller.user_id, "create_email_draft", idempotency_key):
        return EmailDraft.model_validate(hit | {"idempotent_replay": True})
    did = "draft_" + uuid.uuid4().hex[:10]
    with engine().begin() as c:
        c.execute(text("INSERT INTO ws_drafts VALUES (:id,:u,:to,:s,:b,:c)"),
                  {"id": did, "u": caller.user_id, "to": to, "s": subject, "b": body, "c": dt.datetime.now().isoformat()})
    res = EmailDraft(draft_id=did, to=to, subject=subject)
    idem_put(caller.user_id, "create_email_draft", idempotency_key, res.model_dump())
    audit(SERVER, caller, "create_email_draft", {"to": to, "subject": subject}, res.model_dump())
    return res


@mcp.resource("workspace://holds")
def holds_resource() -> str:
    """All tentative holds (for the local user in stdio mode)."""
    with engine().begin() as c:
        rows = c.execute(text("SELECT id, start, end_, title, status FROM ws_events ORDER BY start")).mappings().all()
    return json.dumps([dict(r) for r in rows], indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": SERVER, "backend": "local-mock"})


app = BearerAuthMiddleware(mcp.streamable_http_app())

if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8103")))
    ap.add_argument("--stdio", action="store_true")
    ns = ap.parse_args()
    if ns.stdio:
        mcp.run("stdio")
    else:
        uvicorn.run(app, host=ns.host, port=ns.port)
