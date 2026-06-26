"""Strict prompt construction for one section.

The prompt is deterministic (no timestamps / randomness) so an audited prompt is
byte-stable across reruns over the same bundle. It pins the citation syntax, the
claim discipline, and the strict JSON response contract. The exact text written
here is what is saved to ``wiki/audit/prompts/<section_id>.md`` *before* the
model call, and what a Gemini Gem operator pastes verbatim.
"""
from __future__ import annotations

import json

from .schema import SECTION_DRAFT_SCHEMA_VERSION

SYSTEM_INSTRUCTION = """You are a precise technical writer producing one section \
of a grounded, DeepWiki-style engineering wiki for a real software repository.

You write ONLY from the supplied EvidencePacket. Every repo-specific claim — a \
file path, module, class, function, method, symbol, route, HTTP method, CLI \
command, config key, environment variable, data store, dependency, test, or \
runtime/deployment behavior — MUST be backed by an inline citation to an \
evidence item you were given.

Hard rules:
- Your entire response MUST be one raw strict JSON object that a standard \
`json.loads` parser can parse. Generate JSON with JSON-safe Markdown string \
escaping: the `markdown` value and every other string value must encode Markdown \
newlines as `\\n` and escape any embedded `"` or `\\`; never put raw unescaped \
newlines, raw unescaped double quotes, or other control characters inside a JSON \
string. Do not wrap the object in markdown fences.
- Cite with the EXACT inline syntax `[ev:<section_id>:<NNNN>]`, copied verbatim \
from the `evidence_id` field. Multiple citations are adjacent brackets, e.g. \
`... [ev:overview:0001][ev:overview:0004]`.
- You may ONLY cite `evidence_id` values listed in `allowed_evidence_ids`. Never \
invent an evidence id, never cite a file path or URL directly, never use \
footnotes, and never cite `search_hints` or `context_artifacts`.
- Instruction examples are NOT evidence. Any identifier, route, path, symbol, \
citation id, config key, environment variable, dependency, or command shown in \
these instructions or the response contract is a FORBIDDEN INSTRUCTION EXAMPLE \
unless the exact token appears in the EvidencePacket and is cited. Such examples \
must never be copied into the generated `markdown`, `used_evidence_ids`, or \
`covered_topics[]` to make prose look precise.
- Do NOT introduce any identifier (path, symbol, route, env var, command, \
dependency, version) unless the full exact token appears verbatim in one cited \
evidence item's excerpt, `source`, or `provenance` metadata. If the evidence does \
not support a fact, omit the fact.
- Never synthesize or expand a file path: do not join a directory and a filename, \
complete a partial path, or infer a module's full path. Use a path ONLY when that \
exact string appears in a cited evidence item's `source` or excerpt — otherwise \
refer to the component by the name the evidence actually provides.
- Never synthesize fully-qualified names by joining module/package paths, import \
statements, file paths, package names, file stems, classes, functions, methods, \
aliases, or symbols into a dotted, slashed, or call identifier. Dotted \
class/member, object/member, module/member, and package/member notation is allowed \
ONLY when that full dotted token appears verbatim in one cited evidence item. \
Separate tokens in the same cited item are not enough: a class token plus a method \
token does NOT evidence `ClassName.method_name`, an object token plus a member \
token does NOT evidence `object.member`, and a module/package token plus a symbol \
token does NOT evidence `module.symbol` or `package.symbol`, unless that full \
dotted token appears verbatim in one cited evidence item. If the evidence supports \
separate tokens but not a full dotted token, write the tokens separately; for \
example, refer to an evidenced method and evidenced class as separate cited tokens, \
but never join them into a class-method dotted token unless that full exact dotted \
token appears verbatim in one cited evidence item. Do not transform import \
statements into dotted fully-qualified identifiers: an \
instruction-example line such as `from package.module import Name` evidences only \
exact tokens present in that evidence item (for example, `package.module`, `Name`, \
and the import line itself); it does NOT evidence `package.module.Name` unless \
that full exact dotted token appears verbatim in one cited evidence item. \
Instruction examples in this rule are not evidence. Forbidden instruction \
identifier examples (not evidence; never copy unless the full exact token appears \
in cited EvidencePacket): `pkg/module.py`, `ClassName`, `method_name`, \
`ClassName.method_name`, `pkg.module.ClassName`, \
`common.metadata_es_filter`, `MetaFilterTranslator`, \
`common.metadata_es_filter.MetaFilterTranslator`, `module.function()`. Do not turn \
separate evidence pieces like `pkg/module.py` plus `ClassName` into \
`pkg.module.ClassName`, `common.metadata_es_filter` plus `MetaFilterTranslator` \
into `common.metadata_es_filter.MetaFilterTranslator`, or a module plus function \
into `module.function()`, unless that full exact token appears verbatim in one \
cited evidence item.
- Never expand or interpolate shell or environment variables. Copy identifiers \
exactly; do not compute the result of a variable substitution. Forbidden \
instruction shell examples (not evidence; never copy unless the exact token \
appears in cited EvidencePacket): `CONF_DIR="/ragflow/conf"`, \
`CONF_FILE="${CONF_DIR}/service_conf.yaml"`, `CONF_FILE`, `${CONF_FILE}`, \
`${CONF_DIR}/service_conf.yaml`, `/ragflow/conf/service_conf.yaml`. If a cited \
evidence item itself shows tokens like these, you may write only those exact \
evidenced tokens; you must NOT write an expanded literal unless that exact \
expanded string itself appears in a cited evidence item.
- Never synthesize or normalize a route pattern: do not add or remove prefixes, \
add or remove query parameters/trailing slashes, or convert placeholder syntax \
unless that exact complete route string appears verbatim in one cited evidence \
item. Forbidden instruction route examples (not evidence; never copy unless the \
exact complete route appears in cited EvidencePacket): `/api`, `/api/v1`, \
`/api/{api_version}`, `/{api_version}`, `<id>`, `{id}`, `:id`. For route evidence, \
copy only `source.route` or `source.public_route` values verbatim; do not compose \
a public route from a prefix and a contract route.
- When evidence is partial or split across items, prefer component-level \
descriptions or exact quoted tokens over invented identifiers or routes. For \
example, describe "the metadata filter translator component" or quote \
`MetaFilterTranslator` only if those exact words/tokens are evidenced and cited; \
do not invent a longer qualified name to make prose look precise.
- `exact`/`high` evidence supports definitive statements. `medium` evidence \
needs careful phrasing. `low` (graph-context) evidence must never be the sole \
support for a precise claim — pair it with stronger evidence or omit it.
- No placeholders, TODO/TBD/FIXME, "needs citation", empty headings, apologies, \
or meta commentary about yourself or these instructions.
- Write explanatory prose (paragraphs first, focused lists/tables only when the \
evidence warrants). Do not dump citations as a bibliography; attach each citation \
to the specific claim it supports.

Return ONLY a single JSON object — no prose before or after, no markdown fences \
around it — matching the response contract you are given."""


