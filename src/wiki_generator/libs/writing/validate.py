"""Per-section draft validation and final whole-document validation.

A draft is classified into ``pass`` (no violations), ``rewrite`` (only
format/citation violations that a bounded rewrite may fix), or ``fail`` (any
terminal violation: truncation, a cited context artifact, an invented/unsupported
identifier, or a placeholder). The orchestrator uses that classification to
decide whether one of the (≤2) audited rewrites is permitted.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import citations as cit
from .schema import (
    GOOD_FINISH_REASONS,
    TRUNCATION_FINISH_REASONS,
    WRITING_VALIDATION_SCHEMA_VERSION,
    structural_draft_errors,
)

# Violation codes that a bounded format/citation rewrite is allowed to address.
REWRITEABLE_CODES = frozenset({
    "malformed_json", "wrong_section_id", "empty_markdown", "schema_version",
    "unresolved_citation", "malformed_citation_syntax", "uncited_repo_claim",
})
# Terminal codes: never rewritten, always a fail-closed stop.
# (A "different bundle" citation cannot arise: a Phase 4 run loads packets from
# exactly one bundle root, so a citation either resolves in this bundle's
# EvidenceIndex or is reported as ``unresolved_citation`` — there is no separate
# cross-bundle code to add.)
TERMINAL_CODES = frozenset({
    "truncation", "context_artifact_citation", "invented_identifier",
    "placeholder", "empty_response",
})


@dataclass
class SectionValidation:
    section_id: str
    status: str                              # pass | rewrite | fail
    markdown: str | None = None
    used_evidence_ids: list = field(default_factory=list)
    cited_ids: list = field(default_factory=list)
    cross_section: list = field(default_factory=list)
    violations: list = field(default_factory=list)  # {code, message, rewriteable}
    warnings: list = field(default_factory=list)
    citations_total: int = 0
    finish_reason: str = "UNKNOWN"

    @property
    def rewriteable_problems(self) -> list:
        return [f"{v['code']}: {v['message']}" for v in self.violations]


def _available_text(bundle, section_id: str, cited_ids) -> str:
    """Excerpts + serialized source metadata the section may rely on: its own
    packet evidence plus any cross-section evidence it actually cited."""
    parts: list[str] = []
    seen: set = set()

    def add(item):
        if item is None or item.evidence_id in seen:
            return
        seen.add(item.evidence_id)
        parts.append(item.excerpt or "")
        parts.append(json.dumps(item.source, ensure_ascii=False, default=str))
        parts.append(json.dumps(item.provenance, ensure_ascii=False, default=str))

    for eid in bundle.section_evidence_ids.get(section_id, set()):
        add(bundle.evidence_index.get(eid))
    for eid in cited_ids:
        add(bundle.evidence_index.get(eid))
    return "\n".join(parts)


def validate_section_draft(*, section_id, draft, parse_note, finish_reason,
                           bundle) -> SectionValidation:
    """Validate one parsed section draft against citation/claim discipline."""
    violations: list[dict] = []
    warnings: list[str] = []

    def add(code, message):
        violations.append({"code": code, "message": message,
                           "rewriteable": code in REWRITEABLE_CODES})

    # 0. truncation / provider finish reason (terminal) -----------------------
    fr = finish_reason or "UNKNOWN"
    if fr in TRUNCATION_FINISH_REASONS:
        add("truncation",
            f"provider finish_reason={fr}; output truncated — increase "
            "max_output_tokens (>=32768 for gemini-2.5-pro)")

    # 1. parse / structure -----------------------------------------------------
    if draft is None:
        add("malformed_json", f"response did not parse: {parse_note}")
        status = "fail" if any(v["code"] in TERMINAL_CODES for v in violations) \
            else "rewrite"
        return SectionValidation(section_id, status, violations=violations,
                                 warnings=warnings, finish_reason=fr)

    for err in structural_draft_errors(draft, expected_section_id=section_id):
        if "section_id" in err:
            add("wrong_section_id", err)
        elif "markdown is missing or empty" in err:
            add("empty_markdown", err)
        elif "schema_version" in err:
            add("schema_version", err)
        else:
            add("malformed_json", err)

    markdown = draft.get("markdown") if isinstance(draft.get("markdown"), str) else ""
    used_ids = list(draft.get("used_evidence_ids") or [])

    # 2. citation resolution ---------------------------------------------------
    cres = cit.resolve_citations(
        markdown, section_id=section_id, evidence_index=bundle.evidence_index,
        section_evidence_ids=bundle.section_evidence_ids)
    if cres["unresolved"]:
        add("unresolved_citation",
            f"citation(s) resolve to no evidence item: {cres['unresolved']}")
    if cres["malformed_like"]:
        add("malformed_citation_syntax",
            f"malformed ev: token(s) (not a valid [ev:...] citation): "
            f"{cres['malformed_like']}")
    if cres["cross_section"]:
        warnings.append(
            f"cross-section citation(s) (recorded in manifest): {cres['cross_section']}")

    # 3. context-artifact laundering (terminal) --------------------------------
    ca = cit.find_context_artifact_references(markdown)
    if ca:
        add("context_artifact_citation",
            f"prose references non-citeable context artifact(s)/plan(s): {ca}")

    # 4. placeholders / apologies (terminal) -----------------------------------
    ph = cit.find_placeholders(markdown)
    if ph:
        add("placeholder", f"placeholder/apology/empty-heading present: {ph[:5]}")

    # 5. claims: invented identifiers (terminal), uncited paragraphs (rewrite) -
    available = _available_text(bundle, section_id, cres["resolved"])
    claims = cit.analyze_claims(markdown, available)
    if claims["invented_identifiers"]:
        add("invented_identifier",
            "identifier(s) not supported by any cited/available evidence: "
            f"{claims['invented_identifiers'][:8]}")
    if claims["uncited_paragraphs"]:
        add("uncited_repo_claim",
            "paragraph(s) make a groundable repo claim but cite nothing: "
            + " | ".join(claims["uncited_paragraphs"][:3]))

    # confidence discipline: low-only support is a warning, not a hard fail.
    low_only = [eid for eid in cres["resolved"]
                if (bundle.evidence_index.get(eid)
                    and bundle.evidence_index[eid].confidence == "low")]
    if cres["resolved"] and len(low_only) == len(cres["resolved"]):
        warnings.append("section cites only low-confidence (graph-context) evidence; "
                        "claims should stay cautious")

    terminal = any(v["code"] in TERMINAL_CODES for v in violations)
    if not violations:
        status = "pass"
    elif terminal:
        status = "fail"
    else:
        status = "rewrite"
    return SectionValidation(
        section_id, status, markdown=markdown, used_evidence_ids=used_ids,
        cited_ids=cres["resolved"], cross_section=cres["cross_section"],
        violations=violations, warnings=warnings,
        citations_total=len(cit.extract_citations(markdown)), finish_reason=fr)


# --- final whole-document validation ------------------------------------------
def validate_document(bundle, generated, citation_manifest, out_dir) -> dict:
    """Validate the assembled wiki after section files + index are written.

    ``generated`` is a list of generated-section metadata dicts (in order)."""
    checks: list[dict] = []

    def chk(name, ok, details):
        checks.append({"name": name, "status": "pass" if ok else "fail",
                       "details": details})

    by_sid = {g["section_id"]: g for g in generated}
    # 1. one section file per planned section, in order
    missing = [sid for sid in bundle.section_order if sid not in by_sid]
    chk("every_section_generated", not missing,
        f"missing: {missing}" if missing else f"{len(generated)} sections")
    order_ok = [g["section_id"] for g in generated] == list(bundle.section_order)
    chk("sections_in_document_order", order_ok,
        "ok" if order_ok else f"{[g['section_id'] for g in generated]}")

    files_present = []
    for g in generated:
        p = os.path.join(bundle.root, g["markdown_path"])
        files_present.append(os.path.isfile(p))
    chk("section_files_exist", all(files_present),
        f"{sum(files_present)}/{len(generated)} files on disk")

    # 2. index contains all sections in order
    index_path = os.path.join(out_dir, "index.md")
    index_text = ""
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_text = f.read()
    nav_ok = all(g["section_id"] in index_text for g in generated)
    chk("index_navigation_complete", bool(index_text) and nav_ok,
        "index.md links every section" if nav_ok else "index.md missing sections")

    # 3. citations across section files resolve through the manifest
    manifest_ids = {c["evidence_id"] for c in citation_manifest.get("citations", [])}
    all_cited: set = set()
    unresolved: list[str] = []
    placeholders: list[str] = []
    laundered: list[str] = []
    for g in generated:
        p = os.path.join(bundle.root, g["markdown_path"])
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as f:
            text = f.read()
        for token in cit.distinct_citations(text):
            all_cited.add(token)
            if token not in bundle.evidence_index or token not in manifest_ids:
                unresolved.append(f"{g['section_id']}:{token}")
        placeholders += [f"{g['section_id']}:{h}" for h in cit.find_placeholders(text)]
        laundered += [f"{g['section_id']}:{r}"
                      for r in cit.find_context_artifact_references(text)]

    chk("all_citations_resolve_via_manifest", not unresolved,
        f"unresolved: {unresolved[:6]}" if unresolved else f"{len(all_cited)} distinct")
    unused = sorted(manifest_ids - all_cited)
    chk("no_unused_manifest_citations", not unused,
        f"unused: {unused[:6]}" if unused else "all manifest entries used")
    chk("no_placeholders", not placeholders,
        f"{placeholders[:6]}" if placeholders else "none")
    chk("no_context_artifact_citations", not laundered,
        f"{laundered[:6]}" if laundered else "none")

    # 4. provider finish reasons indicate complete output
    truncated = [g["section_id"] for g in generated
                 if g.get("generation", {}).get("finish_reason") not in GOOD_FINISH_REASONS]
    chk("no_truncated_sections", not truncated,
        f"truncated: {truncated}" if truncated else "all complete")

    failed = [c for c in checks if c["status"] != "pass"]
    return {
        "schema_version": WRITING_VALIDATION_SCHEMA_VERSION,
        "status": "pass" if not failed else "fail",
        "bundle_root": bundle.root,
        "section_count": len(bundle.section_order),
        "generated_count": len(generated),
        "distinct_citations": len(all_cited),
        "checks": checks,
        "failures": [f"{c['name']}: {c['details']}" for c in failed],
    }
