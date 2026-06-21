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
UNRESOLVED_JSONL = "unresolved-references.jsonl"
RAW_DOC_JSON = "raw-extracted-document-plan.json"
RAW_SECTIONS_JSONL = "raw-extracted-section-plans.jsonl"


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
    write_json(at(RAW_DOC_JSON), result.raw_document_plan)
    write_jsonl(at(RAW_SECTIONS_JSONL), result.raw_section_plans)

    return {
        "out_dir": out_dir,
        "files": [DOCUMENT_PLAN_JSON, DOCUMENT_PLAN_MD, SECTION_PLANS_JSONL,
                  REPORT_MD, UNRESOLVED_JSONL, RAW_DOC_JSON, RAW_SECTIONS_JSONL],
    }
