#!/usr/bin/env bash
# docker-prune.sh — reclaim dev-stack disk SAFELY (LQ.AI fork).
#
# WHY THIS EXISTS: the dev workflow rebuilds api / arq-worker / ingest-worker / web
# frequently (each is a ~6 GB image). Every rebuild orphans the previous image as a
# dangling <none> layer. On the Crostini/btrfs dev VM these pile up and fill the disk
# (seen 2026-06: a full disk + 65 GB of reclaimable images). The fix is to prune the
# dangling layers — routinely (see CLAUDE.md "Dev-environment hard rules": run
# `docker image prune -f` right after any rebuild) and via this script for a fuller sweep.
#
# WHAT IT REMOVES (all rebuildable / regenerable — never source, volumes, or live data):
#   1. DANGLING images only (untagged <none> layers from past rebuilds)  ← the main win
#   2. stopped/exited containers (one-shot `compose run` + dead test containers)
#   3. leftover throwaway test databases (lq_ai_test_*) from the pytest harness
#
# WHAT IT DELIBERATELY DOES NOT DO (maintainer decision, 2026-06):
#   - NO `docker image prune -a`  → never removes a TAGGED image (your stack images stay
#     even when stopped, so a rebuild stays incremental, not from scratch).
#   - NO `docker builder prune`   → keeps the build cache for fast rebuilds. If the cache
#     itself ever grows large, clear it deliberately: `docker builder prune -f`.
#   - NO `docker volume prune`    → never touches named volumes (postgres/minio data).
#   - NO cron / timer             → run it yourself after a heavy rebuild session.
#
# USAGE:  bash scripts/docker-prune.sh
set -euo pipefail

echo "=== disk before ==="
df -h / | tail -1
before_avail=$(df --output=avail -k / | tail -1)

echo
echo "=== 1/3 dangling images ==="
docker image prune -f

echo
echo "=== 2/3 stopped containers ==="
docker container prune -f

echo
echo "=== 3/3 leftover test databases (lq_ai_test_*) ==="
if docker compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  drops=$(docker compose exec -T postgres psql -U lq_ai -d postgres -tAc \
    "SELECT 'DROP DATABASE IF EXISTS \"'||datname||'\";' FROM pg_database WHERE datname LIKE 'lq_ai_test_%';" 2>/dev/null || true)
  if [ -n "${drops//[[:space:]]/}" ]; then
    n=$(printf '%s\n' "$drops" | grep -c DROP || true)
    printf '%s\n' "$drops" | docker compose exec -T postgres psql -U lq_ai -d postgres >/dev/null 2>&1 || true
    echo "dropped ${n} leftover test database(s)"
  else
    echo "none"
  fi
else
  echo "postgres not running — skipped"
fi

echo
echo "=== disk after ==="
df -h / | tail -1
after_avail=$(df --output=avail -k / | tail -1)
reclaimed_gb=$(awk "BEGIN{printf \"%.1f\", ($after_avail-$before_avail)/1024/1024}")
echo "reclaimed ~${reclaimed_gb} GB"

cat <<'NOTE'

Note (Crostini): freeing space inside the VM does not shrink the ChromeOS-allocated
disk image. After a large reclaim, run `sudo fstrim -v /` to release freed blocks, or
shrink the disk in ChromeOS Settings -> Advanced -> Developers -> Linux -> Disk size.
NOTE
