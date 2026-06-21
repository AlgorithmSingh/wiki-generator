"""Step 3 command: write derived/planning-digest.md (and ensure condensates).

Ensures the Step 2 condensates exist (regenerating them so the digest is always
self-consistent) and writes the top-level ``derived/planning-digest.md`` brief.
For convenience it then runs Step 4 (``bundle``) so a single ``digest`` call also
produces the upload-ready ``planner-digest/`` package; pass ``--no-bundle`` to
stop after the digest.
"""
from __future__ import annotations

import argparse
import os

from . import bundle as bundle_cmd
from . import condense as condense_cmd
from ..digest import loader, planning_digest
from ..util import log, token_estimate, write_text


def run(args: argparse.Namespace) -> int:
    in_dir = os.path.abspath(os.path.expanduser(args.in_dir))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(in_dir, "planner-digest"))
    budget = getattr(args, "budget_tokens", 0)

    bundle = loader.load_bundle(in_dir)
    derived_dir = os.path.join(in_dir, "derived")

    # Step 2: (re)generate condensates so the digest is consistent with them.
    log(f"digest: ensuring condensates for {in_dir}")
    condense_cmd.write_condensates(bundle, derived_dir)

    # Step 3: the top-level brief.
    digest_text = planning_digest.build(bundle)
    digest_path = os.path.join(derived_dir, "planning-digest.md")
    write_text(digest_path, digest_text)
    log(f"  wrote derived/planning-digest.md  (~{token_estimate(digest_text):,} tokens)")

    if getattr(args, "no_bundle", False):
        return 0

    # Step 4 (compatibility): also assemble the upload package.
    report = bundle_cmd.assemble_package(in_dir, out_dir, budget)
    log(f"  wrote upload package: {report['out_dir']}")
    for f in report["files"]:
        log(f"    - {f}")
    if report["trimmed"]:
        log(f"  trimmed to fit budget: {', '.join(report['trimmed'])}")
    log(f"  single-file upload: {os.path.join(report['out_dir'], report['bundle'])} "
        f"(~{report['bundle_tokens']:,} tokens)")
    if report["failed"]:
        log(f"digest: bundle FAIL — required files exceed budget "
            f"({report['required_tokens']:,} > {budget:,} tokens); see upload-list.md")
        return 1
    status = "within budget ✅" if report["within_budget"] else "OVER BUDGET ⚠️"
    log(f"upload total ~{report['total_tokens']:,} tokens "
        f"(budget {budget:,}: {status})")
    return 0
