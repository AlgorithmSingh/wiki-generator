# Working Technical Design

## Design summary

Add a deterministic, repository-derived expanded topic catalog before Phase 2 planning. Use it to constrain LLM planning into a hierarchical PagePlan. Normalize the plan into existing SectionPlan-compatible artifacts, derive a deterministic relevant-source map per page, retrieve evidence per page/topic/content block in Phase 3, render pages through grounded claim/token plans in Phase 4, and validate the full topic→plan→source→evidence→output lineage.

## Architecture overview

```text
Phase 1 deterministic repo bundle
  inventory / symbols / contracts / tests / query packs / runtime surfaces / chunks / spans
    |
    v
New expanded topic catalog (deterministic, planner context, non-citeable)
  derived/topic-catalog.json
  derived/planning-topic-catalog.md
    |
    v
Phase 2 LLM planning constrained by catalog + exact handles
  hierarchical PagePlan / SectionPlan
  page profiles + content blocks + required topics + TERs
    |
    v
Phase 2 deterministic normalization/gates
  plans/document-plan.json
  plans/section-plans.jsonl
  plans/relevant-source-map.json
  plans/coverage-gate.json
  plans/topic-obligations-gate.json
    |
    v
Phase 3 deterministic evidence retrieval
  evidence/packets/<page_id>.json
  evidence/evidenced-coverage.json
  profile-aware evidence sufficiency
    |
    v
Phase 4 grounded rendering through claim/token plan
  wiki/sections/*.md
  wiki/index.md nested navigation
  wiki/metadata/generated-coverage.json
  wiki/validation/generated-coverage-report.md
    |
    v
New coverage traceability and freshness gate
  coverage/coverage-traceability.json
  coverage/coverage-traceability-report.md
  optional benchmark-only comparison report
```

## Component design

### 1. Expanded topic catalog builder

**Purpose:** Turn Phase 1 deterministic repo signals into page/topic candidates before planning.

**Likely modules:**

- Existing: `src/wiki_generator/libs/coverage/signals.py`
- Existing: `src/wiki_generator/libs/coverage/taxonomy.py`
- Inferred new: `src/wiki_generator/libs/coverage/facets.py`
- Inferred new: `src/wiki_generator/libs/coverage/topic_catalog.py`
- Inferred new: `src/wiki_generator/libs/digest/planning_topic_catalog.py`
- Existing to modify: `src/wiki_generator/libs/commands/condense.py`, `digest.py`, `bundle.py`, `src/wiki_generator/libs/digest/upload_package.py`

**Behavior:**

- Read existing Phase 1 artifacts through `digest.loader.Bundle`.
- Detect catalog topics from deterministic signals: paths, top-level directories, docs, tests, configs, deployment files, OpenAPI route groups, frontend routes/components, Go files, symbols, query packs, runtime surfaces, chunks/spans, and source-coverage counts.
- Emit stable topic IDs and candidate source handles.
- Mark the catalog as planner context, not citeable evidence.
- Mark weak/missing signals as known gaps rather than forcing pages.
- Keep existing 13-family taxonomy as a compatibility overlay, not as the full catalog.

### 2. Page profile and content-block taxonomy

**Purpose:** Prevent shallow pages by giving each page type required blocks.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/page_profiles.py`
- Existing to extend: `coverage/taxonomy.py`, `coverage/obligations.py`

**Initial profiles:**

- `overview`
- `architecture-flow`
- `subsystem-deep-dive`
- `api-reference`
- `configuration-reference`
- `deployment-runbook`
- `developer-workflow`
- `data-model-reference`
- `operations-page`
- `glossary`

**Example block requirements:**

- API reference: `purpose`, `route_group_matrix`, `request_response_contracts`, `handlers`, `tests`, `known_gaps`.
- Deployment runbook: `entrypoints`, `docker_compose`, `helm_values`, `config_secrets`, `health_ops`, `rollback_notes`.
- Subsystem deep dive: `purpose`, `entrypoints`, `flow`, `key_files`, `data_dependencies`, `tests`, `operations`.

### 3. Phase 2 planning and normalization

**Purpose:** Use the catalog to make the LLM author a hierarchical plan, then normalize it into strict machine-readable artifacts.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/commands/plan.py`
- Existing to modify: `gemini-gem/GEM_INSTRUCTIONS.md`, `gemini-gem/KICKOFF_PROMPT.md`
- Existing to modify: `src/wiki_generator/libs/plan_normalization/normalize.py`, `writer.py`, `repair.py`
- Existing to extend: `src/wiki_generator/libs/coverage/validate.py`, `obligations.py`

**Design:**

