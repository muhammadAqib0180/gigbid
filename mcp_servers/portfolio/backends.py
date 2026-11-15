"""Evidence backends for the Portfolio MCP server.

* GigBidBackend  - inside the GigBid monorepo: the measured RAG pipeline (rag.retriever), per persona/tenant.
* LiteBackend    - standalone install (`uvx portfolio-evidence-mcp --corpus ./my-portfolio`): any folder of
                   Markdown / text / code / JSON files, BM25 ranking (+ dense re-scoring if fastembed is installed).
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]")
TEXT_EXT = {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".sql", ".json", ".yml", ".yaml", ".r", ".ipynb"}

# Skills recognised in standalone mode (no model): common tools and techniques, matched as whole words.
TECH_SKILLS = sorted({
    "python", "javascript", "typescript", "java", "c#", "c++", "golang", "rust", "php", "ruby", "kotlin", "swift", "sql",
    "react", "next.js", "vue", "angular", "svelte", "node.js", "express", "nestjs", "tailwind", "html", "css", "graphql",
    "django", "flask", "fastapi", "rails", "laravel", "spring", "celery", "rest api", "websocket", "stripe", "supabase",
    "firebase", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "elasticsearch", "snowflake", "bigquery",
    "dbt", "airflow", "spark", "kafka", "docker", "kubernetes", "terraform", "aws", "gcp", "azure", "linux", "ci/cd",
    "github actions", "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow", "keras", "xgboost", "hugging face",
    "transformers", "langchain", "langgraph", "llamaindex", "openai", "llm", "rag", "embeddings", "vector search",
    "qdrant", "pinecone", "faiss", "chromadb", "fine-tuning", "nlp", "computer vision", "opencv", "yolo", "ocr",
    "chatbot", "machine learning", "deep learning", "time series", "forecasting", "a/b testing", "statistics",
    "excel", "power bi", "tableau", "looker", "metabase", "google sheets", "power query", "vba", "etl", "web scraping",
    "selenium", "playwright", "scrapy", "figma", "shopify", "wordpress", "mobile", "flutter", "react native",
})
_SKILL_RE = {s: re.compile(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])") for s in TECH_SKILLS}


class Backend(Protocol):
    name: str

    def search(self, requirement: str, k: int, filters: dict[str, Any]) -> list[dict[str, Any]]: ...
    def get_item(self, item_id: str) -> dict[str, Any] | None: ...
    def list_skills(self) -> list[dict[str, Any]]: ...
    def list_items(self, type_: str | None = None) -> list[dict[str, Any]]: ...


def _tok(t: str) -> list[str]:
    return _TOKEN.findall(t.lower())


class LiteBackend:
    name = "lite"

    def __init__(self, corpus: str | Path) -> None:
        self.root = Path(corpus).expanduser().resolve()
        self.items: list[dict[str, Any]] = []
        for f in sorted(self.root.rglob("*")):
            if f.is_file() and f.suffix.lower() in TEXT_EXT and not f.name.startswith(("_gold", ".")):
                txt = f.read_text(encoding="utf-8", errors="replace")
                rel = f.relative_to(self.root).as_posix()
                typ = "case_study" if "case" in rel.lower() else ("readme" if f.name.lower() == "readme.md" else
                      ("code" if f.suffix.lower() not in {".md", ".txt", ".json"} else "document"))
                self.items.append({"item_id": rel, "type": typ, "title": f.stem, "source": rel, "text": txt, "date": None, "outcome": None})
        self.toks = [Counter(_tok(i["text"])) for i in self.items]
        n = max(1, len(self.items))
        df: Counter[str] = Counter()
        for t in self.toks:
            df.update(t.keys())
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.avg = sum(sum(t.values()) for t in self.toks) / n

    def search(self, requirement: str, k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        q = _tok(requirement)
        scored = []
        for item, tf in zip(self.items, self.toks):
            if filters.get("types") and item["type"] not in filters["types"]:
                continue
            dl = sum(tf.values())
            s = sum(self.idf.get(w, 0) * tf[w] * 2.4 / (tf[w] + 1.4 * (0.25 + 0.75 * dl / self.avg)) for w in q if w in tf)
            if s > 0:
                scored.append((s, item))
        scored.sort(key=lambda t: -t[0])
        return [{"evidence_id": it["item_id"], "item_id": it["item_id"], "type": it["type"], "title": it["title"],
                 "source": it["source"], "date": it["date"], "outcome": it["outcome"], "snippet": it["text"][:600],
                 "score": round(s, 3)} for s, it in scored[:k]]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return next((i for i in self.items if i["item_id"] == item_id), None)

    def list_skills(self) -> list[dict[str, Any]]:
        """Known tools/techniques found in the corpus, with how many files mention each and which ones."""
        where: dict[str, list[str]] = {}
        for item in self.items:
            low = item["text"].lower()
            for s, rx in _SKILL_RE.items():
                if rx.search(low):
                    where.setdefault(s, []).append(item["item_id"])
        ranked = sorted(where.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        return [{"skill": s, "count": len(files), "projects": files[:8]} for s, files in ranked]

    def list_items(self, type_: str | None = None) -> list[dict[str, Any]]:
        return [{k: i[k] for k in ("item_id", "type", "title", "source")} for i in self.items if not type_ or i["type"] == type_]


class GigBidBackend:
    name = "gigbid"

    def __init__(self, persona: str) -> None:
        self.persona = persona

    def _docs(self):
        from rag.ingest.loaders import load_persona

        return load_persona(self.persona)

    def search(self, requirement: str, k: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        import asyncio

        from agent.handoffs import Requirement
        from rag.retriever import get_pipeline

        pipe = get_pipeline(filters.get("variant"))
        job = {"title": requirement[:120], "description": requirement}
        coro = pipe.retrieve(self.persona, job, [Requirement(id="r1", text=requirement)], k=k,
                             exclude_items=set(filters.get("exclude_items") or []), types=filters.get("types"))
        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                res = ex.submit(asyncio.run, coro).result()
        except RuntimeError:
            res = asyncio.run(coro)
        items = [i.model_dump() for i in res.items]
        if filters.get("outcome"):
            items = [i for i in items if i.get("outcome") == filters["outcome"]]
        if filters.get("date_from"):
            items = [i for i in items if not i.get("date") or str(i["date"]) >= str(filters["date_from"])]
        return items[:k]

    def match(self, job: dict[str, Any], requirements: list[dict[str, Any]], k: int) -> dict[str, Any]:
        from agent.handoffs import Requirement
        from rag.retriever import get_pipeline

        reqs = [Requirement.model_validate(r) for r in requirements]
        res = _run_sync(get_pipeline().retrieve(self.persona, job, reqs, k=k))
        return {"items": [i.model_dump() for i in res.items[:k]],
                "per_requirement": [{"requirement_id": rid, "items": [i.model_dump() for i in items], "weak": rid in res.weak_requirements,
                                     "support": res.support.get(rid)} for rid, items in res.per_requirement.items()],
                "weak_requirements": res.weak_requirements, "variant": res.variant, "latency_s": round(res.latency_s, 3)}

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        for d in self._docs():
            if d.item_id == item_id or d.item_id == f"case-{item_id}" or d.item_id == f"repo-{item_id}":
                return {"item_id": d.item_id, "type": d.type, "title": d.title, "source": d.source, "date": d.date,
                        "outcome": d.outcome, "projects": d.projects, "skills": d.skills, "text": d.text}
        return None

    def list_skills(self) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        where: dict[str, set[str]] = {}
        for d in self._docs():
            if d.type == "proposal":
                continue
            for s in d.skills:
                counts[s] += 1
                where.setdefault(s, set()).update(d.projects)
        return [{"skill": s, "count": c, "projects": sorted(where.get(s, set()))[:8]} for s, c in counts.most_common()]

    def list_items(self, type_: str | None = None) -> list[dict[str, Any]]:
        return [{"item_id": d.item_id, "type": d.type, "title": d.title, "source": d.source, "outcome": d.outcome}
                for d in self._docs() if not type_ or d.type == type_]


_BACKENDS: dict[str, Backend] = {}


def _run_sync(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def backend_for(persona: str | None) -> Backend:
    if persona is None:
        try:
            from mcp_servers._shared import _current_caller

            c = _current_caller.get()
            persona = c.persona if c else None
        except ImportError:
            pass
    corpus = os.getenv("PORTFOLIO_CORPUS")
    if corpus:
        key = f"lite:{corpus}"
        if key not in _BACKENDS:
            _BACKENDS[key] = LiteBackend(corpus)
        return _BACKENDS[key]
    try:
        import rag.retriever  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("standalone mode needs --corpus <folder> (or PORTFOLIO_CORPUS)") from exc
    p = persona or os.getenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    key = f"gigbid:{p}"
    if key not in _BACKENDS:
        _BACKENDS[key] = GigBidBackend(p)
    return _BACKENDS[key]


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
