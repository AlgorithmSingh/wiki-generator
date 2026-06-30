# Phase 4 — Design Judgment

## Quality attributes (measurable)

| Attribute | Definition for this design | How it is met |
|---|---|---|
| Determinism | Identical inputs → byte-identical gate JSON, contract, budget, prompts | No clocks/random; budget+contract derived purely from catalog/report; `test_determinism` already covers the gate |
| Non-regression | baseline/enhancement runs unchanged; existing expanded fixtures pass | `enforces_breadth` excludes them; full suite green (687 passed) |
| Backward compatibility | `deepwiki-scale` callers keep working | Alias retained in all mode tuples + CLI choices; equivalence test |
| Source-fidelity | All scale targets derive from the catalog, never the benchmark | `derive_breadth_budget` reads only the catalog; comparator never imported |
| Auditability | A run records exactly what breadth it enforced/targeted | Policy serialized in gate + contract + budget; reports written to disk |
| Safety | No validator weakened; no auto-heal; no synthetic evidence | Gate/contract are read-only; Phase 4 change is additive field only |

## Alternatives considered

### A1. Keep `deepwiki-scale` as the breadth-enforcing mode; leave `expanded` lenient.
Rejected. The user's directive is that scale is the **core**, not a separate product.
Keeping a separate stricter mode perpetuates "another product line" and lets the
official expanded path keep shipping compressed output (exactly the real-run failure).

### A2. Make `expanded` enforce breadth and **delete** `deepwiki-scale`.
Rejected for this slice. Existing tests, docs, run manifests, and operator muscle memory
name `deepwiki-scale`. Deleting it is a gratuitous breaking change. Retaining it as a
behaviour-identical alias costs almost nothing and is honestly documented as deprecated
in favour of `expanded`.

### A3. Enforce breadth as a hard gate only; do not change the planner prompt.
Rejected. The anti-compression slice already did this and the real run still collapsed —
a gate that only *rejects* without teaching the planner to fan out produces failed runs,
not better wikis. The source-derived budget + fan-out rules close the loop.

### A4. Put benchmark-scale numbers (45–70 pages) directly in the prompt.
Rejected (violates comparator isolation). Instead the budget is computed from the
catalog; for a RAGFlow-scale catalog it *lands* in that regime (≥36 pages / ≥94 topics)
without ever reading or copying the benchmark.

### A5. Fully enforce promoted-topic coverage end-to-end in Phase 4 in this slice.
Deferred (staged), not rejected. Wiring a standalone Phase 4 gate that loads the contract
and fails on a missing promoted topic is more invasive (bundle plumbing + a new exit-5
check). The required-topic obligation path already fails an omitted sufficient promoted
topic; this slice ships the data contract + `catalog_topic_id` passthrough + proof tests,
and marks the standalone gate as the next slice. Honest staging beats a rushed, riskier
gate.

## Trade-offs accepted

- `expanded` now **fails closed** on a compressed plan where it previously passed. This is
  the intended behaviour change (the whole point), but it means a previously-"passing"
  compressed expanded run will now fail at Phase 2 — documented in rollout as expected.
- The budget's `min_required_topics` is a conservative floor (one per promoted leaf +
  family overview), so its number is lower than a benchmark's total topic count; this is
  honest (pages carry multiple topics) and never over-claims.

## ADR

See `adr/0001-core-expanded-scale-gates.md` (accepted).
