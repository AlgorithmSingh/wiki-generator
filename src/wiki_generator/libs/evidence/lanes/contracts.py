"""contract lane: OpenAPI references -> operation pointers + recovered handlers."""
from __future__ import annotations

import json
import re

from ...util import clip
from ..model import (
    LaneResult, RawHit, build_scores, chunk_hit, exact_request, span_hit)
from ..schema import EVIDENCE_EXCERPT_CHARS

LANE = "contract"
HTTP_REFERENCE_PATH = "docs/references/http_api_reference.md"


def _escape(segment: str) -> str:
    return str(segment).replace("~", "~0").replace("/", "~1")


def _op_excerpt(operation) -> str:
    return clip(json.dumps(operation, ensure_ascii=False, indent=2),
               EVIDENCE_EXCERPT_CHARS)


def _brace_route(route: str) -> str:
    """Convert Flask/Quart ``<param>`` route placeholders to docs ``{param}``."""
    return re.sub(r"<([^>/]+)>", r"{\1}", str(route or ""))


def _public_route_candidate(route: str) -> str:
    """Canonical public REST route used by the HTTP API reference when present."""
    r = _brace_route(route)
    if r.startswith("/api/"):
        return r
    if r.startswith("/v1/"):
        return "/api" + r
    return "/api/v1" + (r if r.startswith("/") else f"/{r}")


def _http_reference_supports(bundle, *, method: str, route: str) -> str | None:
    """Return the documented public route when the HTTP reference contains it.

    OpenAPI routes in ``contracts/openapi.json`` are internal blueprint paths such
    as ``/datasets/<dataset_id>``. The public HTTP docs spell the same routes as
    ``/api/v1/datasets/{dataset_id}``. Expose that public form only when a
    citeable HTTP-reference chunk/span actually contains it, so Phase 4 can copy
    one route string instead of synthesizing a prefix/placeholders from separate
    evidence items.
    """
    public_route = _public_route_candidate(route)
    method = str(method or "").upper()
    method_markers = (f"**{method}**", f"Method: {method}", f"--request {method}")
    rows = list(getattr(bundle, "spans_by_path", {}).get(HTTP_REFERENCE_PATH, []))
    rows += list(getattr(bundle, "chunks_by_path", {}).get(HTTP_REFERENCE_PATH, []))
    for row in rows:
        text = row.get("text") or ""
        if public_route in text and any(marker in text for marker in method_markers):
            return public_route
    return None


def _route_hit(route, method, operation, *, field, item, rank, request,
               public_route=None) -> RawHit:
    pointer = f"/paths/{_escape(route)}/{method.lower()}"
    source = {"artifact": "contracts/openapi.json", "json_pointer": pointer,
              "route": route, "method": method.upper()}
    if public_route:
        source["public_route"] = public_route
        source["public_route_source"] = HTTP_REFERENCE_PATH
    return RawHit(
        lane=LANE, type="route_operation",
        source=source,
        excerpt=_op_excerpt(operation), confidence="exact",
        provenance={"section_plan_field": field, "input": item.get("input"),
                    "matched_by": "openapi_operation",
                    "handler_symbol_id": operation.get("x-handler-symbol-id"),
                    "x_source": operation.get("x-source")},
        scores=build_scores(lane_rank=rank), dedupe_key=f"openapi|{pointer}",
        coarse_key=f"openapi|{pointer}", is_span=False, lane_rank=rank,
        request=request)


def _recover_handler(bundle, operation, *, field, item, rank, res, options, request):
    """If the operation names a handler symbol, add its source span as linked evidence."""
    symbol_id = operation.get("x-handler-symbol-id")
    if not symbol_id:
        return rank
    symbol = bundle.symbol(symbol_id)
    if symbol is None or not symbol.get("span_id"):
        return rank
    span = bundle.span(symbol["span_id"])
    if span is None:
        return rank
    rank += 1
    res.hits.append(span_hit(
        span, lane=LANE, confidence="exact", lane_rank=rank, request=request,
        provenance={"section_plan_field": field, "input": item.get("input"),
                    "matched_by": "contract_handler", "symbol_id": symbol_id}))
    return rank


