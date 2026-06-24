# Handoff: DeepWiki-Informed Coverage Enhancement Iteration

## Canonical spec

Use exactly one iteration spec for the next coding-agent work:

```text
PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md
```

Older split drafts for writing-validation-only, broader coverage-only, or
"parity" framing are intentionally removed/superseded. Do not create competing
spec files for this iteration.

Current implementation status: **Milestone 1 is implemented locally and tested;
Milestone 2 is not implemented.**

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

Next coding work should focus on Milestone 2: coverage taxonomy, hierarchical
planning/evidence/writing design, and non-live validation scaffolding. Do not
begin a broad implementation without a concrete plan.

## Required guardrails

- Do not modify `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Do not weaken validators.
- Do not use `ragflow-deepwiki.md` as citeable evidence.
- Do not chase line count with filler.
- Do not run Vertex/Gemini/API/live models.
- Do not perform a live/billed retry without explicit user approval.

## Acceptance commands

```bash
git diff --check
git diff --exit-code -- PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
python -m pytest -q tests/test_phase4.py
python -m pytest -q
```
