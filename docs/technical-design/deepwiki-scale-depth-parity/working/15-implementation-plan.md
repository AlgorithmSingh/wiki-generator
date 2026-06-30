# Implementation Plan & Milestones — deepwiki-scale-depth-parity

## M1 — Source-derived depth budget + claim-plan depth gate (THIS slice)

Ordered steps (each maps to the Python build-sequence writing stages):

1. **New module** `libs/writing/depth_budget.py`: `DepthPolicy` (frozen, validated),
   `topic_target`, `TopicDepthTarget`/`BlockDepthTarget`/`SectionDepthBudget`,
   `DepthShortfall`/`PlanDepthReport`, `derive_section_depth_budget`, `evaluate_plan_depth`,
   `render_depth_budget_lines`, schema + defect-code constants.
2. **Wire validator** `claim_plan.validate_claim_plan(..., depth_budget=None)`: append depth
   violations after existing checks.
3. **Wire prompt** `claim_plan.build_claim_plan_prompt` / `build_claim_plan_rewrite_prompt`
   (`depth_budget=None`): insert guidance lines; harden the system instruction.
4. **Wire loop** `grounded.generate_grounded_section(..., depth_budget=None)`: thread into
   both validate calls + the rewrite prompt; add `grounded_meta["depth"]`.
5. **Wire orchestrator** `writing.run()`: compute `depth_budgets[sid]` for expanded grounded
   mode; pass into the prompt build and `generate_grounded_section`.
6. **Tests** `tests/test_phase4_depth_budget.py`: policy bounds, derivation, shortfall codes,
   shallow-fails / detailed-passes / single-evidence-passes, rerun determinism, no-benchmark,
   prompt-carries-budget, baseline/enhancement untouched.

**Definition of M1 done:** shallow plan fails, detailed plan passes, single-mapped-evidence
topic passes, existing suites green, static checks clean, protected spec unchanged.

## M2 — Heading-density depth (follow-up, not this slice)

Content-block-level `####` headings in `render_section` with the block's own anchor, and an
updated `_derive_covered_content_blocks`, validated against the content-block-coverage
evaluator. Plus a document-level depth dashboard (generated vs benchmark, comparison-only).

## M3 — Live confirmation (separately approved)

A billed RAGFlow run confirming the planner reaches the depth budget on the real catalog,
with release-owner sign-off on `DepthPolicy` defaults.

## Sequencing / dependencies

M1 has no external dependency (reads only in-memory Phase 4 data). M2 depends on M1's budget.
M3 depends on M1 + M2 + sign-off. Validation gate for M1: the focused + full pytest suites
and the static checks, all non-live.
