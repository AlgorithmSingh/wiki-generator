"""Deterministic parsing of a Phase 2 planning LLM response (Gemini/Kimi).

The raw response is markdown containing fenced code blocks. The planner is asked
to emit three artifacts, each typically preceded by a one-line ``text`` fence
naming the file (a fence whose only content is e.g. ``plans/document-plan.json``).
We scan the fenced blocks, associate each with its preceding name-fence when
present, then pick out:

* the **DocumentPlan** — a fenced JSON object (labelled ``document-plan.json`` or,
  failing that, the single JSON object that contains a ``sections`` array);
* the **SectionPlans** — a fenced JSONL block (labelled ``section-plans.jsonl`` or
  the single ``jsonl`` block), or a JSON array of section objects.

No LLM and no fuzzy repair: only simple, logged fixes (smart-quote normalisation
before ``json.loads``). If the response is structurally ambiguous — more than one
plausible DocumentPlan or SectionPlans block — we raise rather than guess.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

# A name token is a path ending in a known extension.
_NAME_RE = re.compile(r"^[\w./\-]+\.(?:json|jsonl|md)$")
# A fence line: 3+ backticks/tildes followed by an arbitrary info string.
_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")

_SMART = {
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "–": "-", "—": "-",
}


class ParseError(ValueError):
    """The raw response could not be parsed into a plan unambiguously."""


@dataclass
class Block:
    lang: str
    content: str
    label: str | None = None


@dataclass
class RawPlan:
    document_plan: dict
    section_plans: list[dict]
    doc_plan_md: str | None = None
    warnings: list[str] = field(default_factory=list)


# --- fenced-block scanning -----------------------------------------------------
def _parse_info(info: str) -> tuple[str, str | None]:
    """Split a fence info string into (language, label). The label is the first
    path-like token ending in .json/.jsonl/.md, e.g. both ``json`` and the label
    ``document-plan.json`` from ``json plans/document-plan.json``."""
    info = info.strip()
    if not info:
        return "", None
    tokens = info.split()
    lang = tokens[0].lower()
    label = None
    for t in tokens:
        if _NAME_RE.match(t):
            label = os.path.basename(t)
            break
    if label is not None and len(tokens) == 1:
        lang = ""  # the lone token was a filename, not a language
    return lang, label


def _scan_blocks(text: str) -> list[Block]:
    """Toggle-scan fenced code blocks. Opening fences may carry a language and/or
    a filename in their info string; closing fences are bare. Content verbatim."""
    blocks: list[Block] = []
    inside = False
    lang = ""
    label: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        m = _FENCE_LINE.match(line)
        if not inside:
            if m:
                lang, label = _parse_info(m.group(2))
                inside, body = True, []
            continue
        if m and m.group(2).strip() == "":  # a bare fence closes the block
            blocks.append(Block(lang=lang, content="\n".join(body), label=label))
            inside, lang, label, body = False, "", None, []
            continue
        body.append(line)
    if inside and body:  # tolerate an unterminated final block
        blocks.append(Block(lang=lang, content="\n".join(body), label=label))
    return blocks


def _label_blocks(blocks: list[Block]) -> list[Block]:
    """Resolve each block's label. A block whose info string already named a file
    keeps that label. Otherwise a preceding name-only fence (a ``text`` fence whose
    body is just ``plans/document-plan.json``) labels the block that follows it."""
    out: list[Block] = []
    pending: str | None = None
    for b in blocks:
        c = b.content.strip()
        if (b.label is None and b.lang in ("", "text", "plaintext")
                and "\n" not in c and _NAME_RE.match(c)):
            pending = os.path.basename(c)
            continue
        out.append(Block(lang=b.lang, content=b.content, label=b.label or pending))
        pending = None
    return out


# --- JSON helpers --------------------------------------------------------------
def _loads(text: str, warnings: list[str], what: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = "".join(_SMART.get(ch, ch) for ch in text)
        if repaired != text:
            try:
                obj = json.loads(repaired)
                warnings.append(f"{what}: applied smart-quote repair before parsing")
                return obj
            except json.JSONDecodeError:
                pass
        raise ParseError(f"{what}: not valid JSON")


def _loads_jsonl(text: str, warnings: list[str], what: str) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            repaired = "".join(_SMART.get(ch, ch) for ch in line)
            try:
                rows.append(json.loads(repaired))
                warnings.append(f"{what}: smart-quote repair on line {i}")
            except json.JSONDecodeError:
                warnings.append(f"{what}: skipped unparseable line {i}")
    return rows


def _is_doc(obj) -> bool:
    return isinstance(obj, dict) and ("sections" in obj or "section_order" in obj)


# --- heading-based fallback (accepted raw format #4) ---------------------------
_DOC_HEAD = re.compile(r"document\s*[-_ ]?\s*plan", re.I)
_SEC_HEAD = re.compile(r"section\s*[-_ ]?\s*plans?", re.I)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


def _heading_regions(text: str) -> list[tuple[str, str]]:
    """(heading_text, body_until_next_heading) for each markdown heading."""
    lines = text.split("\n")
    heads = [(i, m.group(1)) for i, m in
             ((j, _HEADING.match(ln)) for j, ln in enumerate(lines)) if m]
    out = []
    for k, (i, htext) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        out.append((htext, "\n".join(lines[i + 1:end])))
    return out


def _balanced(region: str, open_ch: str, close_ch: str) -> str | None:
    """First string-aware balanced ``open_ch..close_ch`` span, or None."""
    start = region.find(open_ch)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(start, len(region)):
        c = region[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return region[start:j + 1]
    return None


def _doc_from_headings(text: str, warnings: list[str]) -> dict | None:
    cands = []
    for htext, body in _heading_regions(text):
        if _DOC_HEAD.search(htext) and not _SEC_HEAD.search(htext):
            raw = _balanced(body, "{", "}")
            if not raw:
                continue
            try:
                obj = _loads(raw, warnings, "document-plan (heading)")
            except ParseError:
                continue
            if isinstance(obj, dict):
                cands.append(obj)
    if not cands:
        return None
    if len(cands) > 1:
        raise ParseError("multiple DocumentPlan headings; refusing to guess")
    warnings.append("DocumentPlan extracted from a markdown heading (format #4)")
    return cands[0]


def _sections_from_headings(text: str, warnings: list[str]) -> list[dict] | None:
    for htext, body in _heading_regions(text):
        if not _SEC_HEAD.search(htext):
            continue
        arr = _balanced(body, "[", "]")
        if arr:
            try:
                obj = _loads(arr, warnings, "section-plans (heading)")
            except ParseError:
                obj = None
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                warnings.append("SectionPlans extracted from a markdown heading (format #4)")
                return obj
        json_lines = [ln for ln in body.splitlines() if ln.strip().startswith("{")]
        if json_lines:
            rows = _loads_jsonl("\n".join(json_lines), warnings, "section-plans (heading)")
            rows = [r for r in rows if isinstance(r, dict) and r]
            if rows:
                warnings.append("SectionPlans extracted from a markdown heading (format #4)")
                return rows
    return None


# --- selection -----------------------------------------------------------------
def _pick_document_plan(blocks: list[Block], warnings: list[str], text: str) -> dict:
    labelled = [b for b in blocks if b.label == "document-plan.json"]
    if len(labelled) > 1:
        raise ParseError("multiple blocks labelled document-plan.json")
    if labelled:
        obj = _loads(labelled[0].content, warnings, "document-plan.json")
        if not isinstance(obj, dict):
            raise ParseError("document-plan.json is not a JSON object")
        return obj
    # Fallback (#2): the single JSON object that looks like a DocumentPlan.
    cands = []
    for b in blocks:
        if b.lang in ("json", "json5", "jsonc"):
            try:
                obj = _loads(b.content, warnings, "document-plan")
            except ParseError:
                continue
            if _is_doc(obj):
                cands.append(obj)
    if len(cands) > 1:
        raise ParseError("multiple plausible DocumentPlan JSON blocks; refusing to guess")
    if cands:
        return cands[0]
    # Fallback (#4): a markdown DocumentPlan heading with raw JSON beneath it.
    obj = _doc_from_headings(text, warnings)
    if obj is not None:
        return obj
    raise ParseError("no DocumentPlan found (need a JSON object with a 'sections' "
                     "array, a fence labelled document-plan.json, or a DocumentPlan "
                     "markdown heading)")


def _pick_section_plans(blocks: list[Block], warnings: list[str], text: str) -> list[dict]:
    labelled = [b for b in blocks if b.label == "section-plans.jsonl"]
    if len(labelled) > 1:
        raise ParseError("multiple blocks labelled section-plans.jsonl")
    if labelled:
        return _loads_jsonl(labelled[0].content, warnings, "section-plans.jsonl")
    jsonl_blocks = [b for b in blocks if b.lang in ("jsonl", "ndjson")]
    if len(jsonl_blocks) > 1:
        raise ParseError("multiple JSONL blocks; refusing to guess which is section-plans")
    if jsonl_blocks:
        return _loads_jsonl(jsonl_blocks[0].content, warnings, "section-plans.jsonl")
    # Fallback (#3): a JSON array of section objects.
    arrays = []
    for b in blocks:
        if b.lang in ("json", "json5", "jsonc"):
            try:
                obj = _loads(b.content, warnings, "section-plans")
            except ParseError:
                continue
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                arrays.append(obj)
    if len(arrays) > 1:
        raise ParseError("multiple plausible SectionPlans arrays; refusing to guess")
    if arrays:
        return arrays[0]
    # Fallback (#4): a markdown SectionPlans heading with raw JSON/JSONL beneath it.
    rows = _sections_from_headings(text, warnings)
    if rows is not None:
        return rows
    raise ParseError("no SectionPlans found (need a JSONL block, a JSON array, a "
                     "fence labelled section-plans.jsonl, or a SectionPlans "
                     "markdown heading)")


def _pick_doc_md(blocks: list[Block]) -> str | None:
    for b in blocks:
        if b.label == "document-plan.md":
            return b.content
    for b in blocks:
        if b.lang in ("markdown", "md"):
            return b.content
    return None


def parse(text: str) -> RawPlan:
    """Parse a raw planning response into a :class:`RawPlan`. Raises
    :class:`ParseError` on ambiguous or missing required blocks."""
    warnings: list[str] = []
    blocks = _label_blocks(_scan_blocks(text))
    document_plan = _pick_document_plan(blocks, warnings, text)
    section_plans = _pick_section_plans(blocks, warnings, text)
    doc_md = _pick_doc_md(blocks)
    return RawPlan(document_plan=document_plan, section_plans=section_plans,
                   doc_plan_md=doc_md, warnings=warnings)
