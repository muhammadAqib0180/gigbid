# Submission checklist (one Google Classroom submission)

Everything below that needs **your** accounts or your own judgement is marked YOU. The repository already contains
the code, data, results and documents.

| # | Deliverable | Status / where | Action |
|---|---|---|---|
| 1 | Public GitHub repo `gigbid` | local repo `D:\AAI2\gigbid` with full commit history | YOU: create an empty public repo named `gigbid`, then `git remote add origin https://github.com/<you>/gigbid.git && git push -u origin main` |
| 2 | Deployed URL (live until grades) | `infra/docker-compose.yml` (VM) or `infra/docker/allinone.Dockerfile` (Hugging Face Space) - see docs/RUNBOOK.md | YOU: deploy, set secrets (`GROQ_API_KEY`, `APP_SECRET_KEY`, `MCP_JWT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `REVIEWER_PASSWORD`), add an UptimeRobot monitor |
| 3 | Reviewer login | seeded on start from `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` | YOU: put them ONLY in the private Classroom comment |
| 4 | R&D report PDF | `report/GigBid_RD_Report.pdf` (source `report/REPORT.md`) | YOU: read it, fill the 3 trace links and the hidden-test paragraph after grading runs |
| 5 | 3-minute demo video | script in `report/DEMO_SCRIPT.md` | YOU: record (OBS), upload unlisted, check it opens in a private window |
| 6 | Portfolio MCP server published | package `mcp_servers/portfolio` (name `portfolio-evidence-mcp`, wheel builds) | YOU: `uv build mcp_servers/portfolio && uv publish` with your PyPI token (or tag `portfolio-mcp-v0.1.0` to use the trusted-publishing workflow) |
| 7 | Technical write-up (1,200-1,800 words) | draft `report/WRITEUP.md` | YOU: edit in your own voice, publish on Medium / LinkedIn / blog |
| 8 | ZIP of source | `git archive --format=zip -o gigbid.zip HEAD` | YOU: run after the final commit |
| 9 | LangSmith public traces (README) | tracing is wired; needs `LANGSMITH_API_KEY` | YOU: run one scam, one approved proposal, one crash-resume with tracing on; share the three traces |
| 10 | Judge calibration (30 human labels) | `evals/datasets/judge_labels.csv` exported | YOU: fill `human_score` (1-5), then `python -m evals.runners.judge_calibration run --profile open` |
| 11 | Blind pairwise human panel | not run (needs classmates) | YOU (optional): ask 3 classmates to rate anonymised pairs from `evals/results/outcomes_*_proposals.csv` |
| 12 | Upwork live mode | adapter + OAuth flow implemented, unit-tested against a fake server | YOU (only if you have an Upwork account): Settings -> Connect Upwork |

Before submitting: `uv run pytest -q`, `cd apps/web && npm run build`, `python -m scripts.render_results --check`,
`python -m scripts.gigsim_manifest --check` all pass; `.env` is not committed (`git ls-files .env` prints nothing).
