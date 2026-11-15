"""Failure-analysis fix trial: sweep thresholds.minimum_fit_score over the SAVED decision-eval rows.

Exact, not an approximation: with budget/risk rules unchanged, raising the minimum only turns bids whose fit is below
the new minimum into watch/skip, so the new prediction is `old == bid and fit >= t`.

    python -m evals.runners.threshold_sweep --source decisions_test
"""

from __future__ import annotations

import argparse
import csv

from evals.runners.common import RESULTS, f1, save


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="decisions_test")
    ns = ap.parse_args()
    rows = list(csv.DictReader(open(RESULTS / f"{ns.source}_per_job.csv", encoding="utf-8")))
    out = []
    for t in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85):
        for subset, rs in (("all", rows), ("real", [r for r in rows if "real" in r["tags"]])):
            tp = fp = fn = 0
            for r in rs:
                gold = r["gold_bid"] == "True"
                pred = r["pred_action"] == "bid" and float(r["fit"] or 0) >= t
                tp += gold and pred
                fp += (not gold) and pred
                fn += gold and not pred
            out.append({"minimum_fit_score": t, "subset": subset, "n": len(rs), **f1(tp, fp, fn)})
    save(f"threshold_sweep_{ns.source}", {"source": ns.source, "rows": out})
    for o in out:
        print(o)


if __name__ == "__main__":
    main()
