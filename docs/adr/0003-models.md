# ADR 0003 - Open models first, routed by node
`open` (deployment): Groq-hosted gpt-oss-20b for cheap nodes (analyst, risk, intent, compliance, HyDE, verifier LLM mode)
and gpt-oss-120b for writer, critic, liaison and the judge; OpenRouter as fallback provider; Ollama qwen3:1.7b as the
fallback model for cheap nodes. `open_local` / `open_small`: Ollama qwen3 4B / 1.7B. Embeddings `BAAI/bge-small-en-v1.5`
and reranker `ms-marco-MiniLM-L-6-v2` run on CPU (ONNX, fastembed) in every profile. `test`: deterministic heuristics.
Cheap decisions (risk floor, decide, pricing, compliance rules, claim grounding) are rules/embeddings first, so most of
a job's analysis costs no tokens. Measured speeds: `evals/results/model_speed.json`.
