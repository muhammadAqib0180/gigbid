# Signature extension - X2 Proposal experiments

**What:** two proposal strategies run as an A/B test in GigSim, with a significance test on reply rate.

| Arm | Strategy | What changes |
|---|---|---|
| A | `evidence_first` | the opening sentence names the client's ask and leads with the most relevant *proven* past result |
| B | `question_first` | the opening asks a sharp question about the client's goal, then gives the evidence |

Everything else is held fixed: same jobs (paired design), same retrieval (`v8_corrective`), same Critic / Compliance,
same price logic, same seeded simulated clients.

**How it is wired:** `experiments.proposal_strategy` in `agent/config.yaml` (or per user in Settings: Evidence first /
Question first / A/B). In `ab` mode `agent/nodes/writer.py::strategy_for` assigns a strategy deterministically from the
job id. The strategy is stored on each draft and on the pipeline card, so Analytics shows reply rate per strategy and
the outcome memory can promote the winner per category (promotion rule: >= 5 outcomes, >= 10-point lift).

**How it is measured:**
```
python -m evals.runners.gigsim_outcomes --n 25 --variant v8_corrective --strategy evidence_first --out outcomes_v8_corrective
python -m evals.runners.gigsim_outcomes --n 25 --variant v8_corrective --strategy question_first --out outcomes_question_first
python -m evals.runners.ab_test --a outcomes_v8_corrective --b outcomes_question_first
```
Primary test: McNemar's exact test on discordant pairs (same jobs in both arms); two-proportion z and Fisher's exact
reported for reference. Results: `evals/results/ab_test.json`, discussed in the R&D report section 7.

**Limits:** the simulated client rewards job-specific openings and penalises generic ones whichever strategy is used, so
this measures the *opening style* effect inside one client model; it is not evidence about real clients.
