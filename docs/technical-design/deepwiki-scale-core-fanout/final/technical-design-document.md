# Technical Design — DeepWiki Scale: Core Fan-Out

| | |
|---|---|
| Slug | `deepwiki-scale-core-fanout` |
| Status | Implemented & validated (non-live) |
| Weight | Full |
| Phase relation | Next implementation phase after the anti-compression slice (`f083e29`); builds on, does not replace, the coverage-expansion and scale-parity TDDs/ADR |
| Author role | TDD phase series (phases 1–6); writer ≠ approver in finalization |
| Comparator isolation | `ragflow-deepwiki.md` is comparison-only — never read as evidence, prompt seed, headings, or copied structure |

## Table of contents

1. Summary
2. Context & background
3. Goals, non-goals & future goals
4. Success metrics
5. Requirements, constraints, assumptions & dependencies
6. Architecture overview
7. Detailed design
8. Interfaces, APIs & behavior
9. Non-functional requirements & quality attributes
10. Alternatives considered & trade-offs
11. Key architecture decisions
12. Implementation plan, milestones & test plan
13. Rollout, migration, rollback & operations
14. Risks, open questions & failure modes
15. Appendices, glossary & references

---

## 1. Summary

This phase makes strict, **source-derived DeepWiki-scale breadth the core behaviour of
the expanded generation path** instead of a separate opt-in product. Three coordinated
changes: (A) `--coverage-mode expanded` now enforces the Phase 2 anti-compression
breadth gate by default, with `deepwiki-scale` retained only as a behaviour-identical
compatibility alias; (B) the Phase 2 planner is hardened — both the prompt and a new
**source-derived breadth budget** rendered into the planner-facing catalog — so the LLM
authors a fanned-out hierarchy rather than only being rejected when it compresses; and
(C) promoted catalog-topic granularity is carried downstream via a
`plans/promoted-topic-contract.json` data contract and a `catalog_topic_id` field on
Phase 4 generated-coverage obligations/rows. All behaviour is deterministic and proven
without live model calls.

## 2. Context & background

`--coverage-mode expanded` is the DeepWiki-style hierarchical mode (enhancement gates +
page-profile + content-block + relevant-source-map gates). The anti-compression slice
added a distributive breadth gate but wired it behind a *separate* `deepwiki-scale`
superset mode (`enforces_breadth(mode) == (mode == "deepwiki-scale")`). Consequently the
official expanded path kept shipping compressed output: a real RAGFlow run (`681b900`,
expanded) collapsed a **147-topic / 94-must / 12-must-family / 82-must-subsystem**
catalog into **21 flat pages and 42 TERs** — every `parent_section_id` null, families
collapsed 1:1 onto a single broad page each.

Two further gaps remained: the planner prompts said "plan a broad, hierarchical guide"
but carried no explicit fan-out rule, page budget, per-promoted-topic TER rule, or
source-derived targets; and although Phase 3 tags evidenced topic rows with
`catalog_topic_id`, Phase 4 dropped it, so promoted catalog-topic granularity was lost
after Phase 2.

## 3. Goals, non-goals & future goals

| # | Goal | Non-goal |
|---|---|---|
| G1 | `expanded` enforces anti-compression by default (core, not opt-in). | Removing `deepwiki-scale` — it stays as a behaviour-identical alias. |
| G2 | Planner gets a source-derived breadth budget + explicit fan-out rules. | Copying benchmark page counts/headings — every number is catalog-derived. |
| G3 | Promoted catalog-topic granularity carried into a downstream contract + Phase 4. | Building the full standalone Phase 4 end-to-end enforcement gate (staged). |
| G4 | `baseline`/`enhancement` behaviour unchanged. | Changing the historical compact-plan path. |
| G5 | All new behaviour deterministic, provable without live calls. | Running a billed live planner/E2E this slice. |

