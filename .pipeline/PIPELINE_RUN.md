# Python-specific-agents pipeline run

> **Historical snapshot.** This `.pipeline/` directory records the original
> build run, before the package was renamed and moved. It refers to the old
> package name `phase1_decomposition` and a flat layout; the current code is
> the `wiki_generator` package under `src/`. Kept for provenance — see
> `README.md` / `RUNBOOK.md` for current docs.


Source pipeline: `05-python-specific-agents` (27-stage Python-first generation
sequence + conditional repair loop), applied to this package.

Mode: **full regenerate from scratch**, with the previously-built, fully-tested
implementation used as the **authoritative reference** so the writer stages did
not re-solve already-solved problems (SCIP symbol ids, cross-artifact id linking,
determinism rules, exact artifact JSON schemas, graceful tool degradation).

## Phases

- **A — Planning (stages 1–13):** `prompt-intent → source-text-grounding →
  requirement-normalizer → acceptance-criteria → python-runtime →
  architecture-planner → python-rule-compliance → package-planner →
  module-planner → symbol-planner → import-planner → test-planner → router`,
  each grounded in its agent definition. Outputs saved under
  `.pipeline/stages/01..13-*.txt`. The router emitted the per-file build manifest.
- **B — Writing (stages 14–24):** one writer agent per file (40 files), each
  regenerating its file from scratch per the plan + hard rules, grounded in the
  reference. Every file compiled (`py_compile`) on write.
- **C — Integrate / static-analysis / validate (stages 25–27 + repair):**
  whole-tree compile, the 31-test `unittest` suite, byte-determinism of decompose
  output, and behavioral checks of condense/digest.

## Result

- 40/40 files regenerated and compiling.
- **31/31 tests pass.**
- decompose output **byte-deterministic** across runs.
- condense/digest produce the planner condensates + upload package within the
  250K-token budget.
- The regenerated tree is **byte-identical to the reference across all 40 files**
  — the validate stage required **no repairs and no reconciliation**. The
  pipeline independently reproduced the proven implementation.

The per-stage planning artifacts in `.pipeline/stages/` are the documented design
trail (acceptance criteria, architecture plan, package/module/symbol/import/test
plans, and the router build manifest).
