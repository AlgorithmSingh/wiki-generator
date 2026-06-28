#!/usr/bin/env bash
# Phase 4: write/synthesize the grounded wiki from a clean Phase 1-3 bundle.
#
# Synthesis only. This never runs Phase 3 retrieval, never repairs the plan, and
# never invents fallback evidence. It gates on readiness PASS + retrieval
# validation pass + no forced/stale provenance + source-evidence hygiene + all
# section packets present, then generates and validates DeepWiki-style sections.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
WIKI_OUT="${WIKI_OUT:-}"
PROVIDER="${PROVIDER:-vertex}"
MODEL="${MODEL:-gemini-2.5-pro}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-32768}"
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
LOCATION="${LOCATION:-${GOOGLE_CLOUD_LOCATION:-us-central1}}"
PROMPT_OUT="${PROMPT_OUT:-}"
RESPONSES_IN="${RESPONSES_IN:-}"
MAX_REWRITE_ATTEMPTS="${MAX_REWRITE_ATTEMPTS:-}"
COVERAGE_MODE="${COVERAGE_MODE:-}"
GROUNDED_CLAIM_PLAN="${GROUNDED_CLAIM_PLAN:-0}"
PREPARE_ONLY=0
ACCEPT_NO_FORCE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/phase4_write_wiki.sh --out /path/to/bundle [options]

Phase 4 writing/synthesis. Reads the accepted Phase 1-3 bundle and writes the
wiki into <bundle>/wiki/. Three provider modes:

  vertex      Vertex AI Gemini 2.5 Pro (default). Needs GOOGLE_CLOUD_PROJECT +
              GOOGLE_CLOUD_LOCATION and `gcloud auth application-default login`.
  gemini-api  Direct Gemini API key (GEMINI_API_KEY). NOT Vertex.
  gemini-gem  Manual Gemini Gem handoff: prepare prompts, paste them into the
              Gem, save verbatim responses, then validate + assemble.

Options:
  --out PATH                 accepted Phase 1/2/3 bundle directory (or env OUT)
  --wiki-out PATH            wiki output dir (default <bundle>/wiki)
  --provider MODE            vertex | gemini-api | gemini-gem (default vertex)
  --model ID                 model id for vertex/gemini-api (default gemini-2.5-pro)
  --temperature F            sampling temperature (default 0.1)
  --max-output-tokens N      max output tokens (default 32768; 8192 can truncate
                             gemini-2.5-pro full-section synthesis)
  --max-rewrite-attempts N   bounded format/citation rewrites (0..2; default 1)
  --coverage-mode MODE       baseline (default) | enhancement. enhancement refuses
                             to call any provider unless the Phase 2 planned-coverage
                             gate (plans/coverage-gate.json) and the Phase 3
                             evidenced-coverage gate (evidence/evidenced-coverage.json
                             + the required_topic_evidence_sufficient contract check)
                             are enforced/passing (else exit 3, pre-provider);
                             preserves parent/child hierarchy; and deterministically
                             validates every evidenced sufficient required topic is
                             generated with valid mapped citations (else exit 5).
  --grounded-claim-plan      opt-in grounded generation. Ask the model/imported Gem
                             response for a structured claim/token plan, validate it,
                             and render Markdown by deterministic token substitution.
                             Composes with --coverage-mode; default off.
  --project ID               GCP project for vertex (default $GOOGLE_CLOUD_PROJECT)
  --location REGION          Vertex location (default $GOOGLE_CLOUD_LOCATION)
  --prepare-prompts-only     (gemini-gem) write per-section prompts and stop
  --prompt-out PATH          prompt dir (default <wiki>/audit/prompts)
  --responses-in PATH        (gemini-gem) verbatim raw responses to import
  --accept-no-force          assert no forced Phase 3 when the bundle has no
                             command manifest (fails closed otherwise)

