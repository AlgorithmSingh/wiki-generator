# Phase 3 — Evidence Retrieval Spec

## Artifact being designed

Phase 3 creates the deterministic **evidence layer** for the Wiki generator.

Target artifact:

```text
phase1-output/
  evidence/
    evidence-manifest.json
    evidence-packets.jsonl
    packets/
      <section_id>.json
    retrieval-validation.json
    retrieval-report.md
    unresolved-evidence.jsonl
```

The core artifact is one **EvidencePacket** per normalized section. Each packet is
machine-readable JSON containing exact, citeable evidence retrieved from the Phase
1 artifact bundle and Step 5 retrieval substrate.

The human-readable companion artifact is `evidence/retrieval-report.md`. It tells
the user whether evidence retrieval satisfied the Phase 3 contract for every
section and, if not, which upstream artifact or implementation path must be fixed.

Phase 3 does **not** write final Wiki prose. It prepares grounded evidence for a
later writing phase.

## Pipeline position

```text
Phase 1 Step 1: decompose
  -> inventory/, symbols/, rag/spans.jsonl, rag/chunks.jsonl, static/,
     queries/, contracts/, tests/

Phase 1 Step 5: build-retrieval
  -> rag/retrieval-capabilities.json
  -> rag/bm25.sqlite
  -> rag/vectors.faiss + rag/vector-metadata.jsonl when hybrid vectors are built

Phase 2 Step 2: normalize-plan
  -> plans/document-plan.json
  -> plans/section-plans.jsonl
  -> plans/normalization-report.md

Phase 3: retrieve-evidence
  -> evidence/packets/<section_id>.json
  -> evidence/evidence-packets.jsonl
  -> evidence/retrieval-report.md
```

Current prerequisites are considered complete when these files exist and validate:

```text
plans/document-plan.json
plans/section-plans.jsonl
plans/normalization-report.md
rag/retrieval-capabilities.json
rag/bm25.sqlite
rag/chunks.jsonl
rag/spans.jsonl
```

If `rag/retrieval-capabilities.json` reports `retrieval_mode: "hybrid"` or
`capabilities.vectors: true`, these are also required:

```text
rag/vectors.faiss
rag/vector-metadata.json or rag/vector-metadata.jsonl
```

## Goal

Given the normalized `DocumentPlan` and all normalized `SectionPlan` rows, Phase 3
retrieves exact evidence for every planned section in one deterministic run.

A successful run answers this question for each section:

> Which exact files, source ranges, symbols, query-pack hits, contracts, tests,
> graph neighbors, BM25 chunks, and optional vector chunks should later Wiki
> writing cite for this section?

## What the normalized plan is used for

The normalized plan is a **retrieval work order**. It is not evidence.

`plans/section-plans.jsonl` tells Phase 3 what to look for:

- stable `section_id`, `title`, `order`, and section intent;
- resolved file anchors and symbol IDs;
- canonical query-pack keys;
- contract and test references;
- graph seed hints;
- topic text for BM25/vector recall.

The plan's prose may explain why a section exists, but it must never be cited as
proof about the target repository. Evidence must come from Phase 1 artifacts and
Step 5 retrieval indexes, such as `rag/spans.jsonl`, `rag/chunks.jsonl`,
`symbols/symbols.jsonl`, `queries/results/rg.jsonl`, `contracts/openapi.json`,
`tests/test-files.jsonl`, `static/edges.jsonl`, `rag/bm25.sqlite`, and vector
metadata when available.

Loose anchors from Phase 2 normalization are retrieval hints only. A loose anchor
must be converted into an exact file range, span, chunk, contract pointer, or test
artifact before it can appear as evidence.

## Determinism and LLM policy

Phase 3 is deterministic and LLM-free.

It must not:

- call an LLM;
- call a network service;
- ask the user to choose among retrieval results;
- use random sampling or nondeterministic tie-breaking;
- write final Wiki prose;
- treat Phase 2 plan text as evidence;
- implement a product workflow where failed sections are manually retried until
  they pass.

All ordering must be stable. Ties are broken by explicit lane priority, score,
`path`, `start_line`, `chunk_id`, `span_id`, and `evidence_id` as applicable.

