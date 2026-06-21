# Phase 1 Step 4 — Planner Upload Bundle Spec

## Artifact being designed

Phase 1 Step 4 creates a **single uploadable planner bundle** from the Step 2 planning condensates and the Step 3 planning digest.

This is still Phase 1. It is deterministic and LLM-free. It does not summarize, reinterpret, or normalize the repo. It only packages already-generated planner-facing files into a safe, ordered upload set for Gemini/Kimi.

## Pipeline position

```text
Phase 1 Step 1: decompose
  -> raw deterministic repo-analysis artifact bundle

Phase 1 Step 2: condense
  -> derived/planning-symbols.md
  -> derived/planning-graph.md
  -> derived/planning-runtime-surfaces.md
  -> derived/planning-tests.md
  -> derived/planning-gaps.md

Phase 1 Step 3: digest
  -> derived/planning-digest.md

Phase 1 Step 4: bundle
  -> planner-digest/README_FOR_PLANNER.md
  -> planner-digest/upload-list.md
  -> planner-digest/planner-upload-bundle.md
  -> planner-digest/planning-*.md copies

Phase 2: LLM planning
  -> plans/phase2-gemini-response.md or provider raw response

Phase 2 normalization: deterministic post-LLM cleanup
  -> plans/document-plan.json
  -> plans/document-plan.md
  -> plans/section-plans.jsonl
```

## Quality bar

The Step 4 artifact is good if:

- it lets the user upload **one file** to Gemini/Kimi instead of many separate files;
- it stays under the configured planning upload budget, default `250000` estimated tokens;
- it preserves the exact content of the included Step 2/3 files, with deterministic boundaries;
- it explicitly excludes raw backend retrieval/index artifacts;
- it gives the planning LLM clear instructions about what the files mean and what Phase 2 must produce;
- it is reproducible from the same Phase 1 output directory.

## Failure modes

Step 4 fails if:

- it includes raw giant backend files such as `symbols/symbols.jsonl`, `static/edges.jsonl`, or `rag/chunks.jsonl`;
- it rewrites or summarizes Step 2/3 content in a way that drops details;
- it exceeds the configured token budget without failing loudly or writing a clear warning;
- it omits required planning files;
- it gives the planning LLM ambiguous output instructions;
- it uses an LLM or non-deterministic ordering.

## Command

Canonical command:

```bash
python3 -m phase1_decomposition bundle \
  --in /path/to/phase1-output \
  --out /path/to/phase1-output/planner-digest \
  --budget-tokens 250000
```

Allowed compatibility behavior:

- `digest` may call `bundle` automatically when passed a flag like `--bundle`.
- But conceptually and in docs, Step 3 is the digest and Step 4 is the upload bundle.

## Inputs

Required:

```text
ARTIFACT_GUIDE.md
derived/repo-summary.md
derived/artifact-index.md
derived/planning-digest.md
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
inventory/source-coverage.json
contracts/contract-sources.md
```

Optional, include only if present and small enough:

```text
contracts/openapi.json
tests/pytest-collect.txt
tests/test-files.jsonl
```

Never include:

```text
symbols/symbols.jsonl
symbols/imports.jsonl
symbols/occurrences.jsonl
static/nodes.jsonl
static/edges.jsonl
rag/chunks.jsonl
rag/spans.jsonl
rag/bm25.sqlite
rag/vectors.faiss
rag/vector-metadata.json
queries/results/rg.jsonl
```

Those raw files remain for Phase 3 retrieval.

## Outputs

```text
planner-digest/
  README_FOR_PLANNER.md
  upload-list.md
  planner-upload-bundle.md
  planning-digest.md
  planning-symbols.md
  planning-graph.md
  planning-runtime-surfaces.md
  planning-tests.md
  planning-gaps.md
```

The `planning-*.md` files in `planner-digest/` should be byte-identical copies of the canonical files under `derived/`.

## `README_FOR_PLANNER.md`

Purpose: orient the Phase 2 planning LLM.

