#!/usr/bin/env bash
#
# gen-secrets.sh — mint fresh per-stack secrets for a hosted tenant's .env.prod.
# SAAS-3, ADR-F060 D6. Prints KEY=value lines to STDOUT ONLY; the values NEVER
# touch the repo or any file in the working tree (the .env.bak leak is the
# standing lesson). On the NODE, as the stack owner, append to the root-owned
# .env.prod:
#
#     bash scripts/gen-secrets.sh >> /opt/lq-ai/.env.prod && chmod 600 /opt/lq-ai/.env.prod
#
# Then fill in the PROCURED, non-secret values (hostnames, S3 endpoint, DNS
# token, provider keys) from .env.prod.example.
#
# PRIVATE profile (ADR-F070, .env.private.example): pass --private to ALSO mint
# the on-box MinIO root credentials and the MATCHING S3_ACCESS_KEY/S3_SECRET_KEY
# pair — nothing S3-related to procure:
#
#     bash scripts/gen-secrets.sh --private >> /opt/lq-ai/.env.private
#
# Without --private the output is exactly the public-path set (no S3_* lines
# that could shadow procured external-S3 values).
#
# Re-running mints BRAND-NEW values — do that ONLY on a deliberate rotation:
# rotating JWT_SECRET forces every user to re-login, rotating POSTGRES_PASSWORD
# needs the DB role's password changed to match, and rotating
# LQ_AI_GATEWAY_MASTER_KEY orphans every already-encrypted provider key.
#
# Requires: openssl (present on any stock Linux node).
set -euo pipefail

private=0
for arg in "$@"; do
	case "$arg" in
	--private) private=1 ;;
	*)
		echo "gen-secrets: unknown argument '$arg' (usage: gen-secrets.sh [--private])" >&2
		exit 2
		;;
	esac
done

if ! command -v openssl >/dev/null 2>&1; then
	echo "gen-secrets: 'openssl' not found on PATH" >&2
	exit 1
fi

# Hex for any secret that ends up embedded in a URL (POSTGRES_PASSWORD flows into
# DATABASE_URL) — hex has no +, /, @, : to percent-escape.
hex32() { openssl rand -hex 32; }

# A Fernet key is urlsafe-base64 of 32 random bytes (gateway LQ_AI_GATEWAY_MASTER_KEY,
# gateway/app/secrets.py). `openssl rand -base64 32` is standard base64; map +/ to
# -_ for the urlsafe alphabet Fernet requires.
fernet_key() { openssl rand -base64 32 | tr '+/' '-_'; }

cat <<EOF
# ---------------------------------------------------------------------------
# Generated $(date -u '+%Y-%m-%dT%H:%M:%SZ') by scripts/gen-secrets.sh — DO NOT COMMIT.
# Root-owned, chmod 600. One set per tenant stack (ADR-F058 isolation).
# ---------------------------------------------------------------------------
POSTGRES_PASSWORD=$(hex32)
JWT_SECRET=$(hex32)
LQ_AI_GATEWAY_KEY=$(hex32)
LQ_AI_GATEWAY_MASTER_KEY=$(fernet_key)
COLLABORA_ADMIN_USER=lqops
COLLABORA_ADMIN_PASSWORD=$(hex32)
EOF

if [ "$private" -eq 1 ]; then
	# Private profile (ADR-F070): the S3 credentials ARE the MinIO root
	# credentials, so the pairs must match — mint once, emit twice.
	minio_user="lq-ai-$(openssl rand -hex 4)"
	minio_password=$(hex32)
	cat <<EOF
# --- private profile only (ADR-F070: on-box MinIO, docker-compose.private.yml).
# S3_ACCESS_KEY/S3_SECRET_KEY deliberately MATCH MINIO_ROOT_USER/PASSWORD.
MINIO_ROOT_USER=$minio_user
MINIO_ROOT_PASSWORD=$minio_password
S3_ACCESS_KEY=$minio_user
S3_SECRET_KEY=$minio_password
EOF
fi
