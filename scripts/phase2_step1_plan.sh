#!/usr/bin/env bash
# Phase 2 Step 1: run the planning LLM via Vertex AI Gemini.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
PROVIDER="${PROVIDER:-gemini}"
MODEL="${MODEL:-gemini-2.5-pro}"
BUNDLE_FILE="${BUNDLE_FILE:-}"
PLAN_OUT="${PLAN_OUT:-}"
SYSTEM_FILE="${SYSTEM_FILE:-}"
PROMPT_FILE="${PROMPT_FILE:-}"
TEMPERATURE="${TEMPERATURE:-}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/phase2_step1_plan.sh --out /path/to/bundle [options]

Runs Phase 2 Step 1 only: calls the planning LLM through Vertex AI Gemini.
This is the only LLM step. Requires GCP Application Default Credentials.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --project ID             GCP project (or env GOOGLE_CLOUD_PROJECT)
  --location LOC           Vertex location (default env GOOGLE_CLOUD_LOCATION or us-central1)
  --provider NAME          provider label for output filename (default: gemini)
  --model NAME             Vertex model id (default: gemini-2.5-pro)
  --bundle-file PATH       explicit planner-upload-bundle.md path
  --plan-out PATH          raw response output directory (default: <bundle>/plans)
  --system PATH            system instructions file
  --prompt PATH            kickoff prompt file
  --temperature N          sampling temperature
  --max-output-tokens N    max output tokens (default: model/CLI default, 65535).
                           Use a realistic cap for the full JSON/JSONL plan: at
                           least 1024 for smoke tests, 8192+ for full e2e runs.
                           Tiny caps stop the response with MAX_TOKENS and are a
                           test-config failure, not a planner-quality result.
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --project)
      PROJECT="${2:-}"; shift 2 ;;
    --location)
      LOCATION="${2:-}"; shift 2 ;;
    --provider)
      PROVIDER="${2:-}"; shift 2 ;;
    --model)
      MODEL="${2:-}"; shift 2 ;;
    --bundle-file)
      BUNDLE_FILE="${2:-}"; shift 2 ;;
    --plan-out)
      PLAN_OUT="${2:-}"; shift 2 ;;
    --system)
      SYSTEM_FILE="${2:-}"; shift 2 ;;
    --prompt)
      PROMPT_FILE="${2:-}"; shift 2 ;;
    --temperature)
      TEMPERATURE="${2:-}"; shift 2 ;;
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
require_nonempty "--project or GOOGLE_CLOUD_PROJECT" "$PROJECT"

# Guard against tiny output caps: gemini-2.5-pro stops with MAX_TOKENS on a tiny
# cap, which is a test-config failure, not a planner result. Require >= 1024.
if [[ -n "$MAX_OUTPUT_TOKENS" && "$MAX_OUTPUT_TOKENS" =~ ^[0-9]+$ \
      && "$((10#$MAX_OUTPUT_TOKENS))" -lt 1024 ]]; then
  fail "--max-output-tokens $MAX_OUTPUT_TOKENS is too small for a full plan; "\
"use at least 1024 (8192+ recommended for full e2e runs)"
fi

install_vertex

cmd=(python -m wiki_generator plan
  --bundle "$OUT"
  --project "$PROJECT"
  --location "$LOCATION"
  --provider "$PROVIDER"
  --model "$MODEL")
if [[ -n "$BUNDLE_FILE" ]]; then
  cmd+=(--bundle-file "$BUNDLE_FILE")
fi
if [[ -n "$PLAN_OUT" ]]; then
  cmd+=(--out "$PLAN_OUT")
fi
if [[ -n "$SYSTEM_FILE" ]]; then
  cmd+=(--system "$SYSTEM_FILE")
fi
if [[ -n "$PROMPT_FILE" ]]; then
  cmd+=(--prompt "$PROMPT_FILE")
fi
if [[ -n "$TEMPERATURE" ]]; then
  cmd+=(--temperature "$TEMPERATURE")
fi
if [[ -n "$MAX_OUTPUT_TOKENS" ]]; then
  cmd+=(--max-output-tokens "$MAX_OUTPUT_TOKENS")
fi

log "Phase 2 Step 1: plan"
"${cmd[@]}"
