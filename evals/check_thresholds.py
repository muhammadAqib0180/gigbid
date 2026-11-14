"""CI eval gate (E2): fail if unsupported claims rise or bid-or-skip F1 drops past the thresholds in
evals/thresholds.yaml, using the smoke-eval results written by `make smoke-eval`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    t = yaml.safe_load((ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8"))
    dec = json.loads((ROOT / "evals" / "results" / "smoke_decisions.json").read_text(encoding="utf-8"))
    out = json.loads((ROOT / "evals" / "results" / "smoke_outcomes.json").read_text(encoding="utf-8"))
    f1 = dec["overall"]["bid_skip"]["f1"]
    scam_recall = dec["overall"]["scam"]["recall"]
    unsup = out["overall"]["unsupported_per_proposal_final"] or 0.0
    checks = [
        ("bid_skip_f1", f1, f1 >= t["min_bid_skip_f1"], f">= {t['min_bid_skip_f1']}"),
        ("scam_recall", scam_recall, scam_recall >= t["min_scam_recall"], f">= {t['min_scam_recall']}"),
        ("unsupported_claims_per_proposal", unsup, unsup <= t["max_unsupported_claims_per_proposal"], f"<= {t['max_unsupported_claims_per_proposal']}"),
    ]
    ok = True
    for name, val, passed, rule in checks:
        print(f"{'PASS' if passed else 'FAIL'} {name} = {val} (rule {rule})")
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