- Preserve `section_id` for compatibility; treat it as the page ID in expanded mode.
- Add normalized fields: `page_profile`, `catalog_topic_ids[]`, `required_content_blocks[]`, `known_gaps[]`, `topic_evidence_requirements[]` extended with optional `content_block_id` and `catalog_topic_id`.
- Gate plan shape before Phase 3:
  - all high-signal catalog topics are planned or explicitly deferred;
  - parent/child hierarchy is acyclic and resolvable;
  - page profiles are valid;
  - required blocks and topics are present;
  - every blocking topic/block has exact source obligations;
  - broad parent pages do not satisfy child obligations.

### 4. Deterministic relevant-source map

**Purpose:** Select page-relevant source handles before Phase 3 so evidence retrieval is focused and deterministic.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/source_selection.py`
- Existing to extend: `coverage/substrate.py`, `coverage/obligations.py`, `plan_normalization/normalize.py`

**Artifact:** `plans/relevant-source-map.json`.

**Inputs:** topic catalog, normalized page plan, exact handle catalog, retrieval substrate, candidate source handles.

**Selection rules:**

- Use exact handles when available: files, symbols, contracts, tests, query packs, spans/chunks.
- Preserve source-field mapping back to PagePlan topic/block obligations.
- Score deterministically by catalog signal strength, handle type, source category, profile requirements, citeable-substrate availability, and deduplication.
- Fail the enhancement gate when a blocking topic/block has no exact, citeable source selection.
- Do not use benchmark material or generated wiki artifacts.

### 5. Phase 3 profile-aware evidence portfolios

**Purpose:** Retrieve enough evidence for each page profile and content block without making Phase 3 nondeterministic.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/evidence/options.py`
- Existing to modify: `src/wiki_generator/libs/evidence/aggregate.py`
- Existing to modify: `src/wiki_generator/libs/evidence/evidenced_coverage.py`
- Existing to modify: `src/wiki_generator/libs/evidence/query_text.py`
- Existing lanes: `src/wiki_generator/libs/evidence/lanes/{files,symbols,contracts,tests,query_packs,bm25,graph,vectors}.py`

**Design:**

- Evidence requirements operate at page/topic/content-block granularity.
- Required blocks define portfolio floors, e.g. API block needs route contract plus handler or test evidence.
- Broad recall can add context but cannot satisfy precise required obligations by itself.
- Evidence matrix statuses remain `sufficient`, `weak`, `missing`, `not_applicable`.
- Enhancement mode fails before Phase 4 for weak/missing blocking obligations.

### 6. Phase 4 grounded page rendering

**Purpose:** Render each expanded page from exact evidence and validated claim/token plans.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/writing/packet.py`
- Existing to modify: `src/wiki_generator/libs/writing/prompt.py`
- Existing to modify: `src/wiki_generator/libs/writing/claim_plan.py`
- Existing to modify: `src/wiki_generator/libs/writing/grounded.py`
- Existing to modify: `src/wiki_generator/libs/writing/token_bank.py`
- Existing to modify: `src/wiki_generator/libs/writing/generated_coverage.py`
- Existing to modify: `src/wiki_generator/libs/writing/validate.py`
- Existing to modify: `src/wiki_generator/libs/writing/assemble.py`

**Design:**

- WritingPacket includes page profile, parent/child context, required content blocks, evidenced topic rows, allowed evidence IDs, and token bank.
- Claim plan requires groups by content block and topic.
- Renderer emits one section per required content block when evidence supports it.
- `covered_topics[]` and inferred `covered_content_blocks[]` are validated against citations and generated Markdown anchors.
- Existing validators remain mandatory after rendering.

### 7. Coverage traceability and evaluation

**Purpose:** Evaluate planned/evidenced/generated breadth without benchmark copying.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/traceability.py`
- Inferred new or extended: `src/wiki_generator/libs/coverage/metrics.py`
- Existing to extend: `src/wiki_generator/libs/commands/validate_coverage.py`
- Existing to extend: `writing/generated_coverage.py`

**Artifacts:**

- `coverage/coverage-traceability.json`
- `coverage/coverage-traceability-report.md`
- `wiki/validation/benchmark-comparison.md` or run-level comparator report, non-citeable and excluded from gates.

**Gate:** Every blocking source-derived topic/content block must have lineage:

`catalog_topic_id -> section_id/page_id -> content_block_id -> topic_evidence_requirement -> relevant_source_map handles -> evidence_ids -> generated markdown anchor -> local citations -> validation status`.

## Data contracts

### Topic catalog

`derived/topic-catalog.json`, schema `deepwiki-topic-catalog-v1`:

```json
{
  "schema_version": "deepwiki-topic-catalog-v1",
  "role": "planner_context",
  "citeable_as_evidence": false,
  "source_fingerprint": "sha256:...",
  "topics": [
    {
      "topic_id": "doc-processing.parsers",
      "parent_topic_id": "doc-processing",
      "family": "doc-processing",
      "label": "Parser implementations",
      "topic_kind": "subsystem",
      "suggested_page_profile": "subsystem-deep-dive",
      "status": "present",
      "signal_strength": "high",
      "priority": "must|should|could",
      "source_signals": [],
      "candidate_source_handles": [],
      "required_content_blocks": ["purpose", "entrypoints", "flow", "key_files", "tests"],
      "expected_evidence_lanes": ["file_anchor", "symbol_anchor", "test"],
      "min_exact_items": 3,
      "known_gap_reason": null
    }
  ]
}
```

