#!/usr/bin/env bash
# Phase 1 Step 3: build derived/planning-digest.md only.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
BUDGET_TOKENS="${BUDGET_TOKENS:-250000}"

usage() {
  cat <<'EOF'
Usage:
  scripts/phase1_step3_digest.sh --out /path/to/bundle [options]

Runs Phase 1 Step 3 only: writes derived/planning-digest.md.
It passes --no-bundle so Step 4 remains a separate script.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --budget-tokens N        target planner upload budget (default: 250000)
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --budget-tokens)
      BUDGET_TOKENS="${2:-}"; shift 2 ;;
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

require_dir "--out" "$OUT"
install_base

log "Phase 1 Step 3: digest"
python -m wiki_generator digest \
  --in "$OUT" \
  --budget-tokens "$BUDGET_TOKENS" \
  --no-bundle
