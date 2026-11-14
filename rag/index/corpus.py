"""In-process portfolio index per (persona, chunking, contextual): chunks + dense matrix + BM25.

The vector store is pluggable (`rag.vector_store`): `numpy` (in-process cosine, used for local runs and
evals) or `qdrant` (QDRANT_URL, used by docker compose). Both are filtered by persona (= tenant) and type.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from agent.settings import cfg
from rag.index.bm25 import BM25
from rag.index.models import embed_queries, embedding_cache
from rag.ingest.chunkers import Chunk, chunk_docs
from rag.ingest.loaders import load_persona

_CORPORA: dict[tuple, Corpus] = {}
_lock = threading.Lock()


@dataclass
class Corpus:
    persona: str
    strategy: str
    contextual: bool
    chunks: list[Chunk]
    matrix: np.ndarray
    bm25: BM25
    project_outcome: dict[str, float] = field(default_factory=dict)
    by_project: dict[str, list[int]] = field(default_factory=dict)

    qdrant: tuple | None = None   # (client, collection) when the Qdrant vector store is configured

    def dense(self, qvec: np.ndarray, top: int, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        if self.qdrant is not None:
            try:
                client, name = self.qdrant
                res = client.query_points(name, query=qvec.tolist(), limit=top * 3 if mask is not None else top).points
                hits = [(int(p.id), float(p.score)) for p in res if mask is None or mask[int(p.id)]]
                return hits[:top]
            except Exception:  # noqa: BLE001 - fall back to the in-process matrix
                pass
        sims = self.matrix @ qvec
        if mask is not None:
            sims = np.where(mask, sims, -1.0)
        idx = np.argsort(-sims)[:top]
        return [(int(i), float(sims[i])) for i in idx if sims[i] > -1.0]

    def sparse(self, query: str, top: int, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        s = np.asarray(self.bm25.scores(query))
        if mask is not None:
            s = np.where(mask, s, -1.0)
        idx = np.argsort(-s)[:top]
        return [(int(i), float(s[i])) for i in idx if s[i] > 0]

    def mask(self, types: list[str] | None = None, exclude_items: set[str] | None = None) -> np.ndarray | None:
        if not types and not exclude_items:
            return None
        return np.array([(not types or c.doc.type in types) and (not exclude_items or c.doc.item_id not in exclude_items)
                         for c in self.chunks])


def _outcome_scores(chunks: list[Chunk]) -> dict[str, float]:
    """Per project: share of past proposals citing it that won or got a reply (outcome-aware ranking, V4)."""
    tally: dict[str, list[float]] = defaultdict(list)
    seen = set()
    for c in chunks:
        d = c.doc
        if d.type != "proposal" or d.item_id in seen:
            continue
        seen.add(d.item_id)
        val = {"won": 1.0, "replied": 0.6, "ignored": 0.0}.get(d.outcome or "", 0.0)
        for p in d.projects:
            tally[p].append(val)
    return {p: sum(v) / len(v) for p, v in tally.items() if v}


def get_corpus(persona: str, strategy: str = "structured", contextual: bool = False, refresh: bool = False) -> Corpus:
    key = (persona, strategy, contextual, cfg("embeddings.model"))
    with _lock:
        if key in _CORPORA and not refresh:
            return _CORPORA[key]
    docs = load_persona(persona)
    chunks = chunk_docs(docs, strategy=strategy, contextual=contextual)
    matrix = embedding_cache().embed([c.index_text for c in chunks])
    bm25 = BM25([c.index_text for c in chunks])
    by_project: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(chunks):
        for p in c.doc.projects:
            by_project[p].append(i)
    corpus = Corpus(persona, strategy, contextual, chunks, matrix, bm25, _outcome_scores(chunks), dict(by_project))
    if (cfg("rag.vector_store") or "numpy") == "qdrant" and os.getenv("QDRANT_URL"):
        _sync_qdrant(corpus)
    with _lock:
        _CORPORA[key] = corpus
    return corpus


def invalidate(persona: str | None = None) -> None:
    with _lock:
        for k in [k for k in _CORPORA if persona is None or k[0] == persona]:
            _CORPORA.pop(k, None)


def _sync_qdrant(corpus: Corpus) -> None:
    """Mirror the persona index into Qdrant (compose deployment). Dense search stays numpy-identical."""
    try:
        from qdrant_client import QdrantClient, models

        client = QdrantClient(url=os.environ["QDRANT_URL"])
        name = f"portfolio_{corpus.persona}_{corpus.strategy}{'_ctx' if corpus.contextual else ''}"
        if not client.collection_exists(name):
            client.create_collection(name, vectors_config=models.VectorParams(size=corpus.matrix.shape[1], distance=models.Distance.COSINE))
        client.upsert(name, points=[
            models.PointStruct(id=i, vector=corpus.matrix[i].tolist(),
                               payload={"chunk_id": c.chunk_id, "tenant": corpus.persona, "type": c.doc.type, "item_id": c.doc.item_id})
            for i, c in enumerate(corpus.chunks)])
        corpus.qdrant = (client, name)
    except Exception:  # noqa: BLE001 - fall back to the in-process index
        corpus.qdrant = None


def query_vector(text: str) -> np.ndarray:
    return embed_queries([text])[0]
