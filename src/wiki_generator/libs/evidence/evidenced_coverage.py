"""Phase 3 evidenced coverage — deterministic per-required-topic evidence gate.

Answers one narrow, deterministic question for every planned required topic:

    Did retrieval produce enough citeable repo evidence to let Phase 4 write that
    topic?

It does **not** make evidence exist. It maps each required topic through the
plan's explicit ``topic_evidence_requirements[]`` source fields to the Phase 3
packet's exact-request coverage records (``coverage.exact_requests[]``) and their
final ``evidence_id`` values — never by fuzzy prose matching. Statuses are
``sufficient`` / ``weak`` / ``missing`` / ``not_applicable``.

The bridge is the per-request coverage record each packet already carries: a
``source_field`` like ``retrieval_needs.files[0]`` with a ``status`` and the
``evidence_ids`` that survived aggregation. A topic is ``sufficient`` only when
its acceptable exact source fields are ``covered`` with at least ``min_items``
citeable evidence IDs. Broad recall (``bm25`` / ``vector`` / ``graph_neighbors``
/ ``search_hints``) is supporting context only: it can make a topic ``weak`` but
never ``sufficient`` (spec "Deterministic topic-to-evidence mapping").

This module is read-only and side-effect-free: it never edits the plan, never
synthesizes evidence, never downgrades a required topic to optional, and never
retries. In ``enhancement`` mode a ``weak``/``missing`` required topic is a
blocking pipeline failure *before* Phase 4 (``bad_underspecified_normalized_plan``,
exit 3). ``baseline`` mode reports the same matrix but never gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_docs import is_provenance_section
# The lane taxonomy, source-field grammar, and required-topic enumeration are the
# single source of truth shared with the producer-side Phase 2 obligation gate
# (libs.coverage.obligations), so this Phase 3 consumer cannot drift from the
# Phase 2 checker on what an exact citeable lane is or which topics are blocking.
from ..coverage.obligations import (
    BROAD_FIELD_LANES as _BROAD_FIELD_LANES,
    EXACT_FIELD_LANES as _EXACT_FIELD_LANES,
    enumerate_section_topics as _section_topics,
    field_index_valid as _field_index_valid,
    parse_source_field as _parse_source_field,
)
from .options import COVERAGE_MODE_ENHANCEMENT

EVIDENCED_COVERAGE_SCHEMA_VERSION = "phase3-evidenced-coverage-v1"

# The named retrieval-validation contract check this gate contributes.
CONTRACT_CHECK_NAME = "required_topic_evidence_sufficient"

# Statuses (spec "Status definitions").
STATUS_SUFFICIENT = "sufficient"
STATUS_WEAK = "weak"
STATUS_MISSING = "missing"
STATUS_NOT_APPLICABLE = "not_applicable"

# Diagnostic codes for a blocking required topic (spec: exit 3 with
# bad_underspecified_normalized_plan, a diagnostic code such as
# required_topic_evidence_weak / required_topic_evidence_missing).
CODE_WEAK = "required_topic_evidence_weak"
CODE_MISSING = "required_topic_evidence_missing"

# ``_EXACT_FIELD_LANES`` (field -> exact citeable lane) and ``_BROAD_FIELD_LANES``
# (field -> broad recall lane) are imported above from libs.coverage.obligations:
# the only lanes that can make a required topic ``sufficient`` are the exact ones,
# and that taxonomy is shared with the Phase 2 obligation gate.


@dataclass
class EvidencedCoverage:
    """The whole-run evidenced-coverage verdict + the artifact matrix."""

    coverage_mode: str
    enforced: bool
    matrix: dict
    blocking_section_ids: list = field(default_factory=list)
    blocking_diagnostics: list = field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return bool(self.blocking_section_ids)


# --- source-field parsing -----------------------------------------------------
# ``_parse_source_field`` and ``_field_index_valid`` are imported above from
# libs.coverage.obligations (shared verbatim with the Phase 2 obligation gate).
def _exact_requests_by_field(packet: dict) -> dict:
    """``source_field`` -> the packet's exact-request coverage record (1:1)."""
    out: dict = {}
    for rec in (packet.get("coverage") or {}).get("exact_requests", []):
        sf = rec.get("source_field")
        if sf is not None:
            out[sf] = rec
    return out


def _returned(packet: dict, lane: str) -> int:
    return int((packet.get("lane_summary") or {}).get(lane, {}).get("returned", 0) or 0)