## Product workflow boundary

A normal Phase 3 run processes **all sections** from
`plans/document-plan.json.section_order` and `plans/section-plans.jsonl`.

There is no product `--section`, `--section-id`, or one-section debugging mode in
this spec. A developer may write unit tests or inspect artifacts manually, but the
Phase 3 command itself is an all-sections artifact producer.

If Phase 3 fails, that failure is not a normal retry loop. The user fixes the
appropriate upstream artifact, normalized plan, or retriever code, then reruns the
same all-section command.

## Command

Canonical command:

```bash
python3 -m wiki_generator retrieve-evidence \
  --bundle /path/to/phase1-output \
  --out /path/to/phase1-output/evidence
```

Equivalent console form:

```bash
wiki-generator retrieve-evidence \
  --bundle /path/to/phase1-output \
  --out /path/to/phase1-output/evidence
```

Recommended deterministic flags:

```text
--bundle PATH                 required Phase 1/2 bundle root
--out PATH                    default: <bundle>/evidence
--max-per-lane N              default: implementation constant, stable across runs
--max-total-per-section N     default: implementation constant, stable across runs
```

Do not add a `--section` flag to the product CLI.

## Inputs

Required normalized plan inputs:

```text
plans/document-plan.json
plans/section-plans.jsonl
plans/normalization-report.md
```

Required retrieval-substrate inputs:

```text
rag/retrieval-capabilities.json
rag/bm25.sqlite
rag/chunks.jsonl
rag/spans.jsonl
```

Required lookup inputs for evidence lanes:

```text
inventory/files.jsonl
symbols/symbols.jsonl
static/nodes.jsonl
static/edges.jsonl
queries/rules/rg/*.json
queries/results/rg.jsonl
contracts/openapi.json
tests/test-files.jsonl
```

Required only when capabilities report vectors enabled:

```text
rag/vectors.faiss
rag/vector-metadata.json or rag/vector-metadata.jsonl
```

Useful optional inputs:

```text
symbols/imports.jsonl
symbols/occurrences.jsonl
rag/rg-results.jsonl
contracts/contract-sources.md
tests/pytest-collect.txt
queries/results/grep-ast/*.md
```

Phase 3 should load optional inputs when present, but absence of an optional input
must not invalidate a run unless the capability contract says that lane is
available and required for retrieval.

## Outputs

Canonical outputs:

```text
evidence/evidence-manifest.json
evidence/evidence-packets.jsonl
evidence/packets/<section_id>.json
evidence/retrieval-validation.json
evidence/retrieval-report.md
evidence/unresolved-evidence.jsonl
```

### `evidence/evidence-manifest.json`

Purpose: machine-readable index of the Phase 3 artifact set.

Minimum shape:

```json
{
  "schema_version": "phase3-evidence-manifest-v1",
  "bundle_root": "/path/to/phase1-output",
  "document_plan": "plans/document-plan.json",
  "section_plans": "plans/section-plans.jsonl",
  "retrieval_capabilities": "rag/retrieval-capabilities.json",
  "retrieval_mode": "hybrid",
  "section_count": 13,
  "packet_count": 13,
  "combined_packets": "evidence/evidence-packets.jsonl",
  "packet_paths": ["evidence/packets/overview.json"],
  "validation": "evidence/retrieval-validation.json",
  "report": "evidence/retrieval-report.md",
  "status": "pass"
}
```

### `evidence/evidence-packets.jsonl`

One line per section, in `DocumentPlan.section_order` order. Each line is the
same object written to `evidence/packets/<section_id>.json`.

### `evidence/unresolved-evidence.jsonl`

Rows describing deterministic retrieval misses that do not become evidence.

Minimum row shape:

```json
{
  "section_id": "rag-pipeline-and-tasks",
  "type": "symbol|file|query_pack|contract|test|graph|bm25|vector",
  "input": "original normalized reference or generated query",
  "reason": "missing_reference|no_hits|ambiguous|invalid_range|capability_disabled",
  "source_field": "retrieval_needs.symbols[0]",
  "candidates": []
}
```

## EvidencePacket schema

