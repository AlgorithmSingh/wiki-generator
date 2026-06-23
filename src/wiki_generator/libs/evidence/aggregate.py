"""Merge lane outputs into final, deterministically ordered evidence items.

Pipeline (spec "Aggregation, dedupe, and ranking" + Iteration 3 amendment):
1. exact dedupe by ``dedupe_key`` (keep all provenance, one item);
2. prefer an exact source span over a chunk describing the same range;
3. select kept items request-aware: reserve one citeable item for every exact
   request that produced candidates, then water-fill balanced exact depth, then
   fill the remaining section budget with broad recall (bm25/vector/graph);
4. sort the kept set by confidence/lane/rank/path/start_line/anchor;
5. assign final ``evidence_id`` values from the sorted, kept list;
6. emit per-request coverage records so feasible exact requests cannot vanish
   silently behind ordinary sorting or per-lane caps.

Iteration 3 fixes the unbalanced exact-lane bug where global sorting + a per-lane
cap let early candidates from one requested file consume the whole file-anchor
budget, leaving other requested files (e.g. ``rag/llm/embedding_model.py``) with
zero kept evidence even though the cap was feasible.
"""
from __future__ import annotations

from collections import Counter

from .model import CONFIDENCE_RANK, LANE_PRIORITY, request_key

# Display order for lane_summary (spec EvidencePacket example).
LANE_SUMMARY_ORDER = (
    "file_anchor", "symbol_anchor", "query_pack", "contract", "test",
    "graph_neighbors", "bm25", "vector",
)
EXPECTED_LABEL_TO_LANE = {
    "files": "file_anchor", "symbols": "symbol_anchor", "queries": "query_pack",
    "contracts": "contract", "tests": "test", "graph": "graph_neighbors",
}

# Lanes whose requests are exact coverage obligations (spec "Required behavior").
# bm25/vector/graph_neighbors are broad recall: they improve recall but are never
# exact-coverage obligations and fill the section budget only after exact minima
# and balanced exact depth are satisfied.
EXACT_LANES = ("file_anchor", "symbol_anchor", "contract", "test", "query_pack")
# unresolved-record ``type`` -> exact lane, for enumerating no-hit/unresolved
# exact requests that produced no candidate at all.
_TYPE_TO_LANE = {
    "file": "file_anchor", "symbol": "symbol_anchor", "contract": "contract",
    "test": "test", "query_pack": "query_pack",
}
_DEFAULT_HANDLE_FIELD = {
    "file_anchor": "resolved_path", "symbol_anchor": "resolved_symbol_id",
    "contract": "operation_ref", "test": "resolved_test", "query_pack": "query_pack",
}


