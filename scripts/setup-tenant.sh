#!/usr/bin/env bash
#
# setup-tenant.sh — the operator's tenant-setup wizard (SETUP-2). Turns one
# tenant's inputs into the node-side artifacts a hosted LQ.AI Oscar Edition
# stack boots from, then (optionally) deploys it and prints the admin handover.
# Governing: docs/fork/plans/SAAS-SETUP-onboarding-architecture.md §3, ADR-F060,
# ADR-F058. Sibling to gen-secrets.sh / deploy.sh / backup.sh — same node, same
# root-owned /opt/lq-ai, same "secrets live only on the node" posture.
#
# TWO MODES
#   Non-interactive:  setup-tenant.sh --manifest tenant-acme.conf
#   Interactive:      setup-tenant.sh            (prompts, then WRITES a manifest
#                                                 so the run is repeatable)
#
# THE MANIFEST is a flat KEY=VALUE env-format file (NOT the plan's "tenants/
# <id>.yaml"). env-format is the v1 pragmatic choice: bash-native, no YAML
# parser on the node, and the manifest is operator-PRIVATE — it is never
# committed and, by hard rule below, never carries a secret.
#
# SECRETS ARE NEVER IN THE MANIFEST (the .env.bak leak is the standing lesson).
# A manifest that carries a secret-suffixed key with a value is REFUSED. Secrets
# come from the invoking ENVIRONMENT (non-interactive) or `read -rs` prompts
# (interactive):  LQ_AI_DNS_API_TOKEN, S3_ACCESS_KEY, S3_SECRET_KEY,
# ANTHROPIC_API_KEY, and SMTP_PASSWORD (only when SMTP_HOST is set). Generated
# secrets come from scripts/gen-secrets.sh (invoked, not duplicated).
#
# ARTIFACTS (node-side only; nothing touches the repo):
#   <out-dir>/.env.prod            root-owned, chmod 600 — every ${VAR:?} the
#                                  prod compose requires + the optional knobs
#   <out-dir>/gateway.yaml         chmod 600 — rendered from
#                                  deploy/gateway/tenant-gateway.yaml.example
#                                  (api_key_env indirection; NO key material)
#   <out-dir>/dns-records.txt      the A/AAAA/CAA records to create
#   <out-dir>/cron.d-lq-ai-backup  ready-to-install nightly backup cron
#   plus the stack files (compose + deploy/backup scripts) synced into <out-dir>
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

die() { echo "setup-tenant: $*" >&2; exit 1; }
info() { echo "setup-tenant: $*"; }
warn() { echo "setup-tenant: WARN $*" >&2; }

# --- The compiled-in DNS provider set (SETUP-1). Anything else would brick the
#     Caddy edge at startup, so the wizard rejects it here, loudly. -----------
readonly SUPPORTED_DNS_PROVIDERS="hetzner ionos"
# v1 renders a single-provider (Anthropic, non-PRC) gateway seed; structured so
# more providers can slot in later (decision table #8 keeps BYOK operator-only).
readonly SUPPORTED_MODEL_PROVIDERS="anthropic"
readonly TENANT_GATEWAY_SEED="$REPO_ROOT/deploy/gateway/tenant-gateway.yaml.example"
# Single source for the SMTP port default (587 = STARTTLS submission, matching
# config.py's smtp_port default) — used by the prompt and the manifest fallback.
readonly DEFAULT_SMTP_PORT=587

usage() {
	cat <<'HELPDOC'
setup-tenant.sh — operator tenant-setup wizard (SETUP-2, ADR-F060)

USAGE
  scripts/setup-tenant.sh [--manifest FILE] [options]

MODES
  --manifest FILE        Non-interactive. FILE is a flat KEY=VALUE env-format
                         manifest (see MANIFEST KEYS). Secrets must NOT appear
                         in it — they come from the environment (see SECRETS).
  (no --manifest)        Interactive: prompt for each input, then write the
                         manifest to --save-manifest so the run is repeatable.

OPTIONS
  --save-manifest FILE   Where interactive mode writes the manifest.
                         Default: ./tenant-<slug>.conf
                         (interactive mode only — rejected with --manifest)
  --out-dir DIR          Where artifacts are written. Default: /opt/lq-ai
  --create-bucket        Create the S3 bucket + versioning + backup lifecycle
                         (via the dockerized aws-cli, same as backup.sh).
  --no-deploy            Render artifacts only; do NOT run deploy.sh / handover.
  --force                Overwrite an existing <out-dir>/.env.prod (rotates the
                         generated secrets — see gen-secrets.sh's blast radius).
  --dry-run              Print what would be done; write nothing, deploy nothing.
  --help                 This help.

MANIFEST KEYS (non-secret only; values are restricted to a conservative
charset — no spaces, quotes, or shell metacharacters — because they land in a
root-sourced env file)
  TENANT_SLUG            2-32 chars of [a-z0-9-], starts/ends alphanumeric
                         (LQ_AI_TENANT_ID, compose project, bucket name)
  PUBLIC_HOST            e.g. acme.example.com or *.acme.example.com
  PUBLIC_ORIGIN          concrete host for Collabora's server_name. REQUIRED
                         when PUBLIC_HOST is a wildcard (a literal * breaks
                         Collabora); defaults to PUBLIC_HOST otherwise.
  DNS_PROVIDER           hetzner | ionos  (the compiled-in set, SETUP-1)
  ACME_EMAIL             ops email for Let's Encrypt expiry notices
  S3_ENDPOINT_URL        any S3-compatible endpoint (IONOS S3 / Hetzner OS)
  S3_REGION              provider region code (e.g. fsn1, de)
  S3_BUCKET              default: lq-ai-<slug>
  ADMIN_EMAIL            the CUSTOMER admin (becomes FIRST_RUN_ADMIN_EMAIL)
  OPERATOR_EMAIL         optional PLATFORM operator account (becomes
                         FIRST_RUN_OPERATOR_EMAIL, ADR-F061; blank/omitted =
                         no operator account — self-host semantics)
  SMTP_HOST/SMTP_PORT/SMTP_FROM/SMTP_USERNAME   optional auth-mail transport
  IMAGE_TAG             ^sha-[0-9a-f]{7,}$  (published image, never :main)
  NODE_PROFILE          full | reduced   (16 GB vs 8 GB node)
  MODEL_PROVIDER        anthropic   (v1; non-PRC default)
  RUN_DEFAULT_BUDGET_PROFILE   optional deployment default budget profile for
                         agent runs (economy | balanced | generous — ADR-F063);
                         blank/omitted = balanced
  AGE_RECIPIENT         age1…  backup public recipient (private key stays OFF node)
  BACKUP_DEADMAN_URL / RESTORE_DEADMAN_URL   optional healthchecks-style pings

SECRETS (from the ENVIRONMENT, or interactive prompt — never the manifest)
  LQ_AI_DNS_API_TOKEN   DNS provider token, scoped to the tenant zone
  S3_ACCESS_KEY         object-storage access key
  S3_SECRET_KEY         object-storage secret key
  ANTHROPIC_API_KEY     the model provider's key (api_key_env in gateway.yaml)
  SMTP_PASSWORD         only required when SMTP_HOST is set
HELPDOC
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MANIFEST=""
SAVE_MANIFEST=""
OUT_DIR="/opt/lq-ai"
CREATE_BUCKET=0
DO_DEPLOY=1
FORCE=0
DRY_RUN=0

while [ $# -gt 0 ]; do
	case "$1" in
		--manifest) MANIFEST="${2:?--manifest needs a file}"; shift 2 ;;
		--save-manifest) SAVE_MANIFEST="${2:?--save-manifest needs a file}"; shift 2 ;;
		--out-dir) OUT_DIR="${2:?--out-dir needs a dir}"; shift 2 ;;
		--create-bucket) CREATE_BUCKET=1; shift ;;
		--no-deploy) DO_DEPLOY=0; shift ;;
		--force) FORCE=1; shift ;;
		--dry-run) DRY_RUN=1; shift ;;
		--help|-h) usage; exit 0 ;;
		*) die "unknown argument '$1' (see --help)" ;;
	esac
