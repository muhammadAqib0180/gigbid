"""Print every headline number from evals/results/*.json compactly (used while writing the report)."""

from __future__ import annotations

import json
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "evals" / "results"


def j(name: str):
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> None:
    d = j("rag_variants")
    if d:
        print(f"RAG n={d['n_jobs']} sha={d['meta']['git_sha']}")
        for r in d["results"]:
            o, t = r["overall"], r["by_tag"]
            tag = {k: t.get(k, {}).get("recall@5") for k in ("exact_tool", "implied", "multi_req", "req>=4", "vague", "real", "synthetic")}
            pp = {p: v["recall@5"] for p, v in r["by_persona"].items()}
            print(f"  {r['variant']:22s} R5={o['recall@5']} MRR={o['mrr']} nDCG={o['ndcg@10']} p50={o['p50_latency_s']} p95={o['p95_latency_s']} {tag} {pp}")
    d = j("decisions_test")
    if d:
        o = d["overall"]
        print("DECISIONS", o["n"], "F1", o["bid_skip"], "acc", o["bid_skip_accuracy"], "scam", o["scam"], "band", o["price_in_fair_band"], o["price_n"],
              "lat", o["p50_latency_s_per_job"], o["p95_latency_s_per_job"])
        for p, m in d["by_persona"].items():
            print("  ", p, m["bid_skip"]["f1"], m["scam"], m["price_in_fair_band"])
        for t, m in d["by_tag"].items():
            print("   tag", t, m["n"], m["bid_skip"]["f1"], m["bid_skip_accuracy"], m["scam"]["recall"])
    for n in ("outcomes_v0_naive", "outcomes_shipped", "outcomes_question_first"):
        d = j(n)
        if d:
            print(n, json.dumps(d["overall"]), d.get("status_counts"))
            for p, m in d["by_persona"].items():
                print("   ", p, m["submitted"], m["reply_rate"], m["hire_rate"], m["unsupported_per_proposal_first_draft"], m["unsupported_per_proposal_final"])
    for n in ("ab_test", "change_request_before", "change_request_after", "injection_open_small", "tool_granularity", "multiagent_compare",
              "model_speed", "single_agent_demo", "judge_calibration"):
        d = j(n)
        if d:
            d = {k: v for k, v in d.items() if k not in {"rows", "transcript", "items", "meta"}}
            if n == "tool_granularity":
                d = {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in d["results"].items()}
            if n == "multiagent_compare":
                d = d.get("summary")
            print(n, json.dumps(d, default=str)[:1500])


if __name__ == "__main__":
    main()