### Page plan / normalized SectionPlan extensions

Existing `plans/section-plans.jsonl` rows gain additive fields:

```json
{
  "section_id": "doc-processing-parsers",
  "parent_section_id": "doc-processing",
  "page_profile": "subsystem-deep-dive",
  "catalog_topic_ids": ["doc-processing.parsers"],
  "coverage_labels": ["doc-processing"],
  "required_content_blocks": [
    {
      "block_id": "flow",
      "block_type": "flow",
      "required": true,
      "required_topics": ["Parser selection flow"],
      "min_exact_items": 3,
      "expected_evidence_lanes": ["file_anchor", "symbol_anchor"]
    }
  ],
  "topic_evidence_requirements": [
    {
      "topic": "Parser selection flow",
      "catalog_topic_id": "doc-processing.parsers",
      "content_block_id": "flow",
      "required": true,
      "source_fields": ["retrieval_needs.files[0]", "retrieval_needs.symbols[0]"],
      "min_items": 3,
      "acceptable_lanes": ["file_anchor", "symbol_anchor"]
    }
  ]
}
```

### Relevant source map

`plans/relevant-source-map.json`, schema `deepwiki-relevant-source-map-v1`:

```json
{
  "schema_version": "deepwiki-relevant-source-map-v1",
  "plan_fingerprint": "sha256:...",
  "catalog_fingerprint": "sha256:...",
  "pages": [
    {
      "section_id": "doc-processing-parsers",
      "page_profile": "subsystem-deep-dive",
      "selected_handles": [
        {
          "handle_id": "doc-processing-parsers:file:0",
          "lane": "file_anchor",
          "source_field": "retrieval_needs.files[0]",
          "path": "rag/svr/task_executor.py",
          "catalog_topic_ids": ["doc-processing.parsers"],
          "content_block_ids": ["flow"],
          "selection_reason": "high-signal parser candidate and citeable chunk/span coverage",
          "citeable": true
        }
      ]
    }
  ]
}
```

### Evidence linkage

Extend `evidence/evidenced-coverage.json` rows with `catalog_topic_id`, `content_block_id`, `page_profile`, `mapped_handle_ids`, and `portfolio_requirements` while preserving existing topic status semantics.

### Coverage traceability

`coverage/coverage-traceability.json`, schema `deepwiki-coverage-traceability-v1`:

```json
{
  "schema_version": "deepwiki-coverage-traceability-v1",
  "status": "pass|fail",
  "lineage_fingerprint": "sha256:...",
  "rows": [
    {
      "catalog_topic_id": "doc-processing.parsers",
      "section_id": "doc-processing-parsers",
      "content_block_id": "flow",
      "topic": "Parser selection flow",
      "plan_status": "planned",
      "source_selection_status": "selected",
      "evidence_status": "sufficient",
      "generated_status": "covered",
      "evidence_ids": ["ev:doc-processing-parsers:0001"],
      "markdown_path": "wiki/sections/006-doc-processing-parsers.md",
      "markdown_anchor": "parser-selection-flow",
      "citation_status": "valid",
      "deferral_reason": null
    }
  ]
}
```

## CLI and compatibility strategy

- Keep `baseline` mode non-breaking.
- Extend existing `--coverage-mode enhancement` rather than introduce a separate top-level product mode unless implementation proves a temporary shadow flag is needed.
- Add catalog outputs during `condense`/`digest`/`bundle`; mark as planner context and non-citeable.
- `normalize-plan --coverage-mode enhancement` should enforce catalog/page/profile/source-selection gates and write `plans/relevant-source-map.json`.
- `retrieve-evidence --coverage-mode enhancement` should require current source map and use it to evaluate evidence portfolios.
- `write-wiki --coverage-mode enhancement --grounded-claim-plan` should remain the production expanded path.
- Official final provider path remains `--provider vertex` with Gemini; non-live tests use fake/Gem fixture paths.

## Failure behavior

- Missing catalog in enhancement mode: Phase 2 input/gate failure before planning or normalization.
- Broad-only page plan: Phase 2 gate failure.
- Missing/weak source selection: Phase 2 gate failure before Phase 3.
- Missing/weak evidence: Phase 3 failure before Phase 4.
- Missing generated topic/block or invalid citations: Phase 4 writing-validation failure.
- Benchmark leakage: validation failure; no repair by copying or patching.
- Stale artifact fingerprint mismatch: gate failure at the first downstream consumer.