Each packet must be valid JSON with this minimum shape:

```json
{
  "schema_version": "phase3-evidence-packet-v1",
  "section_id": "rag-pipeline-and-tasks",
  "title": "RAG Pipeline and Task Execution",
  "order": 5,
  "retrieval_mode": "hybrid",
  "source_plan": {
    "document_plan_path": "plans/document-plan.json",
    "section_plans_path": "plans/section-plans.jsonl",
    "section_plan_sha256": "sha256:..."
  },
  "work_order": {
    "purpose": "What this section should explain.",
    "required_topics": ["string"],
    "expected_evidence_types": ["symbols", "routes", "chunks", "tests"],
    "retrieval_needs": {
      "query_packs": ["web_routes"],
      "symbols": [],
      "files": [],
      "contracts": [],
      "tests": [],
      "graph_nodes": []
    }
  },
  "evidence": [
    {
      "evidence_id": "ev:rag-pipeline-and-tasks:0001",
      "lane": "symbol_anchor",
      "type": "source_span",
      "source": {
        "artifact": "rag/spans.jsonl",
        "path": "src/app/tasks.py",
        "range": {"start_line": 10, "end_line": 48},
        "span_id": "span:src/app/tasks.py:10-48:function",
        "chunk_id": "chunk:src/app/tasks.py:10-48",
        "symbol_id": "python app.tasks/run_task#"
      },
      "excerpt": "deterministically clipped source text",
      "provenance": {
        "section_plan_field": "retrieval_needs.symbols[0]",
        "input": "python app.tasks/run_task#",
        "matched_by": "symbol_id"
      },
      "scores": {
        "lane_rank": 1,
        "lane_score": 1.0,
        "bm25": null,
        "vector": null
      },
      "confidence": "exact",
      "dedupe_key": "src/app/tasks.py:10-48:span:src/app/tasks.py:10-48:function"
    }
  ],
  "lane_summary": {
    "file_anchor": {"requested": 0, "returned": 0, "status": "not_requested"},
    "symbol_anchor": {"requested": 1, "returned": 1, "status": "pass"},
    "query_pack": {"requested": 1, "returned": 4, "status": "pass"},
    "contract": {"requested": 0, "returned": 0, "status": "not_requested"},
    "test": {"requested": 0, "returned": 0, "status": "not_requested"},
    "graph_neighbors": {"requested": 1, "returned": 3, "status": "pass"},
    "bm25": {"requested": 1, "returned": 5, "status": "pass"},
    "vector": {"requested": 1, "returned": 5, "status": "pass"}
  },
  "coverage": {
    "satisfied": ["symbols", "queries", "chunks"],
    "missing": [],
    "warnings": []
  },
  "validation": {
    "status": "pass",
    "errors": [],
    "warnings": []
  }
}
```

### Evidence item rules

Every `evidence[]` item must:

- have a stable `evidence_id` derived from `section_id` and final sorted ordinal;
- name the retrieval `lane` that found it;
- cite a Phase 1 or Step 5 `source.artifact`;
- include a stable source anchor: `path` + `range`, `span_id`, `chunk_id`,
  `symbol_id`, or `json_pointer`, depending on evidence type;
- include an `excerpt` copied from the source artifact, deterministically clipped;
- include `provenance.section_plan_field` when the item traces to an explicit
  SectionPlan field;
- include deterministic score/rank metadata when produced by ranked retrieval;
- never use normalized plan prose as the evidence excerpt.

Allowed `lane` values:

```text
file_anchor
symbol_anchor
query_pack
contract
test
graph_neighbors
bm25
vector
```

Allowed `confidence` values:

```text
exact       # exact file range, symbol range, route operation, or test file
high        # direct chunk/span overlap with exact source anchor
medium      # deterministic query result or graph edge with source recovery
low         # approximate static graph context; never sufficient alone for a claim
```

## Retrieval strategy

Phase 3 should first build in-memory lookup maps from the bundle:

```text
span_id -> span row
chunk_id -> chunk row
symbol_id -> symbol row
path -> file row
path + line -> overlapping chunks/spans
query_pack -> rg result rows
node_id -> graph node
node_id -> graph edges
contract path/method -> OpenAPI operation
```

