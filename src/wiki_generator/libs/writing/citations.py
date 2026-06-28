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
from .schema import (
    CITATION_RE,
    EV_LIKE_TOKEN_RE,
    EVIDENCE_ID_RE,
    LOOSE_CITATION_RE,
    PLACEHOLDER_PATTERNS,
    SECTION_ID_RE,
)

# Repo-specific identifier shapes (high precision; see module docstring).
_RE_PATH = re.compile(r"^/?[\w.+-]+(?:/[\w.+-]+)+$")          # has a slash
_RE_PATH_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")             # ends with an extension
_RE_DOTTED = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*){1,}$")  # a.b or a.b.c
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


# --- malformed evidence-token detection ---------------------------------------
# The canonical citation is exactly ``[ev:<section_id>:<NNNN>]`` (four-digit
# ordinal, manifest-resolving). Anything that *begins like* an evidence citation
# but is not canonical — a wrong-width ordinal, a missing ordinal, a dangling
# opener, extra text/fields, an invalid section id, or an unbracketed ``ev:`` near
# token — is a malformed citation that must fail validation loudly (it must never
# be silently dropped the way the live ``[ev:data-models:010]`` token was).
_LEADING_DIGITS_RE = re.compile(r"\d+")


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based ``(line, column)`` for a character ``offset`` into ``text``."""
    prefix = text[:offset]
    line = prefix.count("\n") + 1
    col = offset - prefix.rfind("\n")        # rfind == -1 (no newline) -> offset+1
    return line, col


def _normalized_candidate(core: str) -> str | None:
    """A deterministically normalized evidence id (no brackets) for ``core`` (the
    inside of a malformed token, starting ``ev:``) when a SAFE zero-padding /
    extra-trim normalization applies, else ``None``.

    Only simple, value-preserving fixes are offered: the section id must already be
    valid, and the ordinal field's *leading* digit run must fit in four digits.
    A section id is never guessed; an absent ordinal is never fabricated."""
    parts = core.split(":")
    if len(parts) < 3 or parts[0] != "ev":
        return None
    sid = parts[1]
    if not SECTION_ID_RE.match(sid):
        return None
    m = _LEADING_DIGITS_RE.match(parts[2].strip())
    if not m:
        return None
    val = int(m.group(0))
    if val >= 10000:                         # no four-digit representation
        return None
    return f"ev:{sid}:{val:04d}"


def classify_malformed_evidence_token(token: str) -> dict:
    """Classify one non-canonical evidence-like ``token`` (starts ``[ev:``; may or
    may not end ``]``). Returns ``{category, remediation, candidate}`` where
    ``candidate`` is a safe normalized id (see :func:`_normalized_candidate`) or
    ``None``. The caller must confirm the candidate exists in the manifest before
    surfacing it as a suggestion."""
    closed = token.endswith("]")
    core = token[1:-1] if closed else token[1:]   # drop '[' and any trailing ']'
    candidate = _normalized_candidate(core)
    if not closed:
        return {"category": "dangling_opener", "candidate": candidate,
                "remediation": "missing closing ']'; a citation must be exactly "
                               "one bracketed token [ev:<section_id>:<NNNN>]"}
    parts = core.split(":")                  # parts[0] == 'ev'
    if len(parts) == 2:
        return {"category": "missing_ordinal_separator", "candidate": candidate,
                "remediation": "no ':<NNNN>' ordinal; expected "
                               "[ev:<section_id>:<NNNN>] with a four-digit ordinal"}
    if len(parts) > 3:
        return {"category": "extra_field", "candidate": candidate,
                "remediation": "extra ':' field; expected exactly "
                               "[ev:<section_id>:<NNNN>]"}
    sid, ordinal = parts[1], parts[2]
    if not SECTION_ID_RE.match(sid):
        return {"category": "invalid_section_id", "candidate": candidate,
                "remediation": "section id must match [a-z0-9][a-z0-9-]* "
                               "(lowercase, no spaces)"}
    if ordinal == "":
        return {"category": "missing_ordinal", "candidate": candidate,
                "remediation": "add a four-digit ordinal, e.g. :0001"}
    if not ordinal.isdigit():
        return {"category": "malformed_ordinal", "candidate": candidate,
                "remediation": "ordinal must be exactly four digits with no extra "
                               "text"}
    return {"category": "wrong_ordinal_width", "candidate": candidate,
            "remediation": f"ordinal '{ordinal}' must be exactly four digits "
                           "(zero-padded), e.g. 0001"}


def find_malformed_evidence_tokens(markdown: str, *, section_id: str | None = None,
                                   section_file: str | None = None) -> list[dict]:
    """Every evidence-like token in ``markdown`` that is NOT a canonical
    ``[ev:<section_id>:<NNNN>]`` citation, as ordered diagnostics.

    Detects three shapes: malformed bracketed tokens (wrong ordinal width, missing
    ordinal, invalid section id, extra text/fields), dangling ``[ev:`` openers, and
    bare unbracketed ``ev:`` near-citations. Each diagnostic carries the token
    text, ``category``, ``remediation``, a normalized ``candidate`` id (or ``None``),
    1-based ``line``/``column``, and any ``section_id``/``section_file`` context.
    Canonical citations are not reported here (they resolve via the manifest)."""
    md = markdown or ""
    diags: list[dict] = []
    consumed: list[tuple[int, int]] = []     # spans covered by a bracketed [ev:...]

    def base(token, start) -> dict:
        line, col = _line_col(md, start)
        return {"token": token, "line": line, "column": col,
                "section_id": section_id, "section_file": section_file}

    for m in EV_LIKE_TOKEN_RE.finditer(md):
        consumed.append((m.start(), m.end()))
        token = m.group(0)
        closed = token.endswith("]")
        core = token[1:-1] if closed else token[1:]
        if closed and EVIDENCE_ID_RE.match(core):
            continue                         # canonical citation — not malformed
        d = base(token, m.start())
        d.update(classify_malformed_evidence_token(token))
        diags.append(d)

    # bare ``ev:...`` near-citations not already inside a bracketed [ev:...] token.
    for m in LOOSE_CITATION_RE.finditer(md):
        if any(cs <= m.start() < ce for cs, ce in consumed):
            continue
        token = m.group(0)
        d = base(token, m.start())
        d.update(category="unbracketed_token",
                 candidate=_normalized_candidate(token),
                 remediation="evidence citations must be bracketed: "
                             "[ev:<section_id>:<NNNN>]")
        diags.append(d)

    diags.sort(key=lambda d: (d["line"], d["column"]))
    return diags


def format_malformed_token(d: dict) -> str:
    """Render one malformed-token diagnostic as a single human/rewrite-friendly
    line: token text, category, location, remediation, and any safe suggestion."""
    where: list[str] = []
    if d.get("section_id"):
        where.append(f"section {d['section_id']}")
    if d.get("section_file"):
        where.append(str(d["section_file"]))
    if d.get("line"):
        where.append(f"line {d['line']} col {d['column']}")
    loc = (" @ " + ", ".join(where)) if where else ""
    suggestion = f"; suggestion: {d['suggestion']}" if d.get("suggestion") else ""
    return (f"{d['token']!r} [{d.get('category', 'malformed')}]{loc}: "
            f"{d.get('remediation', '')}{suggestion}")


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


def candidate_identifiers(span: str) -> list:
    """Public wrapper around :func:`_candidate_identifiers`: the repo-specific
    identifier candidates ``[(kind, needle)]`` (path/dotted/env/call/route/method)
    in one inline-code span. Reused by the grounded claim-plan validator so the
    plan-time and post-render notions of a "terminal technical token" agree."""
    return _candidate_identifiers(span)


def _supported(kind: str, needle: str, available: str) -> bool:
    if kind == "call":
        # the bare symbol name must appear (def name / name( / symbol_id name())
        return needle in available
    if kind == "dotted":
        # Dotted class/member, object/member, module/member, package/member, and
        # fully-qualified names are supported only by the exact dotted token in
        # available evidence. Never let a slash path or separate class+method /
        # module+symbol tokens ground a synthesized dotted identifier.
        return needle in available
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


# --- shell-variable path synthesis (Iteration 2) ------------------------------
# A narrow, *diagnosis-only* detector for deterministic shell-variable path
# expansions. When evidence shows ``CONF_DIR="/ragflow/conf"`` and
# ``CONF_FILE="${CONF_DIR}/service_conf.yaml"`` and the model writes the expanded
# literal ``/ragflow/conf/service_conf.yaml`` (which is NOT a verbatim evidence
# token), this lets the validator classify it as a rewriteable
# ``synthesized_identifier`` and suggest the exact tokens that DO appear in
# evidence (``CONF_FILE``, ``${CONF_FILE}``, ``${CONF_DIR}/service_conf.yaml``).
# It NEVER makes the expanded path grounded: a synthesized identifier still fails
# validation and can only be fixed by rewriting to an exact evidence token.
_SHELL_ASSIGN_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=(\S.*?)[ \t]*$")
_VAR_REF_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_SHELL_LITERAL_RE = re.compile(r"^[\w./+-]*$")   # path-literal remainder (\w incl _)


def _unquote_shell_value(rhs: str) -> str | None:
    """Strip one layer of matching surrounding quotes. Reject a value that still
    carries a quote afterwards (e.g. concatenated ``"a"b"c"``) — that is not a
    single clean literal/${VAR} assignment and must stay terminal."""
    if len(rhs) >= 2 and rhs[0] == rhs[-1] and rhs[0] in ("'", '"'):
        inner = rhs[1:-1]
        return None if ("'" in inner or '"' in inner) else inner
    return None if ("'" in rhs or '"' in rhs) else rhs


def _is_safe_shell_value(val: str) -> bool:
    """A *conservative* assignment value: path-literal text plus AT MOST ONE
    ``${VAR}``/``$VAR`` reference, with no command substitution, arithmetic,
    globbing, operators, whitespace, or multi-variable concatenation."""
    if not val:
        return False
    if len(_VAR_REF_RE.findall(val)) > 1:        # >1 var ref => not deterministic
        return False
    return bool(_SHELL_LITERAL_RE.match(_VAR_REF_RE.sub("", val)))


def _parse_shell_assignments(text: str) -> dict:
    """``{VAR: value}`` for conservative simple assignments in ``text``. A
    variable assigned conflicting safe values is dropped: ambiguous / runtime
    mutation is not a single deterministic expansion."""
    found: dict[str, str] = {}
    ambiguous: set[str] = set()
    for line in (text or "").splitlines():
        m = _SHELL_ASSIGN_RE.match(line)
        if not m:
            continue
        val = _unquote_shell_value(m.group(2).strip())
        if val is None or not _is_safe_shell_value(val):
            continue
        var = m.group(1)
        if var in found and found[var] != val:
            ambiguous.add(var)
        else:
            found.setdefault(var, val)
    for v in ambiguous:
        found.pop(v, None)
    return found


def _shell_expansions(assigns: dict) -> dict:
    """``{one_step_expanded_literal: [vars]}`` for assignments of the form
    ``VAR=<prefix>${OTHER}<suffix>`` where ``OTHER`` has a *literal* value in the
    same map. Exactly one deterministic substitution step is performed (no
    recursion, no multi-variable joins)."""
    literals = {v: val for v, val in assigns.items() if "$" not in val}
    out: dict[str, list] = {}
    for var, val in assigns.items():
        if "$" not in val:
            continue
        m = _VAR_REF_RE.search(val)
        if not m:
            continue
        ref = m.group(1) or m.group(2)
        if ref not in literals:
            continue
        expanded = val[:m.start()] + literals[ref] + val[m.end():]
        out.setdefault(expanded, [])
        if var not in out[expanded]:
            out[expanded].append(var)
    return out


def detect_synthesized_identifier(identifier: str, available_text: str) -> dict | None:
    """If ``identifier`` is an unsupported path that exactly equals a deterministic
    one-step shell-variable expansion derived from ``available_text`` AND there is
    exactly one assignment producing it AND safe exact alternatives are present in
    evidence, return ``{"identifier", "alternatives"}``. Otherwise return ``None``
    (the identifier stays a terminal ``invented_identifier``).

    Ambiguous (multi-target) expansions, multi-step/recursive derivations,
    command substitution, concatenation, routes, and plain directory+filename
    joins do not match here and remain terminal."""
    assigns = _parse_shell_assignments(available_text)
    if not assigns:
        return None
    vars_for = _shell_expansions(assigns).get(identifier)
    if not vars_for or len(vars_for) != 1:
        return None                              # absent, or >1 semantic target
    var = vars_for[0]
    # Prefer the assignment variable and the raw evidence tokens as alternatives,
    # keeping only those that appear verbatim in evidence (so a rewrite to them
    # passes final validation).
    alts: list[str] = []
    for cand in (var, "${" + var + "}", assigns[var]):
        if cand and cand in available_text and cand not in alts:
            alts.append(cand)
    if not alts:
        return None
    return {"identifier": identifier, "alternatives": alts}


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
    """Return invented identifiers (terminal), synthesized identifiers
    (rewriteable shell-variable expansions), and uncited-claim paragraphs
    (rewriteable). ``available_text`` is the concatenation of every excerpt and
    source-metadata blob the section may rely on."""
    invented: list[str] = []
    synthesized: list[dict] = []
    # 1. unsupported identifiers anywhere (inline spans + fenced path/route tokens).
    # Each is classified once: a deterministic shell-variable expansion becomes a
    # rewriteable ``synthesized_identifier``; everything else stays terminal.
    seen_inv: set = set()

    def classify(needle: str) -> None:
        if needle in seen_inv:
            return
        seen_inv.add(needle)
        syn = detect_synthesized_identifier(needle, available_text)
        if syn is not None:
            synthesized.append(syn)
        else:
            invented.append(needle)

    for span in _INLINE_CODE_RE.findall(markdown or ""):
        for kind, needle in _candidate_identifiers(span):
            if not _supported(kind, needle, available_text):
                classify(needle)
    for block in _FENCE_BLOCK_RE.findall(markdown or ""):
        for tok in re.findall(r"[/\w.+{}:-]+", block):
            if "/" in tok and _RE_PATH.match(tok) and _RE_PATH_EXT.search(tok):
                if tok not in available_text and tok.lstrip("/") not in available_text:
                    classify(tok)

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
    return {"invented_identifiers": invented,
            "synthesized_identifiers": synthesized,
            "uncited_paragraphs": uncited}


# --- citation resolution ------------------------------------------------------
def resolve_citations(markdown: str, *, section_id: str, evidence_index: dict,
                      section_evidence_ids: dict) -> dict:
    """Resolve every citation token. Returns a structured result:

    - ``resolved``: ordered distinct ids that resolve to a real evidence item;
    - ``unresolved``: tokens that do not resolve at all;
    - ``cross_section``: resolved ids owned by another section's packet;
    - ``malformed_tokens``: structured diagnostics for every evidence-like token
      that is not a canonical ``[ev:<section_id>:<NNNN>]`` citation (wrong ordinal
      width, dangling opener, extra text, unbracketed near token, ...). A safe
      ``suggestion`` is attached only when the normalized candidate id exists in
      this bundle's ``evidence_index`` (deterministic zero-padding fix);
    - ``malformed_like``: the malformed token texts (back-compat convenience).
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

    # every evidence-like token that is not a canonical citation, with a safe
    # zero-padding suggestion only when the exact normalized id exists in evidence.
    malformed_tokens = find_malformed_evidence_tokens(markdown, section_id=section_id)
    for d in malformed_tokens:
        cand = d.get("candidate")
        if cand and cand in evidence_index:
            d["suggestion"] = f"[{cand}]"
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "cross_section": cross_section,
        "malformed_tokens": malformed_tokens,
        "malformed_like": [d["token"] for d in malformed_tokens],
    }