Must include:

- repo path/name;
- source Phase 1 output path;
- generation timestamp if already used elsewhere, but content ordering must remain deterministic;
- warning that this is a digest, not raw source;
- warning that approximate signals must be treated as approximate;
- list of included files;
- recommended reading order;
- explicit Phase 2 output contract.

Phase 2 output contract:

```text
DocumentPlan
SectionPlan[]
coverage requirements per section
retrieval needs per section
known gaps / uncertainty notes
```

The README must tell the LLM:

- do not write the final Wiki;
- do not invent evidence;
- plan sections and evidence needs only;
- use exact paths/anchors when available;
- flag uncertainty when a signal is approximate.

## `upload-list.md`

Purpose: tell the user and automation exactly what was included/excluded.

Must include:

- included files, in bundle order;
- estimated chars and tokens per included file;
- total estimated upload tokens;
- raw files explicitly excluded;
- budget result: PASS or FAIL.

Token estimate rule:

```text
estimated_tokens = ceil(character_count / 4)
```

This is only a planning budget estimate, not a tokenizer-specific count.

## `planner-upload-bundle.md`

Purpose: the one file the user can upload to Gemini/Kimi.

It must be a concatenation of the upload set, in deterministic order, with clear file boundaries.

Required boundary format:

```markdown
<!-- BEGIN INCLUDED FILE: derived/planning-digest.md -->

<exact file content>

<!-- END INCLUDED FILE: derived/planning-digest.md -->
```

Recommended top-level structure:

```markdown
# Planner Upload Bundle

## What this is
## Planning task
## Included files
## Excluded raw backend artifacts
## Phase 2 required output

<!-- BEGIN INCLUDED FILE: planner-digest/README_FOR_PLANNER.md -->
...
<!-- END INCLUDED FILE: planner-digest/README_FOR_PLANNER.md -->

<!-- BEGIN INCLUDED FILE: derived/planning-digest.md -->
...
<!-- END INCLUDED FILE: derived/planning-digest.md -->
```

Do not alter included file content except normalizing final newline behavior.

## Deterministic ordering

Use this order:

```text
planner-digest/README_FOR_PLANNER.md
derived/planning-digest.md
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
ARTIFACT_GUIDE.md
derived/repo-summary.md
derived/artifact-index.md
inventory/source-coverage.json
contracts/contract-sources.md
contracts/openapi.json, if present and within budget
tests/pytest-collect.txt, if present and within budget
tests/test-files.jsonl, if present and within budget
```

If budget is exceeded, trim optional files first. Never trim:

```text
planner-digest/README_FOR_PLANNER.md
derived/planning-digest.md
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
```

If required files alone exceed the budget, fail loudly and write the reason to `upload-list.md`.

## Implementation notes for the coding agent

Recommended package shape:

```text
phase1_decomposition/
  core/cli.py                 # add bundle subcommand
  libs/commands/bundle.py     # command wrapper
  libs/digest/upload_package.py
  libs/markdown.py            # boundary/header helpers if useful
```

Use only deterministic local file reads/writes. No LLM calls. No network calls.

Recommended implementation functions:

```text
collect_upload_files(phase1_output, budget_tokens) -> list[UploadFile]
write_readme_for_planner(...)
write_upload_list(...)
write_single_file_bundle(...)
copy_planning_files(...)
estimate_tokens(text) -> ceil(len(text) / 4)
```

## Acceptance criteria

A successful Step 4 run:

- creates `planner-digest/README_FOR_PLANNER.md`;
- creates `planner-digest/upload-list.md`;
- creates `planner-digest/planner-upload-bundle.md`;
- copies all `derived/planning-*.md` files into `planner-digest/`;
- keeps the upload bundle under `--budget-tokens`, unless it fails loudly;
- explicitly excludes raw backend indexes;
- preserves deterministic file order and boundary markers;
- passes tests that verify required files, raw exclusions, token budget calculation, and deterministic output.
