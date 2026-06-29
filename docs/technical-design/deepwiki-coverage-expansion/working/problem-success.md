# Problem and Success Definition

## Summary

The current `wiki-generator` can produce a valid, source-grounded overview wiki, but it does not yet plan, evidence, and render DeepWiki-style breadth. The design must move coverage expansion upstream into source-derived cataloging, hierarchical planning, deterministic page-level source selection, per-page evidence sufficiency, grounded rendering, and traceability.

## Current state

- **Sourced:** The official live grounded run passed for its planned scope: 22 sections, 53/53 required topics covered, and 425 distinct citations.
- **Sourced:** The benchmark export shows a much broader hierarchy: 62 page blocks with per-page relevant source files.
- **Sourced:** The benchmark was indexed at a different commit and is comparator-only.
- **Sourced from code/spec:** Existing implementation already has enhancement-mode planned-coverage gates, topic evidence requirements, evidenced coverage, generated coverage, and an opt-in grounded claim/token plan path.
- **Inferred:** The next expansion should build on these existing gates rather than replace the Phase 1–4 pipeline.

## Problem statement

The existing coverage model can pass when all currently planned topics are covered, even if important repository subtopics were never promoted into pages, source obligations, evidence portfolios, or generated coverage rows. This is a planning and evidence granularity problem, not a Phase 4 length problem.

## Goals

| ID | Goal | Grounding |
| --- | --- | --- |
| G-01 | Build a repository-derived expanded topic/page catalog before Phase 2 planning. | Sourced: PRD UR-01 |
| G-02 | Generate a parent/child page plan with page profiles, required content blocks, and required topics. | Sourced: PRD UR-02/UR-03 |
| G-03 | Select relevant files, symbols, spans, contracts, tests, docs, and runtime surfaces per page before Phase 3. | Sourced: PRD UR-04 |
| G-04 | Keep Phase 3 deterministic while retrieving and validating evidence per page/topic/content block. | Sourced: PRD UR-05 and BR-05 |
| G-05 | Render every expanded page through the grounded claim/token plan path. | Sourced: PRD UR-06 and user request |
| G-06 | Evaluate coverage through source-derived topic→plan→evidence→output traceability. | Sourced: PRD UR-07/UR-08 |
| G-07 | Preserve strict validators and fail closed on missing, weak, stale, unsupported, or benchmark-contaminated artifacts. | Sourced: PRD UR-09/UR-10/UR-12 |

## Non-goals

| ID | Non-goal | Grounding |
| --- | --- | --- |
| NG-01 | Do not copy benchmark headings, prose, claims, citations, or page structure into generated output without repository-derived evidence. | Sourced: PRD NG-01 / BR-01 |
| NG-02 | Do not solve coverage by increasing token limits, section length, or verbosity. | Sourced: PRD NG-02 |
| NG-03 | Do not add output patching, generated Markdown mutation, synthetic evidence, generic retry loops, or silent required-to-optional downgrades. | Sourced: PRD NG-03 / BR-07 / BR-08 |
| NG-04 | Do not weaken existing validators. | Sourced: PRD NG-04 / BR-06 |
| NG-05 | Do not replace deterministic Phase 3 retrieval with LLM retrieval or fuzzy semantic acceptance. | Sourced: PRD BR-05 / evidence contract |
| NG-06 | Do not define a benchmark page-count parity target as the primary success criterion. | Sourced: PRD NG-06 |

## Future goals

- Add optional richer language/runtime extractors for Go, TypeScript/TSX, deployment, OpenAPI schema depth, and CLI/admin surfaces beyond the first catalog slice.
- Add sampled RAG-style quality evaluation for high-risk page families after deterministic gates pass.
- Calibrate catalog promotion thresholds and page count ranges from multiple real repositories.
- Decide whether grounded claim-plan mode becomes the default for all expanded coverage runs.

## Success metrics

