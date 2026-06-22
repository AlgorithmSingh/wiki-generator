"""Internal retrieval model: raw hits, lane results, and hit builders.

Lanes produce ``RawHit`` candidates; ``aggregate`` merges/sorts/caps them into
final evidence items. Nothing here is written to disk verbatim — the on-disk
shapes are assembled in ``writer`` from the aggregated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..util import clip
from .schema import EVIDENCE_EXCERPT_CHARS

# Lane priority order (spec "Aggregation, dedupe, and ranking" step 4).
LANES = (
    "file_anchor", "symbol_anchor", "contract", "test",
    "query_pack", "graph_neighbors", "bm25", "vector",
)
LANE_PRIORITY = {lane: i for i, lane in enumerate(LANES)}

# Confidence rank: exact strongest.
CONFIDENCE = ("exact", "high", "medium", "low")
CONFIDENCE_RANK = {c: i for i, c in enumerate(CONFIDENCE)}


@dataclass
class RawHit:
    """One pre-aggregation evidence candidate from a single lane."""

    lane: str
    type: str                       # source_span | source_chunk | route_operation | ...
    source: dict
    excerpt: str
    confidence: str
    provenance: dict
    scores: dict
    dedupe_key: str
    coarse_key: str                 # path:start-end (or a lane-unique key) for span/chunk folding
    is_span: bool
    lane_rank: int | None = None

    def sort_key(self) -> tuple:
        path = self.source.get("path") or ""
        rng = self.source.get("range") or {}
        start = rng.get("start_line", 0)
        anchor = (self.source.get("span_id") or self.source.get("chunk_id")
                  or self.source.get("json_pointer") or "")
        return (
            CONFIDENCE_RANK.get(self.confidence, len(CONFIDENCE)),
            LANE_PRIORITY.get(self.lane, len(LANES)),
            self.lane_rank if self.lane_rank is not None else 1_000_000,
            path,
            start,
            anchor,
            # Final total tiebreak (spec ranking step 4): dedupe_key is unique per
            # surviving rep after exact dedupe, so the order is fully determined
            # without relying on stable-sort + input order.
            self.dedupe_key,
        )


@dataclass
class LaneResult:
    """What one lane produced for one section."""

    lane: str
    requested: int               # plan work items (or 1 for an active recall lane)
    resolved: int                # work items that resolved to a usable reference
    hits: list[RawHit] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    status: str = "not_requested"


def build_scores(*, lane_rank=None, lane_score=None, bm25=None, vector=None) -> dict:
    return {"lane_rank": lane_rank, "lane_score": lane_score,
            "bm25": bm25, "vector": vector}


def _excerpt(text) -> str:
    return clip(text or "", EVIDENCE_EXCERPT_CHARS)


def span_hit(span: dict, *, lane: str, confidence: str, provenance: dict,
             lane_rank: int | None = None, scores: dict | None = None) -> RawHit:
    """Build a RawHit from a ``rag/spans.jsonl`` row."""
    path = span["path"]
    rng = span["range"]
    s, e = rng["start_line"], rng["end_line"]
    sid = span["span_id"]
    source = {
        "artifact": "rag/spans.jsonl",
        "path": path,
        "range": {"start_line": s, "end_line": e},
        "span_id": sid,
    }
    if span.get("symbol_id"):
        source["symbol_id"] = span["symbol_id"]
    return RawHit(
        lane=lane, type="source_span", source=source,
        excerpt=_excerpt(span.get("text")), confidence=confidence,
        provenance=provenance,
        scores=scores or build_scores(lane_rank=lane_rank),
        dedupe_key=f"{path}:{s}-{e}|span:{sid}",
        coarse_key=f"{path}:{s}-{e}", is_span=True, lane_rank=lane_rank,
    )


def chunk_hit(chunk: dict, *, lane: str, confidence: str, provenance: dict,
              lane_rank: int | None = None, scores: dict | None = None) -> RawHit:
    """Build a RawHit from a ``rag/chunks.jsonl`` row."""
    path = chunk["path"]
    rng = chunk["range"]
    s, e = rng["start_line"], rng["end_line"]
    cid = chunk["chunk_id"]
    source = {
        "artifact": "rag/chunks.jsonl",
        "path": path,
        "range": {"start_line": s, "end_line": e},
        "chunk_id": cid,
    }
    if chunk.get("span_ids"):
        source["span_ids"] = list(chunk["span_ids"])
    if chunk.get("symbol_name"):
        source["symbol_name"] = chunk["symbol_name"]
    return RawHit(
        lane=lane, type="source_chunk", source=source,
        excerpt=_excerpt(chunk.get("text")), confidence=confidence,
        provenance=provenance,
        scores=scores or build_scores(lane_rank=lane_rank),
        dedupe_key=f"{path}:{s}-{e}|chunk:{cid}",
        coarse_key=f"{path}:{s}-{e}", is_span=False, lane_rank=lane_rank,
    )
