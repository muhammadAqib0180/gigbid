"""Open embedding + reranker models (CPU, ONNX via fastembed) with an on-disk embedding cache."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from agent.settings import ROOT, cfg

_lock = threading.Lock()


def _cache_dir() -> Path:
    p = Path(cfg("embeddings.cache_dir", "data/processed/models"))
    p = p if p.is_absolute() else ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=4)
def embedder(model_name: str | None = None):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name or cfg("embeddings.model"), cache_dir=str(_cache_dir()))


@lru_cache(maxsize=4)
def reranker(model_name: str | None = None):
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=model_name or cfg("reranker.model"), cache_dir=str(_cache_dir()))


class EmbeddingCache:
    """sqlite: (model, sha1(text)) -> float32 vector bytes. Re-indexing only embeds new/changed chunks."""

    def __init__(self, model_name: str) -> None:
        self.model = model_name
        self.conn = sqlite3.connect(_cache_dir() / "embeddings.sqlite", check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS emb (model TEXT, h TEXT, v BLOB, PRIMARY KEY (model, h))")

    def embed(self, texts: list[str], batch: int = 64) -> np.ndarray:
        hashes = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
        found: dict[str, np.ndarray] = {}
        with _lock:
            for i in range(0, len(hashes), 500):
                part = hashes[i : i + 500]
                q = f"SELECT h, v FROM emb WHERE model=? AND h IN ({','.join('?' * len(part))})"
                for h, v in self.conn.execute(q, [self.model, *part]):
                    found[h] = np.frombuffer(v, dtype=np.float32)
        missing = [(h, t) for h, t in zip(hashes, texts) if h not in found]
        if missing:
            model = embedder(self.model)
            vecs = list(model.embed([t for _, t in missing], batch_size=batch))
            with _lock:
                self.conn.executemany("INSERT OR REPLACE INTO emb VALUES (?,?,?)",
                                      [(self.model, h, np.asarray(v, dtype=np.float32).tobytes()) for (h, _), v in zip(missing, vecs)])
                self.conn.commit()
            for (h, _), v in zip(missing, vecs):
                found[h] = np.asarray(v, dtype=np.float32)
        mat = np.vstack([found[h] for h in hashes]) if hashes else np.zeros((0, 384), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / np.clip(norms, 1e-9, None)


@lru_cache(maxsize=4)
def embedding_cache(model_name: str | None = None) -> EmbeddingCache:
    return EmbeddingCache(model_name or cfg("embeddings.model"))


def embed_queries(texts: list[str], model_name: str | None = None) -> np.ndarray:
    return embedding_cache(model_name).embed(texts)


def rerank_scores(query: str, docs: list[str], model_name: str | None = None) -> np.ndarray:
    if not docs:
        return np.zeros(0)
    return np.asarray(list(reranker(model_name).rerank(query, docs)), dtype=np.float32)
