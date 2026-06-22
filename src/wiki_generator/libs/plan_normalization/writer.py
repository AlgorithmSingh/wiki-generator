"""Write the normalized Phase 2 plan artifacts.

Produces the canonical outputs Phase 3 consumes plus a human-readable plan, a
normalization report, the unresolved-reference log, and raw-extracted debug
copies. All writes are deterministic.
"""
from __future__ import annotations

import os

from ..util import write_json, write_jsonl, write_text
from .normalize import Result

DOCUMENT_PLAN_JSON = "document-plan.json"
DOCUMENT_PLAN_MD = "document-plan.md"
SECTION_PLANS_JSONL = "section-plans.jsonl"
REPORT_MD = "normalization-report.md"
READINESS_REPORT_MD = "phase3-readiness-report.md"
UNRESOLVED_JSONL = "unresolved-references.jsonl"
RAW_DOC_JSON = "raw-extracted-document-plan.json"
RAW_SECTIONS_JSONL = "raw-extracted-section-plans.jsonl"

# Map an unresolved-reference type to the exact lane it was rejected from, and a
# suggested upstream fix keyed by the rejection reason.
_LANE_FIELD = {
    "query_pack": "retrieval_needs.query_packs",
    "symbol": "retrieval_needs.symbols",
    "file": "retrieval_needs.files",
    "contract": "retrieval_needs.contracts",
    "test": "retrieval_needs.tests",
    "graph": "retrieval_needs.graph_nodes",
}
_FIX = {
    "context_only": "remove the planner-context doc from files[] "
                    "(kept in context_artifacts[])",
    "no_match": "use an exact handle from planning-handles.md, "
                "or move it to search_hints[]",
    "ambiguous": "disambiguate to one exact handle, or move it to search_hints[]",
    "path_only": "name an exact METHOD /path operation, or move it to search_hints[]",
    "hint": "name an exact handle, or move it to search_hints[]",
    "display_label": "use the exact node_id (not a display label), "
                     "or move it to search_hints[]",
    "no_retrieval_signal": "add exact handles, query_packs, search_hints, "
                           "or topic text",
}


def _readiness_failures(result: Result) -> dict:
    """Per-section list of readiness failures. A section is Phase-3-ready only if
    it has no rejected exact-lane references and a deterministic retrieval signal.

    A ``context_only`` rejection is NOT a failure: the normalizer already relocated
    the planner-context doc out of the exact ``files[]`` lane into
    ``context_artifacts[]`` (the spec-mandated fix), so the exact lane is clean.
    """
    by_section: dict[str, list] = {s["section_id"]: [] for s in result.sections}
    for u in result.unresolved:
        if u.get("reason") == "context_only":
            continue  # correctly relocated to context_artifacts[]; not a blocker
        sid = u.get("section_id")
        rec = by_section.setdefault(sid, [])
        rec.append({
            "field": _LANE_FIELD.get(u.get("type"), u.get("type")),
            "input": u.get("input"),
            "reason": u.get("reason"),
            "fix": _FIX.get(u.get("reason"),
                            "use an exact handle, or move it to search_hints[]"),
        })
    for s in result.sections:
        nh = s["retrieval_needs"]
        # A deterministic retrieval directive: an exact handle, a canonical query
        # pack, or a search hint. Bare title/topic text is not sufficient — it only
        # feeds BM25/vector recall and may match nothing, which Phase 3 would then
        # classify as bad_underspecified_normalized_plan (spec line 421).
        has_signal = (
            any(nh.get(k) for k in
                ("symbols", "files", "contracts", "tests", "graph_nodes"))
            or bool(nh.get("query_packs")) or bool(nh.get("search_hints")))
        if not has_signal:
            by_section.setdefault(s["section_id"], []).append({
                "field": "retrieval_needs", "input": "(none)",
                "reason": "no_retrieval_signal", "fix": _FIX["no_retrieval_signal"],
            })
    return by_section


def readiness_pass(result: Result) -> bool:
    failures = _readiness_failures(result)
    return not any(failures.get(s["section_id"]) for s in result.sections)


