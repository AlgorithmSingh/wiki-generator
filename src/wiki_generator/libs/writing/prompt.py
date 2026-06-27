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
`evidence-backed claim [ev:overview:0001][ev:overview:0004]`.
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
- Class/object ownership does not create dotted identifiers. If evidence shows a \
method/function name inside or near a class/object, describe it as a separate \
token, e.g. "the `method` method in/inside/on `Class`", or quote the definition; \
do NOT write `Class.method`, `Class._private`, `object.member`, etc. unless that \
full dotted token appears verbatim in cited evidence.
- Nested JSON/YAML/dict/object keys do NOT create dotted identifiers or field \
paths. If evidence shows an object with key `data` containing key `graph`, write \
safe prose such as "the `graph` field under the `data` object" or quote exact \
JSON/YAML/object snippets; do NOT write `object.field`, `parent.child`, or any \
dotted key path unless that exact dotted token appears verbatim in cited \
evidence. This applies to API response examples, config maps, request bodies, \
dict literals, and JSON/YAML snippets. Instruction examples in this object-key \
rule are not evidence.
- Import statements must be described in import syntax or as separate tokens. A \
file path, directory, package context, or section context must never be used to \
qualify an imported symbol/name. If evidence shows a file under a directory or \
package/section context and separately shows `from X import Y` or `import Y`, do \
NOT write `directory.Y`, `package.Y`, `section.Y`, or any dotted context-symbol \
form unless that full dotted token appears verbatim in cited evidence. Instead, \
say the file imports `Y` from `X`, say the file imports `Y`, or quote the exact \
import line. If evidence says a file imports a symbol/name from a package/module, \
write "imports `Name` from `module`" or quote `from module import Name`; do NOT \
write `module.Name`, `package.Name`, or any dotted package-symbol form unless \
that full dotted token appears verbatim in cited evidence. Instruction examples \
in this import rule are not evidence.
- Never synthesize or expand a file path: do not join a directory and a filename, \
complete a partial path, or infer a module's full path. Use a path ONLY when that \
exact string appears in a cited evidence item's `source` or excerpt — otherwise \
refer to the component by the name the evidence actually provides.
- Never synthesize fully-qualified names by joining module/package paths, import \
statements, file paths, file-path directories, package names, package context, \
section context, file stems, classes, functions, methods, aliases, or symbols \
into a dotted, slashed, or call identifier. A cited file path/source directory, \
section id/title/label, or other surrounding context is not a namespace for an \
imported symbol/name and must not qualify it. Dotted \
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
- Never synthesize or normalize a route pattern: do not add or remove route \
prefixes, version markers, base paths, query parameters, or trailing slashes; do \
not convert route-template marker syntax; and do not combine separate route \
fragments unless that exact complete route string appears verbatim in one cited \
evidence item. High-salience route-template rule: Do not rewrite f-strings, code \
templates, variables, or template markers into simplified route patterns; do not \
drop qualifiers such as `self.` or rename variables into brace variables. If only \
a template or f-string is evidenced, either quote the exact evidenced \
template/token or describe it in prose using separate exact tokens; do not invent \
a normalized route pattern. Never put ellipses (three dots or the single \
ellipsis glyph) inside route, path, identifier, or inline-code tokens to \
summarize multiple endpoints or names. Do not write a prefix followed by an \
ellipsis as an abbreviated route/path/identifier unless that exact complete token \
appears verbatim in one cited evidence item. To discuss a family of endpoints, \
use prose such as "routes under the API prefix" or list exact cited routes \
individually; do not invent a pseudo-route. These instructions intentionally \
avoid literal forbidden route examples because example route tokens can leak into \
generated output. For route evidence, copy only `source.route` or \
`source.public_route` values verbatim; do not compose a public route from a base \
path, prefix, version marker, or contract route.
- ONE-SHOT route grounding example (instruction example, not evidence): if an \
evidence item shows client setting/base-builder tokens such as `api_version`, \
`api_base`, and `non_api_base`, plus code that builds API bases from those \
variables, do NOT turn that into a normalized route or a version-placeholder \
route. GOOD: quote the exact evidenced code/template tokens, or write prose such \
as "the client stores an `api_version` setting and builds the base URL in code" \
with the actual evidence citation. GOOD: list exact cited public routes or \
prefixes only when those strings appear verbatim in the cited evidence. BAD: a \
generic slash route pattern made from a root or API prefix plus a brace-wrapped \
version variable; that is an invented route template, not grounded evidence.
- When evidence is partial or split across items, prefer component-level \
descriptions or exact quoted tokens over invented identifiers or routes. For \
example, describe "the metadata filter translator component" or quote \
`MetaFilterTranslator` only if those exact words/tokens are evidenced and cited; \
do not invent a longer qualified name to make prose look precise.
- `exact`/`high` evidence supports definitive statements. `medium` evidence \
needs careful phrasing. `low` (graph-context) evidence must never be the sole \
support for a precise claim — pair it with stronger evidence or omit it.
- The generated `markdown` MUST NOT contain validation-reserved filler words or \
tokens: the literal word `placeholder` (any casing, including plural or compound \
forms that contain that substring), `TODO`, `TBD`, `FIXME`, or the phrase `needs \
citation`. These are terminal validation failures in headings, prose, lists, \
tables, code fences, and inline code.
- If evidence uses the literal validation-reserved word `placeholder` as a \
code/comment concept, do NOT copy that word into `markdown`. Paraphrase with \
precise safe wording such as no-op, stub, default, temporary body, route variable \
marker, or template marker as appropriate, and cite the evidence.
- No empty headings, apologies, or meta commentary about yourself or these \
instructions.
- No empty headings: every heading you emit MUST be followed by substantive \
non-heading content before the next heading. Do not put one heading directly \
after another heading, even with blank lines between them.
- If the `markdown` starts with the section title heading, the next nonblank line \
MUST be a substantive introductory paragraph, list item, or table row with an \
inline citation; it MUST NOT be another heading.
- Do NOT emit a decorative duplicate title heading with no body. A title heading \
is allowed only when it is immediately followed by substantive cited content.
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
        "markdown": ("## " + title + "\n\nThis introductory paragraph states "
                     "an evidence-backed summary for the section before any "
                     "subheading. [ev:" + section_id + ":0001]\n\n"
                     "### Key Evidence\n\nThis subsection opens with cited body "
                     "content before any later heading. "
                     "[ev:" + section_id + ":0001]"),
        "used_evidence_ids": ["ev:" + section_id + ":0001"],
        "self_check": {
            "valid_json": True,
            "json_strings_escaped": True,
            "no_uncited_repo_claims": True,
            "no_context_artifact_citations": True,
            "no_placeholders": True,
            "no_empty_headings": True,
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
                     "paragraph/subsection with valid inline citations drawn ONLY "
                     "from that topic's supporting evidence_ids, and declare it in "
                     "`covered_topics[]`:")
        lines.append("")
        for ob in obligations:
            ids = ", ".join(f"`{e}`" for e in ob.get("supporting_evidence_ids") or [])
            lines.append(f"- **{ob.get('topic')}** — cite from: {ids or '(none)'}")
        lines.append("")
        lines.append("Evidence scope distinction for required-topic coverage:")
        lines.append("- `allowed_evidence_ids` is the section-wide citation allowlist; "
                     "those ids may support other section prose when relevant.")
        lines.append("- For a required topic, its listed `supporting_evidence_ids` are "
                     "the ONLY ids you may cite in the paragraph/subsection/block whose "
                     "purpose is to satisfy that topic, and the ONLY ids you may put in "
                     "that topic's `covered_topics[].evidence_ids` row.")
        lines.append("- Do NOT cite broader section evidence inside a required-topic "
                     "coverage block unless that id is also in that topic's "
                     "supporting_evidence_ids.")
        lines.append("- If broader allowed evidence is useful, discuss it elsewhere "
                     "outside the required-topic coverage block, and do not include it "
                     "in that topic's `covered_topics[].evidence_ids`.")
        lines.append("- Using an id from `allowed_evidence_ids` is not enough for "
                     "required-topic coverage; for that topic, the id counts only if "
                     "it is also listed in that topic's `supporting_evidence_ids`.")
        lines.append("")
        lines.append("For every required topic, add a `covered_topics[]` row with "
                     "`status: \"covered\"`, the `evidence_ids` you actually cited "
                     "inside that topic's coverage block (each MUST be one of that "
                     "topic's supporting evidence_ids), and a `markdown_anchor` equal "
                     "to the GitHub heading slug where you explain it. Omitting a "
                     "required topic, leaving an empty heading, citing broader section "
                     "evidence inside the topic block, or declaring an id outside its "
                     "supporting set fails validation.")
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