def _recover_source(bundle, operation, *, field, item, rank, res, options, request):
    """Recover the route's declaring source line via the ``x-source`` extension."""
    xsrc = operation.get("x-source")
    if not xsrc or ":" not in str(xsrc):
        return rank
    path, _, lineno = str(xsrc).rpartition(":")
    if not lineno.isdigit():
        return rank
    line = int(lineno)
    for chunk in bundle.overlapping_chunks(path, line, line, 1):
        rank += 1
        res.hits.append(chunk_hit(
            chunk, lane=LANE, confidence="high", lane_rank=rank, request=request,
            provenance={"section_plan_field": field, "input": item.get("input"),
                        "matched_by": "contract_source", "x_source": xsrc}))
    return rank


def _contract_request(item, field, route):
    """Stable exact-request identity for one contracts[] reference."""
    method = (item.get("method") or "").upper()
    handle = f"{method} {route}".strip() if method else str(route)
    return exact_request(lane=LANE, source_field=field,
                         requested_input=item.get("input"),
                         handle_field="operation_ref", resolved_handle=handle,
                         resolution=item.get("resolution"))


def run(bundle, section, options) -> LaneResult:
    needs = section.get("retrieval_needs") or {}
    contracts = needs.get("contracts") or []
    sid = section["section_id"]
    res = LaneResult(lane=LANE, requested=len(contracts), resolved=0)
    rank = 0
    paths = (bundle.openapi or {}).get("paths") or {}

    for i, item in enumerate(contracts):
        field = f"retrieval_needs.contracts[{i}]"
        resolution = item.get("resolution")
        route = item.get("path")

        if resolution == "exact" and route in paths:
            method = item.get("method") or ""
            operation = paths[route].get(method.lower())
            if operation is None:
                res.unresolved.append(_miss(sid, item, field, "no_hits"))
                continue
            res.resolved += 1
            req = _contract_request(item, field, route)
            rank += 1
            public_route = _http_reference_supports(bundle, method=method, route=route)
            res.hits.append(_route_hit(route, method, operation,
                                       field=field, item=item, rank=rank,
                                       request=req, public_route=public_route))
            rank = _recover_handler(bundle, operation, field=field, item=item,
                                    rank=rank, res=res, options=options, request=req)
            rank = _recover_source(bundle, operation, field=field, item=item,
                                   rank=rank, res=res, options=options, request=req)
        elif resolution == "path_only" and route in paths:
            res.resolved += 1
            req = _contract_request(item, field, route)
            methods = item.get("methods") or sorted(
                m for m in paths[route] if not m.startswith("x-"))
            for method in sorted(methods)[:options.max_per_lane]:
                operation = paths[route].get(str(method).lower())
                if operation is None:
                    continue
                rank += 1
                public_route = _http_reference_supports(bundle, method=str(method),
                                                        route=route)
                res.hits.append(_route_hit(route, str(method), operation,
                                           field=field, item=item, rank=rank,
                                           request=req, public_route=public_route))
                rank = _recover_handler(bundle, operation, field=field, item=item,
                                        rank=rank, res=res, options=options, request=req)
        elif resolution in ("no_match", "hint") or route not in paths:
            reason = "missing_reference" if resolution == "no_match" else "no_hits"
            res.unresolved.append(_miss(sid, item, field, reason))
        else:
            res.unresolved.append(_miss(sid, item, field, "no_hits"))

    res.status = ("not_requested" if res.requested == 0
                  else "pass" if res.hits else "miss")
    return res


def _miss(sid, item, field, reason) -> dict:
    return {"section_id": sid, "type": "contract", "input": item.get("input"),
            "reason": reason, "source_field": field, "candidates": []}
