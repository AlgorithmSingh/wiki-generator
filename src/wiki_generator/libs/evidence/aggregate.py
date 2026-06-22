"""Merge lane outputs into final, deterministically ordered evidence items.

Pipeline (spec "Aggregation, dedupe, and ranking"):
1. exact dedupe by ``dedupe_key`` (keep all provenance, one item);
2. prefer an exact source span over a chunk describing the same range;
3. sort by confidence, lane priority, lane rank, path, start_line, anchor;
4. apply per-lane and per-section caps after sorting;
5. assign final ``evidence_id`` values from the sorted, capped list.
"""
from __future__ import annotations

from .model import CONFIDENCE_RANK, LANE_PRIORITY

# Display order for lane_summary (spec EvidencePacket example).
LANE_SUMMARY_ORDER = (
    "file_anchor", "symbol_anchor", "query_pack", "contract", "test",
    "graph_neighbors", "bm25", "vector",
)
EXPECTED_LABEL_TO_LANE = {
    "files": "file_anchor", "symbols": "symbol_anchor", "queries": "query_pack",
    "contracts": "contract", "tests": "test", "graph": "graph_neighbors",
}


def _init_merge(hit) -> None:
    hit.lanes = [hit.lane]
    hit.merged_provenance = [hit.provenance]


def _merge_scores(target, other) -> None:
    for k in ("bm25", "vector"):
        if target.scores.get(k) is None and other.scores.get(k) is not None:
            target.scores[k] = other.scores[k]


def _fold(target, other) -> None:
    """Fold ``other`` (a duplicate / superseded hit) into ``target``.

    The surviving item keeps ``target``'s anchor (e.g. a span over a chunk for the
    same range) but is upgraded to the *strongest* member's confidence and
    highest-priority lane, so a high/exact anchor chunk is never demoted into a
    weaker lane's span (spec: "Exact anchor lanes should not be pushed out").
    """
    for lane in other.lanes:
        if lane not in target.lanes:
            target.lanes.append(lane)
    if CONFIDENCE_RANK.get(other.confidence, 99) < CONFIDENCE_RANK.get(target.confidence, 99):
        target.confidence = other.confidence
    if LANE_PRIORITY.get(other.lane, 99) < LANE_PRIORITY.get(target.lane, 99):
        # other wins primary attribution -> its provenance leads.
        target.lane = other.lane
        target.lane_rank = other.lane_rank
        target.merged_provenance = other.merged_provenance + target.merged_provenance
    else:
        target.merged_provenance.extend(other.merged_provenance)
    _merge_scores(target, other)


def _exact_dedupe(hits):
    groups: dict = {}
    order: list = []
    for h in hits:
        _init_merge(h)
        if h.dedupe_key not in groups:
            groups[h.dedupe_key] = []
            order.append(h.dedupe_key)
        groups[h.dedupe_key].append(h)
    reps = []
    for key in order:
        members = groups[key]
        rep = min(members, key=lambda h: h.sort_key())
        for m in members:
            if m is not rep:
                _fold(rep, m)
        reps.append(rep)
    return reps


def _prefer_span(reps):
    by_coarse: dict = {}
    for h in reps:
        by_coarse.setdefault(h.coarse_key, []).append(h)
    dropped: set = set()
    for group in by_coarse.values():
        spans = [h for h in group if h.is_span]
        chunks = [h for h in group if not h.is_span]
        if spans and chunks:
            target = min(spans, key=lambda h: h.sort_key())
            for c in chunks:
                _fold(target, c)
                dropped.add(id(c))
    return [h for h in reps if id(h) not in dropped]


def _provenance(hit) -> dict:
    primary = dict(hit.merged_provenance[0])
    if len(hit.merged_provenance) > 1:
        primary["additional"] = hit.merged_provenance[1:]
    if len(hit.lanes) > 1:
        primary["lanes"] = list(hit.lanes)
    return primary


def _to_item(evidence_id, hit) -> dict:
    item = {
        "evidence_id": evidence_id,
        "lane": hit.lane,
        "type": hit.type,
        "source": hit.source,
        "excerpt": hit.excerpt,
        "provenance": _provenance(hit),
        "scores": hit.scores,
        "confidence": hit.confidence,
        "dedupe_key": hit.dedupe_key,
    }
    return item


def aggregate(section_id, lane_results, options):
    """Return (evidence_items, lane_summary, lanes_present_set)."""
    hits = []
    for lr in lane_results:
        hits.extend(lr.hits)

    reps = _prefer_span(_exact_dedupe(hits))
    reps.sort(key=lambda h: h.sort_key())

    kept = []
    per_lane: dict = {}
    for h in reps:
        if len(kept) >= options.max_total_per_section:
            break
        if per_lane.get(h.lane, 0) >= options.max_per_lane:
            continue
        per_lane[h.lane] = per_lane.get(h.lane, 0) + 1
        kept.append(h)

    evidence = []
    returned_by_lane: dict = {}
    lanes_present: set = set()
    for i, h in enumerate(kept, 1):
        evidence.append(_to_item(f"ev:{section_id}:{i:04d}", h))
        returned_by_lane[h.lane] = returned_by_lane.get(h.lane, 0) + 1
        lanes_present.update(h.lanes)

    lane_summary = _lane_summary(lane_results, returned_by_lane)
    return evidence, lane_summary, lanes_present


def _lane_summary(lane_results, returned_by_lane) -> dict:
    by_lane = {lr.lane: lr for lr in lane_results}
    summary: dict = {}
    for lane in LANE_SUMMARY_ORDER:
        lr = by_lane.get(lane)
        requested = lr.requested if lr else 0
        returned = returned_by_lane.get(lane, 0)
        if lr is None:
            status = "not_requested"
        elif lr.status in ("capability_disabled", "unavailable", "empty",
                           "not_requested"):
            status = lr.status
        else:
            status = "pass" if lr.hits else "miss"
        summary[lane] = {"requested": requested, "returned": returned,
                         "status": status}
    return summary
