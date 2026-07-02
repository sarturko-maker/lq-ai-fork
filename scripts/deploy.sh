#!/usr/bin/env bash
#
# deploy.sh — deploy one pinned image SHA to a hosted tenant stack. SAAS-3,
# ADR-F060 D1/D5. Runs ON THE NODE (the GitHub `deploy-staging` job SSHes in and
# invokes it); the node holds docker-compose.prod.yml + the root-owned .env.prod
# in $LQ_AI_STACK_DIR, but no repo checkout.
#
# Pipeline (SAAS-HOSTING §5.3): pull → dedicated migrate → up --wait → smoke.
# Roll-forward-only; rollback = re-run with the previous SHA.
#
#   LQ_AI_IMAGE_TAG=sha-<12hex>  ./deploy.sh
#   ./deploy.sh sha-<12hex>
#
# Env:
#   LQ_AI_IMAGE_TAG        image tag to deploy (or pass as $1). MUST be sha-<hex>,
#                          never :main (a moving pointer breaks rollback).
#   LQ_AI_STACK_DIR        stack dir holding the compose + .env.prod (default /opt/lq-ai).
#   COMPOSE_PROJECT_NAME   per-tenant compose project (default lq-ai).
set -euo pipefail

TAG="${1:-${LQ_AI_IMAGE_TAG:-}}"
STACK_DIR="${LQ_AI_STACK_DIR:-/opt/lq-ai}"
PROJECT="${COMPOSE_PROJECT_NAME:-lq-ai}"
COMPOSE_FILE="$STACK_DIR/docker-compose.prod.yml"
ENV_FILE="$STACK_DIR/.env.prod"

die() { echo "deploy: $*" >&2; exit 1; }

[ -n "$TAG" ] || die "no image tag (pass \$1 or set LQ_AI_IMAGE_TAG)"
# Immutable-SHA contract: reject :main and anything not shaped like sha-<hex>.
case "$TAG" in
	sha-*) : ;;
	*) die "refusing tag '$TAG' — deploy a published sha-<hex> tag, never :main" ;;
esac
printf '%s' "$TAG" | grep -Eq '^sha-[0-9a-f]{7,}$' || die "malformed tag '$TAG' (want sha-<hex>)"
[ -f "$COMPOSE_FILE" ] || die "missing $COMPOSE_FILE"
[ -f "$ENV_FILE" ] || die "missing $ENV_FILE"
command -v docker >/dev/null 2>&1 || die "docker not found on the node"

# One compose invocation, everywhere — pinned project + file + env-file. The
# per-invocation LQ_AI_IMAGE_TAG (exported below) drives the image: refs.
dc() { docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

export LQ_AI_IMAGE_TAG="$TAG"
echo "deploy: project=$PROJECT tag=$TAG dir=$STACK_DIR"

echo "deploy: [1/4] pulling images…"
dc pull

# [2/4] Dedicated migrate step (ADR-F060 D5): a failed migration fails the DEPLOY
# here, before new containers take traffic, instead of surfacing as a crash-loop.
# LQ_AI_SKIP_MIGRATIONS=1 makes the entrypoint skip its own advisory-locked run so
# this is the single, explicit upgrade (the entrypoint lock stays the worker race
# guard on `up`).
echo "deploy: [2/4] running alembic upgrade head…"
dc run --rm -e LQ_AI_SKIP_MIGRATIONS=1 api alembic upgrade head

echo "deploy: [3/4] starting services (up -d --wait)…"
dc up -d --wait --remove-orphans

# [4/4] Smoke the PUBLIC edge — proves Caddy is terminating TLS with a valid cert
# and routing to the app. First-ever deploy issues the cert via DNS-01 during
# `up`, which can lag DNS propagation, so retry before giving up.
HOST="$(dc exec -T caddy printenv LQ_AI_PUBLIC_HOST 2>/dev/null || true)"
[ -n "$HOST" ] || die "could not read LQ_AI_PUBLIC_HOST from the caddy service"
# A wildcard host (*.tenant…) has no literal A record to curl — smoke a concrete
# label under it instead.
case "$HOST" in
	\*.*) SMOKE_HOST="smoke.${HOST#\*.}" ;;
	*) SMOKE_HOST="$HOST" ;;
esac
URL="https://$SMOKE_HOST/health"
echo "deploy: [4/4] smoking $URL …"
ok=0
for attempt in $(seq 1 12); do
	if curl -fsS --max-time 10 -o /dev/null "$URL"; then
		ok=1
		break
	fi
	echo "deploy: smoke attempt $attempt failed (cert may still be issuing); retrying in 5s…"
	sleep 5
done
[ "$ok" = "1" ] || die "smoke check failed for $URL after retries"

echo "deploy: OK — $PROJECT is serving $TAG at https://$SMOKE_HOST"
