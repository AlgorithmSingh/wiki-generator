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
- Cite with the EXACT inline syntax `[ev:<section_id>:<NNNN>]`, copied verbatim \
from the `evidence_id` field. Multiple citations are adjacent brackets, e.g. \
`... [ev:overview:0001][ev:overview:0004]`.
- You may ONLY cite `evidence_id` values listed in `allowed_evidence_ids`. Never \
invent an evidence id, never cite a file path or URL directly, never use \
footnotes, and never cite `search_hints` or `context_artifacts`.
- Do NOT introduce any identifier (path, symbol, route, env var, command, \
dependency, version) that does not appear in a cited evidence excerpt or its \
source metadata. If the evidence does not support a fact, omit the fact.
- Never synthesize or expand a file path: do not join a directory and a filename, \
complete a partial path, or infer a module's full path. Use a path ONLY when that \
exact string appears in a cited evidence item's `source` or excerpt — otherwise \
refer to the component by the name the evidence actually provides.
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


def _response_contract(section_id: str, title: str) -> dict:
    return {
        "schema_version": SECTION_DRAFT_SCHEMA_VERSION,
        "section_id": section_id,
        "title": title,
        "markdown": ("## " + title + "\n\n<the section body as GitHub-flavored "
                     "Markdown, with inline [ev:...] citations on every "
                     "repo-specific claim>"),
        "used_evidence_ids": ["ev:" + section_id + ":0001"],
        "self_check": {
            "no_uncited_repo_claims": True,
            "no_context_artifact_citations": True,
            "no_placeholders": True,
        },
    }


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
    parts.append("## Response contract (return EXACTLY this JSON shape)")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(_response_contract(sid, wp.title), indent=2,
                            ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("Return only the JSON object.")
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
    extra += [
        "",
        "## Your previous response (verbatim)",
        "```",
        prior_raw.strip(),
        "```",
        "",
        "Return only the corrected JSON object.",
    ]
    return base + "\n".join(extra) + "\n"
