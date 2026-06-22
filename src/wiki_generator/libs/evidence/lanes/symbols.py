"""symbol_anchor lane: resolved symbol_ids -> symbol span + overlapping chunks.

For a class symbol the header span comes first, then its child method spans (so
they rank above the bulk overlapping chunks and survive the per-lane cap), then
overlapping chunks for surrounding context.
"""
from __future__ import annotations

from ..model import LaneResult, chunk_hit, span_hit

LANE = "symbol_anchor"
_RESOLVED = {"exact", "unique_alias"}


def _symbol_span(bundle, symbol):
    """The symbol's own span row, or a span-shaped fallback from its range."""
    span_id = symbol.get("span_id")
    span = bundle.span(span_id) if span_id else None
    if span is not None:
        return span
    return {"span_id": span_id or f"span:{symbol['path']}:"
            f"{symbol['range']['start_line']}-{symbol['range']['end_line']}:symbol",
            "path": symbol["path"], "range": symbol["range"],
            "symbol_id": symbol["symbol_id"],
            "text": symbol.get("signature") or symbol.get("name") or ""}


def run(bundle, section, options) -> LaneResult:
    needs = section.get("retrieval_needs") or {}
    symbols = needs.get("symbols") or []
    sid = section["section_id"]
    res = LaneResult(lane=LANE, requested=len(symbols), resolved=0)
    rank = 0

    for i, item in enumerate(symbols):
        field = f"retrieval_needs.symbols[{i}]"
        resolution = item.get("resolution")
        symbol_id = item.get("symbol_id")
        if resolution not in _RESOLVED or not symbol_id:
            res.unresolved.append({
                "section_id": sid, "type": "symbol", "input": item.get("input"),
                "reason": "ambiguous" if resolution == "ambiguous" else "missing_reference",
                "source_field": field, "candidates": item.get("candidates") or [],
            })
            continue
        symbol = bundle.symbol(symbol_id)
        if symbol is None:
            res.unresolved.append({
                "section_id": sid, "type": "symbol", "input": item.get("input"),
                "reason": "missing_reference", "source_field": field, "candidates": [],
            })
            continue
        res.resolved += 1
        prov = {"section_plan_field": field, "input": item.get("input"),
                "matched_by": "symbol_id", "symbol_id": symbol_id}

        # 1. the symbol's own span (exact).
        rank += 1
        res.hits.append(span_hit(_symbol_span(bundle, symbol), lane=LANE,
                                 confidence="exact", lane_rank=rank, provenance=prov))

        # 2. class child-method spans (high), before bulk chunks so they survive caps.
        if symbol.get("kind") == "class":
            for child in bundle.children_of(symbol_id)[:options.max_per_lane]:
                child_span = bundle.span(child.get("span_id"))
                if child_span is None:
                    continue
                rank += 1
                res.hits.append(span_hit(
                    child_span, lane=LANE, confidence="high", lane_rank=rank,
                    provenance={"section_plan_field": field, "input": item.get("input"),
                                "matched_by": "class_member",
                                "symbol_id": child["symbol_id"]}))

        # 3. overlapping chunks for surrounding context (high).
        r = symbol["range"]
        for chunk in bundle.overlapping_chunks(symbol["path"], r["start_line"],
                                               r["end_line"], options.max_per_lane):
            rank += 1
            res.hits.append(chunk_hit(chunk, lane=LANE, confidence="high",
                                      lane_rank=rank, provenance=prov))

    res.status = ("not_requested" if res.requested == 0
                  else "pass" if res.hits else "miss")
    return res
