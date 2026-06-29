# Design Judgment — DeepWiki Scale-Parity (Anti-Compression)

## Quality attributes (measurable)
- **Determinism (QR-S1)**: sorted, set-free serialization; injected immutable policy;
  no clock/random/network. Verified by an explicit determinism test (AC-S5).
- **Isolation (QR-S2)**: new gate is read-only; no plan mutation; module top level is
  declarations only; `BreadthPolicy` injected.
- **Non-regression (QR-S3)**: opt-in mode; existing three modes and their suites
  untouched (AC-S4 + full suite).
- **Diagnosability (QR-S4)**: each diagnostic carries scope+id+code+measured-vs-required
  +remediation aimed at the LLM-authored plan.

## Alternatives & trade-offs (summary; full list in TDD §11)
- Tighten `expanded` in place → breaks the passing run; rejected.
- Fold into `_eval_catalog_coverage` → conflates existential vs distributive coverage;
  rejected for a separate module.
- Hard-coded thresholds → violates HARD-RULES/tunability; rejected for `BreadthPolicy`.
- Benchmark page count as floor → benchmark quarantine; rejected for catalog floor.
- Phase 3/4 enforcement now → larger blast radius; deferred to M2/M3 with the data
  contract emitted now.

## Honest accepted downsides
- The default thresholds (cap 4 / split 6 / floor) are seeded heuristics (OD-S2). They
  are chosen so the observed collapse fails and a reasonable fan passes, but real
  calibration needs the next live-equivalent run; they are tunable and audited in the
  report. Sign-off required before live.
- A family-heavy catalog with few subsystem leaves yields a low floor; the flat-plan
  check still fires, and FG-S1 (finer catalog) is the durable fix.
- Slice 1 treats `deepwiki-scale` as `expanded` downstream; a future contract mismatch
  is mitigated by emitting `promoted_topics[]` now and specifying VG-13.

## Why this is the right altitude
The loophole is a *planning-time* contract gap. Fixing it at Phase 2 (the producer
boundary) with a deterministic gate that fails before retrieval is cheaper and louder
than catching compression after Phase 4. The data contract lets later phases tighten
without re-architecting.
