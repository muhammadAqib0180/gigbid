One Dockerfile per service (all Python services share identical base layers, so Docker builds them once):

| Dockerfile | Service | Port |
|---|---|---|
| api.Dockerfile | FastAPI (`apps/api`) | 8000 |
| worker.Dockerfile | Arq worker (`worker/`) | - |
| gigsim.Dockerfile | GigSim simulator | 8081 |
| mcp-portfolio.Dockerfile | Portfolio MCP (Streamable HTTP) | 8101 |
| mcp-marketplace.Dockerfile | Marketplace MCP | 8102 |
| mcp-workspace.Dockerfile | Workspace MCP | 8103 |
| web.Dockerfile | Next.js (standalone) | 3000 |
| allinone.Dockerfile | everything in one container for free single-container hosts | 7860 |

Postgres, Redis, Qdrant, Ollama and Caddy use official images (see `../docker-compose.yml`).
