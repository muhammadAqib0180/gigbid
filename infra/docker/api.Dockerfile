# api (same Python base layers as the other Python services, so builds share cache)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    FASTEMBED_CACHE=/models HF_HUB_DISABLE_PROGRESS_BARS=1
RUN pip install --no-cache-dir uv==0.13.8
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY agent ./agent
COPY rag ./rag
COPY mcp_servers ./mcp_servers
COPY gigsim ./gigsim
COPY apps/api ./apps/api
COPY apps/__init__.py ./apps/__init__.py
COPY worker ./worker
COPY scripts ./scripts
COPY evals ./evals
COPY data/personas ./data/personas
COPY data/policy_pack ./data/policy_pack
ENV PATH="/app/.venv/bin:$PATH" GIGBID_DATA_DIR=/app/data
# bake the open embedding + reranker models into the image (CPU, ONNX) so containers start offline
RUN python -c "from rag.index.models import embedder, reranker; embedder(); reranker()"
RUN useradd -m gigbid && mkdir -p /app/data/processed && chown -R gigbid /app/data /models
USER gigbid
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
