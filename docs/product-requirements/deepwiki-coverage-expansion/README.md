# DeepWiki Coverage Expansion PRD Workspace

This workspace contains the product requirements run for expanding generated wiki coverage toward a DeepWiki-style hierarchical page plan while preserving strict grounding.

## Files

- `input.md` — captured request, constraints, and source inventory.
- `artifacts/final_prd.md` — final product requirements document.
- `artifacts/traceability_matrix.md` — requirement-to-source, acceptance, and gate traceability.
- `eval/findings.md` — PRD review and validation findings.
- `phase_state.json` — concise PRD Companion phase/gate state.
- `traces/assumptions.jsonl` — durable assumptions.
- `traces/decisions.jsonl` — durable product/process decisions.
- `traces/harness_trace.jsonl` — minimal phase and gate trace.

## Boundary

The benchmark DeepWiki export is treated only as a breadth comparator. Generated output must be planned and grounded from repository-derived evidence, not copied from benchmark headings or prose.
