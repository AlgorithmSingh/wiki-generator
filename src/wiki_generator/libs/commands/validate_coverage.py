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

    rc = gate.exit_code
    # Expanded-family modes additionally prove catalog→plan→source→evidence→output
    # traceability + artifact freshness over the produced downstream artifacts
    # (``deepwiki-scale`` is a strict superset of ``expanded``).
    if coverage.is_expanded_family(mode):
        trace_rc = _run_traceability(bundle_root, out_dir)
        if trace_rc != 0 and rc == 0:
            rc = trace_rc
    return rc


def _run_traceability(bundle_root: str, out_dir: str) -> int:
    """Build + gate the coverage traceability over the bundle's expanded artifacts.

    Writes ``coverage/coverage-traceability.json`` + ``coverage-traceability-report.md``.
    Returns ``0`` on a fresh, fully-traced PASS; ``2`` when a required upstream
    artifact is absent; ``3`` when a stale fingerprint or broken lineage fails closed.
    Read-only — it never edits an upstream artifact."""
    try:
        report, gate = coverage.build_and_gate_from_bundle(bundle_root)
    except FileNotFoundError as e:
        log(f"  traceability: {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT
    write_json(os.path.join(out_dir, "coverage-traceability.json"), report.to_dict())
    write_text(os.path.join(out_dir, "coverage-traceability-report.md"),
               coverage.render_traceability_markdown(report))
    for line in gate.summary_lines():
        log(f"  {line}")
    log(f"  traceability report: "
        f"{os.path.join(out_dir, 'coverage-traceability-report.md')}")
    return gate.exit_code
