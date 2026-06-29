"""Build a compact, model-safe ``WritingPacket`` for one section.

The model never receives the raw bundle. For each section we join the
``DocumentPlan`` row, the ``SectionPlan`` work order, and the validated
``EvidencePacket`` into a bounded packet: section intent, orientation-only
search hints, explicitly non-citeable context artifacts, and a deduplicated
evidence table whose ``evidence_id`` values are the *only* citeable handles.
Evidence IDs are copied verbatim — never renumbered — so citations round-trip.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .. import util
from . import generated_coverage as gencov
from .options import COVERAGE_MODE_EXPANDED, ENFORCING_COVERAGE_MODES
from .schema import WRITING_PACKET_SCHEMA_VERSION

# Phase C artifact the expanded writing packet surfaces per page (optional read).
_RELEVANT_SOURCE_MAP_REL = "plans/relevant-source-map.json"


@dataclass
class WritingPacket:
    section_id: str
    title: str
    order: int
    data: dict                       # the serializable packet handed to the prompt
    allowed_evidence_ids: list       # this section's own citeable IDs (verbatim)
    required_topics_coverage: list = None  # enhancement: evidenced topic obligations
    content_block_coverage: list = None    # expanded: evidenced content-block obligations


def _evidence_row(ev: dict) -> dict:
    """Compact one EvidencePacket evidence item into a writer-facing row.

    Keeps the verbatim ``evidence_id``, lane/type/confidence, the full source
    anchor metadata (path/range/symbol/route/operation), the excerpt, the
    provenance ``matched_by``, and the lane rank for prioritization."""
    src = ev.get("source") or {}
    prov = ev.get("provenance") or {}
    scores = ev.get("scores") or {}
    row = {
        "evidence_id": ev.get("evidence_id"),
        "lane": ev.get("lane"),
        "type": ev.get("type"),
        "confidence": ev.get("confidence"),
        "source": {
            k: src[k] for k in (
                "artifact", "path", "range", "span_id", "chunk_id", "symbol_id",
                "symbol_name", "json_pointer", "route", "method",
                "public_route", "public_route_source")
            if src.get(k) is not None
        },
        "provenance": {
            k: prov[k] for k in ("matched_by", "symbol_id", "handler_symbol_id",
                                 "x_source", "pack", "input")
            if prov.get(k) is not None
        },
        "lane_rank": scores.get("lane_rank"),
        "excerpt": ev.get("excerpt") or "",
    }
    return row


def build_writing_packet(bundle, sid: str) -> WritingPacket:
    """Assemble the compact WritingPacket for section ``sid`` from the validated
    bundle (document plan + section plan + evidence packet)."""
    doc = bundle.document_plan
    plan = bundle.section_plans[sid]
    pkt = bundle.packets[sid]

    needs = plan.get("retrieval_needs") or {}
    search_hints = [
        h.get("text") if isinstance(h, dict) else h
        for h in (needs.get("search_hints") or [])
    ]
    search_hints = [h for h in search_hints if h]
    context_artifacts = []
    for ca in needs.get("context_artifacts") or []:
        path = ca.get("path") if isinstance(ca, dict) else ca
        if path:
            context_artifacts.append({"path": path, "citeable_as_evidence": False})

    evidence_rows = [_evidence_row(ev) for ev in pkt.get("evidence") or []]
    allowed_ids = [r["evidence_id"] for r in evidence_rows]

    data = {
        "schema_version": WRITING_PACKET_SCHEMA_VERSION,
        "document": {
            "title": doc.get("title") or "",
            "purpose": doc.get("purpose") or "",
            "audience": doc.get("audience") or "",
            "section_order": list(bundle.section_order),
        },
        "section": {
            "section_id": sid,
            "title": plan.get("title") or sid,
            "order": pkt.get("order"),
            "purpose": plan.get("purpose") or "",
            "goal": plan.get("goal") or "",
            "required_topics": list(plan.get("required_topics") or []),
            "key_questions": list(plan.get("key_questions") or []),
            "expected_evidence_types": list(plan.get("expected_evidence_types") or []),
        },
        "orientation_only": {
            "search_hints": search_hints,
            "context_artifacts": context_artifacts,
            "note": ("search_hints and context_artifacts are ORIENTATION ONLY. "
                     "They are NOT citeable. Never cite a context artifact and "
                     "never introduce a fact found only there."),
        },
        "evidence": evidence_rows,
        "allowed_evidence_ids": allowed_ids,
    }

    # DeepWiki coverage enhancement: carry the planned hierarchy and the Phase 3
    # evidenced topic rows so the writer knows the exact required topics it must
    # cover and the exact evidence_ids that support each one.
    required_topics_coverage = None
    content_block_coverage = None
    coverage_mode = getattr(bundle, "coverage_mode", "baseline")
    if coverage_mode in ENFORCING_COVERAGE_MODES:
        obligations = (bundle.topic_obligations or {}).get(sid) or []
        data["hierarchy"] = {
            "parent_section_id": plan.get("parent_section_id"),
            "coverage_labels": list(plan.get("coverage_labels") or []),
            "child_section_ids": gencov.child_section_ids(bundle, sid),
        }
        data["required_topics_coverage"] = [
            {"topic": ob.get("topic"),
             "evidenced_status": ob.get("evidenced_status"),
             "is_obligation": ob.get("is_obligation"),
             "supporting_evidence_ids": list(ob.get("mapped_evidence_ids") or []),
             "min_items": ob.get("min_items")}
            for ob in obligations]
        required_topics_coverage = data["required_topics_coverage"]

    # Expanded (DeepWiki hierarchical) mode: carry the page profile, catalog topics,
    # required content blocks, the Phase D content-block obligations (the exact
    # evidence each block must be written with), and this page's deterministic
    # relevant-source-map rows so the writer renders by content block.
    if coverage_mode == COVERAGE_MODE_EXPANDED:
        block_obs = (getattr(bundle, "content_block_obligations", None) or {}).get(sid) or []
        data["page_profile"] = plan.get("page_profile")
        data["catalog_topic_ids"] = list(plan.get("catalog_topic_ids") or [])
        data["required_content_blocks"] = list(plan.get("required_content_blocks") or [])
        data["content_block_coverage"] = [
            {"content_block_id": ob.get("content_block_id"),
             "evidenced_status": ob.get("evidenced_status"),
             "is_obligation": ob.get("is_obligation"),
             "supporting_evidence_ids": list(ob.get("supporting_evidence_ids") or [])}
            for ob in block_obs]
        content_block_coverage = data["content_block_coverage"]
        data["relevant_source_handles"] = _relevant_source_handles(bundle, sid)

    return WritingPacket(
        section_id=sid,
        title=plan.get("title") or sid,
        order=pkt.get("order"),
        data=data,
        allowed_evidence_ids=allowed_ids,
        required_topics_coverage=required_topics_coverage,
        content_block_coverage=content_block_coverage,
    )


def _relevant_source_handles(bundle, sid: str) -> list:
    """This page's selected source handles from ``plans/relevant-source-map.json``,
    or ``[]`` when the map is absent. Orientation context for the writer — never
    citeable (citations still resolve only through the EvidencePacket manifest)."""
    path = os.path.join(getattr(bundle, "root", ""), _RELEVANT_SOURCE_MAP_REL)
    if not os.path.isfile(path):
        return []
    try:
        source_map = util.read_json(path)
    except (OSError, ValueError):
        return []
    for page in (source_map or {}).get("pages") or []:
        if page.get("section_id") == sid:
            return list(page.get("selected_handles") or [])
    return []
