"""Assemble ``rag/retrieval-capabilities.json`` — the machine-readable contract
Phase 3 reads to learn which retrieval modes this bundle supports.

This is intentionally small and deterministic: the same corpus + outcomes always
produce a byte-identical document (no timestamps, no wall-clock), so reruns are
reproducible. It is not a replacement for ``ARTIFACT_GUIDE.md`` — only the
capability surface Phase 3 needs to pick retrieval tactics per section.
"""
from __future__ import annotations

from ..paths import Paths
from ..util import write_json
from .bm25 import Bm25Outcome
from .loader import Corpus
from .vectors import VectorResult

SCHEMA_VERSION = "retrieval-substrate-v1"
HYBRID = "hybrid"
LEXICAL_SYMBOLIC = "lexical-symbolic"


def retrieval_mode(vectors: VectorResult) -> str:
    """Phase-3 mode: hybrid when vectors are built, else lexical-symbolic."""
    return HYBRID if vectors.built else LEXICAL_SYMBOLIC


def build(corpus: Corpus, bm25: Bm25Outcome, vectors: VectorResult,
          warnings: list[str]) -> dict:
    """Return the capability document as a plain dict (ready for JSON)."""
    paths: Paths = corpus.paths
    bm25_enabled = bm25.status != "disabled"
    caps = {
        "file_lookup": corpus.has_files,
        "symbol_lookup": corpus.has_symbols,
        "bm25": bm25_enabled and bm25.ok,
        "ripgrep_results": corpus.has_ripgrep_results,
        "query_packs": corpus.has_query_packs,
        "static_graph": corpus.has_static_graph,
        "contracts": corpus.has_contracts,
        "tests": corpus.has_tests,
        "vectors": vectors.built,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "bundle_root": corpus.root,
        "chunk_count": corpus.chunk_count,
        "span_count": corpus.span_count,
        "retrieval_mode": retrieval_mode(vectors),
        "capabilities": caps,
        "indexes": {
            "bm25": {
                "path": paths.rel(paths.bm25_sqlite) if bm25_enabled else None,
                "row_count": bm25.row_count,
                "content_fingerprint": bm25.fingerprint,
                "status": bm25.status,
            },
            "vectors": {
                "path": vectors.index_path,
                "metadata_path": vectors.metadata_path,
                "metadata_format": vectors.metadata_format,
                "row_count": vectors.count,
                "model": vectors.model if vectors.built else None,
                "distance": vectors.distance if vectors.built else None,
                "status": vectors.status,
                "reason": vectors.reason,
            },
        },
        "warnings": list(warnings),
        "generated_by": "wiki-generator build-retrieval",
    }


def write(corpus: Corpus, doc: dict) -> str:
    """Write the capability document and return its absolute path."""
    path = corpus.paths.retrieval_capabilities
    write_json(path, doc)
    return path
