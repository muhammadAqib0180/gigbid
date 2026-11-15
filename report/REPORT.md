# GigBid: R&D Report

**AI-4016, Assignment II.** GigBid is a multi-agent freelancer copilot built with LangGraph, three MCP servers, a
retrieval layer that grounds every claim in the freelancer's portfolio, and a Next.js interface. It finds and assesses
jobs and drafts proposals and replies, but nothing is sent without human approval. Every number in this report comes from
a file in `evals/results/`, and each file records the commit that produced it.

## 1. Problem and constraints

**Workflow.** Freelancers spend hours scanning job feeds, pay Connects to bid on jobs they are unlikely to win, send
generic proposals, and run into scams that ask for free trial work, off-platform payment or credentials. GigBid takes over
discovery, assessment and drafting; the freelancer keeps every decision.

**What is never automated.** Submitting a proposal, sending a message, spending Connects, moving a conversation
off-platform, and claiming experience the portfolio does not show. These limits are enforced in code, not in prompts: a
LangGraph `interrupt()` before every external write, a separate idempotent submit step, per-agent tool allowlists (the
Writer cannot see `submit_proposal`), a Compliance Guard and claim verification. The highest autonomy setting can skip
jobs automatically but never sends anything.

**Budgets** (`agent/config.yaml`). p95 latency of 20 s per analysed job and 60 s per proposal; USD 0.001 per analysed job
and USD 0.006 per proposal on the hosted `open` profile (Groq gpt-oss). Each thread is limited to 40 graph steps and 24k
tokens; exceeding either moves it to `needs_attention`.

**Data and environment.** The starter kit had no GigSim, persona corpora or dev set, so we built them
(`docs/DATA_CARD.md`): GigSim serves 60k real Upwork job posts from the Kaggle datasets in the brief, priced from 1.3M
contracts and 250k postings, plus labelled synthetic data (three personas, scams, prompt injections, reposts, client
preferences and rule-based gold labels); the dev set has 600 jobs. Everything ran on an 8-thread laptop CPU with no GPU
or paid API. LLM studies use Qwen3-1.7B through Ollama at small sample sizes and can be repeated at full size on the
hosted profile (`make eval-llm`).

## 2. Architecture

GigBid runs two hand-written LangGraph graphs, both drawn from code in the Appendix.

* **Bid graph** (one thread per job): scout; analyst, risk assessor and fit matcher in parallel (fan-out with `Send`,
  fan-in at the decision node); decide; pricing; writer; verifier; critic (at most two revisions); compliance; approval
  (`interrupt()`); submit. Every router first checks for a halt condition: an exceeded budget sends the thread to
  `needs_attention`, repeated failure to `dead_letter`.
* **Conversation graph** (one thread per client conversation): load the thread, classify the message, draft a reply,
  compliance, approval (`interrupt()`), send.

**Why each agent exists.** The three analysis nodes depend only on the job, so they run in parallel; the fit matcher
extracts requirements itself rather than waiting for the analyst. Risk, the bid decision, pricing, compliance and claim
grounding are rules and embeddings first, because they run on every job and must not be argued out of a red flag by text
inside a job post; the LLM adds judgement on top. Only the Writer and Critic need the strongest open model (gpt-oss-120b
on Groq in the `open` profile).

**Marketplace port and MCP servers.** `agent/marketplace_port.py` is the only interface to the marketplace; it calls our
Marketplace MCP server, which picks the GigSim or live-Upwork adapter from configuration, so moving to live mode needs
no code change. Our three servers (`docs/TOOLS.md`) are *Portfolio* (4 read-only tools, 4 resource templates and 3
prompts; published on PyPI as `portfolio-evidence-mcp`), *Marketplace* (8 read and 3 write tools; every write needs an
idempotency key and supports `dry_run`; bearer-JWT auth, a per-user rate limiter and an append-only audit log) and
*Workspace* (calendar slots, holds and email drafts). GigBid also uses the official Upwork MCP server (OAuth 2.1, drafts
only) and the official GitHub MCP server (read-only).

