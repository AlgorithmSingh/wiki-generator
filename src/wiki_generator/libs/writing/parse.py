"""Parse a raw model response into the strict section-draft object.

A response may be clean JSON, JSON wrapped in a ```json fence, or JSON with stray
prose around it (a common Gem artifact). We try, in order: whole-text JSON, a
fenced block, then the first balanced ``{...}`` object. Anything that yields no
parseable object is reported as malformed so the caller can decide whether a
bounded format rewrite is permitted.
"""
from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _balanced_object(text: str) -> str | None:
    """Return the first top-level balanced ``{...}`` substring, honoring strings
    and escapes, or None."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_section_response(raw_text: str) -> tuple[dict | None, str]:
    """Return (parsed_object_or_None, note). Note describes the parse strategy or
    the failure reason (for audit + rewrite feedback)."""
    if raw_text is None:
        return None, "empty response (None)"
    text = raw_text.strip()
    if not text:
        return None, "empty response"

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, "parsed whole-text JSON"
    except (ValueError, json.JSONDecodeError):
        pass

    m = _FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj, "parsed fenced ```json block"
        except (ValueError, json.JSONDecodeError):
            pass

    blob = _balanced_object(text)
    if blob:
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict):
                return obj, "parsed first balanced {...} object"
        except (ValueError, json.JSONDecodeError) as e:
            return None, f"found a {{...}} block but it is not valid JSON: {e}"

    return None, "no JSON object found in response"
