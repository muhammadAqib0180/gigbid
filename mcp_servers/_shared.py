"""Shared plumbing for GigBid's own MCP servers (marketplace, workspace):

* Bearer-token auth (HS256 JWT minted by the API/agent per user + trace) on the HTTP endpoint.
* Caller identity inside tools (user, tenant/persona, trace id) from request headers.
* Append-only audit log (DB trigger forbids UPDATE/DELETE): user, tool, args, result, trace id - PII-masked.
* Idempotency store: (user, tool, key) -> first response, so a retried write never runs twice.
* Per-user token-bucket rate limiter (in-process, or Redis when REDIS_URL is set).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from agent.safety import mask_obj
from agent.settings import database_url

JWT_SECRET = os.getenv("MCP_JWT_SECRET", "dev-mcp-secret-change-me")
_current_caller: ContextVar[Caller | None] = ContextVar("mcp_caller", default=None)


@dataclass
class Caller:
    user_id: str
    persona: str
    trace_id: str


def mint_token(user_id: str, persona: str, trace_id: str | None = None, ttl_s: int = 900) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "persona": persona, "trace": trace_id or uuid.uuid4().hex, "iat": now,
                       "exp": now + ttl_s, "aud": "gigbid-mcp"}, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> Caller:
    claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="gigbid-mcp")
    return Caller(user_id=claims["sub"], persona=claims.get("persona", "ai_ml_engineer"), trace_id=claims.get("trace", ""))


def caller_from_ctx(ctx: Any) -> Caller:
    """Identity for the current tool call. HTTP: from the verified bearer token (+ X-Trace-Id header).
    stdio / in-memory tests: from MCP_DEFAULT_USER / MCP_DEFAULT_PERSONA."""
    c = _current_caller.get()
    req = None
    try:
        req = ctx.request_context.request
    except Exception:  # noqa: BLE001
        req = None
    if req is not None:
        auth = req.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            c = verify_token(auth.split(" ", 1)[1])
            tid = req.headers.get("x-trace-id")
            if tid:
                c.trace_id = tid
    if c is None:
        c = Caller(user_id=os.getenv("MCP_DEFAULT_USER", "local"), persona=os.getenv("MCP_DEFAULT_PERSONA", "ai_ml_engineer"),
                   trace_id=uuid.uuid4().hex)
    return c


class BearerAuthMiddleware:
    """ASGI middleware: every request except /health must carry a valid GigBid MCP JWT."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path", "") not in {"/health", "/healthz"}:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            auth = headers.get("authorization", "")
            try:
                if not auth.lower().startswith("bearer "):
                    raise ValueError("missing bearer token")
                verify_token(auth.split(" ", 1)[1])
            except Exception as exc:  # noqa: BLE001
                body = json.dumps({"error": "unauthorized", "detail": str(exc)[:120]}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------- persistence
_engine: Engine | None = None
_engine_lock = threading.Lock()


def engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            url = database_url().replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")
            _engine = create_engine(url, future=True, pool_pre_ping=True)
            _init_schema(_engine)
    return _engine


def _init_schema(eng: Engine) -> None:
    pg = eng.dialect.name == "postgresql"
    serial = "BIGSERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with eng.begin() as c:
        c.execute(text(f"""CREATE TABLE IF NOT EXISTS mcp_audit_log (
            id {serial}, ts DOUBLE PRECISION NOT NULL, server TEXT NOT NULL, user_id TEXT NOT NULL, tool TEXT NOT NULL,
            args TEXT, result TEXT, status TEXT, trace_id TEXT)"""))
        c.execute(text("""CREATE TABLE IF NOT EXISTS mcp_idempotency (
            user_id TEXT NOT NULL, tool TEXT NOT NULL, key TEXT NOT NULL, response TEXT NOT NULL, ts DOUBLE PRECISION,
            PRIMARY KEY (user_id, tool, key))"""))
        if pg:
            c.execute(text("""CREATE OR REPLACE FUNCTION mcp_audit_append_only() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'mcp_audit_log is append-only'; END; $$ LANGUAGE plpgsql"""))
            c.execute(text("DROP TRIGGER IF EXISTS mcp_audit_no_update ON mcp_audit_log"))
            c.execute(text("""CREATE TRIGGER mcp_audit_no_update BEFORE UPDATE OR DELETE ON mcp_audit_log
                FOR EACH ROW EXECUTE FUNCTION mcp_audit_append_only()"""))
        else:
            c.execute(text("""CREATE TRIGGER IF NOT EXISTS mcp_audit_no_update BEFORE UPDATE ON mcp_audit_log
                BEGIN SELECT RAISE(ABORT, 'mcp_audit_log is append-only'); END"""))
            c.execute(text("""CREATE TRIGGER IF NOT EXISTS mcp_audit_no_delete BEFORE DELETE ON mcp_audit_log
                BEGIN SELECT RAISE(ABORT, 'mcp_audit_log is append-only'); END"""))


def audit(server: str, caller: Caller, tool: str, args: dict, result: Any, status: str = "ok") -> None:
    payload = json.dumps(mask_obj(result), default=str)[:4000]
    with engine().begin() as c:
        c.execute(text("INSERT INTO mcp_audit_log (ts, server, user_id, tool, args, result, status, trace_id) "
                       "VALUES (:ts, :server, :user, :tool, :args, :result, :status, :trace)"),
                  {"ts": time.time(), "server": server, "user": caller.user_id, "tool": tool,
                   "args": json.dumps(mask_obj(args), default=str)[:4000], "result": payload, "status": status,
                   "trace": caller.trace_id})


def audit_rows(user_id: str | None = None, limit: int = 200, tool: str | None = None) -> list[dict]:
    sql = "SELECT * FROM mcp_audit_log WHERE 1=1"
    params: dict[str, Any] = {"limit": limit}
    if user_id:
        sql += " AND user_id = :user"
        params["user"] = user_id
    if tool:
        sql += " AND tool = :tool"
        params["tool"] = tool
    with engine().begin() as c:
        rows = c.execute(text(sql + " ORDER BY id DESC LIMIT :limit"), params).mappings().all()
    return [dict(r) for r in rows]


def idem_get(user_id: str, tool: str, key: str) -> dict | None:
    with engine().begin() as c:
        row = c.execute(text("SELECT response FROM mcp_idempotency WHERE user_id=:u AND tool=:t AND key=:k"),
                        {"u": user_id, "t": tool, "k": key}).first()
    return json.loads(row[0]) if row else None


def idem_put(user_id: str, tool: str, key: str, response: dict) -> None:
    with engine().begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(text("INSERT INTO mcp_idempotency VALUES (:u,:t,:k,:r,:ts) ON CONFLICT DO NOTHING"),
                      {"u": user_id, "t": tool, "k": key, "r": json.dumps(response, default=str), "ts": time.time()})
        else:
            c.execute(text("INSERT OR IGNORE INTO mcp_idempotency VALUES (:u,:t,:k,:r,:ts)"),
                      {"u": user_id, "t": tool, "k": key, "r": json.dumps(response, default=str), "ts": time.time()})


# --------------------------------------------------------------------------- rate limiting
class RateLimiter:
    """Token bucket per user. Stays under GigSim's limit (config marketplace.max_requests_per_minute)."""

    def __init__(self, per_minute: int) -> None:
        self.rate = per_minute / 60.0
        self.capacity = max(1, per_minute // 4)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._redis = None
        if os.getenv("REDIS_URL"):
            try:
                import redis

                self._redis = redis.Redis.from_url(os.environ["REDIS_URL"])
            except Exception:  # noqa: BLE001
                self._redis = None

    def acquire(self, user_id: str) -> float:
        """Returns seconds to wait (0 = go now). Callers sleep that long - polite, never bursty."""
        if self._redis is not None:
            try:
                key = f"rl:{user_id}:{int(time.time() // 60)}"
                n = self._redis.incr(key)
                self._redis.expire(key, 61)
                return 0.0 if n <= self.rate * 60 else 60 - (time.time() % 60)
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            now = time.monotonic()
            tokens, last = self._buckets.get(user_id, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[user_id] = (tokens - 1, now)
                return 0.0
            wait = (1 - tokens) / self.rate
            self._buckets[user_id] = (tokens - 1, now)
            return wait
