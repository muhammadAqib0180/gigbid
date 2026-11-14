"""Render the README / report tables FROM evals/results/*.json (CI rule: every number traces to a results file).

    python -m scripts.render_results           # rewrite tables between <!-- results:NAME --> markers in README.md
    python -m scripts.render_results --check   # CI: fail if README tables are stale
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"
README = ROOT / "README.md"


def _load(name: str) -> dict | None:
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _f(x, nd=3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def rag_table() -> str:
    d = _load("rag_variants")
    if not d:
        return "_not run yet_"
    o_v0 = _load("outcomes_v0_naive") or {}
    o_best = _load("outcomes_v8_corrective") or {}
    rows = ["| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal (first draft -> final) | GigSim reply rate | p95 retrieval latency (s) | Cost / proposal (USD) |",
            "|---|---|---|---|---|---|---|---|"]
    for r in d["results"]:
        o = r["overall"]
        out = {"v0_naive": o_v0, "v8_corrective": o_best}.get(r["variant"], {}).get("overall", {})
        unsup = f"{_f(out.get('unsupported_per_proposal_first_draft'), 2)} -> {_f(out.get('unsupported_per_proposal_final'), 2)}" if out else ""
        rows.append(f"| {r['variant']} | {_f(o['recall@5'])} | {_f(o['mrr'])} | {_f(o['ndcg@10'])} | {unsup} | {_f(out.get('reply_rate'), 3) if out else ''} | "
                    f"{_f(o['p95_latency_s'], 2)} | {_f(out.get('usd_per_proposal'), 4) if out else ''} |")
    rows.append(f"\n_n = {d['n_jobs']} dev jobs with gold evidence (project-level); source `evals/results/rag_variants.json` @ {d['meta']['git_sha']}._")
    return "\n".join(rows)


def decision_table() -> str:
    d = _load("decisions_test")
    if not d:
        return "_not run yet_"
    rows = ["| Slice | n | Bid/skip F1 | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) |", "|---|---|---|---|---|---|---|"]
    for name, m in [("overall", d["overall"])] + list(d["by_persona"].items()):
        rows.append(f"| {name} | {m['n']} | {_f(m['bid_skip']['f1'])} | {_f(m['scam']['precision'])} | {_f(m['scam']['recall'])} | "
                    f"{_f(m['price_in_fair_band'])} | {_f(m['p95_latency_s_per_job'], 2)} |")
    rows.append(f"\n_source `evals/results/decisions_test.json` @ {d['meta']['git_sha']}._")
    return "\n".join(rows)


def multiagent_table() -> str:
    d = _load("multiagent_compare")
    if not d:
        return "_not run yet (needs an LLM endpoint; see docs/RUNBOOK.md)_"
    rows = ["| System | n | Bid/skip accuracy | Unsupported claims / proposal | Violations left in final text | Simulated reply rate | Tokens / job | p95 latency (s) |",
            "|---|---|---|---|---|---|---|---|"]
    for s, m in d["summary"].items():
        rows.append(f"| {s} | {m['n']} | {_f(m['bid_skip_accuracy'])} | {_f(m['unsupported_per_proposal'], 2)} | {m['violations_in_final_text']} | "
                    f"{_f(m['simulated_reply_rate'])} | {_f(m['tokens_per_job'], 0)} | {_f(m['p95_latency_s'], 1)} |")
    rows.append(f"\n_model profile `{d['meta']['model_profile']}`; source `evals/results/multiagent_compare.json` @ {d['meta']['git_sha']}._")
    return "\n".join(rows)


TABLES = {"rag": rag_table, "decisions": decision_table, "multiagent": multiagent_table}


def render(text: str) -> str:
    for name, fn in TABLES.items():
        text = re.sub(rf"(<!-- results:{name} -->)(.*?)(<!-- /results:{name} -->)", lambda m: f"{m.group(1)}\n{fn()}\n{m.group(3)}", text, flags=re.S)
    return text


def main() -> int:
    cur = README.read_text(encoding="utf-8")
    new = render(cur)
    if "--check" in sys.argv:
        if new != cur:
            print("README results tables are stale: run `python -m scripts.render_results`")
            return 1
        print("README tables match evals/results")
        return 0
    README.write_text(new, encoding="utf-8")
    print("README tables rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
