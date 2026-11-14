"""Shared evaluation helpers: dataset loading, metrics, in-process GigSim, result files with provenance."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
PERSONAS = ["ai_ml_engineer", "fullstack_web", "data_analyst"]


def setup_env(profile: str | None = None) -> None:
    """Isolated SQLite files + in-process MCP; GigSim served in-process (no ports)."""
    tmp = Path(tempfile.mkdtemp(prefix="gigbid-eval-"))
    os.environ.setdefault("MODEL_PROFILE", profile or os.getenv("MODEL_PROFILE", "test"))
    if profile:
        os.environ["MODEL_PROFILE"] = profile
    os.environ["GIGBID_MCP_INPROCESS"] = "1"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp / 'app.db').as_posix()}"
    os.environ["MCP_DATABASE_URL"] = f"sqlite:///{(tmp / 'mcp.db').as_posix()}"
    os.environ["GIGSIM_DB"] = str(tmp / "gigsim.db")
    os.environ["GIGSIM_ERROR_RATE"] = os.getenv("EVAL_GIGSIM_ERROR_RATE", "0")
    os.environ["GIGSIM_RATE_PER_MIN"] = "1000000"
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
    import httpx

    from gigsim.app import app as gigsim_app
    from mcp_servers.marketplace import adapters as adapters_mod
    from mcp_servers.marketplace import server as server_mod
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

    def patched(user_id: str, persona: str, mode: str | None = None):
        return GigSimAdapter(freelancer_id=persona, base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim_app))

    adapters_mod.get_adapter = patched
    server_mod.get_adapter = patched


def load_dev(persona: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / f"dev_{persona}.jsonl").read_text(encoding="utf-8").splitlines()]


_JOBS: dict[str, dict] | None = None


def jobs_by_id() -> dict[str, dict]:
    global _JOBS
    if _JOBS is None:
        _JOBS = {}
        with open(ROOT / "gigsim" / "seed" / "jobs.jsonl", encoding="utf-8") as fh:
            for line in fh:
                j = json.loads(line)
                _JOBS[j["job_id"]] = j
    return _JOBS


def public_job(j: dict) -> dict:
    from gigsim.policy import POLICIES, connects_cost

    out = {k: v for k, v in j.items() if k not in {"release_offset_min", "visibility"}}
    out["connects_cost"] = connects_cost(j, POLICIES["2026-10"])
    return out


def sample(rows: list[dict], n: int | None, seed: int = 7) -> list[dict]:
    if not n or n >= len(rows):
        return rows
    r = random.Random(seed)
    rows = list(rows)
    r.shuffle(rows)
    return rows[:n]


# ----------------------------------------------------------------------------- metrics
def recall_at(ranked: list[str], gold: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(gold)) / len(gold) if gold else 0.0


def mrr(ranked: list[str], gold: list[str]) -> float:
    for i, p in enumerate(ranked):
        if p in gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(ranked: list[str], gold: list[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, p in enumerate(ranked[:k]) if p in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return dcg / idcg if idcg else 0.0


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(math.ceil(q * len(xs))) - 1)], 4)


def mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def cohen_kappa(a: list[int], b: list[int], weights: str | None = None) -> float:
    cats = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return 0.0
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    ra = [sum(row) for row in obs]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    def w(i: int, j: int) -> float:
        if weights == "quadratic":
            return ((i - j) ** 2) / ((k - 1) ** 2) if k > 1 else 0.0
        return 0.0 if i == j else 1.0

    po = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * ra[i] * rb[j] for i in range(k) for j in range(k)) / (n * n)
    return round(1 - po / pe, 4) if pe else 1.0


# ----------------------------------------------------------------------------- results
def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def save(name: str, payload: dict[str, Any]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    from agent.llm import active_profile
    from agent.settings import cfg

    meta = {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "git_sha": git_sha(),
            "model_profile": active_profile(), "embedding_model": cfg("embeddings.model"), "reranker": cfg("reranker.model"),
            "command": " ".join(os.sys.argv)}
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps({"meta": meta, **payload}, indent=2, default=str), encoding="utf-8")
    print(f"wrote {path}")
    return path
