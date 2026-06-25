"""Phase 4 artifact schema versions, constants, and the model-response contract.

This module owns the *output* contract Phase 4 writes (generated section/document
metadata, citation manifest, writing validation) and the *input* contract the
model must satisfy (the section-draft JSON). Validation logic that needs the
loaded bundle (citations, claims) lives in ``citations``/``validate``; this file
holds only shape constants and a pure structural validator for one draft.
"""
from __future__ import annotations

import re

# --- schema versions ----------------------------------------------------------
SECTION_DRAFT_SCHEMA_VERSION = "phase4-section-draft-v1"
GENERATED_SECTION_SCHEMA_VERSION = "phase4-generated-section-v1"
GENERATED_DOCUMENT_SCHEMA_VERSION = "phase4-generated-document-v1"
CITATION_MANIFEST_SCHEMA_VERSION = "phase4-citation-manifest-v1"
WRITING_VALIDATION_SCHEMA_VERSION = "phase4-writing-validation-v1"
WRITING_PACKET_SCHEMA_VERSION = "phase4-writing-packet-v1"
# DeepWiki coverage enhancement (Phase 4 generated coverage) artifact version.
GENERATED_COVERAGE_SCHEMA_VERSION = "phase4-generated-coverage-v1"

# --- citation syntax ----------------------------------------------------------
# Inline evidence-ID citation: [ev:<section_id>:<four_digit_ordinal>].
# section_id is a slug (lowercase letters/digits/hyphens); ordinal is 4 digits.
CITATION_RE = re.compile(r"\[(ev:[a-z0-9][a-z0-9-]*:\d{4})\]")
EVIDENCE_ID_RE = re.compile(r"^ev:[a-z0-9][a-z0-9-]*:\d{4}$")
# The canonical section-id grammar, on its own (used to classify malformed tokens).
SECTION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# A loosely-formed citation the model may have produced (for rewrite feedback):
# tolerates spaces, missing brackets, or wrong digit width around an ev: token.
LOOSE_CITATION_RE = re.compile(r"ev:[a-z0-9][a-z0-9-]*:\d{1,6}")
# Any bracketed evidence-LIKE token. Two shapes, tried in order:
#   1. a *closed* token ``[ev:...]`` running to the first ``]`` on the same line
#      (this keeps the malformed "extra text" case ``[ev:x:0010 extra]`` intact);
#   2. a *dangling* opener ``[ev:...`` with no closer, stopping at the first
#      whitespace — a real citation has no internal whitespace, so this avoids
#      swallowing the rest of the line.
# Both inner classes exclude ``[``/``]`` so adjacent citations
# (``[ev:a:0001][ev:b:0002]``) never merge into one match. Every match is then
# checked against the canonical ``EVIDENCE_ID_RE``; anything that is not exactly
# ``[ev:<section_id>:<NNNN>]`` is a malformed citation that must fail validation.
EV_LIKE_TOKEN_RE = re.compile(r"\[ev:[^\[\]\n]*\]|\[ev:[^\[\]\s]*")

# Provider finish reasons that indicate complete, trustworthy output.
GOOD_FINISH_REASONS = frozenset({"STOP", "stop", "imported", "complete", "COMPLETE"})
TRUNCATION_FINISH_REASONS = frozenset({"MAX_TOKENS", "max_tokens", "length", "LENGTH"})

# Placeholder / apology markers that must never reach final prose.
PLACEHOLDER_PATTERNS = (
    re.compile(r"\btodo\b", re.IGNORECASE),
    re.compile(r"\btbd\b", re.IGNORECASE),
    re.compile(r"\bfixme\b", re.IGNORECASE),
    re.compile(r"\bxxx\b"),
    re.compile(r"needs?\s+citation", re.IGNORECASE),
    re.compile(r"add\s+more\s+detail", re.IGNORECASE),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"\[\s*(?:todo|tbd|fill in|insert)\b", re.IGNORECASE),
    re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    # model apologies / meta self-talk
    re.compile(r"\bas an ai\b", re.IGNORECASE),
    re.compile(r"\bi (?:cannot|can't|am unable to|was unable to)\b", re.IGNORECASE),
    re.compile(r"\bi (?:apologize|'m sorry|am sorry)\b", re.IGNORECASE),
    re.compile(r"\bi do not have (?:access|enough)\b", re.IGNORECASE),
)

_REQUIRED_DRAFT_KEYS = ("schema_version", "section_id", "title", "markdown")


def structural_draft_errors(draft, *, expected_section_id: str) -> list[str]:
    """Pure structural validation of one parsed section-draft object.

    Returns a list of violation strings (empty == structurally valid). Does NOT
    check citations or claims (those need the evidence index)."""
    errors: list[str] = []
    if not isinstance(draft, dict):
        return [f"section draft is not a JSON object: {type(draft).__name__}"]

    for key in _REQUIRED_DRAFT_KEYS:
        if key not in draft:
            errors.append(f"missing required draft key '{key}'")

    sv = draft.get("schema_version")
    if sv is not None and sv != SECTION_DRAFT_SCHEMA_VERSION:
        errors.append(
            f"schema_version {sv!r} != {SECTION_DRAFT_SCHEMA_VERSION!r}")

    sid = draft.get("section_id")
    if sid != expected_section_id:
        errors.append(
            f"section_id {sid!r} does not match requested {expected_section_id!r}")

    md = draft.get("markdown")
    if not isinstance(md, str) or not md.strip():
        errors.append("markdown is missing or empty")

    used = draft.get("used_evidence_ids")
    if used is not None and not isinstance(used, list):
        errors.append("used_evidence_ids must be a list when present")

    return errors
