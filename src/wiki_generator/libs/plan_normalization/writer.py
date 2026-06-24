"""Write the normalized Phase 2 plan artifacts.

Produces the canonical outputs Phase 3 consumes plus a human-readable plan, a
normalization report, the unresolved-reference log, and raw-extracted debug
copies. All writes are deterministic.
"""
from __future__ import annotations

import os

from ..context_docs import (
    is_diagnostic_artifact, is_provenance_section, section_has_retrieval_signal,
)
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
    # Patch 2: a malformed required SectionPlan JSONL row.
    "section_plan_jsonl_parse_error":
        "fix the malformed SectionPlan JSONL row (one valid JSON object per line; "
        "prose belongs in verification_needs[]/known_gaps[]), or run the bounded "
        "Phase 2 planner-artifact repair (plan-repair)",
    # Patch 3: a normal section backed only by internal planning diagnostics.
    "diagnostic_only_user_section":
        "remove this section, convert it to a controlled provenance/meta section "
        "(role: provenance), or add real retrieval signals (source files, symbols, "
        "tests, contracts, graph nodes, query packs, or precise search hints)",
    # Patch 1: a directory-like path that leaked into the active exact files lane.
    "directory_like_in_exact_lane":
        "a directory / trailing-slash path is not a citeable file; use an exact "
        "file (e.g. agent/component/base.py) or route the area to search_hints[]",
}


# Artifact-level failures (no recoverable section_id) bucket under this key.
_ARTIFACT_BUCKET = "(artifact)"


def _diagnostic_paths(section: Result) -> list[str]:
    """Repo-relative paths of the section's *diagnostic* context artifacts."""
    out: list[str] = []
    for ca in section["retrieval_needs"].get("context_artifacts", []):
        path = ca.get("path") if isinstance(ca, dict) else ca
        if path and is_diagnostic_artifact(path):
            out.append(path)
    return out


def _readiness_failures(result: Result) -> dict:
    """Per-section list of readiness failures. A normal section is Phase-3-ready
    only if it has no rejected exact-lane references, no malformed-row parse error,
    and a deterministic retrieval signal.

    NON-failures (correct normalizer actions, not blockers):
    - ``context_only``: the planner-context doc was relocated out of ``files[]``
      into ``context_artifacts[]`` (the spec-mandated fix);
    - ``directory_like_routed`` (``blocking: false``): a broad directory anchor was
      routed to ``search_hints[]`` (Patch 1) — reported as a warning, not a failure;
    - controlled provenance/meta sections (Patch 3): handled outside source lanes.
    """
    by_section: dict[str, list] = {s["section_id"]: [] for s in result.sections}
    section_ids = set(by_section)

    # Patch 2: a malformed required SectionPlan JSONL row is the PRIMARY failure for
    # its section (attached by recovered section_id when it maps to the plan, else
    # reported at artifact level). It must never be hidden behind a synthesized
    # empty section that only reports no_retrieval_signal.
    for d in result.parse_diagnostics:
        if d.get("severity") != "failure":
            continue
        rec = {
            "field": d.get("artifact", "section-plans.jsonl"),
            "input": f"line {d.get('line')}",
            "reason": d.get("code", "section_plan_jsonl_parse_error"),
            "fix": _FIX["section_plan_jsonl_parse_error"],
        }
        sid = d.get("section_id")
        by_section.setdefault(sid if sid in section_ids else _ARTIFACT_BUCKET,
                              []).append(rec)

    for u in result.unresolved:
        if u.get("reason") == "context_only" or not u.get("blocking", True):
            continue  # relocated/routed correctly — not a blocker
        sid = u.get("section_id")
        by_section.setdefault(sid, []).append({
            "field": _LANE_FIELD.get(u.get("type"), u.get("type")),
            "input": u.get("input"),
            "reason": u.get("reason"),
            "fix": _FIX.get(u.get("reason"),
                            "use an exact handle, or move it to search_hints[]"),
        })

    # Patch 1 (defense-in-depth): the readiness gate independently FAILs if any
    # directory-like path leaked into an active exact files lane — it does not rely
    # solely on the normalizer having routed it out.
    for s in result.sections:
        for f in s["retrieval_needs"].get("files", []):
            path = (f.get("path") or f.get("input")) if isinstance(f, dict) else f
            if isinstance(path, str) and path.rstrip().endswith("/"):
                by_section.setdefault(s["section_id"], []).append({
                    "field": "retrieval_needs.files", "input": path,
                    "reason": "directory_like_in_exact_lane",
                    "fix": _FIX["directory_like_in_exact_lane"]})

    for s in result.sections:
        # Patch 3: a controlled provenance/meta section is non-source — it does not
        # require source-evidence retrieval signals and is reported separately.
        if is_provenance_section(s):
            continue
        # A deterministic retrieval directive: an exact handle, a canonical query
        # pack, or a search hint. Bare title/topic text is not sufficient.
        if section_has_retrieval_signal(s):
            continue
        diag = _diagnostic_paths(s)
        if diag:
            # Patch 3: a normal section backed ONLY by internal planning diagnostics
            # is a diagnostic_only_user_section (primary), not merely no-signal.
            by_section.setdefault(s["section_id"], []).append({
                "field": "retrieval_needs", "input": ", ".join(diag),
                "reason": "diagnostic_only_user_section",
                "fix": _FIX["diagnostic_only_user_section"],
                "secondary": "no_retrieval_signal",
            })
        else:
            by_section.setdefault(s["section_id"], []).append({
                "field": "retrieval_needs", "input": "(none)",
                "reason": "no_retrieval_signal", "fix": _FIX["no_retrieval_signal"],
            })
    return by_section


def readiness_pass(result: Result) -> bool:
    return not any(_readiness_failures(result).values())


