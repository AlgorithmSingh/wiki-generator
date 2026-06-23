"""Phase 3 — deterministic, LLM-free evidence retrieval (all-sections producer).

``run(options)`` reads the normalized Phase 2 plan and the Step 5 retrieval
substrate, retrieves exact evidence for every planned section through eight
lanes, aggregates/dedupes/ranks it, validates the result as a contract check,
and writes one EvidencePacket per section plus the manifest, validation, report,
and unresolved sidecar.

There is no product ``--section`` mode and no interactive retry loop: a failed
run points at the upstream fix and expects the same all-sections command rerun.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .. import util
from ..context_docs import is_provenance_section, section_has_retrieval_signal
from .aggregate import EXPECTED_LABEL_TO_LANE, aggregate
from .lanes import bm25 as bm25_lane
from .lanes import contracts as contracts_lane
from .lanes import files as files_lane
from .lanes import graph as graph_lane
from .lanes import query_packs as query_packs_lane
from .lanes import symbols as symbols_lane
from .lanes import tests as tests_lane
from .lanes import vectors as vectors_lane
from .loader import BadInputArtifact, load_bundle
from .options import EvidenceOptions
from .schema import (
    CAT_BAD_INPUT, EXIT_BAD_INPUT, PACKET_SCHEMA_VERSION,
)
from .validate import validate_run
from .writer import write_all, write_failure_stub

__all__ = ["run", "EvidenceOptions", "EvidenceResult", "BadInputArtifact"]


@dataclass
class EvidenceResult:
    ok: bool
    status: str
    failure_category: str | None
    exit_code: int
    retrieval_mode: str | None
    counts: dict
    files_written: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def run(options: EvidenceOptions, *, vector_backend=None) -> EvidenceResult:
    os.makedirs(options.out_dir, exist_ok=True)
    try:
        bundle = load_bundle(options)
    except BadInputArtifact as e:
        written = write_failure_stub(options.out_dir, options.bundle_root,
                                     CAT_BAD_INPUT, str(e))
        return EvidenceResult(False, "fail", CAT_BAD_INPUT, EXIT_BAD_INPUT,
                              None, {}, written, [str(e)])

    packets: list = []
    unresolved_all: list = []
    for i, sid in enumerate(bundle.section_order):
        packet, unresolved = _build_packet(bundle, sid, i, options, vector_backend)
        packets.append(packet)
        unresolved_all.extend(unresolved)

    # Deterministic, environment-independent note when a hybrid bundle could not
    # run its vector lane (e.g. faiss/model2vec not installed on this machine).
    if any(p["lane_summary"].get("vector", {}).get("status") == "unavailable"
           for p in packets):
        bundle.warnings.append(
            "vector lane unavailable on this host (backend not importable); "
            "hybrid recall skipped — exact/lexical lanes unaffected")

    validation, category, exit_code = validate_run(
        bundle, packets, options, substrate_warnings=bundle.warnings)
    files_written = write_all(bundle, options, packets, validation, unresolved_all)
    return EvidenceResult(
        ok=category is None, status=validation["status"], failure_category=category,
        exit_code=exit_code, retrieval_mode=bundle.retrieval_mode,
        counts=validation["counts"], files_written=files_written,
        warnings=validation["warnings"])


def _section_sha(bundle, sid) -> str | None:
    raw = bundle.section_raw_by_id.get(sid)
    return f"sha256:{util.sha256_text(raw)}" if raw is not None else None


def _context_artifact_paths(needs) -> list:
    """Repo-relative paths of the section's planner-context docs (traceability
    only — these are never citeable as evidence)."""
    out: list = []
    for ca in needs.get("context_artifacts") or []:
        path = ca.get("path") if isinstance(ca, dict) else ca
        if path and path not in out:
            out.append(path)
    return out


def _work_order(section) -> dict:
    needs = section.get("retrieval_needs") or {}
    return {
        "purpose": section.get("purpose") or "",
        "required_topics": list(section.get("required_topics") or []),
        "expected_evidence_types": list(section.get("expected_evidence_types") or []),
        "retrieval_needs": {
            "query_packs": list(needs.get("query_packs") or []),
            "symbols": [s.get("symbol_id") or s.get("input")
                        for s in needs.get("symbols") or []],
            "files": [f.get("path") or f.get("input") for f in needs.get("files") or []],
            "contracts": [c.get("input") for c in needs.get("contracts") or []],
            "tests": [t.get("path") or t.get("input") for t in needs.get("tests") or []],
            "graph_nodes": list(needs.get("graph_nodes") or []),
        },
        "context_artifacts": _context_artifact_paths(needs),
    }


def _missing_packet(bundle, sid, index, options) -> dict:
    evidence, lane_summary, _ = aggregate(sid, [], options)
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "section_id": sid,
        "title": sid,
        "order": index + 1,
        "retrieval_mode": bundle.retrieval_mode,
        "source_plan": {
            "document_plan_path": "plans/document-plan.json",
            "section_plans_path": "plans/section-plans.jsonl",
            "section_plan_sha256": None,
        },
        "work_order": {"purpose": "", "required_topics": [],
                       "expected_evidence_types": [],
                       "retrieval_needs": {"query_packs": [], "symbols": [], "files": [],
                                           "contracts": [], "tests": [], "graph_nodes": []},
                       "context_artifacts": []},
        "evidence": evidence,
        "lane_summary": lane_summary,
        "coverage": {"satisfied": [], "missing": [], "warnings": []},
        "validation": {
            "status": "fail",
            "errors": ["section present in DocumentPlan but has no SectionPlan"],
            "warnings": [],
        },
    }


def _provenance_packet(bundle, section, sid, index, options) -> dict:
    """Packet for a controlled provenance/meta section (Patch 3).

    A provenance/meta section is non-source: it is handled OUTSIDE the normal
    evidence lanes. No source retrieval runs, no generic fallback, and its
    diagnostic/context artifacts are carried for traceability only (never cited).
    It validates as pass because absence of source evidence is correct here."""
    evidence, lane_summary, _ = aggregate(sid, [], options)
    note = ("controlled provenance/meta section — handled outside normal evidence "
            "lanes; diagnostics are non-source context, not citeable evidence")
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "section_id": sid,
        "section_role": "provenance",
        "title": section.get("title") or sid,
        "order": section.get("order") if isinstance(section.get("order"), int)
        else index + 1,
        "retrieval_mode": bundle.retrieval_mode,
        "source_plan": {
            "document_plan_path": "plans/document-plan.json",
            "section_plans_path": "plans/section-plans.jsonl",
            "section_plan_sha256": _section_sha(bundle, sid),
        },
        "work_order": _work_order(section),
        "evidence": evidence,
        "lane_summary": lane_summary,
        "coverage": {"satisfied": [], "missing": [], "warnings": [note]},
        "validation": {"status": "pass", "errors": [], "warnings": [note]},
    }


def _build_packet(bundle, sid, index, options, vector_backend):
    section = bundle.section_by_id.get(sid)
    if section is None:
        return _missing_packet(bundle, sid, index, options), []

    # Patch 3: a controlled provenance/meta section is non-source — never retrieve
    # source evidence (and never generic fallback) for it.
    if is_provenance_section(section):
        return _provenance_packet(bundle, section, sid, index, options), []

    # Patch 3: a no-signal normal section must NOT be rescued by generic BM25/vector
    # fallback. The recall lanes run only when the section has a legitimate
    # retrieval driver (exact handles, query packs, or search hints); the same
    # predicate the readiness gate uses, so a section that should have failed
    # readiness cannot be quietly rescued here.
    has_signal = section_has_retrieval_signal(section)
    lane_results = [
        files_lane.run(bundle, section, options),
        symbols_lane.run(bundle, section, options),
        query_packs_lane.run(bundle, section, options),
        contracts_lane.run(bundle, section, options),
        tests_lane.run(bundle, section, options),
        graph_lane.run(bundle, section, options),
    ]
    if has_signal:
        lane_results.append(bm25_lane.run(bundle, section, options))
        lane_results.append(
            vectors_lane.run(bundle, section, options, backend=vector_backend))
    evidence, lane_summary, lanes_present = aggregate(sid, lane_results, options)
    unresolved = [u for lr in lane_results for u in lr.unresolved]
    by_lane = {lr.lane: lr for lr in lane_results}

    expected = list(section.get("expected_evidence_types") or [])
    satisfied = [lbl for lbl in expected
                 if EXPECTED_LABEL_TO_LANE.get(lbl) in lanes_present]
    missing = [lbl for lbl in expected if lbl not in satisfied]

    errors: list = []
    warnings: list = []
    coverage_warnings: list = []
    if not evidence:
        errors.append("no evidence retrieved for section")
    for label in missing:
        lr = by_lane.get(EXPECTED_LABEL_TO_LANE.get(label))
        if lr is None or lr.resolved == 0:
            errors.append(f"expected evidence type '{label}' has no resolvable work item")
        else:
            msg = f"expected evidence type '{label}' resolved but produced no evidence"
            warnings.append(msg)
            coverage_warnings.append(msg)
    if unresolved:
        warnings.append(f"{len(unresolved)} unresolved reference(s)")

    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "section_id": sid,
        "title": section.get("title") or sid,
        "order": section.get("order") if isinstance(section.get("order"), int)
        else index + 1,
        "retrieval_mode": bundle.retrieval_mode,
        "source_plan": {
            "document_plan_path": "plans/document-plan.json",
            "section_plans_path": "plans/section-plans.jsonl",
            "section_plan_sha256": _section_sha(bundle, sid),
        },
        "work_order": _work_order(section),
        "evidence": evidence,
        "lane_summary": lane_summary,
        "coverage": {"satisfied": satisfied, "missing": missing,
                     "warnings": coverage_warnings},
        "validation": {"status": "fail" if errors else "pass",
                       "errors": errors, "warnings": warnings},
    }
    return packet, unresolved
