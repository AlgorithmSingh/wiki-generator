"""SQLite FTS5 lexical/BM25 index over the chunk corpus.

This is the **single source of truth** for the BM25 schema and how chunks, files,
and symbols are written into it. Both the decompose ``rag`` lane (which builds the
index inline during Phase 1 Step 1) and the Step 5 ``build-retrieval`` command
(which verifies or rebuilds it) call :func:`build_index`, so the schema can never
drift between the two producers.

The module is pure mechanism: it takes plain ``list[dict]`` rows — exactly the
shape stored in ``inventory/files.jsonl``, ``rag/chunks.jsonl`` and
``symbols/symbols.jsonl`` — and never reads the bundle layout itself. Every
connection is closed via :func:`contextlib.closing` so the file handle is
released even on error.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass

from . import fingerprints

SCHEMA = """
CREATE TABLE files (
  path TEXT PRIMARY KEY, name TEXT, ext TEXT, size_bytes INTEGER, line_count INTEGER,
  language TEXT, category TEXT, top_dir TEXT, sha256 TEXT,
  is_generated INTEGER, is_vendor INTEGER
);
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY, path TEXT, start_line INTEGER, end_line INTEGER,
  chunk_type TEXT, language TEXT, category TEXT, symbol_name TEXT,
  heading_path TEXT, section_name TEXT, span_ids TEXT, token_estimate INTEGER,
  sha256 TEXT, text TEXT
);
CREATE INDEX idx_chunks_path ON chunks(path);
CREATE INDEX idx_chunks_type ON chunks(chunk_type);
CREATE TABLE symbols (
  symbol_id TEXT, name TEXT, kind TEXT, path TEXT,
  start_line INTEGER, end_line INTEGER, signature TEXT, parent_symbol_id TEXT
);
CREATE INDEX idx_symbols_name ON symbols(name);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text, symbol_name, heading_path, path,
  content='chunks', content_rowid='rowid', tokenize='porter unicode61'
);
"""

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class IndexState:
    """What an existing index records about the corpus it was built from."""

    row_count: int
    fingerprint: str


@dataclass(frozen=True)
class Bm25Outcome:
    """Result of ensuring a usable BM25 index exists for the corpus."""

    status: str             # built | rebuilt | verified | disabled
    row_count: int
    chunk_count: int
    fingerprint: str
    ok: bool                # row_count == chunk_count (the integrity invariant)
    reason: str | None = None  # why a (re)build happened; None when verified


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    span_ids: list[str]
    score: float


def build_index(db_path: str, files: Iterable[dict], chunks: Iterable[dict],
                symbols: Iterable[dict]) -> int:
    """Create ``db_path`` from scratch and return the indexed chunk row count.

    Any pre-existing file at ``db_path`` is removed first so a rebuild never
    leaves stale rows behind. ``files``/``chunks``/``symbols`` are the records
    from ``inventory/files.jsonl``, ``rag/chunks.jsonl`` and
    ``symbols/symbols.jsonl`` respectively.
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    chunk_rows = list(chunks)
    with closing(sqlite3.connect(db_path)) as con:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT OR IGNORE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r["path"], r.get("name"), r.get("ext"), r.get("size_bytes"),
              r.get("line_count"), r.get("language"), r.get("category"),
              r.get("top_dir"), r.get("sha256"),
              int(bool(r.get("is_generated"))), int(bool(r.get("is_vendor"))))
             for r in files],
        )
        con.executemany(
            "INSERT OR IGNORE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(c["chunk_id"], c["path"], c["range"]["start_line"],
              c["range"]["end_line"], c.get("chunk_type"), c.get("language"),
              c.get("category"), c.get("symbol_name"), c.get("heading_path"),
              c.get("section_name"), json.dumps(c.get("span_ids") or []),
              c.get("token_estimate"), c.get("sha256"), c.get("text", ""))
             for c in chunk_rows],
        )
        # Symbols are auxiliary (a name->range lookup table), so a malformed row
        # is skipped rather than crashing the whole index build.
        sym_rows = []
        for s in symbols:
            rng = s.get("range") if isinstance(s, dict) else None
            if "symbol_id" not in (s or {}) or not isinstance(rng, dict):
                continue
            sym_rows.append((
                s["symbol_id"], s.get("name"), s.get("kind"), s.get("path"),
                rng.get("start_line"), rng.get("end_line"),
                s.get("signature"), s.get("parent_symbol_id")))
        con.executemany("INSERT INTO symbols VALUES (?,?,?,?,?,?,?,?)", sym_rows)
        con.execute(
            "INSERT INTO chunks_fts(rowid, text, symbol_name, heading_path, path) "
            "SELECT rowid, text, COALESCE(symbol_name,''), "
            "COALESCE(heading_path,''), path FROM chunks")
        con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')")
        con.commit()
    return len(chunk_rows)


