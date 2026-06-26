# Documentation journal and status index

This is the single README for project documentation. Keep detailed specs, handoffs, and design plans under `docs/`; keep the repository root focused on code entry points, `README.md`, and `RUNBOOK.md`.

## Status folders

- `specs/done/` — completed, implemented, or superseded specs/design plans kept for provenance. These are archive material unless a current doc explicitly points back to them.
- `specs/not-done/` — active approved work with remaining implementation or verification tasks. This is where the current coding-agent source of truth should live.
- `specs/future/` — proposed ideas or reference-driven architecture notes. These are not approved for implementation and are not gates.
- `specs/protected/` — canonical contracts that should be amended through new iteration specs rather than casually edited.
- `handoffs/done/` — historical handoffs for completed or superseded phases.
- `handoffs/not-done/` — active handoffs for unfinished work.

There is intentionally no separate `plans/` tree now. Early plans are treated as historical specs and live in `specs/done/`.

## Current source of truth

- Active implementation spec: `specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md`
- Active handoff: `handoffs/not-done/HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md`
- Protected Phase 3 evidence contract: `specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`
- Future architecture borrowing note: `specs/future/DEEPWIKI_OPEN_ARCHITECTURE_BORROWING_SPEC.md`

## Sequence journal

Oldest to newest, by project intent:

1. `specs/done/PHASE1_DECOMPOSITION_PLAN.md` — **done / archived plan**. Defined the deterministic Phase 1 artifact bundle.
2. `specs/done/PHASE1_STEP2_STEP3_PLANNING_CONDENSATES.md` — **done / archived plan**. Defined planner condensates and digest.
3. `specs/done/PHASE1_STEP4_PLANNER_UPLOAD_BUNDLE_SPEC.md` — **done / archived spec**. Defined the planner upload bundle.
4. `specs/done/PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md` plus `handoffs/done/HANDOFF_STEP5.md` — **done / historical handoff**. Built the retrieval substrate.
5. `specs/done/PHASE2_PLAN_NORMALIZATION_SPEC.md` — **done / archived spec**. Defined Phase 2 plan normalization.
6. `specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` — **protected canonical contract**. Phase 3 deterministic evidence retrieval. Do not edit casually; amend through iteration specs.
7. `specs/done/PHASE1_PHASE2_PHASE3_READINESS_ITERATION_SPEC.md` plus `handoffs/done/HANDOFF_READINESS_ITERATION.md` — **superseded / historical**. First readiness pass; not current.
8. `specs/done/PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md` plus `handoffs/done/HANDOFF_READINESS_ITERATION_2.md` — **done / baseline historical**. Accepted Phase 1-3 readiness baseline and Phase 4 follow-up context.
9. `specs/done/PHASE1_PHASE2_PHASE3_READINESS_ITERATION_3_SPEC.md` — **done / amendment**. Exact evidence coverage and public-route evidence fixes.
10. `specs/done/PHASE4_WRITING_SYNTHESIS_SPEC.md` — **done / implemented spec**. Phase 4 writing command and validation baseline.
11. `specs/done/PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md` — **done / implemented amendment**. Shell-variable/path synthesized-identifier rewrite behavior.
12. `specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md` plus `handoffs/not-done/HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md` — **active / not done**. Completed foundation slices: Milestone 1 malformed-token validation, Milestone 2 coverage taxonomy/validation, Phase 2 planning/PagePlan obligation preservation, Phase 1 deterministic coverage-signal expansion, Phase 2 planned-coverage upstream-prevention gating, Phase 3 evidenced coverage, Phase 4 enhancement-mode hierarchical writing + generated coverage, wrapper `--coverage-mode` support, the non-live hierarchical E2E + benchmark-only comparison, the Phase 2 required-topic evidence-obligation gate, the Phase 2 TER source-field canonicalization + enhancement-mode bounded `plan-repair` diagnostics, and the Phase 2/3 TER evidence-alignment gate (lane/type consistency + citeable-substrate viability via `coverage/substrate.py`). The latest approved live retry at `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-160914` passed Phase 2 after bounded repair (`13/13` planned families, `59/59` topic obligations) and Phase 3 retrieved `22/22` packets with `704` evidence items, but evidenced coverage failed before Phase 4 (`56/59` sufficient, `1` weak, `2` missing); those three blockers (non-citeable `go.mod`/`Dockerfile` exact lanes and a `tests[0]` source field with `acceptable_lanes:["file_anchor"]`) are now caught at the Phase 2 obligation gate before Phase 3. Pending next: explicit user approval is required before any further billed retry against the stricter gate.
13. `specs/future/DEEPWIKI_OPEN_ARCHITECTURE_BORROWING_SPEC.md` — **future / not approved**. Reference-only architecture borrowing ideas from `deepwiki-open`.

## Cleanup rules for future agents

- Prefer one README: update this file rather than adding nested `README.md` files under docs subfolders.
- Move docs with `git mv` so history is preserved.
- When a doc is no longer current, either move it to a `done/` folder and mark it superseded/archive in this journal, or update its top status banner if it already has one.
- Do not create competing specs for the same active iteration. Update the canonical `specs/not-done/...` file until the iteration is complete.
- Keep `future/` separate from `not-done/`: future means proposed/not approved; not-done means active/approved but unfinished.
- `.sessions/` checklists are adviser/sign-off state only. If they reveal durable pending implementation work, mirror it into `specs/not-done/`, `handoffs/not-done/`, and this sequence journal.
- Before committing a docs reorg, run a stale-reference scan and `git diff --check`.
