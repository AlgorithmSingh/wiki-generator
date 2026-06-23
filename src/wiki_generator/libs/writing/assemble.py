"""Write every Phase 4 artifact: audit (prompts/responses/rewrites), generated
section Markdown, the assembled ``index.md``, the citation manifest, generated
metadata, the writing-validation report, and the final run report.

All writes go through the deterministic serializers in ``util`` (no timestamps,
stable key order) so a rerun over the same bundle + same responses is byte-stable.
"""
from __future__ import annotations

import os

from .. import markdown as md
from .. import util
from .schema import (
    CITATION_MANIFEST_SCHEMA_VERSION,
    GENERATED_DOCUMENT_SCHEMA_VERSION,
    GENERATED_SECTION_SCHEMA_VERSION,
)


def _rel(bundle_root: str, abspath: str) -> str:
    return os.path.relpath(abspath, bundle_root).replace(os.sep, "/")


def _audit_dir(out_dir: str, *parts: str) -> str:
    return os.path.join(out_dir, "audit", *parts)


# --- audit --------------------------------------------------------------------
def write_prompt(prompts_dir: str, section_id: str, prompt_text: str) -> str:
    path = os.path.join(prompts_dir, f"{section_id}.md")
    util.write_text(path, prompt_text)
    return path


def write_response_audit(out_dir: str, section_id: str, *, raw_text,
                         parsed, generation_meta: dict) -> tuple[str, str]:
    raw_path = _audit_dir(out_dir, "responses", f"{section_id}.raw.txt")
    util.write_text(raw_path, raw_text if raw_text is not None else "")
    parsed_path = _audit_dir(out_dir, "responses", f"{section_id}.parsed.json")
    util.write_json(parsed_path, {"parsed": parsed, "generation": generation_meta})
    return raw_path, parsed_path


def write_rewrite_audit(out_dir: str, section_id: str, attempt: int, *,
                        prompt: str, raw_text, problems: list) -> None:
    base = _audit_dir(out_dir, "rewrites", f"{section_id}-attempt-{attempt}")
    util.write_text(os.path.join(base, "prompt.md"), prompt)
    util.write_text(os.path.join(base, "response.raw.txt"),
                    raw_text if raw_text is not None else "")
    util.write_json(os.path.join(base, "problems.json"), {"problems": problems})


# --- section markdown ---------------------------------------------------------
def section_filename(order: int, section_id: str) -> str:
    return f"{int(order):03d}-{section_id}.md"


def write_section_markdown(out_dir: str, order: int, section_id: str,
                           markdown_text: str) -> str:
    path = os.path.join(out_dir, "sections", section_filename(order, section_id))
    text = markdown_text if markdown_text.endswith("\n") else markdown_text + "\n"
    util.write_text(path, text)
    return path


# --- citation manifest --------------------------------------------------------
def build_citation_manifest(bundle, generated: list) -> dict:
    """Map every used citation to its EvidencePacket item + source anchor.

    ``generated`` carries each section's resolved ``evidence_ids_used`` and the
    output section_id, so a citation records both where it came from (the owning
    packet) and where it is used."""
    used_by: dict = {}
    total_occurrences = 0
    for g in generated:
        for eid in g.get("evidence_ids_used", []):
            used_by.setdefault(eid, []).append(g["section_id"])
        total_occurrences += g.get("validation", {}).get("citations_total", 0)

    citations = []
    for eid in sorted(used_by):
        item = bundle.evidence_index.get(eid)
        if item is None:
            continue
        citations.append({
            "evidence_id": eid,
            "owner_section_id": item.section_id,
            "used_in_sections": sorted(set(used_by[eid])),
            "source_packet_path": item.packet_path,
            "lane": item.lane,
            "type": item.type,
            "confidence": item.confidence,
            "source": item.source,
        })
    return {
        "schema_version": CITATION_MANIFEST_SCHEMA_VERSION,
        "bundle_root": bundle.root,
        "section_plans_sha_basis": "plans/section-plans.jsonl",
        "counts": {
            "distinct_citations": len(citations),
            "total_citation_occurrences": total_occurrences,
        },
        "citations": citations,
    }


