"""GigBid API (FastAPI). Routers: auth, jobs, proposals, approvals, messages, runs, analytics, settings.

Run:  uvicorn apps.api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent.mcp_client import probe
from agent.persistence import persistence
from agent.safety import mask_pii
from agent.tracing import set_trace_id
from apps.api.db import init_db
from apps.api.dispatch import Dispatcher
from apps.api.routers import analytics, approvals, auth, jobs, messages, proposals, runs, settings
from worker.runner import GraphRunner


class PIIMaskingFilter(logging.Filter):
    """E4: mask emails, phone numbers and payment details in every log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask_pii(str(record.getMessage()))
            record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True


def _setup_logging() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(PIIMaskingFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    await init_db()
    async with persistence() as (cp, store):
        runner = GraphRunner(cp, store)
        dispatcher = Dispatcher(runner)
        app.state.runner, app.state.dispatcher, app.state.store = runner, dispatcher, store
        tasks = []
        if dispatcher.mode == "inline":
            await dispatcher.recover()
        if dispatcher.mode == "inline" and os.getenv("DISABLE_SCHEDULER") != "1":
            tasks.append(asyncio.create_task(dispatcher.inline_loop()))

        async def health_loop() -> None:
            while True:
                for srv in ("marketplace", "portfolio", "workspace"):
                    await probe(srv)
                await asyncio.sleep(15)

        tasks.append(asyncio.create_task(health_loop()))
        if os.getenv("SEED_ON_START") == "1":
            from scripts.seed import seed

            await seed()
        yield
        dispatcher.stop()
        for t in tasks:
            t.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot. Every proposal, message and Connects spend needs human approval.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    tid = set_trace_id(request.headers.get("x-trace-id"))
    resp = await call_next(request)
    resp.headers["X-Trace-Id"] = tid
    return resp


for r in (auth.router, jobs.router, approvals.router, proposals.router, messages.router, runs.router, analytics.router, settings.router):
    app.include_router(r)


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "gigbid-api"}