Then it processes each `SectionPlan` in document order and executes the following
lanes.

### 1. Files and exact ranges -> `file_anchor`

Source field:

```text
SectionPlan.retrieval_needs.files[]
```

Rules:

- If `path` is resolved and `anchor_confidence` is `exact_range` or `line_only`,
  retrieve overlapping spans/chunks for that exact range.
- If `path` is resolved but the anchor is absent or `file_only`, retrieve stable
  representative chunks for the file, ordered by line number.
- If the normalized plan preserved a loose text anchor, use it only as an
  in-file BM25/text filter. It is not final evidence unless it resolves to an
  exact range or chunk.
- Invalid ranges are plan-quality failures, not an invitation to guess.

### 2. Symbol IDs -> `symbol_anchor`

Source field:

```text
SectionPlan.retrieval_needs.symbols[]
```

Rules:

- Use only entries with a resolved `symbol_id` and `resolution` of `exact` or
  `unique_alias`.
- Resolve the symbol through `symbols/symbols.jsonl`.
- Prefer the symbol's own `span_id` from `symbols/symbols.jsonl` or a matching
  row in `rag/spans.jsonl`.
- Include overlapping chunks from `rag/chunks.jsonl` so later writing has enough
  context.
- For class symbols, include the class header span first, then child method spans
  only when needed for coverage and within caps.
- Ambiguous or unresolved symbol references are normalized-plan failures.

### 3. Query packs -> `query_pack`

Source field:

```text
SectionPlan.retrieval_needs.query_packs[]
```

Rules:

- Query-pack keys must already be canonical from Phase 2 normalization.
- Read matching rows from `queries/results/rg.jsonl`.
- Convert each match's `path` + `line` into overlapping chunks/spans.
- Preserve query-pack provenance: pack name, regex rule path, matched line, and
  matched text.
- Treat query-pack hits as pointers to source, not as final proof by themselves.
- Stable order is `pack`, `path`, `line`, then matched text.

### 4. Contracts -> `contract`

Source field:

```text
SectionPlan.retrieval_needs.contracts[]
```

Rules:

- Resolve exact `METHOD /path` or `path_only` references against
  `contracts/openapi.json`.
- Evidence may cite the OpenAPI operation by JSON pointer, for example
  `/paths/~1api~1users/get`.
- If the operation has `x-handler-symbol-id`, retrieve the handler through the
  `symbol_anchor` lane and link both evidence items.
- If only `contracts/contract-sources.md` identifies a source file/range, recover
  that source anchor when possible.
- A path-only contract with multiple methods should list deterministic candidate
  methods and retrieve each within caps, rather than choosing silently.

### 5. Tests -> `test`

Source field:

```text
SectionPlan.retrieval_needs.tests[]
```

Rules:

- Exact or unique-suffix test files map through `tests/test-files.jsonl` and
  `rag/chunks.jsonl`.
- If `tests/pytest-collect.txt` is present, include matching collected test node
  names as provenance.
- Test hints that do not resolve to a file become BM25 queries constrained to
  test files when possible.
- Test evidence should cite test source ranges, not only the test inventory row.

### 6. Graph neighbors -> `graph_neighbors`

Source fields:

```text
SectionPlan.retrieval_needs.graph_nodes[]
resolved symbol_ids from retrieval_needs.symbols[]
resolved file paths from retrieval_needs.files[]
```

Rules:

- Seed graph lookup with resolved symbol nodes and file nodes.
- Expand one hop by default.
- Prefer edge types that explain local structure:
  `CONTAINS`, `IMPORTS`, `INHERITS`, `DECORATED_BY`, `CALLS_APPROX`,
  `TESTS_APPROX`, and `MENTIONS`.
- Exact/observed edges have higher confidence than inferred approximate edges.
- Approximate edges are context, not truth. They must not be the only evidence for
  a claim unless the later writing phase labels the claim as approximate.
- Convert neighbor nodes back to source spans/chunks when possible.

### 7. BM25 -> `bm25`

Source fields used to build the query:

