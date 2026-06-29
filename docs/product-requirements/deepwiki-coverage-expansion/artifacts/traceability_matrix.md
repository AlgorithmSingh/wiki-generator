# Traceability Matrix — DeepWiki Coverage Expansion PRD

## Source IDs

| ID | Source |
| --- | --- |
| SRC-USER | Captured user request in `input.md`. |
| SRC-PRD-GUIDE | PRD Companion Round 2 phase guide. |
| SRC-REV | `reverse-engineer.md`. |
| SRC-COMP | `GPT55_XHIGH_BENCHMARK_COMPARISON.md`. |
| SRC-COVX | `COVERAGE_EXPANSION_GPT55_XHIGH.md`. |
| SRC-DR | `COVERAGE_EXPANSION_DEEP_RESEARCH.md`. |
| SRC-E2E | `OFFICIAL_LIVE_E2E_RESULT.md`. |
| SRC-GENCOV | `wiki/metadata/generated-coverage.json`. |
| SRC-CITMAN | `wiki/metadata/citation-manifest.json`. |
| SRC-SPEC | `PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md`. |
| SRC-HANDOFF | `HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md`. |

## Acceptance criteria IDs

| ID | Acceptance criterion |
| --- | --- |
| AC-01 | Catalog is derived from repository signals and excludes benchmark-only evidence. |
| AC-02 | Hierarchical page plan includes parent/child links, stable IDs, page profiles, required content blocks, and required topics. |
| AC-03 | Each planned page has deterministic relevant source selections before Phase 3. |
| AC-04 | Every blocking required topic/content block has sufficient citeable evidence before Phase 4. |
| AC-05 | Expanded pages are rendered from validated grounded claim plans. |
| AC-06 | Generated coverage maps every evidenced obligation to Markdown anchors and local citations. |
| AC-07 | Strict validators remain unchanged or stricter. |
| AC-08 | Benchmark comparison remains separate and comparator-only. |
| AC-09 | Known gaps are explicit when source evidence is weak/missing. |
| AC-10 | Bounded repair is limited to LLM-authored plan/claim-plan artifacts with diagnostics and hard caps. |
| AC-11 | Artifact lineage/freshness prevents stale gate artifacts from passing downstream sign-off. |
| AC-12 | Human navigation preserves hierarchy and supports reader/audience paths. |
| AC-13 | Coverage metrics report planned, evidenced, and generated status by page/topic/facet/content block. |

## Evaluation gate IDs

| ID | Evaluation gate |
| --- | --- |
| VG-01 | Catalog gate. |
| VG-02 | Planning gate. |
| VG-03 | Source-selection gate. |
| VG-04 | Evidence sufficiency gate. |
| VG-05 | Grounded rendering gate. |
| VG-06 | Generated coverage gate. |
| VG-07 | Validator gate. |
| VG-08 | Artifact freshness gate. |
| VG-09 | Benchmark isolation gate. |
| VG-10 | Traceability gate. |

## Requirement traceability

| Requirement | Sources | Acceptance criteria | Evaluation gates | Notes |
| --- | --- | --- | --- | --- |
| UR-01 — Build repository-derived expanded topic/page catalog | SRC-USER, SRC-REV, SRC-COVX, SRC-DR, SRC-SPEC, SRC-HANDOFF | AC-01, AC-09, AC-13 | VG-01, VG-10 | Addresses missing ingredient: repo-derived page/subtopic discovery. |
| UR-02 — Plan hierarchical parent/child page tree | SRC-USER, SRC-REV, SRC-COMP, SRC-COVX, SRC-DR, SRC-SPEC | AC-02, AC-12 | VG-02, VG-10 | Moves beyond the current 22 broad sections. |
| UR-03 — Assign page profiles and content blocks | SRC-COVX, SRC-DR, SRC-SPEC | AC-02, AC-13 | VG-02, VG-06 | Prevents shallow one-paragraph pages by requiring page-appropriate structure. |
| UR-04 — Deterministically select sources per page | SRC-USER, SRC-REV, SRC-COVX, SRC-DR, SRC-SPEC | AC-03 | VG-03, VG-04 | Mirrors benchmark observation of per-page relevant source files without copying benchmark content. |
| UR-05 — Retrieve and validate page/topic evidence before writing | SRC-USER, SRC-COVX, SRC-DR, SRC-E2E, SRC-SPEC, SRC-HANDOFF | AC-04 | VG-04, VG-07 | Preserves deterministic Phase 3 retrieval and fail-closed evidence sufficiency. |
| UR-06 — Use grounded claim-plan rendering per page | SRC-USER, SRC-E2E, SRC-SPEC, SRC-HANDOFF | AC-05, AC-07 | VG-05, VG-07 | Keeps Phase 4 as grounded renderer, not a coverage inventor. |
| UR-07 — Produce planned/evidenced/generated traceability | SRC-PRD-GUIDE, SRC-COVX, SRC-DR, SRC-GENCOV, SRC-SPEC | AC-06, AC-13 | VG-06, VG-10 | Extends existing generated-coverage matrix to deeper page/topic obligations. |
| UR-08 — Evaluate source-derived coverage, not benchmark copying | SRC-USER, SRC-COMP, SRC-COVX, SRC-DR, SRC-REV | AC-08, AC-13 | VG-09, VG-10 | Benchmark is breadth dashboard only. |
| UR-09 — Preserve strict validators | SRC-USER, SRC-COMP, SRC-E2E, SRC-CITMAN, SRC-SPEC, SRC-HANDOFF | AC-07 | VG-07 | Required by user constraints and current pipeline guardrails. |
| UR-10 — Fail closed on missing/weak/stale coverage | SRC-PRD-GUIDE, SRC-COVX, SRC-DR, SRC-SPEC, SRC-HANDOFF | AC-04, AC-07, AC-11 | VG-04, VG-07, VG-08 | Prevents output patching and false PASS states. |
| UR-11 — Record known gaps instead of invention | SRC-COVX, SRC-DR, SRC-SPEC | AC-09 | VG-01, VG-04, VG-10 | Keeps unsupported topics explicit and non-blocking only when justified. |
| UR-12 — Separate benchmark comparison from evidence gates | SRC-USER, SRC-REV, SRC-COMP, SRC-COVX, SRC-DR | AC-08 | VG-09 | Enforces benchmark-only rule and commit mismatch caveat. |
| UR-13 — Human-readable nested navigation | SRC-REV, SRC-COMP, SRC-COVX, SRC-DR | AC-12 | VG-02, VG-06 | Supports DeepWiki-style drill-down and audience paths. |
| UR-14 — Report citation, coverage, and freshness per page | SRC-COMP, SRC-GENCOV, SRC-CITMAN, SRC-COVX, SRC-SPEC | AC-06, AC-11, AC-13 | VG-06, VG-07, VG-08 | Builds on existing generated coverage and citation manifest artifacts. |
| UR-15 — Limit bounded repair to LLM-authored artifacts | SRC-USER, SRC-SPEC, SRC-HANDOFF, SRC-PRD-GUIDE | AC-10 | VG-05, VG-07, VG-08 | Allows exact-diagnostic repair only for plans/claim plans; forbids generic healing. |