**State, trace and memory** are kept separate: typed graph state (`BidState`, `ConversationState`) with reducers for
parallel writes; an execution trace in the MCP audit log, the `run_events` table and LangSmith; and a long-term store with
style and outcome namespaces, written only by explicit promotion rules (`agent/memory/promotion_rules.py`). A style rule
needs the same edit in three different proposals within 30 days; an outcome insight needs five outcomes in a category
and a 10-point reply-rate lift.

**Durability.** Threads are checkpointed in Postgres (SQLite locally) and pending approvals are read from checkpoints, so
a restart never loses one. Submission follows approval and uses idempotency keys stored by the Marketplace server and
forwarded to GigSim. Killing the API while four drafts awaited approval, restarting and approving produced exactly one
`submit_proposal` in the audit log; an integration test covers the same path.

## 3. R&D question A: does tool granularity change agent behaviour?

**Hypotheses.** H-A1: a task-oriented tool set beats both a fine-grained and a coarse set on tool-selection accuracy,
with the coarse set worst on arguments. H-A2: the fine-grained set costs the most tokens.

**Setup.** 20 tasks with known correct calls: ten intents with two instances each, built from real dev-set ids (search
jobs, fetch a job, check a client, Connects balance, market rates, portfolio evidence, open a case study, free calendar
slots, read a thread, preview a proposal). Three tool sets were bound to the same model: *fine* (17 narrow tools),
*coarse* (3 tools with an `action` argument) and *best* (10 task-oriented tools with rewritten descriptions). We score the
first tool call without executing it. Model: Qwen3-1.7B on CPU. CPU time limited the run to 20 of the planned 40 tasks
(`tool_granularity.json`).

| Tool set | Tools | Tool-selection accuracy | Argument accuracy | Tokens per task |
|---|---|---|---|---|
| fine | 17 | 0.50 | 0.50 | 930 |
| coarse | 3 | 0.10 | 0.10 | 472 |
| best (shipped) | 10 | **0.90** | **0.80** | 789 |

**Results.** Both hypotheses hold. Almost every miss by the weaker sets was a missing tool call: the model answered in
prose instead of acting. With the coarse set it called a tool for one intent in ten, because an `action` value inside a
generic tool gives the model nothing to match the request against. With the fine set it called tools only when a tool name
echoed the request, and failed on "is this client trustworthy?" when the choices were `get_client_rating` and
`get_client_spend`. The shipped set missed only "How many Connects do I have left?". The fine set also used 18% more
prompt tokens per task than the shipped set.

**Conclusion.** Tool design matters more than tool count. Our servers expose one tool per user intent, named with the
user's verbs, with a description that says when to use it. Where a whole workflow is a single intent, one coarser tool is
better: `match_requirements` maps all of a job's requirements to evidence in one call.

## 4. R&D question B: retrieval, claim verification and the shipped pipeline

**Hypotheses** (`evals/HYPOTHESES.md`, written before any run). H-B1: requirement decomposition plus hybrid search raises
project Recall@5 by at least 10 points over V0 on jobs with four or more requirements. H-B2: hybrid search beats dense
retrieval on jobs that name exact tools. H-B3: multi-vector retrieval helps most when a skill is only implied. H-B4: claim
verification halves unsupported claims. H-B5: better retrieval will not translate one-for-one into a better reply rate.

**Setup.** 90 dev jobs (30 per persona; a seeded sample of jobs with gold evidence, scams excluded). Scoring is per
portfolio project: a case study, its README, its code and the proposals that cite it count as one hit. Embeddings:
bge-small-en-v1.5; cross-encoder: ms-marco-MiniLM-L-6 (input truncated to 512 characters). V7 uses a template-generated
hypothetical proposal instead of an LLM. V1 to V8 each change one idea; the rows marked "without" remove one component
from the full stack (V8). Sources: `rag_variants.json`, `rag_variants_per_job.csv`.

