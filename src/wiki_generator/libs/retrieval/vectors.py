"""Optional local vector lane: embed chunks and build/verify a FAISS index.

The *policy* (auto/on/off semantics, stable chunk ordering, metadata assembly,
count verification, skip-reason recording) lives in :func:`build_or_verify` and
is fully deterministic and library-free. The *mechanism* (importing faiss/numpy/
model2vec, loading the embedding model, writing the index) is hidden behind the
:class:`VectorBackend` seam. The real backend lazily imports the heavy libraries
inside its methods — never at import time — so importing this module is always
cheap and side-effect free, and tests can inject a fake backend to exercise the
hybrid path without faiss installed.

No network calls, no API keys, no external services: embeddings are computed
locally or the lane is skipped with an explicit reason.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from .. import config as C
from ..util import log, write_json, write_jsonl
from .loader import Corpus
from .options import BuildOptions

SCHEMA_VERSION = "vector-metadata-v1"
DISTANCE = "cosine"

# Status values for the vector lane (also surfaced in the capability contract).
BUILT = "built"
SKIPPED = "skipped"
DISABLED = "disabled_by_user"
FAILED = "failed"


@dataclass(frozen=True)
class ProbeResult:
    available: bool
    reason: str | None = None
    versions: dict = field(default_factory=dict)


class VectorBackend(Protocol):
    """The platform seam for local embeddings + a FAISS index."""

    def probe(self) -> ProbeResult:
        """Report whether faiss/numpy/model2vec can be used here, and why not."""

    def build(self, texts: list[str], index_path: str, *, model: str,
              batch_size: int, max_seq_length: int) -> int:
        """Embed ``texts``, write a cosine index to ``index_path``, return ntotal."""

    def count(self, index_path: str) -> int:
        """Re-open a written index and return its vector count (for verification)."""


@dataclass(frozen=True)
class VectorResult:
    status: str                       # built | skipped | disabled_by_user | failed
    model: str
    count: int = 0
    index_path: str | None = None     # bundle-relative, set only when built
    metadata_path: str | None = None  # bundle-relative
    metadata_format: str = "stub"     # json | jsonl | stub
    distance: str = DISTANCE
    reason: str | None = None

    @property
    def built(self) -> bool:
        return self.status == BUILT


def _embed_text(chunk: dict, max_chars: int) -> str:
    """The exact text embedded for a chunk: a context line (path + symbol +
    heading + docstring) followed by the chunk body, capped for the embedder."""
    ctx_line = " ".join(filter(None, [
        chunk.get("path"), chunk.get("symbol_name"),
        chunk.get("heading_path"), chunk.get("docstring")]))
    return (ctx_line + "\n" + chunk.get("text", ""))[:max_chars]


def _ordered_chunks(corpus: Corpus) -> list[dict]:
    """Stable chunk ordering for embedding + metadata (deterministic across runs)."""
    return sorted(
        corpus.chunks,
        key=lambda c: (c["path"], c["range"]["start_line"], c["chunk_id"]))


def _metadata_rows(chunks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for i, c in enumerate(chunks):
        rows.append({
            "ordinal": i,
            "chunk_id": c["chunk_id"],
            "span_ids": c.get("span_ids") or [],
            "path": c["path"],
            "range": {"start_line": c["range"]["start_line"],
                      "end_line": c["range"]["end_line"]},
            "language": c.get("language"),
            "category": c.get("category"),
            "sha256": c.get("sha256"),
        })
    return rows


def _cleanup_index_files(paths: "_Paths") -> None:
    """Remove the FAISS index, its atomic-write temp sibling, and any JSONL
    metadata so a skipped/failed/disabled vector lane never leaves an orphan that
    contradicts the capability contract (capabilities advertise vectors=false, so
    no index must remain on disk)."""
    for p in (paths.faiss, paths.faiss + ".tmp", paths.meta_jsonl):
        if os.path.exists(p):
            os.remove(p)


def _write_stub(opts: BuildOptions, status: str, reason: str | None) -> VectorResult:
    paths = _Paths(opts)
    _cleanup_index_files(paths)
    write_json(paths.meta_json, {
        "schema_version": SCHEMA_VERSION, "model": opts.embedding_model,
        "distance": DISTANCE, "status": status, "reason": reason,
        "count": 0, "vectors": [],
    })
    return VectorResult(
        status=status, model=opts.embedding_model, count=0,
        metadata_path=paths.rel(paths.meta_json), metadata_format="stub",
        reason=reason)


class _Paths:
    """Tiny adapter so this module reads the three vector paths off the bundle."""

    def __init__(self, opts: BuildOptions) -> None:
        from ..paths import Paths
        self._p = Paths(repo=opts.bundle_root, out=opts.bundle_root)

    @property
    def faiss(self) -> str:
        return self._p.vectors_faiss

    @property
    def meta_json(self) -> str:
        return self._p.vector_metadata

    @property
    def meta_jsonl(self) -> str:
        return self._p.vector_metadata_jsonl

    def rel(self, abspath: str) -> str:
        return self._p.rel(abspath)


def build_or_verify(corpus: Corpus, opts: BuildOptions,
                    backend: VectorBackend) -> VectorResult:
    """Build the vector index per ``opts.vectors_mode``; never raises on a normal
    skip/disable/failure — the runner maps a non-built result to PASS/FAIL."""
    paths = _Paths(opts)
    if opts.rebuild:
        _cleanup_index_files(paths)

    if opts.vectors_mode == "off":
        return _write_stub(opts, DISABLED, "disabled by user (--vectors off)")

    probe = backend.probe()
    if not probe.available:
        if opts.vectors_mode == "on":
            return _write_stub(
                opts, FAILED,
                f"vectors required (--vectors on) but unavailable: {probe.reason}")
        return _write_stub(opts, SKIPPED, probe.reason)

    ordered = _ordered_chunks(corpus)
    if not ordered:
        # No chunks to embed: do not advertise a vector capability with no index.
        return _write_stub(opts, SKIPPED, "no chunks to embed")
    rows = _metadata_rows(ordered)

    log(f"vectors: embedding {len(ordered)} chunks with {opts.embedding_model} ...")
    texts = [_embed_text(c, C.EMBED_TEXT_CHARS) for c in ordered]
    try:
        n_built = backend.build(
            texts, paths.faiss, model=opts.embedding_model,
            batch_size=opts.batch_size, max_seq_length=opts.max_seq_length)
        n_index = backend.count(paths.faiss)
    except Exception as e:  # noqa: BLE001 — any backend failure becomes a clean result
        return _write_stub(opts, FAILED, f"vector build failed: {type(e).__name__}: {e}")

    n_meta = len(rows)
    if not (n_built == n_index == n_meta):
        return _write_stub(
            opts, FAILED,
            f"vector/metadata count diverge: built={n_built} "
            f"index={n_index} metadata={n_meta}")

    if n_meta > opts.metadata_jsonl_threshold:
        write_jsonl(paths.meta_jsonl, rows)
        write_json(paths.meta_json, {
            "schema_version": SCHEMA_VERSION, "model": opts.embedding_model,
            "distance": DISTANCE, "count": n_meta, "format": "jsonl",
            "vectors_metadata_path": paths.rel(paths.meta_jsonl)})
        meta_path, meta_fmt = paths.rel(paths.meta_jsonl), "jsonl"
    else:
        if os.path.exists(paths.meta_jsonl):
            os.remove(paths.meta_jsonl)
        write_json(paths.meta_json, {
            "schema_version": SCHEMA_VERSION, "model": opts.embedding_model,
            "distance": DISTANCE, "count": n_meta, "vectors": rows})
        meta_path, meta_fmt = paths.rel(paths.meta_json), "json"

    return VectorResult(
        status=BUILT, model=opts.embedding_model, count=n_meta,
        index_path=paths.rel(paths.faiss), metadata_path=meta_path,
        metadata_format=meta_fmt)


class FaissModel2VecBackend:
    """Real backend: model2vec static embeddings + a FAISS ``IndexFlatIP`` (cosine
    over L2-normalized vectors). Heavy imports happen lazily inside methods."""

    def probe(self) -> ProbeResult:
        try:
            import faiss  # type: ignore
            import numpy  # type: ignore  # noqa: F401
            import model2vec  # type: ignore
        except Exception as e:  # noqa: BLE001 — report any import failure as a reason
            return ProbeResult(False, f"{type(e).__name__}: {e}")
        versions = {
            "faiss": getattr(faiss, "__version__", "unknown"),
            "model2vec": getattr(model2vec, "__version__", "unknown"),
        }
        return ProbeResult(True, None, versions)

    def build(self, texts: list[str], index_path: str, *, model: str,
              batch_size: int, max_seq_length: int) -> int:
        import faiss  # type: ignore
        import numpy as np  # type: ignore
        from model2vec import StaticModel  # type: ignore

        static = StaticModel.from_pretrained(model)
        parts = []
        for i in range(0, len(texts), batch_size):
            v = np.asarray(
                static.encode(texts[i:i + batch_size], max_length=max_seq_length),
                dtype="float32")
            norms = np.linalg.norm(v, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            parts.append(v / norms)
        mat = np.vstack(parts).astype("float32")
        index = faiss.IndexFlatIP(mat.shape[1])
        index.add(mat)
        os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
        # Write atomically: a temp sibling + os.replace, so an interrupted or
        # failed write never leaves a truncated index at the canonical path.
        tmp = index_path + ".tmp"
        faiss.write_index(index, tmp)
        os.replace(tmp, index_path)
        return int(index.ntotal)

    def count(self, index_path: str) -> int:
        import faiss  # type: ignore
        return int(faiss.read_index(index_path).ntotal)
