# Phase 1 Step 2/3 — Planning Condensates and Planner Digest

## Goal

After the Phase 1 decomposition tool creates the full repo-analysis artifact bundle, create a smaller set of **planner-facing files** that can be uploaded to an LLM planning Gem, such as Gemini, without sending multi-million-token raw indexes.

This document reconciles the two related needs:

1. Keep the full decomposition artifacts for later retrieval.
2. Create compact planning condensates and a final planner brief for Phase 2.

This step does **not** replace the raw decomposition. It summarizes it for planning.

## Clarified structure

```text
Step 2: Decomposition artifacts + planning condensates
Step 3: Final planner-facing digest / upload package
Phase 2: LLM planning -> DocumentPlan + SectionPlans
```

### Step 2

Step 2 is still decomposition. It produces:

- the raw decomposition bundle
- smaller planning condensates derived from the huge symbol/static/query artifacts

Canonical Step 2 planning condensates live under:

```text
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
```

### Step 3

Step 3 creates the final planner brief and upload-ready package.

Canonical Step 3 final brief:

```text
derived/planning-digest.md
```

Optional upload-ready package:

```text
planner-digest/
  README_FOR_PLANNER.md
  planning-digest.md
  planning-symbols.md
  planning-graph.md
  planning-runtime-surfaces.md
  planning-tests.md
  planning-gaps.md
  upload-list.md
```

The files in `planner-digest/` may be copies of the canonical `derived/` files plus the README/upload list. The important contract is that the planning LLM receives the condensed files, not the raw multi-million-token indexes.

## Why this split exists

In the RAGFlow test decomposition, these files were too large for direct upload:

```text
static/edges.jsonl       ~5.5M tokens
symbols/symbols.jsonl    ~2.5M tokens
static/nodes.jsonl       ~2.2M tokens
everything else          ~155K tokens
```

The planner does not need the raw graph or full symbol table. It needs compact summaries of the important structure:

- top modules by symbol count
- top files by graph degree
- top import clusters
- route summary
- worker summary
- CLI summary
- model/schema summary
- config/env summary
- test area summary
- most central functions/classes
- unresolved/dynamic areas

## Implementation location

Implemented in the **same Python package** as Step 1 — the `wiki_generator`
package under `src/` (`src/wiki_generator/`). Step 2/3 consumes the exact artifact
formats Step 1 produces, so it reuses the same package, paths, JSONL utilities,
artifact conventions, and tests rather than forking a separate codebase.

Code shape (as implemented):

```text
src/wiki_generator/
  cli.py                             # decompose/condense/digest/bundle/plan/normalize-plan
  libs/
    commands/                        # command bodies (condense.py, digest.py, bundle.py, …)
    digest/
      loader.py                      # read the Step 1 artifact bundle
      planning_symbols.py            # Step 2: derived/planning-symbols.md
      planning_graph.py              # Step 2: derived/planning-graph.md
      planning_runtime_surfaces.py   # Step 2: derived/planning-runtime-surfaces.md
      planning_tests.py              # Step 2: derived/planning-tests.md
      planning_gaps.py               # Step 2: derived/planning-gaps.md
      planning_digest.py             # Step 3: derived/planning-digest.md
      upload_package.py              # Step 4: planner-digest/* + upload-list.md + bundle
```

## Command shape

Step 2 and Step 3 can be exposed as separate commands:

```bash
python -m wiki_generator condense \
  --in /path/to/phase1-output \
  --budget-tokens 250000

python -m wiki_generator digest \
  --in /path/to/phase1-output \
  --out /path/to/phase1-output/planner-digest \
  --budget-tokens 250000
```

Or `digest` can run both steps in sequence if the Step 2 condensates are missing.

The commands consume an existing decomposition folder and write planner-facing outputs.

Implementation note: the command can write canonical files into `/path/to/phase1-output/derived/` and then copy them into `/path/to/phase1-output/planner-digest/` for upload convenience.

