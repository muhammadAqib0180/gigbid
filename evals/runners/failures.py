"""Collect failed dev jobs into the failure taxonomy (report section 8): wrong skip, wrong bid, missed scam,
false scam, mispriced, unsupported claim, generic opening, injection, tool error.

    python -m evals.runners.failures --decisions decisions_test --outcomes outcomes_shipped
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict

from evals.runners.common import RESULTS, jobs_by_id, save


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", default="decisions_test")
    ap.add_argument("--outcomes", default="outcomes_shipped")
    ns = ap.parse_args()
    jobs = jobs_by_id()
    cats: dict[str, list[dict]] = defaultdict(list)
    with open(RESULTS / f"{ns.decisions}_per_job.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            gold_bid, pred = r["gold_bid"] == "True", r["pred_action"]
            gold_scam, pred_scam = r["gold_scam"] == "True", r["pred_scam"] == "True"
            j = jobs.get(r["job_id"], {})
            base = {"job_id": r["job_id"], "persona": r["persona"], "title": j.get("title", "")[:80], "tags": r["tags"],
                    "fit": r["fit"], "risk": r["risk"], "reason": r["reason"], "gold_reason": r["label_reason"]}
            if gold_scam and not pred_scam:
                cats["missed_scam"].append(base)
            elif pred_scam and not gold_scam:
                cats["false_scam"].append(base)
            elif gold_bid and pred != "bid":
                cats["wrong_skip"].append(base)
            elif not gold_bid and pred == "bid":
                cats["wrong_bid"].append(base)
            if r["in_band"] == "False":
                cats["mispriced"].append({**base, "price": r["price"]})
    p = RESULTS / f"{ns.outcomes}_proposals.csv"
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["unsupported_final"] not in ("", "0", "None") and float(r["unsupported_final"] or 0) > 0:
                    cats["unsupported_claim"].append({"job_id": r["job_id"], "persona": r["persona"], "title": r["title"][:80]})
                if r["status"] in {"dead_letter", "needs_attention", "error"}:
                    cats["tool_error_or_halt"].append({"job_id": r["job_id"], "persona": r["persona"], "status": r["status"]})
                if r["text"] and r["text"].lower().startswith(("dear", "hi", "hello", "i am excited")):
                    cats["generic_opening"].append({"job_id": r["job_id"], "persona": r["persona"]})
    summary = {k: len(v) for k, v in cats.items()}
    save("failures", {"counts": summary, "examples": {k: v[:6] for k, v in cats.items()}})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
