# ADR-0001 — `deepwiki-scale` opt-in mode with a separate anti-compression gate

- **Status**: Accepted
- **Date context**: authored alongside Slice 1 (next phase of deepwiki-coverage-expansion)

## Context
The `expanded` coverage mode passes the real RAGFlow non-live E2E yet permits a
94-`must` / 13-family catalog to collapse into 21 flat pages / 42 TERs. The defect is
that planning coverage is *existential* (`topic_id` appears on any page) rather than
*distributive* (each promoted topic earns its own leaf page, TER, hierarchy slot). We
must enforce breadth from the source catalog without breaking the passing `expanded`
run, the existing tests, or the strict validators, and without copying the benchmark.

## Decision
Introduce a new opt-in coverage mode **`deepwiki-scale`**, a strict superset of
`expanded`, and a **new, separate** deterministic Phase 2 gate module
`libs/coverage/anti_compression.py` that computes a source-derived promotion contract
and enforces density cap, distributive leaf-page + TER coverage per promoted topic,
family fan-out, non-flat hierarchy, and a catalog-derived breadth floor. Thresholds
live in an injectable `BreadthPolicy`. The gate runs only in `deepwiki-scale` (via
`enforces_breadth(mode)`), after the existing expanded gates in `normalize-plan`.
Downstream commands accept the mode and behave as `expanded` in Slice 1; a plan-time
`promoted_topics[]` data contract is emitted for later Phase 3/4 enforcement (VG-13).

## Alternatives considered
- Tighten `expanded` in place — rejected: breaks the passing run and existing tests.
- Extend `page_planning._eval_catalog_coverage` — rejected: conflates existential and
  distributive coverage; risks the stable `expanded` contract.
- Hard-code thresholds — rejected: violates HARD-RULES and OD-S2 tunability.
- Benchmark page count as floor — rejected: benchmark quarantine (BR-S5).

## Consequences
- (+) The observed collapse fails deterministically before Phase 3; existing modes are
  byte-for-byte unchanged; thresholds are tunable and audited in the report.
- (+) A clean data contract lets later slices tighten Phase 3/4 without re-architecting.
- (−) A second coverage gate to maintain and one more mode in CLI `choices`.
- (−) Default thresholds are seeded heuristics requiring sign-off (OD-S2) before live.
