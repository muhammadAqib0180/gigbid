"""Local dev launcher without Docker: GigSim + API (inline worker, in-process MCP servers) [+ web].

    python -m scripts.dev            # gigsim :8081, api :8000
    python -m scripts.dev --web      # also `npm run dev` in apps/web (:3000)
    python -m scripts.dev --reset    # wipe local SQLite state first and reseed the reviewer

Docker compose (infra/docker-compose.yml) runs the same services as separate containers with Postgres,
Redis, Qdrant, the Arq worker and HTTP MCP servers.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--profile", default=os.getenv("MODEL_PROFILE", "test"))
    ns = ap.parse_args()
    proc = ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    if ns.reset:
        for pat in ("gigbid.db*", "checkpoints.sqlite*", "memory_store.sqlite*", "mcp.db*", "gigsim.db*"):
            for f in proc.glob(pat):
                f.unlink()
    env = {**os.environ, "MODEL_PROFILE": ns.profile, "GIGBID_MCP_INPROCESS": "1", "PYTHONIOENCODING": "utf-8",
           "GIGSIM_BASE_URL": "http://localhost:8081", "GIGSIM_AUTO_TICK_SECONDS": os.getenv("GIGSIM_AUTO_TICK_SECONDS", "60"),
           "GIGSIM_ERROR_RATE": os.getenv("GIGSIM_ERROR_RATE", "0.02"), "SCHEDULER_TICK_SECONDS": "30",
           "REVIEWER_PASSWORD": os.getenv("REVIEWER_PASSWORD", "review-local-only"), "SEED_ON_START": "1"}
    procs = [
        subprocess.Popen([PY, "-m", "uvicorn", "gigsim.app:app", "--port", "8081", "--log-level", "warning"], cwd=ROOT, env=env),
        subprocess.Popen([PY, "-m", "uvicorn", "apps.api.main:app", "--port", "8000", "--log-level", "warning"], cwd=ROOT, env=env),
    ]
    if ns.web:
        npm = shutil.which("npm") or "npm"
        procs.append(subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "apps" / "web", env={**env, "API_URL": "http://localhost:8000"},
                                      shell=os.name == "nt"))
    print("GigSim http://localhost:8081  API http://localhost:8000/docs" + ("  Web http://localhost:3000" if ns.web else ""))
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM if os.name != "nt" else signal.CTRL_BREAK_EVENT) if False else p.terminate()


if __name__ == "__main__":
    main()
