# Phase 4 Writing / Synthesis Spec

## Status and source of truth

Status: **SPEC ONLY / future implementation**. This file designs Phase 4; it does
not implement a command, run a model, or change Phase 1-3 behavior.

Design target: a grounded DeepWiki-style generated wiki/document produced from a
clean Phase 1-3 artifact bundle.

Authoritative upstream constraints:

- Current readiness handoff: `HANDOFF_READINESS_ITERATION_2.md`.
- Current Phase 1/2/3 readiness spec: `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md`.
- Baseline readiness amendment: `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_SPEC.md`.
- Phase 3 evidence contract: `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` must remain
  unchanged.
- Fresh accepted Phase 1-3 bundle for this design:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038`.
- Fresh acceptance report:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038/EXPERIMENT_RESULT.md`.

Do **not** design against stale pre-patch bundles, forced Phase-3-after-`FAIL`
outputs, or older `11-testing-pipeline` artifacts.

## Purpose and scope

Phase 4 consumes a clean Phase 1-3 bundle and writes the final wiki/document.
It is a synthesis step, not a retrieval or repair step.

Phase 4 must:

1. Load the normalized plan, section plans, evidence packets, retrieval
   validation, readiness report, and provenance/context metadata from one bundle.
2. Gate on Phase 1-3 success before any writing call.
3. Generate DeepWiki-style explanatory Markdown for each planned section.
4. Assemble those sections into a coherent wiki/index.
5. Emit a citation manifest, raw prompt/response audit, validation report, and
   final run report for the user.

Phase 4 must **not**:

- re-run Phase 3 retrieval;
- silently repair missing evidence;
- cite normalized plans, derived condensates, planning diagnostics, or context
  artifacts as source evidence;
- run Phase 2 planner repair;
- create generic fallback evidence for no-signal sections;
- launder stale, forced, or failed Phase 3 artifacts into final prose.

If required evidence is missing, invalid, stale, or non-citeable, Phase 4 fails
closed and points back to the upstream phase that owns the fix.

## Inputs

A future Phase 4 command should accept a single bundle root and provider config.
For example, this spec assumes a bundle layout like the accepted run:

```text
$BUNDLE/
  plans/
    document-plan.json
    section-plans.jsonl
    phase3-readiness-report.md
    normalization-report.md
  evidence/
    evidence-packets.jsonl
    packets/<section_id>.json
    retrieval-validation.json
    retrieval-report.md
    evidence-manifest.json
  derived/
    planning-*.md
    repo-summary.md
  rag/ symbols/ static/ contracts/ tests/ inventory/ queries/
  run-metadata.json
  EXPERIMENT_RESULT.md or equivalent external acceptance report, when present
```

Required Phase 4 inputs:

1. **Document plan** — `plans/document-plan.json`.
   - Provides document title, section order, section titles, and high-level plan
     metadata.
2. **Section plans** — `plans/section-plans.jsonl`.
   - Provides one normalized work order per section.
3. **Evidence packets** — `evidence/evidence-packets.jsonl` and/or
   `evidence/packets/<section_id>.json`.
   - Provides the only citeable source evidence for final prose.
4. **Retrieval validation** — `evidence/retrieval-validation.json`.
   - Must show Phase 3 `status: pass` and all required contract checks passing.
5. **Readiness report** — `plans/phase3-readiness-report.md`.
   - Must show `Status: PASS` and `Failures: 0`.
6. **Context artifacts and provenance** — `context_artifacts[]` in section work
   orders, `normalization-report.md`, `retrieval-report.md`, `evidence-manifest.json`,
   `run-metadata.json`, and optional command manifest / acceptance report.
   - These may inform structure, audit, and validation, but context artifacts are
     not citeable source evidence.
7. **Provider config** — one of the two model/provider modes in this spec.
   - Gemini Gem / direct Gemini mode: a browser Gemini Gem prompt/response
     exchange, with optional direct API-key automation via `google-genai` +
     `GEMINI_API_KEY`.
   - Vertex AI mode using `google-genai` + Vertex environment variables.

