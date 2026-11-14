"""Entry point of the single-container image (infra/docker/allinone.Dockerfile): GigSim + API (inline worker,
in-process MCP servers) + Next.js standalone server on $PORT. Restarts a child if it dies."""

from __future__ import annotations

import os
import subprocess
import sys
import time

PORT = os.getenv("PORT", "7860")


def spawn(name: str) -> subprocess.Popen:
    if name == "gigsim":
        cmd = [sys.executable, "-m", "uvicorn", "gigsim.app:app", "--host", "127.0.0.1", "--port", "8081", "--log-level", "warning"]
    elif name == "api":
        cmd = [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"]
    else:
        cmd = ["node", "server.js"]
    env = {**os.environ, "PORT": PORT if name == "web" else os.environ.get("PORT", ""), "HOSTNAME": "0.0.0.0"}
    return subprocess.Popen(cmd, cwd="/app/web" if name == "web" else "/app", env=env)


def main() -> None:
    procs = {n: spawn(n) for n in ("gigsim", "api", "web")}
    print(f"GigBid all-in-one on :{PORT}", flush=True)
    while True:
        time.sleep(5)
        for n, p in list(procs.items()):
            if p.poll() is not None:
                print(f"{n} exited ({p.returncode}); restarting", flush=True)
                procs[n] = spawn(n)


if __name__ == "__main__":
    main()