def _readiness_report_md(result: Result) -> str:
    dp = result.document_plan
    sections = result.sections
    failures = _readiness_failures(result)
    status = "PASS" if readiness_pass(result) else "FAIL"

    L = ["# Phase 3 Readiness Report", "",
         f"Status: {status}",
         f"Bundle: {dp['repo']['root']}",
         "Document plan: plans/document-plan.json",
         "Section plans: plans/section-plans.jsonl",
         f"Sections: {len(sections)}", "",
         "## Exact-lane checks", ""]
    for label, key, utype in (
            ("symbols", "symbols", "symbol"), ("files", "files", "file"),
            ("contracts", "contracts", "contract"), ("tests", "tests", "test"),
            ("graph_nodes", "graph_nodes", "graph"),
            ("query_packs", "query_packs", "query_pack")):
        resolved = sum(len(s["retrieval_needs"][key]) for s in sections)
        rejected = sum(1 for u in result.unresolved if u.get("type") == utype
                       and u.get("reason") != "context_only")
        L.append(f"- {label}: {resolved} resolved, {rejected} rejected")
    L.append("")

    total_hints = sum(len(s["retrieval_needs"].get("search_hints", []))
                      for s in sections)
    moved = sum(1 for s in sections
                for h in s["retrieval_needs"].get("search_hints", [])
                if h.get("reason") != "planner search hint")
    L += ["## Search hints", "",
          f"- Total: {total_hints}",
          f"- Broad/unresolvable requests moved out of exact lanes: {moved}", ""]
    for s in sections:
        n = len(s["retrieval_needs"].get("search_hints", []))
        if n:
            L.append(f"- `{s['section_id']}`: {n}")
    L.append("")

    total_ca = sum(len(s["retrieval_needs"].get("context_artifacts", []))
                   for s in sections)
    L += ["## Context artifacts", "",
          f"- Total (all non-citeable): {total_ca}", ""]
    for s in sections:
        for ca in s["retrieval_needs"].get("context_artifacts", []):
            L.append(f"- `{s['section_id']}`: `{ca['path']}` "
                     "(citeable_as_evidence: false)")
    L.append("")

    L += ["## Expected evidence derivation", ""]
    for s in sections:
        types = s.get("expected_evidence_types") or []
        L.append(f"- `{s['section_id']}`: "
                 + (", ".join(types) if types else "_none_"))
    L.append("")

    L += ["## Failures", ""]
    ordered = list(dp["section_order"]) + [
        s["section_id"] for s in sections
        if s["section_id"] not in dp["section_order"]]
    any_fail = False
    for sid in ordered:
        for f in failures.get(sid, []):
            any_fail = True
            L.append(f"- `{sid}` — {f['field']}: invalid input {f['input']!r} "
                     f"({f['reason']}); fix: {f['fix']}")
    if not any_fail:
        L.append("_none_")
    L.append("")
    return "\n".join(L) + "\n"


def _document_plan_md(result: Result) -> str:
    dp = result.document_plan
    L = [f"# {dp['title']}", "",
         f"- Repository: `{dp['repo']['name']}` (`{dp['repo']['root']}`)",
         f"- Source response: `{dp['source_raw_response']}`",
         f"- Provider: {dp.get('provider') or 'n/a'}",
         f"- Unresolved references: {dp['normalization']['unresolved_count']}",
         ""]
    if dp.get("purpose"):
        L += ["**Purpose.** " + dp["purpose"], ""]
    if dp.get("summary"):
        L += [dp["summary"], ""]
    if dp.get("audience"):
        L += [f"**Audience.** {dp['audience']}", ""]
    L += ["## Sections", ""]
    by_id = {s["section_id"]: s for s in result.sections}
    for sid in dp["section_order"]:
        s = by_id[sid]
        prefix = f"{s['order']}. "
        suffix = f"  _(under `{s['parent']}`)_" if s.get("parent") else ""
        L.append(f"{prefix}**{s['title']}** — `{sid}`{suffix}")
        if s.get("purpose"):
            L.append(f"   - Purpose: {s['purpose']}")
        nh = s["retrieval_needs"]
        bits = []
        if nh["query_packs"]:
            bits.append("query packs: " + ", ".join(f"`{q}`" for q in nh["query_packs"]))
        if nh["symbols"]:
            ok = sum(1 for x in nh["symbols"] if x["resolution"] in ("exact", "unique_alias"))
            bits.append(f"symbols: {ok}/{len(nh['symbols'])} resolved")
        if nh["files"]:
            ok = sum(1 for x in nh["files"]
                     if x["resolution"] in ("file_exists", "unique_suffix", "digest_artifact"))
            bits.append(f"files: {ok}/{len(nh['files'])} resolved")
        if nh["contracts"]:
            bits.append(f"contracts: {len(nh['contracts'])}")
        if nh["tests"]:
            bits.append(f"tests: {len(nh['tests'])}")
        if bits:
            L.append("   - Evidence — " + "; ".join(bits))
        if s.get("normalization_warnings"):
            L.append(f"   - ⚠ {len(s['normalization_warnings'])} normalization warning(s)")
        L.append("")
    return "\n".join(L) + "\n"


