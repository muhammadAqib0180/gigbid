"""Decision evaluation (B4): bid-or-skip F1, scam detection precision/recall, price inside the fair band,
latency/tokens/cost per job analysed. Runs the real agent nodes (scout -> analyst || risk || matcher -> decide
-> pricing) through the in-process MCP servers against an in-process GigSim.

    python -m evals.runners.decision_eval --n 200 --profile test
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
    f1,
    jobs_by_id,
    load_dev,
    mean,
    pct,
    public_job,
    sample,
    save,
    setup_env,
)


async def analyse(persona: str, job: dict) -> dict:
    from agent.nodes.analyst import analyst
    from agent.nodes.decision import decide
    from agent.nodes.fit_matcher import fit_matcher
    from agent.nodes.pricing import pricing
    from agent.nodes.risk_assessor import risk_assessor
    from agent.profile import merged_profile
    from agent.state import merge_usage

    state = {"thread_id": f"eval:{job['job_id']}", "user_id": "eval", "persona_id": persona, "job_id": job["job_id"], "job": job,
             "trace_id": "eval", "user_profile": merged_profile(persona), "steps": 0}
    t0 = time.perf_counter()
    outs = await asyncio.gather(analyst(state, None, None), risk_assessor(state, None, None), fit_matcher(state, None, None))
    usage: dict = {}
    for o in outs:
        state.update({k: v for k, v in o.items() if k not in {"usage", "steps"}})
        usage = merge_usage(usage, o.get("usage"))
    d = await decide(state, None, None)
    state.update(d)
    if d["decision"]["action"] == "bid":
        p = await pricing(state, None, None)
        state.update({k: v for k, v in p.items() if k not in {"usage", "steps"}})
    lat = time.perf_counter() - t0
    return {"state": state, "latency_s": lat, "usage": usage}


async def main_async(args) -> None:
    setup_env(args.profile)
    from agent.llm import total_tokens, total_usd

    jobs_map = jobs_by_id()
    rows = []
    sem = asyncio.Semaphore(args.concurrency)
    t_start = time.time()

    async def one(persona: str, gold: dict) -> None:
        async with sem:
            if rows and len(rows) % 20 == 0:
                print(f"  {len(rows)} jobs done ({time.time() - t_start:.0f}s)", flush=True)
            job = public_job(jobs_map[gold["job_id"]])
            try:
                r = await analyse(persona, job)
            except Exception as exc:  # noqa: BLE001
                rows.append({"persona": persona, "job_id": job["job_id"], "error": f"{type(exc).__name__}: {exc}"[:200], "gold": gold})
                return
            st = r["state"]
            price = st.get("price") or {}
            band = gold["fair_price"]
            in_band = None
            if st["decision"]["action"] == "bid" and gold["gold_bid"] and price:
                in_band = price.get("unit") == band["unit"] and band["low"] * 0.999 <= price["amount"] <= band["high"] * 1.001
            rows.append({"persona": persona, "job_id": job["job_id"], "tags": gold["tags"], "gold_bid": gold["gold_bid"],
                         "pred_action": st["decision"]["action"], "gold_scam": gold["gold_scam"], "pred_scam": bool(st["risk"]["is_scam"]),
                         "risk": st["risk"]["score"], "fit": st["fit"]["score"], "price": price.get("amount"), "price_unit": price.get("unit"),
                         "band": band, "in_band": in_band, "latency_s": r["latency_s"], "tokens": total_tokens(r["usage"]),
                         "usd": total_usd(r["usage"]), "reason": st["decision"]["reasons"][:1], "label_reason": gold["label_reason"]})

    tasks = []
    for persona in PERSONAS:
        for g in sample(load_dev(persona), args.n):
            tasks.append(one(persona, g))
    print(f"{len(tasks)} jobs")
    t0 = time.time()
    await asyncio.gather(*tasks)
    print(f"done in {time.time() - t0:.0f}s")
    ok = [r for r in rows if "error" not in r]

    def metrics(rs: list[dict]) -> dict:
        tp = sum(r["gold_bid"] and r["pred_action"] == "bid" for r in rs)
        fp = sum((not r["gold_bid"]) and r["pred_action"] == "bid" for r in rs)
        fn = sum(r["gold_bid"] and r["pred_action"] != "bid" for r in rs)
        stp = sum(r["gold_scam"] and r["pred_scam"] for r in rs)
        sfp = sum((not r["gold_scam"]) and r["pred_scam"] for r in rs)
        sfn = sum(r["gold_scam"] and not r["pred_scam"] for r in rs)
        band = [r["in_band"] for r in rs if r["in_band"] is not None]
        return {"n": len(rs), "bid_skip": f1(tp, fp, fn),
                "bid_skip_accuracy": round(sum((r["pred_action"] == "bid") == r["gold_bid"] for r in rs) / len(rs), 4) if rs else None,
                "scam": f1(stp, sfp, sfn), "price_in_fair_band": round(sum(band) / len(band), 4) if band else None, "price_n": len(band),
                "p50_latency_s_per_job": pct([r["latency_s"] for r in rs], 0.5), "p95_latency_s_per_job": pct([r["latency_s"] for r in rs], 0.95),
                "tokens_per_job": mean([r["tokens"] for r in rs]), "usd_per_job": mean([r["usd"] for r in rs])}

    by_persona = defaultdict(list)
    by_tag = defaultdict(list)
    for r in ok:
        by_persona[r["persona"]].append(r)
        for t in r["tags"]:
            by_tag[t].append(r)
    name = args.out or f"decisions_{args.profile or 'test'}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / f"{name}_per_job.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["persona", "job_id", "tags", "gold_bid", "pred_action", "gold_scam", "pred_scam", "risk", "fit", "price", "in_band", "latency_s", "reason", "label_reason"])
        for r in ok:
            w.writerow([r["persona"], r["job_id"], "|".join(r["tags"]), r["gold_bid"], r["pred_action"], r["gold_scam"], r["pred_scam"],
                        r["risk"], r["fit"], r["price"], r["in_band"], round(r["latency_s"], 3), r["reason"], r["label_reason"]])
    save(name, {"overall": metrics(ok), "by_persona": {p: metrics(v) for p, v in by_persona.items()},
                "by_tag": {t: metrics(v) for t, v in sorted(by_tag.items())}, "errors": [r for r in rows if "error" in r][:20],
                "n_errors": len(rows) - len(ok)})
    m = metrics(ok)
    print("bid/skip F1", m["bid_skip"]["f1"], "scam P/R", m["scam"]["precision"], m["scam"]["recall"], "price in band", m["price_in_fair_band"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="jobs per persona")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
