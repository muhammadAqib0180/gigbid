# Single-container image for free hosts (Hugging Face Spaces, Render, Fly): GigSim + API (inline worker,
# in-process MCP servers, SQLite) + Next.js behind one port. docker compose remains the reference deployment.
FROM node:22-alpine AS web
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1 API_URL=http://127.0.0.1:8000
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy FASTEMBED_CACHE=/models HF_HUB_DISABLE_PROGRESS_BARS=1 \
    GIGBID_MCP_INPROCESS=1 WORKER_MODE=inline GIGSIM_BASE_URL=http://127.0.0.1:8081 GIGSIM_AUTO_TICK_SECONDS=60 \
    SEED_ON_START=1 MODEL_PROFILE=open PORT=7860
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.13.8
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY agent ./agent
COPY rag ./rag
COPY mcp_servers ./mcp_servers
COPY gigsim ./gigsim
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY worker ./worker
COPY scripts ./scripts
COPY evals ./evals
COPY data/personas ./data/personas
COPY data/policy_pack ./data/policy_pack
COPY --from=web /web/.next/standalone ./web
COPY --from=web /web/.next/static ./web/.next/static
ENV PATH="/app/.venv/bin:$PATH" GIGBID_DATA_DIR=/app/data
RUN python -c "from rag.index.models import embedder, reranker; embedder(); reranker()" && useradd -m -u 1000 gigbid \
    && mkdir -p /app/data/processed && chown -R gigbid /app /models
USER gigbid
EXPOSE 7860
CMD ["python", "-m", "scripts.run_all"]