done

# --save-manifest only makes sense interactively — with --manifest the manifest
# already exists; a silent second copy would just invite drift.
if [ -n "$MANIFEST" ] && [ -n "$SAVE_MANIFEST" ]; then
	die "--save-manifest applies to interactive mode only (with --manifest the manifest already exists)"
fi

# ---------------------------------------------------------------------------
# Input state (populated from the manifest or interactive prompts)
# ---------------------------------------------------------------------------
TENANT_SLUG="" PUBLIC_HOST="" PUBLIC_ORIGIN="" DNS_PROVIDER="" ACME_EMAIL=""
S3_ENDPOINT_URL="" S3_REGION="" S3_BUCKET="" ADMIN_EMAIL="" OPERATOR_EMAIL=""
SMTP_HOST="" SMTP_PORT="" SMTP_FROM="" SMTP_USERNAME=""
IMAGE_TAG="" NODE_PROFILE="full" MODEL_PROVIDER="anthropic"
AGE_RECIPIENT="" BACKUP_DEADMAN_URL="" RESTORE_DEADMAN_URL=""
RUN_DEFAULT_BUDGET_PROFILE=""

# ---------------------------------------------------------------------------
# Manifest loader — controlled parse (NOT `source`, which would execute code):
# allowlist every key, and refuse any secret-suffixed key that carries a value.
# The suffix set mirrors the .env.prod.example guard test's _SECRET_KEY_RE.
# ---------------------------------------------------------------------------
load_manifest() {
	local f="$1" ln key val
	[ -f "$f" ] || die "manifest not found: $f"
	while IFS= read -r ln || [ -n "$ln" ]; do
		ln="${ln%$'\r'}"                       # tolerate CRLF
		case "$ln" in ''|'#'*) continue ;; esac
		case "$ln" in *=*) : ;; *) continue ;; esac
		key="${ln%%=*}"; val="${ln#*=}"
		key="$(printf '%s' "$key" | tr -d '[:space:]')"
		# SECRET FENCE (hard rule): a secret NEVER lives in the manifest.
		case "$key" in
			*_PASSWORD|*_SECRET|*_TOKEN|*_KEY|*APPLICATION_CREDENTIALS)
				if [ -n "${val//[[:space:]]/}" ]; then
					die "manifest carries secret-shaped key '$key' with a value — secrets come from the ENVIRONMENT or a prompt, never the manifest (the .env.bak leak is the standing lesson)"
				fi ;;
		esac
		case "$key" in
			TENANT_SLUG) TENANT_SLUG="$val" ;;
			PUBLIC_HOST) PUBLIC_HOST="$val" ;;
			PUBLIC_ORIGIN) PUBLIC_ORIGIN="$val" ;;
			DNS_PROVIDER) DNS_PROVIDER="$val" ;;
			ACME_EMAIL) ACME_EMAIL="$val" ;;
			S3_ENDPOINT_URL) S3_ENDPOINT_URL="$val" ;;
			S3_REGION) S3_REGION="$val" ;;
			S3_BUCKET) S3_BUCKET="$val" ;;
			ADMIN_EMAIL) ADMIN_EMAIL="$val" ;;
			OPERATOR_EMAIL) OPERATOR_EMAIL="$val" ;;
			SMTP_HOST) SMTP_HOST="$val" ;;
			SMTP_PORT) SMTP_PORT="$val" ;;
			SMTP_FROM) SMTP_FROM="$val" ;;
			SMTP_USERNAME) SMTP_USERNAME="$val" ;;
			IMAGE_TAG) IMAGE_TAG="$val" ;;
			NODE_PROFILE) NODE_PROFILE="$val" ;;
			MODEL_PROVIDER) MODEL_PROVIDER="$val" ;;
			RUN_DEFAULT_BUDGET_PROFILE) RUN_DEFAULT_BUDGET_PROFILE="$val" ;;
			AGE_RECIPIENT) AGE_RECIPIENT="$val" ;;
			BACKUP_DEADMAN_URL) BACKUP_DEADMAN_URL="$val" ;;
			RESTORE_DEADMAN_URL) RESTORE_DEADMAN_URL="$val" ;;
			*) die "unknown manifest key '$key' (see --help for the accepted set)" ;;
		esac
	done < "$f"
}