def _response_contract(section_id: str, title: str, *, covered_topics=None) -> dict:
    contract = {
        "schema_version": SECTION_DRAFT_SCHEMA_VERSION,
        "section_id": section_id,
        "title": title,
        "markdown": ("## " + title + "\n\n<the section body as GitHub-flavored "
                     "Markdown, with inline [ev:...] citations on every "
                     "repo-specific claim>"),
        "used_evidence_ids": ["ev:" + section_id + ":0001"],
        "self_check": {
            "valid_json": True,
            "json_strings_escaped": True,
            "no_uncited_repo_claims": True,
            "no_context_artifact_citations": True,
            "no_placeholders": True,
            "no_synthesized_identifiers": True,
            "no_synthesized_routes": True,
        },
    }
    if covered_topics is not None:
        # DeepWiki coverage enhancement: a structured generated-topic declaration.
        # One row per required topic, status ``covered``, the exact supporting
        # evidence_ids actually cited, and the markdown anchor (heading slug) where
        # the topic is explained.
        contract["covered_topics"] = covered_topics
    return contract


def _enhancement_block(wp) -> list[str]:
    """Prompt guidance for DeepWiki coverage enhancement: the planned hierarchy and
    the exact required topics (with supporting evidence) the writer must cover."""
    hierarchy = (wp.data.get("hierarchy") or {})
    obligations = [o for o in (wp.required_topics_coverage or [])
                   if o.get("is_obligation")]
    lines: list[str] = ["", "## DeepWiki coverage enhancement — REQUIRED", ""]
    parent = hierarchy.get("parent_section_id")
    labels = hierarchy.get("coverage_labels") or []
    children = hierarchy.get("child_section_ids") or []
    lines.append(
        f"This page sits in a planned hierarchy: parent_section_id="
        f"`{parent}`, coverage_labels={labels or '[]'}, "
        f"child_section_ids={children or '[]'}. Write this page's own depth; do not "
        "fold a child page's required topics into this broad parent (a broad parent "
        "page never counts as coverage for a child required topic).")
    lines.append("")
    if obligations:
        lines.append("You MUST explain each required topic below in its own non-empty "
                     "paragraph/subsection with valid inline citations to the exact "
                     "supporting evidence_ids listed, and declare it in "
                     "`covered_topics[]`:")
        lines.append("")
        for ob in obligations:
            ids = ", ".join(f"`{e}`" for e in ob.get("supporting_evidence_ids") or [])
            lines.append(f"- **{ob.get('topic')}** — cite from: {ids or '(none)'}")
        lines.append("")
        lines.append("For every required topic, add a `covered_topics[]` row with "
                     "`status: \"covered\"`, the `evidence_ids` you actually cited "
                     "(each MUST be one of that topic's supporting evidence_ids), and "
                     "a `markdown_anchor` equal to the GitHub heading slug where you "
                     "explain it. Omitting a required topic, leaving an empty "
                     "heading, or citing an id outside its supporting set fails "
                     "validation.")
    else:
        lines.append("_This page has no evidenced required-topic obligations; return "
                     "an empty `covered_topics` list._")
    lines.append("")
    return lines


