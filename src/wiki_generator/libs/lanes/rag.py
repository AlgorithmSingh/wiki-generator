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

import os

from .. import config as C
from .. import ids
from .. import chunker
from ..context import RunContext
from ..retrieval import bm25, vectors
from ..retrieval.loader import Corpus
from ..retrieval.options import BuildOptions
from ..util import (clip, read_text, sha256_text, write_jsonl, log,
                    module_header_last)


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
    # Delegates to the shared builder so decompose and `build-retrieval` (Step 5)
    # always write the identical FTS5 schema — see libs/retrieval/bm25.py.
    return bm25.build_index(ctx.paths.bm25_sqlite, inv["files"], chunks, symbols)


def _build_vectors(ctx: RunContext, chunks: list[dict]) -> vectors.VectorResult:
    """Optional model2vec + FAISS index. Delegates to the shared Step 5 builder
    (``libs/retrieval/vectors.py``) so decompose and ``build-retrieval`` emit
    byte-identical vector artifacts — same embed text, FAISS mechanism,
    ``vector-metadata-v1`` schema, and chunk ordering — then maps the result onto
    this run's artifact index / warning collectors."""
    opts = BuildOptions(bundle_root=ctx.out, vectors_mode=ctx.opts.embeddings,
                        embedding_model=C.EMBED_MODEL)
    corpus = Corpus(root=ctx.out, paths=ctx.paths, chunks=chunks)
    res = vectors.build_or_verify(corpus, opts, vectors.FaissModel2VecBackend())
    if res.built:
        ctx.record(ctx.paths.vectors_faiss, produced_by="model2vec + faiss",
                   description="local semantic vectors over chunks", rows=res.count)
        ctx.record(ctx.paths.vector_metadata, produced_by="model2vec + faiss",
                   description="embedding model / vector-metadata-v1")
        ctx.count("rag/vectors", res.count)
    else:
        ctx.record(ctx.paths.vector_metadata, produced_by="(skipped)",
                   description="vector index metadata", skipped=True, note=res.reason)
        ctx.warn(f"vector lane {res.status}: {res.reason}; rag/vectors.faiss not "
                 "written. BM25 + ripgrep still provide retrieval.")
    return res


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
    # 3-key sort (chunk_id tiebreak) matches retrieval.vectors._ordered_chunks, so
    # chunks.jsonl order and the embedding/FAISS row order agree across producers.
    all_chunks.sort(key=lambda c: (c["path"], c["range"]["start_line"], c["chunk_id"]))

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
        f"{n_raw} raw rg, vectors={'yes' if vec.built else 'no'}")
    return {"spans": n_spans, "chunks": n_chunks,
            "vectors": {"built": vec.built, "count": vec.count}}