| Variant | Recall@5 | MRR | nDCG@10 | p95 (s) | R@5 exact-tool | R@5 implied | R@5 real | R@5 synthetic |
|---|---|---|---|---|---|---|---|---|
| V0 naive dense | 0.462 | 0.744 | 0.522 | 0.11 | 0.467 | 0.560 | 0.431 | 0.507 |
| V1 decomposition | 0.477 | 0.720 | 0.546 | 0.10 | 0.558 | 0.640 | 0.407 | 0.583 |
| V2 hybrid (RRF) | 0.494 | 0.779 | 0.547 | 0.10 | 0.519 | 0.520 | 0.448 | 0.563 |
| V3 cross-encoder re-rank | 0.473 | 0.748 | 0.540 | 2.56 | 0.519 | 0.520 | 0.420 | 0.552 |
| V4 outcome-aware | 0.490 | 0.745 | 0.530 | 0.09 | 0.505 | 0.560 | 0.461 | 0.533 |
| V5 multi-vector | 0.491 | 0.741 | 0.543 | 0.11 | 0.519 | 0.453 | 0.460 | 0.537 |
| V6 contextual header | 0.460 | 0.759 | 0.520 | 0.12 | 0.498 | 0.440 | 0.448 | 0.480 |
| V7 HyDE (template) | 0.494 | **0.811** | 0.565 | 0.17 | 0.498 | 0.493 | 0.455 | 0.554 |
| V8 full stack | 0.489 | 0.710 | 0.608 | 11.53 | 0.537 | 0.640 | 0.385 | 0.644 |
| V8 without corrective loop | 0.491 | 0.710 | 0.605 | 10.11 | 0.537 | 0.640 | 0.389 | 0.644 |
| V8 without re-ranking | **0.508** | 0.719 | **0.627** | 0.14 | **0.568** | 0.520 | 0.424 | 0.633 |
| V8 without hybrid | 0.475 | 0.714 | 0.603 | 13.18 | 0.516 | 0.600 | 0.377 | 0.622 |
| V8 without decomposition | 0.417 | 0.653 | 0.489 | 4.27 | 0.467 | 0.520 | 0.387 | 0.463 |
| V8 without outcome boost | 0.480 | 0.665 | 0.539 | 22.67 | 0.547 | 0.640 | 0.370 | 0.644 |
| V8 without multi-vector | 0.448 | 0.668 | 0.491 | 12.31 | 0.484 | 0.480 | 0.410 | 0.506 |
| **Shipped** (V8 without re-ranking, cosine support) | **0.508** | 0.719 | **0.627** | **0.05** | 0.568 | 0.520 | 0.424 | 0.633 |

**Findings.**

1. *Single ideas give small gains.* Hybrid search (+3.2 points Recall@5) and the template HyDE (+3.3 points, best MRR of
   0.811) are the best single changes and add almost no latency. Contextual chunk headers had no effect (-0.1): on a
   template-generated corpus the header repeats what the chunk already says.
2. *The cross-encoder hurts.* On its own it adds 1.1 points for 25 times the latency. Inside the full stack, removing it
   improves every metric (Recall@5 0.489 to 0.508, nDCG@10 0.608 to 0.627) and cuts p95 latency from 11.5 s to 0.14 s.
   The model was trained on MS MARCO to find passages that answer a question. A requirement such as "hands-on Metabase"
   matched against a README that lists Metabase is relevant evidence but not an answer, and the model scored much of that
   evidence near zero while ranking fluent proposal text higher.
3. *Three components carry the stack.* Removing decomposition, multi-vector grouping or the outcome boost costs 7.2, 4.1
   and 0.9 points of Recall@5 (11.9, 11.8 and 6.9 points of nDCG@10). The corrective loop adds almost nothing once
   ranking is good.
4. *Hypotheses.* H-B1 is not supported: on jobs with four or more requirements the shipped stack gains 2.7 points (0.464
   to 0.492). H-B2 is supported: hybrid search adds 5.3 points on exact-tool jobs alone and 2.1 inside the stack. H-B3 is
   mixed: V5 alone lowers recall on implied-skill jobs (0.560 to 0.453), but inside the stack multi-vector grouping is
   worth 16 points on them (0.48 to 0.64).