**Future goals:** a standalone Phase 4 gate cross-referencing the promoted-topic contract
end-to-end; a billed live RAGFlow run to confirm the planner reaches the source-derived
page/topic budget.

## 4. Success metrics

- **SM1** Compressed-family fixture → `expanded` fails (exit 3,
  `bad_compressed_normalized_plan`).
- **SM2** `expanded` and `deepwiki-scale` produce identical verdict/exit/defect codes.
- **SM3** `baseline`/`enhancement` never run the breadth gate; full suite green.
- **SM4** Budget over the real RAGFlow catalog targets ≥ 36 pages / ≥ 94 required topics
  with a per-family fan-out floor (vs the 21-page / 42-TER collapse).
- **SM5** Embedded + Gem prompts contain the fan-out / TER-per-promoted-topic /
  no-broad-page / breadth-budget rules.
- **SM6** `promoted-topic-contract.json` emitted + loadable; a promoted catalog topic
  that is a sufficient obligation but omitted from output fails Phase 4 generated coverage.

All six are met (see §12 and `working/validation-report.json`).

## 5. Requirements, constraints, assumptions & dependencies

**Functional**

- **FR1** `enforces_breadth(mode)` true for `expanded` and `deepwiki-scale`.
- **FR2** `normalize-plan` (expanded family) runs the breadth gate and writes
  `anti-compression-gate.json`, `anti-compression-report.md`, `promoted-topic-contract.json`.
- **FR3** `planning-topic-catalog.md` includes a source-derived breadth-budget block.
- **FR4** Phase 4 obligations + generated-coverage rows carry `catalog_topic_id`.

**Constraints** — no live calls (C1); validators not weakened (C2); protected spec
untouched (C3); comparator isolation (C4); Python hard rules (C5).

**Assumptions** — A1: Phase 3 expanded already writes `catalog_topic_id` per evidenced
topic row (verified, `evidenced_coverage.py:360-362`). **Dependencies** — D1: the Phase A
topic catalog must exist (expanded already fails closed, exit 2, when absent).

## 6. Architecture overview

No new services. Changes are localized to `libs/coverage`, two commands, the planner
prompts, and the Phase 4 writing module:

```
condense → derived/topic-catalog.json
           derived/planning-topic-catalog.md   ◀ (B) breadth-budget block
plan(LLM) → raw response                        ◀ (B) hardened fan-out prompt
normalize-plan --coverage-mode expanded
   ├ planned-coverage / topic-obligation / page-planning / relevant-source-map gates
   └ anti-compression breadth gate              ◀ (A) CORE for expanded by default
        ├ plans/anti-compression-gate.json
        └ plans/promoted-topic-contract.json    ◀ (C) downstream contract
retrieve-evidence → evidence/evidenced-coverage.json (topic.catalog_topic_id present)
write-wiki → generated-coverage obligations/rows ◀ (C) carry catalog_topic_id
```

## 7. Detailed design

### A. Mode semantics — `libs/coverage/validate.py`
New module-private `_BREADTH_MODES = {MODE_EXPANDED, MODE_DEEPWIKI_SCALE}`;
`enforces_breadth(mode)` returns `mode in _BREADTH_MODES`. `EXPANDED_MODES` /
`_ENFORCING_MODES` already contained both, so the hierarchical/enforcing semantics are
unchanged. `deepwiki-scale` stays in `_MODES` (and all CLI choices) as a documented
compatibility alias. Pure classification functions; no state.

