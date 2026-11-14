# Data card

GigBid's simulator (GigSim), persona portfolios and evaluation sets combine **real public job-market data**
(Kaggle) with **synthetic data generated for this project**. The starter kit shipped without the
instructor's GigSim, persona corpora or dev set (only 2 sample jobs), so everything below was built here.
Every synthetic record carries `synthetic: true` and/or a `source: synthetic:<generator>` field; every real
record carries `source: kaggle:<dataset>`.

## 1. Sources, licences and attribution

| Dataset (Kaggle) | Licence | Rows read | Used for | Real / synthetic |
|---|---|---|---|---|
| ahmedmyalo / *upwork-freelance-jobs-60k* | Apache-2.0 | 60,544 usable (desc >= 80 chars) of 63,950 | job titles, descriptions, skills (Category_1-9), experience level, budget / hourly range, **Connects cost**, client attributes (payment verified, spend, rating, feedback count, country) | real |
| asaniczka / *upwork-job-postings-dataset-2024-50k-records* | ODC-By 1.0 | 53,058 | market statistics: fixed budgets, posted hourly ranges by category | real |
| asaniczka / *all-jobs-on-upwork-200k-plus* (3 files) | ODC-By 1.0 | 826,328 (all files, incl. overlap) | market statistics | real |
| asaniczka / *freelance-contracts-dataset-1-3-million-entries* | ODC-By 1.0 | 491,652 contracts with an hourly rate in [3, 300] | **paid** hourly rate percentiles by category | real |
| sarveshchhetri / *freelancer-success-earnings-and-churn-prediction* | Apache-2.0 | 5k-row survey | sanity band for persona rates only (it appears synthetic itself - noted in `market_stats.json`) | real-but-synthetic-looking |
| adityammantri / *trial-1* | "unknown" on Kaggle | downloaded, **not used** | licence unknown, content not needed | - |

Attribution: data from the four asaniczka datasets is used under the Open Data Commons Attribution License
(ODC-By 1.0) - "Contains information from Upwork job postings / contracts datasets by asaniczka on Kaggle".
Apache-2.0 datasets are credited above. Raw downloads live in `data/raw/` (git-ignored); only derived seed
files are committed. No personal data of freelancers is used; client records keep only aggregate attributes
(country, spend, rating) and get synthetic ids.

## 2. What was generated (synthetic)

| Artefact | Generator | Count | Notes |
|---|---|---|---|
| 3 freelancer personas (AI/ML engineer, full-stack web, data analyst) | `scripts/persona_specs.py` + `scripts/generate_personas.py` | 18 projects each | fictional names marked "(synthetic)" |
| case studies (Markdown) | same | 54 | **implied skills are described, never named** (e.g. "slow steps run on a background worker queue" for Celery) |
| repos: README + code | same | 54 repos, ~4 files each | README lists only the explicit stack; implied skills appear only as imports / config in code (tests multi-vector retrieval) |
| CV (PDF) | fpdf2 | 3 | exercises the PDF loader |
| client reviews | same | 36 | |
| past proposals with outcome | same | 450 (150 / persona) | job titles are **real** Kaggle titles; texts synthetic; outcomes (won / replied / ignored) drawn from a logistic model of relevance, personalisation, metrics and length - 26-42% got a reply or win per persona |
| scams | `scripts/build_gigsim_data.py` (12 templates) | 90 dev + 36 stream | half "disguised": a real job description with the scam ask appended |
| planted prompt injections | same (8 templates incl. hidden HTML comment and zero-width obfuscation) | 60 dev + 24 stream | injected into **real** job texts |
| duplicate reposts | same | 20 stream | same text, retitled ("(repost)", "- URGENT") |
| requirement-targeted jobs | same | 150 dev | multi-requirement, exact tool names, implied needs, vague posts |
| client hidden preferences | same | per job | must-have skills, budget ceiling (1.0-1.25 x budget), dislikes generic openings (p=0.65), prefers short (p=0.4), responsiveness |
| client ids, history details, review snippets | same | 2,370 clients | attributes from the real row, ids and history detail synthetic |