| Metric | Target | Grounding |
| --- | --- | --- |
| Topic catalog completeness | 100% of high-signal source-derived facets planned or explicitly deferred with source-derived reason. | Sourced: PRD M-01 |
| Hierarchy completeness | Every normal source page has a parent/child placement, profile, content blocks, topics, and source obligations. | Sourced: PRD M-02 |
| Evidence sufficiency | 100% of blocking topics/content blocks sufficient before Phase 4. | Sourced: PRD M-03 |
| Generated coverage | 100% of evidenced required topics/content blocks generated with valid local citations. | Sourced: PRD M-04 |
| Citation quality | Zero unresolved citations, malformed tokens, context-artifact citations, unsupported identifiers, placeholders, or truncation defects. | Sourced: PRD M-05 |
| Artifact freshness | 100% of PASS reports fingerprint the current plan/evidence artifacts consumed downstream. | Sourced: PRD M-06 |
| Coverage breadth | Material expansion beyond 22 sections/53 topics, with first target band calibrated after the catalog; PRD suggests roughly 45–70 pages and 150–250 topics only if source support exists. | Sourced: PRD M-07 |
| Benchmark leakage | Zero benchmark-derived citeable evidence IDs, copied headings, copied prose, or benchmark-only claims. | Sourced: PRD M-08 |

## Functional requirements

| ID | Requirement | TDD treatment |
| --- | --- | --- |
| UR-01 | Build source-derived topic/page catalog. | Topic catalog component and `derived/topic-catalog.json`. |
| UR-02 | Plan hierarchical parent/child tree. | PagePlan extensions over existing SectionPlan. |
| UR-03 | Assign page profile and content blocks. | Page profile taxonomy and content-block obligations. |
| UR-04 | Deterministically select sources per page. | Relevant source map before Phase 3. |
| UR-05 | Retrieve and validate page/topic/block evidence. | Profile-aware evidence portfolios and sufficiency matrix. |
| UR-06 | Render through grounded claim-plan path. | Page-profile claim groups using existing token-bank/claim-plan renderer. |
| UR-07 | Produce planned→evidenced→generated traceability. | Coverage traceability artifact and final gate. |
| UR-08 | Evaluate source-derived coverage, not benchmark copying. | Coverage metrics and benchmark isolation gate. |
| UR-09 | Preserve strict validators. | Validator preservation requirements and tests. |
| UR-10 | Fail closed on missing/weak/stale coverage. | Gates before Phase 4 and final validation. |
| UR-11 | Record known gaps when evidence is weak/absent. | `known_gaps[]` and deferral policy. |
| UR-12 | Separate benchmark comparison from evidence gates. | Comparator-only report outside evidence paths. |
| UR-13 | Expose human-readable nested navigation. | Nested index and audience paths. |
| UR-14 | Report citation, coverage, and freshness per page. | Per-page reports and traceability matrix. |
| UR-15 | Limit bounded repair to LLM-authored plans/claim plans. | Repair discipline and audit hard caps. |

## Constraints

- **Sourced:** Phase 3 must remain deterministic and fail closed.
- **Sourced:** Benchmark material must remain comparator-only.
- **Sourced:** Strict validators must not be weakened.
- **Sourced:** Output patching and generic healing are forbidden.
- **Sourced:** Official final provider path remains Vertex/Gemini.
- **Inferred:** Existing baseline mode should remain non-breaking.
- **Inferred:** Existing `section_id` can remain the canonical ID while `page_id` becomes an alias/semantic label in expanded mode.

## Assumptions

- **Sourced:** Repository-derived signals can identify enough high-value facets to justify deeper hierarchy.
- **Sourced:** Grounded claim-plan rendering can scale to per-page generation while preserving strict validation.
- **Inferred:** Existing coverage signal and topic-obligation modules are the right seams for a catalog and content-block extension.
- **Open:** Promotion thresholds and initial page-profile set require calibration during implementation.

## Dependencies

- Existing Phase 1 artifacts: inventory, symbols, contracts, tests, query packs, runtime surfaces, handles, chunks, spans.
- Existing Phase 2 normalization and enhancement gates.
- Existing Phase 3 EvidencePacket, exact-request coverage, and evidenced coverage artifacts.
- Existing Phase 4 WritingPacket, token bank, claim plan, generated coverage, and validators.
- Existing CLI wrappers and scripts for non-live and official live E2E flows.
