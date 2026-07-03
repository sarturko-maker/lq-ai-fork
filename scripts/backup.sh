#!/usr/bin/env bash
#
# backup.sh — encrypted Postgres backup for a hosted tenant stack. SAAS-3,
# ADR-F060 D4. Streams pg_dump -Fc → age (asymmetric; the node holds only the
# PUBLIC recipient, so a compromised node cannot read its own history) → S3-
# compatible object storage under tenants/<id>/backups/, then pings a dead-man
# switch. Intended as a nightly cron on the node (see the staging-bringup runbook).
#
# Node deps: docker + age (a single static binary). The DB credentials never
# leave the postgres container; the S3 upload runs in a pinned aws-cli container
# so the node needs no aws-cli install.
#
# Reads its config from the ENVIRONMENT (the cron sources the stack's .env.prod
# first). Required: LQ_AI_TENANT_ID, LQ_AI_BACKUP_AGE_RECIPIENT, S3_ENDPOINT_URL,
# S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_REGION. Optional:
# LQ_AI_BACKUP_DEADMAN_URL, LQ_AI_STACK_DIR (/opt/lq-ai), COMPOSE_PROJECT_NAME
# (lq-ai), LQ_AI_AWSCLI_IMAGE.
#
# Retention (7 daily / 4 weekly) is enforced by the bucket's LIFECYCLE rule, not
# this script — see the runbook. Customer files in object storage are covered by
# bucket versioning, NOT this DB dump (ADR-F060 D4).
set -euo pipefail

STACK_DIR="${LQ_AI_STACK_DIR:-/opt/lq-ai}"
PROJECT="${COMPOSE_PROJECT_NAME:-lq-ai}"
COMPOSE_FILE="$STACK_DIR/docker-compose.prod.yml"
ENV_FILE="$STACK_DIR/.env.prod"
AWSCLI_IMAGE="${LQ_AI_AWSCLI_IMAGE:-amazon/aws-cli:2.17.0}"

die() { echo "backup: $*" >&2; exit 1; }

for var in LQ_AI_TENANT_ID LQ_AI_BACKUP_AGE_RECIPIENT \
	S3_ENDPOINT_URL S3_ACCESS_KEY S3_SECRET_KEY S3_BUCKET S3_REGION; do
	[ -n "${!var:-}" ] || die "$var is required (source the stack's .env.prod first)"
done
command -v docker >/dev/null 2>&1 || die "docker not found on the node"
command -v age >/dev/null 2>&1 || die "age not found (single static binary — see the runbook)"
[ -f "$COMPOSE_FILE" ] || die "missing $COMPOSE_FILE"
[ -f "$ENV_FILE" ] || die "missing $ENV_FILE"

dc() { docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
stamp="$(date -u '+%Y/%m/%dT%H%M%SZ')"
key="tenants/$LQ_AI_TENANT_ID/backups/$stamp.dump.age"

echo "backup: dumping postgres (pg_dump -Fc)…"
# Dump INSIDE the container so DB creds never touch the node: pg_dump reads the
# postgres service's own POSTGRES_* env; -Fc is the compressed, pg_restore-able
# custom format.
# shellcheck disable=SC2016  # intentional: $POSTGRES_* expand in the CONTAINER, not the host
dc exec -T postgres sh -c \
	'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
	>"$tmp/db.dump"
[ -s "$tmp/db.dump" ] || die "pg_dump produced an empty file"
# A custom-format archive begins with the magic string "PGDMP" — a cheap guard
# against silently uploading a truncated / error-page dump.
head -c 5 "$tmp/db.dump" | grep -q 'PGDMP' || die "output is not a pg_dump -Fc archive"

echo "backup: encrypting (age -r, asymmetric)…"
age -r "$LQ_AI_BACKUP_AGE_RECIPIENT" -o "$tmp/db.dump.age" "$tmp/db.dump"

echo "backup: uploading s3://$S3_BUCKET/$key …"
# Secret VALUES must never ride in docker's argv — argv is world-readable via
# /proc/*/cmdline (SETUP-2 review). Env-prefix the credentials and pass `-e NAME`
# with no value: docker then reads them from its own environment.
AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
AWS_DEFAULT_REGION="$S3_REGION" \
docker run --rm -i \
	-e AWS_ACCESS_KEY_ID \
	-e AWS_SECRET_ACCESS_KEY \
	-e AWS_DEFAULT_REGION \
	"$AWSCLI_IMAGE" \
	s3 cp - "s3://$S3_BUCKET/$key" --endpoint-url "$S3_ENDPOINT_URL" \
	<"$tmp/db.dump.age"

echo "backup: OK — s3://$S3_BUCKET/$key ($(wc -c <"$tmp/db.dump.age") bytes encrypted)"

# Dead-man switch: ping ONLY after full success, so a silent backup failure is
# itself the alert (the switch fires when the expected ping doesn't arrive).
if [ -n "${LQ_AI_BACKUP_DEADMAN_URL:-}" ]; then
	curl -fsS --max-time 15 -o /dev/null "$LQ_AI_BACKUP_DEADMAN_URL" \
		|| echo "backup: WARN dead-man ping failed (backup itself succeeded)" >&2
fi
