"""Phase 2 Step 1b: bounded planner-artifact repair (Patch 2 / Patch 3).

Deterministically normalizes the raw planning response; if the result is not
Phase-3-ready (malformed required SectionPlan row, unresolved exact-lane handle,
or a diagnostic-only user section), re-prompts Vertex/Gemini for *corrected
planning artifacts only*, re-validates with the same strict deterministic gate,
and writes the canonical plan artifacts only when readiness passes. Bounded and
audited; fails loudly if Gemini is unavailable or repair cannot succeed.

    python -m wiki_generator plan-repair \\
        --bundle <bundle> --raw-response <bundle>/plans/phase2-gemini-response.md \\
        [--out <dir>] [--max-attempts 2] [--project P --location L]

This is a Phase 2 step. Phase 3 never invokes it. Exit codes:
0 = readiness PASS (no repair needed, or repair succeeded);
2 = bad input / repair unavailable (Vertex/Gemini not reachable);
1 = repair ran but could not produce valid, Phase-3-ready artifacts.
"""
from __future__ import annotations

import argparse
import os

from ..plan_normalization import repair as _repair
from ..util import log


def run(args: argparse.Namespace) -> int:
    bundle_dir = os.path.abspath(os.path.expanduser(args.bundle))
    raw_path = os.path.abspath(os.path.expanduser(args.raw_response))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_dir, "plans"))

    if not os.path.isdir(bundle_dir):
        log(f"plan-repair: not a bundle directory: {bundle_dir}")
        return 2
    if not os.path.isfile(raw_path):
        log(f"plan-repair: raw response not found: {raw_path}")
        return 2

    project = (getattr(args, "project", None)
               or os.environ.get("GOOGLE_CLOUD_PROJECT"))
    location = (getattr(args, "location", None)
                or os.environ.get("GOOGLE_CLOUD_LOCATION") or _repair.DEFAULT_LOCATION)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    log(f"plan-repair: {raw_path}")
    try:
        report = _repair.repair_plan(
            bundle_dir, raw_path, out_dir,
            provider=getattr(args, "provider", "gemini"),
            max_attempts=getattr(args, "max_attempts", 2),
            project=project, location=location,
            model=getattr(args, "model", _repair.DEFAULT_MODEL),
            api_key=api_key,
            max_output_tokens=getattr(args, "max_output_tokens", 32768),
        )
    except _repair.RepairUnavailable as e:
        log(f"plan-repair: repair REQUIRED but unavailable — {e}")
        log("  fix: configure Vertex (--project/$GOOGLE_CLOUD_PROJECT) or set "
            "$GEMINI_API_KEY, then rerun; or fix the planner artifacts by hand")
        return 2
    except _repair.RepairFailed as e:
        log(f"plan-repair: FAILED — {e}")
        return 1

    if report["repaired"]:
        log(f"plan-repair: repaired in {report['attempts']} attempt(s) "
            f"via {report.get('client_mode')} — readiness PASS")
        log(f"  audit: {os.path.join(out_dir, 'repair')}")
    else:
        log("plan-repair: no repair needed — readiness already PASS")
    log(f"  wrote plan artifacts: {report['out_dir']}")
    return 0