5. *The gains come from synthetic jobs.* The shipped stack lifts synthetic, requirement-targeted jobs from 0.507 to 0.633
   but not real Kaggle posts (0.431 to 0.424). Real posts are vaguer and their rule-based gold labels are noisier; this is
   the main limitation of the retrieval results.

**Shipped pipeline** (ADR 0005). Decomposition, hybrid BM25 and dense retrieval fused with reciprocal rank fusion, the
outcome boost and multi-vector grouping, without re-ranking. It has the best Recall@5 and nDCG@10 we measured at about 1%
of the full stack's latency. The Fit Matcher still needs a per-requirement signal of whether the evidence proves a
requirement. The cross-encoder could not provide it (with top-1 grading almost every requirement of good jobs scored as
unproven), so support is the bi-encoder cosine between a requirement and its top eight evidence chunks, with thresholds
calibrated on 308 dev requirements. At the coverage threshold of 0.70, 70% of requirements the persona has the skill for
pass, but so do 47% of those it does not. Because of this overlap, the Fit Matcher also checks that the skill appears in
the evidence text. Decision quality with the shipped pipeline and with V8 is about the same (section 5), at half the
median latency.

**Claim verification (H-B4).** In the 57 GigSim proposals of the shipped run (3.04 claims each), unsupported claims fell
from 0.018 per proposal in the first draft to zero after verification (`outcomes_shipped.json`). The baseline is low
because the offline Writer only quotes evidence, so this run does not really test H-B4. With an LLM writer the verifier
missed vague statements such as "I have successfully completed projects similar to this"; after the claim patterns were
widened it found two claims in that letter, one supported and one partly supported (`verifier_fix_demo.json`).

**Retrieval quality and replies (H-B5).** The same 60 jobs and the same deterministic Writer, with V0 and with the shipped
pipeline (`outcomes_v0_naive.json`, `outcomes_shipped.json`):

| Retrieval | Bids submitted | Reply rate per proposal | Replies | Hires | Claims per proposal | Unsupported claims, first draft to final |
|---|---|---|---|---|---|---|
| V0 naive | 40 / 60 | **0.850** | 34 | 14 | 1.48 | 0.100 to 0.000 |
| Shipped | **57 / 60** | 0.772 | **44** | **16** | 3.04 | 0.018 to 0.000 |

Per proposal V0 looks better, but this is selection, not quality. Weaker evidence gives lower fit scores, so V0 bid only
on the 40 jobs it was most confident about, which are also the jobs the simulated clients favour. Per job, the shipped
pipeline produced 29% more replies and two more hires, and its drafts made twice as many claims with less than a fifth of
the unsupported-claim rate before verification. H-B5 is supported. We therefore report reply rate per job as well as per
proposal, and keep claim verification, which took V0's unsupported claims from 0.10 per proposal to zero.

## 5. R&D question C: is the multi-agent design worth it?

**Setup.** Three systems ran on the same jobs with the same model: (a) a single ReAct agent holding the read tools
(`create_react_agent`), (b) `langgraph-supervisor` with a marketplace researcher, a portfolio researcher and a writer, and
(c) the GigBid bid graph. Every final letter goes through the same claim verifier, compliance rules and simulated client.
Model: Qwen3-1.7B on CPU, with a 25-minute timeout per run. A sampling error in the evaluation runner (since fixed)
limited the completed sample to 45 jobs from one persona, `ai_ml_engineer`: 1 bid-labelled and 44 skip-labelled.
Decisions, errors and latency per job were recovered from the run log; claim, reply and token metrics were not retained
(`multiagent_compare.json`, rebuilt by `evals/runners/multiagent_from_log.py`). Accuracy and the false-bid rate exclude
runs that errored.

| System | Jobs | Errors (timeouts) | Bid/skip accuracy | Bids on skip-labelled jobs | Bid-labelled job bid | p50 (s) | p95 (s) |
|---|---|---|---|---|---|---|---|
| (a) Single ReAct agent | 45 | 2 (2) | 0.256 | 32 / 42 (76%) | 1/1 | 125 | 532 |
| (b) Prebuilt supervisor | 45 | 11 (3) | 0.353 | 22 / 33 (67%) | 1/1 | 125 | 1500 |
| (c) GigBid graph | 45 | **0** | **0.778** | **10 / 44 (23%)** | 1/1 | 122 | 503 |

