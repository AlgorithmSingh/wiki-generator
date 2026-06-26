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
lossy, LLM-free static-analysis summary). You are producing a retrieval work \
order, not final Wiki prose. You are a planner, not a writer.

Hard rules: do NOT write the Wiki; do NOT invent evidence; treat CALLS_APPROX \
edges, lexical query hits, the derived OpenAPI contract, and the static-only \
test scan as approximate and flag them for verification.

Use exact handles when filling exact retrieval lanes (take them from \
`planning-handles.md`). If you cannot name an exact handle, do NOT place the \
item in that exact lane — move it to `search_hints[]`. Move planning \
digest/condensate documents into `context_artifacts[]`.

Produce exactly three artifacts, each in its own fenced block labeled with its \
filename (a one-line text fence naming the file, then the content):
1. plans/document-plan.json — {repo, one_line_purpose, summary, audience[], \
sections:[{id(kebab), title, order, parent, purpose, rationale, priority}]}
2. plans/document-plan.md — the same plan as a readable outline.
3. plans/section-plans.jsonl — one JSON object per line, 1:1 with the sections, \
each {section_id, title, parent_section_id, coverage_labels[], goal, \
coverage_requirements[], required_topics[], topic_evidence_requirements[], \
key_questions[], \
evidence_needs:{symbol_ids[], file_anchors[], query_packs[], graph_nodes[], \
contracts[], search_hints[], context_artifacts[]}, depends_on[], \
verification_needs[], estimated_size}.

Lane rules (the output is consumed by a deterministic normalizer):
- symbol_ids[]: exact `symbol_id` only — no dotted guesses, repo names, globs, \
or `retrieve: …` requests.
- file_anchors[]: exact repo source files only — never a directory or \
trailing-slash path (agent/component/ is INVALID; use agent/component/base.py or \
move the area to search_hints[]); never `derived/planning-*.md`.
- contracts[]: exact `METHOD /path` only — `contracts/openapi.json` alone is \
NOT a contract.
- tests[]: exact test file and function/node id when available.
- graph_nodes[]: exact `node_id` only (e.g. `dep:pytest`) — never a display \
label like `pytest [Dependency]`.
- query_packs[]: canonical keys only (web_routes, task_workers, cli_commands, \
models_schemas, config_keys, config_file_keys, env_vars, auth_security, \
datastore, llm_integrations, entrypoints, plugin_registries).
- search_hints[]: broad/fuzzy recall text such as `retrieve: api.apps.*`, \
`module layout`, or `test function markers`.
- context_artifacts[]: digest/planning docs used to understand the repo; never \
citeable source evidence.

section-plans.jsonl must be valid JSONL: exactly one complete JSON object per line, \
with no bare strings, comments, or prose between/inside objects. Every sentence \
belongs to a named field — verification work in verification_needs[], uncertainty in \
known_gaps[]. BAD: {"section_id":"x","verification_needs":[],"a bare sentence.","estimated_size":"M"} \
GOOD: {"section_id":"x","verification_needs":["a bare sentence."],"known_gaps":[],"estimated_size":"M"}

planning-gaps.md is internal planning/provenance context, NOT source evidence: do \
not put it in file_anchors[] and do not create a "Known gaps / unverified" section \
from it — attach uncertainty to affected sections via verification_needs[]. Every \
section must have a real retrieval signal (an exact handle, query pack, or search hint).
Use stable kebab ids (section_id must equal a document-plan id).

DeepWiki coverage enhancement: plan a broad, hierarchical guide. Where the digest \
has real signal, give each mandatory topic family its own page (or child page under \
a subsystem via parent_section_id) and tag it with a canonical coverage_labels[] \
value: frontend, memory, queue-system, helm-k8s, ci-cd-build, go-native, \
retrieval-internals, doc-processing, llm-internals, user-tenant-admin-health, \
sandbox-executor, migrations-operations, glossary. A broad parent page does NOT \
count as coverage for a deep child topic unless that child has its own page, label, \
and evidence. Do not invent a family the digest shows no signal for — note its \
absence in known_gaps[]. `planning-coverage-signals.md` maps where each family \
likely lives (candidate paths, present/low/missing status, suggested \
coverage_labels[]/search_hints[]) — it is planner CONTEXT only, never citeable \
evidence: do not place its candidate paths in a file_anchors[] exact lane; cite \
exact handles from planning-handles.md instead. A coverage-enhanced run gates the \
normalized plan against all thirteen mandatory families before Phase 3, so omitting \
a supported family fails loudly.

