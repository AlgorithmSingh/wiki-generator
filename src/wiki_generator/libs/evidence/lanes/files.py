"""file_anchor lane: resolved file references -> exact source ranges/chunks."""
from __future__ import annotations

from ..model import LaneResult, chunk_hit, span_hit

LANE = "file_anchor"
_RESOLVED = {"file_exists", "unique_suffix", "digest_artifact"}


def _parse_anchor(anchor):
    """Parse a numeric anchor ('120-145' or '42') into (start, end) or None."""
    if not anchor:
        return None
    text = str(anchor).strip()
    if "-" in text:
        a, _, b = text.partition("-")
        a, b = a.strip(), b.strip()
        if a.isdigit() and b.isdigit():
            s, e = int(a), int(b)
            return (s, e) if e >= s else (e, s)
        return None
    return (int(text), int(text)) if text.isdigit() else None


def run(bundle, section, options) -> LaneResult:
    needs = section.get("retrieval_needs") or {}
    files = needs.get("files") or []
    sid = section["section_id"]
    res = LaneResult(lane=LANE, requested=len(files), resolved=0)
    rank = 0

    for i, item in enumerate(files):
        field = f"retrieval_needs.files[{i}]"
        path = item.get("path")
        resolution = item.get("resolution")
        if path is None or resolution not in _RESOLVED:
            res.unresolved.append({
                "section_id": sid, "type": "file", "input": item.get("input"),
                "reason": "ambiguous" if resolution == "ambiguous" else "missing_reference",
                "source_field": field, "candidates": item.get("candidates") or [],
            })
            continue
        res.resolved += 1

        ac = item.get("anchor_confidence")
        parsed = _parse_anchor(item.get("anchor"))
        cap = options.max_per_lane
        before = rank

        if ac in ("exact_range", "line_only") and parsed:
            start, end = parsed
            for span in bundle.overlapping_spans(path, start, end, cap):
                rank += 1
                res.hits.append(span_hit(
                    span, lane=LANE, confidence="exact", lane_rank=rank,
                    provenance={"section_plan_field": field, "input": item.get("input"),
                                "matched_by": "file_range", "anchor": item.get("anchor")}))
            for chunk in bundle.overlapping_chunks(path, start, end, cap):
                rank += 1
                res.hits.append(chunk_hit(
                    chunk, lane=LANE, confidence="high", lane_rank=rank,
                    provenance={"section_plan_field": field, "input": item.get("input"),
                                "matched_by": "file_range", "anchor": item.get("anchor")}))
        else:
            # file_only / no anchor / loose heading hint -> representative chunks.
            if parsed is not None:
                # A numeric anchor that the normalizer demoted to file_only means the
                # range was invalid for the file; record it but still ground the file.
                res.unresolved.append({
                    "section_id": sid, "type": "file", "input": item.get("input"),
                    "reason": "invalid_range", "source_field": field, "candidates": [],
                })
            for chunk in bundle.file_repr_chunks(path, cap):
                rank += 1
                res.hits.append(chunk_hit(
                    chunk, lane=LANE, confidence="high", lane_rank=rank,
                    provenance={"section_plan_field": field, "input": item.get("input"),
                                "matched_by": "file_repr", "anchor": item.get("anchor")}))

        if rank == before:
            # Resolved path but the rag corpus has no chunk for it (stale/empty file).
            res.unresolved.append({
                "section_id": sid, "type": "file", "input": item.get("input"),
                "reason": "no_hits", "source_field": field, "candidates": [],
            })

    res.status = _status(res)
    return res


def _status(res: LaneResult) -> str:
    if res.requested == 0:
        return "not_requested"
    if res.hits:
        return "pass"
    return "miss"
