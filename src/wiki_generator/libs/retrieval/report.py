"""Render the human-readable readiness reports for Step 5.

``retrieval-substrate-report.md`` tells a person whether Phase 3 will run in
hybrid or lexical-symbolic mode and whether the substrate PASSED. The optional
``vector-build-report.md`` records the vector lane's model, count, or skip reason
plus the FAISS gotchas worth checking when ``--vectors on`` fails.

The reports are deterministic (no wall-clock) so they diff cleanly across reruns.
"""
from __future__ import annotations

from ..util import write_text
from .bm25 import Bm25Outcome
from .capabilities import HYBRID, LEXICAL_SYMBOLIC, retrieval_mode
from .loader import Corpus
from .vectors import BUILT, VectorResult

_FAISS_GOTCHAS = (
    "`faiss-cpu` wheel not available for this Python/macOS/architecture combo",
    "Rosetta/x86_64 vs arm64 environment mismatch",
    "pip fell back to a source build",
    "older pinned `faiss-cpu` with no Python 3.11+ wheel",
    "native OpenMP/libomp issues — try `FAISS_OPT_LEVEL=generic` to diagnose",
)


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _mode_recommendation(vectors: VectorResult) -> str:
    if retrieval_mode(vectors) == HYBRID:
        return (f"`{HYBRID}` — lexical-symbolic **plus** vector retrieval "
                f"({vectors.count:,} vectors, model `{vectors.model}`).")
    return (f"`{LEXICAL_SYMBOLIC}` — BM25 + ripgrep + symbols + graph + "
            "contracts + tests. Vectors are not available; install the "
            "`embeddings` extra and rerun with `--vectors on` for hybrid.")


def render_substrate_report(corpus: Corpus, bm25: Bm25Outcome,
                            vectors: VectorResult, warnings: list[str],
                            *, passed: bool) -> str:
    caps_present = [
        ("file_anchor (exact file/path/range)", corpus.has_files),
        ("symbol_anchor (symbol_id → span/chunk)", corpus.has_symbols),
        ("bm25 (lexical search over chunks)", bm25.status != "disabled" and bm25.ok),
        ("ripgrep_results (raw exact matches)", corpus.has_ripgrep_results),
        ("query_pack (canonical query-pack hits)", corpus.has_query_packs),
        ("graph_neighbors (static graph expansion)", corpus.has_static_graph),
        ("contract_lookup (OpenAPI routes)", corpus.has_contracts),
        ("test_lookup (test files/functions)", corpus.has_tests),
        ("vector (semantic search over chunks)", vectors.built),
    ]
    lines = [
        "# Retrieval substrate report",
        "",
        f"**Status:** {'PASS ✅' if passed else 'FAIL ❌'}",
        f"**Recommended Phase 3 retrieval mode:** {_mode_recommendation(vectors)}",
        "",
        "## Input bundle",
        "",
        f"- Bundle root: `{corpus.root}`",
        f"- Chunks: {corpus.chunk_count:,}",
        f"- Spans: {corpus.span_count:,}",
        "",
        "## BM25 lexical index",
        "",
        f"- Status: **{bm25.status}**"
        + (f" ({bm25.reason})" if bm25.reason else ""),
        f"- Indexed rows: {bm25.row_count:,} (chunk count: {bm25.chunk_count:,})",
        f"- Row-count check: {'OK' if bm25.ok else 'MISMATCH'}",
        f"- Content fingerprint: `{bm25.fingerprint}`",
        "",
        "## Vector index",
        "",
        f"- Status: **{vectors.status}**"
        + (f" — {vectors.reason}" if vectors.reason else ""),
        f"- Model: `{vectors.model}`" if vectors.built else "- Model: (none)",
        f"- Vectors: {vectors.count:,}",
        f"- Distance: {vectors.distance}" if vectors.built else "- Distance: (n/a)",
    ]
    if vectors.metadata_path:
        lines.append(f"- Metadata: `{vectors.metadata_path}` "
                     f"({vectors.metadata_format})")
    lines += [
        "",
        "## Retrieval modes available to Phase 3",
        "",
    ]
    lines += [f"- [{'x' if present else ' '}] {label}"
              for label, present in caps_present]
    lines += [
        "",
        "## Caveats",
        "",
    ]
    if warnings:
        lines += [f"- {w}" for w in warnings]
    else:
        lines.append("- None.")
    if not vectors.built:
        lines += [
            "",
            "If vectors were expected, common FAISS install gotchas:",
            "",
        ]
        lines += [f"- {g}" for g in _FAISS_GOTCHAS]
    lines.append("")
    return "\n".join(lines)


def render_vector_build_report(corpus: Corpus, vectors: VectorResult) -> str:
    lines = [
        "# Vector build report",
        "",
        f"**Status:** {vectors.status}",
    ]
    if vectors.reason:
        lines.append(f"**Reason:** {vectors.reason}")
    lines += [
        "",
        f"- Model: `{vectors.model}`",
        f"- Distance: {vectors.distance}",
        f"- Vectors written: {vectors.count:,}",
        f"- Index: `{vectors.index_path}`" if vectors.index_path else "- Index: (none)",
        f"- Metadata: `{vectors.metadata_path}` ({vectors.metadata_format})"
        if vectors.metadata_path else "- Metadata: (none)",
        "",
    ]
    if vectors.status != BUILT:
        lines += [
            "Vectors were not built. To enable hybrid retrieval, install the "
            "embeddings extra and rerun:",
            "",
            "```bash",
            "pip install -e '.[embeddings]'",
            "wiki-generator build-retrieval --in <bundle> --vectors on",
            "```",
            "",
            "FAISS install gotchas to check:",
            "",
        ]
        lines += [f"- {g}" for g in _FAISS_GOTCHAS]
        lines.append("")
    return "\n".join(lines)


def write_substrate_report(corpus: Corpus, text: str) -> str:
    path = corpus.paths.retrieval_report
    write_text(path, text)
    return path


def write_vector_build_report(corpus: Corpus, text: str) -> str:
    path = corpus.paths.vector_build_report
    write_text(path, text)
    return path
