"""Phase 1 Step 5 command: build the retrieval substrate over a Step 1 bundle.

Verifies or rebuilds the BM25 lexical index, optionally builds local vectors, and
writes the Phase 3 capability contract + readiness report. Deterministic; no LLM
calls, no network.

    python -m wiki_generator build-retrieval --in <bundle> \\
        [--bm25 auto|on|off] [--vectors auto|on|off] \\
        [--embedding-model NAME] [--batch-size N] [--rebuild] \\
        [--smoke-query TEXT] [--fail-without-vectors]

Exit codes: 0 = PASS, 1 = FAIL (e.g. ``--vectors on`` with no backend, or a
BM25 integrity mismatch), 2 = missing/unreadable required corpus.
"""
from __future__ import annotations

import argparse
import os

from .. import retrieval
from ..util import log


def build_options(args: argparse.Namespace) -> retrieval.BuildOptions:
    """Translate parsed CLI args into the builder's options contract.

    Optional knobs the user did not pass are omitted so ``BuildOptions``' own
    dataclass defaults are the single source of truth (no re-hardcoded defaults),
    and an explicit out-of-range value (e.g. ``--batch-size 0``) reaches the
    dataclass validator rather than being silently coerced."""
    kwargs = {
        "bundle_root": os.path.abspath(os.path.expanduser(args.in_dir)),
        "bm25_mode": getattr(args, "bm25", "on"),
        "vectors_mode": "on" if getattr(args, "fail_without_vectors", False)
        else getattr(args, "vectors", "auto"),
        "rebuild": getattr(args, "rebuild", False),
        "smoke_query": getattr(args, "smoke_query", None),
    }
    if getattr(args, "embedding_model", None) is not None:
        kwargs["embedding_model"] = args.embedding_model
    if getattr(args, "batch_size", None) is not None:
        kwargs["batch_size"] = args.batch_size
    return retrieval.BuildOptions(**kwargs)


def run(args: argparse.Namespace) -> int:
    try:
        options = build_options(args)
    except ValueError as e:
        log(f"build-retrieval: invalid options — {e}")
        return 2
    if not os.path.isdir(options.bundle_root):
        log(f"build-retrieval: not a bundle directory: {options.bundle_root}")
        return 2

    log(f"build-retrieval: {options.bundle_root}")
    try:
        result = retrieval.run(options)
    except retrieval.MissingCorpusError as e:
        log(f"build-retrieval: {e}")
        return 2

    b = result.bm25
    log(f"  bm25: {b.status} — {b.row_count:,} rows "
        f"(chunks {b.chunk_count:,}){' ' + b.reason if b.reason else ''}")
    v = result.vectors
    log(f"  vectors: {v.status}"
        + (f" — {v.count:,} @ {v.model}" if v.built
           else (f" — {v.reason}" if v.reason else "")))
    for f in result.files_written:
        log(f"    - {f}")
    if result.smoke:
        for row in result.smoke:
            log(f"  smoke[{row['mode']}] '{row['query']}': {row['hit_count']} hit(s)")
    log(f"  retrieval mode: {result.retrieval_mode}")
    for w in result.warnings:
        log(f"  warning: {w}")

    if not result.ok:
        log("build-retrieval: FAIL — see retrieval-substrate-report.md")
        return 1
    log("build-retrieval: PASS")
    return 0
