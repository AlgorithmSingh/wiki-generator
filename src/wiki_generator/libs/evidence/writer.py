"""Write the Phase 3 artifact set: packets, manifest, validation, report, unresolved.

All writes go through the shared deterministic serializers in ``util`` (no
timestamps, stable key insertion order) so reruns over identical inputs are
byte-identical.
"""
from __future__ import annotations

import os

from .. import markdown as md
from .. import util
from .aggregate import LANE_SUMMARY_ORDER
from .schema import MANIFEST_SCHEMA_VERSION


def _rel(bundle, abspath: str) -> str:
    return bundle.paths.rel(abspath).replace(os.sep, "/")


def write_all(bundle, options, packets, validation, unresolved,
              *, evidenced=None) -> list[str]:
    """Write every output artifact. Returns bundle-relative paths written."""
    out = options.out_dir
    packets_dir = os.path.join(out, "packets")
    os.makedirs(packets_dir, exist_ok=True)

    written: list[str] = []
    packet_paths: list[str] = []
    for packet in packets:
        ppath = os.path.join(packets_dir, f"{packet['section_id']}.json")
        util.write_json(ppath, packet)
        packet_paths.append(_rel(bundle, ppath))

    combined = os.path.join(out, "evidence-packets.jsonl")
    util.write_jsonl(combined, packets)

    # Phase 3 evidenced coverage: deterministic per-required-topic status matrix
    # + human-readable remediation. Written in both modes (report-only in baseline,
    # blocking in enhancement) so the artifact contract is stable.
    evidenced_paths: list[str] = []
    if evidenced is not None:
        ec_json = os.path.join(out, "evidenced-coverage.json")
        util.write_json(ec_json, evidenced.matrix)
        ec_report = os.path.join(out, "evidenced-coverage-report.md")
        util.write_text(ec_report, _evidenced_report(bundle, evidenced))
        evidenced_paths = [_rel(bundle, ec_json), _rel(bundle, ec_report)]

    manifest = _manifest(bundle, options, packets, packet_paths, validation,
                         evidenced=evidenced)
    manifest_path = os.path.join(out, "evidence-manifest.json")
    util.write_json(manifest_path, manifest)

    validation_path = os.path.join(out, "retrieval-validation.json")
    util.write_json(validation_path, validation)

    unresolved_path = os.path.join(out, "unresolved-evidence.jsonl")
    util.write_jsonl(unresolved_path, unresolved)

    report_path = os.path.join(out, "retrieval-report.md")
    util.write_text(report_path, _report(bundle, options, packets, validation,
                                         unresolved))

    for p in (combined, manifest_path, validation_path, unresolved_path, report_path):
        written.append(_rel(bundle, p))
    return packet_paths + written + evidenced_paths


def _manifest(bundle, options, packets, packet_paths, validation,
              *, evidenced=None) -> dict:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "bundle_root": bundle.root,
        "document_plan": "plans/document-plan.json",
        "section_plans": "plans/section-plans.jsonl",
        "retrieval_capabilities": "rag/retrieval-capabilities.json",
        "retrieval_mode": bundle.retrieval_mode,
        "coverage_mode": options.coverage_mode,
        "section_count": len(bundle.section_order),
        "packet_count": len(packets),
        "combined_packets": _rel(bundle, os.path.join(options.out_dir,
                                                      "evidence-packets.jsonl")),
        "packet_paths": packet_paths,
        "validation": _rel(bundle, os.path.join(options.out_dir,
                                                "retrieval-validation.json")),
        "report": _rel(bundle, os.path.join(options.out_dir, "retrieval-report.md")),
        "status": validation["status"],
    }
    if evidenced is not None:
        manifest["evidenced_coverage"] = _rel(
            bundle, os.path.join(options.out_dir, "evidenced-coverage.json"))
        manifest["evidenced_coverage_report"] = _rel(
            bundle, os.path.join(options.out_dir, "evidenced-coverage-report.md"))
        manifest["evidenced_coverage_status"] = evidenced.matrix["status"]
    return manifest


