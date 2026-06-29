"""Grounded claim/token plan: schema, deterministic validation, and rendering.

This is the second half of the Phase 4 grounded-generation slice (the first being
:mod:`token_bank`). Instead of having the model free-write Markdown and chasing
invented technical tokens after the fact, the grounded path asks the model for a
small, structured **claim plan**, validates it deterministically, and then renders
the Markdown itself from accepted claim skeletons plus exact token-bank
substitutions.

A claim plan (``phase4-claim-plan-v1``) is plain JSON — not a DSL:

```json
{
  "schema_version": "phase4-claim-plan-v1",
  "section_id": "service",
  "claims": [
    {
      "claim_id": "c1",
      "claim_kind": "file_role",
      "evidence_ids": ["ev:service:0001"],
      "token_ids": ["tok:service:0007"],
      "required_topic": null,
      "intent": "Describe what the service module does.",
      "skeleton": "The {{tok:service:0007}} function builds the item list."
    }
  ]
}
```

The skeleton references every terminal technical string by ``{{token_id}}``
placeholder and contains NO inline ``[ev:...]`` citations. The deterministic
validator rejects a plan — before any Markdown is rendered — when it references
unknown evidence/token ids, free-types a terminal technical token in a skeleton
instead of using a placeholder, or (in enhancement mode) leaves a required topic
unplanned. Token ids carry their own provenance, and placeholders are authoritative:
if a skeleton uses a known placeholder but the model forgets to repeat it in
``token_ids``, validation records a warning and derives the token use from the
placeholder. Required-topic linkage is also evidence-derived: when a claim omits
``required_topic`` but uses evidence mapped to exactly one required-topic obligation,
validation records a warning and assigns that topic. Rendering attaches both the
claim evidence ids and the evidence ids for each used token. Rendering then
substitutes the exact bank string for each placeholder, so a synthesized composite
is structurally unreachable in the grounded path: it has no token id to reference.

Pure and deterministic: no model call, no mutation of the parsed plan.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import citations as cit
from . import generated_coverage as gencov
from .schema import CLAIM_PLAN_SCHEMA_VERSION

# Advisory claim kinds (audit/readability only; the grounding invariants — not the
# kind label — keep a claim safe). ``prose`` is a citation-backed claim with no
# terminal tokens.
CLAIM_KINDS = frozenset({
    "api_route", "class_behavior", "config_field", "data_shape", "dependency",
    "file_role", "runtime_flow", "cli_command", "env_config", "overview", "summary", "prose",
})

# ``{{tok:<section_id>:<NNNN>}}`` placeholder for one token-bank entry.
PLACEHOLDER_RE = re.compile(r"\{\{(tok:[a-z0-9][a-z0-9-]*:\d{4})\}\}")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_ELLIPSIS_RE = re.compile(r"\.\.\.|…")
_EV_TOKEN_RE = re.compile(r"\[ev:")
_BARE_DOTTED_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")
_BARE_SLASH_RE = re.compile(r"(?<![\w.])/[A-Za-z0-9_./{}:…-]+")
_BARE_REL_PATH_RE = re.compile(r"\b[\w.+-]+(?:/[\w.+-]+)+\b")
_BARE_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_BARE_CALL_RE = re.compile(r"\b[A-Za-z_][\w.]*\(\)?")
_BARE_METHOD_PATH_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[\w/{}.:-]*)")
_COMMON_DOTTED_PROSE = frozenset({"e.g", "i.e"})


# --- validation result --------------------------------------------------------
@dataclass
class PlanValidation:
    section_id: str
    ok: bool
    violations: list = field(default_factory=list)   # [{code, message}]
    warnings: list = field(default_factory=list)
    claims: list = field(default_factory=list)        # normalized claim dicts

    def problem_lines(self) -> list:
        return [f"{v['code']}: {v['message']}" for v in self.violations]


def _v(code: str, message: str) -> dict:
    return {"code": code, "message": message}


# --- plan validation ----------------------------------------------------------
def validate_claim_plan(plan, *, section_id, token_bank, allowed_evidence_ids,
                        evidence_index, obligations=None) -> PlanValidation:
    """Deterministically validate one parsed claim ``plan``. Returns a
    :class:`PlanValidation`; never mutates ``plan``. ``obligations`` (the section's
    sufficient required-topic obligations, each with ``topic``/``mapped_evidence_ids``)
    is supplied only in enhancement mode and enforces required-topic planning."""
    violations: list = []
    warnings: list = []
    by_token = token_bank.by_id()
    allowed = set(allowed_evidence_ids)
    obligations = obligations or []

    if not isinstance(plan, dict):
        return PlanValidation(section_id, False,
                              [_v("malformed_plan",
                                  f"claim plan is not a JSON object: "
                                  f"{type(plan).__name__}")])

    sv = plan.get("schema_version")
    if sv is not None and sv != CLAIM_PLAN_SCHEMA_VERSION:
        violations.append(_v("schema_version",
                             f"schema_version {sv!r} != {CLAIM_PLAN_SCHEMA_VERSION!r}"))
    psid = plan.get("section_id")
    if psid is not None and psid != section_id:
        violations.append(_v("wrong_section_id",
                             f"plan section_id {psid!r} != requested {section_id!r}"))

    claims = plan.get("claims")
    if not isinstance(claims, list) or not claims:
        violations.append(_v("no_claims",
                             "claim plan has no non-empty 'claims' list"))
        return PlanValidation(section_id, False, violations, warnings)

    seen_ids: set = set()
    norm_claims: list = []
    planned_topics: set = set()

    for idx, claim in enumerate(claims):
        cid = (claim.get("claim_id") if isinstance(claim, dict) else None) or f"#{idx}"
        if not isinstance(claim, dict):
            violations.append(_v("malformed_claim", f"claim {cid} is not an object"))
            continue
        if not isinstance(claim.get("claim_id"), str) or not claim["claim_id"].strip():
            violations.append(_v("missing_claim_id",
                                 f"claim {cid} has no string claim_id"))
        elif claim["claim_id"] in seen_ids:
            violations.append(_v("duplicate_claim_id",
                                 f"duplicate claim_id {claim['claim_id']!r}"))
        else:
            seen_ids.add(claim["claim_id"])

        kind = claim.get("claim_kind")
        if kind not in CLAIM_KINDS:
            violations.append(_v("invalid_claim_kind",
                                 f"claim {cid} claim_kind {kind!r} not in "
                                 f"{sorted(CLAIM_KINDS)}"))

        skeleton = claim.get("skeleton")
        if not isinstance(skeleton, str) or not skeleton.strip():
            violations.append(_v("empty_skeleton",
                                 f"claim {cid} has an empty skeleton"))
            skeleton = ""

        ev_ids = claim.get("evidence_ids")
        ev_ids = [e for e in ev_ids if isinstance(e, str)] \
            if isinstance(ev_ids, list) else []
        if not ev_ids:
            violations.append(_v("claim_uncited",
                                 f"claim {cid} cites no evidence_ids (every claim "
                                 "must cite at least one evidence item)"))
        for eid in ev_ids:
            if eid not in allowed:
                violations.append(_v("evidence_not_allowed",
                                     f"claim {cid} cites {eid!r} not in this section's "
                                     "allowed_evidence_ids"))
            elif eid not in evidence_index:
                violations.append(_v("unresolved_evidence",
                                     f"claim {cid} cites {eid!r} that resolves to no "
                                     "evidence item"))

        tok_ids = claim.get("token_ids")
        tok_ids = [t for t in tok_ids if isinstance(t, str)] \
            if isinstance(tok_ids, list) else []
        token_evidence_ids: list = []
        for tid in tok_ids:
            entry = by_token.get(tid)
            if entry is None:
                violations.append(_v("unknown_token_id",
                                     f"claim {cid} selects {tid!r} not in the section "
                                     "token bank"))
                continue
            for eid in entry.evidence_ids:
                if eid not in token_evidence_ids:
                    token_evidence_ids.append(eid)
            if not (set(entry.evidence_ids) & set(ev_ids)):
                warnings.append(
                    f"claim {cid} selects {tid!r} ({entry.token!r}) without listing "
                    f"its token provenance evidence {entry.evidence_ids}; the "
                    "renderer will attach token provenance citations automatically")

        # skeleton discipline: placeholders must be known; token_ids are advisory
        # and can be derived from placeholders. No free-typed terminal tokens,
        # inline citations, or ellipsis route-families.
        placeholders = PLACEHOLDER_RE.findall(skeleton)
        declared = set(tok_ids)
        for ph in placeholders:
            if ph not in by_token:
                violations.append(_v("unknown_placeholder",
                                     f"claim {cid} skeleton uses {{{{{ph}}}}} which is "
                                     "not a token-bank id"))
            elif ph not in declared:
                warnings.append(
                    f"claim {cid} skeleton uses {{{{{ph}}}}} not listed in token_ids; "
                    "derived token use from placeholder")
                tok_ids.append(ph)
                declared.add(ph)
                entry = by_token[ph]
                for eid in entry.evidence_ids:
                    if eid not in token_evidence_ids:
                        token_evidence_ids.append(eid)
                if not (set(entry.evidence_ids) & set(ev_ids)):
                    warnings.append(
                        f"claim {cid} uses placeholder {{{{{ph}}}}} ({entry.token!r}) "
                        f"without listing its token provenance evidence "
                        f"{entry.evidence_ids}; the renderer will attach token "
                        "provenance citations automatically")
        unused = declared - set(placeholders)
        if unused:
            warnings.append(f"claim {cid} declares token_ids not used in its "
                            f"skeleton: {sorted(unused)}")

        for free in _free_typed_terminal_tokens(skeleton):
            violations.append(_v("free_typed_terminal_token",
                                 f"claim {cid} skeleton free-types terminal technical "
                                 f"token `{free}`; reference it by {{{{token_id}}}} "
                                 "from the token bank or omit it"))
        if _EV_TOKEN_RE.search(skeleton):
            violations.append(_v("inline_citation_in_skeleton",
                                 f"claim {cid} skeleton contains an inline [ev:...] "
                                 "citation; the renderer attaches citations from "
                                 "evidence_ids — do not write them"))
        placeholders = cit.find_placeholders(skeleton)
        if placeholders:
            violations.append(_v("placeholder_in_skeleton",
                                 f"claim {cid} skeleton contains reserved "
                                 f"placeholder/apology/empty-heading text: "
                                 f"{placeholders[:5]}; write concrete grounded "
                                 "prose or omit the claim"))

        rt = claim.get("required_topic")
        if rt is not None and not isinstance(rt, str):
            violations.append(_v("malformed_required_topic",
                                 f"claim {cid} required_topic must be a string or null"))
            rt = None
        if isinstance(rt, str) and rt.strip():
            planned_topics.add(rt.strip())

        render_evidence_ids = list(ev_ids)
        for eid in token_evidence_ids:
            if eid not in render_evidence_ids:
                render_evidence_ids.append(eid)
        cb = claim.get("content_block_id")
        norm_claims.append({
            "claim_id": claim.get("claim_id"),
            "claim_kind": kind,
            "evidence_ids": ev_ids,
            "token_ids": tok_ids,
            "token_evidence_ids": token_evidence_ids,
            "render_evidence_ids": render_evidence_ids,
            "required_topic": rt.strip() if isinstance(rt, str) and rt.strip() else None,
            # Phase E: optional link to the page's content block this claim grounds.
            "content_block_id": cb.strip() if isinstance(cb, str) and cb.strip()
            else None,
            "intent": claim.get("intent") if isinstance(claim.get("intent"), str)
            else "",
            "skeleton": skeleton,
        })

    # enhancement: required_topic is useful audit metadata, but topic coverage is
    # ultimately grounded by Phase 3's mapped evidence ids. If a claim omitted
    # required_topic and its rendered evidence maps to exactly one obligation, derive
    # the linkage deterministically instead of failing on a redundant field.
    _derive_required_topics_from_mapped_evidence(norm_claims, obligations, warnings)

    # enhancement: every sufficient required-topic obligation must be planned by a
    # claim that also cites or uses at least one of the topic's mapped evidence ids.
    for ob in obligations:
        if not ob.get("is_obligation"):
            continue
        topic = (ob.get("topic") or "").strip()
        mapped = set(ob.get("mapped_evidence_ids") or [])
        topic_claims = [c for c in norm_claims if c["required_topic"] == topic]
        if not topic_claims:
            violations.append(_v("required_topic_not_planned",
                                 f"required topic {topic!r} has no claim "
                                 "(required_topic linkage missing)"))
            continue
        if mapped and not any(
            set(c.get("render_evidence_ids") or c["evidence_ids"]) & mapped
            for c in topic_claims
        ):
            violations.append(_v("required_topic_evidence_not_mapped",
                                 f"required topic {topic!r} is planned but no claim "
                                 f"cites or uses a token from one of its mapped evidence "
                                 f"ids {sorted(mapped)}"))

    ok = not violations
    return PlanValidation(section_id, ok, violations, warnings, norm_claims)


def _derive_required_topics_from_mapped_evidence(claims: list, obligations: list,
                                                 warnings: list) -> None:
    obligation_rows = [o for o in (obligations or []) if o.get("is_obligation")]
    for claim in claims:
        if claim.get("required_topic"):
            continue
        evidence_ids = set(claim.get("render_evidence_ids") or claim.get("evidence_ids") or [])
        matches: list = []
        for ob in obligation_rows:
            mapped = set(ob.get("mapped_evidence_ids") or [])
            topic = (ob.get("topic") or "").strip()
            if topic and mapped and (evidence_ids & mapped):
                matches.append(topic)
        if len(matches) == 1:
            claim["required_topic"] = matches[0]
            warnings.append(
                f"claim {claim.get('claim_id')} omitted required_topic; derived "
                f"{matches[0]!r} from mapped evidence ids")



def _free_typed_terminal_tokens(skeleton: str) -> list:
    """Terminal technical tokens written literally in a skeleton instead of via a
    ``{{token_id}}`` placeholder. Placeholders are stripped first. Inline-code spans
    are checked using the same candidate detector as final validation, and the plain
    text outside code spans is scanned for high-precision terminal-token shapes
    (dotted composites, routes/paths, env vars, method+route, and calls). This is
    stricter than the final prose validator on purpose: grounded mode must not rely
    on the model freely typing risky terminal strings and hoping later validation
    catches only backticked forms."""
    stripped = PLACEHOLDER_RE.sub(" ", skeleton or "")
    out: list = []

    for span in _INLINE_CODE_RE.findall(stripped):
        if _ELLIPSIS_RE.search(span):
            out.append(span.strip())
            continue
        if cit.candidate_identifiers(span):
            out.append(span.strip())

    plain = _INLINE_CODE_RE.sub(" ", stripped)
    out.extend(_plain_terminal_candidates(plain))

    deduped: list = []
    seen: set = set()
    for tok in out:
        tok = tok.strip()
        if tok and tok not in seen:
            seen.add(tok)
            deduped.append(tok)
    return deduped


def _plain_terminal_candidates(text: str) -> list:
    """High-precision terminal-token candidates in non-code prose. This does not
    try to detect every single-symbol identifier; it catches the synthesis-prone
    shapes that caused Phase 4 failures while avoiding ordinary English."""
    candidates: list = []
    for m in _BARE_METHOD_PATH_RE.finditer(text or ""):
        candidates.append(f"{m.group(1)} {m.group(2)}")
    for regex in (_BARE_SLASH_RE, _BARE_REL_PATH_RE, _BARE_DOTTED_RE,
                  _BARE_ENV_RE, _BARE_CALL_RE):
        for m in regex.finditer(text or ""):
            tok = m.group(0).rstrip(".,;:)")
            if tok in _COMMON_DOTTED_PROSE:
                continue
            if cit.candidate_identifiers(tok):
                candidates.append(tok)
    return candidates


# --- rendering ----------------------------------------------------------------
@dataclass
class RenderedSection:
    section_id: str
    title: str
    markdown: str
    used_evidence_ids: list = field(default_factory=list)
    covered_topics: list | None = None
    covered_content_blocks: list | None = None


def _skeleton_paragraph_template(skeleton: str) -> str:
    """Normalize a claim skeleton into one paragraph template before token
    substitution. A skeleton is structured plan text, not final Markdown; allowing
    embedded newlines would let one claim render as multiple paragraphs while the
    renderer appends citations only once at the end."""
    return re.sub(r"\s+", " ", skeleton or "").strip()


def _render_claim_paragraph(claim, by_token) -> str:
    """One claim → one Markdown paragraph: skeleton with placeholders substituted by
    backtick-wrapped exact bank strings, followed by the claim's evidence citations
    (attached deterministically by the renderer, never typed by the model)."""
    def sub(m):
        entry = by_token.get(m.group(1))
        return f"`{entry.token}`" if entry is not None else m.group(0)

    body = PLACEHOLDER_RE.sub(sub, _skeleton_paragraph_template(claim["skeleton"])).strip()
    citation_ids = claim.get("render_evidence_ids") or claim["evidence_ids"]
    cites = "".join(f"[{eid}]" for eid in citation_ids)
    return f"{body} {cites}".strip() if cites else body


def render_section(plan_validation: PlanValidation, *, token_bank, title,
                   section_id, obligations=None,
                   content_block_obligations=None) -> RenderedSection:
    """Render the section Markdown deterministically from an accepted plan.

    Baseline: a title heading followed by one paragraph per claim. Enhancement
    (``obligations`` given): each sufficient required topic is rendered under its own
    ``###`` heading so its generated coverage is locally grounded and anchor-locatable,
    with a deterministically derived ``covered_topics[]`` declaration. Expanded
    (``content_block_obligations`` given): each evidence-bearing content block is
    additionally proven covered by the topic subsection(s) of the claims linked to it
    (``content_block_id``), with a deterministically derived ``covered_content_blocks[]``
    declaration. Must only be called on a passing :class:`PlanValidation`."""
    by_token = token_bank.by_id()
    claims = plan_validation.claims
    obligations = obligations or []
    obligation_topics = {(o.get("topic") or "").strip()
                         for o in obligations if o.get("is_obligation")}

    lines: list = [f"## {title}", ""]
    used: set = set()
    covered_rows: list = []
    # topic -> (anchor, cited mapped evidence ids) for content-block derivation.
    topic_render: dict = {}

    # Non-obligation claims first as flat intro/body paragraphs.
    body_claims = [c for c in claims
                   if not (c["required_topic"] in obligation_topics
                           and c["required_topic"])]
    topic_claims: dict = {}
    for c in claims:
        rt = c["required_topic"]
        if rt and rt in obligation_topics:
            topic_claims.setdefault(rt, []).append(c)

    for c in body_claims:
        lines.append(_render_claim_paragraph(c, by_token))
        lines.append("")
        used.update(c.get("render_evidence_ids") or c["evidence_ids"])

    # One ``###`` subsection per planned required topic (enhancement mode).
    for ob in obligations:
        if not ob.get("is_obligation"):
            continue
        topic = (ob.get("topic") or "").strip()
        cs = topic_claims.get(topic) or []
        if not cs:
            continue
        heading_line = f"### {topic}"
        lines.append(heading_line)
        lines.append("")
        mapped = set(ob.get("mapped_evidence_ids") or [])
        topic_cited: list = []
        for c in cs:
            lines.append(_render_claim_paragraph(c, by_token))
            lines.append("")
            rendered_ids = c.get("render_evidence_ids") or c["evidence_ids"]
            used.update(rendered_ids)
            for eid in rendered_ids:
                if eid in mapped and eid not in topic_cited:
                    topic_cited.append(eid)
        anchor = gencov.heading_slug(heading_line)
        covered_rows.append({
            "topic": topic, "status": gencov.GEN_COVERED,
            "evidence_ids": topic_cited, "markdown_anchor": anchor,
        })
        topic_render[topic] = (anchor, topic_cited)

    # Expanded mode: derive covered content blocks from the topic subsections of the
    # claims linked to each block (a block is grounded by its linked covered topics).
    block_rows = _derive_covered_content_blocks(
        content_block_obligations or [], claims, topic_claims, topic_render)

    markdown = "\n".join(lines).rstrip() + "\n"
    return RenderedSection(
        section_id=section_id, title=title, markdown=markdown,
        used_evidence_ids=sorted(used),
        covered_topics=covered_rows if obligations else None,
        covered_content_blocks=block_rows
        if content_block_obligations is not None else None)


def _derive_covered_content_blocks(block_obligations: list, claims: list,
                                   topic_claims: dict, topic_render: dict) -> list:
    """Deterministically derive ``covered_content_blocks[]`` for the rendered page.

    A content block obligation is declared covered when a claim links it
    (``content_block_id``) to a required topic that was rendered under its own
    subsection: the block reuses that topic's anchor and the subset of its cited
    evidence that is in the block's supporting Phase 3 IDs. No new headings are
    invented; coverage is the topic subsection that grounds the block."""
    # block_id -> ordered list of (topic) the linked claims belong to.
    topics_by_block: dict = {}
    for c in claims:
        bid = c.get("content_block_id")
        rt = c.get("required_topic")
        if bid and rt and rt in topic_render:
            topics_by_block.setdefault(bid, [])
            if rt not in topics_by_block[bid]:
                topics_by_block[bid].append(rt)

    rows: list = []
    for ob in block_obligations:
        if not ob.get("is_obligation"):
            continue
        bid = ob.get("content_block_id")
        supporting = set(ob.get("supporting_evidence_ids") or [])
        topics = topics_by_block.get(bid) or []
        if not topics:
            continue
        anchor, _ = topic_render[topics[0]]
        cited: list = []
        for t in topics:
            _, topic_cited = topic_render[t]
            for eid in topic_cited:
                if (not supporting or eid in supporting) and eid not in cited:
                    cited.append(eid)
        if not cited:
            continue
        rows.append({
            "content_block_id": bid, "status": gencov.GEN_COVERED,
            "evidence_ids": cited, "markdown_anchor": anchor,
        })
    return rows


def rendered_draft(rendered: RenderedSection) -> dict:
    """A section-draft dict (the contract :func:`validate.validate_section_draft`
    consumes) built from a deterministically rendered section. The grounded path
    feeds this through the SAME strict validators as a model-authored draft."""
    from .schema import SECTION_DRAFT_SCHEMA_VERSION
    draft = {
        "schema_version": SECTION_DRAFT_SCHEMA_VERSION,
        "section_id": rendered.section_id,
        "title": rendered.title,
        "markdown": rendered.markdown,
        "used_evidence_ids": list(rendered.used_evidence_ids),
    }
    if rendered.covered_topics is not None:
        draft["covered_topics"] = rendered.covered_topics
    if rendered.covered_content_blocks is not None:
        draft["covered_content_blocks"] = rendered.covered_content_blocks
    return draft


# --- prompt construction ------------------------------------------------------
CLAIM_PLAN_SYSTEM_INSTRUCTION = """You are a precise technical writer planning one \
section of a grounded, DeepWiki-style engineering wiki for a real software \
repository. You DO NOT write the final Markdown. You author a structured claim \
plan; deterministic code renders the Markdown from your plan, so you cannot \
free-type technical strings into the output.