**Decision quality at scale.** On 120 dev jobs with the rule-based analysis path (`decisions_test.json`), the graph
reaches a bid/skip F1 of 0.723 (precision 0.586, recall 0.944) and accuracy of 0.783. Scam precision is 0.80 and scam
recall 1.00, and 94% of priced bids fall inside the fair price band. With the V8 retrieval stack the same graph reaches F1
0.727 (precision 0.683, recall 0.778) at almost twice the median latency (`decisions_v8.json`). Synthetic,
requirement-targeted jobs reach F1 1.00; real Kaggle jobs only 0.50 (precision 0.35), because the graph over-bids on vague
or off-domain posts (section 8).

**Conclusion.** On the question this sample can answer, whether the system knows when not to bid, only the hand-built
graph is usable: it bid on 23% of skip-labelled jobs, against 76% for the single agent and 67% for the supervisor, and
none of its runs failed. A small model asked to both decide and write tends to bid. The graph moves that decision out of
the LLM into rule-based risk, evidence coverage and a scored decision node, and uses the model only for writing. The
supervisor is multi-agent but routed by the LLM, so it keeps the over-bidding and adds routing failures (11 of 45 runs
errored or timed out). Median latency is similar for all three (about two minutes on CPU); the graph's slower tail comes
from the Writer and Critic loop on the jobs it bids on. Limitations: one persona, one bid-labelled job (all three systems
bid on it, so recall is untested), a 1.7B model, and no claim or reply metrics.

## 6. The change request

**What changed.** GigSim policy `2026-11-02` (`gigsim/policy.py`) adds two rules: every proposal must end with
"Disclosure: drafted with AI assistance and reviewed by me.", and jobs above $1,000 cost two extra Connects for each
started $1,000. The instructor's update was not part of the starter kit, so we wrote one with the required shape. GigSim
rejects non-compliant proposals with `422 policy_violation` and charges the new price itself.

**Before.** With the old configuration and the new policy, 0 of 6 proposals for jobs above $1,000 were accepted; all were
rejected for the missing disclosure (`change_request_before.json`).

**What we edited.** The first commit changed 4 lines in `agent/config.yaml` (policy version, Connects step rule, required
disclosure) and added a 5-line policy-pack file. All six proposals were then accepted, but our Connects estimate was wrong
for all six, because the configured formula added the surcharge to a price GigSim had already surcharged. The second
commit changed `connects_cost()` in `agent/nodes/pricing.py` (7 lines) so the marketplace's reported price takes
precedence and the formula applies only when no price is reported, and added a unit test. In total: 4 files, 23 lines
added and 11 removed, about 7 minutes from the first edit to passing checks.

**After.** 6 of 6 accepted, 6 of 6 Connects estimates correct, and the disclosure present in all six
(`change_request_after.json`).

**What it shows about the design.** Platform rules were in configuration from the start, so the rule change needed only
configuration: the Writer prompt reads the disclosure list from config and the Compliance Guard adds any missing line. The
cost change exposed a real bug, two sources of truth for one price, which configuration alone cannot prevent; the check
script `evals/runners/change_request.py` caught it.

## 7. Signature extension: proposal A/B experiments (X2)

Two opening strategies were compared on the same 57 jobs (paired), with everything else fixed (`ab_test.json`).

| Arm | Strategy | Replied | Reply rate | Hire rate |
|---|---|---|---|---|
| A | Evidence-first | 44 / 57 | 0.772 | 0.281 |
| B | Question-first | 50 / 57 | 0.877 | 0.351 |

