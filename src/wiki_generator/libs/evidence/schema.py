"""EvidencePacket / manifest / validation schema constants + a packet validator.

This module owns the *output* contract (the JSON shapes Phase 3 writes). The
internal raw-hit model used while retrieving lives in ``model.py``.
"""
from __future__ import annotations

# --- schema versions ----------------------------------------------------------
PACKET_SCHEMA_VERSION = "phase3-evidence-packet-v1"
MANIFEST_SCHEMA_VERSION = "phase3-evidence-manifest-v1"
VALIDATION_SCHEMA_VERSION = "phase3-retrieval-validation-v1"

# --- deterministic excerpt cap ------------------------------------------------
# Source text copied into an evidence excerpt is clipped to this many chars so
# packets stay bounded and byte-identical across reruns.
EVIDENCE_EXCERPT_CHARS = 1200

# --- allowed enums (spec "Evidence item rules") -------------------------------
ALLOWED_LANES = frozenset({
    "file_anchor", "symbol_anchor", "query_pack", "contract", "test",
    "graph_neighbors", "bm25", "vector",
})
ALLOWED_CONFIDENCE = frozenset({"exact", "high", "medium", "low"})
ALLOWED_LANE_STATUS = frozenset({
    "pass", "miss", "not_requested", "capability_disabled", "unavailable", "empty",
})

# --- failure categories (spec "Failure categories") + exit codes --------------
CAT_BAD_INPUT = "bad_missing_input_artifact"
CAT_BAD_PLAN = "bad_underspecified_normalized_plan"
CAT_BUG = "retriever_implementation_bug"

EXIT_OK = 0
EXIT_BUG = 1
EXIT_BAD_INPUT = 2
EXIT_BAD_PLAN = 3

EXIT_FOR_CATEGORY = {
    None: EXIT_OK,
    CAT_BAD_INPUT: EXIT_BAD_INPUT,
    CAT_BAD_PLAN: EXIT_BAD_PLAN,
    CAT_BUG: EXIT_BUG,
}

_REQUIRED_PACKET_KEYS = (
    "schema_version", "section_id", "title", "order", "retrieval_mode",
    "source_plan", "work_order", "evidence", "lane_summary", "coverage",
    "validation",
)
_REQUIRED_EVIDENCE_KEYS = (
    "evidence_id", "lane", "type", "source", "excerpt", "provenance",
    "scores", "confidence", "dedupe_key",
)


def validate_packet(packet: dict) -> list[str]:
    """Return a list of schema-violation strings for one EvidencePacket.

    A schema-valid input must never yield a schema-invalid packet, so any error
    here is treated by the caller as a retriever implementation bug.
    """
    errors: list[str] = []
    if not isinstance(packet, dict):
        return [f"packet is not an object: {type(packet).__name__}"]

    sid = packet.get("section_id", "<unknown>")
    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        errors.append(f"{sid}: schema_version != {PACKET_SCHEMA_VERSION}")
    for key in _REQUIRED_PACKET_KEYS:
        if key not in packet:
            errors.append(f"{sid}: missing packet key '{key}'")

    if not isinstance(packet.get("order"), int):
        errors.append(f"{sid}: order is not an int")

    seen_ids: set[str] = set()
    evidence = packet.get("evidence")
    if not isinstance(evidence, list):
        errors.append(f"{sid}: evidence is not a list")
        evidence = []
    for i, item in enumerate(evidence):
        errors.extend(_validate_evidence_item(sid, i, item, seen_ids))
    return errors


def _validate_evidence_item(sid: str, i: int, item, seen_ids: set[str]) -> list[str]:
    out: list[str] = []
    if not isinstance(item, dict):
        return [f"{sid}: evidence[{i}] is not an object"]
    for key in _REQUIRED_EVIDENCE_KEYS:
        if key not in item:
            out.append(f"{sid}: evidence[{i}] missing key '{key}'")

    eid = item.get("evidence_id")
    if eid in seen_ids:
        out.append(f"{sid}: duplicate evidence_id '{eid}'")
    elif isinstance(eid, str):
        seen_ids.add(eid)

    lane = item.get("lane")
    if lane not in ALLOWED_LANES:
        out.append(f"{sid}: evidence[{i}] illegal lane '{lane}'")
    conf = item.get("confidence")
    if conf not in ALLOWED_CONFIDENCE:
        out.append(f"{sid}: evidence[{i}] illegal confidence '{conf}'")

    source = item.get("source")
    if not isinstance(source, dict):
        out.append(f"{sid}: evidence[{i}] source is not an object")
    else:
        if not source.get("artifact"):
            out.append(f"{sid}: evidence[{i}] source missing artifact")
        anchored = any(source.get(k) for k in
                       ("span_id", "chunk_id", "json_pointer", "symbol_id")) or (
            source.get("path") and isinstance(source.get("range"), dict))
        if not anchored:
            out.append(f"{sid}: evidence[{i}] has no stable source anchor")

    if not isinstance(item.get("excerpt"), str):
        out.append(f"{sid}: evidence[{i}] excerpt is not a string")
    return out
