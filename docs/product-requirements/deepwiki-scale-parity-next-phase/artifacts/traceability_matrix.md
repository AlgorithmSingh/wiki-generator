# Traceability Matrix — DeepWiki Scale-Parity (Anti-Compression)

Objective → User Need → Requirement → Acceptance Criterion → Gate → PRD Section.
Status: `Traced` (covered), `Slice-2` (specified, built later), `Open` (decision).

| Objective | User Need | Requirement | Priority | Acceptance | Gate | PRD § | Status |
|---|---|---|---|---|---|---|---|
| G-S1 collapse impossible | Operator: a 94-must catalog must not pass as 21 flat pages | UR-S3, UR-S4, UR-S6, UR-S7 | Must | AC-S1 | VG-12a/b/d/e/f | §7,§11,§14 | Traced |
| G-S2 promotion contract | Future agent: know which topics are blocking | UR-S2, UR-S8 | Must | AC-S7 | VG-11 | §8,§10.2 | Traced |
| G-S2 promotion contract | Operator: defer unsupported topics | UR-S12 | Must | AC-S7 | VG-11 | §8 BR-S1 | Traced |
| G-S3 catalog-derived breadth | Operator: thresholds from source, not benchmark | UR-S7, UR-S14, BR-S5 | Must | AC-S2 | VG-12f | §8,§13 | Traced |
| G-S1 distributive TER | Maintainer: 1 TER per promoted topic | UR-S5 | Must | AC-S1 | VG-12c | §7,§14 M-S3 | Traced |
| G-S3 hierarchy quality | Reader: non-flat, fanned-out plan | UR-S6 | Must | AC-S1,AC-S2 | VG-12d/e | §7,§14 M-S4/5 | Traced |
| G-S4 downstream contract | Future agent: consume promoted-topic data | UR-S8 | Must | AC-S2 | VG-11 | §10.2 | Traced |
| G-S4 promoted-topic enforcement | Reader: every promoted topic evidenced+rendered | UR-S9, UR-S10 | Should | AC (later) | VG-13 | §6.2,§11 | Slice-2 |
| G-S5 non-regression | Maintainer: existing modes unchanged | UR-S11, QR-S3 | Must | AC-S4 | (suite) | §3,§9 | Traced |
| G-S5 isolation/determinism | Maintainer: read-only, injected policy | UR-S13, UR-S14, QR-S1/2 | Must | AC-S5 | VG-12 | §9 | Traced |
| G-S6 non-live validation | Operator: no billed calls | UR-S15 | Must | (manual) | — | §1,§3 | Traced |
| benchmark quarantine | Operator: no benchmark leakage | BR-S5, M-S9 | Must | (review) | VG-09 | §13 | Traced (inherited) |
| CLI coherence | Operator: mode accepted end-to-end | UR-S1 | Must | AC-S6 | — | §10.3 | Traced |

## Orphan / coverage check
- No `Must` requirement is unmapped: UR-S1…UR-S8, UR-S11…UR-S15 all trace to ≥1 AC and
  a gate/suite. UR-S9/UR-S10 are `Should`, explicitly Slice-2.
- No AC is orphaned: AC-S1…AC-S7 each trace to ≥1 requirement and gate.
- Open decisions OD-S1…OD-S4 are recorded in PRD §12 and TDD risks; none block Slice 1
  (defaults applied, sign-off required before live use).
