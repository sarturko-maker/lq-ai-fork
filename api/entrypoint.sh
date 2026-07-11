#!/bin/sh
set -e

# api container entrypoint.
#
# The api service is the single owner of the database schema in the
# Compose stack. We run `alembic upgrade head` before exec'ing uvicorn
# so a fresh deployment lands a fully-migrated schema by the time the
# HTTP server accepts traffic. If migrations fail, this script fails —
# the container does not start a half-configured api.
#
# env.py's run_migrations_online() acquires a Postgres session-level
# advisory lock (MIGRATION_ADVISORY_LOCK_KEY) around the migration run,
# so multiple workers / replicas racing this step coordinate correctly:
# the first to acquire the lock applies migrations to head, the rest
# block then no-op once they see the schema is current (HS-1).
#
# Operators on a deployment that handles migrations out-of-band (an
# external job, a sidecar, Kubernetes pre-deploy hook, etc.) can
# disable the in-entrypoint step by setting LQ_AI_SKIP_MIGRATIONS=1.

if [ "${LQ_AI_SKIP_MIGRATIONS:-0}" = "1" ]; then
    echo "LQ.AI api: LQ_AI_SKIP_MIGRATIONS=1 set; skipping alembic upgrade head."
else
    echo "LQ.AI api: running alembic upgrade head…"
    alembic upgrade head
    echo "LQ.AI api: migrations complete."
fi

# Respect the container's CMD when one is provided — the api service runs
# without an override (and gets uvicorn) while the ingest-worker service
# passes `arq app.workers.document_pipeline.WorkerSettings`. Hardcoding
# `exec uvicorn` here silently turned the ingest-worker into a duplicate
# api server (surfaced 2026-05-16 when KB ingestion stopped completing
# after a worker image rebuild).
# HTTP keep-alive timeout. uvicorn's default is 5s, which is SHORTER than both a
# fronting reverse proxy's upstream idle timeout (our shipped Caddy keeps upstream
# connections ~120s and reuses them) and the multi-second gaps between a browser's
# requests during a multi-step flow (e.g. the setup wizard). When the server closes
# an idle keep-alive connection the client still believes is live and the client
# then reuses it, the request fails mid-flight — surfacing as a sporadic
# "Failed to fetch" in the SPA on otherwise-valid requests (login, wizard steps).
# Fix: keep the SERVER timeout comfortably ABOVE the fronting proxy's idle timeout
# so the proxy/browser is always the side that closes an idle connection, never the
# server mid-request. Default 130 clears Caddy's ~120s upstream idle; an operator
# fronting the api with a proxy that idles longer must raise this to exceed it.
KEEP_ALIVE="${LQ_AI_HTTP_KEEP_ALIVE_TIMEOUT:-130}"

if [ "$#" -eq 0 ]; then
    echo "LQ.AI api: starting uvicorn on 0.0.0.0:8000 (keep-alive ${KEEP_ALIVE}s)."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive "${KEEP_ALIVE}"
else
    echo "LQ.AI api: exec'ing container CMD: $*"
    exec "$@"
fi
