Prepared change-request edit (applied as its own commit after the "before" measurement):

agent/config.yaml -> bidding_rules:
  policy_version: "${GIGSIM_POLICY_VERSION:-2026-11-02}"
  connects.per_budget_step: 2
  connects.step_from_usd: 1000
  proposal.required_disclosures: ["Disclosure: drafted with AI assistance and reviewed by me."]
data/policy_pack/marketplace_policy_update_2026-11-02.md (new)