Optional Phase 4 inputs:

- Output directory, defaulting to `$BUNDLE/wiki/`.
- Style profile, defaulting to `deepwiki`.
- Section length hints, defaulting to model-safe per-section budgets.
- Audit mode, defaulting to raw prompt/response audit enabled.

## Preconditions and gates

Phase 4 must run all gates before model invocation. A failed gate is a hard stop.

### Gate 1 — readiness PASS

- `plans/phase3-readiness-report.md` exists and parses.
- Status is exactly `PASS`.
- Failures are exactly `0`.
- Diagnostic-only normal sections, unresolved no-signal sections, malformed
  section rows, or readiness `FAIL` entries are not allowed.

### Gate 2 — retrieval validation PASS

- `evidence/retrieval-validation.json` exists and validates against the Phase 3
  retrieval validation schema.
- `status` is `pass`.
- `failure_category` is `null`.
- `sections_expected == sections_processed == packets_written`.
- All required contract checks are present and pass, including:
  - all sections have packets;
  - document plan valid;
  - section plans valid JSONL;
  - section plans cover section order;
  - capabilities consistent;
  - packets schema valid;
  - evidence anchors resolve;
  - no plan-only evidence;
  - no context-artifact evidence.

### Gate 3 — no forced or stale provenance

- Phase 3 must not have been produced with `--force` after readiness `FAIL`.
- If a command manifest/transcript is present, it must contain no Phase 3
  `--force` invocation.
- If force provenance is unavailable, Phase 4 must fail closed unless the bundle
  carries another explicit no-force acceptance signal.
- Evidence packet `source_plan.section_plan_sha256` must match the current
  `plans/section-plans.jsonl` content.
- Packet section IDs, order, and counts must match `document-plan.json`.
- Output must come from one coherent bundle, not copied artifacts from different
  runs.

### Gate 4 — source-evidence hygiene

- No `evidence[].source.artifact` or `evidence[].source.path` may point to
  `plans/*`, `derived/*`, planner responses, readiness reports, or final wiki
  outputs.
- `context_artifacts[]` may be preserved in writing packets for orientation only,
  but they must be marked non-citeable and cannot appear in citation manifests as
  evidence.
- Controlled provenance/meta sections, if ever present, must remain separate from
  normal source-evidence sections.
- `known-gaps`, `planning-gaps`, or equivalent diagnostic material must not become
  normal source-evidence content.

### Gate 5 — all section packets present

For every section in `document-plan.json.section_order`:

- one and only one `EvidencePacket` exists;
- packet `section_id`, `title`, and `order` match the plan;
- packet `validation.status` is `pass`;
- packet evidence IDs are unique;
- packet evidence source anchors resolve.

## Outputs

Phase 4 should write all outputs under `$BUNDLE/wiki/` by default.

```text
$BUNDLE/wiki/
  index.md
  sections/
    001-overview.md
    002-architecture.md
    ...
  metadata/
    generated-sections.jsonl
    generated-document.json
    citation-manifest.json
  audit/
    prompts/<section_id>.md
    responses/<section_id>.raw.txt
    responses/<section_id>.parsed.json
    rewrites/<section_id>-attempt-<n>/...
  validation/
    writing-validation.json
    writing-validation-report.md
  PHASE4_RUN_REPORT.md
```

Required outputs:

1. **Generated section Markdown** — one file per section.
2. **Assembled wiki/index** — `wiki/index.md`, with title, navigation, section
   content, and optional citation appendix.
3. **Citation manifest** — machine-readable mapping from every used citation to
   its `EvidencePacket` evidence item and source anchor.
4. **Writing prompts/responses audit** — raw prompt, raw response, parsed response,
   provider config, finish reason, token counts when available, and rewrite audit
   if a bounded rewrite was used.
5. **Validation report JSON/MD** — machine-readable and human-readable final
   validation status.
