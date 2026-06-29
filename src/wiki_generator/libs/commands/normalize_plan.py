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


def _run_coverage_gates(bundle_dir: str, out_dir: str, mode: str) -> int:
    """Deterministic Phase 2 → Phase 3 coverage gates over the just-written plan.

    Loads the normalized plan from ``out_dir`` (the exact artifacts Phase 3 reads)
    and runs the deterministic gates for ``mode`` before Phase 3 retrieval. Both the
    ``enhancement`` and ``expanded`` modes run:

    1. **Planned coverage** — does the plan name every mandatory DeepWiki topic
       family? Writes ``coverage-gate.json`` + ``coverage-gate-report.md``.
    2. **Topic-obligation completeness** — does every normalized required topic in a
       normal source-evidence section carry a complete, exact, citeable
       ``topic_evidence_requirements[]`` obligation (so it could become sufficient
       evidence in Phase 3)? Writes ``topic-obligations-gate.json`` +
       ``topic-obligations-report.md``. This catches the live-run failure patterns —
       required topics merged from ``coverage_requirements[]`` with no matching
       topic-evidence row, topics grounded only on broad recall, a TER source field
       whose lane is not in ``acceptable_lanes[]``, or an exact file/test source
       field that resolves in inventory but has no citeable chunk coverage — at the
       Phase 2 boundary instead of after Phase 3 retrieves and fails closed.

    The ``expanded`` (DeepWiki-style hierarchical) mode additionally runs:

    3. **Hierarchical page planning** — resolved acyclic parent/child links, a valid
       page profile and its required content blocks per page, and every high-signal
       catalog topic planned or explicitly deferred. Writes ``page-planning-gate.json``
       + ``page-planning-report.md``. It reads the Phase A ``derived/topic-catalog.json``;
       an absent catalog in expanded mode is a hard missing-input failure (exit 2).

    The citeable-source-availability part of gate 2 reads the bundle's
    ``rag/chunks.jsonl`` corpus (the same chunk substrate Phase 3 cites) into a
    read-only :class:`~coverage.CiteableSubstrate` view. When that corpus is absent,
    the citeability check is skipped (report-only) and only the plan-only shape +
    lane/type checks run; the gate logs which mode it used.

    Returns ``0`` only when ALL applicable gates pass; the first failing gate's exit
    code otherwise. No gate adds or repairs anything — upstream prevention is by loud
    failure, not auto-heal."""
    try:
        document_plan, sections = coverage.load_plan_from_dir(out_dir)
    except FileNotFoundError as e:
        # The normalizer just wrote these; their absence is a real failure.
        log(f"  coverage gate: cannot read normalized plan — {e}")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    label = f"{mode} mode"

    # 1) planned coverage gate (mandatory topic families).
    cov_gate = coverage.gate_plan_coverage(document_plan, sections, mode=mode)
    write_json(os.path.join(out_dir, "coverage-gate.json"), cov_gate.to_dict())
    write_text(os.path.join(out_dir, "coverage-gate-report.md"),
               coverage.render_markdown(
                   cov_gate.report, title=f"Phase 2 Planned Coverage Gate ({label})"))
    for line in cov_gate.summary_lines():
        log(f"  {line}")
    log("  planned coverage gate report: "
        f"{os.path.join(out_dir, 'coverage-gate-report.md')}")

    # 2) topic-obligation completeness gate (exact, lane-acceptable, citeable
    # obligation per topic). The citeable-substrate view is read from the bundle's
    # rag corpus; absent corpus -> citeability check skipped (report-only).
    substrate = coverage.load_citeable_substrate(bundle_dir)
    if substrate is None:
        log("  topic-obligation gate: no rag/chunks.jsonl corpus — citeable-source "
            "viability NOT checked (lane/type + shape checks only)")
    ob_gate = coverage.gate_topic_obligations(document_plan, sections, mode=mode,
                                              substrate=substrate)
    write_json(os.path.join(out_dir, "topic-obligations-gate.json"),
               ob_gate.to_dict())
    write_text(os.path.join(out_dir, "topic-obligations-report.md"),
               coverage.render_obligations_markdown(
                   ob_gate.report, title=f"Phase 2 Topic-Obligation Gate ({label})"))
    for line in ob_gate.summary_lines():
        log(f"  {line}")
    log("  topic-obligation gate report: "
        f"{os.path.join(out_dir, 'topic-obligations-report.md')}")

    if not cov_gate.passed:
        return cov_gate.exit_code
    if not ob_gate.passed:
        return ob_gate.exit_code

    # 3) expanded gate set (hierarchical page planning + relevant-source map). Run for
    # ``expanded`` and its strict superset ``deepwiki-scale``; the latter additionally
    # runs the anti-compression breadth gate (see _run_expanded_gates).
    if coverage.is_expanded_family(mode):
        return _run_expanded_gates(bundle_dir, out_dir, document_plan, sections, mode)
    return 0