# ---------------------------------------------------------------------------
# Interactive prompts — plain `read` (defaults shown); the manifest is written
# afterwards. Secrets are prompted separately with `read -rs` (never echoed,
# never written to the manifest).
# ---------------------------------------------------------------------------
ask() {  # ask VARNAME "prompt" "default"
	local __var="$1" __prompt="$2" __default="${3:-}" __reply=""
	if [ -n "$__default" ]; then
		read -r -p "$__prompt [$__default]: " __reply || true
		[ -n "$__reply" ] || __reply="$__default"
	else
		read -r -p "$__prompt: " __reply || true
	fi
	printf -v "$__var" '%s' "$__reply"
}

interactive_collect() {
	info "interactive setup — answers become a repeatable manifest at the end."
	ask TENANT_SLUG "Tenant slug (2-32 chars of [a-z0-9-], starts/ends alphanumeric)"
	ask PUBLIC_HOST "Public host (e.g. acme.example.com or *.acme.example.com)"
	case "$PUBLIC_HOST" in
		\*.*) ask PUBLIC_ORIGIN "Concrete origin for Collabora (wildcard host needs one, e.g. app.${PUBLIC_HOST#\*.})" ;;
	esac
	ask DNS_PROVIDER "DNS provider (hetzner|ionos)" "hetzner"
	ask ACME_EMAIL "ACME / Let's Encrypt email"
	ask S3_ENDPOINT_URL "S3 endpoint URL"
	ask S3_REGION "S3 region code" "fsn1"
	ask S3_BUCKET "S3 bucket" "lq-ai-${TENANT_SLUG}"
	ask ADMIN_EMAIL "Customer admin email (FIRST_RUN_ADMIN_EMAIL)"
	ask OPERATOR_EMAIL "Platform operator email (FIRST_RUN_OPERATOR_EMAIL; blank = no operator account)" ""
	ask SMTP_HOST "SMTP host (blank = no auth mail)" ""
	if [ -n "$SMTP_HOST" ]; then
		ask SMTP_PORT "SMTP port" "$DEFAULT_SMTP_PORT"
		ask SMTP_FROM "SMTP From address" "$ADMIN_EMAIL"
		ask SMTP_USERNAME "SMTP username" ""
	fi
	ask IMAGE_TAG "Image tag (^sha-[0-9a-f]{7,}$)"
	ask NODE_PROFILE "Node profile (full|reduced)" "full"
	ask MODEL_PROVIDER "Model provider (anthropic)" "anthropic"
	ask AGE_RECIPIENT "Backup age recipient (age1…)"
	ask BACKUP_DEADMAN_URL "Backup dead-man URL (optional)" ""
	ask RESTORE_DEADMAN_URL "Restore dead-man URL (optional)" ""
}

# Write the collected NON-SECRET inputs back as a manifest so an interactive run
# is repeatable. Secrets are collected separately and never appear here.
write_manifest() {
	local f="$1"
	# Recreate rather than truncate-in-place so a pre-existing file's looser mode
	# never applies during the write window (SETUP-2 review; umask 077 below).
	rm -f "$f"
	{
		cat <<EOF
# Tenant manifest for "$TENANT_SLUG" — written by setup-tenant.sh (SETUP-2).
# env-format (flat KEY=VALUE), operator-PRIVATE, NEVER committed. Contains NO
# secrets: LQ_AI_DNS_API_TOKEN / S3_ACCESS_KEY / S3_SECRET_KEY / ANTHROPIC_API_KEY
# / SMTP_PASSWORD come from the environment or a prompt. Re-run:
#   setup-tenant.sh --manifest $f
TENANT_SLUG=$TENANT_SLUG
PUBLIC_HOST=$PUBLIC_HOST
PUBLIC_ORIGIN=$PUBLIC_ORIGIN
DNS_PROVIDER=$DNS_PROVIDER
ACME_EMAIL=$ACME_EMAIL
S3_ENDPOINT_URL=$S3_ENDPOINT_URL
S3_REGION=$S3_REGION
S3_BUCKET=$S3_BUCKET
ADMIN_EMAIL=$ADMIN_EMAIL
OPERATOR_EMAIL=$OPERATOR_EMAIL
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_FROM=$SMTP_FROM
SMTP_USERNAME=$SMTP_USERNAME
IMAGE_TAG=$IMAGE_TAG
NODE_PROFILE=$NODE_PROFILE
MODEL_PROVIDER=$MODEL_PROVIDER
AGE_RECIPIENT=$AGE_RECIPIENT
BACKUP_DEADMAN_URL=$BACKUP_DEADMAN_URL
RESTORE_DEADMAN_URL=$RESTORE_DEADMAN_URL
EOF
	} > "$f"
	chmod 600 "$f"
	info "wrote repeatable manifest $f (non-secret; do NOT commit)"
}

# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------
if [ -n "$MANIFEST" ]; then
	load_manifest "$MANIFEST"
else
	interactive_collect
fi

