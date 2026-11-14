# ADR 0004 - RAG variants as composable presets
Each variant is a `PipelineConfig` preset (`rag/variants/v*.py`): query (whole / decompose / HyDE), retriever (dense /
BM25 / hybrid RRF), cross-encoder rerank, outcome boost, chunking (fixed / structure-aware), contextual header,
multi-vector project grouping, corrective loop. V0-V8 isolate one idea each over the V0 baseline; `stack_no_*` remove
one component from the full stack for the ablation. **Deviation:** V6 builds the context line from metadata instead of
an LLM call per chunk (~1.4k chunks x 3 personas was out of budget on CPU). V9 (GraphRAG) not implemented; V8 covers
the required agentic group. Evaluation is project-level (a case study, its README, its code and the proposals citing it
are one project).
