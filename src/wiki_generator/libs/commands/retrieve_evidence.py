"""retrieve-evidence command wrapper (Phase 3).

Thin: resolve paths + options, dispatch to ``libs.evidence``, map the classified
result to an exit code. Exit codes: 0 = PASS; 2 = bad/missing input artifact;
3 = bad/underspecified normalized plan; 1 = retriever implementation bug.
There is deliberately no ``--section`` option — this is an all-sections producer.
"""
from __future__ import annotations

import argparse
import os

from .. import evidence
from ..util import log


def build_options(args: argparse.Namespace) -> "evidence.EvidenceOptions":
    """Translate parsed CLI args into the retriever's options contract.

    Knobs the user did not pass are omitted so ``EvidenceOptions``' dataclass
    defaults stay the single source of truth, and an explicit out-of-range value
    reaches the dataclass validator rather than being silently coerced.
    """
    bundle_root = os.path.abspath(os.path.expanduser(args.bundle))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_root, "evidence"))
    kwargs = {"bundle_root": bundle_root, "out_dir": out_dir}
    if getattr(args, "max_per_lane", None) is not None:
        kwargs["max_per_lane"] = args.max_per_lane
    if getattr(args, "max_total_per_section", None) is not None:
        kwargs["max_total_per_section"] = args.max_total_per_section
    return evidence.EvidenceOptions(**kwargs)


def run(args: argparse.Namespace) -> int:
    try:
        options = build_options(args)
    except ValueError as e:
        log(f"retrieve-evidence: invalid options — {e}")
        return 2
    if not os.path.isdir(options.bundle_root):
        log(f"retrieve-evidence: not a bundle directory: {options.bundle_root}")
        return 2

    log(f"retrieve-evidence: {options.bundle_root}")
    try:
        result = evidence.run(options)
    except Exception as e:  # unclassified retriever failure -> bug, exit 1
        from ..evidence.schema import CAT_BUG
        from ..evidence.writer import write_failure_stub
        write_failure_stub(options.out_dir, options.bundle_root, CAT_BUG, repr(e))
        log(f"retrieve-evidence: internal error — {e}")
        return 1

    log(f"  retrieval mode: {result.retrieval_mode}")
    counts = result.counts or {}
    if counts:
        log(f"  sections: {counts.get('sections_processed')}/"
            f"{counts.get('sections_expected')}  "
            f"evidence items: {counts.get('evidence_items')}")
    for f in result.files_written:
        log(f"    - {f}")
    for w in result.warnings:
        log(f"  warning: {w}")

    if result.ok:
        log("retrieve-evidence: PASS")
    else:
        log(f"retrieve-evidence: FAIL ({result.failure_category}) — "
            "see retrieval-report.md")
    return result.exit_code