# ---------------------------------------------------------------------------
# Validate + derive
# ---------------------------------------------------------------------------
# GENERIC VALUE FENCE (SETUP-2 review, SHOULD_FIX 2): every one of these values
# lands unquoted in .env.prod, which the backup cron SOURCES AS ROOT
# (`set -a; . .env.prod`) — a value carrying $(…), backticks, `;` or a bare
# space would be latent root code execution at 03:17. ADMIN_EMAIL is customer-
# originated, so this is a real injection surface. Reject loudly; never escape.
check_value() {  # check_value VARNAME  (empty = optional key, allowed)
	local key="$1" val="${!1:-}"
	[ -z "$val" ] && return 0
	printf '%s' "$val" | grep -Eq '^[A-Za-z0-9@:/._%+*?=-]+$' \
		|| die "$key value contains characters outside the safe set [A-Za-z0-9@:/._%+*?=-] — refusing (values land in a root-sourced env file)"
}
for k in TENANT_SLUG PUBLIC_HOST PUBLIC_ORIGIN DNS_PROVIDER ACME_EMAIL \
	S3_ENDPOINT_URL S3_REGION S3_BUCKET ADMIN_EMAIL OPERATOR_EMAIL SMTP_HOST \
	SMTP_PORT SMTP_FROM SMTP_USERNAME IMAGE_TAG NODE_PROFILE MODEL_PROVIDER \
	RUN_DEFAULT_BUDGET_PROFILE AGE_RECIPIENT BACKUP_DEADMAN_URL RESTORE_DEADMAN_URL; do
	check_value "$k"
done

# Anchored per-field formats on top of the generic fence.
readonly EMAIL_RE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$'
readonly URL_RE='^https?://[A-Za-z0-9./_%?=&-]+$'

# Slug: starts/ends alphanumeric (a leading '-' would parse as a docker flag; a
# trailing '-' is an invalid bucket name), 32 chars max.
[ -n "$TENANT_SLUG" ] || die "TENANT_SLUG is required"
printf '%s' "$TENANT_SLUG" | grep -Eq '^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$' \
	|| die "TENANT_SLUG '$TENANT_SLUG' must be [a-z0-9-], max 32 chars, starting and ending alphanumeric"

[ -n "$PUBLIC_HOST" ] || die "PUBLIC_HOST is required"
printf '%s' "$PUBLIC_HOST" | grep -Eq '^(\*\.)?[A-Za-z0-9.-]+$' \
	|| die "PUBLIC_HOST '$PUBLIC_HOST' must be a hostname, optionally with a leading '*.' label"
# A literal '*' must never reach LQ_AI_PUBLIC_ORIGIN (Collabora's server_name /
# frame-ancestors derive from it) — a wildcard host REQUIRES a concrete origin.
case "$PUBLIC_HOST" in
	\*.*)
		[ -n "$PUBLIC_ORIGIN" ] \
			|| die "PUBLIC_HOST is a wildcard — set PUBLIC_ORIGIN to the concrete host Collabora serves (server_name cannot be '*.…'); see --help" ;;
	*)
		[ -n "$PUBLIC_ORIGIN" ] || PUBLIC_ORIGIN="$PUBLIC_HOST" ;;
esac
printf '%s' "$PUBLIC_ORIGIN" | grep -Eq '^[A-Za-z0-9.-]+(:[0-9]+)?$' \
	|| die "PUBLIC_ORIGIN '$PUBLIC_ORIGIN' must be a concrete host[:port] — no wildcard, no scheme"

# DNS_PROVIDER must be in the compiled-in set or the edge bricks at startup.
case " $SUPPORTED_DNS_PROVIDERS " in
	*" $DNS_PROVIDER "*) : ;;
	*) die "DNS_PROVIDER '$DNS_PROVIDER' is not compiled into lq-ai-caddy — must be one of: $SUPPORTED_DNS_PROVIDERS (SETUP-1)" ;;
esac

[ -n "$ACME_EMAIL" ] || die "ACME_EMAIL is required"
printf '%s' "$ACME_EMAIL" | grep -Eq "$EMAIL_RE" \
	|| die "ACME_EMAIL '$ACME_EMAIL' is not a plausible email address"
[ -n "$ADMIN_EMAIL" ] || die "ADMIN_EMAIL is required (the customer admin)"
printf '%s' "$ADMIN_EMAIL" | grep -Eq "$EMAIL_RE" \
	|| die "ADMIN_EMAIL '$ADMIN_EMAIL' is not a plausible email address"
# OPERATOR_EMAIL is optional (SETUP-3b, ADR-F061): empty ⇒ no operator account
# is minted (self-host semantics); when set it must be a plausible email.
[ -z "$OPERATOR_EMAIL" ] || printf '%s' "$OPERATOR_EMAIL" | grep -Eq "$EMAIL_RE" \
	|| die "OPERATOR_EMAIL '$OPERATOR_EMAIL' is not a plausible email address"

[ -n "$S3_ENDPOINT_URL" ] || die "S3_ENDPOINT_URL is required"
printf '%s' "$S3_ENDPOINT_URL" | grep -Eq "$URL_RE" \
	|| die "S3_ENDPOINT_URL '$S3_ENDPOINT_URL' must be an http(s) URL"
[ -n "$S3_REGION" ] || die "S3_REGION is required"
[ -n "$S3_BUCKET" ] || S3_BUCKET="lq-ai-${TENANT_SLUG}"
[ -z "$BACKUP_DEADMAN_URL" ] || printf '%s' "$BACKUP_DEADMAN_URL" | grep -Eq "$URL_RE" \
	|| die "BACKUP_DEADMAN_URL '$BACKUP_DEADMAN_URL' must be an http(s) URL"
[ -z "$RESTORE_DEADMAN_URL" ] || printf '%s' "$RESTORE_DEADMAN_URL" | grep -Eq "$URL_RE" \
	|| die "RESTORE_DEADMAN_URL '$RESTORE_DEADMAN_URL' must be an http(s) URL"

# SMTP_PORT: numeric only — config.py's smtp_port is an int, so a non-numeric
# value here crash-loops the api at boot. Defaulted BEFORE the check so the
# manifest may simply omit it.
SMTP_PORT="${SMTP_PORT:-$DEFAULT_SMTP_PORT}"
printf '%s' "$SMTP_PORT" | grep -Eq '^[0-9]+$' \
	|| die "SMTP_PORT '$SMTP_PORT' must be numeric (api's smtp_port is an int)"

# IMAGE_TAG: same immutable-SHA contract as deploy.sh (never :main).
[ -n "$IMAGE_TAG" ] || die "IMAGE_TAG is required"
printf '%s' "$IMAGE_TAG" | grep -Eq '^sha-[0-9a-f]{7,}$' \
	|| die "IMAGE_TAG '$IMAGE_TAG' must match ^sha-[0-9a-f]{7,}$ (a published sha-<hex> tag, never :main)"

