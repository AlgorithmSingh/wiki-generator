"""Load a Step 1 corpus into memory for retrieval-substrate building.

The single seam between the bundle on disk and the substrate builder. It reads
the corpus the index is built from (chunks, files, symbols), confirms the
citeable layers exist (spans), and probes which *optional* retrieval surfaces are
present so the capability contract can report them. Missing optional artifacts
degrade to ``False`` capabilities; a missing/unreadable required corpus raises
:class:`MissingCorpusError`.

Nothing here interprets the data — it stays a thin, deep IO module, mirroring
``libs/digest/loader.py``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from ..paths import Paths


class MissingCorpusError(Exception):
    """A required corpus artifact (chunks/spans) is missing, unreadable, or
    malformed (e.g. a chunk lacking chunk_id/path/range, or a duplicate
    chunk_id). Surfaced by the command layer as exit code 2."""


def _validate_chunks(chunks: list[dict], rel: str) -> None:
    """Fail fast on a structurally-broken corpus so the index builder never hits
    a raw KeyError and a duplicate chunk_id never silently truncates the index.

    ``loader`` reads JSONL leniently (skipping syntactically bad lines); this is
    the schema gate that the leniency would otherwise let through.
    """
    seen: set = set()
    for i, c in enumerate(chunks):
        rng = c.get("range") if isinstance(c, dict) else None
        if (not isinstance(c, dict) or "chunk_id" not in c or "path" not in c
                or not isinstance(rng, dict)
                or "start_line" not in rng or "end_line" not in rng):
            raise MissingCorpusError(
                f"malformed chunk at index {i} in {rel}: each chunk needs "
                "chunk_id, path, and range.start_line/range.end_line")
        cid = c["chunk_id"]
        if cid in seen:
            raise MissingCorpusError(
                f"duplicate chunk_id in {rel}: {cid!r} — the corpus is not "
                "deduplicated; rerun `decompose`")
        seen.add(cid)


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _count_jsonl(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _present_nonempty_jsonl(path: str) -> bool:
    return os.path.isfile(path) and _count_jsonl(path) > 0


def _openapi_has_routes(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    paths = doc.get("paths") if isinstance(doc, dict) else None
    return bool(paths)


@dataclass
class Corpus:
    """An in-memory view of the corpus a retrieval substrate is built over."""

    root: str
    paths: Paths
    chunks: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)
    span_count: int = 0
    # Optional-surface presence flags (drive the capability contract).
    has_files: bool = False
    has_symbols: bool = False
    has_ripgrep_results: bool = False
    has_query_packs: bool = False
    has_static_graph: bool = False
    has_contracts: bool = False
    has_tests: bool = False
    missing_optional: list[str] = field(default_factory=list)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


def load_corpus(paths: Paths) -> Corpus:
    """Read the corpus and probe optional surfaces. Missing chunks/spans raise."""
    if not os.path.isfile(paths.chunks_jsonl):
        raise MissingCorpusError(
            f"required corpus missing: {paths.rel(paths.chunks_jsonl)} not found "
            "— run `decompose` first")
    if not os.path.isfile(paths.spans_jsonl):
        raise MissingCorpusError(
            f"required corpus missing: {paths.rel(paths.spans_jsonl)} not found "
            "— run `decompose` first")

    chunks = _read_jsonl(paths.chunks_jsonl)
    _validate_chunks(chunks, paths.rel(paths.chunks_jsonl))
    files = _read_jsonl(paths.files_jsonl)
    symbols = _read_jsonl(paths.symbols_jsonl)
    span_count = _count_jsonl(paths.spans_jsonl)

    missing: list[str] = []
    for label, present in (
        ("symbols/symbols.jsonl", bool(symbols)),
        ("inventory/files.jsonl", bool(files)),
        ("rag/rg-results.jsonl", _present_nonempty_jsonl(paths.rg_results_jsonl)),
        ("queries/results/rg.jsonl", _present_nonempty_jsonl(paths.rg_jsonl)),
        ("static/edges.jsonl", _present_nonempty_jsonl(paths.edges_jsonl)),
        ("contracts/openapi.json", _openapi_has_routes(paths.openapi_json)),
        ("tests/test-files.jsonl", _present_nonempty_jsonl(paths.test_files_jsonl)),
    ):
        if not present:
            missing.append(label)

    return Corpus(
        root=paths.out,
        paths=paths,
        chunks=chunks,
        files=files,
        symbols=symbols,
        span_count=span_count,
        has_files=bool(files),
        has_symbols=bool(symbols),
        has_ripgrep_results=_present_nonempty_jsonl(paths.rg_results_jsonl),
        has_query_packs=_present_nonempty_jsonl(paths.rg_jsonl),
        has_static_graph=_present_nonempty_jsonl(paths.edges_jsonl),
        has_contracts=_openapi_has_routes(paths.openapi_json),
        has_tests=_present_nonempty_jsonl(paths.test_files_jsonl),
        missing_optional=missing,
    )
