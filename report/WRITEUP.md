# The re-ranker made it worse: what 15 retrieval experiments taught me about proving a freelancer's experience

*Draft for Medium / LinkedIn (~1,500 words). Every number links to a results file in the GigBid repository.*

Every "advanced RAG" checklist I have read ends the same way: retrieve broadly, then put a cross-encoder on top to
re-rank the candidates. It is the step that turns a demo into a "production" pipeline. I added it to GigBid, the
multi-agent freelancer copilot I built for a course project, expecting it to be the best component in the system.

It was the worst. On the job my retrieval had to do, the re-ranker lowered recall, lowered ranking quality, and made
every request about seventy times slower. Removing it from the full pipeline improved every metric I tracked. This
post is about why that happened and what it taught me about measuring a RAG system against the task it actually serves,
rather than against the task its components were trained on.

## The task: evidence, not vibes

GigBid reads a freelance job post, decides whether it is worth bidding on, and drafts a proposal - but every sentence in
that proposal that claims experience has to be backed by something real in the freelancer's portfolio: a case study, a
repository, a client review, a past proposal. A separate verifier checks each claim against the evidence and deletes
the ones it cannot ground before a human ever sees the draft.

So retrieval here is not "find a passage that answers a question". It is "for each thing this client asks for, find the
project that proves I have done it". A job that asks for Celery, Redis and a Django admin is three retrieval problems,
not one. And the portfolio is deliberately awkward: the same project is described three ways (a client-facing case
study, a technical README, a sales-y paragraph in an old proposal), and some skills are only implied - a case study says
"slow steps run on a background worker queue with automatic retries", while the word "Celery" only appears in an
`import` line inside the repository.

I built three synthetic personas (an ML engineer, a full-stack developer, a data analyst) with 18 projects each and 150
past proposals labelled won, replied or ignored, and a 600-job dev set from real Upwork job posts (a public Kaggle
dataset) plus synthetic scams and prompt-injection attacks. For each job, the "gold" answer is the set of portfolio
projects that prove its requirements. I scored retrieval at the project level: a README and a case study about the same
project count as the same hit.

## Fifteen variants, one baseline

I implemented nine variants as composable presets over one pipeline, so each changes exactly one idea against a naive
baseline, then built the full stack and ablated it one component at a time. On 90 dev jobs (CPU only, open models):

| Variant | Recall@5 | MRR | nDCG@10 | p95 latency |
|---|---|---|---|---|
| V0 naive dense | 0.462 | 0.744 | 0.522 | 0.11 s |
| V1 requirement decomposition | 0.477 | 0.720 | 0.546 | 0.10 s |
| V2 hybrid BM25 + dense | 0.494 | 0.779 | 0.547 | 0.10 s |
| V3 cross-encoder re-rank | 0.473 | 0.748 | 0.540 | 2.56 s |
| V7 HyDE (template, no LLM) | 0.494 | 0.811 | 0.565 | 0.17 s |
| Full stack (decompose + hybrid + re-rank + outcome boost + multi-vector + corrective loop) | 0.489 | 0.710 | 0.608 | 11.5 s |
| Full stack **without** re-rank | **0.508** | 0.719 | **0.627** | 0.14 s |

(`evals/results/rag_variants.json`)

Three things surprised me.

**1. Every idea helps a little and nothing helps a lot.** The best single change - hybrid retrieval - adds about three
points of recall. Contextual headers on chunks added nothing at all. If you have read the papers, you expect bigger
numbers; if you have read your own corpus, you should not. A template-generated portfolio is regular enough that dense
retrieval already finds the obvious matches; the remaining misses are hard for every method.

**2. Decomposition carries the stack.** Removing requirement decomposition from the full pipeline was the biggest
single drop (Recall@5 0.489 -> 0.417). Treating "Django + Celery + Postgres + Stripe" as one query lets the most
distinctive term win and starves the others; one query per requirement, merged round-robin, gives each requirement a
seat at the table. This is the cheapest idea in the list and the most valuable.

**3. The re-ranker hurt, and it could not even serve as a judge.** The cross-encoder I used is a standard choice - a
small MiniLM fine-tuned on MS MARCO, the default in most tutorials. MS MARCO is question-answering: given a query, is
this passage *the answer*? My queries are not questions. "Hands-on Metabase" against a README whose stack section lists
Metabase is relevant, but it is not an answer, and the model scored a lot of genuinely relevant evidence near zero. In
the full stack it confidently promoted fluent prose (past proposals, CV summaries) over terse but decisive evidence (a
README, a `requirements.txt`).

It got worse when I tried to keep the cross-encoder in a smaller role: using it only to grade the top-ranked evidence
for each requirement, as a "did we find proof?" signal for the bid decision. With top-1 grading, almost every
requirement of a perfectly good job came back "no evidence". I replaced it with plain bi-encoder cosine similarity
calibrated on 308 labelled requirements - a weaker separator than I would like (the score distributions overlap
heavily), but at least an honest one, paired with a lexical check that the required skill actually appears in the evidence.

## What ships, and why that is the real lesson

The pipeline GigBid now ships is the full stack *minus* the re-ranker: decomposition, hybrid BM25 + dense with reciprocal
rank fusion, a small boost for evidence from proposals that won, and multi-vector grouping so a project's README, code
and case study vote together. It has the best recall and ranking quality I measured, at about one percent of the
latency of the "advanced" version.

The lesson I keep coming back to is not "re-rankers are bad". It is that **a component's benchmark is not your
benchmark**. The re-ranker is excellent at the task it was trained for. My task looked similar enough to fool me, and
the only reason I found out is that every variant was a config switch and one command re-ran the whole comparison. If I
had added the re-ranker because the checklist said so and eyeballed a few results, it would be in production now,
slower and worse, and I would be telling people it helped.

## Better retrieval did not buy replies one-for-one

The end metric for GigBid is not recall; it is whether a (simulated) client replies. I ran the complete agent graph on
a fixed set of jobs with the naive retriever and with the shipped one, submitted every approved draft to the simulator
and counted replies: {{OUTCOME_SENTENCE}} The simulated clients care about whether the opening is specific to their
job, whether the price fits their ceiling and whether the proposal names their must-have skills - retrieval feeds only
part of that. I had written down that I expected this gap before running anything, and it still felt deflating to see it.

## What I would do next

* Fine-tune (or simply choose) a cross-encoder on *requirement -> evidence* pairs instead of question -> answer.
* Replace rule-based gold labels with a human-labelled slice; my dev labels encode my own definition of fit.
* Measure on real portfolios, which are far less regular than mine and may reward the re-ranker after all.

The code, the data card, the pre-registered hypotheses and every results file are in the repository. If you are adding
a re-ranker to your RAG pipeline this week, run it against your own task first. It took me fifteen variants to learn
that one.