def _report_md(result: Result, out_dir: str, strict: bool,
               strict_pass: bool) -> str:
    c = result.counts
    dp = result.document_plan
    sym_total = sum(len(s["retrieval_needs"]["symbols"]) for s in result.sections)
    file_total = sum(len(s["retrieval_needs"]["files"]) for s in result.sections)
    qp_total = sum(len(s["retrieval_needs"]["query_packs"]) for s in result.sections)
    sym_ok = sum(1 for s in result.sections for x in s["retrieval_needs"]["symbols"]
                 if x["resolution"] in ("exact", "unique_alias"))
    file_ok = sum(1 for s in result.sections for x in s["retrieval_needs"]["files"]
                  if x["resolution"] in ("file_exists", "unique_suffix", "digest_artifact"))
    hint_total = sum(len(s["retrieval_needs"].get("search_hints", []))
                     for s in result.sections)
    ca_total = sum(len(s["retrieval_needs"].get("context_artifacts", []))
                   for s in result.sections)
    L = ["# Normalization report", "",
         f"- Raw response: `{dp['source_raw_response']}`",
         f"- Output directory: `{out_dir}`",
         f"- Provider: {dp.get('provider') or 'n/a'}",
         f"- Sections: **{c['sections']}**",
         "",
         "## Reference resolution", "",
         f"- Query packs resolved: **{qp_total}** (to canonical keys)",
         f"- Symbols resolved: **{sym_ok}/{sym_total}**",
         f"- Files resolved: **{file_ok}/{file_total}**",
         f"- Search hints (recall, non-exact): **{hint_total}**",
         f"- Context artifacts (non-citeable): **{ca_total}**",
         f"- Unresolved (all types): **{c['unresolved_total']}**",
         ""]
    if c["unresolved_by_type"]:
        L.append("Unresolved by type:")
        L.append("")
        for t in sorted(c["unresolved_by_type"]):
            L.append(f"- {t}: {c['unresolved_by_type'][t]}")
        L.append("")
    L += ["## Warnings", ""]
    if result.warnings:
        L += [f"- {w}" for w in result.warnings]
    else:
        L.append("_none_")
    L.append("")
    mode = "strict" if strict else "lenient (allow-unresolved)"
    verdict = "PASS ✅" if strict_pass else "FAIL ⚠️"
    L += [f"## Mode: {mode}", "",
          f"Result: **{verdict}**"
          + ("" if strict_pass else
             f" — {c['unresolved_total']} unresolved reference(s) under --strict."),
          "",
          "## Outputs", "",
          f"- `{DOCUMENT_PLAN_JSON}` — normalized DocumentPlan",
          f"- `{DOCUMENT_PLAN_MD}` — human-readable plan",
          f"- `{SECTION_PLANS_JSONL}` — one normalized SectionPlan per line",
          f"- `{READINESS_REPORT_MD}` — Phase 3 readiness gate (PASS/FAIL)",
          f"- `{UNRESOLVED_JSONL}` — unresolved references for review",
          f"- `{RAW_DOC_JSON}`, `{RAW_SECTIONS_JSONL}` — raw extracted (debug)",
          "",
          "## Notes for Phase 3 retrieval", "",
          "- Resolved `symbol_id`s and verified file paths are safe to retrieve "
          "directly against `symbols/` and the raw indexes.",
          "- File anchors with confidence `file_only` are planning hints (often a "
          "heading, not a line range) — locate them lexically, do not treat as "
          "exact spans.",
          "- Unresolved references must be resolved (or dropped) before retrieval; "
          "they are listed in `unresolved-references.jsonl`.",
          ""]
    return "\n".join(L) + "\n"


def write_all(out_dir: str, result: Result, *, strict: bool,
              strict_pass: bool) -> dict:
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)

    def at(name: str) -> str:
        return os.path.join(out_dir, name)

    write_json(at(DOCUMENT_PLAN_JSON), result.document_plan)
    write_text(at(DOCUMENT_PLAN_MD), _document_plan_md(result))
    write_jsonl(at(SECTION_PLANS_JSONL), result.sections)
    write_jsonl(at(UNRESOLVED_JSONL), result.unresolved)
    write_text(at(REPORT_MD), _report_md(result, out_dir, strict, strict_pass))
    write_text(at(READINESS_REPORT_MD), _readiness_report_md(result))
    write_json(at(RAW_DOC_JSON), result.raw_document_plan)
    write_jsonl(at(RAW_SECTIONS_JSONL), result.raw_section_plans)

    return {
        "out_dir": out_dir,
        "files": [DOCUMENT_PLAN_JSON, DOCUMENT_PLAN_MD, SECTION_PLANS_JSONL,
                  REPORT_MD, READINESS_REPORT_MD, UNRESOLVED_JSONL,
                  RAW_DOC_JSON, RAW_SECTIONS_JSONL],
        "readiness_pass": readiness_pass(result),
    }