case "$NODE_PROFILE" in
	full|reduced) : ;;
	*) die "NODE_PROFILE '$NODE_PROFILE' must be 'full' or 'reduced'" ;;
esac

case " $SUPPORTED_MODEL_PROVIDERS " in
	*" $MODEL_PROVIDER "*) : ;;
	*) die "MODEL_PROVIDER '$MODEL_PROVIDER' unsupported in v1 — only: $SUPPORTED_MODEL_PROVIDERS (non-PRC default; more providers land later)" ;;
esac

# RUN_DEFAULT_BUDGET_PROFILE is optional (SETUP-5a, ADR-F063): empty ⇒ the line
# is omitted from .env.prod (api falls back to balanced); when set it must be
# EXACTLY one of the three profiles — the api refuses to boot on anything else.
[ -z "$RUN_DEFAULT_BUDGET_PROFILE" ] \
	|| printf '%s' "$RUN_DEFAULT_BUDGET_PROFILE" | grep -Eq '^(economy|balanced|generous)$' \
	|| die "RUN_DEFAULT_BUDGET_PROFILE '$RUN_DEFAULT_BUDGET_PROFILE' must be one of: economy, balanced, generous (or omitted for balanced)"

# Full-shape check (not prefix-only): age1 + lowercase bech32 payload.
[ -n "$AGE_RECIPIENT" ] || die "AGE_RECIPIENT is required"
printf '%s' "$AGE_RECIPIENT" | grep -Eq '^age1[0-9a-z]{20,}$' \
	|| die "AGE_RECIPIENT '$AGE_RECIPIENT' is not an age public recipient (age1 + bech32 payload)"

[ -f "$TENANT_GATEWAY_SEED" ] || die "missing gateway seed template: $TENANT_GATEWAY_SEED"

# Interactive runs persist their non-secret answers as a repeatable manifest.
if [ -z "$MANIFEST" ]; then
	[ -n "$SAVE_MANIFEST" ] || SAVE_MANIFEST="./tenant-${TENANT_SLUG}.conf"
fi

# ---------------------------------------------------------------------------
# Collect secrets — environment first, then an interactive prompt if a TTY is
# attached. Values are held in shell vars only (in-memory) and written ONLY to
# the chmod-600 .env.prod; they are NEVER echoed or written to the manifest.
# ---------------------------------------------------------------------------
prompt_secret() {  # prompt_secret VARNAME "label"
	local __var="$1" __label="$2" __reply=""
	if [ -t 0 ]; then
		read -rs -p "  $__label: " __reply || true
		echo
		printf -v "$__var" '%s' "$__reply"
	fi
}

require_secret() {  # require_secret VARNAME "label"
	local __var="$1" __label="$2"
	if [ -z "${!__var:-}" ]; then
		prompt_secret "$__var" "$__label"
	fi
	[ -n "${!__var:-}" ] || die "$__var is required — set it in the environment or answer the prompt (secrets never live in the manifest)"
}

require_secret LQ_AI_DNS_API_TOKEN "DNS API token (LQ_AI_DNS_API_TOKEN)"
require_secret S3_ACCESS_KEY       "S3 access key (S3_ACCESS_KEY)"
require_secret S3_SECRET_KEY       "S3 secret key (S3_SECRET_KEY)"
require_secret ANTHROPIC_API_KEY   "Anthropic API key (ANTHROPIC_API_KEY)"
if [ -n "$SMTP_HOST" ]; then
	require_secret SMTP_PASSWORD "SMTP password (SMTP_PASSWORD)"
fi
SMTP_PASSWORD="${SMTP_PASSWORD:-}"

ENV_FILE="$OUT_DIR/.env.prod"
GATEWAY_FILE="$OUT_DIR/gateway.yaml"
DNS_FILE="$OUT_DIR/dns-records.txt"
CRON_FILE="$OUT_DIR/cron.d-lq-ai-backup"

info "tenant=$TENANT_SLUG host=$PUBLIC_HOST dns=$DNS_PROVIDER profile=$NODE_PROFILE out=$OUT_DIR tag=$IMAGE_TAG"

if [ "$DRY_RUN" = "1" ]; then
	[ -n "$MANIFEST" ] || info "[dry-run] would write repeatable manifest to $SAVE_MANIFEST"
	info "[dry-run] would write: $ENV_FILE (chmod 600), $GATEWAY_FILE (chmod 600), $DNS_FILE, $CRON_FILE"
	info "[dry-run] would sync stack files (docker-compose.prod.yml, deploy.sh, backup.sh, restore-drill.sh) into $OUT_DIR"
	if [ -f "$ENV_FILE" ] && [ "$FORCE" != "1" ]; then
		info "[dry-run] WARNING: $ENV_FILE exists — a real run would REFUSE without --force (secret-rotation blast radius, see gen-secrets.sh)"
	fi
	[ "$CREATE_BUCKET" = "1" ] && info "[dry-run] would create bucket s3://$S3_BUCKET + versioning + backup lifecycle"
	if [ "$DO_DEPLOY" = "1" ]; then
		info "[dry-run] would run deploy.sh $IMAGE_TAG and print the admin handover"
	else
		info "[dry-run] --no-deploy: would stop after rendering artifacts"
	fi
	info "[dry-run] no files written, nothing deployed."
	exit 0
fi

# ---------------------------------------------------------------------------
# Write artifacts
# ---------------------------------------------------------------------------
# Every file from here on is born 600/700 (umask), so no content ever exists on
# disk under a looser mode — the explicit chmods below are belt-and-braces.
umask 077

# Persist the interactive answers first, so the run is repeatable even if a
# later step fails.
[ -n "$MANIFEST" ] || write_manifest "$SAVE_MANIFEST"

mkdir -p "$OUT_DIR"

