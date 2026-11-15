"""Retriever factory: the deployed variant is chosen by config (`rag.variant`), which is set from the
measured comparison in evals/results/rag_variants.json (R6)."""

from __future__ import annotations

import importlib

from agent.settings import cfg
from rag.variants.base import Pipeline, PipelineConfig

VARIANT_MODULES = [
    "v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector", "v6_contextual",
    "v7_hyde", "v8_corrective",
]


def variants() -> dict[str, PipelineConfig]:
    out = {}
    for m in VARIANT_MODULES:
        mod = importlib.import_module(f"rag.variants.{m}")
        out[mod.VARIANT.name] = mod.VARIANT
    # composite stacks used by the ablation (best pipeline minus one component)
    full = out["v8_corrective"]
    out["stack_no_corrective"] = full.with_(name="stack_no_corrective", corrective=False)
    out["stack_no_rerank"] = full.with_(name="stack_no_rerank", rerank=False, corrective=False)
    out["stack_no_hybrid"] = full.with_(name="stack_no_hybrid", retriever="dense")
    out["stack_no_decompose"] = full.with_(name="stack_no_decompose", query="whole")
    out["stack_no_outcome"] = full.with_(name="stack_no_outcome", outcome_boost=False)
    out["stack_no_multivector"] = full.with_(name="stack_no_multivector", group_projects=False, chunking="fixed")
    # SHIPPED (chosen by evals/results/rag_variants.json, ADR 0005): the ablation showed the cross-encoder re-ranking
    # step LOWERS Recall@5 / nDCG@10 on this corpus and costs ~70x latency, so ranking = decomposition + hybrid +
    # outcome boost + multi-vector; support per requirement = bi-encoder cosine of its top-8 evidence (calibrated on dev:
    # the cross-encoder scored many relevant chunks ~0), used by the Fit Matcher and the "do not claim" signal.
    # Ranking is identical to stack_no_rerank.
    out["shipped"] = full.with_(name="shipped", rerank=False, corrective=False, grade_top=8,
                                description="decompose + hybrid + outcome + multi-vector; cosine-graded support per requirement")
    return out


def get_pipeline(name: str | None = None) -> Pipeline:
    name = name or cfg("rag.variant") or "v8_corrective"
    v = variants()
    if name not in v:
        raise KeyError(f"unknown RAG variant {name}; known: {sorted(v)}")
    return Pipeline(v[name])