6. **Final run report inputs to user** — bundle path, provider mode/model,
   upstream gate status, output paths, validation status, evidence/citation
   counts, warnings, and failure paths when applicable.

No successful Phase 4 run may omit the citation manifest or raw prompt/response
audit.

## GeneratedSection artifact

Each generated section should have Markdown plus a metadata record in
`metadata/generated-sections.jsonl`.

Minimum metadata shape:

```json
{
  "schema_version": "phase4-generated-section-v1",
  "section_id": "api-agents",
  "title": "Agents API",
  "order": 6,
  "markdown_path": "wiki/sections/006-api-agents.md",
  "source_packet_path": "evidence/packets/api-agents.json",
  "source_packet_sha256": "sha256:...",
  "evidence_ids_available": ["ev:api-agents:0001"],
  "evidence_ids_used": ["ev:api-agents:0001"],
  "context_artifacts_consulted": [
    {"path": "derived/planning-runtime-surfaces.md", "citeable_as_evidence": false}
  ],
  "generation": {
    "provider_mode": "vertex-ai",
    "model": "gemini-2.5-pro",
    "temperature": 0.1,
    "max_output_tokens": 32768,
    "prompt_path": "wiki/audit/prompts/api-agents.md",
    "response_path": "wiki/audit/responses/api-agents.raw.txt",
    "finish_reason": "STOP"
  },
  "validation": {
    "status": "pass",
    "citations_total": 18,
    "unresolved_citations": [],
    "context_artifact_citations": [],
    "unsupported_claims": [],
    "placeholders": []
  }
}
```

The Markdown file should contain only final reader-facing content plus inline
citations. Implementation metadata belongs in sidecar artifacts, not in prose.

## GeneratedDocument artifact

The assembled document should have a metadata record in
`metadata/generated-document.json`.

Minimum shape:

```json
{
  "schema_version": "phase4-generated-document-v1",
  "bundle_root": "/abs/path/to/bundle",
  "document_path": "wiki/index.md",
  "section_order": ["overview", "architecture"],
  "section_paths": ["wiki/sections/001-overview.md", "wiki/sections/002-architecture.md"],
  "citation_manifest_path": "wiki/metadata/citation-manifest.json",
  "validation_path": "wiki/validation/writing-validation.json",
  "provider_mode": "gemini-gem|direct-gemini-api|vertex-ai",
  "model": "gemini-2.5-pro",
  "status": "pass"
}
```

## GeneratedSection and GeneratedDocument quality bar

The output should read like a DeepWiki page: explanatory, structured, and useful
to an engineer trying to understand or modify the repository.

Required quality bar:

- **DeepWiki-style prose.** Explain architecture, data flow, APIs, runtime
  behavior, configuration, tests, and deployment in coherent paragraphs with
  focused lists and diagrams only when supported by evidence.
- **Grounded claims only.** Every factual repo-specific, code-specific,
  API-specific, configuration-specific, runtime-specific, test-specific, or
  deployment-specific claim must be source-backed.
- **EvidencePacket citations only.** Inline citations must resolve to
  `evidence[].evidence_id` values from the relevant Phase 3 EvidencePacket.
- **Context artifacts are non-citeable.** `context_artifacts[]` may guide section
  structure or remind the writer of planner intent, but they cannot support a
  final claim and cannot appear as citations.
- **No unsupported material.** No invented files, modules, APIs, endpoints,
  environment variables, commands, dependencies, version claims, performance
  claims, security claims, or runtime behavior.
- **No placeholders.** No `TODO`, `TBD`, `FIXME`, "needs citation", "add more
  detail", empty headings, or model apologies.
- **No diagnostic laundering.** `known-gaps` / `planning-gaps` diagnostics are
  not normal source-evidence content. If limitations are discussed, they must be
  backed by real source evidence or represented only as clearly separated
  provenance/audit metadata.
- **No citation dumping.** Citations should attach to the claims they support, not
  appear as an unrelated bibliography replacing claim-level grounding.