Gemini Gem two-step:
  scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider gemini-gem --prepare-prompts-only
  # paste each wiki/audit/prompts/<section>.md into the Gem, save verbatim
  # responses to wiki/audit/responses/<section>.raw.txt, then:
  scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider gemini-gem \
      --responses-in "$BUNDLE/wiki/audit/responses"

Exit codes: 0 PASS/prepared; 2 bad/missing input; 3 upstream gate failure;
            4 provider failure; 5 writing-validation failure; 1 internal bug.
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="${2:-}"; shift 2 ;;
    --wiki-out) WIKI_OUT="${2:-}"; shift 2 ;;
    --provider) PROVIDER="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --temperature) TEMPERATURE="${2:-}"; shift 2 ;;
    --max-output-tokens) MAX_OUTPUT_TOKENS="${2:-}"; shift 2 ;;
    --max-rewrite-attempts) MAX_REWRITE_ATTEMPTS="${2:-}"; shift 2 ;;
    --coverage-mode) COVERAGE_MODE="${2:-}"; shift 2 ;;
    --grounded-claim-plan) GROUNDED_CLAIM_PLAN=1; shift ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --location) LOCATION="${2:-}"; shift 2 ;;
    --prompt-out) PROMPT_OUT="${2:-}"; shift 2 ;;
    --responses-in) RESPONSES_IN="${2:-}"; shift 2 ;;
    --prepare-prompts-only) PREPARE_ONLY=1; shift ;;
    --accept-no-force) ACCEPT_NO_FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
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

# Readiness gate (cheap, pre-install). Phase 4 also re-checks every gate itself,
# but stop early on an obviously not-ready bundle before installing anything.
READINESS="$OUT/plans/phase3-readiness-report.md"
if [[ -f "$READINESS" ]]; then
  if grep -Eiq '^[*[:space:]]*Status:[*[:space:]]*PASS' "$READINESS"; then
    log "Phase 4 readiness pre-check: PASS"
  else
    log "ERROR: readiness report is not PASS: $READINESS"
    log "Fix the plan upstream (Phase 2 normalize/repair) and rerun Phase 3 cleanly."
    exit 3
  fi
fi

# gemini-gem makes no API call; vertex/gemini-api need the google-genai SDK.
if [[ "$PROVIDER" == "gemini-gem" ]]; then
  install_base
else
  install_vertex
fi

cmd=(python -m wiki_generator write-wiki --bundle "$OUT" --provider "$PROVIDER")
[[ -n "$WIKI_OUT" ]] && cmd+=(--out "$WIKI_OUT")
[[ -n "$PROMPT_OUT" ]] && cmd+=(--prompt-out "$PROMPT_OUT")
[[ "$ACCEPT_NO_FORCE" == "1" ]] && cmd+=(--accept-no-force)
# Omitted when unset so the CLI default (baseline) stays the single source of truth.
[[ -n "$COVERAGE_MODE" ]] && cmd+=(--coverage-mode "$COVERAGE_MODE")
[[ "$GROUNDED_CLAIM_PLAN" == "1" ]] && cmd+=(--grounded-claim-plan)

if [[ "$PREPARE_ONLY" == "1" ]]; then
  cmd+=(--prepare-prompts-only)
elif [[ "$PROVIDER" == "gemini-gem" ]]; then
  [[ -n "$RESPONSES_IN" ]] && cmd+=(--responses-in "$RESPONSES_IN")
  cmd+=(--validate-and-assemble)
else
  cmd+=(--model "$MODEL" --temperature "$TEMPERATURE"
        --max-output-tokens "$MAX_OUTPUT_TOKENS")
  [[ -n "$MAX_REWRITE_ATTEMPTS" ]] && cmd+=(--max-rewrite-attempts "$MAX_REWRITE_ATTEMPTS")
  if [[ "$PROVIDER" == "vertex" ]]; then
    [[ -n "$PROJECT" ]] && cmd+=(--project "$PROJECT")
    [[ -n "$LOCATION" ]] && cmd+=(--location "$LOCATION")
  fi
fi

log "Phase 4: write-wiki (provider=$PROVIDER)"
"${cmd[@]}"
