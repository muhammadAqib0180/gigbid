# Pre-registered hypotheses

Written and committed **before** any evaluation run (see `git log -- evals/HYPOTHESES.md`).
Results are reported against these in the R&D report, including the ones that fail.

## R&D question A - tool granularity
- **H-A1.** The "best" tool set (our MCP tools with rewritten, task-oriented descriptions) gives higher
  tool-selection accuracy than both the fine-grained set (16 narrow tools) and the coarse set (3 tools with an
  `action` argument), with the coarse set worst on argument accuracy.
- **H-A2.** The fine-grained set costs the most prompt tokens per task (more tool schemas in context).

## R&D question B - retrieval
- **H-B1.** Requirement decomposition + hybrid retrieval (V1 + V2, inside the full stack) raises project
  Recall@5 by **≥ 10 points over V0** on jobs with four or more requirements.
- **H-B2.** Hybrid BM25 + dense (V2) beats dense-only (V0) on the `exact_tool` job type (named tools such as
  Celery, dbt, Pinecone that embeddings blur).
- **H-B3.** Multi-vector project grouping (V5) helps most on `implied` jobs, where the skill only appears in a
  repository's code, not its README or case study.
- **H-B4.** Claim verification cuts unsupported claims per proposal by at least half.
- **H-B5 (expected negative).** Better retrieval will NOT translate one-for-one into a higher GigSim reply rate,
  because simulated clients also weigh price, personalisation and generic openings.

## R&D question C - multi-agent vs single agent
- **H-C1.** The hand-built graph catches more compliance violations and produces fewer unsupported claims than
  a single ReAct agent with all tools, at lower or similar token cost per job (cheap nodes are rule-based or
  small-model).
- **H-C2.** The single ReAct agent can match the graph on bid/skip accuracy for obvious scams and clearly
  off-domain jobs, where one tool call is enough to decide.

## Safety
- **H-S1.** Delimiting untrusted text + injection detection + the Compliance Guard reduce the attack success
  rate on planted-injection jobs to under 10%, from a materially higher rate with defences disabled.

## Signature extension (X2)
- **H-X2.** Evidence-first openings get a higher GigSim reply rate than question-first openings; we expect a
  small effect that may not be significant at our sample size.
