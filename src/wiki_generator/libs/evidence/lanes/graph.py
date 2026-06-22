"""graph_neighbors lane: one-hop static-graph expansion -> recovered source."""
from __future__ import annotations

from ..model import LaneResult, chunk_hit, span_hit

LANE = "graph_neighbors"
# Edge types that explain local structure (spec "Graph neighbors").
_PREFERRED = ("CONTAINS", "IMPORTS", "INHERITS", "DECORATED_BY",
              "CALLS_APPROX", "TESTS_APPROX", "MENTIONS")
_FILE_NODES = {"File", "Test", "ConfigFile", "Module"}


def _seeds(bundle, section):
    """Ordered, de-duped (node_id, source_field, input) seeds for graph expansion."""
    needs = section.get("retrieval_needs") or {}
    seen: set = set()
    seeds: list = []
    explicit: list = []

    def add(node_id, field, value):
        if node_id and node_id not in seen:
            seen.add(node_id)
            seeds.append((node_id, field, value))

    for i, g in enumerate(needs.get("graph_nodes") or []):
        field = f"retrieval_needs.graph_nodes[{i}]"
        candidates = [g, f"sym:{g}", f"file:{g}"]
        found = next((c for c in candidates if bundle.node(c)), None)
        explicit.append((g, field, found))
        add(found or g, field, g)
    for i, s in enumerate(needs.get("symbols") or []):
        if s.get("resolution") in ("exact", "unique_alias") and s.get("symbol_id"):
            add(f"sym:{s['symbol_id']}", f"retrieval_needs.symbols[{i}]", s.get("input"))
    for i, f in enumerate(needs.get("files") or []):
        if f.get("path") and f.get("resolution") in (
                "file_exists", "unique_suffix", "digest_artifact"):
            add(f"file:{f['path']}", f"retrieval_needs.files[{i}]", f.get("input"))
    return seeds, explicit


def _neighbors(bundle, node_id):
    """Sorted (edge, neighbor_node_id) one hop away over preferred edge types."""
    out = []
    for e in bundle.out_edges(node_id):
        if e.get("type") in _PREFERRED:
            out.append((e, e["dst"]))
    for e in bundle.in_edges(node_id):
        if e.get("type") in _PREFERRED:
            out.append((e, e["src"]))
    out.sort(key=lambda ev: (_PREFERRED.index(ev[0]["type"]), ev[1]))
    return out


def _recover(bundle, node, *, lane_rank, confidence, prov):
    """Turn a neighbor node into a source span/chunk hit, or None if external."""
    if node.get("symbol_id"):
        sym = bundle.symbol(node["symbol_id"])
        if sym and sym.get("span_id") and bundle.span(sym["span_id"]):
            return span_hit(bundle.span(sym["span_id"]), lane=LANE,
                            confidence=confidence, lane_rank=lane_rank, provenance=prov)
    if node.get("type") in _FILE_NODES and node.get("path"):
        chunks = bundle.file_repr_chunks(node["path"], 1)
        if chunks:
            return chunk_hit(chunks[0], lane=LANE, confidence=confidence,
                             lane_rank=lane_rank, provenance=prov)
    if node.get("type") == "DocSection" and node.get("path") and node.get("range"):
        r = node["range"]
        chunks = bundle.overlapping_chunks(node["path"], r["start_line"],
                                           r["end_line"], 1)
        if chunks:
            return chunk_hit(chunks[0], lane=LANE, confidence=confidence,
                             lane_rank=lane_rank, provenance=prov)
    return None


def run(bundle, section, options) -> LaneResult:
    sid = section["section_id"]
    seeds, explicit = _seeds(bundle, section)
    res = LaneResult(lane=LANE, requested=len(seeds), resolved=0)
    rank = 0

    for node_id, field, value in seeds:
        seed_node = bundle.node(node_id)
        if seed_node is None:
            continue
        res.resolved += 1
        for edge, neighbor_id in _neighbors(bundle, node_id)[:options.max_per_lane]:
            neighbor = bundle.node(neighbor_id)
            if neighbor is None:
                continue
            confidence = "medium" if edge.get("basis") == "observed" else "low"
            prov = {"section_plan_field": field, "input": value,
                    "matched_by": "graph_edge", "edge_type": edge.get("type"),
                    "seed_node": node_id, "neighbor_node": neighbor_id,
                    "basis": edge.get("basis")}
            hit = _recover(bundle, neighbor, lane_rank=rank + 1,
                           confidence=confidence, prov=prov)
            if hit is not None:
                rank += 1
                res.hits.append(hit)

    for g, field, found in explicit:
        if found is None:
            res.unresolved.append({
                "section_id": sid, "type": "graph", "input": g,
                "reason": "missing_reference", "source_field": field, "candidates": [],
            })

    res.status = ("not_requested" if res.requested == 0
                  else "pass" if res.hits else "miss")
    return res
