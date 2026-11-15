# Runbook

## Run it

| How | Command | What runs |
|---|---|---|
| Laptop, no Docker | `python -m scripts.dev --reset --web` | GigSim :8081, API :8000 (inline worker, in-process MCP servers, SQLite), web :3000 |
| Full stack | `cp .env.example .env` then `cd infra && docker compose --env-file ../.env up --build` | web, api, worker (Arq), 3 MCP servers (HTTP), GigSim, Postgres, Redis, Qdrant |
| + local models | `docker compose --profile local-llm up` | adds Ollama with qwen3:1.7b / qwen3:4b (`MODEL_PROFILE=open_local`) |
| + HTTPS | `DOMAIN=gigbid.example.org docker compose --profile prod up -d` | adds Caddy with automatic TLS |
| One container (free hosts) | `docker build -f infra/docker/allinone.Dockerfile -t gigbid .` | everything on :7860 (Render free web service via `render.yaml`; any Docker host) |

Reviewer account: `python -m scripts.seed` (or `SEED_ON_START=1`) with `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` from the
environment. Credentials go only in the private Google Classroom comment.

## Models
`MODEL_PROFILE=open` (deployment) needs `GROQ_API_KEY` (free tier) and optionally `OPENROUTER_API_KEY` as the fallback.
`open_local` / `open_small` use Ollama. `test` is deterministic and offline (CI, Playwright, no-key demo).
Every node's model is set in `agent/config.yaml`.

## Deploy (keep it live until grades are released)
1. A VM with Docker (DigitalOcean / Azure student credit, or Oracle Always Free ARM), ports 80/443 open.
2. `git clone`, create `.env` from `.env.example` (generate `APP_SECRET_KEY`, `MCP_JWT_SECRET`,
   `TOKEN_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
3. `cd infra && DOMAIN=<your domain> docker compose --env-file ../.env --profile prod up -d --build`.
4. Point a DNS name (DuckDNS works) at the VM; Caddy gets the certificate.
5. Add an UptimeRobot monitor on `https://<domain>/api/health`.
Free alternative without a VM (no payment method): `render.yaml` deploys `allinone.Dockerfile` as one free Render web
service (Render -> New -> Blueprint -> this repo; it asks for `GROQ_API_KEY` and `REVIEWER_PASSWORD` and generates the
other secrets). Free instances have 512 MB RAM and 0.1 CPU, sleep after 15 idle minutes (an UptimeRobot ping on
`/api/health` every 5 min keeps one service awake within the 750 free hours) and reset their disk on restart (the reviewer
account and demo data are re-seeded on start). Hugging Face Docker Spaces stopped being free in July 2026.

## Scheduling and rate limits (E1, A4)
* Each saved search runs on its own interval (default 30 simulated-minutes in GigSim). The worker's `scout_tick`
  cron checks due searches every minute; `sync_tick` pulls marketplace events every 30 s.
* Our per-user token bucket allows 20 requests/min to the marketplace; GigSim's own limit is 30/min, so we stay
  under it and back off on `429 Retry-After`.
* **Live Upwork mode: saved searches run at most every 120 minutes** (`scheduler.live_interval_minutes`). Why:
  a freelancer realistically reviews new jobs a few times a day; 12 searches/day x a handful of saved searches is
  well inside what a human clicking "search" would do, never looks like scraping, and leaves Upwork's API quota for
  the user's own usage. Reads only; proposals/messages are created as drafts after approval and confirmed by the
  user on Upwork. No browser automation, no cookies, no scraping.

## Degraded mode (viva question 1)
* Simulate: `curl -X POST -H "X-Admin-Token: $GIGSIM_ADMIN_TOKEN" -H 'content-type: application/json' -d '{"down": true}' localhost:8081/admin/outage`
  (or `docker compose stop mcp-marketplace` / `stop gigsim`).
* What the user sees: the "Marketplace unavailable" banner (polls `/api/health/dependencies` every 15 s and
  listens for `degraded` events on the SSE stream).
* Code: `agent/mcp_client.py` (`probe`, `mark_health`, `ToolUnavailable`), `agent/nodes/common.py`
  (`MarketplaceDown` stops the run at its last checkpoint), `worker/runner.py` (`RETRY_BACKOFF_S`, run status
  `waiting_marketplace`), `apps/web/src/components/DegradedBanner.tsx`.
* Recover: `{"down": false}`; the next retry resumes each parked thread from its checkpoint.

## Crash and resume, exactly once (viva question 2)
1. Approve a draft in the Proposal studio, then immediately `docker compose kill worker` (or kill the API in
   inline mode).
2. `docker compose up -d worker`. The job is still `awaiting_approval` / `resuming`; approve again if the decision
   was lost with the process, or the worker resumes the thread from its checkpoint.
3. Proof: `SELECT tool, count(*) FROM mcp_audit_log WHERE tool='submit_proposal' GROUP BY tool;` and GigSim
   `GET /admin/outcomes` show one submission; the second `submit_proposal` (if any) returns `idempotent_replay: true`.
   Covered by `tests/integration/test_graphs.py::test_bid_interrupts_then_crash_resume_submits_exactly_once`.

## Change request (policy update)
`curl -X POST -H "X-Admin-Token: ..." -d '{"version":"2026-11-02"}' localhost:8081/admin/policy` switches GigSim to the
updated policy. GigBid absorbs it through `agent/config.yaml` -> `bidding_rules` (see docs/adr/0008-change-request.md).

## Secrets
Only from environment variables (`.env`, never committed; CI runs gitleaks). OAuth tokens are Fernet-encrypted in
the `secrets` table and never logged; logs and traces are PII-masked (`agent/safety.py::mask_pii`).

## Backups
`docker compose exec postgres pg_dump -U gigbid gigbid > backup.sql` (checkpoints, memory, audit log, app data).
