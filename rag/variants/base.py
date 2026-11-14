"""Composable retrieval pipeline. Each RAG variant (v0..v9) is a PipelineConfig preset, so the
ablation can switch one component at a time and one command reruns the full comparison."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from agent.handoffs import EvidenceItem, Requirement
from agent.requirements import extract_requirements
from agent.settings import cfg
from rag.index.corpus import Corpus, get_corpus, query_vector
from rag.index.models import rerank_scores


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    query: str = "whole"            # whole | decompose | hyde
    retriever: str = "dense"        # dense | bm25 | hybrid
    rerank: bool = False
    outcome_boost: bool = False
    chunking: str = "structured"    # fixed | structured
    contextual: bool = False        # V6 context header on each chunk
    group_projects: bool = False    # V5 multi-vector: summary/README/code returned as one project
    corrective: bool = False        # V8 grade -> re-query -> refuse
    k: int = 8
    pool: int = 30
    description: str = ""

    def with_(self, **kw: Any) -> PipelineConfig:
        return replace(self, **kw)


@dataclass
class RetrievalResult:
    items: list[EvidenceItem]
    per_requirement: dict[str, list[EvidenceItem]] = field(default_factory=dict)
    weak_requirements: list[str] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    latency_s: float = 0.0
    usage: dict = field(default_factory=dict)
    variant: str = ""

    def ranked_projects(self) -> list[str]:
        out: list[str] = []
        for it in self.items:
            for p in (it.project.split(",") if it.project else []):
                if p and p not in out:
                    out.append(p)
        return out


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _rrf(lists: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
    acc: dict[int, float] = defaultdict(float)
    for lst in lists:
        for rank, (i, _) in enumerate(lst):
            acc[i] += 1.0 / (k + rank + 1)
    return sorted(acc.items(), key=lambda kv: -kv[1])


def to_item(corpus: Corpus, idx: int, score: float) -> EvidenceItem:
    c = corpus.chunks[idx]
    d = c.doc
    return EvidenceItem(evidence_id=c.chunk_id, item_id=d.item_id, type=d.type, title=d.title, source=d.source, date=d.date,
                        outcome=d.outcome, project=",".join(d.projects) if d.projects else None, skills=d.skills,
                        snippet=c.text[:600], score=round(float(score), 4))


class Pipeline:
    def __init__(self, conf: PipelineConfig) -> None:
        self.conf = conf

    # ------------------------------------------------------------------ queries
    async def queries_for(self, job: dict, reqs: list[Requirement]) -> tuple[list[tuple[str, str]], dict]:
        text = f"{job.get('title', '')}\n{job.get('description', '')}"
        if self.conf.query == "decompose":
            return [(r.id, r.text) for r in reqs], {}
        if self.conf.query == "hyde":
            from rag.variants.v7_hyde import hypothetical_proposal

            hypo, usage = await hypothetical_proposal(job)
            return [("hyde", hypo)], usage
        return [("job", text[:2000])], {}

    # ------------------------------------------------------------------ candidates for one query
    def candidates(self, corpus: Corpus, query: str, mask: Any, rerank: bool | None = None) -> list[tuple[int, float]]:
        pool = self.conf.pool
        if self.conf.retriever == "dense":
            cands = corpus.dense(query_vector(query), pool, mask)
        elif self.conf.retriever == "bm25":
            cands = corpus.sparse(query, pool, mask)
        else:
            cands = _rrf([corpus.dense(query_vector(query), pool, mask), corpus.sparse(query, pool, mask)])[:pool]
        if (self.conf.rerank if rerank is None else rerank) and cands:
            scores = rerank_scores(query, [corpus.chunks[i].text for i, _ in cands])
            cands = sorted(((i, sigmoid(float(s))) for (i, _), s in zip(cands, scores)), key=lambda t: -t[1])
        if self.conf.outcome_boost:
            w = cfg("rag.outcome_boost", {}) or {}
            boosted = []
            for i, s in cands:
                d = corpus.chunks[i].doc
                b = 0.0
                if d.type == "proposal":
                    b += float(w.get(d.outcome or "", 0.0))
                if d.projects:
                    b += 0.3 * max(corpus.project_outcome.get(p, 0.0) for p in d.projects) * float(w.get("won", 0.25))
                boosted.append((i, s + b * (1.0 if self.conf.rerank else 0.05)))
            cands = sorted(boosted, key=lambda t: -t[1])
        return cands

    # ------------------------------------------------------------------ main
    async def retrieve(self, persona: str, job: dict, requirements: list[Requirement] | None = None, k: int | None = None,
                       exclude_items: set[str] | None = None, types: list[str] | None = None) -> RetrievalResult:
        t0 = time.perf_counter()
        k = k or self.conf.k
        corpus = get_corpus(persona, self.conf.chunking, self.conf.contextual)
        reqs = requirements or extract_requirements(job)
        mask = corpus.mask(types, exclude_items)
        queries, usage = await self.queries_for(job, reqs)
        per_query: dict[str, list[tuple[int, float]]] = {}
        for qid, q in queries:
            per_query[qid] = self.candidates(corpus, q, mask)
        weak: list[str] = []
        if self.conf.corrective:
            from rag.variants.v8_corrective import corrective_loop

            per_query, weak = corrective_loop(self, corpus, dict(queries), per_query, mask, reqs)
        # merge: round-robin across queries so every requirement is represented, max-score de-dup
        merged: dict[int, float] = {}
        order: list[int] = []
        lists = [v for v in per_query.values() if v]
        depth = max((len(v) for v in lists), default=0)
        for r in range(depth):
            for lst in lists:
                if r < len(lst):
                    i, s = lst[r]
                    if i not in merged:
                        order.append(i)
                    merged[i] = max(merged.get(i, -1e9), s)
        ranked = order
        if self.conf.group_projects:
            ranked = self._group(corpus, order, merged)
        items = [to_item(corpus, i, merged[i]) for i in ranked[: max(k, 10)]]
        per_req = {qid: [to_item(corpus, i, s) for i, s in lst[:3]] for qid, lst in per_query.items()}
        return RetrievalResult(items=items, per_requirement=per_req, weak_requirements=weak, requirements=reqs,
                               queries=[q for _, q in queries], latency_s=time.perf_counter() - t0, usage=usage,
                               variant=self.conf.name)

    @staticmethod
    def _group(corpus: Corpus, order: list[int], scores: dict[int, float]) -> list[int]:
        """Multi-vector: a project's case study, README and code chunks vote together; return the best
        chunk of each project in project-score order (max + 0.15 * sum of the rest)."""
        proj_hits: dict[str, list[int]] = defaultdict(list)
        loose: list[int] = []
        for i in order:
            projs = corpus.chunks[i].doc.projects
            if projs and corpus.chunks[i].doc.type != "proposal":
                proj_hits[projs[0]].append(i)
            else:
                loose.append(i)
        proj_score = {}
        for p, idxs in proj_hits.items():
            vals = sorted((scores[i] for i in idxs), reverse=True)
            proj_score[p] = vals[0] + 0.15 * sum(vals[1:])
        heads = sorted(proj_hits, key=lambda p: -proj_score[p])
        out: list[int] = []
        for p in heads:
            best = max(proj_hits[p], key=lambda i: scores[i])
            out.append(best)
            scores[best] = proj_score[p]
        # interleave proposals/reviews/cv after the project heads, by score
        out += sorted(loose, key=lambda i: -scores[i])
        rest = [i for p in heads for i in proj_hits[p] if i not in out]
        return out + rest
