"""Deterministic citeable-substrate view for the Phase 2 TER viability check.

The Phase 2 topic-obligation gate (:mod:`.obligations`) can decide *from the plan
alone* whether a required topic's ``topic_evidence_requirements[]`` source fields
are lane-type-consistent with ``acceptable_lanes[]``. It cannot, from the plan
alone, decide whether an exact source field that resolves in inventory will
actually yield **citeable** evidence when Phase 3 retrieves it.

The live RAGFlow enhancement run proved that gap is real: ``go.mod`` and
``Dockerfile`` resolved as ``file_exists`` in the inventory and passed every plan
shape check, but the retrieval substrate held **zero** chunks/spans for either
path, so Phase 3 produced no citeable evidence and failed closed after retrieval
(``56/59`` sufficient, ``1`` weak, ``2`` missing) — too late, after 22 packets and
704 evidence items.

This module is the smallest read-only view of the retrieval substrate the Phase 2
gate needs to catch that class *before* Phase 3: the set of repo paths the
file/test evidence lanes could actually cite. Citeability is **lane-specific**,
mirroring exactly what those lanes draw from:

- ``file_anchor`` (``evidence/lanes/files.py``): an exact-anchor request emits
  ``overlapping_spans`` hits *and* ``overlapping_chunks`` hits; a file-only request
  emits ``file_repr_chunks``. So a file is citeable on this lane when it has at
  least one **chunk OR span** (``chunks_by_path`` / ``spans_by_path``). This matters
  because ``lanes/rag.py`` always emits a ``module_header`` span for a Python file
  even when the chunker produced no chunk for it — a chunk-only test would wrongly
  reject such a file.
- ``test`` (``evidence/lanes/tests.py``): only ``file_repr_chunks`` is used, so a
  test file is citeable on this lane only when it has at least one **chunk**.

``symbol_anchor`` / ``contract`` / ``query_pack`` citeability is NOT modelled here
(a resolved symbol always yields at least its own span); the gate leaves those
lanes undecidable so they never produce a false non-citeable failure.

It is deterministic, network-free, and LLM-free. It never edits the plan, never
synthesizes evidence, and never makes evidence exist; it only reports which exact
file/test handles the substrate *could* cite so the gate can fail loudly upstream.
When the corpus is absent or empty (e.g. a unit fixture with no ``rag/`` directory)
the loader returns ``None`` and the gate skips the citeability check (report-only /
non-breaking) rather than attributing a missing/empty index to per-topic plan
defects — an empty corpus is already a hard input error Phase 3's loader reports.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from ..paths import Paths

CITEABLE_SUBSTRATE_SCHEMA_VERSION = "phase2-citeable-substrate-v1"


@dataclass(frozen=True)
class CiteableSubstrate:
    """The minimal read-only retrieval-substrate view the Phase 2 gate needs.

    ``chunk_paths`` is the set of repo paths with ≥1 chunk in ``rag/chunks.jsonl``;
    ``span_paths`` is the set with ≥1 span in ``rag/spans.jsonl``. Citeability is
    lane-specific: the ``file_anchor`` lane can cite a path via chunk **or** span,
    the ``test`` lane only via chunk. ``available`` is ``True`` only when a real
    chunk corpus was read."""

    chunk_paths: frozenset
    span_paths: frozenset = frozenset()
    available: bool = True

    def cites_file(self, path) -> bool:
        """True when the ``file_anchor`` lane could cite ``path`` (chunk OR span)."""
        return isinstance(path, str) and (path in self.chunk_paths
                                          or path in self.span_paths)

    def cites_test(self, path) -> bool:
        """True when the ``test`` lane could cite ``path`` (chunk only)."""
        return isinstance(path, str) and path in self.chunk_paths

    @property
    def citeable_path_count(self) -> int:
        return len(self.chunk_paths | self.span_paths)


def _stream_paths(path: str) -> set:
    """The distinct ``path`` values in a JSONL corpus, read by streaming (only the
    ``path`` field matters to citeability). Lenient: a bad line is skipped."""
    out: set = set()
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = row.get("path") if isinstance(row, dict) else None
            if isinstance(p, str):
                out.add(p)
    return out


def load_citeable_substrate(bundle_dir: str) -> CiteableSubstrate | None:
    """Build the citeable-substrate view from ``bundle_dir``'s rag corpus.

    Streams ``rag/chunks.jsonl`` and ``rag/spans.jsonl`` once each, collecting the
    distinct ``path`` values that determine file/test citeability. Returns ``None``
    when ``rag/chunks.jsonl`` is missing, or when the corpus is present but empty
    (no chunk and no span path) — the caller then runs the gate in
    report-only/citeability-skipped mode rather than attributing a missing/empty
    index to per-topic plan defects (Phase 3's loader reports an empty corpus as a
    hard input error itself).

    Deterministic and read-only."""
    paths = Paths(repo=bundle_dir, out=bundle_dir)
    if not os.path.isfile(paths.chunks_jsonl):
        return None
    chunk_paths = _stream_paths(paths.chunks_jsonl)
    span_paths = _stream_paths(paths.spans_jsonl)
    if not chunk_paths and not span_paths:
        return None
    return CiteableSubstrate(chunk_paths=frozenset(chunk_paths),
                             span_paths=frozenset(span_paths))
