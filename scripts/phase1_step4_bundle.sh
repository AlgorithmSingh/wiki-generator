#!/usr/bin/env bash
# Phase 1 Step 4: assemble the single-file planner upload bundle.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
BUDGET_TOKENS="${BUDGET_TOKENS:-250000}"
BUNDLE_OUT="${BUNDLE_OUT:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/phase1_step4_bundle.sh --out /path/to/bundle [options]

Runs Phase 1 Step 4 only: writes planner-digest/planner-upload-bundle.md.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --bundle-out PATH        planner-digest output directory
                           (default: <bundle>/planner-digest)
  --budget-tokens N        target planner upload budget (default: 250000)
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --bundle-out)
      BUNDLE_OUT="${2:-}"; shift 2 ;;
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

cmd=(python -m wiki_generator bundle
  --in "$OUT"
  --budget-tokens "$BUDGET_TOKENS")
if [[ -n "$BUNDLE_OUT" ]]; then
  cmd+=(--out "$BUNDLE_OUT")
fi

log "Phase 1 Step 4: bundle"
"${cmd[@]}"
