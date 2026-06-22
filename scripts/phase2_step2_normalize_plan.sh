#!/usr/bin/env bash
# Phase 2 Step 2: normalize the raw planning response deterministically.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
PROVIDER="${PROVIDER:-gemini}"
RAW_RESPONSE="${RAW_RESPONSE:-}"
PLAN_OUT="${PLAN_OUT:-}"
STRICT=0

usage() {
  cat <<'EOF'
Usage:
  scripts/phase2_step2_normalize_plan.sh --out /path/to/bundle [options]

Runs Phase 2 Step 2 only: normalize a saved Gemini/Kimi planning response into
plans/document-plan.json and plans/section-plans.jsonl. No LLM call.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --raw-response PATH      raw planner response markdown
                           (default: <bundle>/plans/phase2-<provider>-response.md)
  --provider NAME          provider label (default: gemini)
  --plan-out PATH          normalized output directory (default: <bundle>/plans)
  --strict                 fail if any reference is unresolved
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --raw-response)
      RAW_RESPONSE="${2:-}"; shift 2 ;;
    --provider)
      PROVIDER="${2:-}"; shift 2 ;;
    --plan-out)
      PLAN_OUT="${2:-}"; shift 2 ;;
    --strict)
      STRICT=1; shift ;;
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
if [[ -z "$RAW_RESPONSE" ]]; then
  RAW_RESPONSE="$OUT/plans/phase2-${PROVIDER}-response.md"
fi
[[ -f "$RAW_RESPONSE" ]] || fail "raw response does not exist: $RAW_RESPONSE"

install_base

cmd=(python -m wiki_generator normalize-plan
  --bundle "$OUT"
  --raw-response "$RAW_RESPONSE"
  --provider "$PROVIDER")
if [[ -n "$PLAN_OUT" ]]; then
  cmd+=(--out "$PLAN_OUT")
fi
if [[ "$STRICT" == "1" ]]; then
  cmd+=(--strict)
fi

log "Phase 2 Step 2: normalize-plan"
"${cmd[@]}"

# Report the Phase 3 readiness verdict (written by normalize-plan). This is a
# soft notice here; the hard gate lives in phase3_retrieve_evidence.sh.
READINESS="${PLAN_OUT:-$OUT/plans}/phase3-readiness-report.md"
if [[ -f "$READINESS" ]]; then
  if grep -Eiq '^[*[:space:]]*Status:[*[:space:]]*PASS' "$READINESS"; then
    log "Phase 3 readiness: PASS — safe to run Phase 3 ($READINESS)"
  else
    log "Phase 3 readiness: FAIL — fix planner/normalization before Phase 3"
    log "  see $READINESS"
  fi
fi
