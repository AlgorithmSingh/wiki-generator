# DeepWiki Scale — Core Fan-Out (TDD)

This workspace is the **next implementation phase after the anti-compression slice**
(`f083e29 Add DeepWiki scale anti-compression mode`). It makes strict, source-derived
DeepWiki-scale breadth the **core behaviour of the expanded generation path** rather
than a separate optional product/mode.

- Document weight: **full**
- Status: see `status.md`
- Final document: `final/technical-design-document.md`
- Definition of done: `definition-of-done.json`

## What this changes

1. The core `--coverage-mode expanded` path now enforces the Phase 2 anti-compression
   breadth gate **by default**. `deepwiki-scale` is retained only as a
   behaviour-identical **compatibility alias**, not a separate product.
2. The Phase 2 planner prompt/schema is hardened so the LLM planner authors a
   fanned-out hierarchy, and a **source-derived breadth budget** (page / required-topic
   targets, per-family fan-out floor) is computed from the catalog and shown to the
   planner.
3. Promoted catalog-topic granularity is carried downstream: Phase 2 emits a
   `plans/promoted-topic-contract.json` data contract, and Phase 4 carries each
   evidenced topic's `catalog_topic_id` into its generated-coverage obligations/rows.

## Relationship to prior design docs (preserved, not replaced)

- `docs/product-requirements/deepwiki-coverage-expansion/` (PRD)
- `docs/technical-design/deepwiki-coverage-expansion/` (TDD)
- `docs/product-requirements/deepwiki-scale-parity-next-phase/` (PRD)
- `docs/technical-design/deepwiki-scale-parity-next-phase/` (TDD + ADR 0001)

This TDD builds directly on the anti-compression TDD/ADR; it does not delete or
supersede them.

## Comparator isolation (binding)

`ragflow-deepwiki.md` is a **breadth comparator only**. No benchmark text, headings,
structure, or prose is read as evidence, copied, or used as a prompt seed. All scale
targets are derived from the repository's own topic catalog.
