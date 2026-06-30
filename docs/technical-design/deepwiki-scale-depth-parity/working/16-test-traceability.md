# Test Traceability — deepwiki-scale-depth-parity

Every requirement and success metric maps to a concrete test. New tests live in
`tests/test_phase4_depth_budget.py` (stdlib `unittest`, deterministic, no live model),
plus non-regression of the existing suites.

| Requirement / SM | Test | Method |
|---|---|---|
| FR1, SM7, DoD1 | `DepthPolicyTests::test_bounds_validated`, `test_topic_target_clamps` | unit |
| FR2, SM2/SM5 | `DeriveBudgetTests::test_per_topic_target_from_mapped_evidence`, `test_section_floor_is_sum_of_targets` | unit |
| FR2 edge | `DeriveBudgetTests::test_single_mapped_evidence_target_is_one` (SM3) | unit |
| FR3, SM1 | `DepthGateTests::test_shallow_plan_fails_topic_underfilled` | unit |
| FR3, SM2 | `DepthGateTests::test_detailed_plan_passes` | unit |
| FR3 | `DepthGateTests::test_section_underfilled_backstop`, `test_content_block_omission_left_to_generated_coverage` (depth gate does NOT preempt the generated-coverage content-block gate — repair R6) | unit |
| FR3 safety | `DepthGateTests::test_depth_check_does_not_mutate_claims`, `test_none_budget_is_byte_identical` | unit |
| FR3 ordering | `DepthGateTests::test_grounding_violation_still_reported_with_depth` | unit |
| FR4, DoD4, SM5 | `DepthPromptTests::test_prompt_carries_per_topic_targets`, `test_prompt_has_no_benchmark_string` | unit |
| FR5, SM6, DoD5 | `DepthGroundedE2ETests::test_expanded_grounded_records_depth_audit`, `test_expanded_grounded_shallow_fails_closed` | integration (fake provider / gem import, non-live) |
| FR6, SM5 | `DeriveBudgetTests::test_rerun_byte_identical` | unit |
| C5, SM4, DoD3 | `DepthGateTests::test_baseline_enhancement_compute_no_budget`; existing `tests/test_phase4_grounded.py`, `tests/test_phase4_generated_coverage.py` (incl. `ops` expanded E2E), `tests/test_deepwiki_scale_core.py`, `tests/test_phase2_anti_compression.py` | regression |
| C2, DoD3 | full suite `uv run python -m pytest -q` | regression |
| C3, C4, DoD6 | `git diff --exit-code` on the protected spec; `grep` no comparator import in `src/` | gate check |
| C6, DoD7 | `.sequence/static-analysis.json` (py_compile, mutable-default scan, import-time scan, layer scan); `git diff --check` | static |

## Evidence not claimed

No live-model evidence is claimed this slice. The depth gate's effect on a real billed run is
deferred to M3 and is **not** asserted here. The non-live integration tests prove the gate
fires and the audit records depth; they do not prove the live planner reaches the budget.
