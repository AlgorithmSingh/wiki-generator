#!/usr/bin/env bash
# Phase 2 Step 1b: bounded planner-artifact repair (Patch 2 / Patch 3).
#
# Normalizes the raw planning response; if it is not Phase-3-ready (malformed
# required SectionPlan row, unresolved exact-lane handle, or a diagnostic-only
# user section), re-prompts Vertex/Gemini for corrected planning artifacts only,
# re-validates with the same strict deterministic gate, and writes the canonical
# plan artifacts only when readiness passes. Bounded (<=2 attempts), audited
# under <bundle>/plans/repair/, and fails loudly if Gemini is unavailable or
# repair cannot succeed. Phase 3 never invokes this.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
PROVIDER="${PROVIDER:-gemini}"
RAW_RESPONSE="${RAW_RESPONSE:-}"
PLAN_OUT="${PLAN_OUT:-}"
PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
MODEL="${MODEL:-gemini-2.5-pro}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-2}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/phase2_step1b_repair_plan.sh --out /path/to/bundle [options]

Bounded Vertex/Gemini repair of the Phase 2 planner artifacts when deterministic
normalization is not Phase-3-ready. Needs the [vertex] extra + either GCP ADC
(--project / GOOGLE_CLOUD_PROJECT) or a GEMINI_API_KEY env var.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --raw-response PATH      raw planner response markdown
                           (default: <bundle>/plans/phase2-<provider>-response.md)
  --provider NAME          provider label (default: gemini)
  --plan-out PATH          normalized output directory (default: <bundle>/plans)
  --project ID             GCP project for Vertex (or env GOOGLE_CLOUD_PROJECT)
  --location LOC           Vertex location (default GOOGLE_CLOUD_LOCATION or us-central1)
  --model NAME             Vertex/Gemini model id (default: gemini-2.5-pro)
  --max-attempts N         bounded repair attempts (1 or 2; hard cap 2)
  --max-output-tokens N    max output tokens (default 32768; never use a tiny cap)
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
    --project)
      PROJECT="${2:-}"; shift 2 ;;
    --location)
      LOCATION="${2:-}"; shift 2 ;;
    --model)
      MODEL="${2:-}"; shift 2 ;;
    --max-attempts)
      MAX_ATTEMPTS="${2:-}"; shift 2 ;;
    --max-output-tokens)
      MAX_OUTPUT_TOKENS="${2:-}"; shift 2 ;;
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

# Guard against tiny output caps (a full corrected plan needs room).
if [[ -n "$MAX_OUTPUT_TOKENS" && "$MAX_OUTPUT_TOKENS" =~ ^[0-9]+$ \
      && "$((10#$MAX_OUTPUT_TOKENS))" -lt 1024 ]]; then
  fail "--max-output-tokens $MAX_OUTPUT_TOKENS is too small for a full plan; "\
"use at least 1024 (8192+ recommended)"
fi

install_vertex

cmd=(python -m wiki_generator plan-repair
  --bundle "$OUT"
  --raw-response "$RAW_RESPONSE"
  --provider "$PROVIDER"
  --model "$MODEL"
  --max-attempts "$MAX_ATTEMPTS")
if [[ -n "$PLAN_OUT" ]]; then
  cmd+=(--out "$PLAN_OUT")
fi
if [[ -n "$PROJECT" ]]; then
  cmd+=(--project "$PROJECT")
fi
if [[ -n "$LOCATION" ]]; then
  cmd+=(--location "$LOCATION")
fi
if [[ -n "$MAX_OUTPUT_TOKENS" ]]; then
  cmd+=(--max-output-tokens "$MAX_OUTPUT_TOKENS")
fi

log "Phase 2 Step 1b: plan-repair"
"${cmd[@]}"

# Report the resulting readiness verdict (the hard gate lives in
# phase3_retrieve_evidence.sh).
READINESS="${PLAN_OUT:-$OUT/plans}/phase3-readiness-report.md"
if [[ -f "$READINESS" ]]; then
  if grep -Eiq '^[*[:space:]]*Status:[*[:space:]]*PASS' "$READINESS"; then
    log "Phase 3 readiness: PASS — safe to run Phase 3 ($READINESS)"
  else
    log "Phase 3 readiness: FAIL — see $READINESS and plans/repair/repair-report.md"
  fi
fi
