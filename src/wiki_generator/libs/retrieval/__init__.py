"""Phase 1 Step 5 — the retrieval substrate builder (facade).

``run(options)`` is the one public entry point. It loads the Step 1 corpus,
ensures a fresh BM25 lexical index, optionally builds local vectors, writes the
machine-readable capability contract + human-readable readiness report, and runs
any smoke query — then returns a :class:`Result` the command layer maps to an
exit code. Everything is deterministic and LLM-free; no network, no API keys.

The heavy lifting lives in the sibling deep modules (``loader``, ``bm25``,
``vectors``, ``capabilities``, ``report``, ``smoke``); this module only wires
them together and decides PASS/FAIL. The vector backend is injected (defaulting
to the real faiss/model2vec one) so the whole pipeline is testable without the
optional embedding libraries installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..paths import Paths
from . import bm25, capabilities, fingerprints, report, smoke, vectors
from .bm25 import Bm25Outcome
from .loader import Corpus, MissingCorpusError, load_corpus
from .options import BuildOptions
from .vectors import FaissModel2VecBackend, VectorBackend, VectorResult

__all__ = [
    "BuildOptions", "Result", "run", "MissingCorpusError",
    "VectorBackend", "FaissModel2VecBackend",
]


@dataclass
class Result:
    ok: bool
    retrieval_mode: str
    capabilities: dict
    bm25: Bm25Outcome
    vectors: VectorResult
    warnings: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    smoke: list[dict] = field(default_factory=list)


def _collect_warnings(corpus: Corpus, bm25_outcome: Bm25Outcome,
                      vector_result: VectorResult, faiss_exists: bool) -> list[str]:
    warnings: list[str] = []
    if bm25_outcome.status == "disabled":
        warnings.append("BM25 disabled (--bm25 off); lexical chunk search "
                        "unavailable for Phase 3.")
    elif not bm25_outcome.ok:
        warnings.append(
            f"BM25 row count {bm25_outcome.row_count} != chunk count "
            f"{bm25_outcome.chunk_count}; lexical index is incomplete.")
    if vector_result.status == vectors.SKIPPED:
        warnings.append(f"Vectors skipped: {vector_result.reason}")
    elif vector_result.status == vectors.DISABLED:
        warnings.append("Vectors disabled by user (--vectors off); Phase 3 runs "
                        "lexical-symbolic.")
    elif vector_result.status == vectors.FAILED:
        warnings.append(f"Vectors failed: {vector_result.reason}")
    if not vector_result.built and faiss_exists:
        warnings.append(
            "A pre-existing rag/vectors.faiss is present but was not verified and "
            "is not advertised in capabilities; rerun with `--rebuild --vectors "
            "on` to rebuild it.")
    for label in corpus.missing_optional:
        warnings.append(f"Optional surface absent or empty: {label}")
    return warnings


def run(options: BuildOptions, *, backend: VectorBackend | None = None) -> Result:
    """Build/verify the retrieval substrate. Raises :class:`MissingCorpusError`
    when the required corpus (chunks/spans) is missing."""
    paths = Paths(repo=options.bundle_root, out=options.bundle_root)
    corpus = load_corpus(paths)

    current_fp = fingerprints.corpus_fingerprint(corpus.chunks)
    bm25_outcome = bm25.ensure_index(
        paths.bm25_sqlite, corpus.files, corpus.chunks, corpus.symbols,
        current_fingerprint=current_fp, rebuild=options.rebuild,
        enabled=(options.bm25_mode != "off"))

    vector_result = build_vectors(corpus, options, backend)
    # Check for an orphan index AFTER the build, so a file left by a failed
    # in-run build (or already removed by --rebuild) is judged on its real state.
    faiss_after = os.path.exists(paths.vectors_faiss)

    bm25_required = options.bm25_mode != "off"
    can_smoke = bm25_required and bm25_outcome.ok

    warnings = _collect_warnings(corpus, bm25_outcome, vector_result, faiss_after)
    if options.smoke_query and not can_smoke:
        warnings.append("Smoke query requested but no lexical index is available "
                        "(bm25 disabled or incomplete); smoke skipped.")
        # don't let a prior run's smoke file misrepresent this run
        if os.path.exists(paths.retrieval_smoke):
            os.remove(paths.retrieval_smoke)
    caps_doc = capabilities.build(corpus, bm25_outcome, vector_result, warnings)

    passed = True
    if bm25_required and not bm25_outcome.ok:
        passed = False
    if options.vectors_mode == "on" and not vector_result.built:
        passed = False

    files_written = [capabilities.write(corpus, caps_doc)]
    report_text = report.render_substrate_report(
        corpus, bm25_outcome, vector_result, warnings, passed=passed)
    files_written.append(report.write_substrate_report(corpus, report_text))
    if options.vectors_mode != "off":
        vec_report = report.render_vector_build_report(corpus, vector_result)
        files_written.append(report.write_vector_build_report(corpus, vec_report))

    smoke_rows: list[dict] = []
    if options.smoke_query and can_smoke:
        smoke_rows = smoke.run_smoke(corpus, options.smoke_query, bm25_enabled=True)
        files_written.append(paths.retrieval_smoke)

    return Result(
        ok=passed,
        retrieval_mode=caps_doc["retrieval_mode"],
        capabilities=caps_doc,
        bm25=bm25_outcome,
        vectors=vector_result,
        warnings=warnings,
        files_written=[paths.rel(p) for p in files_written],
        smoke=smoke_rows,
    )


def build_vectors(corpus: Corpus, options: BuildOptions,
                  backend: VectorBackend | None) -> VectorResult:
    """Resolve the vector backend (real one by default) and run the lane."""
    return vectors.build_or_verify(
        corpus, options, backend or FaissModel2VecBackend())