# .env.prod — refuse to clobber an existing one (rotating POSTGRES_PASSWORD /
# JWT_SECRET / LQ_AI_GATEWAY_MASTER_KEY has real blast radii — see gen-secrets.sh).
if [ -f "$ENV_FILE" ] && [ "$FORCE" != "1" ]; then
	die "$ENV_FILE already exists — refusing to overwrite (would rotate the generated secrets). Re-run with --force ONLY if you intend to rotate."
fi

# Generated secrets: invoke gen-secrets.sh (do NOT duplicate its logic). It
# prints a comment header + KEY=value lines (POSTGRES_PASSWORD, JWT_SECRET,
# LQ_AI_GATEWAY_KEY, LQ_AI_GATEWAY_MASTER_KEY, COLLABORA_ADMIN_USER/PASSWORD)
# to STDOUT only; we capture and embed them, never echoing to the terminal.
[ -f "$SCRIPT_DIR/gen-secrets.sh" ] || die "missing $SCRIPT_DIR/gen-secrets.sh"
GEN_SECRETS="$(bash "$SCRIPT_DIR/gen-secrets.sh")" || die "gen-secrets.sh failed"

# Node-profile knob: an 8 GB (reduced) node OOMs the full ingest concurrency
# (ADR-F056); pin it to 1 there. 'full' leaves the compose default (2).
INGEST_CONCURRENCY_LINE=""
if [ "$NODE_PROFILE" = "reduced" ]; then
	INGEST_CONCURRENCY_LINE="LQ_AI_INGEST_WORKER_CONCURRENCY=1"
fi

# FIRST_RUN_OPERATOR_EMAIL mints the PLATFORM operator account at first boot
# (SETUP-3a/3b, ADR-F061 D3). Written ONLY when provided; omitted entirely
# otherwise so a stack without an operator keeps self-host semantics.
OPERATOR_EMAIL_LINE=""
if [ -n "$OPERATOR_EMAIL" ]; then
	OPERATOR_EMAIL_LINE="FIRST_RUN_OPERATOR_EMAIL=$OPERATOR_EMAIL"
fi

# RUN_DEFAULT_BUDGET_PROFILE (SETUP-5a, ADR-F063): deployment default budget
# profile. Written ONLY when provided; omitted ⇒ the api defaults to balanced.
BUDGET_PROFILE_LINE=""
if [ -n "$RUN_DEFAULT_BUDGET_PROFILE" ]; then
	BUDGET_PROFILE_LINE="RUN_DEFAULT_BUDGET_PROFILE=$RUN_DEFAULT_BUDGET_PROFILE"
fi

# --force overwrite: recreate rather than truncate-in-place, so an existing
# file's OLD (possibly looser) mode never applies while the new secrets are
# being written — the file is born 0600 under umask 077 (SETUP-2 review).
rm -f "$ENV_FILE"
{
	cat <<EOF
# =============================================================================
# .env.prod — hosted tenant stack "$TENANT_SLUG" (SETUP-2, ADR-F060 D6).
# Rendered by scripts/setup-tenant.sh — root-owned, chmod 600, DO NOT COMMIT.
# One set per tenant stack (ADR-F058 isolation). Secrets live only on this node.
# =============================================================================

# --- Deploy pin --------------------------------------------------------------
LQ_AI_IMAGE_TAG=$IMAGE_TAG

# --- Generated secrets (scripts/gen-secrets.sh) ------------------------------
$GEN_SECRETS

# --- Public identity + TLS (caddy edge) --------------------------------------
LQ_AI_PUBLIC_HOST=$PUBLIC_HOST
LQ_AI_PUBLIC_ORIGIN=$PUBLIC_ORIGIN
LQ_AI_ACME_EMAIL=$ACME_EMAIL
LQ_AI_DNS_PROVIDER=$DNS_PROVIDER
LQ_AI_DNS_API_TOKEN=$LQ_AI_DNS_API_TOKEN

# --- Object storage (S3-compatible) ------------------------------------------
S3_ENDPOINT_URL=$S3_ENDPOINT_URL
S3_ACCESS_KEY=$S3_ACCESS_KEY
S3_SECRET_KEY=$S3_SECRET_KEY
S3_BUCKET=$S3_BUCKET
S3_REGION=$S3_REGION

# --- Gateway config + provider keys ------------------------------------------
# Node path to this tenant's gateway.yaml seed; the named volume holds the live
# writable copy across restarts (gateway/entrypoint.sh seeds it only-if-absent).
GATEWAY_CONFIG_FILE=$GATEWAY_FILE
# Provider key — compose forwards it to the gateway; gateway.yaml references it
# by name (api_key_env: ANTHROPIC_API_KEY), never inlines the value.
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

# --- Retrieval (local ONNX = \$0, no extra egress) ---------------------------
EMBEDDING_PROVIDER=local
RERANK_ENABLED=true

# --- Agent-run budget default (SETUP-5a, ADR-F063; line omitted = balanced) ---
$BUDGET_PROFILE_LINE

# --- Auth + notification email (FIRST_RUN_ADMIN_EMAIL + SMTP; SETUP-2 gap fix)-
# FIRST_RUN_ADMIN_EMAIL seeds the customer admin at first boot (config.py has no
# env_prefix — the var is the bare field name). SMTP is optional (smtp_host-gated).
# FIRST_RUN_OPERATOR_EMAIL (optional, SETUP-3b/ADR-F061) mints the platform
# operator; the line is omitted when no operator email was provided.
FIRST_RUN_ADMIN_EMAIL=$ADMIN_EMAIL
$OPERATOR_EMAIL_LINE
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USERNAME=$SMTP_USERNAME
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
SMTP_USE_TLS=true

# --- Trusted proxy + CORS ----------------------------------------------------
# HARDEN before announcing the URL: pin FORWARDED_ALLOW_IPS to Caddy's fixed
# container IP (drop the *) — ADR-F059 D4, runbook checklist. Same-origin ⇒ no CORS.
FORWARDED_ALLOW_IPS=*
LQ_AI_CORS_ORIGINS=

# --- Collabora extras (prod defaults) ----------------------------------------
COLLABORA_SSL_TERMINATION=true
COLLABORA_HOME_MODE=true

# --- Node profile ($NODE_PROFILE) --------------------------------------------
$INGEST_CONCURRENCY_LINE

# --- Backups + ops (read by scripts/backup.sh, NOT compose) ------------------
LQ_AI_TENANT_ID=$TENANT_SLUG
LQ_AI_BACKUP_AGE_RECIPIENT=$AGE_RECIPIENT
LQ_AI_BACKUP_DEADMAN_URL=$BACKUP_DEADMAN_URL
LQ_AI_RESTORE_DEADMAN_URL=$RESTORE_DEADMAN_URL
LQ_AI_STACK_DIR=$OUT_DIR
COMPOSE_PROJECT_NAME=$TENANT_SLUG

# --- Postgres/Redis identity (defaults) --------------------------------------
POSTGRES_DB=lq_ai
POSTGRES_USER=lq_ai
EOF
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"
info "wrote $ENV_FILE (chmod 600)"

# gateway.yaml — copy the seed VERBATIM (api_key_env indirection means there is
# no secret to render; this guarantees no key material lands in the file).
# rm first: cp onto an existing file keeps the DESTINATION's mode (same
# mode-window rationale as .env.prod above).
rm -f "$GATEWAY_FILE"
cp "$TENANT_GATEWAY_SEED" "$GATEWAY_FILE"
chmod 600 "$GATEWAY_FILE"
info "wrote $GATEWAY_FILE (chmod 600) from tenant-gateway.yaml.example"

# dns-records.txt — the records to create (deploy/dns/README.md, filled with the
# host). Node IPs are placeholders (filled from the VPS console).
# For a wildcard host the app is only reachable at names that resolve, but the
# DNS-01 wildcard cert issues regardless.
case "$PUBLIC_HOST" in
	\*.*) DNS_A_NAME="*.${PUBLIC_HOST#\*.}" ;;
	*) DNS_A_NAME="$PUBLIC_HOST" ;;
