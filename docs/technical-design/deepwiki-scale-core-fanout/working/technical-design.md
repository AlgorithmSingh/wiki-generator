# Phase 3 — Technical Design

## Views selected

- **Component view** — the coverage gate set and where the breadth concern lives.
- **Data view** — the promotion contract and the `catalog_topic_id` field as it flows
  Phase 2 → 3 → 4.
- **Runtime/behaviour view** — what `normalize-plan --coverage-mode expanded` does, and
  the failure paths.

Omitted: deployment/allocation views (no infra change), sequence diagram for unchanged
phases.

## Architecture overview

Three coordinated changes, all inside `libs/coverage` + the two commands + the writing
phase, with no new services:

```
condense ──> derived/topic-catalog.json
            derived/planning-topic-catalog.md  ◀─ (B) breadth-budget block (NEW)
                         │
plan (LLM) ──> raw planner response  ◀─ (B) hardened fan-out prompt (NEW)
                         │
normalize-plan --coverage-mode expanded
   ├─ planned-coverage gate
   ├─ topic-obligation gate
   ├─ page-planning gate
   ├─ relevant-source-map gate
   └─ anti-compression breadth gate   ◀─ (A) now CORE for expanded (NEW default)
        ├─ plans/anti-compression-gate.json
        └─ plans/promoted-topic-contract.json  ◀─ (C) downstream contract (NEW)
                         │
retrieve-evidence --coverage-mode expanded
   └─ evidence/evidenced-coverage.json  (already carries topic.catalog_topic_id)
                         │
write-wiki --coverage-mode expanded
   └─ generated coverage obligations + rows  ◀─ (C) now carry catalog_topic_id (NEW)
```

## Component / module design

### A. Mode semantics (`libs/coverage/validate.py`)

- New module-private `_BREADTH_MODES = {MODE_EXPANDED, MODE_DEEPWIKI_SCALE}`.
- `enforces_breadth(mode)` returns `mode in _BREADTH_MODES` (was `== MODE_DEEPWIKI_SCALE`).
- `EXPANDED_MODES` and `_ENFORCING_MODES` unchanged (already contained both).
- Single responsibility: classify a mode. Pure functions, no state. `deepwiki-scale`
  stays in `_MODES` so existing callers/choices keep resolving (compatibility alias).

### B. Source-derived breadth budget (`libs/coverage/anti_compression.py`)

- `BreadthBudget` / `FamilyBudget` dataclasses + `derive_breadth_budget(catalog, *, policy)`.
- Reuses `classify_promotion` and `BreadthPolicy.required_leaf_pages` so the planner's
  guidance and the gate's enforcement are derived **identically** (one source of truth).
- Targets: `min_leaf_pages = Σ ceil(promoted_leaf_f / cap)` (the gate's exact floor);
  `max_leaf_pages = promoted_leaf_count`; `min_overview_pages = families_with_promoted + 1`;
  `min_required_topics = promoted_leaf_count + families_with_promoted`.
- `render_breadth_budget_lines(budget)` → markdown embedded by `topic_catalog.render_catalog_markdown`.
- Policy injected (`BreadthPolicy`), no scattered constants. Empty/absent catalog → all-zero
  budget and `[]` lines (no guidance noise).

### C. Promoted-topic contract (`libs/coverage/anti_compression.py`)

- `build_promoted_topic_contract(report)` → a normalized projection of the `TIER_PAGE`
  rows: `{catalog_topic_id, family, tier, has_ter, leaf_pages, status}` plus policy +
  counts; schema `deepwiki-promoted-topic-contract-v1`.
- `load_promoted_topic_contract(plans_dir)` (read-only, returns `None` when absent) and
  `promoted_catalog_topic_ids(contract)` (the downstream granularity key set).
- `normalize-plan` writes `plans/promoted-topic-contract.json` whenever the breadth gate
  runs (pass or fail), so the artifact is always available for inspection/downstream.

### C (Phase 4). Granularity passthrough (`libs/writing/generated_coverage.py`)

- `build_topic_obligations` adds `catalog_topic_id` to each obligation row (read from the
  Phase 3 evidenced-topic row, which carries it in the expanded family).
- `evaluate_section_coverage` adds `catalog_topic_id` to each output row (covered/omitted/
  invalid). No new failure logic: a promoted leaf topic that is a `sufficient` required
  topic is *already* a generation obligation, so omitting it already fails (exit 5); this
  change makes that failure **catalog-topic-addressable** rather than prose-only.

## Data design

- **`plans/promoted-topic-contract.json`** (NEW). Owner: Phase 2 anti-compression gate.
  Source of truth for which catalog topics are promoted leaf topics. Read-only downstream.
  Deterministic, timestamp-free.
- **`catalog_topic_id`** field (additive) on: Phase 3 evidenced topic rows (existing),
  Phase 4 obligation rows (NEW), Phase 4 generated-coverage rows (NEW). `None` when absent
  (non-expanded or family-only catalog) — never required, never crashes.
- No schema change to `topic-catalog.json` or `document-plan.json`/`section-plans.jsonl`.

## Interfaces & behavior

`normalize-plan --coverage-mode expanded` (and `deepwiki-scale` alias):

- **Success:** all gates pass → writes `anti-compression-gate.json` (passed=true),
  `promoted-topic-contract.json`, exit 0.
- **Compressed plan:** breadth gate fails → `anti-compression-gate.json` (passed=false,
  failure_category `bad_compressed_normalized_plan`), contract still written (uncovered
  rows visible), exit 3. Loud, actionable remediation per defect.
- **Missing catalog:** exit 2 (hard missing input) — unchanged.
- **baseline/enhancement:** anti-compression gate not run; no contract file — unchanged.

Failure paths preserved: the gate never edits/synthesizes/heals the plan; it reports +
fails. The budget is guidance only (never gates). The contract is read-only data.
