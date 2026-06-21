"""Command-line interface (thin dispatcher).

The CLI only parses arguments and routes to a command in
``wiki_generator.libs.commands``. All real work lives in ``libs``; this
module stays deliberately small.

    python -m wiki_generator decompose     --repo <repo> --out <out> [flags]
    python -m wiki_generator condense      --in <bundle> [--budget-tokens N]
    python -m wiki_generator digest        --in <bundle> [--out <dir>] [--budget-tokens N]
    python -m wiki_generator bundle        --in <bundle> [--out <dir>] [--budget-tokens N]
    python -m wiki_generator plan          --bundle <bundle> [--project P --location L]  (Vertex AI; LLM step)
    python -m wiki_generator normalize-plan --bundle <bundle> --raw-response <file> [--out <dir>]
"""
from __future__ import annotations

import argparse

from .libs.commands import bundle as bundle_cmd
from .libs.commands import condense as condense_cmd
from .libs.commands import decompose as decompose_cmd
from .libs.commands import digest as digest_cmd
from .libs.commands import normalize_plan as normalize_plan_cmd
from .libs.commands import plan as plan_cmd

_TOGGLE = ("auto", "on", "off")
DEFAULT_BUDGET_TOKENS = 250_000


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki_generator",
        description="Phase 1 decomposition: build a deterministic repo-analysis "
                    "artifact bundle from a Python repo (no LLM calls), then "
                    "condense it into planner-facing digests.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decompose", help="produce the artifact bundle (Step 1)")
    d.add_argument("--repo", required=True, help="path to the Python repo to decompose")
    d.add_argument("--out", required=True, help="output directory for the artifact bundle")
    d.add_argument("--embeddings", choices=_TOGGLE, default="auto",
                   help="vector lane (rag/vectors.faiss). auto=use if faiss+model2vec "
                        "importable (default), on=require, off=skip")
    d.add_argument("--grep-ast", choices=_TOGGLE, default="auto",
                   help="grep-ast AST previews. auto=use if it self-tests, else "
                        "built-in fallback (default)")
    d.add_argument("--semgrep", choices=_TOGGLE, default="auto",
                   help="semgrep query results. auto=use if installed (default)")
    d.add_argument("--ast-grep", choices=_TOGGLE, default="auto",
                   help="ast-grep query results. auto=use if installed (default)")
    d.add_argument("--pytest-collect", choices=_TOGGLE, default="auto",
                   help="pytest --collect-only (imports test modules). auto=attempt "
                        "if pytest importable (default), off=static scan only")
    d.add_argument("--contracts-import", action="store_true",
                   help="UNSAFE: import the app to extract a live OpenAPI schema "
                        "(executes repo code). Off by default; static discovery only.")
    d.add_argument("--rg-cap", type=int, default=80,
                   help="max digested hits captured per ripgrep query pack")

    c = sub.add_parser("condense",
                       help="Step 2: write planning condensates into <bundle>/derived/")
    c.add_argument("--in", dest="in_dir", required=True,
                   help="path to an existing decomposition bundle")
    c.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS,
                   help="target upload token budget (default 250000)")

    g = sub.add_parser("digest",
                       help="Step 3: write derived/planning-digest.md (also runs Step 4)")
    g.add_argument("--in", dest="in_dir", required=True,
                   help="path to an existing decomposition bundle")
    g.add_argument("--out", dest="out_dir", default=None,
                   help="upload package directory (default <bundle>/planner-digest)")
    g.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS,
                   help="target upload token budget (default 250000)")
    g.add_argument("--no-bundle", action="store_true",
                   help="stop after planning-digest.md; do not assemble the bundle")

    b = sub.add_parser("bundle",
                       help="Step 4: assemble the single-file planner upload bundle")
    b.add_argument("--in", dest="in_dir", required=True,
                   help="path to an existing decomposition bundle")
    b.add_argument("--out", dest="out_dir", default=None,
                   help="upload package directory (default <bundle>/planner-digest)")
    b.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS,
                   help="target upload token budget (default 250000)")

    pl = sub.add_parser("plan",
                        help="Phase 2 Step 1: run the planning LLM (Vertex AI "
                             "Gemini 2.5 Pro) on the upload bundle. The only LLM "
                             "step; needs the [vertex] extra + GCP credentials.")
    pl.add_argument("--bundle", required=True,
                    help="path to the Phase 1 decomposition bundle")
    pl.add_argument("--bundle-file", dest="bundle_file", default=None,
                    help="explicit upload bundle path "
                         "(default <bundle>/planner-digest/planner-upload-bundle.md)")
    pl.add_argument("--out", dest="out_dir", default=None,
                    help="output directory for the raw response (default <bundle>/plans)")
    pl.add_argument("--model", default="gemini-2.5-pro",
                    help="Vertex AI model id (default gemini-2.5-pro)")
    pl.add_argument("--project", default=None,
                    help="GCP project (default $GOOGLE_CLOUD_PROJECT)")
    pl.add_argument("--location", default=None,
                    help="Vertex AI location (default $GOOGLE_CLOUD_LOCATION or us-central1)")
    pl.add_argument("--provider", default="gemini",
                    help="provider label for the output filename (default gemini)")
    pl.add_argument("--system", default=None,
                    help="system-instructions file (default gemini-gem/GEM_INSTRUCTIONS.md "
                         "if present, else built-in)")
    pl.add_argument("--prompt", default=None,
                    help="kickoff-prompt file (default gemini-gem/KICKOFF_PROMPT.md "
                         "if present, else built-in)")
    pl.add_argument("--temperature", type=float, default=0.2,
                    help="sampling temperature (default 0.2)")
    pl.add_argument("--max-output-tokens", dest="max_output_tokens", type=int,
                    default=65535, help="max output tokens (default 65535)")

    n = sub.add_parser("normalize-plan",
                       help="Phase 2 Step 2: deterministically normalize a planning "
                            "LLM response into machine-resolvable plan artifacts")
    n.add_argument("--bundle", required=True,
                   help="path to the Phase 1 decomposition bundle")
    n.add_argument("--raw-response", dest="raw_response", required=True,
                   help="path to the raw Gemini/Kimi planning response (markdown)")
    n.add_argument("--out", dest="out_dir", default=None,
                   help="output directory for plan artifacts (default <bundle>/plans)")
    n.add_argument("--strict", action="store_true",
                   help="exit non-zero if any symbol/file/query-pack is unresolved")
    n.add_argument("--allow-unresolved", action="store_true", default=True,
                   help="record unresolved references and continue (default)")
    n.add_argument("--provider", default="gemini",
                   help="planning provider name, recorded as metadata only")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "decompose":
        return decompose_cmd.run(args)
    if args.command == "condense":
        return condense_cmd.run(args)
    if args.command == "digest":
        return digest_cmd.run(args)
    if args.command == "bundle":
        return bundle_cmd.run(args)
    if args.command == "plan":
        return plan_cmd.run(args)
    if args.command == "normalize-plan":
        return normalize_plan_cmd.run(args)
    return 2  # pragma: no cover - argparse enforces a known command


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
