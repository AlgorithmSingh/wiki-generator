"""test lane: resolved test files -> test source chunks (+ pytest nodeids)."""
from __future__ import annotations

from ..model import LaneResult, chunk_hit, exact_request

LANE = "test"
_RESOLVED = {"test_file", "unique_suffix", "file_exists"}


def _pytest_nodes(bundle, path, cap=8):
    """Collected pytest nodeids declared in this test file (provenance only)."""
    out = []
    for line in bundle.pytest_collect_lines:
        line = line.strip()
        if line.startswith(path) and "::" in line:
            out.append(line)
            if len(out) >= cap:
                break
    return out


def run(bundle, section, options) -> LaneResult:
    needs = section.get("retrieval_needs") or {}
    tests = needs.get("tests") or []
    sid = section["section_id"]
    res = LaneResult(lane=LANE, requested=len(tests), resolved=0)
    rank = 0

    for i, item in enumerate(tests):
        field = f"retrieval_needs.tests[{i}]"
        resolution = item.get("resolution")
        path = item.get("path")
        if resolution not in _RESOLVED or not path:
            res.unresolved.append({
                "section_id": sid, "type": "test", "input": item.get("input"),
                "reason": "ambiguous" if resolution == "ambiguous" else "missing_reference",
                "source_field": field, "candidates": item.get("candidates") or [],
            })
            continue
        res.resolved += 1
        req = exact_request(lane=LANE, source_field=field,
                            requested_input=item.get("input"),
                            handle_field="resolved_test", resolved_handle=path,
                            resolution=resolution)
        nodes = _pytest_nodes(bundle, path)
        chunks = bundle.file_repr_chunks(path, options.max_per_lane)
        if not chunks:
            res.unresolved.append({
                "section_id": sid, "type": "test", "input": item.get("input"),
                "reason": "no_hits", "source_field": field, "candidates": [],
            })
            continue
        for chunk in chunks:
            rank += 1
            prov = {"section_plan_field": field, "input": item.get("input"),
                    "matched_by": "test_file", "test_path": path}
            if nodes:
                prov["pytest_nodes"] = nodes
            res.hits.append(chunk_hit(chunk, lane=LANE, confidence="high",
                                      lane_rank=rank, provenance=prov, request=req))

    res.status = ("not_requested" if res.requested == 0
                  else "pass" if res.hits else "miss")
    return res
