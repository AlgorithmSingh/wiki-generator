"""query_pack lane: canonical ripgrep packs -> source chunks/spans at each hit."""
from __future__ import annotations

from ..model import LaneResult, build_scores, chunk_hit, span_hit

LANE = "query_pack"


def run(bundle, section, options) -> LaneResult:
    needs = section.get("retrieval_needs") or {}
    packs = needs.get("query_packs") or []
    sid = section["section_id"]
    res = LaneResult(lane=LANE, requested=len(packs), resolved=0)
    rank = 0

    for i, pack in enumerate(packs):
        field = f"retrieval_needs.query_packs[{i}]"
        rows = bundle.rg_by_pack.get(pack, [])
        res.resolved += 1  # the pack key is already canonical from Phase 2.
        if not rows:
            res.unresolved.append({
                "section_id": sid, "type": "query_pack", "input": pack,
                "reason": "no_hits", "source_field": field, "candidates": [],
            })
            continue
        for row in rows[:options.max_per_lane]:
            path, line = row.get("path"), row.get("line")
            if path is None or line is None:
                continue
            prov = {"section_plan_field": field, "input": pack,
                    "matched_by": "query_pack", "pack": pack, "why": row.get("why"),
                    "matched_line": line, "matched_text": row.get("text"),
                    "rule_path": f"queries/rules/rg/{pack}.json"}
            scores = build_scores(lane_rank=None)
            chunks = bundle.overlapping_chunks(path, line, line, 1)
            spans = bundle.overlapping_spans(path, line, line, 1)
            if chunks:
                rank += 1
                scores = build_scores(lane_rank=rank)
                res.hits.append(chunk_hit(chunks[0], lane=LANE, confidence="medium",
                                          lane_rank=rank, provenance=prov, scores=scores))
            if spans:
                rank += 1
                res.hits.append(span_hit(spans[0], lane=LANE, confidence="medium",
                                         lane_rank=rank, provenance=prov,
                                         scores=build_scores(lane_rank=rank)))
            if not chunks and not spans:
                res.unresolved.append({
                    "section_id": sid, "type": "query_pack", "input": pack,
                    "reason": "no_hits", "source_field": field,
                    "candidates": [f"{path}:{line}"],
                })

    res.status = ("not_requested" if res.requested == 0
                  else "pass" if res.hits else "miss")
    return res
