"""GigSim: marketplace simulator REST API.

Built for this project because the starter kit shipped without the instructor's GigSim. It mimics the
behaviour the assignment describes: jobs (Kaggle-derived + synthetic scams/injections/duplicates),
clients with histories and hidden preferences, Connects, proposals, messages, rate limits (429) and
occasional 5xx errors. All state is in a SQLite file so a restart keeps proposals and threads.

Auth: `Authorization: Bearer <GIGSIM_API_TOKEN>` + `X-Freelancer-Id: <persona id>`.
Run:  uvicorn gigsim.app:app --port 8081
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from gigsim import sim
from gigsim.policy import POLICIES, active_version, connects_cost

SEED = Path(__file__).resolve().parent / "seed"
DB_PATH = Path(os.getenv("GIGSIM_DB", str(Path(__file__).resolve().parents[1] / "data" / "processed" / "gigsim.db")))
TOKEN = os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
ADMIN_TOKEN = os.getenv("GIGSIM_ADMIN_TOKEN", "gigsim-admin-token")
RATE_PER_MIN = int(os.getenv("GIGSIM_RATE_PER_MIN", "30"))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))
AUTO_TICK_S = float(os.getenv("GIGSIM_AUTO_TICK_SECONDS", "0"))
TICK_MINUTES = int(os.getenv("GIGSIM_TICK_MINUTES", "30"))
INITIAL_STREAM_MIN = int(os.getenv("GIGSIM_INITIAL_STREAM_MINUTES", "240"))


# --------------------------------------------------------------------------- data
class Data:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        with open(SEED / "jobs.jsonl", encoding="utf-8") as fh:
            for line in fh:
                j = json.loads(line)
                self.jobs[j["job_id"]] = j
        self.clients = {c["client_id"]: c for c in json.loads((SEED / "clients.json").read_text(encoding="utf-8"))}
        self.hidden = json.loads((SEED / "hidden.json").read_text(encoding="utf-8"))
        self.stats = json.loads((SEED / "market_stats.json").read_text(encoding="utf-8"))
        self.freelancers = {f["freelancer_id"]: f for f in json.loads((SEED / "freelancers.json").read_text(encoding="utf-8"))}


DATA = Data()
_lock = threading.RLock()


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


CONN = db()
CONN.executescript(
    """
    CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS connects (freelancer_id TEXT PRIMARY KEY, balance INTEGER, spent INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS proposals (
        proposal_id TEXT PRIMARY KEY, freelancer_id TEXT, job_id TEXT, client_id TEXT, status TEXT,
        cover_letter TEXT, bid_amount REAL, bid_unit TEXT, screening_answers TEXT, connects_cost INTEGER,
        created_min INTEGER, submitted_min INTEGER, decision TEXT, policy_version TEXT);
    CREATE TABLE IF NOT EXISTS threads (thread_id TEXT PRIMARY KEY, proposal_id TEXT, freelancer_id TEXT, job_id TEXT,
        client_id TEXT, stage TEXT, created_min INTEGER);
    CREATE TABLE IF NOT EXISTS messages (message_id TEXT PRIMARY KEY, thread_id TEXT, sender TEXT, text TEXT,
        at_min INTEGER, meta TEXT, processed INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, freelancer_id TEXT, type TEXT,
        proposal_id TEXT, thread_id TEXT, payload TEXT, at_min INTEGER);
    CREATE TABLE IF NOT EXISTS idem (key TEXT, freelancer_id TEXT, endpoint TEXT, response TEXT,
        PRIMARY KEY (key, freelancer_id, endpoint));
    """
)


def kv_get(k: str, default: Any = None) -> Any:
    row = CONN.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(row["v"]) if row else default


def kv_set(k: str, v: Any) -> None:
    CONN.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


def now_min() -> int:
    return int(kv_get("sim_minutes", INITIAL_STREAM_MIN))


def policy() -> dict:
    return POLICIES[active_version(kv_get("policy_version"))]


def ensure_connects(fid: str) -> None:
    if not CONN.execute("SELECT 1 FROM connects WHERE freelancer_id=?", (fid,)).fetchone():
        bal = DATA.freelancers.get(fid, {}).get("connects_balance", 120)
        CONN.execute("INSERT INTO connects(freelancer_id, balance) VALUES(?,?)", (fid, bal))


def event(fid: str, type_: str, proposal_id: str | None = None, thread_id: str | None = None, **payload: Any) -> None:
    CONN.execute("INSERT INTO events(freelancer_id,type,proposal_id,thread_id,payload,at_min) VALUES(?,?,?,?,?,?)",
                 (fid, type_, proposal_id, thread_id, json.dumps(payload), now_min()))


def public_job(j: dict) -> dict:
    out = {k: v for k, v in j.items() if k not in {"release_offset_min", "visibility"}}
    out["connects_cost"] = connects_cost(j, policy())
    return out


# --------------------------------------------------------------------------- auth / limits / faults
_hits: dict[str, deque] = defaultdict(deque)


async def caller(request: Request, authorization: str = Header(""), x_freelancer_id: str = Header("")) -> str:
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    fid = x_freelancer_id or "ai_ml_engineer"
    if fid not in DATA.freelancers:
        raise HTTPException(403, f"unknown freelancer {fid}")
    q = _hits[fid]
    t = time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MIN:
        retry = max(1, int(60 - (t - q[0])) + 1)
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(retry)})
    q.append(t)
    if kv_get("outage", False):
        raise HTTPException(503, "marketplace outage (simulated)")
    if ERROR_RATE and random.random() < ERROR_RATE:
        raise HTTPException(503, "transient upstream error (simulated)")
    with _lock:
        ensure_connects(fid)
    return fid


def admin(x_admin_token: str = Header("")) -> None:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")


def idem_lookup(key: str | None, fid: str, endpoint: str) -> dict | None:
    if not key:
        return None
    row = CONN.execute("SELECT response FROM idem WHERE key=? AND freelancer_id=? AND endpoint=?", (key, fid, endpoint)).fetchone()
    return json.loads(row["response"]) if row else None


def idem_store(key: str | None, fid: str, endpoint: str, resp: dict) -> None:
    if key:
        CONN.execute("INSERT OR IGNORE INTO idem(key,freelancer_id,endpoint,response) VALUES(?,?,?,?)", (key, fid, endpoint, json.dumps(resp)))


# --------------------------------------------------------------------------- simulation clock
def tick(minutes: int = TICK_MINUTES) -> dict:
    with _lock:
        t = now_min() + minutes
        kv_set("sim_minutes", t)
        processed = 0
        # client decisions on submitted proposals (after 30-60 simulated minutes)
        for p in CONN.execute("SELECT * FROM proposals WHERE status='submitted' AND submitted_min <= ?", (t - 30,)).fetchall():
            job = DATA.jobs[p["job_id"]]
            hidden = DATA.hidden.get(p["job_id"], {})
            d = sim.decide(job, hidden, dict(p))
            CONN.execute("UPDATE proposals SET status=?, decision=? WHERE proposal_id=?",
                         ("replied" if d["replied"] else ("viewed" if d["viewed"] else "unseen"), json.dumps(d), p["proposal_id"]))
            if d["viewed"]:
                event(p["freelancer_id"], "proposal_viewed", p["proposal_id"])
            if d["replied"]:
                tid = "th_" + p["proposal_id"][3:]
                CONN.execute("INSERT OR IGNORE INTO threads VALUES(?,?,?,?,?,?,?)",
                             (tid, p["proposal_id"], p["freelancer_id"], p["job_id"], p["client_id"], "replied", t))
                msg = sim.client_message(d["intent"], job, dict(p), p["proposal_id"])
                CONN.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,1)",
                             ("m_" + uuid.uuid4().hex[:10], tid, "client", msg, t, json.dumps({"intent": d["intent"]})))
                event(p["freelancer_id"], "client_replied", p["proposal_id"], tid, intent=d["intent"])
            processed += 1
        # client responses to freelancer messages
        for m in CONN.execute("SELECT m.*, th.proposal_id, th.freelancer_id, th.job_id FROM messages m JOIN threads th "
                              "ON m.thread_id=th.thread_id WHERE m.sender='freelancer' AND m.processed=0 AND m.at_min <= ?",
                              (t - 30,)).fetchall():
            meta = json.loads(m["meta"] or "{}")
            p = CONN.execute("SELECT * FROM proposals WHERE proposal_id=?", (m["proposal_id"],)).fetchone()
            job = DATA.jobs[m["job_id"]]
            d = json.loads(p["decision"] or "{}")
            f = d.get("features", {})
            if DATA.hidden.get(m["job_id"], {}).get("scam"):
                reply = "Why are you not answering on Telegram? Last chance."
                stage = "lost"
            elif meta.get("slots"):
                reply = sim.client_message("after_slots", job, dict(p), m["message_id"], slot=meta["slots"][0]["start"])
                stage = "interview"
                event(m["freelancer_id"], "interview_scheduled", m["proposal_id"], m["thread_id"], slot=meta["slots"][0])
            else:
                reply = sim.client_message("after_answer", job, dict(p), m["message_id"])
                stage = "replied"
            CONN.execute("UPDATE messages SET processed=1 WHERE message_id=?", (m["message_id"],))
            CONN.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,1)", ("m_" + uuid.uuid4().hex[:10], m["thread_id"], "client", reply, t, "{}"))
            CONN.execute("UPDATE threads SET stage=? WHERE thread_id=?", (stage, m["thread_id"]))
            event(m["freelancer_id"], "message", m["proposal_id"], m["thread_id"])
            if stage in {"interview", "replied"}:
                rng = sim._rng(m["message_id"], "hire")
                if rng.random() < sim.hire_probability(f, stage == "interview") * 0.5:
                    CONN.execute("UPDATE threads SET stage='hired' WHERE thread_id=?", (m["thread_id"],))
                    CONN.execute("UPDATE proposals SET status='hired' WHERE proposal_id=?", (m["proposal_id"],))
                    event(m["freelancer_id"], "hired", m["proposal_id"], m["thread_id"])
            processed += 1
        return {"sim_minutes": t, "processed": processed}


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if AUTO_TICK_S > 0:
        async def loop() -> None:
            while True:
                await asyncio.sleep(AUTO_TICK_S)
                await asyncio.to_thread(tick)
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="GigSim marketplace simulator", version="1.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"error": exc.detail, "status": exc.status_code}, status_code=exc.status_code, headers=exc.headers)


@app.get("/health")
def health() -> JSONResponse:
    body = {"status": "ok", "sim_minutes": now_min(), "policy_version": policy()["version"], "jobs": len(DATA.jobs)}
    if kv_get("outage", False):
        return JSONResponse({**body, "status": "outage"}, status_code=503)
    return JSONResponse(body)


# --------------------------------------------------------------------------- read API
@app.get("/v1/jobs/search")
def search_jobs(
    fid: str = Depends(caller), q: str = "", category: str | None = None, skills: str | None = None,
    min_budget: float | None = None, since_minutes: int | None = None, limit: int = Query(20, le=50),
) -> dict:
    t = now_min()
    terms = [w for w in q.lower().split() if w]
    want = {s.strip().lower() for s in (skills or "").split(",") if s.strip()}
    out = []
    for j in DATA.jobs.values():
        if j["visibility"] != "stream" or j["release_offset_min"] > t:
            continue
        if since_minutes is not None and j["release_offset_min"] < t - since_minutes:
            continue
        if category and j.get("category") != category:
            continue
        if min_budget and (j.get("budget") or 0) < min_budget and not j.get("is_hourly"):
            continue
        blob = (j["title"] + " " + j["description"] + " " + " ".join(j.get("skills", []))).lower()
        if terms and not any(w in blob for w in terms):
            continue
        if want and not want & {s.lower() for s in j.get("skills", [])}:
            continue
        out.append(j)
    out.sort(key=lambda j: -j["release_offset_min"])
    return {"jobs": [public_job(j) for j in out[:limit]], "total": len(out), "sim_minutes": t}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, fid: str = Depends(caller)) -> dict:
    j = DATA.jobs.get(job_id)
    if not j or (j["visibility"] == "stream" and j["release_offset_min"] > now_min()):
        raise HTTPException(404, "job not found")
    return public_job(j)


@app.get("/v1/clients/{client_id}")
def client_history(client_id: str, fid: str = Depends(caller)) -> dict:
    c = DATA.clients.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return c


@app.get("/v1/market/stats")
def market_stats(category: str = "other", fid: str = Depends(caller)) -> dict:
    cats = DATA.stats["categories"]
    return {"category": category, **(cats.get(category) or cats.get("other", {})), "sources": DATA.stats["sources"]}


@app.get("/v1/connects")
def connects(fid: str = Depends(caller)) -> dict:
    row = CONN.execute("SELECT * FROM connects WHERE freelancer_id=?", (fid,)).fetchone()
    return {"freelancer_id": fid, "balance": row["balance"], "spent": row["spent"],
            "weekly_allowance": DATA.freelancers[fid]["weekly_connects"]}


@app.get("/v1/policy")
def get_policy(fid: str = Depends(caller)) -> dict:
    return policy()


@app.get("/v1/proposals")
def list_proposals(fid: str = Depends(caller), status: str | None = None) -> dict:
    sql, args = "SELECT * FROM proposals WHERE freelancer_id=?", [fid]
    if status:
        sql += " AND status=?"
        args.append(status)
    rows = [dict(r) | {"decision": None} for r in CONN.execute(sql + " ORDER BY created_min DESC", args).fetchall()]
    return {"proposals": rows}


@app.get("/v1/threads")
def list_threads(fid: str = Depends(caller)) -> dict:
    rows = CONN.execute("SELECT * FROM threads WHERE freelancer_id=? ORDER BY created_min DESC", (fid,)).fetchall()
    return {"threads": [dict(r) for r in rows]}


@app.get("/v1/threads/{thread_id}/messages")
def list_messages(thread_id: str, fid: str = Depends(caller)) -> dict:
    th = CONN.execute("SELECT * FROM threads WHERE thread_id=? AND freelancer_id=?", (thread_id, fid)).fetchone()
    if not th:
        raise HTTPException(404, "thread not found")
    msgs = [dict(m) | {"meta": json.loads(m["meta"] or "{}")} for m in
            CONN.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY at_min, rowid", (thread_id,)).fetchall()]
    return {"thread": dict(th), "messages": msgs}


@app.get("/v1/events")
def events(fid: str = Depends(caller), since: int = 0, limit: int = Query(100, le=500)) -> dict:
    rows = CONN.execute("SELECT * FROM events WHERE freelancer_id=? AND seq>? ORDER BY seq LIMIT ?", (fid, since, limit)).fetchall()
    return {"events": [dict(r) | {"payload": json.loads(r["payload"] or "{}")} for r in rows]}


# --------------------------------------------------------------------------- write API
@app.post("/v1/proposals")
def create_proposal(body: dict = Body(...), fid: str = Depends(caller)) -> dict:
    key = body.get("idempotency_key")
    if (hit := idem_lookup(key, fid, "create_proposal")) is not None:
        return hit | {"idempotent_replay": True}
    job = DATA.jobs.get(body.get("job_id", ""))
    if not job:
        raise HTTPException(404, "job not found")
    if not (body.get("cover_letter") or "").strip():
        raise HTTPException(422, "cover_letter required")
    with _lock:
        pid = "pr_" + uuid.uuid4().hex[:12]
        cost = connects_cost(job, policy())
        CONN.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pid, fid, job["job_id"], job["client_id"], "draft", body["cover_letter"], float(body.get("bid_amount") or 0),
                      body.get("bid_unit", "fixed"), json.dumps(body.get("screening_answers", [])), cost, now_min(), None, None,
                      policy()["version"]))
        resp = {"proposal_id": pid, "status": "draft", "connects_cost": cost, "job_id": job["job_id"]}
        idem_store(key, fid, "create_proposal", resp)
    return resp


@app.post("/v1/proposals/{proposal_id}/submit")
def submit_proposal(proposal_id: str, body: dict = Body(default={}), fid: str = Depends(caller)) -> dict:
    key = body.get("idempotency_key")
    if (hit := idem_lookup(key, fid, "submit")) is not None:
        return hit | {"idempotent_replay": True}
    with _lock:
        p = CONN.execute("SELECT * FROM proposals WHERE proposal_id=? AND freelancer_id=?", (proposal_id, fid)).fetchone()
        if not p:
            raise HTTPException(404, "proposal not found")
        if p["status"] != "draft":
            resp = {"proposal_id": proposal_id, "status": p["status"], "connects_spent": 0, "note": "already submitted"}
            idem_store(key, fid, "submit", resp)
            return resp
        pol = policy()
        missing = [d for d in pol["required_disclosures"] if d.lower() not in (p["cover_letter"] or "").lower()]
        if missing:
            raise HTTPException(422, f"policy_violation: missing required disclosure {missing[0]!r} (policy {pol['version']})")
        job = DATA.jobs[p["job_id"]]
        cost = connects_cost(job, pol)
        bal = CONN.execute("SELECT balance FROM connects WHERE freelancer_id=?", (fid,)).fetchone()["balance"]
        if bal < cost:
            raise HTTPException(402, f"insufficient connects: need {cost}, have {bal}")
        CONN.execute("UPDATE connects SET balance=balance-?, spent=spent+? WHERE freelancer_id=?", (cost, cost, fid))
        CONN.execute("UPDATE proposals SET status='submitted', submitted_min=?, connects_cost=? WHERE proposal_id=?",
                     (now_min(), cost, proposal_id))
        event(fid, "proposal_submitted", proposal_id)
        resp = {"proposal_id": proposal_id, "status": "submitted", "connects_spent": cost, "balance": bal - cost}
        idem_store(key, fid, "submit", resp)
    return resp


@app.post("/v1/threads/{thread_id}/messages")
def send_message(thread_id: str, body: dict = Body(...), fid: str = Depends(caller)) -> dict:
    key = body.get("idempotency_key")
    if (hit := idem_lookup(key, fid, f"msg:{thread_id}")) is not None:
        return hit | {"idempotent_replay": True}
    th = CONN.execute("SELECT * FROM threads WHERE thread_id=? AND freelancer_id=?", (thread_id, fid)).fetchone()
    if not th:
        raise HTTPException(404, "thread not found")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "text required")
    with _lock:
        mid = "m_" + uuid.uuid4().hex[:10]
        CONN.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,0)",
                     (mid, thread_id, "freelancer", text, now_min(), json.dumps({"slots": body.get("slots") or []})))
        resp = {"message_id": mid, "thread_id": thread_id, "status": "sent"}
        idem_store(key, fid, f"msg:{thread_id}", resp)
    return resp


# --------------------------------------------------------------------------- admin
@app.post("/admin/tick", dependencies=[Depends(admin)])
def admin_tick(minutes: int = TICK_MINUTES) -> dict:
    return tick(minutes)


@app.post("/admin/policy", dependencies=[Depends(admin)])
def admin_policy(version: str = Body(..., embed=True)) -> dict:
    if version not in POLICIES:
        raise HTTPException(404, "unknown policy version")
    kv_set("policy_version", version)
    return POLICIES[version]


@app.post("/admin/outage", dependencies=[Depends(admin)])
def admin_outage(down: bool = Body(..., embed=True)) -> dict:
    """Simulate the marketplace going down (viva question 1 / Playwright degraded-mode test)."""
    kv_set("outage", bool(down))
    return {"outage": bool(down)}


@app.post("/admin/reset", dependencies=[Depends(admin)])
def admin_reset() -> dict:
    with _lock:
        for t in ("proposals", "threads", "messages", "events", "idem", "connects", "kv"):
            CONN.execute(f"DELETE FROM {t}")
    return {"status": "reset"}


@app.get("/admin/outcomes", dependencies=[Depends(admin)])
def admin_outcomes(freelancer_id: str | None = None) -> dict:
    sql, args = "SELECT proposal_id, freelancer_id, job_id, status, decision FROM proposals WHERE status!='draft'", []
    if freelancer_id:
        sql += " AND freelancer_id=?"
        args.append(freelancer_id)
    rows = [dict(r) | {"decision": json.loads(r["decision"] or "null")} for r in CONN.execute(sql, args).fetchall()]
    return {"proposals": rows}
