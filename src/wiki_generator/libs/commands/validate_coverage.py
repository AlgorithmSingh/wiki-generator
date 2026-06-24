"""validate-coverage command (Milestone 2 coverage-validation scaffold).

Deterministic, LLM-free, read-only. Loads a bundle's normalized Phase 2 plan,
checks it against the mandatory DeepWiki topic-family taxonomy, writes a coverage
report (JSON + Markdown), and maps the verdict to an exit code:

    0 = coverage PASS (all mandatory families planned, or baseline/report-only mode)
    2 = bad/missing input artifact (no normalized plan to check)
    3 = planned coverage gate FAIL (enhancement mode: a mandatory topic family is missing)

It never calls a model, never runs Phase 1/2/3/4, and never edits plan or wiki
artifacts — it only writes its own report under ``<bundle>/coverage`` (or ``--out``).
"""
from __future__ import annotations

import argparse
import os

from .. import coverage
from ..util import log, write_json, write_text


def run(args: argparse.Namespace) -> int:
    bundle_root = os.path.abspath(os.path.expanduser(args.bundle))
    if not os.path.isdir(bundle_root):
        log(f"validate-coverage: not a bundle directory: {bundle_root}")
        return 2

    mode = getattr(args, "mode", coverage.MODE_ENHANCEMENT)
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_root, "coverage"))

    try:
        document_plan, sections = coverage.load_plan_for_coverage(bundle_root)
    except FileNotFoundError as e:
        log(f"validate-coverage: {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    try:
        gate = coverage.gate_plan_coverage(document_plan, sections, mode=mode)
    except ValueError as e:
        log(f"validate-coverage: invalid request — {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    report = gate.report
    json_path = os.path.join(out_dir, "coverage-validation.json")
    md_path = os.path.join(out_dir, "coverage-validation-report.md")
    write_json(json_path, report.to_dict())
    write_text(md_path, coverage.render_markdown(report))

    log(f"validate-coverage: {bundle_root}")
    for line in gate.summary_lines():
        log(f"  {line}")
    log(f"  report: {md_path}")

    if gate.passed:
        log("validate-coverage: PASS")
    else:
        log(f"validate-coverage: FAIL — {len(report.missing_mandatory)} mandatory "
            "topic family(ies) not planned (see coverage-validation-report.md)")
    return gate.exit_code
