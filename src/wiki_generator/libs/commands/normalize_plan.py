"""Phase 2 Step 2 command: deterministically normalize a planning response.

Reads the raw Gemini/Kimi planning response and the Phase 1 indexes, then writes
machine-resolvable plan artifacts for Phase 3. No LLM calls.

    python -m wiki_generator normalize-plan \\
        --bundle <bundle> --raw-response <bundle>/plans/phase2-gemini-response.md \\
        [--out <dir>] [--strict] [--provider gemini] [--coverage-mode enhancement]

``--coverage-mode`` (default ``baseline``) is the Phase 2 → Phase 3 planned
coverage boundary. ``baseline`` keeps the historical behaviour: the normalization report
carries a non-enforcing DeepWiki coverage matrix but coverage never gates the
command (safe for compact/legacy plans). ``enhancement`` adds a *deterministic*
gate: after the normalized plan is written, planned coverage is checked against all
thirteen mandatory DeepWiki topic families, a ``coverage-gate-report.md`` is written, and a
plan missing any mandatory family fails loudly (exit 3) before Phase 3 retrieval.
The gate never edits, synthesizes, or heals the plan — it only reports and fails.
"""
from __future__ import annotations

import argparse
import os

from .. import coverage
from .. import plan_normalization
from ..util import log, write_json, write_text


def _run_enhancement_gate(out_dir: str) -> int:
    """Deterministic Phase 2 → Phase 3 planned coverage gate over the just-written plan.

    Loads the normalized plan from ``out_dir`` (the exact artifacts Phase 3 reads),
    checks it against the mandatory DeepWiki topic-family taxonomy, writes the gate
    report, logs actionable diagnostics, and returns ``0`` on PASS or
    ``COVERAGE_GATE_FAIL_EXIT`` (3) on a missing mandatory family. It does not add
    or repair anything; upstream prevention is by loud failure, not auto-heal."""
    try:
        document_plan, sections = coverage.load_plan_from_dir(out_dir)
    except FileNotFoundError as e:
        # The normalizer just wrote these; their absence is a real failure.
        log(f"  planned coverage gate: cannot read normalized plan — {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    gate = coverage.gate_plan_coverage(document_plan, sections,
                                       mode=coverage.MODE_ENHANCEMENT)
    write_json(os.path.join(out_dir, "coverage-gate.json"), gate.to_dict())
    write_text(os.path.join(out_dir, "coverage-gate-report.md"),
               coverage.render_markdown(
                   gate.report, title="Phase 2 Planned Coverage Gate (enhancement mode)"))
    for line in gate.summary_lines():
        log(f"  {line}")
    log("  planned coverage gate report: "
        f"{os.path.join(out_dir, 'coverage-gate-report.md')}")
    return gate.exit_code


def run(args: argparse.Namespace) -> int:
    bundle_dir = os.path.abspath(os.path.expanduser(args.bundle))
    raw_path = os.path.abspath(os.path.expanduser(args.raw_response))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_dir, "plans"))

    if not os.path.isdir(bundle_dir):
        log(f"normalize-plan: not a bundle directory: {bundle_dir}")
        return 2
    if not os.path.isfile(raw_path):
        log(f"normalize-plan: raw response not found: {raw_path}")
        return 2

    log(f"normalize-plan: {raw_path}")
    try:
        report = plan_normalization.run(
            bundle_dir, raw_path, out_dir,
            strict=getattr(args, "strict", False),
            allow_unresolved=not getattr(args, "strict", False),
            provider=getattr(args, "provider", None),
        )
    except plan_normalization.ParseError as e:
        log(f"normalize-plan: cannot parse raw response — {e}")
        return 2

    log(f"  wrote plan artifacts: {report['out_dir']}")
    for f in report["files"]:
        log(f"    - {f}")
    log(f"  sections: {report['sections']}")
    by_type = report["unresolved_by_type"]
    detail = (" (" + ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items())) + ")"
              if by_type else "")
    log(f"  unresolved references: {report['unresolved_total']}{detail}")
    readiness = "PASS" if report.get("readiness_pass") else "FAIL"
    log(f"  Phase 3 readiness: {readiness} (see phase3-readiness-report.md)")
    if readiness == "FAIL":
        log("  note: readiness FAIL — fix upstream planner/normalization before "
            "Phase 3 (or run Phase 3 only to test failure behavior)")

    rc = 0
    if report["strict"] and not report["strict_pass"]:
        log(f"normalize-plan: STRICT FAIL — {report['unresolved_total']} "
            "unresolved reference(s); see unresolved-references.jsonl")
        rc = 1
    else:
        log("normalize-plan: done")

    # Phase 2 → Phase 3 planned coverage boundary. Baseline (default) stays non-breaking;
    # enhancement runs the deterministic planned coverage gate and fails loudly on a missing family.
    coverage_mode = getattr(args, "coverage_mode", coverage.MODE_BASELINE)
    if coverage_mode == coverage.MODE_ENHANCEMENT:
        gate_rc = _run_enhancement_gate(out_dir)
        # A strict-normalization failure is more fundamental than coverage; report
        # both but let strict (rc=1) take precedence over the coverage code (3).
        if gate_rc != 0 and rc == 0:
            rc = gate_rc
    return rc