## Citation rules and claim discipline

### Citation syntax

Use inline evidence-ID citations with this exact parsable syntax:

```text
[ev:<section_id>:<four_digit_ordinal>]
```

Examples:

```markdown
The agent APIs include endpoints for listing and creating agents [ev:api-agents:0003][ev:api-agents:0004].
```

Rules:

- The cited string must exactly match an `EvidencePacket.evidence[].evidence_id`.
- Multiple citations are written as adjacent brackets, sorted by evidence ID when
  order does not matter.
- Citations resolve through `citation-manifest.json`; path-only, URL-only,
  footnote-only, or plan-file citations are invalid.
- A section should normally cite evidence from its own packet. Cross-section
  evidence may be allowed only if the citation manifest records the source packet
  and the cited evidence belongs to the same validated bundle.

### Claims that require citation

Cite every repo-specific claim about:

- project purpose, features, or supported workflows;
- architecture, subsystem boundaries, and data/control flow;
- concrete file paths, modules, packages, classes, functions, methods, symbols,
  route handlers, model names, schemas, or data stores;
- HTTP methods, API paths, request/response behavior, auth behavior, or OpenAPI
  operations;
- CLI commands, scripts, configuration files, environment variables, defaults, or
  deployment/runtime requirements;
- database, queue, cache, storage, parser, embedding, LLM, or external service
  integration behavior;
- tests, fixtures, test coverage claims, or validation behavior;
- limitations, gaps, deprecations, version support, security boundaries,
  performance, scaling, or operational caveats.

Claims that do not require citation:

- section headings;
- short transition sentences that make no repo-specific factual claim;
- generic definitions that are explicitly framed as background, not claims about
  the repository.

### Multi-source claims

A claim that combines facts from multiple files, symbols, routes, or tests must
cite each source needed to support the combined statement. Examples:

- An endpoint-to-handler claim cites both the contract operation and handler span.
- A data-flow claim spanning an API route, service method, and storage model cites
  each piece.
- A test-backed behavior claim cites source behavior and the test evidence.

### Confidence discipline

- `exact` and `high` evidence may support definitive claims when the excerpt and
  source anchor actually contain the fact.
- `medium` evidence may support claims phrased with appropriate specificity, but
  should not be the sole basis for precise API/config/runtime claims unless the
  excerpt itself is explicit.
- `low` evidence must never be the sole support for a definitive factual claim;
  it may only motivate cautious graph-context language when paired with stronger
  evidence.

### No invented paths or APIs

The writer must not introduce an identifier unless it appears in:

- the cited evidence excerpt;
- cited evidence source metadata (`source.path`, `symbol_id`, `span_id`,
  `chunk_id`, route operation metadata, etc.); or
- another cited source anchor in the same claim.

If the evidence packet does not contain enough evidence for a desired fact, omit
that fact and fail validation if the section cannot meet its required topics.

## Writing packet construction

For each section, Phase 4 should build a compact `WritingPacket` from validated
artifacts. The model should never receive the entire raw bundle by default.

Minimum `WritingPacket` content:

- document title and section order context;
- current section title, purpose, required topics, and expected evidence types;
- section plan retrieval needs and search hints for orientation only;
- `context_artifacts[]` names with `citeable_as_evidence: false` warnings;
- a deduplicated evidence table containing:
  - `evidence_id`;
  - lane/type/confidence;
  - source artifact/path/range/symbol/route metadata;
  - excerpt;
  - provenance field;
  - any lane score/rank useful for prioritization;
- citation syntax and claim discipline instructions;
- output schema instructions.

The packet must preserve enough source text for the model to write accurately,
but it should not include raw derived planning docs as citeable evidence.

## Model output contract

The preferred model response contract is strict JSON, not free-form Markdown, so
Phase 4 can validate and write artifacts deterministically.

Minimum response shape:

```json
{
  "schema_version": "phase4-section-draft-v1",
  "section_id": "api-agents",
  "title": "Agents API",
  "markdown": "## Agents API\n... [ev:api-agents:0001]",
  "used_evidence_ids": ["ev:api-agents:0001"],
  "self_check": {
    "no_uncited_repo_claims": true,
    "no_context_artifact_citations": true,
    "no_placeholders": true
  }
}
```

Malformed JSON, a wrong `section_id`, missing Markdown, unresolved citations, or
provider truncation are validation failures. A bounded rewrite may be attempted
only for format or citation syntax violations as described below.

## Algorithm / workflow

### 1. Validate inputs

- Resolve `$BUNDLE` to an absolute path.
- Load `document-plan.json`, `section-plans.jsonl`, readiness report,
  retrieval-validation, evidence manifest, and packets.
- Run all precondition gates.
- Build a canonical `EvidenceIndex` keyed by `evidence_id`.
- Compute SHA-256 hashes for plans, packets, provider config, prompts, and final
  outputs for audit.

### 2. Build per-section writing packets

For each section in document order:

- join the `DocumentPlan` row, `SectionPlan`, and matching `EvidencePacket`;
- compact evidence into a model-safe table without changing evidence IDs;
- mark context artifacts as non-citeable;
- include section-specific citation and quality instructions;
- write the exact prompt to `wiki/audit/prompts/<section_id>.md` before the model
  call.

### 3. Generate sections

- Call the configured provider once per section or with a full-plan batch only if
  the provider token budget is adequate.
- Use low temperature, default `0.1`.
- Use `max_output_tokens >= 32768` for `gemini-2.5-pro` full-plan or full-section
  synthesis; do not use `8192` for these calls because the fresh run showed it
  can truncate `gemini-2.5-pro` outputs.
- Save raw provider response and parsed draft before validation.
- Treat provider `MAX_TOKENS`, truncation, safety block, empty response, or
  schema mismatch as failure unless one bounded format/citation rewrite is
  allowed and succeeds.

### 4. Validate citations and claims

For each draft:

- parse all citation tokens;
- reject citations that do not resolve to `EvidenceIndex`;
- reject citations to context artifacts, `derived/*`, `plans/*`, or generated wiki
  artifacts;
- reject citations whose evidence packet is missing or from a different bundle;
- reject Markdown with placeholders, TODOs, empty headings, apologies, or hidden
  prompt/audit text;
- reject repo-specific identifiers, paths, endpoints, env vars, or symbol names
  that are not present in the cited evidence excerpts or source metadata;
- reject uncited factual sentences according to the citation rules;
- reject unsupported or over-specific claims that cite only low-confidence graph
  context.

The validator is expected to catch deterministic support violations and obvious
unsupported claims. It is not a license for the model to invent facts that merely
look plausible.

### 5. Optional bounded rewrite for citation/format violations only

A future implementation may allow at most one or two audited rewrite attempts per
section, with a hard cap of two.

Allowed rewrite reasons:

- response was valid content but malformed JSON;
- citation syntax was malformed but evidence IDs are recognizable;
- a factual sentence omitted a citation even though the needed evidence is
  already in the packet;
- Markdown formatting violates the required section shape.

Disallowed rewrite reasons:

- missing Phase 3 evidence;
- readiness or retrieval validation failure;
- stale or forced bundle;
- context artifact cited as evidence;
- invented API/path/symbol not supported by packet evidence;
- request to retrieve more evidence or repair the plan.

Every rewrite attempt must use the same `WritingPacket`, must not add evidence,
and must be saved under `wiki/audit/rewrites/`. If the final attempt fails,
Phase 4 fails closed.

### 6. Assemble the document

- Write each validated section to `wiki/sections/` with stable numeric prefixes.
- Build `wiki/index.md` in document order.
- Add a table of contents and optional source appendix generated from the citation
  manifest.
- Keep raw audit metadata out of reader-facing prose.

### 7. Validate final document

Run final validation after assembly:

- every planned section has exactly one generated section file;
- assembled document contains all sections in order;
- every citation in every section resolves through `citation-manifest.json`;
- every citation in the manifest is used by at least one output file;
- no citation resolves to context artifacts, derived docs, plans, prompts, or
  generated outputs;
- no placeholders or TODOs remain;
- provider finish reasons indicate non-truncated output;
- validation report and final run report are written.

## Failure modes

Phase 4 should classify failures clearly and stop without publishing a successful
`generated-document.json`.

### Missing or invalid inputs

Examples:

- missing `document-plan.json`, `section-plans.jsonl`, readiness report,
  retrieval validation, evidence manifest, or packets;
- invalid JSON/JSONL;
- duplicate or missing section IDs;
- packet schema failure.

Behavior: fail before model calls; tell the user which upstream artifact is bad.

### Readiness not PASS

Examples:

- readiness report missing;
- `Status: FAIL`;
- failures greater than zero;
- diagnostic-only normal section or malformed planner row present.

Behavior: fail before model calls; fix in Phase 2 readiness/repair, not Phase 4.

### Retrieval validation not PASS

Examples:

- `status` not `pass`;
- non-null `failure_category`;
- packets missing;
- evidence anchors unresolved;
- plan-only or context-artifact evidence detected.

Behavior: fail before model calls; fix Phase 3 inputs or rerun all-section Phase 3
without `--force` after readiness passes.

### Citation unresolved

Examples:

- output contains `[ev:api-agents:9999]` not in the packet;
- citation from another bundle;
- malformed evidence ID.

Behavior: bounded citation/format rewrite may run; otherwise fail.

### Unsupported claims

Examples:

- output names a file, endpoint, CLI command, env var, class, function, or runtime
  behavior absent from cited evidence;
- output makes a precise API/config/security/deployment claim using only low
  confidence graph context;
- output uses generic knowledge to fill a repo-specific gap.

Behavior: fail. Do not retrieve more evidence or silently repair.

### Context artifact cited

Examples:

- output cites `derived/planning-digest.md`, `derived/planning-gaps.md`,
  `plans/document-plan.json`, or a planner response;
- citation manifest maps an output claim to `context_artifacts[]`.

Behavior: fail. Context artifacts may inform only, never support source claims.

### Malformed model output

Examples:

- invalid JSON response;
- wrong `section_id`;
- missing `markdown`;
- response contains prompt instructions or self-analysis;
- empty output.

Behavior: bounded format rewrite may run if the raw response is not truncated and
contains usable section content; otherwise fail.

### Provider failure

Examples:

- credentials missing;
- quota/rate limit;
- safety block;
- network error;
- unsupported model/provider config.

Behavior: fail with provider mode, model, and safe error details in the audit.

### Token truncation

Examples:

- finish reason `MAX_TOKENS`;
- JSON closes incorrectly after a long response;
- response lacks required trailer/self-check;
- output is cut mid-section.

Behavior: fail and recommend increasing `max_output_tokens`. For
`gemini-2.5-pro`, use at least `32768` for full-plan or full-section synthesis;
`8192` is not adequate for this workload based on the fresh Phase 1-3 run.

### Stale bundle or mixed artifacts

Examples:

- packet `section_plan_sha256` does not match current section plans;
- readiness report and evidence packets disagree on section count/order;
- artifacts copied from different runs;
- old forced outputs are present.

Behavior: fail; rerun the appropriate upstream phases from a clean bundle.

### Old forced artifacts

Examples:

- command manifest includes Phase 3 `--force`;
- Phase 3 ran after readiness `FAIL`;
- evidence exists for a no-signal diagnostic section due to fallback retrieval.

Behavior: fail; do not generate a user-facing wiki.

## Provider options

Phase 4 must support two user-facing execution options because both are required
for future implementation.

### Option 1 — Gemini Gem / direct Gemini mode

