"""bm25 lane: deterministic lexical recall over rag/bm25.sqlite."""
from __future__ import annotations

from ...util import clip
from ...retrieval import bm25 as bm25_lib
from ..model import LaneResult, build_scores, chunk_hit
from ..query_text import build_query_text

LANE = "bm25"


def run(bundle, section, options) -> LaneResult:
    if not bundle.caps.get("bm25"):
        return LaneResult(lane=LANE, requested=0, resolved=0,
                          status="capability_disabled")

    query = build_query_text(section)
    res = LaneResult(lane=LANE, requested=1, resolved=0)
    if not query.strip():
        res.status = "empty"
        return res

    hits = bm25_lib.search(bundle.paths.bm25_sqlite, query, k=options.max_per_lane)
    query_label = clip(query, 200)
    for rank, hit in enumerate(hits, 1):
        chunk = bundle.chunk(hit.chunk_id)
        if chunk is None:
            continue
        score = round(float(hit.score), 6)
        res.hits.append(chunk_hit(
            chunk, lane=LANE, confidence="medium", lane_rank=rank,
            provenance={"section_plan_field": "query_text", "input": query_label,
                        "matched_by": "bm25"},
            scores=build_scores(lane_rank=rank, lane_score=score, bm25=score)))

    res.resolved = 1 if res.hits else 0
    res.status = "pass" if res.hits else "empty"
    return res
