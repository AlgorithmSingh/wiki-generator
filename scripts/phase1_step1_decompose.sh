#!/usr/bin/env bash
# Phase 1 Step 1: decompose repo into raw deterministic artifacts.
#
# Vectors are intentionally OFF here. Step 5 owns vector building and requires
# FAISS/model2vec with `--vectors on`, so retrieval setup is not buried in Step 1.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

REPO="${REPO:-}"
OUT="${OUT:-}"
RG_CAP="${RG_CAP:-80}"
CONTRACTS_IMPORT=0

usage() {
  cat <<'EOF'
Usage:
  scripts/phase1_step1_decompose.sh --repo /path/to/repo --out /path/to/bundle [options]

Runs Phase 1 Step 1 only: inventory, symbols, chunks/spans, BM25, query packs,
contracts/tests, and derived raw summaries. The script passes `--embeddings off`;
Phase 1 Step 5 builds vectors separately and requires them.

Options:
  --repo PATH              target repository to document (or env REPO)
  --out PATH               output bundle directory (or env OUT)
  --rg-cap N               max digested hits per ripgrep query pack (default: 80)
  --contracts-import       UNSAFE: allow app import for live OpenAPI extraction
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"; shift 2 ;;
    --out)
      OUT="${2:-}"; shift 2 ;;
    --rg-cap)
      RG_CAP="${2:-}"; shift 2 ;;
    --contracts-import)
      CONTRACTS_IMPORT=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      if handle_common_arg "$@"; then
        usage >&2; fail "unknown argument: $1"
      else
        consumed=$?
        shift "$consumed"
      fi ;;
  esac
done

require_dir "--repo" "$REPO"
require_nonempty "--out" "$OUT"

install_base

cmd=(python -m wiki_generator decompose
  --repo "$REPO"
  --out "$OUT"
  --embeddings off
  --rg-cap "$RG_CAP")
if [[ "$CONTRACTS_IMPORT" == "1" ]]; then
  cmd+=(--contracts-import)
fi

log "Phase 1 Step 1: decompose"
"${cmd[@]}"
