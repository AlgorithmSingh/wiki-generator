"""Deterministic citation + claim validators for one generated section.

These catch the *deterministic* support violations the spec enumerates: citations
that do not resolve to a real EvidencePacket item, citations/laundering of
non-citeable context artifacts, placeholders/apologies, and repo-specific
identifiers that are not present in any available evidence (invented facts). The
checks are intentionally high-precision — an inline ``code span`` that is a path,
dotted module, env var, function call, or route, but is supported by no evidence,
is flagged; ordinary prose is left alone. This validator catches blatant
fabrication; it is not a license for the model to invent plausible facts.
"""
from __future__ import annotations

import re

from ..context_docs import is_generated_context_path
from .schema import CITATION_RE, EVIDENCE_ID_RE, LOOSE_CITATION_RE, PLACEHOLDER_PATTERNS

# Repo-specific identifier shapes (high precision; see module docstring).
_RE_PATH = re.compile(r"^/?[\w.+-]+(?:/[\w.+-]+)+$")          # has a slash
_RE_PATH_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")             # ends with an extension
_RE_DOTTED = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*){2,}$")  # a.b.c module
_RE_ENV = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")     # ENV_VAR_NAME
_RE_CALL = re.compile(r"^([A-Za-z_][\w.]*)\(\)?$")           # func() / a.b.func()
_RE_ROUTE = re.compile(r"^/[\w/{}.:-]+$")                     # /agents, /v1/{id}
_RE_METHOD_PATH = re.compile(
    r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[\w/{}.:-]*)$")

_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_FENCE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s")


# --- citation extraction ------------------------------------------------------
def extract_citations(markdown: str) -> list[str]:
    """Ordered list of well-formed evidence-id tokens cited in ``markdown``
    (one entry per occurrence, in document order)."""
    return CITATION_RE.findall(markdown or "")


def distinct_citations(markdown: str) -> list[str]:
    seen: list[str] = []
    for c in extract_citations(markdown):
        if c not in seen:
            seen.append(c)
    return seen


def loose_citation_tokens(markdown: str) -> list[str]:
    """``ev:...`` tokens that look like citations but may be malformed (missing
    brackets, wrong digit width). Used to give the rewrite useful feedback."""
    return LOOSE_CITATION_RE.findall(markdown or "")


# --- context-artifact / non-source laundering ---------------------------------
_PLAN_REFS = (
    "plans/document-plan.json", "plans/section-plans.jsonl",
    "phase3-readiness-report.md", "normalization-report.md",
    "retrieval-validation.json", "retrieval-report.md", "evidence-manifest.json",
)


def find_context_artifact_references(markdown: str) -> list[str]:
    """Inline code spans that name a non-citeable BUNDLE artifact — a plan,
    derived/condensate, readiness/normalization report, or prior wiki output
    (diagnostic laundering).

    Matching is restricted to references under a known bundle subtree
    (``plans/`` ``derived/`` ``planner-digest/`` ``wiki/``), the bundle's own
    generated context namespaces, or an exact bundle report filename. A target
    repo file that merely *shares a basename* with a context doc (e.g. its own
    ``docs/repo-summary.md``) is deliberately NOT flagged, so legitimate prose is
    never failed."""
    offenders: list[str] = []
    for span in _INLINE_CODE_RE.findall(markdown or ""):
        token = span.strip().split()[0] if span.strip() else ""
        norm = token.replace("\\", "/")
        if (norm.startswith(("plans/", "derived/", "planner-digest/", "wiki/"))
                or is_generated_context_path(norm)
                or any(norm == p or norm.endswith("/" + p) for p in _PLAN_REFS)):
            offenders.append(token)
    return offenders


# --- placeholders -------------------------------------------------------------
def find_placeholders(markdown: str) -> list[str]:
    md = markdown or ""
    hits: list[str] = []
    for pat in PLACEHOLDER_PATTERNS:
        m = pat.search(md)
        if m:
            hits.append(m.group(0).strip())
    hits += _empty_headings(md)
    # de-dup, preserve order
    out: list[str] = []
    for h in hits:
        if h not in out:
            out.append(h)
    return out


def _heading_level(line: str) -> int | None:
    m = _HEADING_RE.match(line)
    return len(m.group(1)) if m else None