def ensure_index(db_path: str, files: Iterable[dict], chunks: Iterable[dict],
                 symbols: Iterable[dict], *, current_fingerprint: str,
                 rebuild: bool = False, enabled: bool = True) -> Bm25Outcome:
    """Build, rebuild, or verify the BM25 index so it matches the corpus.

    A (re)build is triggered when the index is missing, ``rebuild`` is requested,
    the recorded row count diverges from the chunk count, or the corpus
    fingerprint is stale. Otherwise the existing index is verified in place. The
    integrity invariant ``row_count == chunk_count`` is re-checked after any
    build and reported as :attr:`Bm25Outcome.ok`.
    """
    chunk_rows = list(chunks)
    chunk_count = len(chunk_rows)
    if not enabled:
        return Bm25Outcome("disabled", 0, chunk_count, current_fingerprint,
                           ok=True, reason="bm25 disabled (--bm25 off)")

    state = read_index_state(db_path)
    if rebuild:
        reason = "--rebuild requested"
        status = "rebuilt" if state is not None else "built"
        need = True
    elif state is None:
        reason, status, need = "index missing or unreadable", "built", True
    elif state.row_count != chunk_count:
        reason = f"row count {state.row_count} != chunk count {chunk_count}"
        status, need = "rebuilt", True
    elif fingerprints.is_stale(state.fingerprint, current_fingerprint):
        reason, status, need = "corpus fingerprint changed (stale index)", "rebuilt", True
    else:
        reason, status, need = None, "verified", False

    if need:
        build_index(db_path, files, chunk_rows, symbols)
        state = read_index_state(db_path)

    row_count = state.row_count if state is not None else 0
    fingerprint = state.fingerprint if state is not None else current_fingerprint
    return Bm25Outcome(status, row_count, chunk_count, fingerprint,
                       ok=(row_count == chunk_count), reason=reason)


def read_index_state(db_path: str) -> IndexState | None:
    """Return the row count and corpus fingerprint recorded by an index.

    ``None`` if the file is missing or is not a readable BM25 index (so callers
    treat a corrupt/foreign file the same as "needs rebuild").
    """
    if not os.path.isfile(db_path):
        return None
    try:
        with closing(sqlite3.connect(db_path)) as con:
            rows = con.execute(
                "SELECT chunk_id, COALESCE(sha256,'') FROM chunks").fetchall()
            count = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    except sqlite3.DatabaseError:
        return None
    fp = fingerprints.fingerprint_pairs((str(cid), str(sha)) for cid, sha in rows)
    return IndexState(row_count=int(count), fingerprint=fp)


def fts_match_query(text: str) -> str | None:
    """Turn free text into a lenient, injection-safe FTS5 MATCH expression.

    Alphanumeric tokens are each double-quoted (so FTS5 treats them as literals,
    never operators) and OR-joined. Returns ``None`` when the text has no usable
    tokens, so the caller can skip the query rather than issue an empty MATCH.
    """
    tokens = _TOKEN_RE.findall(text or "")
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def search(db_path: str, query: str, k: int = 5) -> list[SearchHit]:
    """Deterministic top-k BM25 search. Empty list for an empty/no-token query.

    Ordered by ascending FTS5 ``bm25()`` score (lower is more relevant) with a
    ``chunk_id`` tiebreak so results are stable across runs.
    """
    match = fts_match_query(query)
    if match is None:
        return []
    with closing(sqlite3.connect(db_path)) as con:
        rows = con.execute(
            "SELECT c.chunk_id, c.path, c.start_line, c.end_line, c.span_ids, "
            "bm25(chunks_fts) AS score "
            "FROM chunks_fts JOIN chunks c ON c.rowid = chunks_fts.rowid "
            "WHERE chunks_fts MATCH ? "
            "ORDER BY score ASC, c.chunk_id ASC LIMIT ?",
            (match, int(k)),
        ).fetchall()
    hits: list[SearchHit] = []
    for cid, path, start, end, span_ids, score in rows:
        try:
            spans = json.loads(span_ids) if span_ids else []
        except json.JSONDecodeError:
            spans = []
        hits.append(SearchHit(
            chunk_id=cid, path=path, start_line=int(start), end_line=int(end),
            span_ids=list(spans), score=float(score)))
    return hits
