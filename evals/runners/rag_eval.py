"""Retrieval evaluation (B4): project-level evidence Recall@5, MRR, nDCG@10 per variant, persona and job type.

Evaluation unit = portfolio PROJECT: a retrieved chunk counts for every project it belongs to (a case study,
its README, its code files and the past proposals citing it are different descriptions of the same project).
Gold projects come from the dev set (rule-based labels, scripts/build_gigsim_data.py).

    python -m evals.runners.rag_eval --set main            # V0..V8
    python -m evals.runners.rag_eval --set ablation        # best stack minus one component
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import time
from collections import defaultdict

from evals.runners.common import (
    PERSONAS,
    RESULTS,
    jobs_by_id,
    load_dev,
    mean,
    mrr,
    ndcg_at,
    pct,
    public_job,
    recall_at,
    sample,
    save,
    setup_env,
)

MAIN = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector", "v6_contextual", "v7_hyde", "v8_corrective"]
ABLATION = ["v8_corrective", "stack_no_corrective", "stack_no_rerank", "stack_no_hybrid", "stack_no_decompose", "stack_no_outcome",
            "stack_no_multivector"]


async def run_variant(name: str, jobs: list[tuple[str, dict, dict]]) -> dict:
    from rag.retriever import get_pipeline

    pipe = get_pipeline(name)
    per_persona: dict[str, list[dict]] = defaultdict(list)
    rows = []
    for persona, job, gold in jobs:
        t0 = time.perf_counter()
        res = await pipe.retrieve(persona, job)
        lat = time.perf_counter() - t0
        ranked = res.ranked_projects()
        g = gold["gold_projects"]
        m = {"recall@5": recall_at(ranked, g, 5), "mrr": mrr(ranked, g), "ndcg@10": ndcg_at(ranked, g, 10), "latency_s": lat,
             "n_requirements": len(res.requirements), "tags": gold["tags"], "job_id": job["job_id"], "persona": persona,
             "weak": len(res.weak_requirements)}
        per_persona[persona].append(m)
        rows.append(m)

    def agg(ms: list[dict]) -> dict:
        return {"n": len(ms), "recall@5": mean([m["recall@5"] for m in ms]), "mrr": mean([m["mrr"] for m in ms]),
                "ndcg@10": mean([m["ndcg@10"] for m in ms]), "p50_latency_s": pct([m["latency_s"] for m in ms], 0.5),
                "p95_latency_s": pct([m["latency_s"] for m in ms], 0.95)}

    by_tag: dict[str, list[dict]] = defaultdict(list)
    for m in rows:
        for t in m["tags"]:
            by_tag[t].append(m)
        by_tag["req>=4" if m["n_requirements"] >= 4 else "req<4"].append(m)
    return {"variant": name, "overall": agg(rows), "by_persona": {p: agg(v) for p, v in per_persona.items()},
            "by_tag": {t: agg(v) for t, v in sorted(by_tag.items())}, "_rows": rows}


async def main_async(args) -> None:
    setup_env(args.profile)
    from rag.retriever import variants

    names = {"main": MAIN, "ablation": ABLATION, "all": MAIN + ABLATION[1:]}[args.set] if not args.variants else args.variants.split(",")
    known = variants()
    jobs_map = jobs_by_id()
    jobs: list[tuple[str, dict, dict]] = []
    for persona in PERSONAS:
        rows = [r for r in load_dev(persona) if r["gold_projects"] and not r["gold_scam"]]
        for r in sample(rows, args.n):
            jobs.append((persona, public_job(jobs_map[r["job_id"]]), r))
    print(f"{len(jobs)} jobs x {len(names)} variants", flush=True)
    import json
    import time as _t

    out_name = args.out or f"rag_{args.set}"
    partial = RESULTS / f"{out_name}.partial.jsonl"
    done = {}
    if partial.exists() and args.resume:
        for line in partial.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done[r["variant"]] = r
    results = []
    for name in names:
        if name in done:
            results.append(done[name])
            print("resume", name, flush=True)
            continue
        t_v = _t.time()
        if name not in known:
            print("skip unknown", name)
            continue
        if name == "v7_hyde" and args.hyde_n is not None:
            sub = [j for i, j in enumerate(jobs) if i % max(1, len(jobs) // args.hyde_n) == 0][: args.hyde_n]
            r = await run_variant(name, sub)
        else:
            r = await run_variant(name, jobs)
        print(f"{name:22s} R@5={r['overall']['recall@5']} MRR={r['overall']['mrr']} nDCG@10={r['overall']['ndcg@10']} "
              f"p95={r['overall']['p95_latency_s']}s n={r['overall']['n']} ({_t.time() - t_v:.0f}s)", flush=True)
        results.append(r)
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(partial, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / f"{out_name}_per_job.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "persona", "job_id", "recall@5", "mrr", "ndcg@10", "latency_s", "n_requirements", "tags"])
        for r in results:
            for m in r["_rows"]:
                w.writerow([r["variant"], m["persona"], m["job_id"], round(m["recall@5"], 4), round(m["mrr"], 4), round(m["ndcg@10"], 4),
                            round(m["latency_s"], 4), m["n_requirements"], "|".join(m["tags"])])
    for r in results:
        r.pop("_rows", None)
    partial.unlink(missing_ok=True)
    save(out_name, {"n_jobs": len(jobs), "unit": "project", "results": results,
                    "notes": "Gold labels are rule-based (skill overlap with synthetic persona projects); see docs/DATA_CARD.md."})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="main", choices=["main", "ablation", "all"])
    ap.add_argument("--variants")
    ap.add_argument("--n", type=int, default=None, help="jobs per persona (default: all with gold evidence)")
    ap.add_argument("--hyde-n", type=int, default=None, help="subsample for V7 (LLM per query)")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--out")
    ap.add_argument("--resume", action="store_true", help="reuse variants already in <out>.partial.jsonl")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