## Step 2 — Raw decomposition artifacts

These remain the canonical backend decomposition/retrieval artifacts. They are not all meant to be uploaded to the planner.

```text
ARTIFACT_GUIDE.md
inventory/files.jsonl
inventory/git-tracked-files.txt
inventory/source-coverage.json
symbols/symbols.jsonl
symbols/imports.jsonl
symbols/occurrences.jsonl
symbols/tags
symbols/tags.jsonl
rag/spans.jsonl
rag/chunks.jsonl
rag/bm25.sqlite
rag/rg-results.jsonl
rag/vectors.faiss
rag/vector-metadata.json
static/nodes.jsonl
static/edges.jsonl
queries/rules/rg/*.json
queries/results/rg.jsonl
queries/results/grep-ast/*.md
queries/results/semgrep.json
queries/results/semgrep.sarif
queries/results/ast-grep.json
contracts/openapi.json
contracts/contract-sources.md
tests/pytest-collect.txt
tests/test-files.jsonl
derived/repo-summary.md
derived/artifact-index.md
```

## Step 2 — Planning condensates

These are condensed markdown summaries derived from the raw artifacts, especially because `symbols/` and `static/` are too large to upload directly.

Step 2 should create:

```text
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
```

### `derived/planning-symbols.md`

Purpose: condensed symbol summary replacing full `symbols/symbols.jsonl` for planning.

Condenses:

```text
symbols/symbols.jsonl
symbols/imports.jsonl
symbols/occurrences.jsonl
symbols/tags
symbols/tags.jsonl
```

Should include:

- symbol counts by kind
- top modules by symbol count
- top files by class/function/method count
- largest classes
- most decorated functions/classes
- route handler symbols
- worker/task symbols
- CLI command symbols
- model/schema symbols
- config/settings symbols
- top imports by frequency
- external dependency imports
- parse errors
- representative examples with file/line anchors

Do not include every symbol. Include ranked tables and representative examples.

### `derived/planning-graph.md`

Purpose: condensed graph summary replacing full `static/nodes.jsonl` and `static/edges.jsonl` for planning.

Condenses:

```text
static/nodes.jsonl
static/edges.jsonl
```

Should include:

- graph node counts by type
- graph edge counts by type
- top files/modules by total graph degree
- top files/modules by incoming edges
- top files/modules by outgoing edges
- top files by graph degree
- top import hubs
- top approximate call hubs
- top inheritance roots/subclasses
- top decorator clusters
- approximate subsystem/import clusters grouped by path prefix and import relationships
- simple import/path-prefix clusters
- graph limitations
- unresolved/dynamic call warnings

Important: call edges are approximate. Preserve warnings like unresolved dynamic calls.

### `derived/planning-runtime-surfaces.md`

Purpose: summarize framework/query/contract signals that usually become DeepWiki sections.

Condenses:

```text
queries/results/rg.jsonl
queries/results/grep-ast/*.md
contracts/openapi.json
contracts/contract-sources.md
tests/test-files.jsonl
tests/pytest-collect.txt
selected symbol/static summaries
```

Should include:

- web routes summary
- API path/method summary from `contracts/openapi.json` or derived routes
- route summary
- task/worker summary
- worker summary
- CLI summary
- model/schema summary
- env var summary
- config key summary
- config/env summary
- datastore/storage/cache summary
- auth/security summary
- plugin/registry/factory summary
- LLM integration summary
- entrypoint summary
- test area summary

This file replaces the idea of a custom `framework-facts.json`. Framework facts are represented as query results, native contracts, and planner-facing summaries, not a new canonical schema.

### `derived/planning-tests.md`

Purpose: summarize test coverage signals.

Condenses:

```text
tests/pytest-collect.txt
tests/test-files.jsonl
static TESTS_APPROX edges, if useful
```

Should include:

- test file count
- test function count
- top test directories
- test files grouped by likely subsystem
- heavily tested modules if inferable
- pytest collection status
- warnings if pytest was skipped and only static scan was used

### `derived/planning-gaps.md`

Purpose: make uncertainty explicit before the LLM plans the Wiki.

Should include:

- skipped tools: ctags, semgrep, ast-grep, pytest, embeddings, grep-ast, if skipped
- parse errors
- unresolved call count
- missing vectors if embeddings were skipped
- missing OpenAPI specs if contracts are derived
- dynamic import/dispatch limitations
- areas where evidence exists only as approximate query hits
- any warnings emitted by the decomposition command

Example warnings from the RAGFlow run:

```text
symbols: 57531 call sites could not be name-resolved; references are approximate.
vector lane skipped; rag/vectors.faiss not written. BM25 + ripgrep still provide retrieval.
pytest is not importable in this environment; test inventory comes from the static scan only.
```

## Step 3 — Planner-facing digest / brief

Step 3 creates the final compact file the Phase 2 planning LLM should read first.

Step 3 canonical output:

```text
derived/planning-digest.md
```

It should be generated from:

```text
ARTIFACT_GUIDE.md
derived/repo-summary.md
derived/artifact-index.md
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
inventory/source-coverage.json
contracts/contract-sources.md
tests/pytest-collect.txt
```

### `derived/planning-digest.md` contents

Purpose: one compact overview of the repo for planning.

It should include:

- file/category counts
- repo size and language/category coverage
- major directories/packages
- likely product purpose from docs/config/query signals
- main runtime surfaces
- likely major subsystems
- dependency summary
- dependency/deployment/config overview
- docs summary
- deployment/config summary
- what areas look large/important
- what areas are weak or uncertain
- explicit planning warnings
- recommended section-planning considerations

It must include these planning-critical summary points:

- top modules by symbol count
- top files by graph degree
- top import clusters
- route summary
- worker summary
- CLI summary
- model/schema summary
- config/env summary
- test area summary
- most central functions/classes
- unresolved/dynamic areas

This is the first content file the planning LLM should read after `README_FOR_PLANNER.md`.

## Optional upload package

For convenience, Step 3 may also create:

```text
planner-digest/
  README_FOR_PLANNER.md
  planning-digest.md
  planning-symbols.md
  planning-graph.md
  planning-runtime-surfaces.md
  planning-tests.md
  planning-gaps.md
  upload-list.md
  planner-upload-bundle.md     # single-file concatenation of the whole upload set
```

### `planner-digest/planner-upload-bundle.md`

Purpose: let the user (or an automated step) upload **one file** to the planning
Gem instead of ~14. It concatenates the entire recommended upload set — the
`README_FOR_PLANNER.md`, the `planning-*.md` condensates, and the small supporting
artifacts (`ARTIFACT_GUIDE.md`, `derived/repo-summary.md`,
`derived/artifact-index.md`, `inventory/source-coverage.json`,
`contracts/contract-sources.md`, `contracts/openapi.json`,
`tests/pytest-collect.txt`) — into a single markdown file. Each source file is
wrapped in a labeled delimiter block:

```text
================================================================================
FILE: planning-digest.md
================================================================================

<file content>
```

The bundle preserves reading order (README first, then condensates, then extras),
keeps all source anchors, and — like the rest of the package — **excludes** the
raw large indexes (`symbols/`, `static/`, `rag/`). It is produced automatically by
the `digest` command alongside `upload-list.md`.

### `planner-digest/README_FOR_PLANNER.md`

Purpose: tell the planning LLM what it is looking at and what it must produce.

Include:

- repo name/path
- digest generation date
- source decomposition path
- warning that this is a digest, not raw source
- list of digest files
- recommended reading order
- Phase 2 output contract:

```text
plans/document-plan.json
plans/document-plan.md
plans/section-plans.jsonl
```

### `planner-digest/upload-list.md`