# --- index --------------------------------------------------------------------
def build_index(bundle, generated: list, manifest: dict) -> str:
    doc = bundle.document_plan
    title = doc.get("title") or "Generated Wiki"
    n = len(generated)
    m = manifest["counts"]["distinct_citations"]
    lines: list[str] = []
    lines += md.heading(1, title)
    if doc.get("purpose"):
        lines.append(f"> {doc['purpose']}")
        lines.append("")
    lines.append(f"_Generated DeepWiki-style documentation: {n} section(s), grounded "
                 f"in {m} cited source-evidence item(s) from the validated Phase 1-3 "
                 "bundle. Each section links below; every repo-specific claim carries "
                 "an inline citation to a source anchor._")
    lines.append("")
    lines += md.heading(2, "Contents")
    plans = bundle.section_plans
    for i, g in enumerate(generated, 1):
        sid = g["section_id"]
        # link target relative to index.md (i.e. sections/NNN-sid.md)
        link = f"sections/{section_filename(g['order'], sid)}"
        lines.append(f"{i}. [{g['title']}]({link})")
        purpose = (plans.get(sid) or {}).get("purpose")
        if purpose:
            lines.append(f"   - {purpose}")
    lines.append("")
    lines += md.heading(2, "Sources")
    lines.append("Each inline citation resolves to a source anchor "
                 "(`wiki/metadata/citation-manifest.json`):")
    lines.append("")
    rows = []
    for c in manifest["citations"]:
        src = c["source"]
        anchor = src.get("path") or src.get("artifact") or ""
        rng = src.get("range") or {}
        if rng:
            anchor += f":{rng.get('start_line')}-{rng.get('end_line')}"
        elif src.get("route"):
            anchor = f"{src.get('method','')} {src.get('route')}".strip()
        rows.append([f"`{c['evidence_id']}`", c["lane"], c["confidence"], anchor])
    lines += md.md_table(["citation", "lane", "confidence", "source"], rows)
    return "\n".join(lines) + "\n"


# --- generated metadata -------------------------------------------------------
def generated_section_record(bundle, options, *, writing_packet, validation,
                             prompt_path, raw_path, section_file, attempts) -> dict:
    sid = writing_packet.section_id
    packet_rel = bundle.packet_paths.get(sid, "")
    packet_abs = os.path.join(bundle.root, packet_rel)
    plan = bundle.section_plans.get(sid) or {}
    needs = plan.get("retrieval_needs") or {}
    consulted = []
    for ca in needs.get("context_artifacts") or []:
        path = ca.get("path") if isinstance(ca, dict) else ca
        if path:
            consulted.append({"path": path, "citeable_as_evidence": False})
    unsupported = [v["message"] for v in validation.violations
                   if v["code"] == "invented_identifier"]
    ph = [v["message"] for v in validation.violations if v["code"] == "placeholder"]
    ca_cits = [v["message"] for v in validation.violations
               if v["code"] == "context_artifact_citation"]
    return {
        "schema_version": GENERATED_SECTION_SCHEMA_VERSION,
        "section_id": sid,
        "title": writing_packet.title,
        "order": writing_packet.order,
        "markdown_path": _rel(bundle.root, section_file),
        "source_packet_path": packet_rel,
        "source_packet_sha256": (f"sha256:{util.sha256_file(packet_abs)}"
                                 if os.path.isfile(packet_abs) else None),
        "evidence_ids_available": list(writing_packet.allowed_evidence_ids),
        "evidence_ids_used": list(validation.cited_ids),
        "cross_section_citations": list(validation.cross_section),
        "context_artifacts_consulted": consulted,
        "generation": {
            "provider_mode": options.provider,
            "model": options.model_for_metadata,
            "temperature": options.temperature if options.uses_live_model else None,
            "max_output_tokens": (options.max_output_tokens
                                  if options.uses_live_model else None),
            "prompt_path": _rel(bundle.root, prompt_path),
            "response_path": _rel(bundle.root, raw_path),
            "finish_reason": validation.finish_reason,
            "rewrite_attempts": attempts,
        },
        "validation": {
            "status": validation.status,
            "citations_total": validation.citations_total,
            "unresolved_citations": [v["message"] for v in validation.violations
                                     if v["code"] == "unresolved_citation"],
            "context_artifact_citations": ca_cits,
            "unsupported_claims": unsupported,
            "placeholders": ph,
            "warnings": list(validation.warnings),
        },
    }


def write_generated_metadata(out_dir: str, bundle, options, generated: list,
                             manifest: dict, validation_doc: dict) -> dict:
    meta_dir = os.path.join(out_dir, "metadata")
    util.write_jsonl(os.path.join(meta_dir, "generated-sections.jsonl"), generated)
    manifest_path = os.path.join(meta_dir, "citation-manifest.json")
    util.write_json(manifest_path, manifest)

    document = {
        "schema_version": GENERATED_DOCUMENT_SCHEMA_VERSION,
        "bundle_root": bundle.root,
        "document_path": _rel(bundle.root, os.path.join(out_dir, "index.md")),
        "section_order": list(bundle.section_order),
        "section_paths": [g["markdown_path"] for g in generated],
        "citation_manifest_path": _rel(bundle.root, manifest_path),
        "validation_path": _rel(bundle.root,
                                os.path.join(out_dir, "validation",
                                             "writing-validation.json")),
        "provider_mode": options.provider,
        "model": options.model_for_metadata,
        "status": validation_doc["status"],
    }
    util.write_json(os.path.join(meta_dir, "generated-document.json"), document)
    return document


