# Technical Design Document: DeepWiki Coverage Expansion

**Status:** Final TDD
**Date:** 2026-06-29
**Workspace:** `docs/technical-design/deepwiki-coverage-expansion/`
**Product area:** `wiki-generator` coverage planning, evidence retrieval, grounded writing, and validation
**Primary PRD:** `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`
**ADR:** `adr/0001-expanded-coverage-as-hierarchical-topic-catalog.md`

## Table of Contents

1. [Summary](#1-summary)
2. [Context and Background](#2-context-and-background)
3. [Goals, Non-Goals, and Future Goals](#3-goals-non-goals-and-future-goals)
4. [Success Metrics and Definition of Done](#4-success-metrics-and-definition-of-done)
5. [Requirements, Constraints, Assumptions, and Dependencies](#5-requirements-constraints-assumptions-and-dependencies)
6. [Architecture Overview](#6-architecture-overview)
7. [Detailed Component and Module Design](#7-detailed-component-and-module-design)
8. [Data Contracts and Artifacts](#8-data-contracts-and-artifacts)
9. [CLI, Wrapper, and API Behavior](#9-cli-wrapper-and-api-behavior)
10. [Runtime Behavior and Failure Paths](#10-runtime-behavior-and-failure-paths)
11. [Validation and Evaluation Design](#11-validation-and-evaluation-design)
12. [Quality Attributes](#12-quality-attributes)
13. [Alternatives Considered and Trade-Offs](#13-alternatives-considered-and-trade-offs)
14. [Architecture Decisions](#14-architecture-decisions)
15. [Implementation Plan, Milestones, and Tests](#15-implementation-plan-milestones-and-tests)
16. [Rollout, Rollback, and Operations](#16-rollout-rollback-and-operations)
17. [Risks, Open Questions, and Failure Modes](#17-risks-open-questions-and-failure-modes)
18. [Appendix: Glossary and References](#18-appendix-glossary-and-references)

---

## 1. Summary

`wiki-generator` currently produces a valid, grounded overview wiki for the plan it is given. The official RAGFlow run passed for its scoped plan: 22 sections, 53/53 required topics covered, and 425 distinct citations. [Sourced: PRD, coverage expansion reports]

The product gap is breadth. The DeepWiki benchmark export shows a wider, subsystem-oriented hierarchy with 62 page blocks and per-page relevant source files, but it is comparison-only and was indexed at a different commit. It must not become evidence, copied structure, headings, prose, or claims. [Sourced: PRD, reverse-engineering report]

This design expands coverage by adding an upstream, repository-derived hierarchical topic catalog before Phase 2 planning. The catalog constrains LLM page planning, feeds deterministic per-page source selection before Phase 3, and enables page/topic/content-block traceability through evidence retrieval and grounded rendering.

The core rule is unchanged: **Phase 3 remains deterministic, and Phase 4 remains a grounded renderer.** Expanded coverage must be earned by source-derived topics, exact source obligations, sufficient citeable evidence, valid local citations, and traceability—not by benchmark copying, output patching, or longer prose.

---

## 2. Context and Background

### 2.1 Existing pipeline

`wiki-generator` uses a Phase 1–4 pipeline. [Sourced: README and inspected code]

```text
Phase 1  decompose / condense / digest / bundle / build-retrieval
Phase 2  plan with LLM, optional bounded plan-repair, normalize-plan
Phase 3  retrieve-evidence deterministically for every planned section
Phase 4  write-wiki from validated EvidencePackets and strict validators
```

The existing implementation already includes several enhancement foundations. [Sourced: existing spec and code]

- `--coverage-mode enhancement` for Phase 2 planned coverage, Phase 3 evidenced coverage, and Phase 4 generated coverage.
- A 13-family coverage taxonomy and deterministic coverage signals.
- `topic_evidence_requirements[]` and topic-obligation gates.
- Phase 3 `evidence/evidenced-coverage.json`.
- Phase 4 `wiki/metadata/generated-coverage.json` and generated coverage validation.
- Opt-in `--grounded-claim-plan` with token-bank and claim-plan validation.

### 2.2 Problem

The current coverage model can pass when all currently planned topics are covered, even if important repository subtopics were never promoted into pages, source obligations, evidence portfolios, or generated coverage rows. [Sourced: PRD and expansion reports]

A broad parent page must not count as coverage for child topics. Coverage expansion therefore belongs upstream:

```text
repository signals -> catalog -> hierarchical plan -> relevant source map -> evidence -> grounded output -> traceability
```

### 2.3 Benchmark boundary

The benchmark export is useful as a breadth and structure dashboard only. It is not source truth. The design forbids benchmark-derived evidence IDs, copied headings, copied prose, copied claims, and benchmark-only required topics. [Sourced: PRD BR-01/BR-02/BR-10]

---

## 3. Goals, Non-Goals, and Future Goals

### 3.1 Goals

| ID | Goal | Source |
| --- | --- | --- |
| G-01 | Build a repository-derived expanded topic/page catalog before Phase 2 planning. | PRD UR-01 |
| G-02 | Generate hierarchical parent/child page plans from deterministic repo signals plus LLM planning constrained by evidence-backed candidates. | PRD UR-02/UR-03 |
| G-03 | Select relevant files, symbols, spans, contracts, tests, docs, configs, and runtime surfaces per page before Phase 3. | PRD UR-04 |
| G-04 | Retrieve and validate evidence per page/topic/content block while keeping Phase 3 deterministic. | PRD UR-05/BR-05 |
| G-05 | Render expanded pages through the grounded claim/token plan path. | PRD UR-06, existing spec |
| G-06 | Evaluate coverage through topic→plan→evidence→output traceability. | PRD UR-07/UR-08 |
| G-07 | Preserve strict validators and fail closed on missing, weak, stale, unsupported, or benchmark-contaminated artifacts. | PRD UR-09/UR-10/UR-12 |

### 3.2 Non-goals

- Do not copy benchmark headings, prose, claims, citations, or page structure into generated output. [Sourced]
- Do not solve coverage by increasing token limits, page length, or verbosity. [Sourced]
- Do not add output patching, generated Markdown mutation, synthetic evidence, generic retry loops, or silent required-to-optional downgrades. [Sourced]
- Do not weaken citation, malformed-token, unsupported-identifier, placeholder, truncation, context-artifact, generated coverage, or evidence validators. [Sourced]
- Do not replace deterministic Phase 3 retrieval with LLM retrieval or fuzzy semantic acceptance. [Sourced]
- Do not make page-count or word-count parity with the benchmark the primary success criterion. [Sourced]

### 3.3 Future goals

- Calibrate promotion thresholds from multiple real repositories. [Open]
- Add optional richer language extractors for Go, TypeScript/TSX, deployment, OpenAPI schema depth, and CLI/admin surfaces. [Inferred]
- Add sampled RAG-style quality checks after deterministic gates pass. [Sourced from research, future]
- Decide whether grounded claim-plan mode becomes default for expanded coverage runs. [Open]

---

## 4. Success Metrics and Definition of Done

### 4.1 Product success metrics

| Metric | Target |
| --- | --- |
| Catalog completeness | 100% of high-signal source-derived facets planned or explicitly deferred with source-derived reason. |
| Hierarchy completeness | Every normal source page has parent/child placement, profile, content blocks, required topics, and source obligations. |
| Evidence sufficiency | 100% of blocking topics/content blocks sufficient before Phase 4. |
| Generated coverage | 100% of evidenced required topics/content blocks generated with valid local citations. |
| Citation quality | 0 unresolved citations, malformed tokens, context-artifact citations, unsupported identifiers, placeholders, or truncation defects. |
| Artifact freshness | 100% of downstream PASS reports fingerprint current plan/evidence artifacts. |
| Coverage breadth | Material expansion beyond 22 sections/53 topics; first target band calibrated after catalog generation. |
| Benchmark leakage | 0 benchmark-derived citeable evidence IDs, copied headings, copied prose, or benchmark-only claims. |

### 4.2 TDD definition of done

The TDD-specific definition of done is captured in `definition-of-done.json`. It requires:

- all required workspace files present;
- formal TDD structure and table of contents;
- coverage of all PRD Must requirements;
- benchmark isolation;
- strict validator preservation;
- deterministic Phase 3 design;
- bounded repair policy;
- explicit data contracts;
- implementation readiness and tests;
- valid JSON workspace artifacts.

---

## 5. Requirements, Constraints, Assumptions, and Dependencies

### 5.1 Functional requirements

| PRD ID | Requirement | Design response |
| --- | --- | --- |
| UR-01 | Build source-derived topic/page catalog. | Add deterministic topic catalog artifacts from Phase 1 signals. |
| UR-02 | Plan hierarchical parent/child tree. | Extend SectionPlan as PagePlan with hierarchy fields. |
| UR-03 | Assign page profile and required content blocks. | Add page profile taxonomy and block obligations. |
| UR-04 | Select sources per page before Phase 3. | Write `plans/relevant-source-map.json`. |
| UR-05 | Retrieve/validate evidence per page/topic/block. | Extend Phase 3 evidenced coverage to profile-aware portfolios. |
| UR-06 | Render through grounded claim-plan path. | Use existing token bank and claim-plan renderer, extended by page profile/block. |
| UR-07 | Produce planned→evidenced→generated traceability. | Add `coverage/coverage-traceability.json`. |
| UR-08 | Evaluate source-derived coverage, not benchmark copying. | Add coverage metrics; keep benchmark report separate. |
| UR-09 | Preserve strict validators. | No validator weakening; add stricter gates as needed. |
| UR-10 | Fail closed on missing/weak/stale coverage. | Gate at Phase 2, Phase 3, Phase 4, and traceability/freshness. |
| UR-11 | Record known gaps instead of invention. | Use catalog/page `known_gaps[]` and deferral reasons. |
| UR-12 | Separate benchmark comparison from evidence gates. | Comparator-only report excluded from evidence and citations. |
| UR-13 | Human-readable nested navigation. | Nested `wiki/index.md` with audience paths. |
| UR-14 | Per-page quality/freshness reporting. | Traceability and per-page validation reports. |
| UR-15 | Bounded repair only for LLM-authored plan/claim artifacts. | Repair policy and audit hard caps. |

### 5.2 Constraints

- Phase 3 remains deterministic and LLM-free. [Sourced]
- Benchmark material is comparison-only. [Sourced]
- Strict validators are preserved or strengthened. [Sourced]
- No output patching and no generic heal/retry loops. [Sourced]
- Bounded repair only for LLM-authored page plans or claim plans, with exact diagnostics, audit artifacts, hard caps, and strict revalidation. [Sourced]
- Official final provider path remains Vertex/Gemini. [Sourced from user request and existing CLI]
- Baseline mode should remain non-breaking. [Inferred from existing mode design]

### 5.3 Assumptions

- Existing enhancement-mode artifacts are the right extension points. [Inferred]
- `section_id` can remain the implementation key while representing a page in expanded mode. [Inferred]
- Existing Phase 1 artifacts are sufficient for the first catalog slice; optional extractors can improve later. [Inferred]
- Page-count targets must be calibrated after catalog generation. [Sourced]

### 5.4 Dependencies

- Phase 1: inventory, symbols, contracts, tests, query results, runtime surfaces, chunks, spans, and exact handles.
- Phase 2: planner prompts, normalization, topic-obligation gates, plan repair.
- Phase 3: EvidencePacket schema, exact request coverage, evidence lanes, evidenced coverage.
- Phase 4: WritingPacket, token bank, claim plan, generated coverage, citation and validation modules.
- CLI/wrappers: `normalize-plan`, `retrieve-evidence`, `write-wiki`, non-live E2E scripts, and official Vertex/Gemini configuration.

---

## 6. Architecture Overview

### 6.1 High-level architecture

```text
Phase 1 deterministic repository analysis
  -> expanded topic catalog (new, deterministic, non-citeable planner context)
  -> Phase 2 LLM hierarchical page planning constrained by catalog
  -> Phase 2 deterministic normalization + catalog/profile/source gates
  -> relevant source map (new, deterministic source-selection artifact)
  -> Phase 3 deterministic evidence retrieval and profile-aware sufficiency
  -> Phase 4 grounded claim/token rendering per page
  -> generated coverage + citation validation
  -> coverage traceability + artifact freshness + benchmark-only comparator
```

### 6.2 Key design principles

1. **Coverage is planned before it is written.** Missing pages must fail in Phase 2, not be hidden by Phase 4 prose.
2. **Source selection is explicit before retrieval.** Each page has deterministic relevant handles before Phase 3.
3. **Evidence sufficiency is per obligation.** Page profiles and content blocks define what evidence is enough.
4. **Rendering is grounded.** Expanded pages use token-bank and claim-plan validation.
5. **Evaluation traces lineage.** Coverage passes only when catalog topics trace to plan, source selection, evidence, output, and citations.
6. **Benchmark is isolated.** It can warn about breadth; it cannot create generated content.

### 6.3 Architecture views selected

- Context view: where the catalog/source map fits in Phase 1–4.
- Component/module view: implementer-facing file/module changes.
- Data/artifact view: schemas and ownership.
- Runtime behavior view: gate order and failure paths.
- Validation/operations view: rollout, rollback, freshness, strictness.

---

## 7. Detailed Component and Module Design

New module names below are **inferred** unless marked existing.

### 7.1 Expanded topic catalog

**Responsibility:** Generate a deterministic repository-derived topic/page catalog from Phase 1 artifacts.

**Likely modules:**

- Existing: `src/wiki_generator/libs/coverage/signals.py`
- Existing: `src/wiki_generator/libs/coverage/taxonomy.py`
- Inferred new: `src/wiki_generator/libs/coverage/facets.py`
- Inferred new: `src/wiki_generator/libs/coverage/topic_catalog.py`
- Inferred new: `src/wiki_generator/libs/digest/planning_topic_catalog.py`
- Existing to modify: `src/wiki_generator/libs/commands/condense.py`, `digest.py`, `bundle.py`
- Existing to modify: `src/wiki_generator/libs/digest/upload_package.py`

**Inputs:** inventory files, source coverage, symbols, contracts/OpenAPI, tests, query packs, runtime surfaces, chunks/spans, existing coverage signals.

**Outputs:**

- `derived/topic-catalog.json`
- `derived/planning-topic-catalog.md`

**Rules:**

- Deterministic and timestamp-free.
- Non-citeable planner context.
- Stable topic IDs.
- Every high-signal topic has candidate source handles or a known-gap reason.
- Existing 13-family taxonomy remains a compatibility overlay, not the complete catalog.

### 7.2 Page profiles and content blocks

**Responsibility:** Define what each page type must contain and what evidence lanes can satisfy it.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/page_profiles.py`
- Existing to extend: `coverage/taxonomy.py`, `coverage/obligations.py`

**Initial profiles:** `overview`, `architecture-flow`, `subsystem-deep-dive`, `api-reference`, `configuration-reference`, `deployment-runbook`, `developer-workflow`, `data-model-reference`, `operations-page`, `glossary`.

**Example profile requirements:**

| Profile | Required blocks |
| --- | --- |
| `api-reference` | purpose, route/resource matrix, request/response contracts, handlers, examples/tests, known gaps |
| `deployment-runbook` | entrypoints, Docker/Compose, Helm/Kubernetes, config/secrets, health/ops, rollback |
| `subsystem-deep-dive` | purpose, entrypoints, flow, key files/symbols, dependencies, tests, operations |
| `configuration-reference` | config/env key matrix, defaults/source, consumers, operational notes |
| `glossary` | term, source occurrence, meaning context, related pages |

### 7.3 Phase 2 planning and normalization

**Responsibility:** Make the LLM author a hierarchy from catalog topics, then normalize and gate it.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/commands/plan.py`
- Existing to modify: `gemini-gem/GEM_INSTRUCTIONS.md`, `gemini-gem/KICKOFF_PROMPT.md`
- Existing to modify: `src/wiki_generator/libs/plan_normalization/normalize.py`, `writer.py`, `repair.py`
- Existing to extend: `src/wiki_generator/libs/coverage/validate.py`, `obligations.py`

**Additive normalized fields:**

- `page_profile`
- `catalog_topic_ids[]`
- `required_content_blocks[]`
- `topic_evidence_requirements[].catalog_topic_id`
- `topic_evidence_requirements[].content_block_id`
- `known_gaps[]` with source-derived defer reasons

**Gates:**

- catalog coverage gate;
- hierarchy gate;
- page profile gate;
- content-block obligation gate;
- exact source obligation gate;
- benchmark isolation gate;
- artifact freshness gate.

### 7.4 Relevant source map

**Responsibility:** Select deterministic per-page source handles before Phase 3 retrieval.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/source_selection.py`
- Existing to extend: `coverage/substrate.py`, `coverage/obligations.py`, `plan_normalization/normalize.py`

**Output:** `plans/relevant-source-map.json`.

**Selection inputs:** topic catalog, normalized SectionPlan/PagePlan, exact handles, chunks/spans, citeable substrate, page profile requirements.

**Selection rules:**

- Prefer exact handles that are citeable and profile-relevant.
- Preserve source-field mapping to content blocks/topics.
- Include files, symbols, spans/chunks, contracts, tests, docs, configs, and runtime handles where available.
- Treat broad recall as context only.
- Fail if a blocking topic/content block lacks selected exact citeable handles.

### 7.5 Phase 3 profile-aware evidence portfolios

**Responsibility:** Retrieve and validate evidence per page/topic/content block.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/evidence/options.py`
- Existing to modify: `src/wiki_generator/libs/evidence/aggregate.py`
- Existing to modify: `src/wiki_generator/libs/evidence/evidenced_coverage.py`
- Existing to modify: `src/wiki_generator/libs/evidence/query_text.py`
- Existing lanes to extend if needed: `src/wiki_generator/libs/evidence/lanes/*.py`

**Behavior:**

- Consume `plans/relevant-source-map.json` and normalized TERs.
- Apply profile-specific evidence floors.
- Preserve statuses: `sufficient`, `weak`, `missing`, `not_applicable`.
- Fail enhancement mode before Phase 4 on weak/missing blocking obligations.
- Do not synthesize evidence or retry retrieval with LLM help.

### 7.6 Phase 4 grounded page rendering

**Responsibility:** Render expanded pages from validated claim/token plans.

**Likely modules:**

- Existing to modify: `src/wiki_generator/libs/writing/packet.py`
- Existing to modify: `src/wiki_generator/libs/writing/prompt.py`
- Existing to modify: `src/wiki_generator/libs/writing/claim_plan.py`
- Existing to modify: `src/wiki_generator/libs/writing/grounded.py`
- Existing to modify: `src/wiki_generator/libs/writing/token_bank.py`
- Existing to modify: `src/wiki_generator/libs/writing/generated_coverage.py`
- Existing to modify: `src/wiki_generator/libs/writing/validate.py`
- Existing to modify: `src/wiki_generator/libs/writing/assemble.py`

**Behavior:**

- WritingPacket includes page profile, content blocks, catalog topics, relevant source map rows, evidenced topic/block rows, and allowed evidence IDs.
- Claim plan groups claims by content block and topic.
- Deterministic renderer substitutes exact tokens and attaches evidence citations.
- Generated coverage validates both `covered_topics[]` and `covered_content_blocks[]` or derives block coverage from accepted claim groups.
- Existing validators run after rendering.

### 7.7 Traceability and metrics

**Responsibility:** Prove coverage lineage and produce source-derived metrics.

**Likely modules:**

- Inferred new: `src/wiki_generator/libs/coverage/traceability.py`
- Inferred new or extended: `src/wiki_generator/libs/coverage/metrics.py`
- Existing to extend: `src/wiki_generator/libs/commands/validate_coverage.py`

**Outputs:**

- `coverage/coverage-traceability.json`
- `coverage/coverage-traceability-report.md`
- optional benchmark-only comparison report outside evidence gates.

---

## 8. Data Contracts and Artifacts

### 8.1 Topic catalog

Path: `derived/topic-catalog.json`
Schema: `deepwiki-topic-catalog-v1`
Owner: Phase 1 catalog builder
Citeable: **false**

Required fields:

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
      "priority": "must",
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

### 8.2 Planning digest

Path: `derived/planning-topic-catalog.md`
Owner: Phase 1 condense/digest
Role: human/LLM-readable catalog summary
Citeable: **false**

It must include a loud warning: candidate paths and topic labels are planner context only; final claims must cite EvidencePacket IDs.

### 8.3 PagePlan / SectionPlan extensions

Path: `plans/section-plans.jsonl`
Owner: Phase 2 normalization
Compatibility: additive to existing SectionPlan rows

Example:

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

### 8.4 Relevant source map

Path: `plans/relevant-source-map.json`
Owner: Phase 2 normalization/source-selection gate
Role: deterministic page-level source portfolio before Phase 3

Required fields:

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
          "selection_reason": "high-signal candidate and citeable chunk/span coverage",
          "citeable": true
        }
      ]
    }
  ]
}
```

### 8.5 Evidence linkage

Path: `evidence/evidenced-coverage.json`
Owner: Phase 3 retrieval
Existing schema extended additively.

New row fields:

- `catalog_topic_id`
- `content_block_id`
- `page_profile`
- `mapped_handle_ids[]`
- `portfolio_requirements[]`
- `portfolio_status`

### 8.6 Generated coverage

Path: `wiki/metadata/generated-coverage.json`
Owner: Phase 4 writing/assembly

Extend existing generated coverage with:

- page profile;
- content block rows;
- catalog topic IDs;
- generated anchors;
- local citation status;
- topic/block coverage statuses.

### 8.7 Coverage traceability

Path: `coverage/coverage-traceability.json`
Schema: `deepwiki-coverage-traceability-v1`
Owner: validation/coverage command

Example row:

```json
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
```

---

## 9. CLI, Wrapper, and API Behavior

### 9.1 Compatibility strategy

- `baseline` mode remains non-breaking.
- Existing `--coverage-mode enhancement` remains the expanded-coverage enforcement mode.
- New artifacts are additive and ignored by baseline runs.
- Existing `section_id` remains the canonical implementation ID.
- Existing Vertex/Gemini provider path remains official for final live validation.

### 9.2 Expected command behavior

#### `condense` / `digest` / `bundle`

- Generate and include `derived/topic-catalog.json` and `derived/planning-topic-catalog.md`.
- Mark catalog as non-citeable planner context.
- Do not upload raw indexes beyond existing bundle policy.

#### `normalize-plan --coverage-mode enhancement`

- Read the topic catalog.
- Normalize PagePlan/SectionPlan fields.
- Validate hierarchy, page profiles, content blocks, topic obligations, and benchmark isolation.
- Produce `plans/relevant-source-map.json`.
- Fail before Phase 3 if catalog/page/source obligations are incomplete.

#### `retrieve-evidence --coverage-mode enhancement`

- Require a current normalized plan and relevant-source map.
- Retrieve evidence deterministically for every planned page.
- Enforce profile-aware topic/content-block sufficiency.
- Fail before Phase 4 on weak/missing blocking obligations.

#### `write-wiki --coverage-mode enhancement --grounded-claim-plan`

- Refuse provider calls unless Phase 2 and Phase 3 enhancement gates are current and passing.
- Render pages from grounded claim/token plans.
- Validate generated topics/content blocks and citations.
- Preserve nested hierarchy in `wiki/index.md` and metadata.

### 9.3 Exit-code compatibility

Preserve existing exit categories where possible:

- `0`: pass/prepared.
- `2`: bad/missing input artifact.
- `3`: upstream gate failure or underspecified plan/evidence before writing.
- `4`: provider failure.
- `5`: writing validation failure.
- `1`: implementation bug.

---

## 10. Runtime Behavior and Failure Paths

### 10.1 Happy path

1. Phase 1 builds deterministic repo artifacts.
2. Catalog builder emits source-derived topic catalog and planner markdown.
3. Planner creates hierarchical pages from catalog candidates and exact handles.
4. Normalizer resolves plan fields, writes source map, and gates plan/source obligations.
5. Phase 3 retrieves page evidence and validates profile-aware sufficiency.
6. Phase 4 creates token banks, gets/validates claim plans, renders Markdown, and validates generated coverage.
7. Traceability command proves catalog→plan→source→evidence→output lineage.
8. Optional benchmark comparison reports breadth gaps without influencing evidence or output.

### 10.2 Failure paths

| Failure | Phase | Behavior |
| --- | --- | --- |
| Catalog missing in enhancement mode | Phase 2 | Fail before normalization/planning gate completion. |
| High-signal topic unplanned without defer reason | Phase 2 | Catalog coverage gate fail. |
| Broad parent page used to satisfy child topic | Phase 2 | Hierarchy/content-block gate fail. |
| Required block lacks exact source obligation | Phase 2 | Topic/block obligation gate fail. |
| Selected source handle is stale or unciteable | Phase 2 | Relevant source map gate fail. |
| Required evidence weak/missing | Phase 3 | Fail before Phase 4. |
| Upstream gates absent/baseline/stale | Phase 4 | Pre-provider gate failure; no model call. |
| Claim plan invents terminal token | Phase 4 | Claim-plan validation failure; bounded claim-plan repair only if configured. |
| Generated page omits evidenced obligation | Phase 4 | Writing-validation failure. |
| Benchmark material appears as evidence/output seed | Validation | Gate failure; no patching. |

---

## 11. Validation and Evaluation Design

### 11.1 Gates

| Gate | Owner | Acceptance |
| --- | --- | --- |
| Catalog gate | Phase 1/2 | Catalog is source-derived, deterministic, non-citeable, and covers/defer high-signal topics. |
| Planning gate | Phase 2 | Plan has hierarchy, profiles, blocks, topics, and exact source obligations. |
| Source-selection gate | Phase 2 | Every blocking topic/block has deterministic relevant source handles. |
| Evidence sufficiency gate | Phase 3 | Every blocking topic/block has sufficient citeable evidence. |
| Grounded rendering gate | Phase 4 | Claim plans validate before Markdown rendering. |
| Generated coverage gate | Phase 4 | Every evidenced obligation appears with valid local citations. |
| Validator gate | Phase 4/final | Existing strict validators pass. |
| Freshness gate | Downstream consumers | PASS artifacts fingerprint consumed plan/evidence/source map. |
| Benchmark isolation gate | Validation | Benchmark remains comparator-only and excluded from evidence/output. |
| Traceability gate | Coverage command | Full lineage exists or deferral is explicit and justified. |

### 11.2 Evaluation metrics

Source-derived metrics:

- planned/evidenced/generated topic and content-block counts;
- per-page citation quality;
- high-signal facet coverage;
- page profile completeness;
- source-selection completeness;
- artifact freshness;
- known-gap count and reasons;
- language/runtime surface coverage for frontend, Go/native, deployment, API, tests, configs, operations.

Comparator-only metrics:

- generated-vs-benchmark page/heading/word scale;
- qualitative structure gaps by family;
- no copied headings/prose/claims;
- no benchmark-derived evidence IDs.

### 11.3 Test strategy

- Unit tests for catalog detectors, page profiles, source selection, and traceability.
- Phase 2 fixture tests for hierarchy, block requirements, source obligations, and negative cases.
- Phase 3 fixture tests for profile-aware evidence portfolios and broad-only failures.
- Phase 4 fake-provider tests for grounded block rendering and generated coverage failures.
- Non-live hierarchical E2E before any live provider run.
- Live Vertex/Gemini validation only after explicit approval.

---

## 12. Quality Attributes

| Attribute | Target | Design support |
| --- | --- | --- |
| Grounding | All repo-specific claims cite valid EvidencePacket IDs. | Phase 3 evidence sufficiency + grounded claim/token rendering. |
| Determinism | Same inputs produce same deterministic artifacts. | Catalog/source/evidence/validation are LLM-free and timestamp-free. |
| Traceability | Every blocking topic/block has lineage to output. | `coverage-traceability.json`. |
| Breadth | High-signal facets become pages or explicit gaps. | Topic catalog and page-profile gates. |
| Citation integrity | Zero malformed/unresolved/context citations. | Existing strict validators preserved. |
| Usability | Nested navigation and reader paths. | Hierarchical index and metadata. |
| Failure transparency | Diagnostics name page/topic/block/source/evidence issue. | Gate diagnostics and reports. |
| Repair discipline | No generic healing. | Repair only LLM-authored plan/claim artifacts with caps and audits. |
| Benchmark safety | No benchmark leakage. | Comparator isolation and validation. |

---

## 13. Alternatives Considered and Trade-Offs

| Alternative | Decision | Reason |
| --- | --- | --- |
| Ask Phase 4 to write longer pages | Rejected | Does not create missing page/source/evidence obligations. |
| Copy benchmark hierarchy/headings | Rejected | Violates comparator-only rule. |
| Use only 13 mandatory families | Rejected | Too coarse; can still compress child topics. |
| Replace deterministic retrieval with LLM retrieval | Rejected | Violates Phase 3 determinism. |
| Relax validators | Rejected | Would make expanded breadth untrustworthy. |
| Hard-code a 62-page target | Rejected | Page count must follow source-derived catalog. |
| Build Tree-sitter/SCIP/graph stack first | Deferred | Useful later, but not required for first catalog slice. |
| Add separate `select-sources` command | Deferred | Integrating source map into enhancement normalization is more compatible; separate command can be added if implementation size demands it. |

---

## 14. Architecture Decisions

ADR 0001 is accepted: expanded coverage is represented as a repository-derived hierarchical topic catalog.

Decision summary:

- The catalog is generated before Phase 2.
- It is planner context and non-citeable.
- It constrains page planning, source selection, evidence, rendering, and traceability.
- Existing SectionPlan artifacts are extended additively for compatibility.
- Benchmark material remains comparator-only.

---

## 15. Implementation Plan, Milestones, and Tests

### Milestone A — Catalog foundation, shadow mode

- Add deterministic topic catalog builder and markdown digest.
- Include catalog in planner upload package.
- Tests: new `tests/test_coverage_facets.py`; extend `test_coverage_signals.py`, `test_phase1.py`.

### Milestone B — Hierarchical planning contract and gates

- Extend planner prompts and normalization fields.
- Add page profile/content-block gates.
- Tests: new `tests/test_phase2_topic_catalog_planning.py`; extend Phase 2 coverage/gate/obligation tests.

### Milestone C — Relevant-source map

- Add deterministic page-level source selection.
- Write `plans/relevant-source-map.json` with freshness fingerprints.
- Tests: new `tests/test_relevant_source_map.py`; extend Phase 2/3 tests.

### Milestone D — Evidence portfolios

- Extend Phase 3 evidenced coverage for page profiles and content blocks.
- Tests: new `tests/test_phase3_evidence_portfolios.py`; extend Phase 3 tests.

### Milestone E — Grounded page rendering depth

- Extend WritingPacket, prompt, claim plan, and generated coverage for content blocks.
- Tests: new `tests/test_phase4_depth_profiles.py`; extend `test_phase4_grounded.py`, `test_phase4_generated_coverage.py`, `test_phase4.py`.

### Milestone F — Traceability and non-live E2E

- Add coverage traceability and freshness gates.
- Extend non-live hierarchical E2E.
- Tests: new `tests/test_coverage_traceability.py`, `tests/test_artifact_consistency.py`; extend `test_phase_wrappers.py`.

### Milestone G — Approved live validation

- Run official Vertex/Gemini expanded coverage validation only after all non-live gates pass and user approval is explicit.
- Human review high-risk page families before default rollout.

---

## 16. Rollout, Rollback, and Operations

### 16.1 Rollout

1. Catalog shadow mode: produce catalog/report only.
2. Planning shadow mode: planner sees catalog; gates report but do not block baseline.
3. Enhancement enforcement: `--coverage-mode enhancement` blocks missing catalog/page/source obligations.
4. Family-limited expanded rendering: start with lower-risk families.
5. High-risk family rollout: deployment/config/auth/API/migrations/storage/retrieval/LLM providers/operations require human review.
6. Default decision: promote expanded behavior only after repeated clean non-live and approved live passes.

### 16.2 Rollback

- Baseline mode remains available.
- Disable expanded catalog enforcement while keeping shadow reports.
- Keep grounded claim-plan opt-in if page-profile rendering is unstable.
- Do not patch generated Markdown, manifests, or coverage rows to recover failures.
- Rerun from the owning upstream phase after fixing producer defects.

### 16.3 Operations

- Store artifact fingerprints for catalog, normalized plan, source map, evidence, generated coverage, and traceability.
- Fail downstream consumers on stale or mismatched artifacts.
- Keep audit artifacts for LLM-authored page plans and claim plans.
- Require explicit approval for any live/billed Vertex/Gemini run.
- Refresh this TDD/ADR when schemas, CLI behavior, validator policy, provider path, or rollout status changes.

---

## 17. Risks, Open Questions, and Failure Modes

### 17.1 Risks

| Risk | Mitigation |
| --- | --- |
| Page-count chasing creates filler. | Gate by source-derived topics, profiles, blocks, and evidence. |
| Benchmark leakage. | Comparator-only policy and validation. |
| Unsupported topics are over-required. | Known gaps and calibrated promotion thresholds. |
| Broad recall masks weak evidence. | Exact evidence portfolio requirements. |
| Larger hierarchy creates stale artifacts. | Fingerprints and freshness gates. |
| Writer consistency degrades across many pages. | Grounded claim/token plans and page profiles. |
| Language/runtime blind spots persist. | Add extractors in staged milestones and report low-signal gaps. |
| Repair expands into retry loops. | Repair hard caps and artifact-only scope. |
| Live provider cost/instability. | Non-live E2E first; explicit approval required. |

### 17.2 Open questions

| ID | Question | Owner |
| --- | --- | --- |
| OD-01 | What thresholds promote a catalog topic to required page/block status? | Product/engineering lead |
| OD-02 | Should expanded catalog enforcement be immediate under `--coverage-mode enhancement` or staged behind a temporary flag? | Engineering lead |
| OD-03 | Which page profiles are included in the first implementation slice? | Product/engineering lead |
| OD-04 | What human sign-off is required for high-risk page families? | Release owner/domain maintainers |
| OD-05 | When should grounded claim-plan mode become default for expanded runs? | Product/engineering lead |

### 17.3 Failure modes

- Catalog detects too many low-value topics: mitigate with promotion thresholds and `should/could` priority.
- Catalog misses a major runtime surface: add deterministic detector and fixture.
- Planner omits required catalog topic: Phase 2 gate fails; optional bounded plan repair only with exact diagnostics.
- Source map selects unciteable file: Phase 2 gate fails before Phase 3.
- Phase 3 evidence weak/missing: Phase 3 fails before Phase 4.
- Phase 4 omits a topic or block: writing validation fails.
- Benchmark content leaks into output: benchmark isolation gate fails.

---

## 18. Appendix: Glossary and References

### 18.1 Glossary

- **Catalog topic:** Stable source-derived topic candidate before planning.
- **PagePlan:** Product concept for a planned wiki page; implemented as additive SectionPlan fields for compatibility.
- **SectionPlan:** Existing normalized per-page/section JSONL row consumed by Phase 3.
- **Content block:** Required part of a page profile, such as flow, API matrix, config matrix, tests, or operations.
- **TER:** `topic_evidence_requirements[]`, the plan-to-evidence bridge for a required topic/block.
- **Relevant source map:** Deterministic per-page source selection artifact before Phase 3.
- **EvidencePacket:** Phase 3 citeable evidence packet for one planned page/section.
- **Grounded claim plan:** LLM-authored JSON claim plan validated against token bank and allowed evidence before rendering.
- **Benchmark comparator:** External DeepWiki export used only to understand breadth gaps, never as evidence.

### 18.2 References

- `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`
- `docs/product-requirements/deepwiki-coverage-expansion/artifacts/traceability_matrix.md`
- `/Users/ankitsingh/Documents/deep-wiki/reverse-engineer.md`
- `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_GPT55_XHIGH.md`
- `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_DEEP_RESEARCH.md`
- `docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md`
- `src/wiki_generator/libs/commands/*`
- `src/wiki_generator/libs/coverage/*`
- `src/wiki_generator/libs/digest/*`
- `src/wiki_generator/libs/evidence/*`
- `src/wiki_generator/libs/plan_normalization/*`
- `src/wiki_generator/libs/writing/*`
