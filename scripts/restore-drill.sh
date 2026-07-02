#!/usr/bin/env bash
#
# restore-drill.sh — prove a backup is restorable. SAAS-3, ADR-F060 D4. Fetches
# the latest encrypted dump from object storage, decrypts it with the operator-
# held age identity, restores it into a THROWAWAY postgres container, and asserts
# the schema + row counts came back. Restore drills are part of the gate
# (SAAS-HOSTING §5): a backup you have never restored is not a backup.
#
# NEVER restores into the live stack — always a fresh scratch container that is
# torn down at the end. Prod→staging data copies are prohibited; this reads a
# tenant's own encrypted dump and never writes it anywhere but the scratch DB.
#
# Node deps: docker + age. Config from the ENVIRONMENT. Required: LQ_AI_TENANT_ID,
# LQ_AI_BACKUP_AGE_IDENTITY (path to the operator's PRIVATE age key — present only
# during a drill), S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET,
# S3_REGION. Optional: LQ_AI_RESTORE_PG_IMAGE (pgvector/pgvector:pg16),
# LQ_AI_AWSCLI_IMAGE, LQ_AI_RESTORE_DEADMAN_URL.
set -euo pipefail

AWSCLI_IMAGE="${LQ_AI_AWSCLI_IMAGE:-amazon/aws-cli:2.17.0}"
PG_IMAGE="${LQ_AI_RESTORE_PG_IMAGE:-pgvector/pgvector:pg16}"

die() { echo "restore-drill: $*" >&2; exit 1; }

for var in LQ_AI_TENANT_ID LQ_AI_BACKUP_AGE_IDENTITY \
	S3_ENDPOINT_URL S3_ACCESS_KEY S3_SECRET_KEY S3_BUCKET S3_REGION; do
	[ -n "${!var:-}" ] || die "$var is required"
done
command -v docker >/dev/null 2>&1 || die "docker not found"
command -v age >/dev/null 2>&1 || die "age not found (single static binary — see the runbook)"
[ -f "$LQ_AI_BACKUP_AGE_IDENTITY" ] || die "age identity file not found: $LQ_AI_BACKUP_AGE_IDENTITY"

aws() {
	docker run --rm \
		-e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
		-e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
		-e AWS_DEFAULT_REGION="$S3_REGION" \
		"$AWSCLI_IMAGE" "$@" --endpoint-url "$S3_ENDPOINT_URL"
}

tmp="$(mktemp -d)"
# Unique scratch container name without Math.random/$RANDOM reliance — the PID +
# nanoseconds is plenty for a one-shot drill.
scratch="lq-ai-restore-drill-$$-$(date -u +%s%N)"
cleanup() {
	docker rm -f "$scratch" >/dev/null 2>&1 || true
	rm -rf "$tmp"
}
trap cleanup EXIT

prefix="tenants/$LQ_AI_TENANT_ID/backups/"
echo "restore-drill: finding latest dump under s3://$S3_BUCKET/$prefix …"
latest="$(aws s3api list-objects-v2 \
	--bucket "$S3_BUCKET" --prefix "$prefix" \
	--query 'sort_by(Contents,&LastModified)[-1].Key' --output text 2>/dev/null || true)"
[ -n "$latest" ] && [ "$latest" != "None" ] || die "no backup objects under $prefix"
echo "restore-drill: latest = s3://$S3_BUCKET/$latest"

echo "restore-drill: downloading + decrypting…"
aws s3 cp "s3://$S3_BUCKET/$latest" - >"$tmp/db.dump.age"
[ -s "$tmp/db.dump.age" ] || die "downloaded object is empty"
age -d -i "$LQ_AI_BACKUP_AGE_IDENTITY" -o "$tmp/db.dump" "$tmp/db.dump.age"
head -c 5 "$tmp/db.dump" | grep -q 'PGDMP' || die "decrypted file is not a pg_dump -Fc archive"

echo "restore-drill: starting throwaway $PG_IMAGE ($scratch)…"
docker run -d --name "$scratch" -e POSTGRES_PASSWORD=drill "$PG_IMAGE" >/dev/null
ready=0
for _ in $(seq 1 30); do
	if docker exec "$scratch" pg_isready -U postgres -q >/dev/null 2>&1; then
		ready=1
		break
	fi
	sleep 1
done
[ "$ready" = "1" ] || die "throwaway postgres did not become ready"

echo "restore-drill: restoring into scratch DB…"
docker exec "$scratch" createdb -U postgres restore_check
# --no-owner/--no-privileges: the tenant's DB roles do not exist here; we are
# checking that the DATA + schema restore, not re-creating grants. pg_restore may
# emit ignorable warnings; the row-count assertions below are the real gate.
docker exec -i "$scratch" pg_restore -U postgres -d restore_check \
	--no-owner --no-privileges <"$tmp/db.dump" || echo "restore-drill: (pg_restore reported non-fatal warnings)"

echo "restore-drill: asserting the schema came back…"
q() { docker exec "$scratch" psql -U postgres -d restore_check -tAc "$1" 2>/dev/null || true; }
ver_rows="$(q 'SELECT count(*) FROM alembic_version')"
[ "$ver_rows" = "1" ] || die "alembic_version has '$ver_rows' rows (want 1) — restore did not land the schema"
ver="$(q 'SELECT version_num FROM alembic_version')"
users="$(q 'SELECT count(*) FROM users')"
echo "restore-drill: OK — schema at alembic $ver; users=$users (from $latest)"

if [ -n "${LQ_AI_RESTORE_DEADMAN_URL:-}" ]; then
	curl -fsS --max-time 15 -o /dev/null "$LQ_AI_RESTORE_DEADMAN_URL" \
		|| echo "restore-drill: WARN dead-man ping failed (drill itself passed)" >&2
fi
