# ADR 0008 - Absorbing the platform policy update (change request)
**What changed (GigSim policy 2026-11-02, `gigsim/policy.py`):** (1) proposals must carry the line
"Disclosure: drafted with AI assistance and reviewed by me."; (2) jobs above $1,000 cost +2 Connects per started $1,000.
The instructor's own update text was not in the starter kit, so this update is self-authored with the same shape
("a new rule or cost affecting bidding"); if the official one differs, the same mechanism applies.
**What we edit:** `agent/config.yaml` -> `bidding_rules.policy_version`, `connects.per_budget_step/step_from_usd`,
`proposal.required_disclosures`, plus the policy pack text. No Python changes: the Writer prompt receives the
disclosures, the Compliance Guard appends any missing one, and Pricing applies the Connects formula. The diff, the time
it took and the before/after GigSim submit results are in the R&D report section 6.