## Business rule traceability

| Rule | Sources | Acceptance/gates |
| --- | --- | --- |
| BR-01 Benchmark is comparator-only | SRC-USER, SRC-REV, SRC-COMP, SRC-COVX, SRC-DR | AC-08, VG-09 |
| BR-02 Repository evidence outranks benchmark breadth | SRC-USER, SRC-REV, SRC-COVX, SRC-DR | AC-01, AC-08, VG-01, VG-09 |
| BR-03 Parent pages do not satisfy child obligations | SRC-USER, SRC-COVX, SRC-DR, SRC-SPEC | AC-02, AC-06, VG-02, VG-06 |
| BR-04 Broad recall cannot be sole precise support | SRC-COVX, SRC-DR, SRC-SPEC, SRC-HANDOFF | AC-04, VG-04 |
| BR-05 Phase 3 retrieval remains deterministic | SRC-USER, SRC-E2E, SRC-SPEC, SRC-HANDOFF | AC-04, VG-04 |
| BR-06 Validators remain strict | SRC-USER, SRC-E2E, SRC-CITMAN, SRC-SPEC | AC-07, VG-07 |
| BR-07 No output patching | SRC-USER, SRC-COVX, SRC-DR, SRC-SPEC | AC-07, VG-07 |
| BR-08 No generic heal/retry loops | SRC-USER, SRC-SPEC, SRC-HANDOFF | AC-10, VG-05, VG-07 |
| BR-09 Artifact freshness required | SRC-COVX, SRC-SPEC, SRC-HANDOFF | AC-11, VG-08 |
| BR-10 Expansion bounded by evidence, not line count | SRC-USER, SRC-COMP, SRC-COVX, SRC-DR | AC-01, AC-04, VG-01, VG-04 |
| BR-11 Known gaps explicit | SRC-COVX, SRC-DR, SRC-SPEC | AC-09, VG-01, VG-04 |
| BR-12 Machine-readable and human-readable auditability | SRC-PRD-GUIDE, SRC-GENCOV, SRC-CITMAN, SRC-SPEC | AC-06, AC-13, VG-06, VG-10 |

## Source fact traceability

| Fact used in PRD | Source |
| --- | --- |
| Current official generated wiki has 22 sections and 53/53 covered required topics. | SRC-E2E, SRC-GENCOV, SRC-COMP |
| Current citation manifest has 425 distinct citations and 725 total occurrences. | SRC-CITMAN, SRC-COMP, SRC-E2E |
| Benchmark export has 62 page blocks with per-page relevant source files. | SRC-REV, SRC-COMP |
| Benchmark was indexed at commit `d32e05d5`; local runs used different commits, so benchmark headings are breadth signals only. | SRC-REV, SRC-USER |
| Coverage expansion should target planning/source selection/evidence obligations upstream, not longer Phase 4 prose. | SRC-USER, SRC-COVX, SRC-DR, SRC-SPEC |
| Existing enhancement contracts already include planned coverage, evidenced coverage, generated coverage, and grounded claim-plan rendering. | SRC-SPEC, SRC-HANDOFF |
| Bounded repair is allowed only for LLM-authored plans/claim plans with exact diagnostics and hard caps. | SRC-USER, SRC-SPEC, SRC-HANDOFF |

## Traceability findings

- All Must requirements have at least one source, acceptance criterion, and validation gate.
- Benchmark-only material is traced only to comparator/business-rule requirements, not to source-evidence requirements.
- No requirement proposes output patching, synthetic evidence, generic healing, or validator weakening.