def _empty_headings(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        level = _heading_level(line)
        if level is None:
            continue
        # A heading owns content until the next same-or-higher-level heading.
        # Descendant headings are allowed: a grouping heading is not empty when
        # one of its nested subsections contains body text.
        has_body = False
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                continue
            nxt_level = _heading_level(nxt)
            if nxt_level is not None and nxt_level <= level:
                break
            if nxt_level is None:
                has_body = True
                break
        if not has_body:
            out.append(f"empty heading: {line.strip()}")
    return out


# --- identifier support / invented-fact detection -----------------------------
def _candidate_identifiers(span: str) -> list[tuple[str, str]]:
    """Return [(kind, needle)] repo-specific identifiers extracted from a code
    span (kind in path/dotted/env/call/route/method)."""
    s = span.strip()
    if not s:
        return []
    out: list[tuple[str, str]] = []
    m = _RE_METHOD_PATH.match(s)
    if m:
        out.append(("route", m.group(2)))
        return out
    if s.startswith("/") and len(s) > 1 and _RE_ROUTE.match(s):
        # a leading-slash route like /agents or /v1/{id}
        out.append(("route", s))
        return out
    if _RE_PATH.match(s) and (_RE_PATH_EXT.search(s) or s.startswith("/")):
        out.append(("path", s))
        return out
    if _RE_DOTTED.match(s):
        out.append(("dotted", s))
        return out
    if _RE_ENV.match(s):
        out.append(("env", s))
        return out
    m = _RE_CALL.match(s)
    if m:
        out.append(("call", m.group(1)))
        return out
    return []


def _supported(kind: str, needle: str, available: str) -> bool:
    if kind == "call":
        # the bare symbol name must appear (def name / name( / symbol_id name())
        return needle in available
    if kind == "dotted":
        return needle in available or needle.replace(".", "/") in available
    if kind == "route":
        return needle in available
    if kind == "path":
        # Require the FULL path to appear in available evidence — never a bare
        # basename. Evidence source metadata always carries full repo paths, so a
        # bare-basename match would let an invented path (e.g. app/ghost.py) slip
        # through merely because some unrelated test/ghost.py exists in evidence.
        n = needle.lstrip("/")
        return n in available or needle in available
    return needle in available


def _strip_code_and_headings(markdown: str) -> list[str]:
    """Paragraph blocks with fenced code removed and headings dropped."""
    no_fence = _FENCE_BLOCK_RE.sub("\n\n", markdown or "")
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n", no_fence):
        lines = [ln for ln in block.splitlines() if not _HEADING_RE.match(ln)]
        text = "\n".join(lines).strip()
        if text:
            blocks.append(text)
    return blocks


def analyze_claims(markdown: str, available_text: str) -> dict:
    """Return invented identifiers (terminal) and uncited-claim paragraphs
    (rewriteable). ``available_text`` is the concatenation of every excerpt and
    source-metadata blob the section may rely on."""
    invented: list[str] = []
    # 1. invented identifiers anywhere (inline spans + fenced path/route tokens)
    seen_inv: set = set()
    for span in _INLINE_CODE_RE.findall(markdown or ""):
        for kind, needle in _candidate_identifiers(span):
            if not _supported(kind, needle, available_text) and needle not in seen_inv:
                invented.append(needle)
                seen_inv.add(needle)
    for block in _FENCE_BLOCK_RE.findall(markdown or ""):
        for tok in re.findall(r"[/\w.+{}:-]+", block):
            if "/" in tok and _RE_PATH.match(tok) and _RE_PATH_EXT.search(tok):
                if tok not in available_text and tok.lstrip("/") not in available_text \
                        and tok not in seen_inv:
                    invented.append(tok)
                    seen_inv.add(tok)

    # 2. uncited repo-claim paragraphs (supported identifier present, no citation)
    uncited: list[str] = []
    for block in _strip_code_and_headings(markdown):
        if CITATION_RE.search(block):
            continue
        groundable = False
        for span in _INLINE_CODE_RE.findall(block):
            for kind, needle in _candidate_identifiers(span):
                if _supported(kind, needle, available_text):
                    groundable = True
                    break
            if groundable:
                break
        if groundable:
            snippet = " ".join(block.split())[:120]
            uncited.append(snippet)
    return {"invented_identifiers": invented, "uncited_paragraphs": uncited}


# --- citation resolution ------------------------------------------------------
def resolve_citations(markdown: str, *, section_id: str, evidence_index: dict,
                      section_evidence_ids: dict) -> dict:
    """Resolve every citation token. Returns a structured result:

    - ``resolved``: ordered distinct ids that resolve to a real evidence item;
    - ``unresolved``: tokens that do not resolve at all;
    - ``cross_section``: resolved ids owned by another section's packet;
    - ``malformed_like``: loose ``ev:`` tokens that are not well-formed citations.
    """
    distinct = distinct_citations(markdown)
    resolved: list[str] = []
    unresolved: list[str] = []
    cross_section: list[str] = []
    own = section_evidence_ids.get(section_id, set())
    for token in distinct:
        if not EVIDENCE_ID_RE.match(token):
            unresolved.append(token)
            continue
        item = evidence_index.get(token)
        if item is None:
            unresolved.append(token)
            continue
        resolved.append(token)
        if token not in own:
            cross_section.append(token)

    # loose ev: tokens that never became a well-formed [ev:...] citation
    well_formed = set(distinct)
    malformed_like = [t for t in loose_citation_tokens(markdown)
                      if t not in well_formed and f"[{t}]" not in markdown]
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "cross_section": cross_section,
        "malformed_like": malformed_like,
    }