This option covers the non-Vertex Gemini path. The primary compatibility target
is a **Gemini Gem handoff**, matching the manual workflow already used for Phase 2:
Phase 4 writes section-level prompt packets, the operator runs them through the
Gemini Gem, and the tool imports the full raw responses for deterministic parsing,
validation, citation checking, and assembly.

A future implementation may also automate the same prompt/response contract with
direct Gemini API-key authentication (`google-genai` + `GEMINI_API_KEY`). If this
is described as "direct Gemini" or "Gemini API-key mode", clarify that it is **not
Vertex AI**.

Manual Gemini Gem flow, spec only:

```bash
export BUNDLE="/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038"

python -m wiki_generator write-wiki \
  --bundle "$BUNDLE" \
  --provider gemini-gem \
  --prepare-prompts-only \
  --prompt-out "$BUNDLE/wiki/audit/prompts"

# Operator runs each prompt in the configured Gemini Gem, then saves verbatim
# responses under $BUNDLE/wiki/audit/responses/<section_id>.raw.txt.

python -m wiki_generator write-wiki \
  --bundle "$BUNDLE" \
  --provider gemini-gem \
  --responses-in "$BUNDLE/wiki/audit/responses" \
  --validate-and-assemble
```

Direct Gemini API-key variant, spec only:

```bash
export BUNDLE="/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038"
export GEMINI_API_KEY="..."
unset GOOGLE_GENAI_USE_VERTEXAI
# or explicitly:
export GOOGLE_GENAI_USE_VERTEXAI=false

python -m wiki_generator write-wiki \
  --bundle "$BUNDLE" \
  --provider gemini-api \
  --model gemini-2.5-pro \
  --temperature 0.1 \
  --max-output-tokens 32768 \
  --audit-raw
```

Provider requirements:

- Gem mode must audit the exact prompt packet and exact pasted raw response for
  every section;
- direct API mode must use `google-genai` direct API-key authentication and must
  not require `GOOGLE_CLOUD_PROJECT` or `GOOGLE_CLOUD_LOCATION`;
- record provider mode as `gemini-gem` or `direct-gemini-api` in metadata;
- default temperature should be low, e.g. `0.1`;
- default `max_output_tokens` should be at least `32768` for
  `gemini-2.5-pro` full-section synthesis;
- manual Gem responses are never trusted because they came from a browser; they
  must pass the same parser, citation resolver, and unsupported-claim checks as
  automated responses.

### Option 2 — Vertex AI Gemini 2.5 Pro

This mode should match the style already used in Phase 2.

Environment:

```bash
export BUNDLE="/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038"
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="my-gcp-project"
export GOOGLE_CLOUD_LOCATION="us-central1"
gcloud auth application-default login
```

Future CLI example, spec only:

```bash
python -m wiki_generator write-wiki \
  --bundle "$BUNDLE" \
  --provider vertex \
  --model gemini-2.5-pro \
  --temperature 0.1 \
  --max-output-tokens 32768 \
  --audit-raw
```

Provider requirements:

- use `google-genai` with Vertex mode enabled;
- require `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` or equivalent CLI
  flags;
- default model: `gemini-2.5-pro`;
- default temperature should be low, e.g. `0.1`;
- default `max_output_tokens` should be at least `32768` for
  `gemini-2.5-pro` full-section synthesis;
- do not use `8192` as the default for `gemini-2.5-pro` synthesis because the
  accepted fresh run showed `8192` can truncate outputs;
- audit raw prompt and response for every section.

## Validation expectations and tests to implement later

No tests are implemented by this spec. Future implementation should add at least
the following.

### Unit tests for validators

- Readiness parser accepts `Status: PASS / Failures: 0` and rejects missing or
  `FAIL` reports.
- Retrieval validation gate accepts `status: pass` and rejects non-pass status,
  non-null failure category, missing contract checks, or packet count mismatch.
- Section packet loader requires exactly one packet per document-plan section.
- Packet SHA check rejects stale `section-plans.jsonl` / packet mismatches.
- No-force provenance check rejects command manifests containing Phase 3
  `--force`.