```text
SectionPlan.title
SectionPlan.purpose
SectionPlan.goal
SectionPlan.required_topics[]
SectionPlan.key_questions[]
SectionPlan.verification_needs[]
SectionPlan.retrieval_needs.* unresolved hints, when present
```

Rules:

- Use `rag/bm25.sqlite` only if `rag/retrieval-capabilities.json` reports
  `capabilities.bm25: true`.
- Build deterministic query text by joining normalized strings in the field order
  above, removing duplicates while preserving first occurrence.
- Search using the Step 5 BM25/FTS mechanism.
- Convert every hit to a `chunk_id`, path/range, span IDs, and excerpt.
- BM25 is a recall lane. It strengthens coverage but does not override exact
  file/symbol/contract evidence.

### 8. Vectors -> `vector`

Source fields used to build the query are the same as BM25.

Rules:

- Use vectors only if `rag/retrieval-capabilities.json` reports
  `retrieval_mode: "hybrid"` or `capabilities.vectors: true`.
- Validate the FAISS index and vector metadata path from the capability file
  before querying.
- Map vector ordinals through `rag/vector-metadata.json` or
  `rag/vector-metadata.jsonl` to `chunk_id`, path/range, and span IDs.
- If capabilities report lexical-symbolic mode, vector retrieval is skipped with
  lane status `capability_disabled`; this is not a failure.
- If capabilities report vectors enabled but vector files are missing or counts
  diverge, this is a bad/missing input artifact failure.

## Aggregation, dedupe, and ranking

Phase 3 should merge lane outputs per section using deterministic rules:

1. Assign every raw hit a candidate `dedupe_key`.
2. Prefer exact source spans over chunks when both describe the same range.
3. Merge duplicate candidates by keeping all lane provenance but one evidence
   item.
4. Sort by:
   - confidence rank: `exact`, `high`, `medium`, `low`;
   - lane priority: `file_anchor`, `symbol_anchor`, `contract`, `test`,
     `query_pack`, `graph_neighbors`, `bm25`, `vector`;
   - lane rank / score;
   - `path`;
   - `range.start_line`;
   - `chunk_id` / `span_id`;
   - final `evidence_id`.
5. Apply per-lane and per-section caps after sorting.
6. Generate final `evidence_id` values from the final sorted list.

Exact anchor lanes should not be pushed out by BM25 or vector recall hits.

## Validation and reports

Validation is a deterministic contract check. It is not an invitation to rerun
individual sections until they pass.

Because Phase 3 retrieval is deterministic, rerunning a failed section with the
same inputs will produce the same failure. The correct response is to fix the
violated contract: missing/corrupt artifacts, underspecified normalized plan, or
retriever implementation bug. Then rerun the all-sections command.

### `evidence/retrieval-validation.json`

Minimum shape:

```json
{
  "schema_version": "phase3-retrieval-validation-v1",
  "status": "pass",
  "failure_category": null,
  "retrieval_mode": "hybrid",
  "counts": {
    "sections_expected": 13,
    "sections_processed": 13,
    "packets_written": 13,
    "evidence_items": 180
  },
  "contract_checks": [
    {
      "name": "all_sections_have_packets",
      "status": "pass",
      "details": "13/13 packets written"
    }
  ],
  "section_results": [
    {
      "section_id": "rag-pipeline-and-tasks",
      "status": "pass",
      "evidence_count": 18,
      "missing_expected_evidence_types": [],
      "warnings": []
    }
  ],
  "errors": [],
  "warnings": []
}
```

Required contract checks:

- `document-plan.json` is valid and has a stable `section_order`.
- `section-plans.jsonl` is valid JSONL and contains every section in
  `section_order`.
- Every normal run processes all sections.
- `retrieval-capabilities.json` is valid and agrees with required Step 5 files.
- BM25 is readable when `capabilities.bm25` is true.
- Vector files and metadata are readable and count-consistent when vectors are
  true.
- Every EvidencePacket validates against `phase3-evidence-packet-v1`.
- Every evidence item cites a real artifact and stable source anchor.
- No evidence item cites only the normalized plan.
- Evidence IDs are unique within a packet and stable across reruns.
- The combined JSONL contains exactly one packet per section in document order.

