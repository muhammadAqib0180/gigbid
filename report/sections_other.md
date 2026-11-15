## 3. R&D question A - tool granularity

**Hypothesis (pre-registered).** H-A1: our task-oriented tool set beats both a fine-grained set (17 narrow tools) and a
coarse set (3 tools with an `action` argument) on tool-selection accuracy, with the coarse set worst on arguments. H-A2:
the fine-grained set costs the most tokens.

**Setup.** {{A_N}} tasks with known correct calls (10 intents x instances built from real dev-set ids: search jobs,
fetch a job, check a client, Connects balance, market rates, portfolio evidence, open a case study, free slots, read a
thread, preview a proposal). The three tool sets are bound to the same model; we score the **first** tool call.
Tools are never executed. Model: {{A_MODEL}} (CPU, `open_small` profile) - the hosted `open` profile reproduces this with
`make eval-llm`. Source: `evals/results/tool_granularity.json`.

{{A_TABLE}}

**Conclusion.** {{A_CONCLUSION}}

## 5. R&D question C - single agent vs prebuilt supervisor vs our graph

**Setup.** The same jobs and the same model for (a) one ReAct agent holding the read tools (`create_react_agent`, prompt
`agent/prompts/single_agent.md`), (b) `langgraph-supervisor` with a marketplace researcher, a portfolio researcher and
a writer, (c) the GigBid bid graph. Every final letter goes through the same claim verifier, the same compliance rules
and the same simulated client. Source: `evals/results/multiagent_compare.json`.

{{C_TABLE}}

**Decisions with the rule-based analysis (the deployed graph's cheap path).** On {{DEC_N}} dev jobs the graph's
analysis nodes (`decision_eval`, profile `test`) reach bid/skip F1 {{DEC_F1}}, scam precision {{DEC_SP}} and recall
{{DEC_SR}}, price inside the fair band {{DEC_BAND}} (`evals/results/decisions_test.json`); the same graph with the V8
retrieval stack gives F1 {{DEC_V8_F1}} (`decisions_v8.json`).

**Conclusion.** {{C_CONCLUSION}}

## 6. The change request

**What changed.** GigSim policy `2026-11-02` (`gigsim/policy.py`): proposals must carry "Disclosure: drafted with AI
assistance and reviewed by me."; jobs above $1,000 cost +2 Connects per started $1,000. The starter kit did not contain
the instructor's update, so this one is self-authored with the required shape; GigSim rejects non-compliant submissions
with `422 policy_violation` and charges the new Connects price server-side.

**Before the edit** (`evals/results/change_request_before.json`): {{CR_BEFORE}}.
**What we edited**: one commit, {{CR_DIFF}} - `agent/config.yaml` (`bidding_rules.policy_version`,
`connects.per_budget_step`, `connects.step_from_usd`, `proposal.required_disclosures`) and a new policy-pack file. No
Python, prompt or test changed: the Writer prompt receives the disclosures from config, the Compliance Guard appends any
missing one, Pricing applies the formula.
**After** (`change_request_after.json`): {{CR_AFTER}}. Time from reading the rule to green: {{CR_TIME}}.
**What it says about the design.** Platform rules were data from day one (`bidding_rules` in config, policy pack as
text), so a cost or rule change is a config diff plus a re-run of the check, not a code change.

## 7. Signature extension - X2 proposal experiments

Two strategies (evidence-first vs question-first openings) on the same {{X2_N}} jobs (paired), everything else fixed.
{{X2_RESULT}} Primary test McNemar exact on discordant pairs; z-test and Fisher reported (`evals/results/ab_test.json`).
The strategy is a per-user setting (Settings -> Proposal strategy, including "A/B both"), stored on each pipeline card,
shown in Analytics, and fed to outcome memory, which promotes a per-category winner only after >= 5 outcomes and a
>= 10-point lift (docs/EXTENSION.md).

## 8. Failure analysis

{{FAILURES}}

## 10. Hidden test results against the declared budgets

Declared (config `budgets.declared`): p95 latency 20 s per job analysed, 60 s per proposal; USD 0.001 per job analysed,
USD 0.006 per proposal (open profile).

Measured on the dev set, CPU laptop, `test` profile (no LLM tokens): {{BUDGET_MEASURED}}. LLM cost on the hosted `open`
profile was not measured because no API key was available during development; the open-profile token counts per node
are logged in every trace and run record, and the analytics screen reports them on the deployment.

The instructor's hidden-test run happens after submission against the deployed URL; this section is left for those
numbers, reported as measured, without excuses. The optimisation that helped most: dropping the cross-encoder from the
ranking path (p95 retrieval ~11 s -> ~0.14 s per job with better recall).
