"""Portfolio MCP tools (read-only): search_evidence, get_case_study, list_skills."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .backends import backend_for
from .identity import persona_from_ctx

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EvidenceType = Literal["cv", "case_study", "readme", "code", "review", "proposal", "document", "user_upload"]


class EvidenceFilters(BaseModel):
    types: list[EvidenceType] | None = Field(default=None, description="Only these evidence types")
    outcome: Literal["won", "replied", "ignored"] | None = Field(default=None, description="Past-proposal outcome")
    date_from: str | None = Field(default=None, description="ISO date lower bound")
    exclude_items: list[str] | None = Field(default=None, max_length=50)


class Evidence(BaseModel):
    evidence_id: str
    item_id: str
    type: str
    title: str = ""
    source: str = ""
    date: str | None = None
    outcome: str | None = None
    project: str | None = None
    snippet: str = ""
    score: float = 0.0


class EvidenceList(BaseModel):
    requirement: str
    backend: str
    items: list[Evidence]


class CaseStudy(BaseModel):
    item_id: str
    type: str
    title: str
    source: str
    date: str | None = None
    text: str


class SkillCount(BaseModel):
    skill: str
    count: int
    projects: list[str] = Field(default_factory=list)


class SkillList(BaseModel):
    skills: list[SkillCount]


class RequirementIn(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=2, max_length=300)
    skills: list[str] = Field(default_factory=list, max_length=10)
    must_have: bool = True


class RequirementEvidence(BaseModel):
    requirement_id: str
    items: list[Evidence]
    weak: bool = False
    support: float | None = Field(default=None, description="cross-encoder support (0-1) of the best evidence, when graded")


class MatchResult(BaseModel):
    items: list[Evidence]
    per_requirement: list[RequirementEvidence]
    weak_requirements: list[str]
    variant: str
    latency_s: float


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def match_requirements(
        ctx: Context,
        job_title: Annotated[str, Field(max_length=300)],
        job_text: Annotated[str, Field(max_length=8000)],
        requirements: Annotated[list[RequirementIn], Field(min_length=1, max_length=12)],
        k: Annotated[int, Field(ge=1, le=20)] = 8,
    ) -> MatchResult:
        """Map every job requirement to portfolio evidence in one call, using the measured RAG pipeline
        (decomposition, hybrid retrieval, re-ranking, corrective loop). Weak requirements have no evidence:
        do not claim them."""
        b = backend_for(persona_from_ctx(ctx))
        if not hasattr(b, "match"):
            per = [RequirementEvidence(requirement_id=r.id, items=[Evidence.model_validate(i) for i in b.search(r.text, 3, {})])
                   for r in requirements]
            merged = {i.evidence_id: i for p in per for i in p.items}
            return MatchResult(items=list(merged.values())[:k], per_requirement=per, weak_requirements=[], variant=b.name, latency_s=0.0)
        res = await asyncio.to_thread(b.match, {"title": job_title, "description": job_text}, [r.model_dump() for r in requirements], k)
        return MatchResult.model_validate(res)

    @mcp.tool(annotations=READ)
    async def search_evidence(
        ctx: Context,
        requirement: Annotated[str, Field(min_length=2, max_length=500, description="One job requirement, e.g. 'Celery background jobs'")],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        filters: EvidenceFilters | None = None,
    ) -> EvidenceList:
        """Find portfolio evidence (case studies, repos, code, reviews, past proposals) that proves a requirement.
        Each item has type, source, date and (for proposals) outcome. Cite evidence_id when making a claim."""
        b = backend_for(persona_from_ctx(ctx))
        f: dict[str, Any] = filters.model_dump(exclude_none=True) if filters else {}
        items = [Evidence.model_validate(i) for i in await asyncio.to_thread(b.search, requirement, k, f)]
        return EvidenceList(requirement=requirement, backend=b.name, items=items)

    @mcp.tool(annotations=READ)
    async def get_case_study(ctx: Context, id: Annotated[str, Field(min_length=1, max_length=200)]) -> CaseStudy:
        """Full text of one portfolio item (case study id like 'case-churn-predictor', repo slug, or item id)."""
        item = backend_for(persona_from_ctx(ctx)).get_item(id)
        if not item:
            raise ToolError(f"not_found: {id}")
        return CaseStudy.model_validate(item)

    @mcp.tool(annotations=READ)
    async def list_skills(ctx: Context) -> SkillList:
        """Skills that appear in the portfolio with how often and in which projects (proposals excluded)."""
        return SkillList(skills=[SkillCount.model_validate(s) for s in backend_for(persona_from_ctx(ctx)).list_skills()])