# --- validation + run report --------------------------------------------------
def write_validation(out_dir: str, validation_doc: dict) -> None:
    vdir = os.path.join(out_dir, "validation")
    util.write_json(os.path.join(vdir, "writing-validation.json"), validation_doc)
    lines: list[str] = []
    lines += md.heading(1, "Phase 4 — Writing Validation")
    lines.append(f"**Status:** {validation_doc['status'].upper()}")
    lines.append("")
    lines.append(f"- Sections: {validation_doc['generated_count']}/"
                 f"{validation_doc['section_count']}")
    lines.append(f"- Distinct citations: {validation_doc['distinct_citations']}")
    lines.append("")
    lines += md.heading(2, "Checks")
    rows = [[c["name"], c["status"], c["details"]] for c in validation_doc["checks"]]
    lines += md.md_table(["check", "status", "details"], rows)
    if validation_doc["failures"]:
        lines += md.heading(2, "Failures")
        for f in validation_doc["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    util.write_text(os.path.join(vdir, "writing-validation-report.md"),
                    "\n".join(lines) + "\n")


def write_run_report(out_dir: str, *, bundle, options, document, validation_doc,
                     warnings: list) -> str:
    lines: list[str] = []
    lines += md.heading(1, "Phase 4 Run Report")
    status = document["status"].upper()
    lines.append(f"**Status:** {status}")
    lines.append("")
    lines += md.heading(2, "Run")
    lines.append(f"- Bundle: `{bundle.root}`")
    lines.append(f"- Provider mode: `{options.provider}`")
    if options.model_for_metadata:
        lines.append(f"- Model: `{options.model_for_metadata}` "
                     f"(temperature {options.temperature}, "
                     f"max_output_tokens {options.max_output_tokens})")
    lines.append(f"- Output: `{_rel(bundle.root, os.path.join(out_dir, 'index.md'))}`")
    lines.append("")
    lines += md.heading(2, "Upstream gates")
    lines.append(f"- Readiness: {bundle.readiness_status['status']} "
                 f"(Failures: {bundle.readiness_status['failures']})")
    lines.append(f"- Retrieval validation: {bundle.retrieval_validation.get('status')}")
    lines.append(f"- Gate checks: {sum(1 for c in bundle.gate_report if c['status']=='pass')}"
                 f"/{len(bundle.gate_report)} pass")
    lines.append("")
    lines += md.heading(2, "Outputs")
    counts = validation_doc
    lines.append(f"- Sections generated: {counts['generated_count']}/"
                 f"{counts['section_count']}")
    lines.append(f"- Distinct citations: {counts['distinct_citations']}")
    lines.append(f"- Citation manifest: `{document['citation_manifest_path']}`")
    lines.append(f"- Validation: `{document['validation_path']}`")
    lines.append("")
    if warnings:
        lines += md.heading(2, "Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    if validation_doc["status"] != "pass":
        lines += md.heading(2, "Failures")
        for f in validation_doc["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    path = os.path.join(out_dir, "PHASE4_RUN_REPORT.md")
    util.write_text(path, "\n".join(lines) + "\n")
    return path


def write_failure_report(out_dir: str, bundle_root: str, category: str,
                         message: str) -> str:
    """Best-effort run report on a fail-closed condition (gate/provider/writing).

    Always emits a PHASE4_RUN_REPORT.md so a failed run still leaves an auditable
    record pointing at the owning phase."""
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return ""
    lines = [
        "# Phase 4 Run Report", "",
        "**Status:** FAIL", "",
        f"**Failure category:** `{category}`", "",
        f"- Bundle: `{bundle_root}`",
        f"- Error: {message}", "",
        "## Notes", "",
        "- Phase 4 failed closed. It does not repair plans, re-run Phase 3, or "
        "invent fallback evidence. Fix the issue in the owning phase "
        "(readiness/Phase 2 for gate failures; provider config for provider "
        "failures; the pasted/generated response for writing-validation "
        "failures), then rerun `write-wiki`.",
    ]
    path = os.path.join(out_dir, "PHASE4_RUN_REPORT.md")
    util.write_text(path, "\n".join(lines) + "\n")
    return path