- Source hygiene rejects evidence from `derived/*`, `plans/*`, prompts, or wiki
  outputs.
- Citation parser resolves valid `[ev:section:0001]` tokens and rejects malformed
  or unknown IDs.
- Context-artifact citation rejection catches attempts to cite
  `context_artifacts[]`.
- Placeholder detector rejects `TODO`, `TBD`, `FIXME`, empty headings, and model
  apologies.
- Unsupported-claim validator rejects invented paths, endpoints, env vars,
  classes, functions, or API behavior absent from cited evidence.

### Fake provider tests

- Valid fake response produces section Markdown, metadata, citation manifest, and
  final validation `pass`.
- Malformed JSON response triggers a bounded format rewrite if enabled.
- Unresolved citation triggers a bounded citation rewrite if enabled.
- Provider response citing a context artifact is rejected, not rewritten as a
  successful source claim.
- Provider response with an invented path/API is rejected as unsupported.
- Provider response with `MAX_TOKENS` / truncated finish reason fails and records
  token-truncation diagnostics.
- Rewrite cap is enforced at one or two attempts and every attempt is audited.

### Citation resolution tests

- Every citation in section Markdown appears in `citation-manifest.json`.
- Every manifest entry resolves to one EvidencePacket item.
- Multi-source claims with adjacent citations resolve to multiple evidence items.
- Cross-section citations, if allowed, record the source packet and bundle hash.
- Unused citations in the manifest are rejected.

### Context artifact rejection tests

- `derived/planning-digest.md` and `derived/planning-gaps.md` may appear in
  `context_artifacts_consulted` but not in `evidence_ids_used` or manifest source
  evidence.
- A normal generated `known-gaps` section backed only by diagnostics is rejected.
- Controlled provenance/meta content remains separate from normal source-evidence
  sections.

### Provider config tests

- Gemini Gem mode can prepare prompt packets, import verbatim raw responses, and
  validate/assemble without making a provider API call.
- Direct Gemini API variant requires `GEMINI_API_KEY` and does not require Vertex
  project/location.
- Vertex mode requires `GOOGLE_GENAI_USE_VERTEXAI=true`, project, and location.
- All modes record provider mode, model when applicable, temperature when
  applicable, max output tokens when applicable, and raw audit paths.
- `gemini-2.5-pro` defaults to `max_output_tokens >= 32768`.
- `8192` is rejected or warned against for full-plan/full-section synthesis.

### CLI smoke tests

- Future `write-wiki --help` lists Phase 4 as writing/synthesis only.
- Fake-provider smoke run over a tiny valid bundle writes all expected outputs.
- Smoke run fails before provider call when readiness is `FAIL`.
- Smoke run fails before provider call when retrieval validation is not `pass`.
- Smoke run does not invoke Phase 3 retrieval, Phase 2 repair, or any planner
  command.

## Future implementation plan summary

Implementation is future work. A likely sequence:

1. Add Phase 4 artifact schemas and validators.
2. Add provider configuration abstraction for Gemini Gem/import mode, direct
   Gemini API, and Vertex AI.
3. Add writing-packet builder from `DocumentPlan`, `SectionPlan`, and
   `EvidencePacket`.
4. Add strict prompt templates and model response parser.
5. Add citation manifest builder and claim/citation validators.
6. Add bounded rewrite support for format/citation violations only.
7. Add document assembler and final report writer.
8. Add fake-provider unit tests and CLI smoke tests.
9. Update README/RUNBOOK with actual commands only after implementation exists.

This plan must not alter Phase 3. Phase 3 remains deterministic, LLM-free,
all-sections only, with no product `--section` mode, no retry/debug loop, and no
generic fallback rescue for no-signal sections. Bounded/audited planner-artifact
repair remains upstream in Phase 2. Malformed planner output must fail loudly or
be repaired upstream before Phase 3; Phase 4 does not repair plans or evidence.
