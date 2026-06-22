#!/usr/bin/env bash
# Shared helpers for wiki-generator phase scripts.
# shellcheck shell=bash

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
RECREATE_VENV="${RECREATE_VENV:-0}"

log() {
  printf '[wiki-script] %s\n' "$*" >&2
}

fail() {
  printf '[wiki-script] ERROR: %s\n' "$*" >&2
  exit 2
}

_find_python312() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return
  fi
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return
  fi
  if [[ -x /opt/homebrew/bin/python3.12 ]]; then
    printf '%s\n' /opt/homebrew/bin/python3.12
    return
  fi
  fail "Python 3.12 not found. Install it or pass --python /path/to/python3.12"
}

_require_python312_executable() {
  local py="$1"
  [[ -x "$py" ]] || fail "Python executable not found or not executable: $py"
  "$py" - <<'PY' || fail "Expected Python 3.12 exactly"
import sys
print(f"[wiki-script] selected Python: {sys.executable} ({sys.version.split()[0]})")
raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)
PY
}

ensure_python312_venv() {
  local py
  py="$(_find_python312)"
  _require_python312_executable "$py"

  if [[ -x "$VENV_DIR/bin/python" ]]; then
    local venv_version
    venv_version="$($VENV_DIR/bin/python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
    if [[ "$venv_version" != "3.12" ]]; then
      log "existing venv is Python $venv_version; recreating as Python 3.12: $VENV_DIR"
      rm -rf "$VENV_DIR"
    elif [[ "$RECREATE_VENV" == "1" ]]; then
      log "recreating venv: $VENV_DIR"
      rm -rf "$VENV_DIR"
    fi
  elif [[ "$RECREATE_VENV" == "1" ]]; then
    rm -rf "$VENV_DIR"
  fi

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "creating venv with Python 3.12: $VENV_DIR"
    "$py" -m venv "$VENV_DIR"
  fi

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"

  python - <<'PY' || fail "Activated venv is not Python 3.12"
import sys
print(f"[wiki-script] venv Python: {sys.executable} ({sys.version.split()[0]})")
raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)
PY

  if [[ ! -f "$VENV_DIR/.pip-upgraded" ]]; then
    log "upgrading pip"
    python -m pip install -U pip
    touch "$VENV_DIR/.pip-upgraded"
  fi
}

install_base() {
  ensure_python312_venv
  log "installing wiki-generator base package"
  (cd "$ROOT_DIR" && python -m pip install -e .)
}

install_embeddings() {
  ensure_python312_venv
  log "installing wiki-generator with REQUIRED embeddings extra"
  (cd "$ROOT_DIR" && python -m pip install -e '.[embeddings]')
}

install_vertex() {
  ensure_python312_venv
  log "installing wiki-generator with Vertex extra"
  (cd "$ROOT_DIR" && python -m pip install -e '.[vertex]')
}

install_embeddings_and_vertex() {
  ensure_python312_venv
  log "installing wiki-generator with REQUIRED embeddings + Vertex extras"
  (cd "$ROOT_DIR" && python -m pip install -e '.[embeddings,vertex]')
}

verify_vector_deps() {
  log "verifying required vector dependencies"
  python - <<'PY'
import faiss, numpy, model2vec
print('[wiki-script] vector deps ok')
print('[wiki-script] faiss', getattr(faiss, '__version__', 'unknown'))
print('[wiki-script] numpy', numpy.__version__)
print('[wiki-script] model2vec', getattr(model2vec, '__version__', 'unknown'))
PY
}

run_tests() {
  log "running unit tests"
  (cd "$ROOT_DIR" && python -m unittest discover -s tests)
}

require_dir() {
  local label="$1"
  local value="$2"
  [[ -n "$value" ]] || fail "$label is required"
  [[ -d "$value" ]] || fail "$label is not a directory: $value"
}

require_nonempty() {
  local label="$1"
  local value="$2"
  [[ -n "$value" ]] || fail "$label is required"
}

common_options_help() {
  cat <<'EOF'
Common options:
  --python PATH            Python 3.12 executable; default: python3.12 on PATH,
                           then /opt/homebrew/bin/python3.12
  --venv PATH              venv path; default: <wiki-generator>/.venv
  --recreate-venv          delete and recreate the venv before running
EOF
}

handle_common_arg() {
  case "$1" in
    --python)
      PYTHON_BIN="${2:-}"; return 2 ;;
    --venv)
      VENV_DIR="${2:-}"; return 2 ;;
    --recreate-venv)
      RECREATE_VENV=1; return 1 ;;
    *)
      return 0 ;;
  esac
}
