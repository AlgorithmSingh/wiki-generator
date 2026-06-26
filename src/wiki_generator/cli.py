"""Command-line interface (thin dispatcher).

The CLI only parses arguments and routes to a command in
``wiki_generator.libs.commands``. All real work lives in ``libs``; this
module stays deliberately small.

    python -m wiki_generator decompose     --repo <repo> --out <out> [flags]
    python -m wiki_generator condense      --in <bundle> [--budget-tokens N]
    python -m wiki_generator digest        --in <bundle> [--out <dir>] [--budget-tokens N]
    python -m wiki_generator bundle        --in <bundle> [--out <dir>] [--budget-tokens N]
    python -m wiki_generator build-retrieval --in <bundle> [--bm25 ...] [--vectors ...]
    python -m wiki_generator plan          --bundle <bundle> [--project P --location L]  (Vertex AI; LLM step)
    python -m wiki_generator normalize-plan --bundle <bundle> --raw-response <file> [--out <dir>]
    python -m wiki_generator retrieve-evidence --bundle <bundle> [--out <dir>]   (Phase 3)
    python -m wiki_generator write-wiki     --bundle <bundle> --provider {gemini-gem|gemini-api|vertex}  (Phase 4)
"""
from __future__ import annotations

import argparse

from .libs.commands import build_retrieval as build_retrieval_cmd
from .libs.commands import bundle as bundle_cmd
from .libs.commands import condense as condense_cmd
from .libs.commands import decompose as decompose_cmd
from .libs.commands import digest as digest_cmd
from .libs.commands import normalize_plan as normalize_plan_cmd
from .libs.commands import plan as plan_cmd
from .libs.commands import plan_repair as plan_repair_cmd
from .libs.commands import retrieve_evidence as retrieve_evidence_cmd
from .libs.commands import validate_coverage as validate_coverage_cmd
from .libs.commands import write_wiki as write_wiki_cmd

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

    br = sub.add_parser(
        "build-retrieval",
        help="Step 5: build/verify the retrieval substrate (BM25 + optional "
             "vectors) and write the Phase 3 capability contract")
    br.add_argument("--in", dest="in_dir", required=True,
                    help="path to an existing decomposition bundle")
    br.add_argument("--bm25", choices=_TOGGLE, default="on",
                    help="BM25 lexical index. on/auto=build or verify (default), "
                         "off=skip")
    br.add_argument("--vectors", choices=_TOGGLE, default="auto",
                    help="vector lane. auto=build if faiss+model2vec importable, "
                         "else skip with a reason (default); on=require (fail if "
                         "unavailable); off=skip")
    br.add_argument("--embedding-model", dest="embedding_model", default=None,
                    help="local embedding model (default minishlab/potion-base-8M)")
    br.add_argument("--batch-size", dest="batch_size", type=int, default=None,
                    help="embedding batch size (default 2048)")
    br.add_argument("--rebuild", action="store_true",
                    help="delete and rebuild existing retrieval indexes")
    br.add_argument("--smoke-query", dest="smoke_query", default=None,
                    help="optional query to test the substrate after build")
    br.add_argument("--fail-without-vectors", dest="fail_without_vectors",
                    action="store_true", help="alias for --vectors on")

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
    n.add_argument("--coverage-mode", dest="coverage_mode", default="baseline",
                   choices=("baseline", "enhancement"),
                   help=("Phase 2 → Phase 3 planned coverage boundary. "
                         "baseline (default): non-enforcing DeepWiki coverage "
                         "matrix only, never gates the command (safe for "
                         "compact/legacy plans). enhancement: deterministically "
                         "gate the normalized plan against all 13 mandatory topic "
                         "families and fail loudly (exit 3) on a missing family "
                         "before Phase 3. This is a planned-coverage gate only; "
                         "it never edits/heals the plan."))

    pr = sub.add_parser(
        "plan-repair",
        help="Phase 2 Step 1b: bounded Vertex/Gemini repair of planner artifacts "
             "when normalization is not Phase-3-ready (Patch 2/3). Audited, capped, "
             "fails loudly. Phase 3 never invokes this.")
    pr.add_argument("--bundle", required=True,
                    help="path to the Phase 1 decomposition bundle")
    pr.add_argument("--raw-response", dest="raw_response", required=True,
                    help="path to the raw Gemini/Kimi planning response (markdown)")
    pr.add_argument("--out", dest="out_dir", default=None,
                    help="output directory for plan artifacts (default <bundle>/plans)")
    pr.add_argument("--provider", default="gemini",
                    help="planning provider name, recorded as metadata only")
    pr.add_argument("--max-attempts", dest="max_attempts", type=int, default=2,
                    help="bounded repair attempts (1 or 2; hard cap 2)")
    pr.add_argument("--model", default="gemini-2.5-pro",
                    help="Vertex/Gemini model id (default gemini-2.5-pro)")
    pr.add_argument("--project", default=None,
                    help="GCP project for Vertex (default $GOOGLE_CLOUD_PROJECT)")
    pr.add_argument("--location", default=None,
                    help="Vertex location (default $GOOGLE_CLOUD_LOCATION or us-central1)")
    pr.add_argument("--max-output-tokens", dest="max_output_tokens", type=int,
                    default=32768, help="max output tokens (default 32768; not tiny)")
    pr.add_argument("--coverage-mode", dest="coverage_mode", default="baseline",
                    choices=("baseline", "enhancement"),
                    help=("repair acceptance gate. baseline (default): the old "
                          "Phase-3 readiness gate only. enhancement: accept a repair "
                          "ONLY when readiness AND the deterministic planned-coverage "
                          "+ topic-obligation enhancement gates all pass; a repair "
                          "that passes old readiness but fails topic obligations is "
                          "rejected, its diagnostics fed into the next attempt, and "
                          "the run fails loudly after the cap."))

    re_ = sub.add_parser(
        "retrieve-evidence",
        help="Phase 3: retrieve deterministic, citeable evidence packets for "
             "every planned section (no LLM). All-sections producer.")
    re_.add_argument("--bundle", required=True,
                     help="path to the Phase 1/2 bundle root")
    re_.add_argument("--out", dest="out_dir", default=None,
                     help="output directory for evidence (default <bundle>/evidence)")
    re_.add_argument("--max-per-lane", dest="max_per_lane", type=int, default=None,
                     help="max evidence items kept per lane per section "
                          "(default: stable implementation constant)")
    re_.add_argument("--max-total-per-section", dest="max_total_per_section",
                     type=int, default=None,
                     help="max evidence items kept per section (default: stable "
                          "implementation constant)")
    re_.add_argument("--coverage-mode", dest="coverage_mode", default="baseline",
                     choices=("baseline", "enhancement"),
                     help=("evidenced-coverage gate. baseline (default): report "
                           "evidenced coverage without gating (non-breaking for "
                           "legacy/compact fixtures). enhancement: a required "
                           "topic with weak/missing exact evidence fails the run "
                           "(exit 3, bad_underspecified_normalized_plan) BEFORE "
                           "Phase 4. Still all-sections; no --section, no retry "
                           "loop, no synthetic evidence."))

    _ww_help = ("Phase 4: writing/synthesis only. Consume a clean Phase 1-3 bundle, "
                "gate on upstream success, generate grounded DeepWiki-style sections "
                "with EvidencePacket citations, and assemble the wiki. Never re-runs "
                "Phase 3, never repairs the plan, never invents fallback evidence.")
    ww = sub.add_parser("write-wiki", help=_ww_help, description=_ww_help)
    ww.add_argument("--bundle", required=True,
                    help="path to the accepted Phase 1/2/3 bundle root")
    ww.add_argument("--out", dest="out_dir", default=None,
                    help="output directory for the wiki (default <bundle>/wiki)")
    ww.add_argument("--provider", default="vertex",
                    choices=("gemini-gem", "gemini-api", "vertex"),
                    help="execution mode: gemini-gem (manual Gem prompt/response "
                         "handoff), gemini-api (direct GEMINI_API_KEY; NOT Vertex), "
                         "or vertex (Vertex AI). Default: vertex")
    ww.add_argument("--model", default="gemini-2.5-pro",
                    help="model id for gemini-api/vertex (default gemini-2.5-pro)")
    ww.add_argument("--temperature", type=float, default=None,
                    help="sampling temperature for gemini-api/vertex (default 0.1)")
    ww.add_argument("--max-output-tokens", dest="max_output_tokens", type=int,
                    default=None,
                    help="max output tokens (default 32768; <32768 warns for "
                         "gemini-2.5-pro full-section synthesis, 8192 can truncate)")
    ww.add_argument("--prepare-prompts-only", dest="prepare_prompts_only",
                    action="store_true",
                    help="write per-section prompt packets and stop (no model "
                         "call); for the Gemini Gem handoff")
    ww.add_argument("--validate-and-assemble", dest="validate_and_assemble",
                    action="store_true",
                    help="default phase: generate/import responses, validate, and "
                         "assemble (informational; this is the default when "
                         "--prepare-prompts-only is not set)")
    ww.add_argument("--prompt-out", dest="prompt_out", default=None,
                    help="directory for prepared prompts (default "
                         "<out>/audit/prompts)")
    ww.add_argument("--responses-in", dest="responses_in", default=None,
                    help="directory of verbatim raw Gem responses to import "
                         "(gemini-gem mode; default <out>/audit/responses)")
    ww.add_argument("--max-rewrite-attempts", dest="max_rewrite_attempts", type=int,
                    default=None,
                    help="bounded format/citation rewrites for gemini-api/vertex "
                         "(0..2; default 1). Never used to add evidence.")
    ww.add_argument("--coverage-mode", dest="coverage_mode", default="baseline",
                    choices=("baseline", "enhancement"),
                    help=("DeepWiki coverage enhancement. baseline (default): write "
                          "the grounded wiki with no upstream coverage gate and no "
                          "generated-coverage validation (non-breaking for compact "
                          "fixtures). enhancement: refuse to call any provider unless "
                          "the Phase 2 planned-coverage gate (plans/coverage-gate.json) "
                          "and Phase 3 evidenced-coverage gate "
                          "(evidence/evidenced-coverage.json + the "
                          "required_topic_evidence_sufficient contract check) are "
                          "enforced/passing (else exit 3, pre-provider); preserve "
                          "parent/child hierarchy; and deterministically validate that "
                          "every evidenced sufficient required topic is generated with "
                          "valid mapped citations (else exit 5). Never re-runs Phase "
                          "2/3 or synthesizes evidence."))
    ww.add_argument("--project", default=None,
                    help="GCP project for vertex (default $GOOGLE_CLOUD_PROJECT)")
    ww.add_argument("--location", default=None,
                    help="Vertex location (default $GOOGLE_CLOUD_LOCATION or "
                         "us-central1)")
    ww.add_argument("--accept-no-force", dest="accept_no_force",
                    action="store_true",
                    help="operator assertion that Phase 3 was not force-run after a "
                         "readiness FAIL, used only when the bundle carries no "
                         "command manifest (fails closed otherwise)")
    ww.add_argument("--style", default="deepwiki",
                    help="style profile (default deepwiki)")
    ww.add_argument("--audit-raw", dest="audit_raw", action="store_true",
                    default=True, help="audit raw prompt/response (default on)")
    ww.add_argument("--no-audit-raw", dest="no_audit_raw", action="store_true",
                    help="(reserved) disable raw audit; audit is on by default")

    vc_help = ("Milestone 2: deterministic, LLM-free coverage validation. Check a "
               "bundle's normalized Phase 2 plan against the mandatory DeepWiki "
               "topic-family taxonomy and write a coverage report. In enhancement "
               "mode a missing mandatory family fails the gate (exit 3). Never "
               "runs a model or another phase; never edits plan/wiki artifacts.")
    vc = sub.add_parser("validate-coverage", help=vc_help, description=vc_help)
    vc.add_argument("--bundle", required=True,
                    help="path to the Phase 1/2 bundle root (reads plans/)")
    vc.add_argument("--out", dest="out_dir", default=None,
                    help="output directory for the coverage report "
                         "(default <bundle>/coverage)")
    vc.add_argument("--mode", default="enhancement",
                    choices=("enhancement", "baseline"),
                    help="enhancement: missing mandatory family fails the gate "
                         "(default); baseline: report coverage without enforcing")
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
    if args.command == "build-retrieval":
        return build_retrieval_cmd.run(args)
    if args.command == "plan":
        return plan_cmd.run(args)
    if args.command == "normalize-plan":
        return normalize_plan_cmd.run(args)
    if args.command == "plan-repair":
        return plan_repair_cmd.run(args)
    if args.command == "retrieve-evidence":
        return retrieve_evidence_cmd.run(args)
    if args.command == "write-wiki":
        return write_wiki_cmd.run(args)
    if args.command == "validate-coverage":
        return validate_coverage_cmd.run(args)
    return 2  # pragma: no cover - argparse enforces a known command


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
