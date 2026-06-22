#!/usr/bin/env bash
# Phase 3: deterministically retrieve evidence packets for every planned section.

set -Eeuo pipefail
IFS=$'\n\t'

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

OUT="${OUT:-}"
EVIDENCE_OUT="${EVIDENCE_OUT:-}"
MAX_PER_LANE="${MAX_PER_LANE:-}"
MAX_TOTAL_PER_SECTION="${MAX_TOTAL_PER_SECTION:-}"
WITH_VECTORS="${WITH_VECTORS:-0}"

usage() {
  cat <<'EOF'
Usage:
  scripts/phase3_retrieve_evidence.sh --out /path/to/bundle [options]

Runs Phase 3 only: read the normalized Phase 2 plan + Step 5 retrieval substrate
and write one EvidencePacket per section into <bundle>/evidence/. No LLM call.
This is an all-sections producer; there is no per-section mode.

Requires (from earlier phases):
  plans/document-plan.json, plans/section-plans.jsonl,
  rag/retrieval-capabilities.json, rag/bm25.sqlite, rag/chunks.jsonl, rag/spans.jsonl
  (+ rag/vectors.faiss & vector metadata when capabilities report hybrid).

Options:
  --out PATH                    existing Phase 1/2 bundle directory (or env OUT)
  --evidence-out PATH           output directory (default: <bundle>/evidence)
  --max-per-lane N              cap evidence per lane per section
  --max-total-per-section N     cap evidence per section
  --with-vectors                install the [embeddings] extra so the vector lane
                                can run for hybrid bundles (default: base only;
                                the vector lane is skipped if unavailable)

Exit codes: 0 PASS; 2 bad/missing input artifact; 3 bad/underspecified plan;
            1 retriever bug.
EOF
  common_options_help
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:-}"; shift 2 ;;
    --evidence-out)
      EVIDENCE_OUT="${2:-}"; shift 2 ;;
    --max-per-lane)
      MAX_PER_LANE="${2:-}"; shift 2 ;;
    --max-total-per-section)
      MAX_TOTAL_PER_SECTION="${2:-}"; shift 2 ;;
    --with-vectors)
      WITH_VECTORS=1; shift ;;
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

if [[ "$WITH_VECTORS" == "1" ]]; then
  install_embeddings
else
  install_base
fi

cmd=(python -m wiki_generator retrieve-evidence --bundle "$OUT")
if [[ -n "$EVIDENCE_OUT" ]]; then
  cmd+=(--out "$EVIDENCE_OUT")
fi
if [[ -n "$MAX_PER_LANE" ]]; then
  cmd+=(--max-per-lane "$MAX_PER_LANE")
fi
if [[ -n "$MAX_TOTAL_PER_SECTION" ]]; then
  cmd+=(--max-total-per-section "$MAX_TOTAL_PER_SECTION")
fi

log "Phase 3: retrieve-evidence"
"${cmd[@]}"
