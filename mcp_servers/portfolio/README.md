# portfolio-evidence-mcp

An MCP server that turns a folder of your work - case studies, READMEs, code, reviews, past proposals - into
**evidence your AI assistant can cite**. Ask "which of my projects proves I can do X?" or "answer this
screening question from my portfolio" and every claim comes back with the file it came from.

Built for [GigBid](https://github.com/muhammadAqib0180/gigbid) (an AI-4016 project), usable on its own in Claude Desktop, Cursor or any MCP host.

## Install / run

```bash
uvx portfolio-evidence-mcp --corpus ~/my-portfolio          # stdio (for desktop hosts)
uvx portfolio-evidence-mcp --corpus ~/my-portfolio --http --port 8101   # Streamable HTTP
```

Docker: `docker build -f infra/docker/mcp-portfolio.Dockerfile .` from the [GigBid repo](https://github.com/muhammadAqib0180/gigbid).

### Claude Desktop (`claude_desktop_config.json`) / Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "portfolio": { "command": "uvx", "args": ["portfolio-evidence-mcp", "--corpus", "/absolute/path/to/my-portfolio"] }
  }
}
```

## What it exposes

| Kind | Name | What it does |
|---|---|---|
| tool (read-only) | `search_evidence(requirement, k, filters)` | ranked evidence items with type, source, date and (for proposals) outcome |
| tool (read-only) | `match_requirements(job_title, job_text, requirements, k)` | maps every requirement of a job to evidence in one call; weak requirements are flagged so you never claim them |
| tool (read-only) | `get_case_study(id)` | full text of one item |
| tool (read-only) | `list_skills()` | skills in the portfolio and where they appear |
| resource | `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{slug}`, `portfolio://index` | load full items into context |
| prompt | "Answer a screening question from my portfolio" | cites evidence ids, refuses to invent experience |
| prompt | "Write an opening line for this job" | job post treated as untrusted data |
| prompt | "Which of my projects proves this requirement?" | top 3 items with reasons |

Standalone mode ranks with BM25 over your files (no API keys, no network). Inside GigBid it uses the measured
RAG pipeline (requirement decomposition + hybrid BM25/dense + outcome boost + multi-vector grouping; the cross-encoder
re-ranker was dropped because it lowered recall - see the [R&D report](https://github.com/muhammadAqib0180/gigbid/blob/main/report/GigBid_RD_Report.pdf)).

## Safety
Read-only: every tool is annotated `readOnlyHint: true`. Nothing leaves your machine in stdio mode.

MIT licence.
