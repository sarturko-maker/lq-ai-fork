#!/usr/bin/env bash
# fetch_cuad.sh — download the CUAD v1 corpus for the Track-B retrieval eval.
#
# WHY THIS EXISTS: the retrieval-eval baseline (ADR-F049 / slice E0) scores the
# matter FTS retriever against CUAD's human clause-span annotations. CUAD is
# CC-BY-4.0 (see NOTICES.md) and multi-MB — it is NEVER committed. This script
# fetches it on demand into a gitignored fixture dir; the eval skips when absent.
#
# WHAT IT DOES (idempotent):
#   1. downloads the official Atticus data.zip (~18 MB) unless CUADv1.json exists
#   2. extracts CUADv1.json into the fixture dir
#   3. prints size + sha256 so a run can be pinned in the eval manifest
#
# It writes ONLY into the fixture dir (default: api/tests/fixtures/cuad/, which
# .gitignore excludes). No build, no Docker, no DB.
#
# Usage:   scripts/fetch_cuad.sh [target_dir]
#          LQ_AI_CUAD_DIR=/some/dir scripts/fetch_cuad.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-${LQ_AI_CUAD_DIR:-$REPO_ROOT/api/tests/fixtures/cuad}}"
CUAD_JSON="$TARGET_DIR/CUADv1.json"
# Official Atticus Project archive (the same URL the HuggingFace loader pulls).
DATA_ZIP_URL="https://github.com/TheAtticusProject/cuad/raw/main/data.zip"

mkdir -p "$TARGET_DIR"

if [ -f "$CUAD_JSON" ]; then
  echo "CUADv1.json already present at $CUAD_JSON — skipping download."
else
  ZIP_PATH="$TARGET_DIR/data.zip"
  echo "Downloading CUAD data.zip (~18 MB) → $ZIP_PATH"
  curl -fL --retry 3 -o "$ZIP_PATH" "$DATA_ZIP_URL"
  echo "Extracting CUADv1.json …"
  # -j flattens; -o overwrites; the "*CUADv1.json" glob matches the file wherever
  # it sits in the archive (root or a nested dir), extracting just the combined
  # SQuAD file we need.
  unzip -o -j "$ZIP_PATH" "*CUADv1.json" -d "$TARGET_DIR"
  rm -f "$ZIP_PATH"
fi

if [ ! -f "$CUAD_JSON" ]; then
  echo "ERROR: CUADv1.json not found after fetch." >&2
  exit 1
fi

SIZE="$(du -h "$CUAD_JSON" | cut -f1)"
SHA="$(sha256sum "$CUAD_JSON" | cut -d' ' -f1)"
echo
echo "CUAD ready:"
echo "  path:   $CUAD_JSON"
echo "  size:   $SIZE"
echo "  sha256: $SHA"
echo
echo "Attribution (CC-BY-4.0): CUAD © The Atticus Project — https://www.atticusprojectai.org/cuad"
echo "Run the baseline: LQ_AI_CUAD_DIR=$TARGET_DIR pytest tests/agents/scenarios/test_cuad_retrieval_baseline.py -s"