def _init_merge(hit) -> None:
    hit.lanes = [hit.lane]
    hit.merged_provenance = [hit.provenance]
    hit.covers = [hit.request] if hit.request else []


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

    Every exact-request identity covered by ``other`` is preserved on ``target``
    (Iteration 3): a merged representative may satisfy multiple exact requests
    only when that provenance survives in the coverage records.
    """
    for lane in other.lanes:
        if lane not in target.lanes:
            target.lanes.append(lane)
    for req in other.covers:
        if req and not any(request_key(req) == request_key(x) for x in target.covers):
            target.covers.append(req)
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


# --- request-aware selection (Iteration 3) ------------------------------------

def _unique_covers(rep) -> dict:
    """request_key -> request dict for every distinct exact request ``rep`` covers."""
    out: dict = {}
    for req in getattr(rep, "covers", None) or []:
        if req:
            out.setdefault(request_key(req), req)
    return out


def _parse_field(field):
    """('retrieval_needs.files[2]') -> ('files', 2). Index -1 when absent."""
    name = field or ""
    idx = -1
    if name.endswith("]") and "[" in name:
        head, _, tail = name.partition("[")
        name = head
        num = tail[:-1]
        idx = int(num) if num.isdigit() else -1
    if name.startswith("retrieval_needs."):
        name = name[len("retrieval_needs."):]
    return name, idx


def _request_sort(req):
    name, idx = _parse_field(req.get("source_field", ""))
    return (LANE_PRIORITY.get(req.get("lane"), len(LANE_PRIORITY)),
            name, idx, str(req.get("resolved_handle") or ""))


def _build_pools(exact_reps):
    """request_key -> reps (sorted), plus request_key -> request dict."""
    pools: dict = {}
    req_of: dict = {}
    for r in exact_reps:
        for k, req in _unique_covers(r).items():
            pools.setdefault(k, []).append(r)
            req_of[k] = req
    for k in pools:
        pools[k].sort(key=lambda r: r.sort_key())
    return pools, req_of


def _select(pools, req_of, request_keys, broad_reps, options):
    """Pick kept reps: exact minima, then balanced exact depth, then broad fill.

    Returns ``(kept_list, starved_keys)``. ``starved_keys`` are exact requests
    with candidates that could not receive a minimum citeable item because the
    hard section cap (``max_total_per_section``) made the obligations infeasible.
    """
    section_cap = options.max_total_per_section

    # Effective per-lane budget for exact lanes: at least the number of exact
    # requests with candidates in that lane, so max_per_lane never starves the
    # protected minima (spec "Specific file-anchor rule").
    reqs_per_lane = Counter(req_of[k]["lane"] for k in request_keys)
    lane_budget = {lane: max(options.max_per_lane, n)
                   for lane, n in reqs_per_lane.items()}

    kept: list = []
    kept_ids: set = set()
    covered: set = set()
    lane_kept: Counter = Counter()
    starved: set = set()

    def keep(rep):
        kept.append(rep)
        kept_ids.add(id(rep))
        lane_kept[rep.lane] += 1
        for k in _unique_covers(rep):
            covered.add(k)

    def next_rep(k):
        return next((r for r in pools[k] if id(r) not in kept_ids), None)

    # Phase A: reserve one citeable item per exact request (guarded only by the
    # hard section cap; the effective lane budget already covers all minima).
    for k in request_keys:
        if k in covered:
            continue
        rep = next_rep(k)
        if rep is None:
            continue
        if len(kept) >= section_cap:
            starved.add(k)
            continue
        keep(rep)

    # Phase B: balanced exact depth (water-fill / round-robin). Complete depth d
    # for every eligible request before any request reaches depth d+1; exhausted
    # requests are skipped and their unused budget redistributed.
    progress = True
    while progress and len(kept) < section_cap:
        progress = False
        for k in request_keys:
            if len(kept) >= section_cap:
                break
            rep = next_rep(k)
            if rep is None:
                continue
            if lane_kept[rep.lane] >= lane_budget.get(rep.lane, options.max_per_lane):
                continue
            keep(rep)
            progress = True

    # Phase C: broad recall (bm25/vector/graph_neighbors) fills the remainder
    # only after exact obligations are satisfied, with the configured per-lane cap.
    broad_lane_kept: Counter = Counter()
    for r in sorted(broad_reps, key=lambda h: h.sort_key()):
        if len(kept) >= section_cap:
            break
        if broad_lane_kept[r.lane] >= options.max_per_lane:
            continue
        broad_lane_kept[r.lane] += 1
        keep(r)

    return kept, starved


# --- per-request coverage reporting (Iteration 3) -----------------------------

def _handle_from_section(section, lane, source_field):
    """(handle_field, resolved_handle, resolution) for a no-candidate request."""
    handle_field = _DEFAULT_HANDLE_FIELD.get(lane, "resolved_handle")
    if section is None:
        return handle_field, None, None
    name, idx = _parse_field(source_field)
    items = (section.get("retrieval_needs") or {}).get(name) or []
    if not (0 <= idx < len(items)):
        return handle_field, None, None
    item = items[idx]
    if lane == "query_pack":
        return handle_field, (item if isinstance(item, str) else None), "exact"
    if not isinstance(item, dict):
        return handle_field, None, None
    resolution = item.get("resolution")
    if lane in ("file_anchor", "test"):
        return handle_field, item.get("path"), resolution
    if lane == "symbol_anchor":
        return handle_field, item.get("symbol_id"), resolution
    if lane == "contract":
        method = (item.get("method") or "").upper()
        route = item.get("path") or ""
        handle = f"{method} {route}".strip() if method else str(route)
        return handle_field, (handle or None), resolution
    return handle_field, None, resolution


def _coverage_record(req, candidate_count, kept_count, evidence_ids, status,
                     reason=None) -> dict:
    rec = {
        "lane": req["lane"],
        "source_field": req["source_field"],
        "requested_input": req.get("requested_input"),
        req.get("handle_field", "resolved_handle"): req.get("resolved_handle"),
        "resolution": req.get("resolution"),
        "candidate_count": candidate_count,
        "kept_count": kept_count,
        "evidence_ids": evidence_ids,
        "status": status,
    }
    if reason:
        rec["reason"] = reason
    return rec


def _rec_sort(rec):
    name, idx = _parse_field(rec.get("source_field", ""))
    return (LANE_PRIORITY.get(rec.get("lane"), len(LANE_PRIORITY)), name, idx)


def _exact_coverage(pools, req_of, request_keys, kept_ids, id_of, starved,
                    lane_results, section, options):
    """One coverage record per resolved exact request (with or without candidates)."""
    records: list = []
    seen: set = set()           # (lane, source_field) already recorded

    # 1. requests that produced candidates.
    for k in request_keys:
        req = req_of[k]
        seen.add((req["lane"], req["source_field"]))
        pool = pools[k]
        candidate_count = len(pool)
        kept_reps = [r for r in pool if id(r) in kept_ids]
        kept_count = len(kept_reps)
        evidence_ids = sorted(id_of[id(r)] for r in kept_reps)
        if kept_count > 0:
            records.append(_coverage_record(req, candidate_count, kept_count,
                                             evidence_ids, "covered"))
            continue
        # No kept item despite candidates. With a correct allocator this happens
        # only when the hard section cap is infeasible; otherwise it is a
        # fail-closed implementation-failure sentinel. Either way it fails
        # validation loudly (it must never read as a clean lane-level pass).
        infeasible = len(request_keys) > options.max_total_per_section
        if infeasible or k in starved:
            reason = (f"hard section cap (max_total_per_section="
                      f"{options.max_total_per_section}) infeasible: "
                      f"{len(request_keys)} exact requests with candidates exceed cap")
        else:
            reason = ("exact request with candidates received no kept evidence "
                      "under feasible caps (allocation implementation failure)")
        records.append(_coverage_record(req, candidate_count, 0, [],
                                        "starved_by_cap", reason))

    # 2. resolved exact requests that produced no candidate at all (no_hits), and
    # unresolved exact requests that should already have been caught upstream.
    for lr in lane_results:
        for u in lr.unresolved:
            lane = _TYPE_TO_LANE.get(u.get("type"))
            if lane is None:
                continue
            sf = u.get("source_field")
            if (lane, sf) in seen:
                continue
            seen.add((lane, sf))
            reason = u.get("reason")
            status = "unresolved" if reason in ("missing_reference", "ambiguous") \
                else "no_hits"
            hf, handle, resolution = _handle_from_section(section, lane, sf)
            req = {"lane": lane, "source_field": sf,
                   "requested_input": u.get("input"), "handle_field": hf,
                   "resolved_handle": handle, "resolution": resolution}
            records.append(_coverage_record(req, 0, 0, [], status, reason))

    records.sort(key=_rec_sort)
    return records


def aggregate(section_id, lane_results, options, section=None):
    """Return (evidence_items, lane_summary, lanes_present_set, exact_coverage)."""
    hits = []
    for lr in lane_results:
        hits.extend(lr.hits)

    reps = _prefer_span(_exact_dedupe(hits))

    exact_reps = [r for r in reps if _unique_covers(r)]
    broad_reps = [r for r in reps if not _unique_covers(r)]
    pools, req_of = _build_pools(exact_reps)
    request_keys = sorted(pools, key=lambda k: _request_sort(req_of[k]))

    kept, starved = _select(pools, req_of, request_keys, broad_reps, options)
    kept_ids = {id(r) for r in kept}

    # Assign evidence ids last, from the kept set sorted by the ranking key, so
    # output stays byte-stable for identical inputs.
    kept_sorted = sorted(kept, key=lambda h: h.sort_key())
    evidence = []
    id_of: dict = {}
    returned_by_lane: dict = {}
    lanes_present: set = set()
    for i, h in enumerate(kept_sorted, 1):
        eid = f"ev:{section_id}:{i:04d}"
        id_of[id(h)] = eid
        evidence.append(_to_item(eid, h))
        returned_by_lane[h.lane] = returned_by_lane.get(h.lane, 0) + 1
        lanes_present.update(h.lanes)

    lane_summary = _lane_summary(lane_results, returned_by_lane)
    coverage = _exact_coverage(pools, req_of, request_keys, kept_ids, id_of,
                               starved, lane_results, section, options)
    return evidence, lane_summary, lanes_present, coverage


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
