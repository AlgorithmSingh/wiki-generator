# Execution Readiness

## Implementation phases

### Phase A — Catalog foundation, shadow mode

**Goal:** Build source-derived topic catalog artifacts without enforcing them on production runs.

**Likely work:**

- Add inferred modules `coverage/facets.py`, `coverage/topic_catalog.py`, and `digest/planning_topic_catalog.py`.
- Extend `condense`, `digest`, and `bundle` to write/include `derived/topic-catalog.json` and `derived/planning-topic-catalog.md`.
- Mark catalog artifacts as planner context and non-citeable.
- Add deterministic tests for catalog extraction from files, symbols, contracts, tests, configs, deployment, frontend, Go, and docs fixtures.

**Validation:**

- `tests/test_coverage_facets.py` (new/inferred).
- Extend `tests/test_coverage_signals.py` and `tests/test_phase1.py`.
- JSON determinism test: rerun on same fixture produces byte-identical catalog.

### Phase B — Hierarchical planning contract and gates

**Goal:** Make Phase 2 plan from catalog topics into parent/child pages with profiles, blocks, topics, and exact obligations.

**Likely work:**

- Update planner prompts and Gemini Gem instructions.
- Extend plan normalization for `page_profile`, `catalog_topic_ids[]`, `required_content_blocks[]`, and TER block/topic IDs.
- Add catalog coverage gate, hierarchy gate, page-profile completeness gate, and content-block obligation gate.
- Keep baseline mode non-breaking.

**Validation:**

- New `tests/test_phase2_topic_catalog_planning.py`.
- Extend `tests/test_phase2_coverage_planning.py`, `tests/test_phase2_enhancement_gate.py`, `tests/test_phase2_obligation_gate.py`, and `tests/test_plan_truncation.py`.
- Negative fixtures: broad parent-only plan, missing page profile, missing content block, broad-only source fields, invalid parent cycle.

### Phase C — Relevant-source map before Phase 3

**Goal:** Deterministically select per-page file/symbol/span/contract/test/doc handles before retrieval.

**Likely work:**

- Add inferred `coverage/source_selection.py`.
- Write `plans/relevant-source-map.json` and report from enhancement normalization.
- Fingerprint catalog + plan + source map.
- Extend topic-obligation gate to require source-map coverage for blocking topics/blocks.

**Validation:**

- New `tests/test_relevant_source_map.py`.
- Extend `tests/test_phase2_obligation_gate.py` and `tests/test_phase3_evidenced_coverage.py`.
- Negative fixtures: stale source map, unciteable selected path, missing selected handle for required block.

### Phase D — Profile-aware evidence portfolios

**Goal:** Phase 3 retrieves and validates sufficient evidence per page/topic/content block.

**Likely work:**

- Extend `evidence/evidenced_coverage.py`, `evidence/options.py`, `evidence/aggregate.py`, and lane reporting.
- Add profile-aware floors and `portfolio_requirements` in evidenced coverage.
- Preserve deterministic Phase 3 and existing exit-code behavior.

**Validation:**

- New `tests/test_phase3_evidence_portfolios.py`.
- Extend `tests/test_phase3.py` and `tests/test_phase3_evidenced_coverage.py`.
- Negative fixtures: API block with route but no handler/test, config block with only broad recall, deployment block missing citeable compose/Helm source.

### Phase E — Grounded page-profile rendering

**Goal:** Phase 4 renders expanded pages through grounded claim/token plans with content-block coverage validation.

**Likely work:**

- Extend WritingPacket to carry page profile, blocks, catalog topics, source map, and portfolio rows.
- Extend claim-plan schema to group claims by `content_block_id` and required topic.
- Extend generated coverage to validate `covered_content_blocks[]` in addition to `covered_topics[]`.
- Preserve existing strict validators and bounded claim-plan repair.

**Validation:**

- New `tests/test_phase4_depth_profiles.py`.
- Extend `tests/test_phase4_grounded.py`, `tests/test_phase4_generated_coverage.py`, and `tests/test_phase4.py`.
- Negative fixtures: covered topic but missing block, uncited table, out-of-scope evidence ID, unsupported token, malformed citation.

### Phase F — Traceability, freshness, and non-live E2E

**Goal:** Prove catalog→plan→source→evidence→output traceability and artifact freshness end-to-end without live/billed calls.

**Likely work:**

