#!/usr/bin/env bash
# Create/use a Python 3.12 venv and install required vector dependencies.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

WITH_VERTEX=0
SKIP_TESTS=0

usage() {
  cat <<'EOF'
Usage:
  scripts/00_setup_python312_vectors.sh [options]

Creates/uses a Python 3.12 venv, installs wiki-generator with REQUIRED vector
extras (`faiss-cpu`, `numpy`, `model2vec`), and verifies those imports.

Options:
  --with-vertex            also install the Vertex AI planning extra
  --skip-tests             do not run the unit test suite after install
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-vertex)
      WITH_VERTEX=1; shift ;;
    --skip-tests)
      SKIP_TESTS=1; shift ;;
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

if [[ "$WITH_VERTEX" == "1" ]]; then
  install_embeddings_and_vertex
else
  install_embeddings
fi
verify_vector_deps
if [[ "$SKIP_TESTS" != "1" ]]; then
  run_tests
fi
log "setup complete"
