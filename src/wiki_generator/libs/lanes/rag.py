"""RAG / BM25 lane — the local retrieval corpus and indexes.

Artifacts:
  rag/spans.jsonl         citeable source spans (AST units, headings, sections)
  rag/chunks.jsonl        retrieval chunks (link back to span_ids)
  rag/bm25.sqlite         SQLite FTS5 lexical/BM25 index over chunks
  rag/rg-results.jsonl    raw ripgrep --json match capture (exact search substrate)
  rag/vectors.faiss       optional local semantic vectors (model2vec + FAISS)
  rag/vector-metadata.json    embedding model / dim / chunk-id mapping
"""
from __future__ import annotations

import json as _json
import os
import sqlite3

from .. import config as C
from .. import ids
from .. import chunker
from ..context import RunContext
from ..util import (clip, read_text, sha256_text, write_json, write_jsonl, log,
                    module_header_last)

_BM25_SCHEMA = """
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


def _python_spans(rec, parser, lines) -> list[dict]:
    spans: list[dict] = []
    n = len(lines)
    # module header span — always emitted so the materialized module symbol
    # (symbols.jsonl, kind=module) has a resolvable span_id.
    hdr_last = module_header_last(parser.first_def_line, n)
    text = clip("\n".join(lines[0:hdr_last]), C.MAX_CHUNK_CHARS)
    spans.append({
        "span_id": ids.span_id(rec["path"], 1, hdr_last, "module_header"),
        "path": rec["path"], "range": {"start_line": 1, "end_line": hdr_last},
        "language": "python", "category": rec["category"],
        "span_type": "module_header",
        "symbol_id": ids.module_symbol_id(parser.module),
        "heading_path": None, "section_name": None,
        "sha256": sha256_text(text), "text": text,
    })
    for s in parser.symbols:
        start = s["range"]["start_line"]
        end = min(max(s["range"]["end_line"], start), n)
        text = clip("\n".join(lines[start - 1:end]), C.MAX_CHUNK_CHARS)
        spans.append({
            "span_id": s["span_id"],
            "path": rec["path"], "range": {"start_line": start, "end_line": end},
            "language": "python", "category": rec["category"],
            "span_type": s["kind"], "symbol_id": s["symbol_id"],
            "heading_path": None, "section_name": None,
            "sha256": sha256_text(text), "text": text,
        })
    return spans


def _spans_from_chunks(rec, chunks) -> list[dict]:
    """Fallback / non-Python spans: one citeable span per chunk."""
    spans = []
    for c in chunks:
        st = c["range"]["start_line"]
        en = c["range"]["end_line"]
        spans.append({
            "span_id": ids.span_id(rec["path"], st, en, c["chunk_type"]),
            "path": rec["path"], "range": {"start_line": st, "end_line": en},
            "language": rec["language"], "category": rec["category"],
            "span_type": c["chunk_type"], "symbol_id": None,
            "heading_path": c.get("heading_path"),
            "section_name": c.get("section_name"),
            "sha256": c["sha256"], "text": c["text"],
        })
    return spans


def _link_chunks_to_spans(chunks, spans) -> None:
    by_size = sorted(spans, key=lambda s: (s["range"]["end_line"] - s["range"]["start_line"]))
    for c in chunks:
        cs, ce = c["range"]["start_line"], c["range"]["end_line"]
        hits = []
        for s in by_size:
            ss, se = s["range"]["start_line"], s["range"]["end_line"]
            if ss <= ce and cs <= se:  # overlap
                hits.append(s["span_id"])
                if len(hits) >= 8:
                    break
        c["span_ids"] = hits


def _dedupe_chunk_ids(chunks) -> None:
    seen: dict[str, int] = {}
    for c in chunks:
        cid = c["chunk_id"]
        if cid in seen:
            seen[cid] += 1
            c["chunk_id"] = f"{cid}:{c['chunk_type']}#{seen[cid]}"
        else:
            seen[cid] = 0


def _build_bm25(ctx: RunContext, inv: dict, chunks: list[dict], symbols: list[dict]) -> int:
    db = ctx.paths.bm25_sqlite
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    try:
        con.executescript(_BM25_SCHEMA)
        con.executemany(
            "INSERT OR IGNORE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r["path"], r["name"], r["ext"], r["size_bytes"], r["line_count"],
              r["language"], r["category"], r["top_dir"], r["sha256"],
              int(r["is_generated"]), int(r["is_vendor"])) for r in inv["files"]],
        )
        rows = []
        for c in chunks:
            rows.append((
                c["chunk_id"], c["path"], c["range"]["start_line"], c["range"]["end_line"],
                c["chunk_type"], c["language"], c["category"], c.get("symbol_name"),
                c.get("heading_path"), c.get("section_name"),
                _json.dumps(c.get("span_ids") or []), c.get("token_estimate"),
                c.get("sha256"), c.get("text", ""),
            ))
        con.executemany(
            "INSERT OR IGNORE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.executemany(
            "INSERT INTO symbols VALUES (?,?,?,?,?,?,?,?)",
            [(s["symbol_id"], s["name"], s["kind"], s["path"],
              s["range"]["start_line"], s["range"]["end_line"],
              s.get("signature"), s.get("parent_symbol_id")) for s in symbols],
        )
        con.execute(
            "INSERT INTO chunks_fts(rowid, text, symbol_name, heading_path, path) "
            "SELECT rowid, text, COALESCE(symbol_name,''), COALESCE(heading_path,''), path "
            "FROM chunks")
        con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')")
        con.commit()
    finally:
        con.close()
    return len(chunks)


def _build_vectors(ctx: RunContext, chunks: list[dict]) -> dict:
    """Optional model2vec + FAISS index. Returns {built, count, ...}."""
    want = ctx.opts.embeddings
    available = ctx.tools.embeddings.available
    if want == "off" or (want == "auto" and not available):
        note = "disabled" if want == "off" else ctx.tools.embeddings.note
        write_json(ctx.paths.vector_metadata, {
            "built": False, "reason": note, "model": C.EMBED_MODEL})
        ctx.record(ctx.paths.vector_metadata, produced_by="(skipped)",
                   description="vector index metadata", skipped=True, note=note)
        ctx.warn(f"vector lane skipped ({note}); rag/vectors.faiss not written. "
                 f"BM25 + ripgrep still provide retrieval.")
        return {"built": False}
    if want == "on" and not available:
        note = f"--embeddings on but libraries missing: {ctx.tools.embeddings.note}"
        write_json(ctx.paths.vector_metadata, {"built": False, "reason": note})
        ctx.record(ctx.paths.vector_metadata, produced_by="(skipped)",
                   description="vector index metadata", skipped=True, note=note)
        ctx.warn(note)
        return {"built": False}
    try:
        import faiss            # type: ignore
        import numpy as np      # type: ignore
        from model2vec import StaticModel  # type: ignore
    except Exception as e:  # noqa: BLE001
        ctx.warn(f"vector lane import failed at build time: {e}")
        write_json(ctx.paths.vector_metadata, {"built": False, "reason": str(e)})
        return {"built": False}

    model = StaticModel.from_pretrained(C.EMBED_MODEL)
    ids_list, meta, texts = [], [], []
    for c in chunks:
        ctxline = " ".join(filter(None, [c["path"], c.get("symbol_name"),
                                         c.get("heading_path"), c.get("docstring")]))
        texts.append((ctxline + "\n" + c.get("text", ""))[:C.EMBED_TEXT_CHARS])
        ids_list.append(c["chunk_id"])
        meta.append({"chunk_id": c["chunk_id"], "path": c["path"],
                     "start_line": c["range"]["start_line"],
                     "end_line": c["range"]["end_line"],
                     "chunk_type": c["chunk_type"]})
    if not texts:
        write_json(ctx.paths.vector_metadata, {"built": False, "reason": "no chunks"})
        return {"built": False}
    log(f"vector: embedding {len(texts)} chunks with {C.EMBED_MODEL} ...")
    parts = []
    for i in range(0, len(texts), 2048):
        v = np.asarray(model.encode(texts[i:i + 2048], max_length=512), dtype="float32")
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        parts.append(v / norms)
    mat = np.vstack(parts).astype("float32")
    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)
    faiss.write_index(index, ctx.paths.vectors_faiss)
    write_json(ctx.paths.vector_metadata, {
        "built": True, "model": C.EMBED_MODEL, "dim": int(mat.shape[1]),
        "count": len(ids_list), "metric": "cosine (IndexFlatIP, L2-normalized)",
        "ids": ids_list, "meta": meta,
    })
    ctx.record(ctx.paths.vectors_faiss, produced_by="model2vec + faiss",
               description="local semantic vectors over chunks", rows=len(ids_list))
    ctx.record(ctx.paths.vector_metadata, produced_by="model2vec + faiss",
               description="embedding model / dim / chunk-id map")
    ctx.count("rag/vectors", len(ids_list))
    return {"built": True, "count": len(ids_list), "dim": int(mat.shape[1])}


def build(ctx: RunContext, inv: dict, sym: dict, rg_data) -> dict:
    repo = ctx.repo
    modules = sym.get("modules", {})
    all_spans: list[dict] = []
    all_chunks: list[dict] = []

    for rec in inv["files"]:
        if not rec["indexable"]:
            continue
        ap = os.path.join(repo, rec["path"])
        text = read_text(ap, C.MAX_FILE_BYTES_FOR_TEXT)
        if text is None or not text.strip():
            continue
        lines = text.split("\n")
        parser = modules.get(rec["path"])
        chunks = chunker.chunk_file(rec, text, parser)
        if rec["language"] == "python" and parser is not None and not parser.error:
            spans = _python_spans(rec, parser, lines)
        else:
            spans = _spans_from_chunks(rec, chunks)
        _link_chunks_to_spans(chunks, spans)
        all_spans.extend(spans)
        all_chunks.extend(chunks)

    _dedupe_chunk_ids(all_chunks)
    all_spans.sort(key=lambda s: (s["path"], s["range"]["start_line"], s["span_type"]))
    all_chunks.sort(key=lambda c: (c["path"], c["range"]["start_line"]))

    n_spans = write_jsonl(ctx.paths.spans_jsonl, all_spans)
    ctx.count("rag/spans.jsonl", n_spans)
    ctx.record(ctx.paths.spans_jsonl, produced_by="python ast + chunker",
               description="citeable source spans (symbol-linked where Python)",
               rows=n_spans)

    n_chunks = write_jsonl(ctx.paths.chunks_jsonl, all_chunks)
    ctx.count("rag/chunks.jsonl", n_chunks)
    ctx.record(ctx.paths.chunks_jsonl, produced_by="chunker",
               description="retrieval chunks referencing span_ids", rows=n_chunks)

    n_bm = _build_bm25(ctx, inv, all_chunks, sym.get("symbols", []))
    ctx.count("rag/bm25.sqlite", n_bm)
    ctx.record(ctx.paths.bm25_sqlite, produced_by="sqlite fts5",
               description="BM25 lexical index over chunks (+ files/symbols tables)",
               rows=n_bm)

    # raw rg capture
    n_raw = write_jsonl(ctx.paths.rg_results_jsonl, rg_data.raw_events)
    ctx.count("rag/rg-results.jsonl", n_raw)
    ctx.record(ctx.paths.rg_results_jsonl, produced_by="ripgrep --json",
               description="raw exact/regex match capture (query packs)", rows=n_raw,
               note=None if rg_data.available else "ripgrep unavailable")

    vec = _build_vectors(ctx, all_chunks)

    log(f"rag: {n_spans} spans, {n_chunks} chunks, {n_bm} bm25 rows, "
        f"{n_raw} raw rg, vectors={'yes' if vec.get('built') else 'no'}")
    return {"spans": n_spans, "chunks": n_chunks, "vectors": vec}
