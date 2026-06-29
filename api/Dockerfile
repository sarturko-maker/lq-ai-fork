# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps from pyproject.toml (no dev extras in the image)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .
# C4 (ADR-F031): Adeu installed --no-deps — its hard fastmcp[apps] dep would pull
# starlette 0.48 / mcp / pydantic 2.13 and break our pinned FastAPI stack. We never
# use Adeu's FastMCP server (a second egress); its real SDK deps are in pyproject.
RUN pip install --no-cache-dir --no-deps "adeu==1.12.1"

# F2 Slice C1 (ADR-F049): bundle the local embedder's ONNX model at BUILD so the
# first matter search never triggers a Hugging Face download at runtime (ADR-0008
# boot-latency / outage rule). The runtime provider reads the same path via
# EMBEDDING_CACHE_DIR (app.config.Settings.embedding_cache_dir).
ENV EMBEDDING_CACHE_DIR=/opt/fastembed-cache
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5', cache_dir='/opt/fastembed-cache')"

# F2 Slice D (ADR-F049): bundle the cross-encoder reranker's ONNX model at BUILD too
# (same boot-latency/outage rationale; reuses fastembed — no new dependency). The
# runtime provider reads RERANK_CACHE_DIR (app.config.Settings.rerank_cache_dir).
ENV RERANK_CACHE_DIR=/opt/fastembed-cache
RUN python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2', cache_dir='/opt/fastembed-cache')"

# Copy application code, migration files, and the entrypoint script
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY entrypoint.sh /usr/local/bin/lq-ai-entrypoint
RUN chmod +x /usr/local/bin/lq-ai-entrypoint

EXPOSE 8000

# The entrypoint runs `alembic upgrade head` before exec'ing uvicorn so a
# fresh deployment lands a fully-migrated schema before the HTTP server
# accepts traffic. Operators handling migrations out-of-band can set
# LQ_AI_SKIP_MIGRATIONS=1 to bypass the step.
ENTRYPOINT ["/usr/local/bin/lq-ai-entrypoint"]
