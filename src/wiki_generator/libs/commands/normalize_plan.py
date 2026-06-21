"""Phase 2 Step 2 command: deterministically normalize a planning response.

Reads the raw Gemini/Kimi planning response and the Phase 1 indexes, then writes
machine-resolvable plan artifacts for Phase 3. No LLM calls.

    python -m wiki_generator normalize-plan \\
        --bundle <bundle> --raw-response <bundle>/plans/phase2-gemini-response.md \\
        [--out <dir>] [--strict] [--provider gemini]
"""
from __future__ import annotations

import argparse
import os

from .. import plan_normalization
from ..util import log


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

    if report["strict"] and not report["strict_pass"]:
        log(f"normalize-plan: STRICT FAIL — {report['unresolved_total']} "
            "unresolved reference(s); see unresolved-references.jsonl")
        return 1
    log("normalize-plan: done")
    return 0
