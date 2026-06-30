# Phase 2 — Problem & Success

## Summary

The anti-compression slice proved that a high-signal source catalog can be held to a
distributive breadth contract — but it was wired behind a *separate* `deepwiki-scale`
mode, and it only **rejected** compressed plans without telling the planner how to fan
out, and it stopped at Phase 2. This phase makes strict source-derived breadth the
**core behaviour of the expanded path**, teaches the planner to fan out via a
source-derived budget, and carries promoted catalog-topic granularity into Phase 3/4.

## Context & current state

- `--coverage-mode expanded` already runs the enhancement + hierarchical (page-profile,
  content-block, relevant-source-map) gates and is the DeepWiki-style hierarchical
  mode. It did **not** run the anti-compression breadth gate — that was gated behind a
  `deepwiki-scale` superset mode (`enforces_breadth(mode) == (mode == "deepwiki-scale")`).
- The real RAGFlow run (`681b900`, expanded) collapsed a **147-topic / 94-must /
  12-family / 82-must-subsystem** catalog into **21 flat pages and 42 TERs**: every
  `parent_section_id` null, families collapsed 1:1 onto a single broad page each.
- The planner prompts told the model to "plan a broad, hierarchical guide" but carried
  **no** explicit fan-out rule, page budget, per-promoted-topic TER rule, or
  "no broad page claiming leaf coverage" rule, and **no** source-derived target numbers.
- Phase 3 tags evidenced topic rows with `catalog_topic_id` (expanded), but Phase 4
  `build_topic_obligations` dropped it, so generated coverage could only reason at the
  prose-topic level — promoted catalog-topic granularity was lost downstream.

## Problem statement

DeepWiki-scale breadth is treated as a separate, opt-in product rather than the core
behaviour of the expanded path; the planner is not instructed (or given source-derived
targets) to fan out; and promoted catalog-topic granularity does not survive past
Phase 2. The result is benchmark-far output (flat, compressed) even when the source
supports RAGFlow-scale breadth.

## Goals (each paired with a non-goal)

| # | Goal | Non-goal |
|---|---|---|
| G1 | `expanded` enforces the anti-compression breadth gate by default (core, not opt-in). | Not removing `deepwiki-scale`; it stays as a behaviour-identical alias. |
| G2 | The planner is given a deterministic **source-derived breadth budget** and explicit fan-out rules so it authors a hierarchy. | Not copying benchmark page counts/headings; every number derives from the catalog. |
| G3 | Promoted catalog-topic granularity is carried into a downstream data contract and Phase 4 obligations. | Not building the full standalone Phase 4 end-to-end enforcement gate in this slice (staged). |
| G4 | `baseline` and `enhancement` behaviour is unchanged. | Not changing the historical compact-plan path. |
| G5 | All new behaviour is deterministic and provable without live calls. | Not running a billed live planner/E2E in this slice. |

## Future goals

- A standalone Phase 4 gate that cross-references `plans/promoted-topic-contract.json`
  end-to-end and fails when a promoted leaf topic with evidence is missing from output.
- A billed live RAGFlow run to measure GPT-5.4/Gemini response quality to the hardened
  prompt and confirm the planner reaches the source-derived page/topic budget.

## Success metrics

- **SM1 (core):** With a compressed-family fixture, `--coverage-mode expanded`
  fails (exit 3, `bad_compressed_normalized_plan`) — proven by an integration test.
- **SM2 (alias):** `expanded` and `deepwiki-scale` produce identical verdict/exit/defect
  codes on the same plan — proven by a unit test.
- **SM3 (no regression):** `baseline`/`enhancement` never run the anti-compression gate;
  full suite stays green.
- **SM4 (planner budget):** The breadth budget derived from the real RAGFlow catalog
  targets ≥ 36 pages / ≥ 94 required topics (vs the 21-page/42-TER collapse), with a
  per-family fan-out floor — proven deterministically against the real catalog.
- **SM5 (prompt):** Embedded + Gem prompts contain the fan-out / TER-per-promoted-topic /
  no-broad-page / breadth-budget rules — proven by substring tests.
- **SM6 (downstream granularity):** `plans/promoted-topic-contract.json` is emitted and
  loadable, and a promoted catalog topic that is a sufficient obligation but omitted
  from generated output fails Phase 4 generated coverage — proven by tests.

## Requirements, constraints, assumptions, dependencies

- **FR1** `enforces_breadth(mode)` is true for `expanded` and `deepwiki-scale`. *(sourced: validate.py)*
- **FR2** The Phase 2 normalize-plan command runs the anti-compression gate and writes
  `anti-compression-gate.json`, `anti-compression-report.md`, and
  `promoted-topic-contract.json` for the expanded family. *(sourced: normalize_plan.py)*
- **FR3** `planning-topic-catalog.md` includes a source-derived breadth-budget block. *(sourced: topic_catalog.py)*
- **FR4** Phase 4 obligations + generated-coverage rows carry `catalog_topic_id`. *(sourced: generated_coverage.py)*
- **C1** No live calls; **C2** validators not weakened; **C3** protected spec untouched;
  **C4** comparator isolation; **C5** Python hard rules. *(sourced: task constraints)*
- **D1** Phase A topic catalog must exist (expanded already fails closed, exit 2, when absent). *(sourced)*
- **A1** Phase 3 expanded already writes `catalog_topic_id` per evidenced topic row. *(sourced: evidenced_coverage.py:360-362)*
