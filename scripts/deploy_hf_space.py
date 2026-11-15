"""Deploy GigBid to a free Hugging Face Docker Space (CPU basic, no card needed) in one command.

    hf auth login                                  # once; paste a *write* token from huggingface.co/settings/tokens
    python -m scripts.deploy_hf_space              # creates/updates https://huggingface.co/spaces/<you>/gigbid

What it does:
1. Copies only the git-tracked files the image needs into dist/hf_space/ (never .env, data/raw or anything untracked),
   with infra/docker/allinone.Dockerfile as the Space's Dockerfile and a README carrying the Space header.
2. Creates the public Space (sdk=docker) if it does not exist.
3. On first creation (or with --secrets) stores the secrets in the Space settings: GROQ_API_KEY and REVIEWER_PASSWORD
   are read from the environment / your local .env or asked for (input hidden); APP_SECRET_KEY, MCP_JWT_SECRET,
   TOKEN_ENCRYPTION_KEY and GIGSIM_ADMIN_TOKEN are generated. Nothing secret is written to disk or printed.
4. Uploads the folder; Hugging Face builds the image (~10-15 min) and serves it at https://<you>-gigbid.hf.space.

Options: --name gigbid, --dry-run (build the folder only), --secrets (set secrets again, e.g. a new Groq key).
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "dist" / "hf_space"
NEEDED = ["pyproject.toml", "uv.lock", "apps/__init__.py", "apps/api", "apps/web", "agent", "rag", "mcp_servers", "gigsim",
          "worker", "scripts", "evals", "data/personas", "data/policy_pack"]
SKIP_PARTS = {"node_modules", ".next", "test-results", "playwright-report", "__pycache__"}

SPACE_README = """---
title: GigBid
emoji: 📝
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent freelancer copilot with human approval
---

GigBid - a LangGraph multi-agent freelancer copilot that never sends without you. Runs against GigSim, a marketplace
simulator built from real Upwork job posts. Source, report and evaluation: see the GitHub repository.
"""


def read_dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def value(name: str, dotenv: dict[str, str], prompt: str) -> str:
    v = os.getenv(name) or dotenv.get(name, "")
    if v:
        print(f"{name}: using the value from your environment / .env")
    while not v:
        v = getpass.getpass(f"{prompt} (input hidden): ").strip()
    return v


def build_stage() -> int:
    files = subprocess.run(["git", "ls-files", "--", *NEEDED], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    n = 0
    for f in filter(None, files):
        if SKIP_PARTS & set(Path(f).parts) or not (ROOT / f).is_file():
            continue
        dst = STAGE / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dst)
        n += 1
    shutil.copy2(ROOT / "infra" / "docker" / "allinone.Dockerfile", STAGE / "Dockerfile")
    (STAGE / "README.md").write_text(SPACE_README, encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="gigbid")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--secrets", action="store_true", help="(re)set the Space secrets")
    args = ap.parse_args()

    n = build_stage()
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file()) / 1e6
    print(f"staged {n} files ({size:.1f} MB) in {STAGE}")
    if args.dry_run:
        return

    from huggingface_hub import HfApi

    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{args.name}"
    is_new = not api.repo_exists(repo_id, repo_type="space")
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    print(("created" if is_new else "updating"), f"https://huggingface.co/spaces/{repo_id}")

    if is_new or args.secrets:
        dotenv = read_dotenv()
        groq = value("GROQ_API_KEY", dotenv, "Groq API key (free at console.groq.com/keys)")
        reviewer_pw = value("REVIEWER_PASSWORD", dotenv, "Password for the reviewer login (you will share it privately)")
        from cryptography.fernet import Fernet

        for k, v in {"GROQ_API_KEY": groq, "REVIEWER_PASSWORD": reviewer_pw,
                     "APP_SECRET_KEY": secrets.token_urlsafe(32), "MCP_JWT_SECRET": secrets.token_urlsafe(32),
                     "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                     "GIGSIM_ADMIN_TOKEN": secrets.token_urlsafe(24)}.items():
            api.add_space_secret(repo_id, k, v)
        print("secrets set (GROQ_API_KEY, REVIEWER_PASSWORD, APP_SECRET_KEY, MCP_JWT_SECRET, TOKEN_ENCRYPTION_KEY, GIGSIM_ADMIN_TOKEN)")
        host = f"https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space"
        reviewer_email = os.getenv("REVIEWER_EMAIL") or dotenv.get("REVIEWER_EMAIL") or "reviewer@gigbid.app"
        for k, v in {"COOKIE_SECURE": "1", "APP_ENV": "production", "MODEL_PROFILE": "open", "REVIEWER_EMAIL": reviewer_email,
                     "WEB_URL": host, "CORS_ORIGINS": host, "ALLOW_SIGNUP": "0"}.items():
            api.add_space_variable(repo_id, k, v)

    api.upload_folder(folder_path=str(STAGE), repo_id=repo_id, repo_type="space",
                      commit_message="Deploy GigBid")
    host = f"https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space"
    print(f"uploaded. Build log: https://huggingface.co/spaces/{repo_id}?logs=build")
    print(f"when it says Running, open {host} and log in as the reviewer; health check: {host}/api/health")


if __name__ == "__main__":
    main()
