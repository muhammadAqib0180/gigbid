"""Ablation of the full retrieval stack (B4): remove one component at a time from V8 and re-score.

    python -m evals.runners.ablation [--n 30]

This is the `--set ablation` mode of evals/runners/rag_eval.py (variants `stack_no_*` in rag/retriever.py), written to
evals/results/rag_ablation.json. The committed numbers in the report come from the combined run in
evals/results/rag_variants.json (`--set all`), which contains the same `stack_no_*` rows.
"""

from __future__ import annotations

import sys

from evals.runners import rag_eval


def main() -> None:
    args = sys.argv[1:]
    if "--out" not in args:
        args += ["--out", "rag_ablation"]
    sys.argv = [sys.argv[0], "--set", "ablation", *args]
    rag_eval.main()


if __name__ == "__main__":
    main()
