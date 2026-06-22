"""Deterministic SectionPlan -> recall query text for the BM25 and vector lanes.

Both recall lanes embed/search the *same* query string so their hits describe
the same section intent. The string is built by joining normalized fields in a
fixed order, dropping duplicates while preserving first occurrence.
"""
from __future__ import annotations


def _push(seen: set, out: list, value) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    key = text.lower()
    if key in seen:
        return
    seen.add(key)
    out.append(text)


def build_query_text(section: dict) -> str:
    """Join section fields into one deterministic recall query string.

    Field order (spec "BM25" / "Vectors"): title, purpose, goal, required_topics,
    key_questions, verification_needs, then unresolved retrieval-need hints.
    """
    seen: set = set()
    parts: list = []
    _push(seen, parts, section.get("title"))
    _push(seen, parts, section.get("purpose"))
    _push(seen, parts, section.get("goal"))
    for field in ("required_topics", "key_questions", "verification_needs"):
        for value in section.get(field) or []:
            _push(seen, parts, value)

    # Unresolved retrieval-need hints: the original reference text is still a
    # useful recall signal even though it never resolved to exact evidence.
    needs = section.get("retrieval_needs") or {}
    for sym in needs.get("symbols") or []:
        if sym.get("resolution") not in ("exact", "unique_alias"):
            _push(seen, parts, sym.get("input"))
    for f in needs.get("files") or []:
        if not f.get("path"):
            _push(seen, parts, f.get("input"))
    for c in needs.get("contracts") or []:
        if c.get("resolution") in ("no_match", "hint"):
            _push(seen, parts, c.get("input"))
    for t in needs.get("tests") or []:
        if t.get("resolution") in ("ambiguous", "hint"):
            _push(seen, parts, t.get("input"))

    # Explicit search hints: broad recall text the normalizer routed here from a
    # non-exact exact-lane reference, or that the planner supplied directly. They
    # only steer BM25/vector recall — never exact symbol/file/contract evidence.
    for h in needs.get("search_hints") or []:
        _push(seen, parts, h.get("text") if isinstance(h, dict) else h)

    return " ".join(parts)