def build_section_prompt(writing_packet) -> str:
    """The full user prompt for one section (system instruction + packet +
    response contract). This is the exact text audited and/or pasted into a Gem."""
    wp = writing_packet
    sid = wp.section_id
    parts: list[str] = []
    parts.append("# SYSTEM INSTRUCTION")
    parts.append("")
    parts.append(SYSTEM_INSTRUCTION)
    parts.append("")
    parts.append("# WRITING TASK")
    parts.append("")
    parts.append(f"Write the wiki section `{sid}` titled \"{wp.title}\".")
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
        parts.append("_none — this section has no citeable evidence; if you cannot "
                     "write a grounded section, return markdown that states only "
                     "what the (empty) evidence supports._")
    parts.append("")

    # DeepWiki coverage enhancement: hierarchy + required-topic obligations and the
    # extended response contract carrying covered_topics[]. Only present in
    # enhancement mode (baseline packets carry no required_topics_coverage).
    covered_topics_example = None
    if wp.required_topics_coverage is not None:
        parts += _enhancement_block(wp)
        obligations = [o for o in wp.required_topics_coverage
                       if o.get("is_obligation")]
        covered_topics_example = [
            {"topic": ob.get("topic"), "status": "covered",
             "evidence_ids": list(ob.get("supporting_evidence_ids") or [])[:1],
             "markdown_anchor": "<github-heading-slug>"}
            for ob in obligations] or []

    parts.append("## Response contract (return EXACTLY this JSON shape)")
    parts.append("")
    parts.append("The `self_check` booleans are declarations only; downstream ")
    parts.append("validation independently parses JSON and checks citations, ")
    parts.append("identifiers, and routes. Do not rely on these booleans to make ")
    parts.append("invalid output pass.")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(
        _response_contract(sid, wp.title, covered_topics=covered_topics_example),
        indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("Return only the raw JSON object, with JSON-safe Markdown string escaping.")
    return "\n".join(parts) + "\n"


def build_rewrite_prompt(writing_packet, prior_raw: str, problems: list[str]) -> str:
    """A bounded rewrite prompt: the SAME packet plus the specific format/citation
    problems to fix. It adds no evidence and changes no rules."""
    base = build_section_prompt(writing_packet)
    extra = [
        "",
        "# REWRITE — FIX FORMAT / CITATION ISSUES ONLY",
        "",
        "Your previous response did not validate. Fix ONLY the issues below using "
        "the SAME evidence packet (do not add evidence, do not invent facts, do "
        "not change grounded claims):",
        "",
    ]
    extra += [f"- {p}" for p in problems]
    if any(p.startswith("synthesized_identifier") for p in problems):
        extra += [
            "",
            "One or more identifiers are shell-variable EXPANSIONS, not grounded "
            "identifiers: the expanded literal does not appear verbatim in cited "
            "evidence. Replace each flagged identifier with one of the exact "
            "evidence tokens suggested above, or omit the claim entirely. The "
            "instruction examples `CONF_FILE`, `${CONF_FILE}`, and "
            "`${CONF_DIR}/service_conf.yaml` are not evidence; use them only if "
            "they were explicitly suggested above from the SAME cited evidence. "
            "Do NOT expand variables and do NOT justify the expanded path.",
        ]
    extra += [
        "",
        "## Your previous response (verbatim)",
        "```",
        prior_raw.strip(),
        "```",
        "",
        "Return only the corrected raw strict JSON object, with JSON-safe Markdown string escaping.",
    ]
    return base + "\n".join(extra) + "\n"
