"""Load the Phase 1/2 bundle and build deterministic in-memory lookup maps.

Anything wrong with the *inputs* (missing/corrupt/inconsistent artifacts, or a
capability that promises a lane whose artifact is absent) raises
``BadInputArtifact`` — the command maps that to exit code 2. Plan-quality and
retriever-bug problems are detected later, against a successfully loaded bundle.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .. import util
from ..paths import Paths
from ..retrieval import bm25 as bm25_lib


class BadInputArtifact(Exception):
    """A required bundle/substrate artifact is missing, corrupt, or inconsistent."""


# --- small typed readers ------------------------------------------------------
def _read_json(path: str, label: str):
    if not os.path.isfile(path):
        raise BadInputArtifact(f"missing required artifact: {label} ({path})")
    try:
        return util.read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        raise BadInputArtifact(f"invalid JSON in {label}: {e}") from e


def _read_jsonl(path: str, label: str, *, required: bool) -> tuple[list[dict], list[str]]:
    """Return (parsed rows, raw stripped lines). Missing optional file -> empty."""
    if not os.path.isfile(path):
        if required:
            raise BadInputArtifact(f"missing required artifact: {label} ({path})")
        return [], []
    rows: list[dict] = []
    raw: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise BadInputArtifact(
                        f"invalid JSONL in {label} line {n}: {e}") from e
                raw.append(line)
    except OSError as e:
        raise BadInputArtifact(f"cannot read {label}: {e}") from e
    return rows, raw


@dataclass
class Bundle:
    """A loaded, validated bundle with retrieval lookup maps."""

    root: str
    paths: Paths
    document_plan: dict
    section_order: list[str]
    section_by_id: dict
    section_raw_by_id: dict          # section_id -> raw jsonl line (for sha256)
    capabilities: dict
    retrieval_mode: str
    caps: dict

    # lookup maps
    chunks_by_id: dict = field(default_factory=dict)
    spans_by_id: dict = field(default_factory=dict)
    symbols_by_id: dict = field(default_factory=dict)
    symbols_by_parent: dict = field(default_factory=dict)
    files_by_path: dict = field(default_factory=dict)
    chunks_by_path: dict = field(default_factory=dict)
    spans_by_path: dict = field(default_factory=dict)
    rg_by_pack: dict = field(default_factory=dict)
    nodes_by_id: dict = field(default_factory=dict)
    edges_by_src: dict = field(default_factory=dict)
    edges_by_dst: dict = field(default_factory=dict)
    openapi: dict | None = None
    test_files_by_path: dict = field(default_factory=dict)
    pytest_collect_lines: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    # -- capability helpers ----------------------------------------------------
    def cap(self, name: str) -> bool:
        return bool(self.caps.get(name))

    # -- single-id lookups -----------------------------------------------------
    def chunk(self, chunk_id):
        return self.chunks_by_id.get(chunk_id)

    def span(self, span_id):
        return self.spans_by_id.get(span_id)

    def symbol(self, symbol_id):
        return self.symbols_by_id.get(symbol_id)

    def node(self, node_id):
        return self.nodes_by_id.get(node_id)

    def out_edges(self, node_id):
        return self.edges_by_src.get(node_id, [])

    def in_edges(self, node_id):
        return self.edges_by_dst.get(node_id, [])

    # -- range/overlap lookups (deterministic ordering) ------------------------
    def overlapping_chunks(self, path, start, end, cap):
        rows = self.chunks_by_path.get(path, [])
        hits = [c for c in rows
                if c["range"]["start_line"] <= end and start <= c["range"]["end_line"]]
        return hits[:cap]

    def overlapping_spans(self, path, start, end, cap):
        rows = self.spans_by_path.get(path, [])
        hits = [s for s in rows
                if s["range"]["start_line"] <= end and start <= s["range"]["end_line"]]
        return hits[:cap]

    def file_repr_chunks(self, path, cap):
        return self.chunks_by_path.get(path, [])[:cap]

    def children_of(self, symbol_id):
        return self.symbols_by_parent.get(symbol_id, [])


def _check_no_dupes(rows, id_key, label):
    seen = set()
    for r in rows:
        k = r.get(id_key)
        if k in seen:
            raise BadInputArtifact(f"duplicate {id_key} in {label}: {k}")
        seen.add(k)


def load_bundle(options) -> Bundle:
    """Load and validate every artifact Phase 3 consumes. May raise BadInputArtifact."""
    root = options.bundle_root
    paths = Paths(repo=root, out=root)

    # --- normalized plan (required) ------------------------------------------
    doc = _read_json(paths.f("plans", "document-plan.json"), "plans/document-plan.json")
    section_order = doc.get("section_order")
    if not isinstance(section_order, list) or not section_order:
        raise BadInputArtifact(
            "plans/document-plan.json has no non-empty 'section_order'")

    sec_rows, sec_raw = _read_jsonl(
        paths.f("plans", "section-plans.jsonl"), "plans/section-plans.jsonl",
        required=True)
    section_by_id: dict = {}
    section_raw_by_id: dict = {}
    for row, raw in zip(sec_rows, sec_raw):
        sid = row.get("section_id")
        if sid is None:
            raise BadInputArtifact("section-plans.jsonl row missing 'section_id'")
        section_by_id[sid] = row
        section_raw_by_id[sid] = raw

    # --- capabilities (required) ---------------------------------------------
    caps_doc = _read_json(paths.retrieval_capabilities, "rag/retrieval-capabilities.json")
    caps = caps_doc.get("capabilities") or {}
    retrieval_mode = caps_doc.get("retrieval_mode") or "lexical-symbolic"
    indexes = caps_doc.get("indexes") or {}
    if retrieval_mode not in ("hybrid", "lexical-symbolic"):
        raise BadInputArtifact(
            f"unknown retrieval_mode in capabilities: {retrieval_mode!r}")
    if (retrieval_mode == "hybrid") != bool(caps.get("vectors")):
        raise BadInputArtifact(
            f"capabilities inconsistent: retrieval_mode={retrieval_mode} but "
            f"capabilities.vectors={bool(caps.get('vectors'))}")

    # --- rag corpus (required) -----------------------------------------------
    chunks, _ = _read_jsonl(paths.chunks_jsonl, "rag/chunks.jsonl", required=True)
    spans, _ = _read_jsonl(paths.spans_jsonl, "rag/spans.jsonl", required=True)
    if not chunks:
        raise BadInputArtifact("rag/chunks.jsonl is empty")
    if not spans:
        raise BadInputArtifact("rag/spans.jsonl is empty")
    # Duplicate ids make the bundle inconsistent (last-wins would hide a row and
    # could misclassify a dangling anchor as a retriever bug). Hard-stop as bad input.
    _check_no_dupes(chunks, "chunk_id", "rag/chunks.jsonl")
    _check_no_dupes(spans, "span_id", "rag/spans.jsonl")

    b = Bundle(
        root=root, paths=paths, document_plan=doc, section_order=list(section_order),
        section_by_id=section_by_id, section_raw_by_id=section_raw_by_id,
        capabilities=caps_doc, retrieval_mode=retrieval_mode, caps=caps,
    )

    # corpus maps
    b.chunks_by_id = {c["chunk_id"]: c for c in chunks}
    b.spans_by_id = {s["span_id"]: s for s in spans}
    b.chunks_by_path = _group_sorted(chunks, key=lambda c: (c["range"]["start_line"],
                                                            c["chunk_id"]))
    b.spans_by_path = _group_sorted(spans, key=lambda s: (s["range"]["start_line"],
                                                          s.get("span_type") or "",
                                                          s["span_id"]))

    # --- bm25 substrate -------------------------------------------------------
    if caps.get("bm25"):
        if bm25_lib.read_index_state(paths.bm25_sqlite) is None:
            raise BadInputArtifact(
                "capabilities.bm25 is true but rag/bm25.sqlite is missing or unreadable")

    # --- vector substrate -----------------------------------------------------
    if caps.get("vectors"):
        _validate_vectors(paths, indexes.get("vectors") or {})

    # --- lookup inputs (gated by capability flags) ---------------------------
    files = _load_lookup_jsonl(b, paths.files_jsonl, "inventory/files.jsonl",
                               required_cap="file_lookup")
    b.files_by_path = {f["path"]: f for f in files}

    symbols = _load_lookup_jsonl(b, paths.symbols_jsonl, "symbols/symbols.jsonl",
                                 required_cap="symbol_lookup")
    _check_no_dupes(symbols, "symbol_id", "symbols/symbols.jsonl")
    b.symbols_by_id = {s["symbol_id"]: s for s in symbols}
    b.symbols_by_parent = _group_sorted(
        [s for s in symbols if s.get("parent_symbol_id")],
        key_field="parent_symbol_id", sort=lambda s: (s["range"]["start_line"],
                                                      s["symbol_id"]))

    nodes = _load_lookup_jsonl(b, paths.nodes_jsonl, "static/nodes.jsonl",
                               required_cap="static_graph")
    b.nodes_by_id = {n["node_id"]: n for n in nodes}
    edges = _load_lookup_jsonl(b, paths.edges_jsonl, "static/edges.jsonl",
                               required_cap="static_graph")
    b.edges_by_src = _group_sorted(edges, key_field="src",
                                   sort=lambda e: (e.get("type") or "", e["dst"]))
    b.edges_by_dst = _group_sorted(edges, key_field="dst",
                                   sort=lambda e: (e.get("type") or "", e["src"]))

    rg = _load_lookup_jsonl(b, paths.rg_jsonl, "queries/results/rg.jsonl",
                            required_cap="query_packs")
    b.rg_by_pack = _group_sorted(rg, key_field="pack",
                                 sort=lambda r: (r.get("path") or "",
                                                 r.get("line") or 0,
                                                 r.get("text") or ""))

    if caps.get("contracts") and not os.path.isfile(paths.openapi_json):
        raise BadInputArtifact(
            "capabilities.contracts is true but contracts/openapi.json is missing")
    if os.path.isfile(paths.openapi_json):
        b.openapi = _read_json(paths.openapi_json, "contracts/openapi.json")

    test_files = _load_lookup_jsonl(b, paths.test_files_jsonl, "tests/test-files.jsonl",
                                    required_cap="tests")
    b.test_files_by_path = {t["path"]: t for t in test_files}

    collect_txt = util.read_text(paths.pytest_collect)
    b.pytest_collect_lines = collect_txt.splitlines() if collect_txt else []

    return b


def _group_sorted(rows, *, key=None, key_field=None, sort=None) -> dict:
    """Group rows into ``{path-or-field: [rows]}`` with a stable per-bucket sort.

    Either pass ``key`` (a function on a chunk/span row keyed by its ``path``)
    or ``key_field``+``sort`` (group by ``row[key_field]``, sort by ``sort``).
    """
    out: dict = {}
    if key_field is not None:
        for r in rows:
            out.setdefault(r.get(key_field), []).append(r)
        for k in out:
            out[k].sort(key=sort)
        return out
    for r in rows:
        out.setdefault(r["path"], []).append(r)
    for k in out:
        out[k].sort(key=key)
    return out


def _load_lookup_jsonl(b: Bundle, path: str, label: str, *, required_cap: str) -> list:
    required = bool(b.caps.get(required_cap))
    rows, _ = _read_jsonl(path, label, required=required)
    return rows


def _validate_vectors(paths: Paths, vmeta: dict) -> None:
    """Vectors enabled => index + metadata must exist and counts must agree.

    The FAISS ``ntotal`` check needs faiss; when it is importable we enforce the
    full built==index==metadata triple, otherwise we still enforce the
    metadata-vs-capability count so a stale metadata file is rejected.
    """
    if not os.path.isfile(paths.vectors_faiss):
        raise BadInputArtifact(
            "capabilities.vectors is true but rag/vectors.faiss is missing")

    fmt = vmeta.get("metadata_format")
    declared = vmeta.get("row_count")
    meta_count = _count_vector_metadata(paths, fmt)
    if meta_count is None:
        raise BadInputArtifact(
            "capabilities.vectors is true but vector metadata is missing/unreadable")
    if declared is not None and meta_count != declared:
        raise BadInputArtifact(
            f"vector metadata count diverges: capabilities={declared} "
            f"metadata={meta_count}")

    try:
        import faiss  # type: ignore
    except Exception:
        return
    try:
        ntotal = int(faiss.read_index(paths.vectors_faiss).ntotal)
    except Exception as e:
        raise BadInputArtifact(f"cannot read rag/vectors.faiss: {e}") from e
    if ntotal != meta_count:
        raise BadInputArtifact(
            f"vector count diverges: faiss={ntotal} metadata={meta_count}")


def _count_vector_metadata(paths: Paths, fmt) -> int | None:
    """Number of metadata rows on disk, honoring the json/jsonl form."""
    if fmt == "jsonl" or (fmt is None and os.path.isfile(paths.vector_metadata_jsonl)):
        if not os.path.isfile(paths.vector_metadata_jsonl):
            return None
        n = 0
        with open(paths.vector_metadata_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n
    if not os.path.isfile(paths.vector_metadata):
        return None
    try:
        doc = util.read_json(paths.vector_metadata)
    except (OSError, ValueError):
        return None
    if isinstance(doc.get("vectors"), list):
        return len(doc["vectors"])
    return doc.get("count")


def load_vector_metadata(paths: Paths, fmt) -> list[dict]:
    """Return metadata rows ordered by ``ordinal`` (== FAISS ordinal)."""
    rows: list[dict] = []
    if fmt == "jsonl" or (fmt is None and os.path.isfile(paths.vector_metadata_jsonl)):
        with open(paths.vector_metadata_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    else:
        doc = util.read_json(paths.vector_metadata)
        rows = list(doc.get("vectors") or [])
    rows.sort(key=lambda r: r.get("ordinal", 0))
    return rows
