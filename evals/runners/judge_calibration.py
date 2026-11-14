"""LLM-judge calibration (B4): the judge is only trusted after agreeing with HUMAN labels.

1) export 30 proposals for labelling:   python -m evals.runners.judge_calibration export --source outcomes_v8_corrective
2) a human (the student) fills `human_score` (1-5, rubric in agent/prompts/judge.md) in evals/datasets/judge_labels.csv
3) score with the judge + report kappa: python -m evals.runners.judge_calibration run --profile open
No numbers are produced until human labels exist.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random

from evals.runners.common import DATASETS, RESULTS, cohen_kappa, jobs_by_id, save, setup_env

LABELS = DATASETS / "judge_labels.csv"


def export(source: str, n: int) -> None:
    rows = list(csv.DictReader(open(RESULTS / f"{source}_proposals.csv", encoding="utf-8")))
    rows = [r for r in rows if r["text"].strip()]
    rng = random.Random(30)
    replied = [r for r in rows if r["replied"] == "True"]
    other = [r for r in rows if r["replied"] != "True"]
    pick = rng.sample(replied, min(len(replied), n // 2)) + rng.sample(other, min(len(other), n - min(len(replied), n // 2)))
    with open(LABELS, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "persona", "job_id", "job_title", "proposal", "human_score", "notes"])
        for i, r in enumerate(pick):
            w.writerow([f"j{i + 1:02d}", r["persona"], r["job_id"], r["title"], r["text"], "", ""])
    print(f"wrote {len(pick)} items to {LABELS}; fill human_score (1-5) before running `run`")


async def run(profile: str) -> None:
    setup_env(profile)
    from pydantic import BaseModel

    from agent import llm
    from agent.safety import wrap_untrusted

    class Score(BaseModel):
        score: int
        reason: str = ""

    rows = list(csv.DictReader(open(LABELS, encoding="utf-8")))
    jobs = jobs_by_id()
    out = []
    for r in rows:
        j = jobs.get(r["job_id"], {})
        res = await llm.structured("judge", "judge", Score, {"job_title": r["job_title"],
                                                             "job": wrap_untrusted("job_post", (j.get("description") or "")[:1500]),
                                                             "proposal": r["proposal"]})
        out.append({"item_id": r["item_id"], "judge": max(1, min(5, res.value.score)), "reason": res.value.reason[:200],
                    "human": int(r["human_score"]) if r["human_score"].strip().isdigit() else None, "model": res.model})
    labelled = [o for o in out if o["human"] is not None]
    payload: dict = {"n_items": len(out), "n_human_labelled": len(labelled), "items": out}
    if len(labelled) >= 30:
        h = [o["human"] for o in labelled]
        jd = [o["judge"] for o in labelled]
        payload.update({
            "kappa_binary_good_ge4": cohen_kappa([int(x >= 4) for x in h], [int(x >= 4) for x in jd]),
            "kappa_quadratic_1to5": cohen_kappa(h, jd, weights="quadratic"),
            "exact_agreement": round(sum(a == b for a, b in zip(h, jd)) / len(h), 4),
            "disagreements": [o for o in labelled if abs(o["human"] - o["judge"]) >= 2][:10],
            "status": "calibrated"})
    else:
        payload["status"] = "awaiting_human_labels"
    save("judge_calibration", payload)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--source", default="outcomes_v8_corrective")
    e.add_argument("--n", type=int, default=30)
    r = sub.add_parser("run")
    r.add_argument("--profile", default="open")
    ns = ap.parse_args()
    if ns.cmd == "export":
        export(ns.source, ns.n)
    else:
        asyncio.run(run(ns.profile))


if __name__ == "__main__":
    main()
