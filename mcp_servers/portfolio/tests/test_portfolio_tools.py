import os

from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.backends import LiteBackend
from mcp_servers.portfolio.server import mcp


async def test_search_evidence_finds_implied_skill():
    os.environ["PORTFOLIO_PERSONA"] = "fullstack_web"
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("search_evidence", {"requirement": "background jobs that retry with Celery", "k": 5})
        items = r.structuredContent["items"]
        assert items and all({"type", "source", "evidence_id"} <= set(i) for i in items)
        assert any("django-crm" in (i.get("project") or "") or "lms" in (i.get("project") or "") for i in items)


async def test_resources_and_prompts_exposed():
    async with connect(mcp._mcp_server) as s:
        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= templates
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert "answer_screening_question" in prompts


async def test_get_case_study_and_skills():
    os.environ["PORTFOLIO_PERSONA"] = "data_analyst"
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("get_case_study", {"id": "case-dbt-warehouse"})
        assert "dbt" in r.structuredContent["text"]
        skills = (await s.call_tool("list_skills", {})).structuredContent["skills"]
        assert any(k["skill"] == "SQL" for k in skills)


def test_lite_backend_standalone(tmp_path):
    (tmp_path / "case-1.md").write_text("# Churn model\nI built a churn model in scikit-learn that lifted recall to 0.68.")
    (tmp_path / "notes.txt").write_text("Gardening tips")
    b = LiteBackend(tmp_path)
    hits = b.search("churn prediction scikit-learn", 3, {})
    assert hits and hits[0]["item_id"] == "case-1.md"