## 3. GigSim seed (`gigsim/seed/`)

| File | Content |
|---|---|
| `jobs.jsonl` | 2,540 jobs: 1,500 *historical* (real, closed), 600 *dev* (evaluation), 440 *stream* (released 6 per 30 simulated minutes: real + scams + injections + reposts) |
| `clients.json` | 2,370 clients |
| `hidden.json` | per-job hidden client preferences and labels - read only by the simulator, never exposed by its API |
| `market_stats.json` | per category: fixed-budget p10-p90, posted hourly p50, **paid** hourly p25-p75 with n |
| `freelancers.json` | the three persona accounts and Connects balances |

Categories are assigned by keyword rules (`category_of` in `scripts/build_gigsim_data.py`): ml_ai, web_dev,
data_analytics, marketing, design_3d, other.

## 4. Dev evaluation set (`evals/datasets/dev_<persona>.jsonl`, 200 jobs / persona)

Composition per persona: 70 real in-domain + 30 real off-domain Kaggle jobs, 50 synthetic targeted jobs
(15 multi-requirement, 15 exact-tool, 12 implied, 8 vague), 30 scams (15 disguised), 20 real jobs with a planted
injection. Labels per job:

* `gold_bid` - not a scam AND skill coverage >= 0.5 with >= 1 gold project (or a targeted job) AND the budget clears the persona floor;
* `gold_scam`; `gold_projects` - up to 5 persona projects whose explicit + implied skills best cover the job's
  skills (broad skills expanded, e.g. "data visualization" -> Power BI, Tableau, ...); `fair_price` band;
* `tags` (real/synthetic, in/off domain, multi_req, exact_tool, implied, vague, scam, disguised, injection) and `label_reason`.

| Persona | Jobs | gold bid | scams | with gold evidence | skip: low fit | skip: budget |
|---|---|---|---|---|---|---|
| ai_ml_engineer | 200 | 61 | 30 | 136 | 73 | 36 |
| fullstack_web | 200 | 58 | 30 | 134 | 85 | 27 |
| data_analyst | 200 | 60 | 30 | 133 | 83 | 27 |

**Labels are rule-based ("silver"), not human.** They are deterministic and reproducible
(`python -m scripts.build_gigsim_data`, seed 2026) but encode our own definition of fit; a human spot-check of
30 labels is listed as a follow-up in the report. A held-out "hidden-like" set is generated with a different
seed at evaluation time and never committed.

## 5. Preprocessing
Descriptions truncated to 2,200 chars; HTML entities as provided; skills canonicalised through `agent/skills.py`
(aliases such as "Microsoft Power BI" -> "Power BI"); budgets parsed from strings ("$2,500 " -> 2500); fixed budgets
outside $5-$100k and hourly rates outside $3-$300 dropped from statistics; the 60k CSV shipped as a zip
mislabelled `.csv` and was unzipped.

## 6. Known limitations and biases
* Kaggle jobs are a 2023-2024 snapshot, English-only, skewed to US clients and to web/marketing categories (ml_ai is only 2.7k of 60.5k rows).
* Client hidden preferences and the reply model are our assumptions (`gigsim/sim.py`); GigSim reply rates measure
  agreement with that model, not real client behaviour.
* Persona corpora are template-generated: phrasing is more regular than real portfolios, which flatters BM25 and
  makes claim verification easier than on real data.
* Dev labels are rule-based; `low_fit` vs `bid` near the 0.5 coverage boundary is noisy.
* Synthetic scams follow 12 templates; real scams are more varied, so scam recall on the dev set is optimistic.

## 7. Handling
No real client data from live mode is stored in the repo. Raw Kaggle files are git-ignored. GigSim and persona data are
synthetic or public and may be shown publicly.