# --- per-source-field + per-topic evaluation ----------------------------------
def _eval_source_field(section, packet, exact_by_field, source_field,
                       acceptable_lanes):
    """Evaluate one topic source field against the packet's coverage records.

    Returns a deterministic result dict. ``contributes`` lists the citeable
    evidence IDs that count toward sufficiency (covered exact lane within the
    topic's acceptable lanes); ``related`` flags supporting-but-insufficient
    signal (broad recall present, or exact evidence that resolved yet did not
    survive into the acceptable-lane mapping)."""
    field_name, idx = _parse_source_field(source_field)
    valid = False
    lane = None
    kind = "invalid"
    exact_status = None
    candidate_count = 0
    kept_count = 0
    contributes: list[str] = []
    related = False

    if field_name in _EXACT_FIELD_LANES:
        kind = "exact"
        lane = _EXACT_FIELD_LANES[field_name]
        valid = _field_index_valid(section, field_name, idx)
        rec = exact_by_field.get(source_field)
        if rec is not None:
            exact_status = rec.get("status")
            candidate_count = int(rec.get("candidate_count", 0) or 0)
            kept_count = int(rec.get("kept_count", 0) or 0)
            covered = exact_status == "covered"
            ev_ids = list(rec.get("evidence_ids") or [])
            if covered and lane in acceptable_lanes:
                contributes = ev_ids
            # Some related evidence exists for this exact request but it did not
            # become citeable support for the topic (kept under another lane, an
            # excluded lane, or starved by a cap): supporting signal -> weak.
            if candidate_count > 0 and not contributes:
                related = True
    elif field_name in _BROAD_FIELD_LANES:
        kind = "broad"
        broad_lanes = _BROAD_FIELD_LANES[field_name]
        lane = broad_lanes[0]
        valid = _field_index_valid(section, field_name, idx)
        if valid and any(_returned(packet, ln) > 0 for ln in broad_lanes):
            related = True  # broad recall is supporting context, never sufficient

    return {
        "source_field": source_field,
        "field": field_name,
        "index": idx,
        "lane": lane,
        "kind": kind,
        "valid": valid,
        "exact_status": exact_status,
        "candidate_count": candidate_count,
        "kept_count": kept_count,
        "evidence_ids": contributes,
        "related": related,
    }


def _remediation(status: str, topic: str, ter: dict | None) -> str:
    if status == STATUS_MISSING and not ter:
        return (f"declare topic_evidence_requirements[] for required topic "
                f"'{topic}' in the Phase 2 plan, pointing at exact "
                f"retrieval_needs.* source fields (files/symbols/contracts/tests/"
                f"query_packs); fix upstream — do not heal in Phase 3.")
    if status == STATUS_MISSING:
        return (f"point '{topic}' source_fields at real normalized retrieval_needs.* "
                f"entries that resolve to citeable exact evidence, or improve Phase 2 "
                f"planning / retrieval indexing upstream; do not synthesize evidence.")
    if status == STATUS_WEAK:
        return (f"'{topic}' is supported only by broad recall or below-threshold/"
                f"non-exact evidence; add exact file/symbol/contract/test/query_pack "
                f"source fields that resolve to covered evidence, or raise retrieval "
                f"quality upstream. Broad recall alone is not sufficient.")
    return ""


def _eval_topic(section, packet, exact_by_field, topic, ter, *, required,
                provenance):
    """Evaluate one (required) topic -> status record."""
    if provenance:
        return {
            "topic": topic, "required": required, "status": STATUS_NOT_APPLICABLE,
            "diagnostic_code": None, "min_items": 1, "acceptable_lanes": [],
            "source_fields": [], "source_field_results": [],
            "mapped_evidence_ids": [], "evidence_count": 0,
            "source_categories": [],
            "remediation": "",
            "note": ("controlled provenance/meta section — handled outside the "
                     "normal source-evidence lanes"),
        }

    min_items = (ter or {}).get("min_items") or 1
    acceptable = set((ter or {}).get("acceptable_lanes")
                     or list(_EXACT_FIELD_LANES.values()))
    source_fields = list((ter or {}).get("source_fields") or [])

    sf_results = [_eval_source_field(section, packet, exact_by_field, sf, acceptable)
                  for sf in source_fields]

    mapped: list[str] = []
    seen: set = set()
    for r in sf_results:
        for eid in r["evidence_ids"]:
            if eid not in seen:
                seen.add(eid)
                mapped.append(eid)
    mapped.sort()
    any_related = any(r["related"] for r in sf_results)
    categories = sorted({r["lane"] for r in sf_results
                         if r["valid"] and r["lane"]})

    if len(mapped) >= min_items:
        status, code = STATUS_SUFFICIENT, None
    elif mapped or any_related:
        status, code = STATUS_WEAK, CODE_WEAK
    else:
        status, code = STATUS_MISSING, CODE_MISSING

    return {
        "topic": topic, "required": required, "status": status,
        "diagnostic_code": code, "min_items": min_items,
        "acceptable_lanes": sorted(acceptable),
        "source_fields": source_fields, "source_field_results": sf_results,
        "mapped_evidence_ids": mapped, "evidence_count": len(mapped),
        "source_categories": categories,
        "remediation": _remediation(status, topic, ter),
    }