esac
{
	cat <<EOF
# DNS records for tenant "$TENANT_SLUG" — create these at your DNS provider.
# Zone host: $DNS_PROVIDER   (ACME DNS-01 uses LQ_AI_DNS_API_TOKEN, already in .env.prod)
# Source: deploy/dns/README.md (SAAS-3, ADR-F060; multi-provider SETUP-1).
# Replace <node-ipv4>/<node-ipv6> with this stack's VPS IPs. Keep TTL 300 during bring-up.

# A/AAAA — the app (Caddy edge)
A     $DNS_A_NAME     <node-ipv4>    300
AAAA  $DNS_A_NAME     <node-ipv6>    300

# CAA — constrain issuance to Let's Encrypt (recommended)
CAA   @   0 issue "letsencrypt.org"
CAA   @   0 issuewild "letsencrypt.org"

# Reminder: DNS provider = $DNS_PROVIDER; the zone-scoped API token is
# LQ_AI_DNS_API_TOKEN in .env.prod (never committed). No Cloudflare proxy in
# front (its proxy-read-timeout kills SSE agent streams) — Caddy is the only proxy.
EOF
} > "$DNS_FILE"
info "wrote $DNS_FILE"

# cron.d-lq-ai-backup — nightly encrypted backup at 03:17 UTC (runbook §7).
{
	cat <<EOF
# /etc/cron.d/lq-ai-backup — nightly encrypted Postgres backup for "$TENANT_SLUG"
# (SAAS-3, ADR-F060 D4). Sources the stack .env.prod, then runs backup.sh.
17 3 * * *  root  set -a; . $ENV_FILE; set +a; $OUT_DIR/backup.sh >> /var/log/lq-ai-backup.log 2>&1
EOF
} > "$CRON_FILE"
info "wrote $CRON_FILE — install it with:"
info "    install -m 644 $CRON_FILE /etc/cron.d/lq-ai-backup"

# Stack files sync — the node holds no repo checkout; seed the compose + ops
# scripts so deploy.sh/backup.sh can run from $OUT_DIR (the deploy workflow
# re-syncs the compose on every deploy, but the first run needs it present).
for f in docker-compose.prod.yml scripts/deploy.sh scripts/backup.sh scripts/restore-drill.sh; do
	src="$REPO_ROOT/$f"
	dst="$OUT_DIR/$(basename "$f")"
	if [ -f "$src" ]; then
		cp "$src" "$dst"
		# The backup cron + deploy path invoke these scripts directly, so the
		# copies need the execute bit (umask 077 above dropped it).
		case "$f" in *.sh) chmod 700 "$dst" ;; esac
	else
		warn "stack file $src not found — skipped; sync it into $OUT_DIR manually before deploying"
	fi
done
info "synced stack files into $OUT_DIR"

# ---------------------------------------------------------------------------
# Optional: create the S3 bucket + versioning + backup lifecycle, via the SAME
# dockerized aws-cli pattern backup.sh uses (no aws-cli install on the node).
# ---------------------------------------------------------------------------
if [ "$CREATE_BUCKET" = "1" ]; then
	command -v docker >/dev/null 2>&1 || die "docker not found (needed for --create-bucket)"
	AWSCLI_IMAGE="${LQ_AI_AWSCLI_IMAGE:-amazon/aws-cli:2.17.0}"
	# Secret VALUES must never ride in docker's argv — argv is world-readable via
	# /proc/*/cmdline (SETUP-2 review). Env-prefix the credentials and pass `-e
	# NAME` with no value: docker then reads them from its own environment.
	awscli() {
		AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
		AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
		AWS_DEFAULT_REGION="$S3_REGION" \
		docker run --rm -i \
			-e AWS_ACCESS_KEY_ID \
			-e AWS_SECRET_ACCESS_KEY \
			-e AWS_DEFAULT_REGION \
			"$AWSCLI_IMAGE" "$@" --endpoint-url "$S3_ENDPOINT_URL"
	}
	info "creating bucket s3://$S3_BUCKET (idempotent)…"
	awscli s3api create-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1 || true
	awscli s3api put-bucket-versioning --bucket "$S3_BUCKET" \
		--versioning-configuration Status=Enabled >/dev/null
	# Retention approximates the runbook's 7-daily/4-weekly window: expire the
	# backups prefix (and its noncurrent versions) after 35 days. Customer files
	# elsewhere in the bucket are protected by versioning, not this rule (D4).
	awscli s3api put-bucket-lifecycle-configuration --bucket "$S3_BUCKET" \
		--lifecycle-configuration "{\"Rules\":[{\"ID\":\"lq-ai-backups-retention\",\"Filter\":{\"Prefix\":\"tenants/$TENANT_SLUG/backups/\"},\"Status\":\"Enabled\",\"Expiration\":{\"Days\":35},\"NoncurrentVersionExpiration\":{\"NoncurrentDays\":35}}]}" >/dev/null
	info "bucket ready: versioning=Enabled, backup lifecycle=35d on tenants/$TENANT_SLUG/backups/"
