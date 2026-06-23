"""Build a compact, model-safe ``WritingPacket`` for one section.

The model never receives the raw bundle. For each section we join the
``DocumentPlan`` row, the ``SectionPlan`` work order, and the validated
``EvidencePacket`` into a bounded packet: section intent, orientation-only
search hints, explicitly non-citeable context artifacts, and a deduplicated
evidence table whose ``evidence_id`` values are the *only* citeable handles.
Evidence IDs are copied verbatim — never renumbered — so citations round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import WRITING_PACKET_SCHEMA_VERSION


@dataclass
class WritingPacket:
    section_id: str
    title: str
    order: int
    data: dict                       # the serializable packet handed to the prompt
    allowed_evidence_ids: list       # this section's own citeable IDs (verbatim)


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
                "symbol_name", "json_pointer", "route", "method")
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
    return WritingPacket(
        section_id=sid,
        title=plan.get("title") or sid,
        order=pkt.get("order"),
        data=data,
        allowed_evidence_ids=allowed_ids,
    )
