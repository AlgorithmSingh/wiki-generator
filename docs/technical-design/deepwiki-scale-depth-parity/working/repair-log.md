# Repair Log — deepwiki-scale-depth-parity (Phase 6)

The validator step raised the findings below; the repair step applied only these, without
restructuring accepted design.

| # | Validator finding | Repair applied |
|---|---|---|
| R1 | Risk that a flat per-topic minimum would break the legitimately-thin `ops` expanded grounded command E2E (1 mapped evidence id, 1 claim). | Locked the per-topic target to `clamp(ceil(mapped/evidence_per_claim), floor=1, cap)` so a 1-mapped topic targets exactly 1 claim. Added SM3 + a dedicated test. |
| R2 | Depth check could mask a grounding violation if it ran first. | Specified the depth gate runs **after** all existing grounding/required-topic checks; added an ordering test (`test_grounding_violation_still_reported_with_depth`). |
| R3 | Ambiguity on whether content-block `####` headings ship in M1. | Explicitly deferred to M2 with rationale (blast radius on the content-block-coverage evaluator); recorded in §7.4, §10 (A7), and the implementation plan. |
| R4 | DoD4 (no benchmark leakage) needed a concrete check, not an assertion. | Added `DepthPromptTests::test_prompt_has_no_benchmark_string` and a `grep` gate over `src/`. |
| R5 | "Bounded" quality attribute needed enforcement, not just intent. | Added `DepthPolicy.__post_init__` bounds validation + `max_claims_per_required_topic` cap + invalid-policy `ValueError` test. |
| R6 | **Found during implementation** (writer≠approver loop): an initial content-block depth dimension (`claim_plan_content_block_underfilled`) fired at claim-plan validation time and **preempted** the existing, well-tested generated-coverage content-block gate — the omitted-block command E2E (`test_expanded_grounded_command_omitted_block_fails_exit_5`) failed because `generated-coverage.json` was never written. | Scoped the depth gate to **per-topic claim density + section floor**. Content-block *coverage* stays the downstream generated-coverage gate's job (not duplicated/preempted); content blocks are recorded only as an informational budget count. Removed `DepthPolicy.min_claims_per_content_block`, `BlockDepthTarget`, and `CODE_BLOCK_UNDERFILLED`. Re-validated: full suite green (708 passed). This is the depth budget's novel, non-redundant contribution; content-block density (heading depth) moves to M2. |

No finding required a `revisit` to an earlier phase. The structure of the final TDD was not
rewritten; repairs were localized clarifications and added test obligations, all reflected in
the working artifacts and the final document.