fi

# ---------------------------------------------------------------------------
# Deploy + admin handover (SETUP-3b, ADR-F061 addendum D7).
#   SMTP configured → fire POST /auth/password-reset-request for ADMIN_EMAIL:
#     the customer admin sets their own password via the emailed link; the
#     bootstrap password is NEVER scraped or printed on this branch.
#   SMTP unset → fallback: surface the one-time bootstrap password from the
#     api log (the only handover channel without a mail transport).
# ---------------------------------------------------------------------------
if [ "$DO_DEPLOY" = "0" ]; then
	info "--no-deploy: artifacts rendered in $OUT_DIR. Run deploy.sh when ready."
	exit 0
fi

command -v docker >/dev/null 2>&1 || die "docker not found on the node (needed to deploy)"
info "deploying $IMAGE_TAG via deploy.sh…"
LQ_AI_IMAGE_TAG="$IMAGE_TAG" LQ_AI_STACK_DIR="$OUT_DIR" COMPOSE_PROJECT_NAME="$TENANT_SLUG" \
	bash "$SCRIPT_DIR/deploy.sh" "$IMAGE_TAG"

dc() { docker compose -p "$TENANT_SLUG" -f "$OUT_DIR/docker-compose.prod.yml" --env-file "$ENV_FILE" "$@"; }

echo
echo "============================================================"
echo "  TENANT HANDOVER — $TENANT_SLUG"
echo "============================================================"
echo "  URL:          https://$PUBLIC_HOST"
echo "  Admin email:  $ADMIN_EMAIL"
if [ -n "$SMTP_HOST" ]; then
	# Email-first handover (D7): retry against the public origin like
	# deploy.sh's smoke — the first-ever deploy can lag cert issuance/DNS.
	# PUBLIC_ORIGIN is validated concrete (never a wildcard). The endpoint
	# returns a uniform 202 and emails a single-use reset link (1 h TTL).
	RESET_REQUEST_URL="https://$PUBLIC_ORIGIN/api/v1/auth/password-reset-request"
	handover_sent=0
	for attempt in $(seq 1 12); do
		if curl -fsS --max-time 10 -o /dev/null -X POST \
			-H 'Content-Type: application/json' \
			--data "{\"email\":\"$ADMIN_EMAIL\"}" "$RESET_REQUEST_URL"; then
			handover_sent=1
			break
		fi
		echo "setup-tenant: handover request attempt $attempt failed; retrying in 5s…" >&2
		sleep 5
	done
	if [ "$handover_sent" = "1" ]; then
		echo "  Handover email sent to $ADMIN_EMAIL — they set their own password"
		echo "  via the emailed link (single-use, expires in 1 hour). Recovery is"
		echo "  self-serve ('Forgot your password?' on the sign-in page). No"
		echo "  credential was printed or stored during this handover."
		# The 202 is uniform and the mail send is best-effort (never-raise), so a
		# bad SMTP credential fails silently — give the operator a recovery pointer.
		echo "  If no email arrives within a few minutes, check the SMTP settings"
		echo "  in $ENV_FILE or use the reset-admin-password CLI on this node."
	else
		warn "could not reach $RESET_REQUEST_URL after retries — no handover email sent"
		echo "  Ask the admin to use 'Forgot your password?' at"
		echo "      https://$PUBLIC_HOST/lq-ai/reset-password"
		echo "  once the stack is reachable (same effect, self-serve)."
	fi
else
	# SMTP-OFF FALLBACK: no mail transport, so the only handover channel is the
	# one-time bootstrap password from the api log (api/app/main.py logs
	# "First-run admin password …: <pw>" exactly once on the creation event).
	# If the admin already existed, there is no new password to print.
	ADMIN_PW_LINE="$(dc logs api 2>&1 | grep -F 'First-run admin password' | tail -1 || true)"
	ADMIN_PW="${ADMIN_PW_LINE##*: }"
	echo "  (SMTP is not configured — falling back to the log-scraped bootstrap"
	echo "   password. Record it now; do not store.)"
	if [ -n "$ADMIN_PW_LINE" ] && [ -n "$ADMIN_PW" ]; then
		echo "  Admin password (first login only, MUST be changed at first login):"
		echo "      $ADMIN_PW"
	else
		echo "  Admin password: not found in the api log — an admin already existed"
		echo "      (idempotent boot). Reset via the reset-admin-password CLI if needed."
	fi
fi
echo "------------------------------------------------------------"
echo "  NEXT STEPS (pre-exposure hardening checklist — runbook §Pre-exposure):"
echo "   1. Pin FORWARDED_ALLOW_IPS to Caddy's container IP (drop the *) — ADR-F059 D4."
echo "   2. Promote CSP from report-only to enforced once the report is clean — SAAS-2."
echo "   3. Create the DNS records in $DNS_FILE, install the backup cron ($CRON_FILE),"
echo "      and confirm the gateway defaults to a non-PRC model (it does — Anthropic)."
echo "============================================================"
