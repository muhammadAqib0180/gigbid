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


def outcomes_table() -> str:
    rows = ["| Run | Submitted / jobs | Reply rate | Interview rate | Hire rate | Unsupported claims / proposal (first draft -> final) | Mean revisions | p95 s / proposal |",
            "|---|---|---|---|---|---|---|---|"]
    found = False
    for name, label in (("outcomes_v0_naive", "V0 retrieval, evidence-first"), ("outcomes_v8_corrective", "shipped (V8 stack), evidence-first"),
                        ("outcomes_question_first", "shipped (V8 stack), question-first")):
        d = _load(name)
        if not d:
            continue
        found = True
        o = d["overall"]
        rows.append(f"| {label} | {o['submitted']}/{o['jobs']} | {_f(o['reply_rate'])} | {_f(o['interview_rate'])} | {_f(o['hire_rate'])} | "
                    f"{_f(o['unsupported_per_proposal_first_draft'], 2)} -> {_f(o['unsupported_per_proposal_final'], 2)} | {_f(o['mean_revisions'], 2)} | "
                    f"{_f(o['p95_latency_s_per_proposal'], 1)} |")
    ab = _load("ab_test")
    if ab:
        rows.append(f"\n_A/B (X2): McNemar exact p = {ab['mcnemar_exact_p']} on {ab['paired_jobs']} paired jobs; source `evals/results/ab_test.json`._")
    return "\n".join(rows) if found else "_not run yet_"


def tools_table() -> str:
    d = _load("tool_granularity")
    if not d:
        return "_not run yet_"
    rows = ["| Tool set | # tools | Tool-selection accuracy | Argument accuracy | Tokens / task |", "|---|---|---|---|---|"]
    for k, m in d["results"].items():
        rows.append(f"| {k} | {m['n_tools']} | {_f(m['tool_selection_accuracy'])} | {_f(m['argument_accuracy'])} | {_f(m['tokens_per_task'], 0)} |")
    rows.append(f"\n_model `{d.get('model')}`, n = {next(iter(d['results'].values()))['n']} tasks; source `evals/results/tool_granularity.json`._")
    return "\n".join(rows)


def injection_table() -> str:
    d = next((x for x in (_load("injection_open_small"), _load("injection_open"), _load("injection_open_local")) if x), None)
    if not d:
        return "_not run yet_"
    return ("| Condition | Attack success rate |\n|---|---|\n"
            f"| no defences (naive writer, raw text, no Compliance Guard) | {_f(d['attack_success_before'])} |\n"
            f"| GigBid writer prompt + delimiting (before Compliance) | {_f(d['attack_success_after_writer_only'])} |\n"
            f"| full GigBid (+ Compliance Guard) | {_f(d['attack_success_after'])} |\n"
            f"\n_n = {d['n_valid_llm']} planted-injection jobs with valid LLM output; detection rate {_f(d['detection_rate'])}; model profile "
            f"`{d['meta']['model_profile']}`._")


TABLES = {"rag": rag_table, "decisions": decision_table, "multiagent": multiagent_table, "outcomes": outcomes_table,
          "tools": tools_table, "injection": injection_table}


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
