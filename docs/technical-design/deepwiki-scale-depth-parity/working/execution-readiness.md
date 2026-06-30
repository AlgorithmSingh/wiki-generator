# Execution Readiness — deepwiki-scale-depth-parity

Pre-implementation readiness for M1. Confirms the design is buildable, testable, and safe to
start before any code is written.

## Readiness checklist

- [x] Problem and finish line agreed: enforce **depth** (source-derived per-section detail
  density) on the expanded grounded claim plan, not just breadth.
- [x] Code seams identified and read: `claim_plan.py`, `grounded.py`, `__init__.py`,
  `packet.py`, `generated_coverage.py`, `token_bank.py`, `options.py`, `validate.py`, and the
  `anti_compression.py` pattern to mirror.
- [x] Data already available in-memory (mapped evidence, supporting evidence, allowed
  evidence, token bank, source handles, normalized claims) — no new file read, no new dep.
- [x] Backward-compatibility plan: every new parameter optional (`depth_budget=None`);
  expanded grounded only; baseline/enhancement byte-identical.
- [x] Benchmark quarantine plan: `depth_budget.py` imports only stdlib; no comparator read.
- [x] Test plan written (`working/16-test-traceability.md`); new file
  `tests/test_phase4_depth_budget.py`; existing suites are the regression gate.
- [x] Baseline established: focused suites green before changes (104 passed, 12 subtests).
- [x] Rollback is a one-line guard; no persisted schema risk.
- [x] Python build sequence dossier planned at repo-root `.sequence/` (git-ignored).

## Build order (M1)

1. `libs/writing/depth_budget.py` (pure module + tests for it first).
2. `claim_plan.py` validator + prompt wiring.
3. `grounded.py` + `__init__.py` threading + depth audit.
4. `tests/test_phase4_depth_budget.py` full suite.
5. Validation: focused suites, full suite, `git diff --check`, protected-spec diff,
   comparator-import grep.

## Go / no-go

GO. No blocking unknowns. The only open decisions (OD1 policy defaults, OD2 M2 rendering) are
non-blocking for a non-live M1: conservative seeds are used and serialized for later sign-off.
