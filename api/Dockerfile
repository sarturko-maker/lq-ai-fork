# syntax=docker/dockerfile:1.7

FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps from pyproject.toml (no dev extras in the image)
COPY api/pyproject.toml api/README.md ./
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
COPY api/app/ ./app/
COPY api/alembic.ini ./alembic.ini
COPY api/alembic/ ./alembic/
COPY api/entrypoint.sh /usr/local/bin/lq-ai-entrypoint
RUN chmod +x /usr/local/bin/lq-ai-entrypoint

# SAAS-1 (ADR-F058 Mode 2): build context is now the REPO ROOT (see
# docker-compose.yml / images.yml / release.yml `context: .` + `file:
# ./api/Dockerfile`) specifically so this line can reach skills/ — it lives
# outside api/ and a prod host has no separate repo checkout to bind-mount it
# from. Baking it in kills the migration-0032 fresh-DB trap (it reads
# /skills/playbooks/nda/playbook.yaml) for good, not just in dev where the
# ./skills:/skills:ro bind mount (docker-compose.yml) happened to cover it.
COPY skills/ /skills/

# B-7a (ADR-F067 D4): the shipped agent-profile manifests, baked in for the same
# reason as skills/ — they live outside api/ and the API loads them at boot
# (app/profiles/), fail-loud if the dir is absent. Dev also bind-mounts
# ./profiles:/profiles:ro so host edits are live without a rebuild.
COPY profiles/ /profiles/

EXPOSE 8000

# The entrypoint runs `alembic upgrade head` before exec'ing uvicorn so a
# fresh deployment lands a fully-migrated schema before the HTTP server
# accepts traffic. Operators handling migrations out-of-band can set
# LQ_AI_SKIP_MIGRATIONS=1 to bypass the step.
ENTRYPOINT ["/usr/local/bin/lq-ai-entrypoint"]