### `evidence/retrieval-report.md`

Must include:

- bundle root;
- input plan paths;
- retrieval capabilities path;
- retrieval mode: `lexical-symbolic` or `hybrid`;
- output paths;
- number of sections processed;
- evidence counts by section and lane;
- validation PASS/FAIL status;
- failure category, when failed;
- unresolved evidence summary;
- notes for the later writing phase.

The report must not instruct the user to repeatedly run individual sections. It
should point to the appropriate fix path.

## Failure categories and debugging paths

Phase 3 failures must be classified into exactly these product categories.

### 1. Bad/missing input artifact

Meaning: the bundle or retrieval substrate is missing, corrupt, stale, or
inconsistent.

Examples:

- `plans/document-plan.json` missing or invalid JSON;
- `plans/section-plans.jsonl` missing or invalid JSONL;
- `rag/retrieval-capabilities.json` missing or malformed;
- `rag/chunks.jsonl` or `rag/spans.jsonl` missing;
- `rag/bm25.sqlite` missing/corrupt while capabilities say BM25 is enabled;
- capabilities say vectors are enabled, but `rag/vectors.faiss` or vector
  metadata is missing;
- vector metadata count diverges from FAISS vector count;
- source anchors point outside known files because the bundle artifacts are
  stale or inconsistent.

Product behavior:

- hard stop;
- do not publish a successful manifest;
- write `retrieval-validation.json` and `retrieval-report.md` if enough of the
  output directory can be created;
- classify as `bad_missing_input_artifact`.

Debugging path:

- fix the missing or corrupt bundle artifacts;
- rerun `decompose` or `build-retrieval` as appropriate;
- rerun the all-sections Phase 3 command.

### 2. Bad or underspecified normalized plan

Meaning: Phase 2 normalization produced a syntactically valid plan, but the plan
is not a sufficient retrieval work order.

Examples:

- a section in `document-plan.json.section_order` has no corresponding
  `SectionPlan`;
- a section has no resolvable `retrieval_needs` and too little topic text for
  BM25/vector recall;
- `normalization_warnings` contain unresolved references that are required for
  expected evidence;
- `expected_evidence_types` asks for contracts/tests/symbols but the section has
  no resolvable contract/test/symbol work item and no deterministic query path;
- a file anchor is loose or invalid where the section requires an exact range;
- a path-only contract is too broad for the requested section and cannot be
  resolved deterministically within caps.

Product behavior:

- fail validation as a plan-quality problem;
- report the exact section IDs and normalized fields that are underspecified;
- do not enter an interactive retry/debug loop;
- classify as `bad_underspecified_normalized_plan`.

Debugging path:

- fix upstream in Phase 2 planning or in `normalize-plan`;
- regenerate `plans/document-plan.json` and `plans/section-plans.jsonl`;
- rerun the all-sections Phase 3 command.

### 3. Retriever implementation bug

Meaning: the inputs satisfy their contracts, but the Phase 3 retriever code fails
or writes invalid outputs.

Examples:

- unhandled exception on valid artifacts;
- nondeterministic output ordering across identical runs;
- duplicate `evidence_id` values;
- an evidence item references a nonexistent `chunk_id`, `span_id`, path, or JSON
  pointer after the lane claimed success;
- lane scoring or dedupe violates the documented ordering rules;
- schema-valid inputs produce schema-invalid EvidencePackets.

Product behavior:

- fail validation;
- preserve a failure report when possible;
- classify as `retriever_implementation_bug` or a narrower internal code if the
  command layer can do so safely.

Debugging path:

- create or update failing unit/integration tests;
- fix the retriever code;
- rerun tests;
- rerun the all-sections Phase 3 command.

## Exit codes

Recommended exit codes:

```text
0  success: all packets written and validation passed
2  bad/missing input artifact
3  bad or underspecified normalized plan
1  retriever implementation bug or unclassified internal failure
```

## Implementation location

Recommended package shape:

