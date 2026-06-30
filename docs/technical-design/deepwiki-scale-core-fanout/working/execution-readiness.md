# Phase 5 — Execution Readiness

## Implementation plan (this slice, all delivered)

| Step | Change | Files | Validation gate |
|---|---|---|---|
| A1 | `enforces_breadth` true for expanded + deepwiki-scale; reframe mode comments | `coverage/validate.py` | unit: `test_expanded_is_core_breadth_enforcing_path` |
| A2 | Reframe gate docstrings (expanded core; alias) | `coverage/anti_compression.py`, `commands/normalize_plan.py` | full suite green |
| A3 | CLI `--coverage-mode` help: expanded core, deepwiki-scale alias | `cli.py` | manual `--help`; suite green |
| B1 | `BreadthBudget`/`FamilyBudget` + `derive_breadth_budget` + `render_breadth_budget_lines` | `coverage/anti_compression.py` | `BreadthBudgetTests` |
| B2 | Render budget into `planning-topic-catalog.md` | `coverage/topic_catalog.py` | `CatalogMarkdownBudgetTests` |
| B3 | Harden embedded prompts (system + kickoff) | `commands/plan.py` | `PlannerPromptFanOutTests` |
| B4 | Harden Gem prompt files | `gemini-gem/GEM_INSTRUCTIONS.md`, `KICKOFF_PROMPT.md` | `PlannerPromptFanOutTests` |
| C1 | `build_promoted_topic_contract` + `load_promoted_topic_contract` + `promoted_catalog_topic_ids` | `coverage/anti_compression.py` | `PromotedTopicContractTests` |
| C2 | Emit `plans/promoted-topic-contract.json` from normalize-plan | `commands/normalize_plan.py` | integration tests |
| C3 | Carry `catalog_topic_id` into Phase 4 obligations + rows | `writing/generated_coverage.py` | `Phase4PromotedGranularityTests` |
| C4 | Export new symbols | `coverage/__init__.py` | import smoke; suite green |
| T | Adapt existing tests for flipped expanded; add `test_deepwiki_scale_core.py` | `tests/...` | full suite |

## Test traceability

| Requirement / risk | Test method | Test |
|---|---|---|
| FR1 (mode semantics) | unit | `test_expanded_is_core_breadth_enforcing_path`, `test_expanded_and_alias_are_equivalent` |
| FR1 + SM1 (expanded fails compressed) | integration | `IntegratedDeepwikiScaleTests::test_expanded_fails_on_compressed_family` |
| FR2 (gate + contract emitted) | integration | `test_expanded_runs_anti_compression_by_default` |
| SM3 (no regression) | integration + suite | `test_enhancement_does_not_run_anti_compression` + full pytest |
| FR3 + SM4 (budget) | unit + manual | `BreadthBudgetTests`, `CatalogMarkdownBudgetTests`, real-catalog derivation |
| SM5 (prompts) | unit | `PlannerPromptFanOutTests` |
| FR2/FR4 + SM6 (contract + granularity) | unit | `PromotedTopicContractTests`, `Phase4PromotedGranularityTests` |
| C2 (no weakened validator) | regression | full suite (687 passed) + code review |
| C3 (protected spec) | repo check | `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` |

No live model, network, clock, or randomness in any test (Python hard rule: deterministic
+ isolated). Integration tests use a temp bundle + a fake "test" provider label.

## Rollout, migration, rollback, operations

- **Rollout:** off-by-default at the *command* level — `--coverage-mode` still defaults to
  `baseline`. The change only affects callers who explicitly pass `expanded` (or the
  `deepwiki-scale` alias). No flag flip is forced on baseline/enhancement users.
- **Migration:** existing `deepwiki-scale` callers need no change (alias). New callers
  should pass `expanded`. Compressed `expanded` plans that previously passed will now fail
  at Phase 2 with actionable remediation — this is the intended correction.
- **Rollback:** drop `MODE_EXPANDED` from `_BREADTH_MODES` in `validate.py` (one line) to
  restore the prior "deepwiki-scale-only" enforcement; budget/contract/prompt additions are
  additive and inert without breadth enforcement.
- **Operations:** failures are loud and pre-Phase-3 (exit 3) or pre-provider (exit 5),
  each with a remediation string pointing at the LLM-authored plan. Artifacts written:
  `anti-compression-gate.json`, `anti-compression-report.md`, `promoted-topic-contract.json`.

## Risks, open questions, failure modes

| Risk / failure mode | Likelihood | Mitigation |
|---|---|---|
| Hardened prompt does not actually make a live planner fan out | Medium | Budget gives concrete numbers; gate fails closed if it still compresses; measured in the deferred live run |
| BreadthPolicy defaults too strict/loose for some repos | Medium | Policy is injectable + serialized; release-owner sign-off before billed runs |
| Operators relied on lenient expanded passing | Low–Med | Documented expected behaviour change; baseline/enhancement unaffected; rollback is one line |
| Catalog with only family topics yields empty budget | Low | Handled: all-zero budget, `[]` lines, gate passes trivially (no promoted leaves) |
| Phase 4 granularity field absent (non-expanded) | Low | `catalog_topic_id` defaults to `None`; never required, never crashes |

## Open question (for release owner)

- Approve BreadthPolicy defaults (`max_promoted_topics_per_leaf_page=4`,
  `family_split_threshold=6`, `flat_plan_family_threshold=3`) before any billed live run.