def _report(bundle, options, packets, validation, unresolved) -> str:
    counts = validation["counts"]
    lines: list[str] = []
    lines += md.heading(1, "Phase 3 — Evidence Retrieval Report")
    status = validation["status"].upper()
    lines.append(f"**Status:** {status}")
    if validation["failure_category"]:
        lines.append(f"**Failure category:** `{validation['failure_category']}`")
    lines.append("")

    lines += md.heading(2, "Inputs")
    lines.append(f"- Bundle root: `{bundle.root}`")
    lines.append("- Document plan: `plans/document-plan.json`")
    lines.append("- Section plans: `plans/section-plans.jsonl`")
    lines.append("- Capabilities: `rag/retrieval-capabilities.json`")
    lines.append(f"- Retrieval mode: `{bundle.retrieval_mode}`")
    lines.append("")

    lines += md.heading(2, "Outputs")
    for name in ("evidence-manifest.json", "evidence-packets.jsonl",
                 "packets/<section_id>.json", "retrieval-validation.json",
                 "unresolved-evidence.jsonl", "retrieval-report.md"):
        lines.append(f"- `{_rel(bundle, os.path.join(options.out_dir, name))}`")
    lines.append("")

    lines += md.heading(2, "Summary")
    lines.append(f"- Sections expected: {counts['sections_expected']}")
    lines.append(f"- Sections processed: {counts['sections_processed']}")
    lines.append(f"- Packets written: {counts['packets_written']}")
    lines.append(f"- Evidence items: {counts['evidence_items']}")
    lines.append("")

    lines += md.heading(2, "Contract checks")
    rows = [[c["name"], c["status"], c["details"]] for c in validation["contract_checks"]]
    lines += md.md_table(["check", "status", "details"], rows)

    lines += md.heading(2, "Evidence by section and lane")
    header = ["section", "order", "status", "evidence"] + list(LANE_SUMMARY_ORDER)
    rows = []
    by_id = {p["section_id"]: p for p in packets}
    for sid in bundle.section_order:
        p = by_id.get(sid)
        if p is None:
            continue
        ls = p.get("lane_summary", {})
        row = [sid, p.get("order"), (p.get("validation") or {}).get("status", "?"),
               len(p.get("evidence", []))]
        row += [ls.get(lane, {}).get("returned", 0) for lane in LANE_SUMMARY_ORDER]
        rows.append(row)
    lines += md.md_table(header, rows)

    lines += md.heading(2, "Exact-request coverage")
    cov_rows = []
    covered_total = 0
    for sid in bundle.section_order:
        p = by_id.get(sid)
        if p is None:
            continue
        for rec in (p.get("coverage") or {}).get("exact_requests", []):
            if rec.get("status") == "covered":
                covered_total += 1
                continue
            cov_rows.append([sid, rec.get("lane"), rec.get("source_field"),
                             rec.get("requested_input"), rec.get("candidate_count"),
                             rec.get("kept_count"), rec.get("status")])
    if cov_rows:
        lines.append(f"_{covered_total} exact request(s) covered; "
                     f"{len(cov_rows)} not covered:_")
        lines.append("")
        lines += md.md_table(
            ["section", "lane", "source_field", "requested", "candidates",
             "kept", "status"], cov_rows)
    else:
        lines.append(f"_all {covered_total} resolved exact request(s) with "
                     "candidates are covered_")
        lines.append("")

    lines += md.heading(2, "Unresolved evidence")
    if unresolved:
        from collections import Counter
        by_reason = Counter(f"{u['type']}/{u['reason']}" for u in unresolved)
        lines += md.count_table(by_reason, ["type/reason", "count"], 50)
    else:
        lines.append("_none_")
        lines.append("")

    lines += md.heading(2, "Notes for the writing phase")
    if validation["failure_category"]:
        lines.append(_fix_note(validation["failure_category"]))
    else:
        lines.append("- Evidence is grounded and validated. Later Wiki writing should "
                     "cite the `source` anchors in each packet; treat `low` confidence "
                     "graph context as approximate.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _evidenced_report(bundle, evidenced) -> str:
    """Human-readable evidenced-coverage summary + remediation (spec artifact)."""
    m = evidenced.matrix
    c = m["counts"]
    lines: list[str] = []
    lines += md.heading(1, "Phase 3 — Evidenced Coverage Report")
    lines.append(f"**Mode:** `{m['coverage_mode']}` "
                 f"({'enforced' if m['enforced'] else 'report-only'})")
    lines.append(f"**Status:** {m['status'].upper()}")
    if m["failure_category"]:
        lines.append(f"**Failure category:** `{m['failure_category']}`")
    lines.append("")
    lines.append("> Evidenced coverage maps each planned **required** topic through the "
                 "plan's explicit `topic_evidence_requirements[]` source fields to "
                 "citeable exact-evidence IDs (no fuzzy prose matching). Broad recall "
                 "(`bm25`/`vector`/`graph_neighbors`/`search_hints`) is supporting "
                 "context only — it can make a topic `weak` but never `sufficient`. "
                 "Context artifacts, `derived/`, `plans/`, generated wiki files, and "
                 "the reference benchmark are never citeable.")
    lines.append("")

    lines += md.heading(2, "Summary")
    lines.append(f"- Sections: {c['sections']}")
    lines.append(f"- Required topics: {c['required_topics']}")
    lines.append(f"- sufficient: {c['sufficient']}  weak: {c['weak']}  "
                 f"missing: {c['missing']}  not_applicable: {c['not_applicable']}")
    lines.append("")

    lines += md.heading(2, "Required-topic evidence by section")
    rows = []
    for sec in m["sections"]:
        for t in sec["topics"]:
            if not t["required"]:
                continue
            rows.append([sec["section_id"], t["topic"], t["status"],
                         t["evidence_count"], t["min_items"],
                         ", ".join(t["source_fields"]) or "—",
                         ", ".join(t["mapped_evidence_ids"]) or "—"])
    lines += md.md_table(
        ["section", "topic", "status", "evidence", "min", "source_fields",
         "evidence_ids"], rows)

    blocking = [t for sec in m["sections"] for t in sec["topics"]
                if t["required"] and t["status"] in ("weak", "missing")]
    if blocking:
        lines += md.heading(2, "Blocking required topics (remediation)")
        for sec in m["sections"]:
            for t in sec["topics"]:
                if t["required"] and t["status"] in ("weak", "missing"):
                    lines.append(f"- `{sec['section_id']}` / **{t['topic']}** — "
                                 f"`{t['status']}` (`{t['diagnostic_code']}`): "
                                 f"{t['remediation']}")
        lines.append("")

    lines += md.heading(2, "Notes")
    if m["status"] == "fail":
        lines.append("- Enhancement mode: weak/missing required-topic evidence is a "
                     "pipeline failure BEFORE Phase 4. Fix upstream — improve the "
                     "Phase 2 plan's topic/source obligations or retrieval indexing, "
                     "or explicitly accept a human-reviewed known gap. This gate "
                     "does not synthesize evidence, retry, or downgrade required "
                     "topics to optional.")
    elif not m["enforced"]:
        lines.append("- Baseline mode: evidenced coverage is reported but not "
                     "enforced. Re-run with `--coverage-mode enhancement` to gate "
                     "weak/missing required-topic evidence before Phase 4.")
    else:
        lines.append("- All required topics have sufficient citeable exact evidence "
                     "for Phase 4 writing.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _fix_note(category: str) -> str:
    notes = {
        "bad_missing_input_artifact":
            "- Fix the missing/corrupt bundle artifacts, rerun `decompose` or "
            "`build-retrieval` as appropriate, then rerun the all-sections command.",
        "bad_underspecified_normalized_plan":
            "- Fix Phase 2 planning / `normalize-plan` for the failing sections, "
            "regenerate the plan artifacts, then rerun the all-sections command.",
        "retriever_implementation_bug":
            "- Add/adjust a failing test, fix the retriever code, rerun tests, then "
            "rerun the all-sections command.",
    }
    return notes.get(category, "- See retrieval-validation.json for details.")


def write_failure_stub(out_dir: str, bundle_root: str, category: str,
                       message: str) -> list[str]:
    """Best-effort validation + report when the bundle could not even be loaded."""
    from .schema import VALIDATION_SCHEMA_VERSION
    written: list[str] = []
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return written
    validation = {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "fail",
        "failure_category": category,
        "retrieval_mode": None,
        "counts": {"sections_expected": 0, "sections_processed": 0,
                   "packets_written": 0, "evidence_items": 0},
        "contract_checks": [{"name": "load_bundle", "status": "fail",
                             "details": message}],
        "section_results": [],
        "errors": [message],
        "warnings": [],
    }
    vpath = os.path.join(out_dir, "retrieval-validation.json")
    util.write_json(vpath, validation)
    written.append(vpath)

    report = (f"# Phase 3 — Evidence Retrieval Report\n\n**Status:** FAIL\n\n"
              f"**Failure category:** `{category}`\n\n"
              f"- Bundle root: `{bundle_root}`\n- Error: {message}\n\n"
              f"## Notes\n\n{_fix_note(category)}\n")
    rpath = os.path.join(out_dir, "retrieval-report.md")
    util.write_text(rpath, report)
    written.append(rpath)
    return written
