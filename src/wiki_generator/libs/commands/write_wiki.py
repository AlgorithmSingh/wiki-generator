"""write-wiki command wrapper (Phase 4 — writing/synthesis).

Thin: resolve paths + provider config into ``WritingOptions``, dispatch to
``libs.writing``, and map a classified failure to its exit code. Phase 4 is a
synthesis step only — it never runs Phase 3 retrieval, Phase 2 repair, or any
planner command.

Exit codes: 0 PASS / prepared; 2 bad/missing input artifact; 3 upstream gate
failure (readiness/retrieval/force/stale/hygiene/packets); 4 provider failure;
5 writing-validation failure; 1 internal bug.
"""
from __future__ import annotations

import argparse
import os

from .. import writing
from ..util import log
from ..writing import assemble
from ..writing.errors import (
    EXIT_BUG,
    BadInputArtifact,
    GateFailure,
    Phase4Error,
    ProviderFailure,
    WritingValidationFailure,
)
from ..writing.options import CLI_PROVIDERS, WritingOptions


def build_options(args: argparse.Namespace) -> WritingOptions:
    bundle_root = os.path.abspath(os.path.expanduser(args.bundle))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_root, "wiki"))
    provider_mode = CLI_PROVIDERS.get(args.provider)
    if provider_mode is None:
        raise ValueError(f"unknown --provider {args.provider!r}; "
                         f"choose from {sorted(CLI_PROVIDERS)}")

    project = getattr(args, "project", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = (getattr(args, "location", None)
                or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1")
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    kwargs = dict(
        bundle_root=bundle_root,
        out_dir=out_dir,
        provider=provider_mode,
        model=getattr(args, "model", None) or "gemini-2.5-pro",
        prepare_only=bool(getattr(args, "prepare_prompts_only", False)),
        prompt_out=(os.path.abspath(os.path.expanduser(args.prompt_out))
                    if getattr(args, "prompt_out", None) else None),
        responses_in=(os.path.abspath(os.path.expanduser(args.responses_in))
                      if getattr(args, "responses_in", None) else None),
        project=project,
        location=location,
        api_key=api_key,
        accept_no_force=bool(getattr(args, "accept_no_force", False)),
        audit_raw=not getattr(args, "no_audit_raw", False),
    )
    if getattr(args, "temperature", None) is not None:
        kwargs["temperature"] = args.temperature
    if getattr(args, "max_output_tokens", None) is not None:
        kwargs["max_output_tokens"] = args.max_output_tokens
    if getattr(args, "max_rewrite_attempts", None) is not None:
        kwargs["max_rewrite_attempts"] = args.max_rewrite_attempts
    if getattr(args, "style", None):
        kwargs["style"] = args.style
    return WritingOptions(**kwargs)


def run(args: argparse.Namespace) -> int:
    try:
        options = build_options(args)
    except ValueError as e:
        log(f"write-wiki: invalid options — {e}")
        return 2
    if not os.path.isdir(options.bundle_root):
        log(f"write-wiki: not a bundle directory: {options.bundle_root}")
        return 2

    log(f"write-wiki: {options.bundle_root} (provider={options.provider})")
    try:
        result = writing.run(options)
    except BadInputArtifact as e:
        assemble.write_failure_report(options.out_dir, options.bundle_root,
                                      e.category, str(e))
        log(f"write-wiki: bad/missing input — {e}")
        return e.exit_code
    except GateFailure as e:
        assemble.write_failure_report(options.out_dir, options.bundle_root,
                                      e.category, str(e))
        log(f"write-wiki: upstream gate FAILED — {e}")
        log("  fix upstream (readiness/Phase 2 plan/Phase 3 evidence); Phase 4 "
            "does not repair or re-retrieve.")
        return e.exit_code
    except ProviderFailure as e:
        assemble.write_failure_report(options.out_dir, options.bundle_root,
                                      e.category, str(e))
        log(f"write-wiki: provider FAILED — {e}")
        return e.exit_code
    except WritingValidationFailure as e:
        log(f"write-wiki: writing validation FAILED — {e}")
        return e.exit_code
    except Phase4Error as e:  # pragma: no cover - defensive
        log(f"write-wiki: internal error — {e}")
        return e.exit_code
    except Exception as e:  # pragma: no cover - unclassified bug
        assemble.write_failure_report(options.out_dir, options.bundle_root,
                                      "writer_implementation_bug", repr(e))
        log(f"write-wiki: internal error — {e}")
        return EXIT_BUG

    if result.status == "prepared":
        log(f"write-wiki: PREPARED — {result.message}")
        log(f"  prompts under: {options.prompt_out or os.path.join(options.out_dir, 'audit', 'prompts')}")
        return 0
    log(f"  sections: {result.counts.get('generated')}/{result.counts.get('sections')}"
        f"  citations: {result.counts.get('distinct_citations')}")
    for w in result.warnings:
        log(f"  warning: {w}")
    for f in result.files:
        log(f"    - {f}")
    log("write-wiki: PASS")
    return 0