- Add inferred `coverage/traceability.py` and/or `coverage/metrics.py`.
- Write `coverage/coverage-traceability.json` and report.
- Extend artifact lineage/freshness checks.
- Add/extend non-live hierarchical E2E harness.
- Keep benchmark comparison outside evidence gates.

**Validation:**

- New `tests/test_coverage_traceability.py` and `tests/test_artifact_consistency.py`.
- Extend `tests/test_phase_wrappers.py`.
- Run non-live E2E with fake provider and deterministic responses.

### Phase G — Controlled live validation and rollout

**Goal:** Validate the official production provider path after non-live gates pass and explicit approval is granted.

**Likely work:**

- Run Vertex/Gemini only with explicit approval.
- Compare to benchmark as breadth dashboard only.
- Human review high-risk page families.
- Decide whether to promote expanded catalog enforcement to default enhancement mode.

## Test traceability

| Requirement area | Tests |
| --- | --- |
| Topic catalog and benchmark isolation | `test_coverage_facets.py`, `test_coverage_signals.py` |
| Hierarchical planning/profile completeness | `test_phase2_topic_catalog_planning.py`, existing Phase 2 coverage/gate tests |
| Source selection before Phase 3 | `test_relevant_source_map.py`, Phase 2 obligation tests |
| Evidence portfolios | `test_phase3_evidence_portfolios.py`, Phase 3 evidenced coverage tests |
| Grounded rendering and generated coverage | `test_phase4_depth_profiles.py`, Phase 4 grounded/generated coverage tests |
| Artifact freshness and traceability | `test_coverage_traceability.py`, `test_artifact_consistency.py` |
| CLI/wrapper compatibility | `test_phase_wrappers.py`, CLI parser checks |
| No output patching / no generic repair loops | Negative integration tests across Phase 2/4 repair paths |

## Rollout plan

1. **Catalog shadow mode:** Generate catalog and reports, no gating.
2. **Planning shadow mode:** Ask planner to use catalog; gate reports but do not block baseline.
3. **Enhancement enforced mode:** Block `--coverage-mode enhancement` when catalog/page/profile/source-selection gates fail.
4. **Family-limited expanded rendering:** Enable grounded expanded rendering for lower-risk families first.
5. **High-risk family rollout:** Add deployment/config/auth/API/migrations/storage/retrieval/LLM provider pages after human review.
6. **Default decision:** Promote expanded catalog path to default enhancement behavior only after repeated non-live and approved live passes.

## Rollback plan

- Baseline mode remains available and non-breaking.
- If expanded catalog gates are noisy, disable enforcement while keeping catalog reports in shadow mode.
- If Phase 4 grounded profile rendering is unstable, keep `--grounded-claim-plan` opt-in and fall back to existing strict freeform path only for baseline runs, not for expanded sign-off.
- Do not patch generated output to recover a failed expanded run; rerun from the owning phase after fixing the producer.

## Operations and maintenance

- Every enforced PASS artifact must fingerprint the exact upstream artifacts consumed.
- TDD and ADR refresh triggers:
  - new/removed catalog artifact or schema version;
  - CLI flag behavior change;
  - validator weakening or strengthening;
  - change to live provider path;
  - new benchmark-safety or evidence-sufficiency rule;
  - rollout incident or high-risk family sign-off change.
- ADRs should be superseded, not silently rewritten, if the catalog architecture changes.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Page-count chasing creates shallow pages. | Gate by source-derived topics, page profiles, content blocks, and evidence sufficiency. |
| Benchmark leakage. | Keep benchmark comparator-only; validate no benchmark evidence, copied headings, or copied prose. |
| Over-required unsupported topics. | Use status/defer reasons and known gaps; require source-derived promotion thresholds. |
| Broad recall masks weak evidence. | Require exact lane portfolios for blocking topics/blocks. |
| Larger hierarchy creates stale artifacts. | Add lineage/freshness fingerprints and fail downstream mismatches. |
| More pages strain writer consistency. | Use page profiles and grounded claim/token plans. |
| Language/runtime blind spots. | Stage Go/TS/deployment extractors and report low-signal gaps explicitly. |
| Repair loops expand beyond bounds. | Restrict repair to LLM-authored plan/claim-plan artifacts with hard caps and audit logs. |
| Live provider cost or instability. | Use non-live fixtures until ready; live Vertex/Gemini requires explicit approval. |