You are given an EvidencePacket and a TOKEN BANK. The token bank is the complete, \
exact set of terminal technical strings — routes, file paths, imports, \
module/class/function/method names, env vars, commands, JSON pointers, package \
names, and code/config literals — that were found verbatim in the cited evidence. \
Each token has a stable `token_id`.

The single hard rule: every terminal technical string in your prose MUST be \
referenced by its `{{token_id}}` placeholder from the token bank — never typed \
literally. If the exact string you want is NOT in the token bank, it is not \
grounded: describe the concept in plain prose without that string, or omit the \
claim. Do NOT invent a convenient shorthand. In particular, do NOT compose a \
dotted/qualified/normalized form (a class.method, module.symbol, object.field, a \
normalized route, or a route-family ellipsis) unless that EXACT composite string \
exists as its own token in the bank with its own `token_id`.

Plan rules:
- Return ONE raw strict JSON object (no markdown fences) matching the response \
contract. Use JSON-safe string escaping.
- Each claim cites at least one `evidence_id` (only ids from `allowed_evidence_ids`).
- Token ids carry provenance. Include a token's `from` evidence id in \
`evidence_ids` when it supports the claim; the deterministic renderer will also \
attach used-token provenance citations automatically.
- For required topics, set `required_topic` to the exact topic string. If you omit \
it on a claim that uses evidence mapped to exactly one required topic, deterministic \
validation will derive that topic linkage and record a warning.
- Put every `{{token_id}}` placeholder used in a `skeleton` into that claim's \
`token_ids` for audit clarity. If you forget, deterministic validation derives \
the token use from the placeholder and records a warning.
- A `skeleton` MUST NOT contain inline-code technical tokens written literally \
(use placeholders), MUST NOT contain `[ev:...]` citations (the renderer attaches \
claim and token-provenance citations), MUST NOT contain ellipses inside code, and \
MUST NOT contain placeholder/apology/TODO/TBD/meta text.
- Use one of these `claim_kind` values: api_route, class_behavior, cli_command, \
config_field, data_shape, dependency, env_config, file_role, overview, prose, \
runtime_flow, summary.
- Write explanatory prose skeletons; attach each claim to the specific evidence \
that supports it. Prefer plain prose over forcing a token where evidence is thin.
- `exact`/`high` evidence supports definitive statements; `low` (graph-context) \
evidence must never be the sole support for a precise claim."""


def _token_bank_lines(token_bank) -> list:
    lines: list = ["## Token bank (the ONLY terminal technical strings you may use, "
                   "by id)", ""]
    if not token_bank.tokens:
        lines.append("_none — this section has no terminal technical tokens; write "
                     "grounded prose with citations and no inline-code identifiers._")
        lines.append("")
        return lines
    lines.append("| token_id | kind | token | from |")
    lines.append("| --- | --- | --- | --- |")
    for t in token_bank.tokens:
        tok = t.token.replace("|", "\\|").replace("\n", " ")
        frm = ", ".join(t.evidence_ids)
        lines.append(f"| `{t.token_id}` | {t.kind} | `{tok}` | {frm} |")
    lines.append("")
    return lines


def _required_topic_lines(obligations) -> list:
    obs = [o for o in (obligations or []) if o.get("is_obligation")]
    if not obs:
        return []
    lines = ["## Required topics (each MUST have at least one claim)", ""]
    for ob in obs:
        ids = ", ".join(f"`{e}`" for e in ob.get("mapped_evidence_ids") or [])
        lines.append(f"- **{ob.get('topic')}** — set `required_topic` to this exact "
                     f"string on its claim(s); cite from: {ids or '(none)'}")
    lines.append("")
    return lines


def _plan_contract(section_id: str, token_bank, obligations) -> dict:
    example_token = token_bank.tokens[0].token_id if token_bank.tokens \
        else "tok:" + section_id + ":0001"
    claim = {
        "claim_id": "c1",
        "claim_kind": "file_role",
        "evidence_ids": ["ev:" + section_id + ":0001"],
        "token_ids": [example_token],
        "required_topic": None,
        "intent": "One short sentence describing what this claim explains.",
        "skeleton": ("Plain-prose explanation that references terminal strings only "
                     "as placeholders such as {{" + example_token + "}}."),
    }
    return {
        "schema_version": CLAIM_PLAN_SCHEMA_VERSION,
        "section_id": section_id,
        "claims": [claim],
    }


def build_claim_plan_prompt(writing_packet, token_bank, *, obligations=None) -> str:
    """The full claim-plan prompt for one section (system instruction + evidence
    packet + token bank + response contract). Deterministic / byte-stable."""
    wp = writing_packet
    sid = wp.section_id
    parts: list = []
    parts.append("# SYSTEM INSTRUCTION")
    parts.append("")
    parts.append(CLAIM_PLAN_SYSTEM_INSTRUCTION)
    parts.append("")
    parts.append("# CLAIM-PLAN TASK")
    parts.append("")
    parts.append(f"Plan the wiki section `{sid}` titled \"{wp.title}\".")
    parts.append("")
    parts.append("## Section work order and evidence packet")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(wp.data, indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("## Citeable evidence ids (the ONLY values you may cite)")
    parts.append("")
    if wp.allowed_evidence_ids:
        for eid in wp.allowed_evidence_ids:
            parts.append(f"- `{eid}`")
    else:
        parts.append("_none — this section has no citeable evidence._")
    parts.append("")
    parts += _token_bank_lines(token_bank)
    parts += _required_topic_lines(obligations)
    parts.append("## Response contract (return EXACTLY this JSON shape)")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(_plan_contract(sid, token_bank, obligations),
                            indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("Return only the raw JSON claim plan, with JSON-safe string escaping.")
    return "\n".join(parts) + "\n"


def build_claim_plan_rewrite_prompt(writing_packet, token_bank, prior_raw: str,
                                    problems: list, *, obligations=None) -> str:
    """A bounded re-prompt for an INVALID claim plan: the same evidence + token bank
    plus the exact machine-checked plan violations. It adds no evidence, no tokens,
    and no rules — it only asks the model to fix the listed plan defects."""
    base = build_claim_plan_prompt(writing_packet, token_bank, obligations=obligations)
    extra = [
        "",
        "# REWRITE — FIX CLAIM-PLAN VALIDATION ERRORS ONLY",
        "",
        "Your previous claim plan did not validate. Fix ONLY the issues below using "
        "the SAME evidence packet and token bank (do not add evidence, do not invent "
        "tokens, do not free-type technical strings — reference token ids):",
        "",
    ]
    extra += [f"- {p}" for p in problems]
    extra += [
        "",
        "## Your previous claim plan (verbatim)",
        "```",
        (prior_raw or "").strip(),
        "```",
        "",
        "Return only the corrected raw JSON claim plan, with JSON-safe string escaping.",
    ]
    return base + "\n".join(extra) + "\n"