```text
src/wiki_generator/
  cli.py                                  # add retrieve-evidence subcommand only
  libs/commands/retrieve_evidence.py      # command wrapper
  libs/evidence/
    __init__.py                           # all-sections orchestration
    options.py                            # deterministic command options
    loader.py                             # load plans, capabilities, and indexes
    schema.py                             # EvidencePacket and validation helpers
    query_text.py                         # deterministic SectionPlan -> query text
    lanes/
      files.py                            # file_anchor
      symbols.py                          # symbol_anchor
      query_packs.py                      # query_pack
      contracts.py                        # contract
      tests.py                            # test
      graph.py                            # graph_neighbors
      bm25.py                             # BM25 query wrapper
      vectors.py                          # FAISS/vector metadata query wrapper
    aggregate.py                          # merge, dedupe, rank, cap
    validate.py                           # contract/invariant checks
    writer.py                             # packets, manifest, reports
```

Use `libs/retrieval/bm25.py` and Step 5 vector metadata contracts rather than
creating a second BM25/vector schema.

Keep Phase 3 EvidencePacket logic out of Phase 1 Step 5 code. Step 5 builds the
substrate; Phase 3 consumes it section-by-section.

## Tests to require

Unit tests should cover:

- command parser exposes `retrieve-evidence` and does not expose a product
  `--section` option;
- loading `document-plan.json` and `section-plans.jsonl` in document order;
- rejecting missing or malformed required artifacts as
  `bad_missing_input_artifact`;
- rejecting capabilities that report vectors enabled while vector artifacts are
  absent or count-inconsistent;
- detecting a section that is underspecified as
  `bad_underspecified_normalized_plan`;
- exact file ranges map to overlapping spans/chunks;
- loose file anchors are treated as hints, not exact evidence;
- resolved `symbol_id` maps to symbol span/chunk evidence;
- ambiguous/unresolved symbols fail as normalized-plan quality issues;
- query-pack rows map from `queries/results/rg.jsonl` to source chunks/spans;
- exact and path-only OpenAPI contract references produce deterministic evidence;
- test file references map to test source chunks;
- graph neighbor expansion is one-hop, stable, and confidence-aware;
- BM25 search returns deterministic top-k hits and stable tie-breaking;
- vector lane runs only when capabilities say hybrid/vectors true;
- vector-disabled lexical-symbolic mode records a skipped vector lane, not a
  failure;
- aggregation dedupes identical source anchors while preserving provenance;
- evidence IDs are stable and unique;
- EvidencePacket JSON validates against the schema;
- `retrieval-validation.json` catches an evidence item that points to a missing
  source anchor;
- rerunning on the same fixture bundle produces byte-identical packet JSON,
  manifest, validation, and report except for explicitly forbidden timestamps
  which should not be present.

Integration tests should cover:

- a small fixture bundle with two sections writes two packet files, one combined
  JSONL, a manifest, validation JSON, unresolved JSONL, and a report;
- a lexical-symbolic fixture passes without vector files when capabilities report
  vectors false;
- a hybrid fixture uses vector metadata to recover chunks;
- corrupt `bm25.sqlite` with BM25 enabled hard-stops as a bad input artifact;
- a plan with a missing section work order fails as a bad normalized plan;
- a forced invalid evidence source is caught as a retriever implementation bug.

## Acceptance criteria

A successful Phase 3 implementation:

- reads the normalized Phase 2 plan and Step 5 retrieval capabilities;
- treats the normalized plan as a retrieval work order, not evidence;
- processes every section in one normal run;
- writes one EvidencePacket JSON file per section;
- writes `evidence/evidence-packets.jsonl` in document order;
- writes `evidence/evidence-manifest.json`;
- writes deterministic validation and retrieval reports;
- retrieves evidence through file, symbol, query-pack, contract, test, graph,
  BM25, and optional vector lanes;
- uses vectors only when `rag/retrieval-capabilities.json` reports hybrid/vector
  support;
- cites exact Phase 1/Step 5 artifacts for every evidence item;
- validates outputs as contract/invariant checks;
- does not use an LLM or network call;
- does not expose product `--section` behavior;
- does not implement an interactive retry loop;
- classifies failures as bad/missing input artifact, bad or underspecified
  normalized plan, or retriever implementation bug;
- gives the user the correct fix path and then expects the all-sections Phase 3
  command to be rerun.
