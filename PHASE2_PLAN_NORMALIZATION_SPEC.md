# Phase 2 Plan Normalization Spec

## Artifact being designed

Phase 2 uses a planning LLM, such as Gemini or Kimi, to produce a `DocumentPlan` and `SectionPlans` from the Phase 1 planner upload bundle.

The LLM output is useful but not safe to feed directly into Phase 3 retrieval. It may contain human labels, loose anchors, dotted symbol names, prose wrappers, or slightly inconsistent JSON.

This spec defines a deterministic **Phase 2 normalization step** that converts the raw LLM planning response into machine-resolvable plan artifacts for Phase 3.

## Pipeline position

```text
Phase 1 Step 1: decompose
Phase 1 Step 2: condense
Phase 1 Step 3: digest
Phase 1 Step 4: bundle

Phase 2 Step 1: LLM planning
  input: planner-digest/planner-upload-bundle.md
  output: plans/phase2-gemini-response.md or equivalent raw provider response

Phase 2 Step 2: normalize plan deterministically
  input: raw LLM response + Phase 1 indexes
  output: normalized DocumentPlan + SectionPlans

Phase 3: deterministic section evidence retrieval
  input: normalized plan artifacts + raw Phase 1 retrieval indexes
```

## Quality bar

The normalized plan is good if:

- every section has a stable machine-readable ID;
- every query pack reference resolves to a canonical query-pack key;
- every symbol reference is either resolved to an exact `symbol_id` or explicitly marked unresolved with candidates;
- every file reference is either verified against `inventory/files.jsonl` or explicitly marked unresolved;
- loose anchors are not silently treated as exact evidence;
- the output is valid JSON/JSONL and deterministic;
- Phase 3 can consume it without asking an LLM to interpret names.

## Non-goals

The normalizer must not:

- call an LLM;
- rewrite the plan's editorial intent;
- invent evidence;
- create final Wiki prose;
- choose different sections unless the raw output is structurally invalid;
- silently guess ambiguous symbols or file paths.

## Command

Canonical command:

```bash
python3 -m phase1_decomposition normalize-plan \
  --bundle /path/to/phase1-output \
  --raw-response /path/to/phase1-output/plans/phase2-gemini-response.md \
  --out /path/to/phase1-output/plans
```

Optional strictness flags:

```bash
--strict                 # fail on unresolved symbols/files/query packs
--allow-unresolved       # default: write unresolved items to report, continue
--provider gemini        # optional metadata only
```

## Inputs

Required Phase 2 input:

```text
plans/phase2-gemini-response.md
```

Required Phase 1 lookup inputs:

```text
inventory/files.jsonl
symbols/symbols.jsonl
symbols/imports.jsonl
static/nodes.jsonl
static/edges.jsonl
queries/rules/rg/*.json
queries/results/rg.jsonl
contracts/openapi.json
contracts/contract-sources.md
tests/test-files.jsonl
derived/planning-digest.md
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
```

The normalizer may not need every lookup file for every repo, but it should load enough indexes to verify references deterministically.

## Outputs

Canonical normalized outputs:

```text
plans/document-plan.json
plans/document-plan.md
plans/section-plans.jsonl
plans/normalization-report.md
plans/unresolved-references.jsonl
```

Optional debug outputs:

```text
plans/raw-extracted-document-plan.json
plans/raw-extracted-section-plans.jsonl
plans/normalization-map.json
```

## Raw response parsing

The normalizer should parse the raw LLM response deterministically.

Accepted raw formats, in priority order:

1. fenced JSON block labeled `document-plan.json` or containing a top-level `DocumentPlan` object;
2. fenced JSONL block labeled `section-plans.jsonl`;
3. fenced JSON block containing an array of section plans;
4. provider response markdown with clearly marked `DocumentPlan` and `SectionPlans` headings.

If multiple plausible blocks exist, fail with a clear error instead of guessing.

If JSON has minor recoverable issues, the normalizer may apply deterministic repairs only if they are simple and logged, for example:

- remove markdown code fences;
- trim leading/trailing prose outside the fenced block;
- normalize smart quotes only in JSON keys if necessary.

Do not use fuzzy LLM-style repair.

## Normalized `DocumentPlan` schema

Minimum required shape:

```json
{
  "schema_version": "phase2-plan-v1",
  "repo": {
    "name": "string",
    "root": "string"
  },
  "title": "string",
  "purpose": "string",
  "audience": "string",
  "section_order": ["section-id"],
  "coverage_goals": ["string"],
  "known_gaps": ["string"],
  "source_raw_response": "plans/phase2-gemini-response.md",
  "normalization": {
    "generated_by": "phase1_decomposition normalize-plan",
    "unresolved_count": 0,
    "warnings": []
  }
}
```

## Normalized `SectionPlan` JSONL schema

Each line in `plans/section-plans.jsonl` must be one object:

```json
{
  "schema_version": "phase2-section-plan-v1",
  "section_id": "rag-pipeline-and-tasks",
  "title": "RAG Pipeline and Task Execution",
  "order": 5,
  "purpose": "What this section should explain.",
  "required_topics": ["string"],
  "retrieval_needs": {
    "query_packs": ["web_routes", "task_workers"],
    "symbols": [
      {
        "input": "rag.llm.chat_model.LiteLLMBase",
        "symbol_id": "python rag.llm.chat_model/LiteLLMBase#",
        "resolution": "exact",
        "candidates": []
      }
    ],
    "files": [
      {
        "input": "api/apps/sdk_app.py",
        "path": "api/apps/sdk_app.py",
        "anchor": null,
        "resolution": "file_exists"
      }
    ],
    "contracts": ["contracts/openapi.json"],
    "tests": []
  },
  "expected_evidence_types": ["symbols", "routes", "chunks", "tests"],
  "known_gaps": ["string"],
  "normalization_warnings": []
}
```

