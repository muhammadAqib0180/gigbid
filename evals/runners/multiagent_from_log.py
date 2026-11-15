"""Rebuild evals/results/multiagent_compare.json from the per-job lines of a stopped multiagent_compare run.

The 2026-11-15 CPU run (profile open_small) was stopped after 45 jobs: a sampling bug (now fixed) had queued every
skip-labelled dev job of the first persona. Its per-job result lines survive in evals/results/multiagent_compare_log.txt
(`<system> <job_id> bid|skip [err] <latency>s`); claim, reply and token metrics were only held in memory and are lost,
so they are reported as null.

    python -m evals.runners.multiagent_from_log
"""

from __future__ import annotations

import re

from evals.runners.common import PERSONAS, RESULTS, load_dev, mean, pct, save

LINE = re.compile(r"^(graph|single|supervisor) (\S+) (bid|skip) (err)? *(\d+)s$")


def main() -> None:
    gold = {r["job_id"]: (p, r) for p in PERSONAS for r in load_dev(p)}
    rows: dict[str, list[dict]] = {"graph": [], "single": [], "supervisor": []}
    for line in (RESULTS / "multiagent_compare_log.txt").read_text(encoding="utf-8").splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        s, job, act, err, lat = m.groups()
        persona, g = gold[job]
        rows[s].append({"persona": persona, "job_id": job, "gold_bid": bool(g["gold_bid"]), "gold_scam": bool(g.get("gold_scam")),
                        "pred_bid": act == "bid", "error": "error or timeout (message not logged)" if err else None,
                        "latency_s": float(lat), "unsupported": None, "replied": None, "tokens": None})
    summary = {}
    for s, rs in rows.items():
        ok = [x for x in rs if not x["error"]]
        skip_gold = [x for x in rs if not x["gold_bid"]]  # accuracy and false-bid rate exclude errored runs
        summary[s] = {"n": len(rs), "errors": len(rs) - len(ok),
                      "bid_skip_accuracy": mean([float(x["pred_bid"] == x["gold_bid"]) for x in ok]),
                      "false_bid_rate_on_skip_labelled": mean([float(x["pred_bid"]) for x in skip_gold if not x["error"]]),
                      "scams_in_sample": sum(1 for x in rs if x["gold_scam"]),
                      "gold_bid_jobs_bid": sum(1 for x in rs if x["gold_bid"] and x["pred_bid"]),
                      "gold_bid_jobs": sum(1 for x in rs if x["gold_bid"]),
                      "scam_recall": None, "unsupported_per_proposal": None, "violations_in_final_text": None,
                      "simulated_reply_rate": None, "tokens_per_job": None,
                      "p50_latency_s": pct([x["latency_s"] for x in rs], 0.5), "p95_latency_s": pct([x["latency_s"] for x in rs], 0.95)}
    save("multiagent_compare", {"systems": list(rows), "summary": summary, "rows": rows, "complete": False,
                                "note": "rebuilt from evals/results/multiagent_compare_log.txt (run stopped after 45 jobs; "
                                        "1 bid-labelled + 44 skip-labelled jobs, persona ai_ml_engineer; claim/reply/token "
                                        "metrics not recorded)"})
    for s, m in summary.items():
        print(s, m)


if __name__ == "__main__":
    main()
