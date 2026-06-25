"""Phase 2 Step 2 command: deterministically normalize a planning response.

Reads the raw Gemini/Kimi planning response and the Phase 1 indexes, then writes
machine-resolvable plan artifacts for Phase 3. No LLM calls.

    python -m wiki_generator normalize-plan \\
        --bundle <bundle> --raw-response <bundle>/plans/phase2-gemini-response.md \\
        [--out <dir>] [--strict] [--provider gemini] [--coverage-mode enhancement]

``--coverage-mode`` (default ``baseline``) is the Phase 2 → Phase 3 boundary.
``baseline`` keeps the historical behaviour: the normalization report carries a
non-enforcing DeepWiki coverage matrix but coverage never gates the command (safe
for compact/legacy plans). ``enhancement`` adds two *deterministic* gates over the
just-written normalized plan, before Phase 3 retrieval:

- **Planned coverage** — the plan must name all thirteen mandatory DeepWiki topic
  families (``coverage-gate.json`` / ``coverage-gate-report.md``).
- **Topic-obligation completeness** — every normalized required topic in a normal
  source-evidence section must carry a complete, exact, citeable
  ``topic_evidence_requirements[]`` obligation (``topic-obligations-gate.json`` /
  ``topic-obligations-report.md``). This prevents the live-run failure where
  required topics merged from ``coverage_requirements[]`` reached Phase 3 with no
  matching topic-evidence row (or only broad recall) and failed closed after
  retrieval.

Either failure exits 3 before Phase 3. Neither gate edits, synthesizes, or heals
the plan — they only report and fail.
"""
from __future__ import annotations

import argparse
import os

from .. import coverage
from .. import plan_normalization
from ..util import log, write_json, write_text


def _run_enhancement_gate(out_dir: str) -> int:
    """Deterministic Phase 2 → Phase 3 enhancement gates over the just-written plan.

    Loads the normalized plan from ``out_dir`` (the exact artifacts Phase 3 reads)
    and runs two complementary deterministic gates before Phase 3 retrieval:

    1. **Planned coverage** — does the plan name every mandatory DeepWiki topic
       family? Writes ``coverage-gate.json`` + ``coverage-gate-report.md``.
    2. **Topic-obligation completeness** — does every normalized required topic in a
       normal source-evidence section carry a complete, exact, citeable
       ``topic_evidence_requirements[]`` obligation (so it could become sufficient
       evidence in Phase 3)? Writes ``topic-obligations-gate.json`` +
       ``topic-obligations-report.md``. This catches the live-run failure pattern —
       required topics merged from ``coverage_requirements[]`` with no matching
       topic-evidence row, or topics grounded only on broad recall — at the Phase 2
       boundary instead of after Phase 3 retrieves and fails closed.

    Returns ``0`` only when BOTH gates pass; ``COVERAGE_GATE_FAIL_EXIT`` (3) when
    either fails (a planned-coverage miss, or an underspecified required-topic
    obligation). Neither gate adds or repairs anything — upstream prevention is by
    loud failure, not auto-heal."""
    try:
        document_plan, sections = coverage.load_plan_from_dir(out_dir)
    except FileNotFoundError as e:
        # The normalizer just wrote these; their absence is a real failure.
        log(f"  enhancement gate: cannot read normalized plan — {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    # 1) planned coverage gate (mandatory topic families).
    cov_gate = coverage.gate_plan_coverage(document_plan, sections,
                                           mode=coverage.MODE_ENHANCEMENT)
    write_json(os.path.join(out_dir, "coverage-gate.json"), cov_gate.to_dict())
    write_text(os.path.join(out_dir, "coverage-gate-report.md"),
               coverage.render_markdown(
                   cov_gate.report,
                   title="Phase 2 Planned Coverage Gate (enhancement mode)"))
    for line in cov_gate.summary_lines():
        log(f"  {line}")
    log("  planned coverage gate report: "
        f"{os.path.join(out_dir, 'coverage-gate-report.md')}")

    # 2) topic-obligation completeness gate (exact citeable obligation per topic).
    ob_gate = coverage.gate_topic_obligations(document_plan, sections,
                                              mode=coverage.MODE_ENHANCEMENT)
    write_json(os.path.join(out_dir, "topic-obligations-gate.json"),
               ob_gate.to_dict())
    write_text(os.path.join(out_dir, "topic-obligations-report.md"),
               coverage.render_obligations_markdown(
                   ob_gate.report,
                   title="Phase 2 Topic-Obligation Gate (enhancement mode)"))
    for line in ob_gate.summary_lines():
        log(f"  {line}")
    log("  topic-obligation gate report: "
        f"{os.path.join(out_dir, 'topic-obligations-report.md')}")

    # Both must pass to reach Phase 3. Either failure is exit 3 before retrieval.
    return (cov_gate.exit_code if not cov_gate.passed
            else ob_gate.exit_code)


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
