# Handoff: DeepWiki-Informed Coverage Enhancement Iteration

> **Status:** Active / not done. This is the current handoff for the DeepWiki-informed coverage enhancement iteration.

## Canonical spec

Use exactly one iteration spec for the next coding-agent work:

```text
docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md
```

Older split drafts for writing-validation-only, broader coverage-only, or
"parity" framing are intentionally removed/superseded. Do not create competing
spec files for this iteration.

Current implementation status: **Milestone 1 is implemented and tested.
Milestone 2 is in progress: coverage taxonomy/validation, Phase 2
planning/PagePlan obligation preservation, Phase 1 deterministic coverage-signal
expansion, and the Phase 2 enhancement-mode planned-coverage upstream-prevention gate
(`normalize-plan --coverage-mode enhancement` deterministic planned-coverage boundary +
coverage-signal-aware planner prompts) are implemented and tested (non-live).
Pending next: Phase 3 page-level evidence, Phase 4 hierarchical writing, and
non-live hierarchical E2E before any approved live retry.**

## Why this exists

The live Phase 4 run at:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730
```

passed the existing pipeline gates and generated a grounded baseline wiki, but
comparison with:

```text
/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md
```

showed two separate problems:

1. **Immediate validation bug:** malformed evidence-like token
   `[ev:data-models:010]` escaped validation.
2. **Coverage target gap:** the generated wiki is a compact 16-section baseline,
   not a DeepWiki-informed repository guide with richer topic coverage and
   hierarchy.

## Root cause

The 14,717-line reference vs roughly 749-line generated output gap is mainly a
pipeline/spec/planning/evidence-scope issue, not a simple LLM failure.

- Phase 1 did not expose enough planner-facing subsystem/topic signals.
- Phase 2 planned 16 broad sections, not a hierarchical guide.
- Phase 3 retrieved evidence for broad sections, not page-level obligations.
- Phase 4 wrote within those constraints and should not invent missing pages.
- The LLM did create the malformed citation token.
- The validator missed that malformed `ev:` token.

## Next coding-agent work

Milestone 1 from the canonical spec is complete locally:

- malformed `[ev:...]` and dangling `[ev:` tokens are detected;
- malformed-token failures are rewriteable during bounded drafting;
- final validation fails closed if malformed tokens remain;
- unit and fake-provider tests were added;
- historical generated wiki artifacts were not edited in place.

### Milestone 2 — coverage-validation slice (implemented, non-live)

A first, safe, non-live Milestone 2 slice is implemented and tested:

- `src/wiki_generator/libs/coverage/taxonomy.py` — the thirteen mandatory topic
  families with explicit coverage labels and distinctive keyword signals.
- `src/wiki_generator/libs/coverage/validate.py` — `evaluate_plan_coverage(...)`
  with `enhancement` (fail-closed) and `baseline` (report-only) modes, a
  per-family coverage matrix, actionable diagnostics, a markdown renderer, and a
  plan loader.
- `validate-coverage` CLI command — gates a bundle's normalized plan (exit 3 on a
  missing mandatory family in enhancement mode) and writes a coverage report; it
  is standalone and does NOT change Phase 3 retrieval or the default Phase 4 path.
- `tests/test_coverage_validation.py` — compact 16-section baseline fails
  enhancement coverage; expanded plan passes; missing frontend/memory/queue is
  flagged with diagnostics; broad parents do not satisfy deep children; the CLI
  gate works; Milestone 1 malformed-token validation stays intact.

### Milestone 2 — Phase 2 planning/PagePlan obligation slice (implemented, non-live)

Implemented after the coverage-validation scaffold:

- normalized Phase 2 plans preserve canonical `coverage_labels[]`,
  `parent_section_id`, merged `required_topics[]`, and `expected_sources[]`;
- parent/child hierarchy is shown in `document-plan.md`;
- `normalization-report.md` includes a baseline/report-only DeepWiki coverage
  matrix without gating readiness;
- planner prompt surfaces request canonical coverage labels, child-page hierarchy,
  and the broad-parent-does-not-satisfy-deep-child rule;
- `tests/test_phase2_coverage_planning.py` proves the behavior.

### Milestone 2 — Phase 1 coverage-signal slice (implemented, non-live)

Implemented after the planning-obligation slice:

- `src/wiki_generator/libs/coverage/signals.py` derives deterministic
  planner-facing signals for all thirteen mandatory families;
- `src/wiki_generator/libs/digest/planning_coverage_signals.py` renders the
  planner condensate;
- Phase 1 condense/digest emits `derived/planning-coverage-signals.md` plus
  `derived/coverage-signals.json`;
- planner upload includes the coverage-signals condensate with a loud
  context-only / not-citeable warning;
- missing or low-signal families are reported rather than hidden;
- `tests/test_coverage_signals.py` proves deterministic detection and upload
  integration.

### Milestone 2 — Phase 2 enhancement-mode planned-coverage upstream-prevention gate (implemented, non-live)

Implemented after the coverage-signal slice:

- `src/wiki_generator/libs/coverage/validate.py` adds the shared deterministic gate
  `gate_plan_coverage(...)` → `CoverageGate` (verdict + exit code + actionable
  `summary_lines()`) and `load_plan_from_dir(...)`; exit codes 0/2/3;
- `normalize-plan` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). `enhancement` gates the just-written normalized plan against all 13
  families, writes `plans/coverage-gate.json` + `plans/coverage-gate-report.md`,
  logs diagnostics, and exits 3 on a missing family before Phase 3. `baseline`
  stays non-breaking (existing non-enforcing matrix only);
- `validate-coverage` now shares the same gate. No generic healing loop was added;
  bounded LLM re-prompt remains the separate audited `plan-repair` step;
- planner prompts (`GEM_INSTRUCTIONS.md`, `KICKOFF_PROMPT.md`,
  `plan._DEFAULT_SYSTEM`/`_DEFAULT_KICKOFF`) now explicitly cite
  `planning-coverage-signals.md` as planner CONTEXT, not citeable evidence;
- `coverage_labels[]`, `parent_section_id`, merged `required_topics[]`,
  `expected_sources[]` continue to survive normalization;
- `tests/test_phase2_enhancement_gate.py` proves pass/fail/exit-code behaviour,
  missing-family diagnostics, broad-parent-not-deep-child, baseline non-breaking,
  no synthesize/heal, prompt context-only references, and Milestone 1 intact.

### Remaining Milestone 2 work — active pending backlog

- **Next slice:** Phase 3 per-page/child evidence retrieval with per-required-topic
  sufficiency reporting, preserving all existing Phase 3 constraints.
- **Then:** Phase 4 hierarchical writing emitting planned-vs-generated coverage
  metadata and keeping all validators strict.
- **Then:** non-live/fake-provider hierarchical E2E plus benchmark-only
  comparison against `ragflow-deepwiki.md`.

Do not begin the next pipeline-expansion slice without a concrete prompt, and do
not run a live/billed retry without explicit user approval.

### Next-slice acceptance summary

The next Phase 2 slice should be accepted only if non-live tests show:

- the planner prompt/context uses `planning-coverage-signals.md` as context only;
- enhancement mode gates planned coverage in the normalized plan before Phase 3; it does not claim evidence or generated-content readiness;
- missing mandatory families fail loudly with actionable diagnostics;
- baseline mode remains non-breaking/report-only;
- deterministic code does not synthesize or heal missing pages/labels/source
  obligations;
- any LLM re-prompt is bounded, audited, diagnostic-fed, and followed by the same
  strict normalized-plan gate;
- `coverage_labels[]`, `parent_section_id`, merged `required_topics[]`, and
  `expected_sources[]` continue to survive normalization;
- compact/missing-family fixtures fail enhancement mode, expanded hierarchical
  fixtures pass, and Milestone 1 malformed-citation validation remains intact.

## Required guardrails

- Do not modify `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Do not weaken validators.
- Do not use `ragflow-deepwiki.md` as citeable evidence.
- Do not chase line count with filler.
- Do not run Vertex/Gemini/API/live models.
- Do not perform a live/billed retry without explicit user approval.

## Acceptance commands

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
python -m pytest -q tests/test_phase4.py
python -m pytest -q
```