### B. Source-derived breadth budget — `libs/coverage/anti_compression.py`
`BreadthBudget` / `FamilyBudget` dataclasses and `derive_breadth_budget(catalog, *, policy)`
reuse `classify_promotion` and `BreadthPolicy.required_leaf_pages`, so planner guidance and
gate enforcement derive **identically**:
- `min_leaf_pages = Σ_family ceil(promoted_leaf_f / cap)` (the gate's exact floor)
- `max_leaf_pages = promoted_leaf_count`
- `min_overview_pages = families_with_promoted + 1`
- `min_required_topics = promoted_leaf_count + families_with_promoted`

`render_breadth_budget_lines(budget)` emits the markdown block that
`topic_catalog.render_catalog_markdown` inserts into `planning-topic-catalog.md`. An
absent/empty catalog yields an all-zero budget and `[]` lines (no guidance noise). Policy
is injected — no scattered constants.

### B. Prompt hardening — `commands/plan.py` + `gemini-gem/{GEM_INSTRUCTIONS,KICKOFF_PROMPT}.md`
A "fan out, do not compress" rule covering: parent/index vs leaf pages; ≤ ~4 promoted
catalog topics per leaf page; large families fan out into multiple child pages; one
required topic AND one `catalog_topic_id`-keyed TER per promoted catalog topic; a broad
page that merely lists a family's subsystem `catalog_topic_ids[]` does not count as leaf
coverage; hit the source-derived breadth budget; and an explicit BAD (compressed) vs GOOD
(fanned-out) example. The prompt points the planner at the catalog's budget rather than at
any benchmark number.

### C. Promoted-topic contract — `libs/coverage/anti_compression.py` + `commands/normalize_plan.py`
`build_promoted_topic_contract(report)` projects the `TIER_PAGE` rows into
`{catalog_topic_id, family, tier, has_ter, leaf_pages, status}` + policy + counts (schema
`deepwiki-promoted-topic-contract-v1`). `load_promoted_topic_contract` (read-only, `None`
when absent) and `promoted_catalog_topic_ids` complete the contract surface. `normalize-plan`
writes `plans/promoted-topic-contract.json` whenever the breadth gate runs (pass or fail).

### C. Phase 4 granularity passthrough — `libs/writing/generated_coverage.py`
`build_topic_obligations` and `evaluate_section_coverage` add `catalog_topic_id` (read from
the Phase 3 evidenced topic row). No new failure logic: a `sufficient` promoted required
topic is already a generation obligation, so omitting it already fails (exit 5); this makes
that failure catalog-topic-addressable instead of prose-only. `None` when absent.

## 8. Interfaces, APIs & behavior

`normalize-plan --coverage-mode expanded` (and `deepwiki-scale` alias):
- **Success** → all gates pass; writes the gate JSON (passed=true) + contract; exit 0.
- **Compressed plan** → breadth gate fails (`bad_compressed_normalized_plan`); contract
  still written (uncovered rows visible); exit 3; loud per-defect remediation.
- **Missing catalog** → exit 2 (hard missing input) — unchanged.
- **baseline/enhancement** → breadth gate not run, no contract file — unchanged.

The gate never edits/synthesizes/heals the plan. The budget is guidance only (never gates).
The contract is read-only data.

## 9. Non-functional requirements & quality attributes

| Attribute | Definition | How met |
|---|---|---|
| Determinism | identical inputs → byte-identical outputs | no clock/random; derived purely from catalog/report |
| Non-regression | baseline/enhancement unchanged | `enforces_breadth` excludes them; 687 passed |
| Backward compatibility | `deepwiki-scale` callers keep working | alias retained; equivalence test |
| Source-fidelity | targets derive from catalog, never benchmark | comparator never imported |
| Auditability | a run records what it enforced/targeted | policy serialized in gate/contract/budget |
| Safety | no validator weakened; no auto-heal | gate/contract read-only; Phase 4 change additive |

## 10. Alternatives considered & trade-offs

- **Keep breadth behind `deepwiki-scale` only** — rejected (perpetuates a separate product;
  the core path keeps shipping compressed output).
- **Delete `deepwiki-scale`** — rejected this slice (gratuitous breaking change; alias is cheap).
- **Hard-gate only, no prompt change** — rejected (the anti-compression slice already did
  this and the real run still collapsed).
- **Put benchmark page counts in the prompt** — rejected (violates comparator isolation;
  the budget is catalog-derived instead).
- **Full Phase 4 end-to-end enforcement now** — deferred/staged (more invasive; the
  obligation path already fails an omitted sufficient promoted topic).

**Accepted trade-off:** a previously-"passing" compressed `expanded` run now fails at Phase
2. Intended; documented in rollout.

## 11. Key architecture decisions

See `adr/0001-core-expanded-scale-gates.md` (Accepted): expanded is the core breadth-
enforcing path; `deepwiki-scale` is a compatibility alias; planner gets a source-derived
budget + fan-out rules; promoted granularity flows downstream via a contract + `catalog_topic_id`.

## 12. Implementation plan, milestones & test plan

All steps in `working/execution-readiness.md` are delivered. Test traceability:

| Requirement | Test |
|---|---|
| FR1 / SM2 | `test_expanded_is_core_breadth_enforcing_path`, `test_expanded_and_alias_are_equivalent` |
| SM1 / FR2 | `IntegratedDeepwikiScaleTests::test_expanded_fails_on_compressed_family`, `test_expanded_runs_anti_compression_by_default` |
| SM3 | `test_enhancement_does_not_run_anti_compression` + full suite |
| FR3 / SM4 | `BreadthBudgetTests`, `CatalogMarkdownBudgetTests`, real-catalog derivation |
| SM5 | `PlannerPromptFanOutTests` |
| FR2/FR4 / SM6 | `PromotedTopicContractTests`, `Phase4PromotedGranularityTests` |

Results: targeted 69 passed; new file 15 passed; full suite **687 passed, 1 skipped, 21
subtests passed**; `git diff --check` clean; protected spec unchanged. Real-catalog budget:
min_total_pages=36, max_total_pages=95, min_leaf_pages=23, min_required_topics=94.

## 13. Rollout, migration, rollback & operations

- **Rollout** — off-by-default at the command level (`--coverage-mode` defaults to
  `baseline`); only callers passing `expanded`/`deepwiki-scale` are affected.
- **Migration** — `deepwiki-scale` callers unchanged (alias); compressed `expanded` plans
  that previously passed will now fail at Phase 2 (intended correction).
- **Rollback** — drop `MODE_EXPANDED` from `_BREADTH_MODES` (one line); budget/contract/
  prompt additions are additive and inert without breadth enforcement.
- **Operations** — failures are loud (exit 3 pre-Phase-3 / exit 5 pre-provider) with
  remediation; artifacts: gate JSON/MD + `promoted-topic-contract.json`.

## 14. Risks, open questions & failure modes

| Risk / failure mode | Mitigation |
|---|---|
| Live planner still compresses despite the hardened prompt | Budget gives concrete numbers; gate fails closed; measured in the deferred live run |
| BreadthPolicy defaults wrong for some repos | Injectable + serialized; release-owner sign-off before billed runs |
| Operators relied on lenient expanded passing | Documented expected change; baseline/enhancement unaffected; one-line rollback |
| Family-only catalog → empty budget | Handled (all-zero budget, gate passes trivially) |
| `catalog_topic_id` absent (non-expanded) | Defaults to `None`; never required, never crashes |

**Open question:** release-owner approval of BreadthPolicy defaults before any billed live run.

## 15. Appendices, glossary & references

- **Promoted leaf topic** — a `must`, subsystem-kind catalog topic (`TIER_PAGE`); owes its
  own leaf page + its own `catalog_topic_id`-keyed TER.
- **Breadth budget** — deterministic, catalog-derived page/required-topic targets shown to
  the planner; guidance, not a gate.
- **Compatibility alias** — `deepwiki-scale`: selects the identical gate set as `expanded`.
- References: `working/*.md`, `adr/0001-core-expanded-scale-gates.md`, `source-index.md`,
  prior PRDs/TDDs under `docs/product-requirements/` and `docs/technical-design/`.
