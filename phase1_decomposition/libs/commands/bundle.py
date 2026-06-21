"""Step 4 command: assemble the single-file planner upload bundle.

Packages the Step 2 condensates + the Step 3 ``planning-digest.md`` into an
upload-ready ``planner-digest/`` folder (README + upload-list + the one
concatenated ``planner-upload-bundle.md``). Deterministic; no LLM calls.

    python -m phase1_decomposition bundle --in <bundle> [--out <dir>] [--budget-tokens N]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os

from ..digest import loader, upload_package
from ..util import log


def assemble_package(in_dir: str, out_dir: str, budget_tokens: int) -> dict:
    """Shared entry used by both `bundle` and `digest`. Returns the report dict."""
    bundle = loader.load_bundle(in_dir)
    generated_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    repo_root = (bundle.coverage or {}).get("repo_root", in_dir)
    return upload_package.assemble(in_dir, out_dir, budget_tokens,
                                   generated_at, repo_root)


def run(args: argparse.Namespace) -> int:
    in_dir = os.path.abspath(os.path.expanduser(args.in_dir))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(in_dir, "planner-digest"))
    budget = getattr(args, "budget_tokens", 0)

    derived = os.path.join(in_dir, "derived")
    if not os.path.isfile(os.path.join(derived, "planning-digest.md")):
        log("bundle: derived/planning-digest.md not found — run `digest` first "
            "(Step 3) so the condensates exist.")

    log(f"bundle: assembling planner upload package for {in_dir}")
    report = assemble_package(in_dir, out_dir, budget)

    log(f"  wrote upload package: {report['out_dir']}")
    for f in report["files"]:
        log(f"    - {f}")
    if report["trimmed"]:
        log(f"  trimmed to fit budget: {', '.join(report['trimmed'])}")
    single = os.path.join(report["out_dir"], report["bundle"])
    log(f"  single-file upload: {single} (~{report['bundle_tokens']:,} tokens)")

    if report["failed"]:
        log(f"bundle: FAIL — required files alone exceed budget "
            f"({report['required_tokens']:,} > {budget:,} tokens); see upload-list.md")
        return 1
    status = "within budget ✅" if report["within_budget"] else "OVER BUDGET ⚠️"
    log(f"upload total ~{report['total_tokens']:,} tokens "
        f"(budget {budget:,}: {status})")
    return 0
