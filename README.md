# GigBid - a multi-agent freelancer copilot that never sends without you

![demo](docs/images/demo.gif)

**Live:** [gigbid-55p9.onrender.com](https://gigbid-55p9.onrender.com) (reviewer login in the private submission comment; free tier, the first visit after a quiet spell takes ~1 min to wake) ·
**Demo video (3 min):** `<link>` · **Write-up:** `<link>` · **Portfolio MCP server:** [`portfolio-evidence-mcp` on PyPI](https://pypi.org/project/portfolio-evidence-mcp/) (`uvx portfolio-evidence-mcp --corpus ./my-portfolio`)

GigBid is a team of LangGraph agents that scouts freelance jobs, checks them for scams and prompt injections,
proves fit with **evidence from your own portfolio**, prices the bid, drafts a proposal in which every claim is
verified against that evidence, and then **stops and waits for you**. Nothing - no proposal, message or Connects
spend - leaves the system until a human approves it in the UI. It runs against GigSim (a marketplace simulator built
from 60k real Upwork job posts) and, through the same port, the official Upwork MCP server (drafts only).

## Why it is built this way
* **Evidence, not vibes.** The Fit Matcher maps each requirement to portfolio items; the verifier removes any claim the
  evidence does not support *before* the Critic or the human sees it. Hover any claim in the studio to see its source.
* **Cheap where it can be, smart where it must be.** Risk floors, the bid decision, pricing, compliance and claim
  grounding are rules + embeddings; only the Writer and Critic need the large open model.
* **Durable human-in-the-loop.** `interrupt()` + a Postgres checkpointer: kill the server while a draft waits for approval,
  restart, approve - it is submitted exactly once (idempotency keys end to end).

## Architecture

```mermaid
flowchart LR
  UI[Next.js UI] -- REST + SSE --> API[FastAPI] -- enqueue --> W[Arq worker]
  W --> BG[[Bid graph]] & CG[[Conversation graph]]
  BG -- "scout -> analyst || risk || matcher -> decide -> pricing -> writer -> verifier -> critic (<=2) -> compliance -> interrupt -> submit" --- BG
  BG & CG --> GW{{MCP gateway<br/>per-agent allowlists}}
  GW --> PF[Portfolio MCP] & MK[Marketplace MCP] & WS[Workspace MCP]
  MK --> GS[GigSim] & UP[Upwork MCP - drafts only]
  PF -.-> GH[GitHub MCP]
  BG & CG --> PG[(Postgres: checkpoints, memory store, audit log)]
```
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · tools: [docs/TOOLS.md](docs/TOOLS.md) · data: [docs/DATA_CARD.md](docs/DATA_CARD.md) ·
operations: [docs/RUNBOOK.md](docs/RUNBOOK.md) · decisions: [docs/adr/](docs/adr/) · extension (A/B proposal experiments): [docs/EXTENSION.md](docs/EXTENSION.md)

## Results
Every number below is rendered by `python -m scripts.render_results` from `evals/results/*.json` (CI fails if stale).
Gold labels are rule-based on synthetic personas (see the data card); the `test` profile uses the deterministic writer.

### Retrieval variants (B5)
<!-- results:rag -->
| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal (first draft -> final) | GigSim reply rate | p95 retrieval latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| v0_naive | 0.462 | 0.744 | 0.521 | 0.10 -> 0.00 | 0.850 | 0.11 | 0.0000 |
| v1_decompose | 0.477 | 0.720 | 0.546 |  |  | 0.10 |  |
| v2_hybrid | 0.494 | 0.779 | 0.547 |  |  | 0.10 |  |
| v3_rerank | 0.473 | 0.748 | 0.540 |  |  | 2.56 |  |
| v4_outcome | 0.490 | 0.745 | 0.530 |  |  | 0.09 |  |
| v5_multivector | 0.491 | 0.741 | 0.543 |  |  | 0.11 |  |
| v6_contextual | 0.460 | 0.759 | 0.520 |  |  | 0.12 |  |
| v7_hyde | 0.494 | 0.811 | 0.565 |  |  | 0.17 |  |
| v8_corrective | 0.489 | 0.710 | 0.608 |  |  | 11.53 |  |
| stack_no_corrective | 0.491 | 0.710 | 0.605 |  |  | 10.11 |  |
| stack_no_rerank | 0.508 | 0.719 | 0.627 |  |  | 0.14 |  |
| stack_no_hybrid | 0.475 | 0.714 | 0.603 |  |  | 13.18 |  |
| stack_no_decompose | 0.417 | 0.653 | 0.489 |  |  | 4.27 |  |
| stack_no_outcome | 0.480 | 0.665 | 0.539 |  |  | 22.67 |  |
| stack_no_multivector | 0.448 | 0.668 | 0.490 |  |  | 12.31 |  |
| shipped | 0.508 | 0.719 | 0.627 | 0.02 -> 0.00 | 0.772 | 0.05 | 0.0000 |

_n = 90 dev jobs with gold evidence (project-level); source `evals/results/rag_variants.json` @ dd5ab84._
<!-- /results:rag -->

### End-to-end in GigSim (fixed job set, drafts auto-approved for evaluation only)
<!-- results:outcomes -->
| Run | Submitted / jobs | Reply rate | Interview rate | Hire rate | Unsupported claims / proposal (first draft -> final) | Mean revisions | p95 s / proposal |
|---|---|---|---|---|---|---|---|
| V0 retrieval, evidence-first | 40/60 | 0.850 | 0.550 | 0.350 | 0.10 -> 0.00 | 0.35 | 75.0 |
| shipped retrieval, evidence-first | 57/60 | 0.772 | 0.421 | 0.281 | 0.02 -> 0.00 | 0.18 | 72.9 |
| shipped retrieval, question-first | 57/60 | 0.877 | 0.491 | 0.351 | 0.02 -> 0.00 | 0.32 | 75.0 |

_A/B (X2): McNemar exact p = 0.2379 on 57 paired jobs; source `evals/results/ab_test.json`._
<!-- /results:outcomes -->

### Decisions on the dev set
<!-- results:decisions -->
| Slice | n | Bid/skip F1 | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) |
|---|---|---|---|---|---|---|
| overall | 120 | 0.723 | 0.800 | 1.000 | 0.941 | 24.01 |
| ai_ml_engineer | 40 | 0.733 | 1.000 | 1.000 | 1.000 | 24.01 |
| fullstack_web | 40 | 0.733 | 0.800 | 1.000 | 0.909 | 24.01 |
| data_analyst | 40 | 0.706 | 0.667 | 1.000 | 0.917 | 24.01 |

_source `evals/results/decisions_test.json` @ 6ce8e35._
<!-- /results:decisions -->

### Tool granularity (R&D A)
<!-- results:tools -->
| Tool set | # tools | Tool-selection accuracy | Argument accuracy | Tokens / task |
|---|---|---|---|---|
| fine | 17 | 0.500 | 0.500 | 930 |
| coarse | 3 | 0.100 | 0.100 | 472 |
| best | 10 | 0.900 | 0.800 | 789 |

_model `qwen3:1.7b`, n = 20 tasks; source `evals/results/tool_granularity.json`._
<!-- /results:tools -->

### Prompt-injection defence
<!-- results:injection -->
| Condition | Attack success rate |
|---|---|
| no defences (naive writer, raw text, no Compliance Guard) | 0.583 |
| GigBid writer prompt + delimiting (before Compliance) | 0.333 |
| full GigBid (+ Compliance Guard) | 0.000 |

_n = 12 planted-injection jobs with valid LLM output; detection rate 1.000; model profile `open_small`._
<!-- /results:injection -->

### Single agent vs prebuilt supervisor vs hand-built graph (R&D C)
<!-- results:multiagent -->
| System | Jobs | Errors / timeouts | Bid/skip accuracy | Bids on skip-labelled jobs | Bid-labelled job bid | p50 s | p95 s |
|---|---|---|---|---|---|---|---|
| single ReAct agent | 45 | 2 | 0.256 | 0.762 | 1/1 | 125 | 532 |
| prebuilt supervisor | 45 | 11 | 0.353 | 0.667 | 1/1 | 125 | 1500 |
| GigBid graph | 45 | 0 | 0.778 | 0.227 | 1/1 | 122 | 503 |

_model profile `open_small` (Qwen3-1.7B on CPU); source `evals/results/multiagent_compare.json` @ 11a9e41. rebuilt from evals/results/multiagent_compare_log.txt (run stopped after 45 jobs; 1 bid-labelled + 44 skip-labelled jobs, persona ai_ml_engineer; claim/reply/token metrics not recorded)._
<!-- /results:multiagent -->

### Public traces
1. Skipped scam: `<LangSmith share link>`
2. Approved proposal: `<LangSmith share link>`
3. Critic loop / crash-and-resume: `<LangSmith share link>`

## Run it
```bash
uv sync --extra dev && (cd apps/web && npm ci)
python -m scripts.dev --reset --web          # GigSim :8081, API :8000, web :3000 - no Docker, no API key (MODEL_PROFILE=test)
```
Full stack: `cp .env.example .env && cd infra && docker compose --env-file ../.env up --build` (web, api, worker, 3 MCP
servers, GigSim, Postgres, Redis, Qdrant; `--profile local-llm` adds Ollama). Tests: `uv run pytest -q`,
`cd apps/web && npm run test:e2e`. Evaluation: `make eval` (see the Makefile for the individual commands).

## Pinned versions
Python 3.12 · LangGraph 1.2.22 · langchain-core 1.8.0 · langchain-mcp-adapters 0.3.2 · MCP Python SDK 1.30.0 ·
langgraph-supervisor 0.0.31 · FastAPI 0.163.0 · fastembed 0.9.1 · qdrant-client 1.20.0 · Next.js 15.5.29 · React 19.3.1 ·
Playwright 1.65.1 · openapi-typescript 7.13.0 (full lock: `uv.lock`, `apps/web/package-lock.json`).
Models: Groq gpt-oss-20b / gpt-oss-120b (open profile), Ollama qwen3:1.7b / qwen3:4b (local), BAAI/bge-small-en-v1.5
embeddings, ms-marco-MiniLM-L-6-v2 reranker.

## Résumé bullets
- Built GigBid, a LangGraph multi-agent freelancer copilot (3 MCP servers, Next.js UI, interrupt-based human approval, crash-safe exactly-once submission); 7/7 Playwright E2E and 50+ unit/contract/integration tests pass.
- Ran a 15-variant RAG study on a 600-job dev set built from 60k real Upwork posts: shipped hybrid + requirement-decomposition retrieval at 0.508 Recall@5 / 0.627 nDCG@10 (V0: 0.462 / 0.522) at 1% of the re-ranked stack's latency, after an ablation showed the cross-encoder re-ranker lowered quality.

## Repository map
`agent/` graphs, nodes, prompts (one versioned .md per node), memory rules, config · `rag/` loaders, index, variants
V0-V8, claim verification · `mcp_servers/` portfolio, marketplace (GigSim + Upwork adapters), workspace · `apps/api`
FastAPI · `apps/web` Next.js · `worker/` Arq + GraphRunner · `gigsim/` simulator (frozen) · `evals/` datasets,
runners, results · `infra/` Dockerfiles + compose · `docs/`.