def _run_expanded_gates(bundle_dir: str, out_dir: str, document_plan: dict,
                        sections: list, mode: str) -> int:
    """The expanded-family Phase 2 gates: hierarchical page planning and the
    deterministic relevant-source map (``expanded`` and ``deepwiki-scale``), plus the
    anti-compression breadth gate for ``deepwiki-scale`` only. Reads the Phase A topic
    catalog; an absent catalog is a hard missing-input failure (exit 2). Returns ``0``
    when all applicable gates pass, else the first failing gate's exit code. Never edits
    the plan."""
    catalog = coverage.load_topic_catalog(bundle_dir)
    if catalog is None:
        log(f"  page-planning gate: {mode} mode requires "
            "derived/topic-catalog.json (Phase A); it is absent — run condense/"
            "digest first. FAIL (missing input).")
        return coverage.COVERAGE_GATE_INPUT_EXIT

    pp_gate = coverage.gate_page_planning(catalog, document_plan, sections, mode=mode)
    write_json(os.path.join(out_dir, "page-planning-gate.json"), pp_gate.to_dict())
    write_text(os.path.join(out_dir, "page-planning-report.md"),
               coverage.render_page_planning_markdown(
                   pp_gate.report,
                   title=f"Phase 2 Hierarchical Page-Planning Gate ({mode} mode)"))
    for line in pp_gate.summary_lines():
        log(f"  {line}")
    log("  page-planning gate report: "
        f"{os.path.join(out_dir, 'page-planning-report.md')}")
    if not pp_gate.passed:
        return pp_gate.exit_code

    # Phase C: deterministic relevant-source map + source-selection gate.
    sm_rc = _run_source_map_gate(bundle_dir, out_dir, catalog, document_plan, sections,
                                 mode)
    if sm_rc != 0:
        return sm_rc

    # deepwiki-scale only: the anti-compression breadth gate (distributive promotion
    # contract — each promoted leaf catalog topic earns its own leaf page + TER, large
    # families fan out, the plan is not flat, leaf-page count meets the catalog floor).
    if coverage.enforces_breadth(mode):
        return _run_anti_compression_gate(out_dir, catalog, document_plan, sections,
                                          mode)
    return 0


def _run_anti_compression_gate(out_dir: str, catalog: dict, document_plan: dict,
                               sections: list, mode: str) -> int:
    """The ``deepwiki-scale`` anti-compression breadth gate. Deterministic, read-only:
    closes the loophole where a high-signal catalog collapses into too few flat pages.
    Writes ``anti-compression-gate.json`` + ``anti-compression-report.md`` and returns
    ``0`` on pass / ``3`` on a compressed plan. Never edits the plan."""
    ac_gate = coverage.gate_anti_compression(catalog, document_plan, sections,
                                             mode=mode)
    write_json(os.path.join(out_dir, "anti-compression-gate.json"), ac_gate.to_dict())
    write_text(os.path.join(out_dir, "anti-compression-report.md"),
               coverage.render_anti_compression_markdown(
                   ac_gate.report,
                   title=f"Phase 2 Anti-Compression Gate ({mode} mode)"))
    for line in ac_gate.summary_lines():
        log(f"  {line}")
    log("  anti-compression gate report: "
        f"{os.path.join(out_dir, 'anti-compression-report.md')}")
    return ac_gate.exit_code


def _run_source_map_gate(bundle_dir: str, out_dir: str, catalog: dict,
                         document_plan: dict, sections: list, mode: str) -> int:
    """Phase C: build ``plans/relevant-source-map.json`` deterministically and gate it.

    Selects each page's exact citeable source handles from the normalized plan's
    resolved lanes (never benchmark/generated-wiki inputs), fingerprints the catalog
    and plan it consumed, and fails closed (exit 3) when a page-profile floor, a
    blocking required topic, or an evidence-bearing content block has no citeable
    selected handle. The file/test citeability decision uses the bundle's
    ``rag/chunks.jsonl`` substrate when present (else those lanes are undecidable and
    never cause a false failure). Never edits the plan."""
    substrate = coverage.load_citeable_substrate(bundle_dir)
    source_map = coverage.build_relevant_source_map(
        catalog, document_plan, sections, substrate=substrate)
    write_json(os.path.join(out_dir, "relevant-source-map.json"),
               source_map.to_dict())
    sm_gate = coverage.gate_source_map(source_map, sections, mode=mode)
    write_json(os.path.join(out_dir, "source-selection-gate.json"),
               sm_gate.to_dict())
    write_text(os.path.join(out_dir, "relevant-source-map-report.md"),
               coverage.render_source_map_markdown(
                   source_map, sm_gate,
                   title=f"Phase 2 Relevant Source Map ({mode} mode)"))
    for line in sm_gate.summary_lines():
        log(f"  {line}")
    log("  relevant source map: "
        f"{os.path.join(out_dir, 'relevant-source-map.json')}")
    return sm_gate.exit_code


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

    # Phase 2 → Phase 3 coverage boundary. Baseline (default) stays non-breaking;
    # enhancement runs the deterministic planned-coverage + topic-obligation gates;
    # expanded additionally runs the hierarchical page-planning + relevant-source-map
    # gates; deepwiki-scale additionally runs the anti-compression breadth gate (each
    # promoted leaf catalog topic earns its own leaf page + TER; large families fan
    # out; the plan is not flat; leaf-page count meets the catalog floor). Each fails
    # loudly on a missing family/obligation/page/source obligation or a compressed plan.
    coverage_mode = getattr(args, "coverage_mode", coverage.MODE_BASELINE)
    if coverage_mode in (coverage.MODE_ENHANCEMENT, coverage.MODE_EXPANDED,
                         coverage.MODE_DEEPWIKI_SCALE):
        gate_rc = _run_coverage_gates(bundle_dir, out_dir, coverage_mode)
        # A strict-normalization failure is more fundamental than coverage; report
        # both but let strict (rc=1) take precedence over the coverage code (2/3).
        if gate_rc != 0 and rc == 0:
            rc = gate_rc
    return rc