# ``_section_topics`` (the required-topic enumeration) is imported above from
# libs.coverage.obligations: the set of Phase-3-blocking topics this consumer
# evaluates is exactly the set the Phase 2 obligation gate validates.
def evaluate_evidenced_coverage(bundle, packets, options) -> EvidencedCoverage:
    """Build the evidenced-coverage matrix + the enhancement-mode blocking verdict.

    Deterministic and read-only. In ``enhancement`` mode, any required topic in a
    normal source-evidence section that is ``weak`` or ``missing`` is a blocking
    failure; its section id is returned in ``blocking_section_ids`` so the run
    fails before Phase 4 with ``bad_underspecified_normalized_plan`` (exit 3)."""
    enforced = options.coverage_mode == COVERAGE_MODE_ENHANCEMENT
    packet_by_id = {p.get("section_id"): p for p in packets}

    section_rows: list = []
    blocking_sids: list = []
    blocking_diags: list = []
    counts = {STATUS_SUFFICIENT: 0, STATUS_WEAK: 0, STATUS_MISSING: 0,
              STATUS_NOT_APPLICABLE: 0}
    total_topics = 0

    for sid in bundle.section_order:
        section = bundle.section_by_id.get(sid)
        if section is None:
            continue  # missing SectionPlan: already a plan failure upstream.
        packet = packet_by_id.get(sid) or {}
        provenance = is_provenance_section(section)
        exact_by_field = _exact_requests_by_field(packet)

        topic_rows: list = []
        section_blocking = False
        for topic, ter, required in _section_topics(section):
            row = _eval_topic(section, packet, exact_by_field, topic, ter,
                              required=required, provenance=provenance)
            topic_rows.append(row)
            total_topics += 1
            counts[row["status"]] = counts.get(row["status"], 0) + 1
            if (enforced and required and not provenance
                    and row["status"] in (STATUS_WEAK, STATUS_MISSING)):
                section_blocking = True
                blocking_diags.append(
                    f"{sid}: required topic {topic!r} evidence is "
                    f"{row['status']} ({row['diagnostic_code']}); "
                    f"{row['remediation']}")

        if provenance:
            section_status = STATUS_NOT_APPLICABLE
        elif not topic_rows:
            section_status = "pass"  # nothing required to evidence
        elif enforced and section_blocking:
            section_status = "fail"
        else:
            section_status = "pass"

        if section_blocking and sid not in blocking_sids:
            blocking_sids.append(sid)

        section_rows.append({
            "section_id": sid,
            "section_role": section.get("section_role"),
            "status": section_status,
            "required_topic_count": sum(1 for r in topic_rows if r["required"]),
            "topics": topic_rows,
        })

    enforced_blocking = enforced and bool(blocking_sids)
    matrix = {
        "schema_version": EVIDENCED_COVERAGE_SCHEMA_VERSION,
        "coverage_mode": options.coverage_mode,
        "enforced": enforced,
        "status": "fail" if enforced_blocking else "pass",
        "failure_category": ("bad_underspecified_normalized_plan"
                             if enforced_blocking else None),
        "counts": {
            "sections": len(section_rows),
            "required_topics": sum(r["required_topic_count"] for r in section_rows),
            "topics_evaluated": total_topics,
            "sufficient": counts[STATUS_SUFFICIENT],
            "weak": counts[STATUS_WEAK],
            "missing": counts[STATUS_MISSING],
            "not_applicable": counts[STATUS_NOT_APPLICABLE],
        },
        "blocking_sections": sorted(blocking_sids),
        "sections": section_rows,
    }
    return EvidencedCoverage(
        coverage_mode=options.coverage_mode, enforced=enforced, matrix=matrix,
        blocking_section_ids=sorted(blocking_sids),
        blocking_diagnostics=blocking_diags)
