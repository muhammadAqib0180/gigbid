# ADR 0002 - Stack
FastAPI + Next.js (App Router, TS, client generated from OpenAPI with `openapi-typescript` + `openapi-fetch`); LangGraph
(hand-written StateGraphs); official MCP Python SDK (FastMCP) for our three servers; `langchain-mcp-adapters`
(`MultiServerMCPClient`) on the agent side; Postgres for app data + checkpointer + LangGraph store + audit log; Redis for
Arq + pub/sub; Qdrant as the vector store in compose (numpy in-process locally, identical results); LangSmith tracing
with a masking client. **Why:** each is the reference choice named in the brief, and every one has a local fallback
(SQLite, in-process queue, in-process MCP) so the whole system also runs on a laptop without Docker.
