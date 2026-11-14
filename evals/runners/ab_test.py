"""X2 signature extension: proposal-strategy A/B test in GigSim with significance tests.

Both arms run on the SAME fixed job set (paired design), so the primary test is McNemar's exact test on the
discordant pairs; a two-proportion z-test and Fisher's exact test are reported for reference.

    python -m evals.runners.ab_test --a outcomes_v8_corrective --b outcomes_question_first
"""

from __future__ import annotations

import argparse
import csv
import json
import math

from evals.runners.common import RESULTS, save


def _rows(name: str) -> dict[str, bool]:
    out = {}
    with open(RESULTS / f"{name}_proposals.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["proposal_id"]:
                out[r["job_id"]] = r["replied"] == "True"
    return out


def two_prop_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0.0
    if se == 0:
        return 0.0, 1.0
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def p(k: int) -> float:
        return math.comb(r1, k) * math.comb(n - r1, c1 - k) / math.comb(n, c1)

    obs = p(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(p(k) for k in range(lo, hi + 1) if p(k) <= obs * (1 + 1e-9)))


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="outcomes_v8_corrective")
    ap.add_argument("--b", default="outcomes_question_first")
    ns = ap.parse_args()
    a, b = _rows(ns.a), _rows(ns.b)
    common = sorted(set(a) & set(b))
    xa, xb = sum(a[j] for j in common), sum(b[j] for j in common)
    n = len(common)
    only_a = sum(a[j] and not b[j] for j in common)
    only_b = sum(b[j] and not a[j] for j in common)
    z, pz = two_prop_z(xa, n, xb, n) if n else (0.0, 1.0)
    res = {
        "arm_a": {"name": ns.a, "strategy": json.loads((RESULTS / f"{ns.a}.json").read_text())["strategy"], "replied": xa, "n": n,
                  "reply_rate": round(xa / n, 4) if n else None},
        "arm_b": {"name": ns.b, "strategy": json.loads((RESULTS / f"{ns.b}.json").read_text())["strategy"], "replied": xb, "n": n,
                  "reply_rate": round(xb / n, 4) if n else None},
        "paired_jobs": n, "discordant": {"a_only": only_a, "b_only": only_b},
        "mcnemar_exact_p": round(mcnemar_exact(only_a, only_b), 4),
        "two_proportion_z": round(z, 3), "two_proportion_p": round(pz, 4),
        "fisher_exact_p": round(fisher_two_sided(xa, n - xa, xb, n - xb), 4) if n else None,
        "min_detectable_note": "With ~75 paired jobs, only differences of roughly 15+ points in reply rate are detectable at alpha=0.05.",
    }
    save("ab_test", res)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