## Deterministic normalization rules

### Section IDs

If the LLM provides a stable ID, keep it after validation.

Otherwise derive it from the title:

```text
lowercase -> replace non-alphanumeric runs with '-' -> trim '-' -> ensure unique with -2, -3 suffixes
```

Section order must follow the raw plan order.

### Query-pack names

Canonical query-pack keys come from:

```text
queries/rules/rg/*.json name field
```

Normalization algorithm:

1. exact match against canonical `name`;
2. exact match against filename stem;
3. casefold + replace spaces/hyphens with underscores;
4. match known aliases built from the rule `why` text and common display names.

Known aliases should include at least:

```text
Web routes -> web_routes
Routes -> web_routes
API routes -> web_routes
Task workers -> task_workers
Workers -> task_workers
CLI -> cli_commands
CLI commands -> cli_commands
Models -> models_schemas
Schemas -> models_schemas
Model/schema -> models_schemas
Config -> config_keys
Env -> env_vars
Environment variables -> env_vars
Auth -> auth_security
Security -> auth_security
Datastore -> datastore
LLM integrations -> llm_integrations
Entry points -> entrypoints
Plugins -> plugin_registries
Registries -> plugin_registries
```

If a query-pack reference cannot be resolved, write it to `unresolved-references.jsonl` and add a section warning.

### Symbol references

Canonical symbol IDs come from:

```text
symbols/symbols.jsonl symbol_id field
```

Build deterministic lookup aliases for each symbol:

- exact `symbol_id`;
- `name` when globally unique;
- dotted module + symbol name;
- dotted module + class name;
- dotted module + class name + method name;
- `path:name`;
- `path:line` if line range is available.

Resolution rules:

1. exact `symbol_id` -> `exact`;
2. unique alias -> `unique_alias`;
3. multiple candidates -> unresolved with sorted candidate list;
4. no candidate -> unresolved.

Never choose among multiple candidates silently.

### File references and anchors

Canonical file paths come from:

```text
inventory/files.jsonl path field
```

Resolution rules:

1. exact path match -> `file_exists`;
2. unique suffix match -> `unique_suffix`;
3. multiple suffix matches -> unresolved with candidates;
4. no match -> unresolved.

If the LLM gives a line anchor, verify that the line range is valid for that file when line counts are available.

Anchor confidence values:

```text
exact_range       # valid start/end lines
line_only         # one valid line
file_only         # file exists but no valid lines
unresolved        # file not resolved
```

Loose anchors must be preserved as planning hints, not treated as final evidence.

### Contract/API references

Use `contracts/openapi.json` and `contracts/contract-sources.md`.

Normalize API references to:

```text
METHOD /path
```

If the plan names only a path and multiple methods exist, preserve the path and list candidate methods.

### Tests

Use `tests/test-files.jsonl` and, if present, `tests/pytest-collect.txt`.

Normalize test references as file paths. If only a subsystem is named, preserve it as a test search hint, not an exact test file.

## `normalization-report.md`

Must include:

- raw response path;
- output paths;
- number of sections;
- query-pack resolutions count;
- symbol resolutions count;
- file resolutions count;
- unresolved count by type;
- warnings;
- whether strict mode passed or failed;
- notes for Phase 3 retrieval.

## `unresolved-references.jsonl`

Each unresolved reference should include:

```json
{
  "section_id": "string",
  "type": "symbol|file|query_pack|contract|test",
  "input": "original LLM text",
  "reason": "no_match|ambiguous|invalid_range",
  "candidates": []
}
```

## Implementation notes for the coding agent

Recommended package shape:

```text
phase1_decomposition/
  core/cli.py                         # add normalize-plan subcommand
  libs/commands/normalize_plan.py     # command wrapper
  libs/plan_normalization/
    __init__.py
    parse_response.py
    schema.py
    query_packs.py
    symbols.py
    files.py
    contracts.py
    tests.py
    writer.py
```

Use only deterministic local reads/writes. No network calls. No LLM calls.

## Tests to require

Unit tests should cover:

- extracting DocumentPlan and SectionPlans from fenced markdown;
- rejecting ambiguous multiple JSON blocks;
- slugifying section IDs deterministically;
- mapping human query-pack names to canonical keys;
- resolving exact and alias symbol references;
- leaving ambiguous symbols unresolved with candidates;
- resolving exact and suffix file paths;
- preserving loose anchors as non-final evidence hints;
- writing valid `document-plan.json` and `section-plans.jsonl`;
- writing unresolved references and normalization report;
- strict mode fails when unresolved references exist.

## Acceptance criteria

A successful normalization run:

- reads the raw Gemini/Kimi response;
- writes valid `plans/document-plan.json`;
- writes readable `plans/document-plan.md`;
- writes valid JSONL `plans/section-plans.jsonl`;
- maps human query-pack titles to canonical keys;
- resolves unique symbol/file references deterministically;
- never silently guesses ambiguous references;
- writes all unresolved references to `plans/unresolved-references.jsonl`;
- writes a concise `plans/normalization-report.md`;
- produces outputs that Phase 3 retrieval can consume without another LLM call.
