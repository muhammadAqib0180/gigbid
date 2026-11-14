# ADR 0006 - Approval with interrupt() and a separate submit node
`approval` calls `interrupt(payload)`; `submit` is the next node. A node that called `interrupt()` re-runs from its
start on resume, so no side effect may live inside it. Payload = draft, evidence behind every claim, risk report, price
rationale, `dry_run` preview (computed in `prepare_approval` so it is not re-fetched). Edits are diffed, fed to the style
memory promotion rule and loop back through Compliance. Autonomy may auto-skip; nothing auto-sends.
