#!/usr/bin/env bash
# Phase 1 Step 5: build/verify retrieval substrate with vectors REQUIRED.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
SMOKE_QUERY="${SMOKE_QUERY:-}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-}"
BATCH_SIZE="${BATCH_SIZE:-}"
REBUILD=0
RUN_TESTS_FIRST=0

usage() {
  cat <<'EOF'
Usage:
  scripts/phase1_step5_build_retrieval.sh --out /path/to/bundle [options]

Runs Phase 1 Step 5 only: verifies/rebuilds BM25 and builds vectors.
Vectors are REQUIRED: this script installs `.[embeddings]`, verifies faiss/numpy/
model2vec imports, and runs `build-retrieval --vectors on`. If vectors cannot be
built, the script fails.

Options:
  --out PATH               existing Phase 1 bundle directory (or env OUT)
  --smoke-query TEXT       optional BM25 smoke query
  --embedding-model NAME   local model2vec model override
  --batch-size N           embedding batch size override
  --rebuild                force clean retrieval index rebuild
  --run-tests-first        run unit tests before Step 5
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --smoke-query)
      SMOKE_QUERY="${2:-}"; shift 2 ;;
    --embedding-model)
      EMBEDDING_MODEL="${2:-}"; shift 2 ;;
    --batch-size)
      BATCH_SIZE="${2:-}"; shift 2 ;;
    --rebuild)
      REBUILD=1; shift ;;
    --run-tests-first)
      RUN_TESTS_FIRST=1; shift ;;
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
install_embeddings
verify_vector_deps
if [[ "$RUN_TESTS_FIRST" == "1" ]]; then
  run_tests
fi

cmd=(python -m wiki_generator build-retrieval
  --in "$OUT"
  --vectors on)
if [[ "$REBUILD" == "1" ]]; then
  cmd+=(--rebuild)
fi
if [[ -n "$SMOKE_QUERY" ]]; then
  cmd+=(--smoke-query "$SMOKE_QUERY")
fi
if [[ -n "$EMBEDDING_MODEL" ]]; then
  cmd+=(--embedding-model "$EMBEDDING_MODEL")
fi
if [[ -n "$BATCH_SIZE" ]]; then
  cmd+=(--batch-size "$BATCH_SIZE")
fi

log "Phase 1 Step 5: build-retrieval with vectors REQUIRED"
"${cmd[@]}"
