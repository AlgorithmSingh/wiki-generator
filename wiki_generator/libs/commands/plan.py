"""Phase 2 Step 1: run the planning LLM (Vertex AI Gemini 2.5 Pro).

This is the **only** LLM step in the pipeline. It sends the planner instructions +
kickoff prompt + the Step 4 upload bundle to ``gemini-2.5-pro`` on Vertex AI and
saves the raw response to ``<out>/phase2-<provider>-response.md``, which
``normalize-plan`` (Phase 2 Step 2) then consumes. Every other command stays
deterministic and LLM-free.

Auth uses **Application Default Credentials** — run
``gcloud auth application-default login`` or set ``GOOGLE_APPLICATION_CREDENTIALS``.
Project/location come from ``--project`` / ``--location`` or the
``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION`` env vars. Nothing GCP-specific
is hardcoded.

Requires the optional dependency (the google-genai SDK)::

    pip install 'wiki-generator[vertex]'

    python -m wiki_generator plan --bundle <bundle> [--project P --location L]
"""
from __future__ import annotations

import argparse
import os

from ..util import log, read_text, write_text

DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_LOCATION = "us-central1"

# Used only if no instruction/kickoff file is supplied or found on disk. The full
# versions live in gemini-gem/{GEM_INSTRUCTIONS,KICKOFF_PROMPT}.md.
_DEFAULT_SYSTEM = """You are the DeepWiki Planner. You plan a documentation Wiki \
for a software repository from a Phase 1 decomposition digest (a deterministic, \
lossy, LLM-free static-analysis summary). You are a planner, not a writer.

Hard rules: do NOT write the Wiki; do NOT invent evidence (cite only signals in \
the digest, else write `retrieve: <query>`); treat CALLS_APPROX edges, lexical \
query hits, the derived OpenAPI contract, and the static-only test scan as \
approximate and flag them for verification.

Produce exactly three artifacts, each in its own fenced block labeled with its \
filename (a one-line text fence naming the file, then the content):
1. plans/document-plan.json — {repo, one_line_purpose, summary, audience[], \
sections:[{id(kebab), title, order, parent, purpose, rationale, priority}]}
2. plans/document-plan.md — the same plan as a readable outline.
3. plans/section-plans.jsonl — one JSON object per line, 1:1 with the sections, \
each {section_id, title, goal, coverage_requirements[], key_questions[], \
evidence_needs:{symbol_ids[], file_anchors[], query_packs[], graph_nodes[], \
contracts[]}, depends_on[], verification_needs[], estimated_size}.

The output is consumed by a deterministic normalizer, so: use stable kebab ids \
(section_id must equal a document-plan id); prefer canonical query_packs keys \
(web_routes, task_workers, cli_commands, models_schemas, config_keys, \
config_file_keys, env_vars, auth_security, datastore, llm_integrations, \
entrypoints, plugin_registries); prefer real SCIP/dotted symbol ids and \
path:start-end file anchors so references resolve without guessing."""

_DEFAULT_KICKOFF = """You are planning the DeepWiki for the repository summarized \
in the attached Phase 1 decomposition digest. Work only from the attached upload. \
Begin by listing the major runtime surfaces and subsystems you see, then produce \
the three artifacts exactly as specified."""


def _resolve_text(explicit: str | None, candidates: list[str], default: str,
                  what: str) -> str:
    """Return the contents of an explicit file, else the first existing candidate,
    else the embedded default."""
    if explicit:
        text = read_text(os.path.abspath(os.path.expanduser(explicit)))
        if text is None:
            raise FileNotFoundError(f"{what} file not readable: {explicit}")
        return text
    for c in candidates:
        if os.path.isfile(c):
            text = read_text(c)
            if text is not None:
                log(f"  using {what}: {c}")
                return text
    return default


def build_user_content(kickoff: str, bundle_text: str) -> str:
    """Assemble the user turn: the kickoff prompt followed by the upload bundle."""
    return (f"{kickoff.strip()}\n\n"
            "---\n\n"
            "Attached Phase 1 upload bundle:\n\n"
            f"{bundle_text}")


