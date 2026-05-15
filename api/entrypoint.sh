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
# Alembic acquires a Postgres advisory lock via its env.py setup, so
# multiple workers / replicas racing this step coordinate correctly:
# the first to acquire the lock applies migrations, the rest no-op
# once they see the schema is current.
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

echo "LQ.AI api: starting uvicorn on 0.0.0.0:8000."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