topic_evidence_requirements[] (enhancement mode): the normalizer MERGES \
coverage_requirements[] AND required_topics[] into one normalized required-topics \
list, so add one object {topic, required:true, source_fields:[…], min_items, \
acceptable_lanes:[…]} for EVERY entry in BOTH fields in a normal source-evidence \
section — one per coverage_requirements[] entry and one per required_topics[] entry \
(use the exact same topic string). A merged required topic with no matching object \
is the #1 cause of a failed run. source_fields[] must point at the EXACT normalized \
retrieval lanes that will ground the topic, by index: e.g. "retrieval_needs.files[0]", \
"retrieval_needs.symbols[1]", "retrieval_needs.contracts[0]", \
"retrieval_needs.tests[0]", or "retrieval_needs.query_packs[0]" — the same \
evidence_needs entries you filled above, not prose. Prefer these canonical \
retrieval_needs.* names. Raw evidence_needs.* names (e.g. \
"evidence_needs.file_anchors[0]", "evidence_needs.symbol_ids[0]") are accepted only \
as compatibility input: Phase 2 canonicalizes them to retrieval_needs.* ONLY when \
that exact raw handle resolves to a normalized lane, otherwise the topic fails the \
gate — so never use a raw alias for a handle you did not also place in evidence_needs. \
acceptable_lanes[] must include \
at least one exact lane (file_anchor/symbol_anchor/contract/test/query_pack). This is \
plain JSON, not a DSL. A coverage-enhanced run now runs a deterministic Phase 2 gate \
that fails loudly BEFORE Phase 3 if any merged required topic lacks a matching object, \
points at a retrieval_needs lane that does not exist, or is grounded only on broad \
recall (bm25/vector/graph_neighbors/search_hints); Phase 3 then maps each topic to \
citeable evidence and broad recall can never make a topic sufficient. So only require \
a topic you can ground with exact handles, and record an unavoidable gap in \
known_gaps[] instead of over-requiring."""

_DEFAULT_KICKOFF = """You are planning the DeepWiki for the repository summarized \
in the attached Phase 1 decomposition digest. Work only from the attached upload. \
Begin by listing the major runtime surfaces and subsystems you see, then produce \
the three artifacts exactly as specified. Fill exact lanes only with exact \
handles from `planning-handles.md`; put broad recall requests in `search_hints[]` \
and digest/condensate documents in `context_artifacts[]`. Plan a broad, \
hierarchical guide: give each mandatory DeepWiki topic family the digest supports \
its own page (or child page via parent_section_id) tagged with a canonical \
coverage_labels[] value (frontend, memory, queue-system, helm-k8s, ci-cd-build, \
go-native, retrieval-internals, doc-processing, llm-internals, \
user-tenant-admin-health, sandbox-executor, migrations-operations, glossary). Use \
`planning-coverage-signals.md` (planner context only, never citeable evidence) to \
decide which families deserve their own page. For every coverage_requirements[] and \
required_topics[] entry (both merge into the normalized required topics), add a \
topic_evidence_requirements[] entry whose source_fields[] name the exact \
retrieval_needs.* lanes (e.g. retrieval_needs.symbols[0], retrieval_needs.files[1]) \
that ground it — a deterministic Phase 2 gate fails before Phase 3 on any merged \
required topic without a matching exact citeable obligation, and enhancement mode \
fails before Phase 4 on any required topic without sufficient exact evidence."""


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


def _finish_reason_name(resp: object) -> str:
    """Best-effort normalized finish reason of the response's first candidate.

    Returns the enum name (e.g. ``"STOP"``, ``"MAX_TOKENS"``) when available,
    else the stringified value, else ``""``. Tolerant of SDK shape differences
    so the caller can do a simple substring/name check without importing the enum.
    """
    cands = getattr(resp, "candidates", None) or []
    if not cands:
        return ""
    fr = getattr(cands[0], "finish_reason", None)
    if fr is None:
        return ""
    return getattr(fr, "name", None) or str(fr)


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
    finish = _finish_reason_name(resp)
    if not text:
        reason = f" (finish_reason={finish})" if finish else ""
        log(f"plan: model returned no text{reason}")
        return 1

    # Loud guard against a truncated plan. gemini-2.5-pro is a thinking model and
    # spends part of --max-output-tokens on its reasoning, so a cap that is too
    # small stops the response with finish_reason=MAX_TOKENS and a partial (but
    # non-empty) body. Writing that as the canonical response would silently feed
    # a truncated plan into normalize-plan; treat it as a config failure and fail
    # loudly instead, per the --max-output-tokens help ("tiny caps ... are a
    # test-config failure, not a planner-quality result").
    if "MAX_TOKENS" in finish:
        log("plan: response truncated (finish_reason=MAX_TOKENS) — the output cap "
            "was too small for the full plan. A thinking model spends part of "
            "--max-output-tokens on reasoning; raise it (8192+ for smoke, 32768+ "
            "for full e2e runs) and re-run. Refusing to write a truncated plan.")
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