def run(args: argparse.Namespace) -> int:
    bundle_dir = os.path.abspath(os.path.expanduser(args.bundle))
    bundle_file = (os.path.abspath(os.path.expanduser(args.bundle_file))
                   if getattr(args, "bundle_file", None)
                   else os.path.join(bundle_dir, "planner-digest",
                                     "planner-upload-bundle.md"))
    out_dir = (os.path.abspath(os.path.expanduser(args.out_dir))
               if getattr(args, "out_dir", None)
               else os.path.join(bundle_dir, "plans"))
    provider = getattr(args, "provider", "gemini")
    model = getattr(args, "model", DEFAULT_MODEL)

    # --- config checks that don't need the SDK (fail fast, clear messages) ---
    if not os.path.isfile(bundle_file):
        log(f"plan: upload bundle not found: {bundle_file}")
        log("plan: run `bundle` (Step 4) first to produce planner-upload-bundle.md")
        return 2
    bundle_text = read_text(bundle_file)
    if not bundle_text:
        log(f"plan: upload bundle is empty: {bundle_file}")
        return 2

    project = getattr(args, "project", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = (getattr(args, "location", None)
                or os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION)
    if not project:
        log("plan: no GCP project — pass --project or set GOOGLE_CLOUD_PROJECT")
        return 2

    try:
        system_text = _resolve_text(
            getattr(args, "system", None),
            ["gemini-gem/GEM_INSTRUCTIONS.md",
             os.path.join(bundle_dir, "GEM_INSTRUCTIONS.md")],
            _DEFAULT_SYSTEM, "system instructions")
        kickoff_text = _resolve_text(
            getattr(args, "prompt", None),
            ["gemini-gem/KICKOFF_PROMPT.md",
             os.path.join(bundle_dir, "KICKOFF_PROMPT.md")],
            _DEFAULT_KICKOFF, "kickoff prompt")
    except FileNotFoundError as e:
        log(f"plan: {e}")
        return 2

    # --- the LLM call (optional dependency: google-genai) ---
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log("plan: the google-genai SDK is not installed. Install the optional "
            "dependency:  pip install 'wiki-generator[vertex]'")
        return 2

    log(f"plan: Vertex AI {model} (project={project}, location={location})")
    log(f"  upload bundle: {bundle_file} (~{len(bundle_text) // 4:,} tokens)")
    try:
        client = genai.Client(vertexai=True, project=project, location=location)
        config = types.GenerateContentConfig(
            system_instruction=system_text,
            temperature=getattr(args, "temperature", 0.2),
            max_output_tokens=getattr(args, "max_output_tokens", 65535),
        )
        resp = client.models.generate_content(
            model=model,
            contents=build_user_content(kickoff_text, bundle_text),
            config=config,
        )
    except Exception as e:  # noqa: BLE001 - surface any SDK/API error to the user
        log(f"plan: Vertex AI call failed: {e.__class__.__name__}: {e}")
        return 1

    text = getattr(resp, "text", None)
    if not text:
        reason = ""
        cands = getattr(resp, "candidates", None) or []
        if cands:
            reason = f" (finish_reason={getattr(cands[0], 'finish_reason', '?')})"
        log(f"plan: model returned no text{reason}")
        return 1

    out_path = os.path.join(out_dir, f"phase2-{provider}-response.md")
    write_text(out_path, text if text.endswith("\n") else text + "\n")
    log(f"  wrote raw response: {out_path}")
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        log(f"  tokens: prompt={getattr(usage, 'prompt_token_count', '?')}, "
            f"output={getattr(usage, 'candidates_token_count', '?')}, "
            f"total={getattr(usage, 'total_token_count', '?')}")
    log("plan: done. Next: normalize-plan "
        f"--bundle {bundle_dir} --raw-response {out_path}")
    return 0
