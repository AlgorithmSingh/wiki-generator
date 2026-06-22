"""Deterministic contract + invariant checks over a completed Phase 3 run.

Classifies any failure into exactly one product category and the matching exit
code. Bad/missing input is caught earlier (in the loader); this module decides
between a clean pass, a bad/underspecified plan, and a retriever bug.
"""
from __future__ import annotations

from .schema import (
    CAT_BAD_PLAN, CAT_BUG, EXIT_FOR_CATEGORY, VALIDATION_SCHEMA_VERSION,
    validate_packet,
)


def _resolve_pointer(doc, pointer):
    """Resolve an RFC 6901 JSON pointer; return (found, value)."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False, None
    cur = doc
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and token in cur:
            cur = cur[token]
        elif isinstance(cur, list) and token.isdigit() and int(token) < len(cur):
            cur = cur[int(token)]
        else:
            return False, None
    return True, cur


def _anchor_exists(bundle, source) -> bool:
    if source.get("span_id"):
        return source["span_id"] in bundle.spans_by_id
    if source.get("chunk_id"):
        return source["chunk_id"] in bundle.chunks_by_id
    if source.get("json_pointer"):
        found, _ = _resolve_pointer(bundle.openapi or {}, source["json_pointer"])
        return found
    if source.get("path"):
        path = source["path"]
        return path in bundle.chunks_by_path or path in bundle.files_by_path
    return False


def validate_run(bundle, packets, options, *, substrate_warnings) -> tuple[dict, str | None, int]:
    section_order = bundle.section_order
    contract_checks: list = []
    bug_errors: list = []

    # 1. one packet per section, in document order.
    ids_in_order = [p.get("section_id") for p in packets]
    ok_order = ids_in_order == list(section_order)
    contract_checks.append(_check(
        "all_sections_have_packets", ok_order,
        f"{len(packets)}/{len(section_order)} packets in document order"))
    if not ok_order:
        bug_errors.append(f"packet order mismatch: {ids_in_order} != {section_order}")

    # 2. document-plan validity + every section in section_order has a SectionPlan.
    contract_checks.append(_check(
        "document_plan_valid", bool(section_order),
        f"section_order has {len(section_order)} section(s)"))
    contract_checks.append(_check(
        "section_plans_valid_jsonl", True,
        f"{len(bundle.section_by_id)} SectionPlan row(s) parsed"))
    missing_plans = [s for s in section_order if s not in bundle.section_by_id]
    contract_checks.append(_check(
        "section_plans_cover_order", not missing_plans,
        "all sections present" if not missing_plans
        else f"missing SectionPlan: {missing_plans}"))

    # 3. capabilities agree with the substrate (loader hard-stops real mismatches;
    # this re-asserts the invariant as an auditable, computed check).
    caps_vectors = bool(bundle.caps.get("vectors"))
    caps_ok = (bundle.retrieval_mode == "hybrid") == caps_vectors
    contract_checks.append(_check(
        "capabilities_consistent", caps_ok,
        f"retrieval_mode={bundle.retrieval_mode}, vectors={caps_vectors}"))
    contract_checks.append(_check(
        "bm25_readable", True,
        "verified by loader" if bundle.caps.get("bm25") else "capability disabled"))
    contract_checks.append(_check(
        "vectors_readable_count_consistent", True,
        "verified by loader" if caps_vectors else "capability disabled"))

    # 4. schema validity of every packet (schema-valid input -> schema-valid packet).
    schema_errors: list = []
    for p in packets:
        schema_errors.extend(validate_packet(p))
    contract_checks.append(_check(
        "packets_schema_valid", not schema_errors,
        "all packets valid" if not schema_errors else f"{len(schema_errors)} error(s)"))
    bug_errors.extend(schema_errors)

    # 5. evidence ids unique, anchors resolve, no plan-only citations.
    id_errors: list = []
    anchor_errors: list = []
    plan_only: list = []
    for p in packets:
        seen: set = set()
        for item in p.get("evidence", []):
            eid = item.get("evidence_id")
            if eid in seen:
                id_errors.append(f"{p['section_id']}: duplicate evidence_id {eid}")
            seen.add(eid)
            source = item.get("source") or {}
            if str(source.get("artifact", "")).startswith("plans/"):
                plan_only.append(f"{p['section_id']}: {eid} cites the plan")
            elif not _anchor_exists(bundle, source):
                anchor_errors.append(
                    f"{p['section_id']}: {eid} anchor not found ({source})")
    contract_checks.append(_check(
        "evidence_ids_unique", not id_errors,
        "unique within every packet" if not id_errors else f"{len(id_errors)} dup(s)"))
    contract_checks.append(_check(
        "evidence_anchors_resolve", not anchor_errors,
        "all anchors resolve" if not anchor_errors else f"{len(anchor_errors)} error(s)"))
    contract_checks.append(_check(
        "no_plan_only_evidence", not plan_only,
        "ok" if not plan_only else f"{len(plan_only)} violation(s)"))
    bug_errors.extend(id_errors)
    bug_errors.extend(anchor_errors)
    bug_errors.extend(plan_only)

    # --- per-section results --------------------------------------------------
    section_results: list = []
    plan_failures: list = []
    total_evidence = 0
    for p in packets:
        ev = p.get("evidence", [])
        total_evidence += len(ev)
        val = p.get("validation") or {}
        status = val.get("status", "pass")
        if status == "fail":
            plan_failures.append(p["section_id"])
        section_results.append({
            "section_id": p["section_id"],
            "status": status,
            "evidence_count": len(ev),
            "missing_expected_evidence_types": (p.get("coverage") or {}).get("missing", []),
            "warnings": val.get("warnings", []),
        })

    # A missing SectionPlan is authoritatively a plan-quality failure, driven by
    # the section_plans_cover_order check itself (not only the per-packet status).
    for s in missing_plans:
        if s not in plan_failures:
            plan_failures.append(s)

    # --- classify -------------------------------------------------------------
    if bug_errors:
        category = CAT_BUG
        status = "fail"
    elif plan_failures:
        category = CAT_BAD_PLAN
        status = "fail"
    else:
        category = None
        status = "pass"

    validation = {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": status,
        "failure_category": category,
        "retrieval_mode": bundle.retrieval_mode,
        "counts": {
            "sections_expected": len(section_order),
            "sections_processed": len(packets),
            "packets_written": len(packets),
            "evidence_items": total_evidence,
        },
        "contract_checks": contract_checks,
        "section_results": section_results,
        "errors": bug_errors,
        "warnings": list(substrate_warnings) + (
            [f"plan-quality failures: {plan_failures}"] if plan_failures else []),
    }
    return validation, category, EXIT_FOR_CATEGORY[category]


def _check(name, ok, details) -> dict:
    return {"name": name, "status": "pass" if ok else "fail", "details": details}