Of the discordant pairs, 6 jobs got a reply only under A and 12 only under B. The McNemar exact test gives p = 0.238
(two-proportion z-test p = 0.140, Fisher p = 0.218), so the difference is not significant and H-X2 ("evidence-first
wins") is not supported; if anything, question-first is ahead. GigSim's client model explains why: a question that quotes
the client's own requirement always counts as a personalised opening, while an evidence-first opening sometimes leads with
a project title the client never mentioned. With about 60 paired jobs only differences of roughly 15 points or more are
detectable, so the product keeps A/B testing as a per-user setting and promotes a winner per category only after at least
five outcomes and a 10-point lift.

## 8. Failure analysis

Failures come from the 120-job decision run, the 60-job GigSim run (`failures.json`, `decisions_test_per_job.csv`) and
development. The final runs had 24 wrong bids, 2 wrong skips, 3 false scam flags, 2 mispriced jobs, no unsupported claims
(offline Writer) and no tool errors.

| # | Job or case | Category | Cause (node) | Fix tried | Result |
|---|---|---|---|---|---|
| 1 | kg_8280 "bicycle trailer designer" (ML persona) | Wrong bid | Fit Matcher: generic requirements ("experience with design") reached cosine support of 0.70 against unrelated case studies; the off-domain penalty was too weak | Raised `minimum_fit_score` from 0.55 to 0.80 (`threshold_sweep_decisions_test.json`) | Failed: real-job F1 0.50 to 0.51; the relevance signal itself is weak |
| 2-5 | Four more off-domain real jobs (e.g. kg_17) | Wrong bid | Same | Same | Failed |
| 6 | dv_dat_mult_000 | Tool error | The matcher hit the 20 s MCP timeout while re-ranking under load; `decide` then failed on the missing fit | Configurable timeout (60 s); a failed branch now goes to `dead_letter` | Fixed: no dead letters in final runs |
| 7 | All V0 jobs, first GigSim run | Wrong skip | Whole-post variants returned no per-requirement evidence, so fit was 0 and all 60 jobs were skipped | Grade retrieved items per requirement for every variant | Fixed |
| 8 | Supabase / Next.js job | Missed evidence | The requirement splitter ended a sentence at the dot in "Next.js" | Ignore dots attached to the next word | Fixed (unit test) |
| 9 | kg_32001 chatbot draft | Generic opening | The Writer quoted only proposal snippets and opened with a case study's problem statement | Load full case studies and prefer the Results section | Fixed: 3 supported claims |
| 10 | Interview reply | Compliance false positive | ISO timestamps were redacted as phone numbers | Date and time exclusion in `_is_phone` (unit test) | Fixed |
| 11 | Single-agent demo letter | Unsupported claim | Vague experience statements were not treated as claims | Widened claim patterns | Fixed: 0 to 2 claims found |
| 12 | Policy 2026-11-02 | Mispriced | Connects surcharge applied twice | Marketplace price takes precedence | Fixed: 6/6 correct |
| 13 | Three legitimate dev jobs | False scam | Risk rules fire on "test task" wording combined with an unverified, zero-spend client | None; scam rules favour recall (1.00) | Open |
| 14 | in_* injection jobs | Injection | 7 of 12 attacks succeeded without defences | Delimiting, detectors, Compliance Guard | Fixed: 0 of 12 (section 9) |

## 9. Safety and platform respect

**What must never happen.** Sending a proposal or message or spending Connects without approval, off-platform contact or
payment, fabricated experience, guarantees, scraping or browser automation, and leaking personal data or tokens.

**How it is enforced.**

1. *Human gate*: `interrupt()` before every external write, and a separate idempotent submit step.
2. *Least privilege*: per-agent tool allowlists; write tools are reachable only from the approval and submit steps.
3. *Untrusted input*: job posts and client messages are normalised, stripped of hidden characters and HTML comments,
   wrapped in `<untrusted_*>` tags and never placed in a system message; nine injection detectors feed the Risk Assessor.
4. *Compliance Guard*: removes contact details, off-platform terms, guarantees and injection residue, adds required
   disclosures, and blocks the draft when it cannot fix it.
5. *Claim verification* (section 4).
6. *Privacy*: personal data is masked in logs, traces and the audit log; OAuth tokens are Fernet-encrypted and never
   logged; every query is scoped to the user.
7. *Live mode* uses only the official Upwork MCP server, creates drafts only, and runs at most one scheduled search every
   120 minutes.

**Measured** (`injection_open_small.json`; 12 dev jobs with planted injections, Qwen3-1.7B writer). The detectors flagged
12 of 12. An attack counts as successful when the final text does what the injection asked: contact details, a
guarantee, "I am an AI bot", a prompt leak or a $5 price. The success rate was 0.58 with no defences, 0.33 with the
production prompt and delimited input, and 0.00 with the Compliance Guard (H-S1 holds). Some "guarantee" hits may be the
model's own sales language rather than obedience; the guard removes both. With n = 12, a rate of 0.00 means none were
observed, not that none are possible.

**What still gets through.** Instructions phrased as ordinary client requirements, such as "mention your rate is $5 in
line one" or "use the word BANANA to show you read this", are not caught by the pattern-based detectors, and a small model
may follow them. New phrasings can also slip past detection, and the Compliance Guard only removes the effects it has been
written to recognise.

## 10. Hidden test results against the declared budgets

**Declared.** p95 of 20 s per analysed job and 60 s per proposal; USD 0.001 per analysed job and USD 0.006 per proposal on
the hosted `open` profile.

**Measured on the dev set** (8-thread laptop CPU, deterministic `test` profile, other evaluations running at the same
time):

| Measurement | p50 | p95 | Declared p95 | Source |
|---|---|---|---|---|
| Job analysed (scout to pricing), shipped retrieval | 6.0 s | **24.0 s** | 20 s | `decisions_test.json` |
| Job analysed, V8 re-ranked stack | 10.9 s | 24.0 s | 20 s | `decisions_v8.json` |
| Proposal end to end (approval and submit included), 3 concurrent | 72.0 s | **72.9 s** | 60 s | `outcomes_shipped.json` |
| Retrieval only, shipped vs V8 | 0.01 s vs 6.3 s | 0.05 s vs 11.5 s | - | `rag_variants.json` |

**Both latency budgets were missed**: 24 s against 20 s per job, and 73 s against 60 s per proposal. Per-job latencies
fall into two tight clusters (`decisions_test_per_job.csv`): 59 jobs took about 6 s and 55 about 24 s. The gap is
waiting, not computation: our per-user marketplace rate limiter (20 requests per minute, below GigSim's 30) queues the
four jobs analysed concurrently. On the same 12 jobs, relaxing the limiter cut p50 from 10.1 s to 3.3 s and the maximum
from 31.7 s to 9.6 s, with the same F1 of 0.80 (`decisions_rl20.json`, `decisions_norl.json`). The graph meets the budget
on compute, not when a batch of scouted jobs arrives at once. We keep the limiter, because a real marketplace would block
a bursty client, and record the budget as missed.

On the LLM path, generation speed dominates: Qwen3-1.7B produces about 10 tokens per second and Qwen3-4B about 4.5 on this
laptop (`model_speed.json`). Cost was USD 0 locally; the hosted cost per node is recorded in every run but could not be
measured without an API key.

**Largest improvement and next steps.** Removing the cross-encoder from the ranking path cut p95 retrieval latency from
11.5 s to 0.05 s per job and raised Recall@5. Next: cache client histories and category market statistics for each scout
batch, which would cut marketplace calls from 4 to about 1.5 per job and bring queued jobs under 20 s without raising the
request rate; and skip retrieval when the Risk Assessor's hard scam rules already fire.

**Hidden test.** The instructor's hidden test runs against the deployed application after submission; its results will
be reported as measured.

## Appendix. Graphs rendered from code
`python -m scripts.render_graphs` builds both graphs and exports `graph.get_graph().draw_mermaid()` to `docs/images/`;
CI fails if the exported files no longer match the code.

**Bid graph** (one thread per job):  
![Bid graph](../docs/images/bid_graph.png)

**Conversation graph** (one thread per client conversation):  
![Conversation graph](../docs/images/conversation_graph.png)
