## 4. R&D question B - retrieval, verification and what ships

**Hypotheses (committed before any run, `evals/HYPOTHESES.md`).** H-B1: decomposition + hybrid raise project Recall@5 by
>= 10 points over V0 on jobs with >= 4 requirements. H-B2: hybrid beats dense on `exact_tool` jobs. H-B3: multi-vector helps
most on `implied` jobs. H-B4: claim verification halves unsupported claims. H-B5 (expected negative): better retrieval will
not translate one-for-one into reply rate.

**Setup.** 90 dev jobs (30 per persona, seeded sample of jobs with gold evidence, scams excluded). Unit = portfolio *project*
(a case study, its README, its code and the proposals citing it are one project). CPU only: bge-small embeddings,
ms-marco-MiniLM-L-6 cross-encoder (inputs truncated to 512 chars). V7 uses the deterministic hypothetical-proposal
template (no LLM) under the `test` profile. Source: `evals/results/rag_variants.json` (+ `_per_job.csv`).

{{RAG_TABLE}}

**Findings.**
1. **Every single idea beats V0 a little; none beats it a lot.** V2 hybrid (+3.2 pts Recall@5) and the template HyDE V7
   (+3.3 pts, best MRR 0.81) are the best single changes, both essentially free in latency. V6 contextual headers did nothing
   (-0.1 pts): the header repeats metadata the chunk already contains on a template-generated corpus.
2. **The cross-encoder re-ranker hurts on this corpus.** V3 (+1.1 pts) is the weakest helpful change and costs ~25x
   latency; inside the full stack, *removing* it (`stack_no_rerank`) raises Recall@5 from 0.489 to 0.508 and nDCG@10 from
   0.608 to 0.627 while cutting p95 latency from ~11 s to 0.14 s. MS-MARCO trained the model to recognise passages that
   *answer a question*; "Hands-on Metabase" vs a README that lists Metabase is not that, and many relevant chunks scored ~0.
3. **Decomposition carries the stack.** The largest ablation drop is removing decomposition (0.489 -> 0.417 Recall@5,
   nDCG@10 0.608 -> 0.489). Hybrid is second ({{ABL_HYBRID}}). Outcome boost and multi-vector move results by
   {{ABL_SMALL}}.
4. **H-B1** {{HB1}}. **H-B2** {{HB2}}. **H-B3** {{HB3}}.

**What ships (R6, ADR 0005).** `shipped` = decomposition + hybrid BM25/dense (RRF) + outcome boost + multi-vector project
grouping, **no re-ranking**: the best Recall@5 and nDCG@10 we measured at ~1% of the stack's latency. The Fit Matcher still
needs a calibrated "is this requirement proven?" signal. The cross-encoder could not provide it (it scored most relevant
evidence ~0), so `shipped` grades the top-8 evidence of each requirement with bi-encoder cosine. Thresholds come from 308
dev requirements: cover at >= 0.70 (proves 70% of requirements whose skills the persona has, passes 47% of those it does not);
"no evidence, do not claim" below 0.62. The overlap is large, which is why the Fit Matcher also requires a lexical skill
hit or a must-have weighting, and why bid decisions are compared with the V8 stack in section 5.

**Claim verification (B3).** Every draft is split into claims; experience claims are grounded against the evidence
(0.6 x semantic + 0.4 x key-term coverage; every number must appear in the evidence). Unsupported claims are removed and
unverifiable numbers softened before the Critic. On the GigSim runs: {{VERIFY}}.

**Where better retrieval did not buy replies (H-B5).** {{OUTCOME_GAP}}