def _readiness_report_md(result: Result) -> str:
    dp = result.document_plan
    sections = result.sections
    failures = _readiness_failures(result)
    status = "PASS" if readiness_pass(result) else "FAIL"

    # Patch 1: broad directory anchors routed to search_hints[] (warnings).
    dir_routed = [u for u in result.unresolved
                  if u.get("reason") == "directory_like_routed"]
    # Patch 2: malformed-row diagnostics (blocking failures + deterministic repairs).
    parse_fail = [d for d in result.parse_diagnostics
                  if d.get("severity") == "failure"]
    parse_repair = [d for d in result.parse_diagnostics
                    if d.get("severity") == "warning"]
    # Patch 3: controlled provenance/meta sections (non-source).
    provenance = [s for s in sections if is_provenance_section(s)]

    n_fail = sum(len(v) for v in failures.values())
    n_warn = len(dir_routed) + len(parse_repair)

    L = ["# Phase 3 Readiness Report", "",
         f"Status: {status}",
         f"Failures: {n_fail}",
         f"Warnings: {n_warn}",
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
        # A rejection counts only when it is a genuine, blocking exact-lane failure
        # — not a context_only relocation or a routed directory anchor (Patch 1).
        rejected = sum(1 for u in result.unresolved if u.get("type") == utype
                       and u.get("reason") != "context_only"
                       and u.get("blocking", True))
        L.append(f"- {label}: {resolved} resolved, {rejected} rejected")
    L.append("")

    # --- Patch 2: malformed planner artifacts --------------------------------
    L += ["## Malformed planner artifacts", ""]
    if parse_fail or parse_repair:
        L.append(f"- Parse failures (blocking): {len(parse_fail)}")
        L.append(f"- Deterministic repairs (warning): {len(parse_repair)}")
        for d in parse_fail:
            L.append(f"  - FAIL `{d.get('artifact')}` line {d.get('line')} "
                     f"section_id=`{d.get('section_id') or '?'}` "
                     f"({d.get('code')}): {d.get('parse_error', '')}")
        for d in parse_repair:
            L.append(f"  - repaired `{d.get('artifact')}` line {d.get('line')} "
                     f"section_id=`{d.get('section_id') or '?'}`: "
                     f"{d.get('repair', '')}")
    else:
        L.append("_none_")
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

    # --- Patch 1: broad directory refs routed to search_hints[] (warnings) ----
    L += ["## Warnings", "",
          "### Broad directory refs routed to search_hints[]", "",
          f"- Broad directory refs routed to search_hints[]: {len(dir_routed)}"]
    for u in dir_routed:
        L.append(f"  - `{u.get('section_id')}` "
                 f"source_field: {u.get('source_field', 'file_anchors[]')} "
                 f"input: `{u.get('input')}` → {u.get('normalized_to')} "
                 "(non-blocking; directory-like path is recall text, not a "
                 "citeable file)")
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

    # --- Patch 3: controlled provenance / meta sections (non-source) ----------
    L += ["## Controlled provenance / meta sections", ""]
    if provenance:
        for s in provenance:
            diag = _diagnostic_paths(s)
            L.append(f"- `{s['section_id']}` (role: provenance, non-source)"
                     + (f"; diagnostics: {', '.join(diag)}" if diag else ""))
    else:
        L.append("_none_")
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
        if s["section_id"] not in dp["section_order"]] + [_ARTIFACT_BUCKET]
    any_fail = False
    for sid in ordered:
        for f in failures.get(sid, []):
            any_fail = True
            secondary = (f" (secondary: {f['secondary']})"
                         if f.get("secondary") else "")
            L.append(f"- `{sid}` — {f['field']}: invalid input {f['input']!r} "
                     f"({f['reason']}){secondary}; fix: {f['fix']}")
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
        parent_disp = s.get("parent_section_id") or s.get("parent")
        suffix = f"  _(under `{parent_disp}`)_" if parent_disp else ""
        L.append(f"{prefix}**{s['title']}** — `{sid}`{suffix}")
        if s.get("purpose"):
            L.append(f"   - Purpose: {s['purpose']}")
        if s.get("coverage_labels"):
            L.append("   - Coverage labels: "
                     + ", ".join(f"`{c}`" for c in s["coverage_labels"]))
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


def _coverage_summary_md(result: Result) -> list[str]:
    """A non-enforcing DeepWiki coverage matrix for the normalization report.

    Milestone 2: evaluated in **baseline (report-only)** mode so it never gates
    ``normalize-plan`` or changes readiness — it only surfaces which mandatory
    topic families the plan already covers and which to add for coverage-enhanced
    mode. The enforcing gate is the explicit ``validate-coverage --mode
    enhancement`` command. The reference DeepWiki export is a coverage/structure
    benchmark only, never citeable evidence."""
    # Local import keeps the planning writer decoupled from the coverage package
    # at module load and avoids any import cycle.
    from .. import coverage as _coverage

    report = _coverage.evaluate_plan_coverage(
        result.document_plan, result.sections, mode=_coverage.MODE_BASELINE)
    missing = ", ".join(f"`{k}`" for k in report.missing_mandatory) or "_none_"
    return [
        "## DeepWiki coverage (benchmark, non-enforcing)", "",
        f"- Mandatory topic families planned: "
        f"**{report.covered_count}/{report.family_count}** "
        "(baseline / report-only — does not gate normalize-plan)",
        f"- Plan for coverage-enhanced mode: {missing}",
        "",
        "> Reference DeepWiki export is a coverage/structure benchmark only, never "
        "citeable evidence; line count is a warning signal, not the objective. Run "
        "`validate-coverage --mode enhancement` to enforce the coverage gate.",
        "",
    ]


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
    L += _coverage_summary_md(result)
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
