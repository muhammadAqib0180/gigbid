## Résumé bullets (numbers from evals/results)

- Built GigBid, a LangGraph multi-agent freelancer copilot (3 MCP servers, Next.js UI, interrupt-based human approval, crash-safe exactly-once submission); 7/7 Playwright E2E and 50+ unit/contract/integration tests pass.
- Ran a 15-variant RAG study on a 600-job dev set built from 60k real Upwork posts: shipped hybrid + requirement-decomposition retrieval at 0.508 Recall@5 / 0.627 nDCG@10 (V0: 0.462 / 0.522) at 1% of the re-ranked stack's latency, after an ablation showed the cross-encoder re-ranker lowered quality.
