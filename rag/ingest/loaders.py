"""Portfolio loaders: PDF CVs, Markdown case studies, repo READMEs + code, reviews, past proposals.

Every document carries metadata: persona, type, item_id, project(s), skills, date, client_industry and,
for proposals, outcome. `_gold_*` files are never ingested (they hold evaluation ground truth).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent.settings import data_dir
from agent.skills import extract_skills

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".yml", ".yaml", ".R", ".sh", ".json", ".md", ""}


@dataclass
class Doc:
    doc_id: str
    item_id: str
    type: str                      # cv | case_study | readme | code | review | proposal | user_upload
    persona: str
    text: str
    title: str = ""
    source: str = ""
    date: str | None = None
    outcome: str | None = None
    projects: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    client_industry: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def project(self) -> str | None:
        return self.projects[0] if self.projects else None


def persona_dir(persona: str) -> Path:
    return data_dir() / "personas" / persona


def load_cv(persona: str) -> list[Doc]:
    path = persona_dir(persona) / "cv.pdf"
    if not path.exists():
        return []
    import pymupdf

    with pymupdf.open(path) as pdf:
        text = "\n".join(page.get_text() for page in pdf)
    return [Doc(doc_id=f"{persona}:cv", item_id="cv", type="cv", persona=persona, text=text, title="CV",
                source=str(path.relative_to(data_dir().parent)), skills=extract_skills(text))]


def _front_matter(md: str) -> tuple[dict, str]:
    if md.startswith("---"):
        _, fm, body = md.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, md


def load_case_studies(persona: str) -> list[Doc]:
    docs = []
    for f in sorted((persona_dir(persona) / "case_studies").glob("*.md")):
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        title = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        docs.append(Doc(
            doc_id=f"{persona}:{meta.get('id', f.stem)}", item_id=str(meta.get("id", f"case-{f.stem}")), type="case_study",
            persona=persona, text=body, title=title.group(1) if title else f.stem, source=str(f.relative_to(data_dir().parent)),
            date=str(meta.get("date")) if meta.get("date") else None, projects=[meta.get("project", f.stem)],
            skills=list(meta.get("skills") or []), client_industry=meta.get("client_industry")))
    return docs


def load_repos(persona: str) -> list[Doc]:
    docs = []
    root = persona_dir(persona) / "repos"
    for repo in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        slug = repo.name
        for f in sorted(repo.rglob("*")):
            if not f.is_file() or (f.suffix not in CODE_EXT and f.name != "Dockerfile"):
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            rel = f.relative_to(repo).as_posix()
            is_readme = rel.lower() == "readme.md"
            docs.append(Doc(
                doc_id=f"{persona}:repo-{slug}:{rel}", item_id=f"repo-{slug}" if is_readme else f"code-{slug}/{rel}",
                type="readme" if is_readme else "code", persona=persona, text=text, title=f"{slug}/{rel}",
                source=str(f.relative_to(data_dir().parent)), projects=[slug], skills=extract_skills(text)))
    return docs


def load_reviews(persona: str) -> list[Doc]:
    path = persona_dir(persona) / "reviews.json"
    if not path.exists():
        return []
    out = []
    for r in json.loads(path.read_text(encoding="utf-8")):
        out.append(Doc(doc_id=f"{persona}:{r['id']}", item_id=r["id"], type="review", persona=persona,
                       text=f"Client review ({r['stars']} stars, {r['client_industry']}): {r['text']}", title="Client review",
                       source=str(path.relative_to(data_dir().parent)), date=r.get("date"), projects=[r["project"]],
                       client_industry=r.get("client_industry"), skills=extract_skills(r["text"])))
    return out


def load_proposals(persona: str) -> list[Doc]:
    path = persona_dir(persona) / "proposals.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        out.append(Doc(doc_id=f"{persona}:{p['id']}", item_id=p["id"], type="proposal", persona=persona,
                       text=f"Past proposal for \"{p['job_title']}\" (outcome: {p['outcome']}).\n\n{p['text']}",
                       title=p["job_title"], source=str(path.relative_to(data_dir().parent)), date=p.get("date"),
                       outcome=p["outcome"], projects=list(p.get("projects_cited") or []), skills=list(p.get("job_skills") or [])))
    return out


def load_uploads(persona: str) -> list[Doc]:
    """User-added work from the UI (incremental re-index), stored as Markdown in uploads/."""
    out = []
    for f in sorted((persona_dir(persona) / "uploads").glob("*.md")):
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        out.append(Doc(doc_id=f"{persona}:upload-{f.stem}", item_id=f"upload-{f.stem}", type=meta.get("type", "case_study"),
                       persona=persona, text=body, title=meta.get("title", f.stem), source=str(f.relative_to(data_dir().parent)),
                       date=str(meta.get("date") or ""), projects=[meta.get("project", f.stem)], skills=extract_skills(body)))
    return out


def load_persona(persona: str) -> list[Doc]:
    return (load_cv(persona) + load_case_studies(persona) + load_repos(persona) + load_reviews(persona)
            + load_proposals(persona) + load_uploads(persona))