Purpose: tell the user exactly what to upload to Gemini/Kimi for Phase 2 planning.

Recommended upload set:

```text
planner-digest/README_FOR_PLANNER.md
planner-digest/planning-digest.md
planner-digest/planning-symbols.md
planner-digest/planning-graph.md
planner-digest/planning-runtime-surfaces.md
planner-digest/planning-tests.md
planner-digest/planning-gaps.md
ARTIFACT_GUIDE.md
derived/repo-summary.md
derived/artifact-index.md
inventory/source-coverage.json
contracts/contract-sources.md
contracts/openapi.json, if present
tests/pytest-collect.txt, if not too large
tests/test-files.jsonl, if not too large
```

Do not upload these raw backend artifacts to the planning Gem:

```text
symbols/symbols.jsonl
static/nodes.jsonl
static/edges.jsonl
rag/chunks.jsonl
rag/spans.jsonl
rag/bm25.sqlite
```

Those remain for Phase 3 retrieval.

## Token budget

Target:

```text
Planning upload <= 250K tokens
```

Suggested allocation:

```text
README_FOR_PLANNER.md                      2K
derived/planning-digest.md                30K-50K
derived/planning-symbols.md               25K-40K
derived/planning-graph.md                 25K-40K
derived/planning-runtime-surfaces.md      35K-60K
derived/planning-tests.md                 10K-15K
derived/planning-gaps.md                  5K-10K
selected existing small files             remaining budget
buffer                                    remaining
```

If the upload exceeds the budget, trim representative examples first, not counts, coverage warnings, or skipped-tool/gap notes.

A conservative token estimate can use roughly four characters per token.

## Implementation notes

### Ranking calculations

The digest command should compute:

- symbol counts by file/module/path prefix
- class/function/method counts by file
- import counts by source and target module
- graph degree counts from `static/edges.jsonl`
- top incoming/outgoing nodes
- top files/modules by total degree
- approximate call hub counts
- route/worker/CLI/model/config counts from query results
- test counts by directory and file
- unresolved/dynamic call counts

### Cluster heuristics

For V1, clusters can be simple and deterministic:

- group by top-level directory
- group by Python package prefix
- group by import target prefix
- group by query-pack category

No graph ML or LLM clustering is required.

### Source anchors

Every representative example should keep file/line anchors where available:

```text
api/apps/sdk_app.py:37-92
rag/nlp/search.py:120-188
```

The planner digest does not need full source text. Phase 3 retrieval will recover exact spans later.

## Acceptance criteria

A successful Step 2/3 run produces canonical derived files:

```text
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
derived/planning-digest.md
```

And, if using the upload package mode:

```text
planner-digest/README_FOR_PLANNER.md
planner-digest/planning-digest.md
planner-digest/planning-symbols.md
planner-digest/planning-graph.md
planner-digest/planning-runtime-surfaces.md
planner-digest/planning-tests.md
planner-digest/planning-gaps.md
planner-digest/upload-list.md
```

Acceptance checks:

- total planner-facing upload is under the configured token budget
- raw large files are not duplicated into the digest/upload package
- major runtime surfaces are represented
- graph and symbol summaries include ranked top items
- test coverage signals are represented
- known gaps and skipped tools are explicit
- representative examples keep source anchors where possible
- `upload-list.md` gives the user a clear Gemini/Kimi upload set

## Relationship to Phase 2

Phase 2 is the first LLM phase.

Input:

```text
Phase 1 Step 2 planning condensates
+ Phase 1 Step 3 planning digest
```

Output:

```text
plans/document-plan.json
plans/document-plan.md
plans/section-plans.jsonl
```

The Phase 2 prompt should ask for:

```text
DocumentPlan
SectionPlans
coverage requirements per section
retrieval needs per section
```

The planning LLM should not write the final Wiki and should not invent evidence. It should decide what the Wiki should contain and what evidence each section will need in the later retrieval phase.
