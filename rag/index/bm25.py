"""Small Okapi BM25 with a tokenizer that keeps tool names intact (dbt, next.js, c++, gpt-4o)."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]")
STOP = set("a an and are as at be by for from has have i in is it its of on or our that the this to was we were with you your".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOP]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.toks = [tokenize(d) for d in docs]
        self.n = len(docs)
        self.avgdl = sum(map(len, self.toks)) / max(1, self.n)
        df: Counter[str] = Counter()
        for t in self.toks:
            df.update(set(t))
        self.idf = {w: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tf = [Counter(t) for t in self.toks]
        self.len = [len(t) for t in self.toks]

    def scores(self, query: str) -> list[float]:
        q = [w for w in tokenize(query) if w in self.idf]
        out = [0.0] * self.n
        for i in range(self.n):
            tf, dl = self.tf[i], self.len[i]
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[i] = s
        return out
