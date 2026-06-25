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
expansion, the Phase 2 enhancement-mode planned-coverage upstream-prevention gate
(`normalize-plan --coverage-mode enhancement`), the Phase 3 evidenced-coverage
gate (`retrieve-evidence --coverage-mode enhancement`), and the Phase 4
enhancement-mode hierarchical writing + generated-coverage gate
(`write-wiki --coverage-mode enhancement`) are implemented and tested
(non-live). Pending next: non-live hierarchical E2E and benchmark-only comparison
before any approved live retry.**

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

## Coverage sufficiency model

The coverage question is answered in layers, not by one phase:

1. **Planned coverage (Phase 2):** the normalized plan names the required topic
   families/pages/topics. This is now implemented through the planned-coverage
   gate, but it does not prove evidence exists.
2. **Evidenced coverage (Phase 3):** retrieval now validates that each planned
   page and required topic has enough citeable repo evidence. In enhancement
   mode, `weak` or `missing` required-topic evidence is a **pipeline failure
   before Phase 4**, not something to heal, synthesize, retry-until-green, or pass
   to the writer as supported.
3. **Generated coverage (Phase 4):** the final wiki must actually explain the
   planned/evidenced topics with valid citations and strict validators.

The benchmark export `ragflow-deepwiki.md` is only a coverage/structure warning
signal. It must not be counted as evidence.

### Implemented Phase 3 contract

The implementation provides a deterministic evidenced-coverage gate, not a healing
loop.

Implemented contract:

- Preserve/consume additive normalized SectionPlan field
  `topic_evidence_requirements[]` in baseline-compatible fashion.
- In enhancement mode, each required topic must map to explicit source fields such
  as `retrieval_needs.files[0]`, `retrieval_needs.symbols[1]`,
  `retrieval_needs.contracts[0]`, `retrieval_needs.tests[0]`, or
  `retrieval_needs.query_packs[0]`.
- Map those source fields to existing Phase 3 exact-request coverage records and
  final citeable `evidence_id`s. Do not use fuzzy prose matching to claim topic
  support.
- Write deterministic `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`, and surface the result through the
  manifest or retrieval validation artifacts.
- Statuses are `sufficient`, `weak`, `missing`, and `not_applicable`.
- In enhancement mode, `weak` or `missing` required-topic evidence exits `3` with
  `bad_underspecified_normalized_plan` before Phase 4 can run.
- Baseline mode remains non-breaking for legacy/compact fixtures.
- No synthetic evidence, no silent required-to-optional downgrade, no fallback
  rescue, no product `--section`, no `--force`, no retry-until-green, and no
  validator weakening.

### Concrete non-live E2E contract for the next agent

The next agent should prove the completed enhancement gates together in one fresh
non-live hierarchical run, then do a benchmark-only coverage/structure comparison.
This is a validation/integration slice, not a live retry.

Required contract:

- Create a fresh run under
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/non-live-hierarchical-runs/<run-id>/`.
- Use an expanded multi-family hierarchical plan or deterministic fixture that
  exercises parent/child pages and multiple mandatory coverage families, with
  `coverage_labels[]`, `parent_section_id`, `required_topics[]`, and
  `topic_evidence_requirements[]` preserved.
- Run or exercise the real enhancement gates together:
  `normalize-plan --coverage-mode enhancement`,
  `retrieve-evidence --coverage-mode enhancement`, and
  `write-wiki --coverage-mode enhancement`.
- Verify the shell wrappers expose/pass the enhancement flags. In particular,
  check/fix `scripts/phase2_step2_normalize_plan.sh`,
  `scripts/phase3_retrieve_evidence.sh`, and `scripts/phase4_write_wiki.sh` so
  operators can reproduce the enhancement path without bypassing scripts.
- Use fake-provider or deterministic responses only for Phase 4. No Vertex,
  Gemini API, Gemini Gem live/manual production flow, network model call, or
  billed model is allowed.
- Produce `command-manifest.tsv`, `command-transcript.log`, passing planned/
  evidenced/generated coverage artifacts, nested `wiki/index.md`, and
  `NON_LIVE_HIERARCHICAL_E2E_RESULT.md`.
- Compare against `/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md` as a
  benchmark-only coverage/structure warning signal. Never cite it as evidence and
  do not copy prose/headings to satisfy coverage.
- If a deterministic wrapper, validator, or artifact contract defect appears, fix
  that upstream and rerun from the affected phase. Do not hand-edit downstream
  artifacts, add generic healing loops, synthesize evidence, add filler topics,
  downgrade required topics, weaken validators, or edit historical live wiki
  artifacts.
- End with a clear verdict: whether non-live E2E passes, what gaps remain, and
  whether it is reasonable to ask the user for explicit live/billed retry approval.

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

### Milestone 2 — Phase 3 evidenced-coverage gate (implemented, non-live)

Implemented after the planned-coverage gate. This is the Phase 3 Evidence
Sufficiency Contract: a deterministic per-required-topic evidence gate, not a
healing loop.

- Phase 2 normalization preserves the additive, baseline-compatible
  `topic_evidence_requirements[]` SectionPlan field (`normalize._topic_evidence_requirements`):
  each item normalizes to `{topic, required(default true), source_fields[],
  min_items(default 1), acceptable_lanes[](default exact lanes)}`; a plan that
  omits it normalizes to `[]`.
- `src/wiki_generator/libs/evidence/evidenced_coverage.py` —
  `evaluate_evidenced_coverage(bundle, packets, options)` maps each planned
  required topic through its `source_fields[]` to the packet's
  `coverage.exact_requests[]` records and their final `evidence_id`s (the
  deterministic bridge — no fuzzy prose matching). Statuses: `sufficient`
  (≥`min_items` citeable IDs from covered exact lanes within `acceptable_lanes`),
  `weak` (below threshold / only broad recall / resolved-but-unmapped), `missing`
  (no valid source fields, no related evidence, or no `topic_evidence_requirements`
  for a required topic), `not_applicable` (provenance/meta sections). Broad recall
  (`bm25`/`vector`/`graph_neighbors`/`search_hints`) is supporting context only and
  never makes a topic `sufficient`.
- `retrieve-evidence` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). `EvidenceOptions.coverage_mode` is validated. Enhancement mode makes
  a `weak`/`missing` required topic a blocking plan-quality failure BEFORE Phase 4:
  exit `3`, `bad_underspecified_normalized_plan`, via a `required_topic_evidence_sufficient`
  contract check in `retrieval-validation.json`. Baseline stays non-breaking
  (reports the matrix, adds no gate/contract check).
- Deterministic, timestamp-free artifacts: `evidence/evidenced-coverage.json`
  (per-section/per-topic matrix with counts, evidence IDs, source categories,
  remediation, diagnostic codes `required_topic_evidence_weak`/`_missing`) and
  `evidence/evidenced-coverage-report.md`. The evidence manifest references both
  (`evidenced_coverage`, `evidenced_coverage_report`, `evidenced_coverage_status`,
  `coverage_mode`).
- Planner prompt surfaces (`GEM_INSTRUCTIONS.md`, `KICKOFF_PROMPT.md`,
  `plan._DEFAULT_SYSTEM`/`_DEFAULT_KICKOFF`) now ask for
  `topic_evidence_requirements[]` pointing at exact `retrieval_needs.*` source
  fields, and explain that broad recall is never sufficient and over-requiring
  fails before Phase 4.
- No healing loop, no `--section`/`--force`, no synthetic evidence, no
  required→optional downgrade, no validator weakening. The gate is read-only and
  fails upstream.
- `tests/test_phase3_evidenced_coverage.py` (20 tests): pure-evaluator units
  (sufficient/weak/missing/not_applicable, below-threshold, lane-excluded, union,
  baseline report-only); E2E over a real decomposed+retrieval-built bundle
  (enhancement pass; mapped IDs are real packet IDs; missing → exit 3; broad-recall
  → weak/exit 3; baseline + default non-breaking; rerun byte-identical);
  normalization preservation; CLI surface (no `--section`/`--force`).

Acceptance commands run (non-live): `git diff --check` (clean),
`git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`
(unchanged), `pytest tests/test_phase3.py tests/test_phase2_coverage_planning.py
tests/test_phase2_enhancement_gate.py tests/test_phase3_evidenced_coverage.py`, and
the full suite (`388 passed, 1 skipped` — the skip is the pre-existing faiss-backend
test). No Vertex/Gemini/API/network; no historical wiki edits.

Risks / notes: enhancement mode is opt-in and NOT wired into the default Phase 4
path (it would fail the compact fixture bundles, exactly as the planned-coverage
gate). The two evidenced-coverage artifacts are now written on every Phase 3 run
(baseline = report-only) and referenced from the manifest — additive, deterministic,
and verified byte-identical on rerun.

### Milestone 2 — Phase 4 enhancement-mode hierarchical writing + generated-coverage gate (implemented, non-live)

Implemented after the evidenced-coverage gate. This is the Phase 4 Generated
Coverage Contract: an opt-in `write-wiki --coverage-mode enhancement` mode that
trusts and consumes the upstream Phase 2/3 enhancement gates and validates generated
coverage deterministically. Baseline/default is fully non-breaking.

- `write-wiki` gains `--coverage-mode {baseline,enhancement}` (default `baseline`).
  `WritingOptions.coverage_mode` is validated; the wrapper omits it when absent so an
  older arg namespace defaults to baseline.
- `src/wiki_generator/libs/writing/generated_coverage.py` (new) is the engine:
  `read_enhancement_gates` (pre-provider) requires `plans/coverage-gate.json` to be an
  enforced enhancement gate with `passed`/`status: pass`, `evidence/evidenced-coverage.json`
  to be `coverage_mode: enhancement` / `enforced: true` / `status: pass`, and the
  `required_topic_evidence_sufficient` retrieval-validation contract check to be
  present and passing; `build_topic_obligations` derives per-section required-topic
  obligations with exact Phase 3 `mapped_evidence_ids`; `evaluate_generated_coverage`
  checks the writer's `covered_topics[]` against the generated markdown (every
  sufficient required topic declared `covered`, evidence IDs within the topic's mapped
  set, resolving through the citation manifest, cited within the topic's local block
  near its text/anchor).
- `libs/writing/bundle.py` runs the enhancement gate as a sixth pre-provider gate in
  `load_and_gate` (missing/baseline/failed upstream gate → `GateFailure`, exit 3) and
  attaches `coverage_mode` / `evidenced_coverage` / `topic_obligations` to the
  `WritingBundle`.
- `libs/writing/packet.py` + `prompt.py` carry the planned hierarchy and evidenced
  topic rows into each WritingPacket/prompt and extend the section response contract
  with `covered_topics[]` (backward-compatible; baseline unchanged).
- `libs/writing/validate.py` threads `covered_topics[]` through section validation
  and adds the named final check `generated_required_topics_covered`; a generated
  coverage failure is a writing-validation failure (exit 5) after provider output, not
  a rewrite target.
- `libs/writing/assemble.py` renders a nested `index.md` from `parent_section_id`
  (flat when no hierarchy, so compact fixtures are byte-identical), augments
  `generated-sections.jsonl` rows with hierarchy + evidenced/generated topic status,
  references the coverage artifacts + hierarchy from `generated-document.json`, and
  writes `wiki/metadata/generated-coverage.json` + `wiki/validation/generated-coverage-report.md`.
- All existing writing validators stay strict; no healing loop, synthetic filler,
  required→optional downgrade, post-hoc `covered_topics[]` mutation, or use of
  `ragflow-deepwiki.md` as evidence.
- `tests/test_phase4_generated_coverage.py` (24 tests): enhancement happy path over a
  real decomposed+retrieval-built bundle (nested index + generated-coverage artifacts;
  packets carry exact mapped IDs; rerun byte-identical); pre-provider exit-3 gate
  failures (missing/baseline/failed planned gate, missing/baseline evidenced gate,
  missing retrieval contract check — with NO provider call); post-provider exit-5
  failures (omitted topic, declared-without-local-citation, out-of-scope id,
  placeholder-only); baseline/default non-breaking; pure-evaluator units; CLI surface.

Work log (this slice): files changed — `cli.py`, `libs/commands/write_wiki.py`,
`libs/writing/{options,schema,bundle,packet,prompt,validate,assemble,__init__}.py`,
new `libs/writing/generated_coverage.py`, new `tests/test_phase4_generated_coverage.py`,
plus `README.md`, `RUNBOOK.md`, `docs/README.md`, this handoff, and the active spec.
Verification (non-live): `git diff --check` clean; `git diff --exit-code --
docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` unchanged; `pytest -q
tests/test_phase4.py tests/test_phase3_evidenced_coverage.py
tests/test_phase2_enhancement_gate.py tests/test_phase4_generated_coverage.py` →
160 passed; full suite `412 passed, 1 skipped` (pre-existing faiss-backend skip). No
Vertex/Gemini/API/network; no historical wiki edits; protected spec untouched.
Risks/notes: enhancement mode is opt-in and NOT wired into the default Phase 4 path
(it would fail the compact fixtures, exactly like the upstream gates). Phase 4 trusts
`plans/coverage-gate.json`; tests hand-write a passing gate on a 2-section bundle
because Phase 2's 13-family gate (separately tested) cannot pass a compact plan — the
real producer is `normalize-plan --coverage-mode enhancement`.

### Remaining Milestone 2 work — active pending backlog

- **Next slice:** non-live/fake-provider hierarchical E2E over an expanded
  multi-family plan (planning → evidence → writing), keeping all validators strict.
- **Then:** benchmark-only comparison against `ragflow-deepwiki.md` (structure/
  coverage only, never citeable evidence).

Do not begin the next pipeline-expansion slice without a concrete prompt, and do
not run a live/billed retry without explicit user approval.

### Completed-slice acceptance summary — Phase 3 evidenced coverage

This slice is accepted because non-live tests show:

- Phase 2 normalization preserves `topic_evidence_requirements[]` without making
  it mandatory in baseline mode.
- Planner prompt surfaces ask for deterministic topic evidence requirements in
  enhancement-mode planning.
- Phase 3 reads `coverage_labels[]`, `parent_section_id`, `required_topics[]`, and
  `topic_evidence_requirements[]` from the normalized plan.
- Phase 3 writes deterministic `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`.
- Required topics map to citeable `evidence_id`s through exact source-field
  coverage records, not fuzzy prose matching.
- Each topic receives `sufficient`, `weak`, `missing`, or `not_applicable` status
  with counts, evidence IDs/handles, source categories, and remediation.
- In enhancement mode, `weak` or `missing` required-topic evidence is a blocking
  **pipeline failure before Phase 4**, exits `3`, and uses
  `bad_underspecified_normalized_plan`; baseline remains non-breaking.
- Context artifacts, `derived/`, `plans/`, generated wiki files, and
  `ragflow-deepwiki.md` are never counted as citeable evidence.
- No generic retrieval healing loop, no product `--section` retry mode, no
  `--force` after readiness failure, no fallback rescue for no-signal sections,
  no synthetic evidence, no silent downgrade to optional, and no validator
  weakening.

### Next-slice acceptance summary — non-live hierarchical E2E and benchmark-only review

The next slice should be accepted only if non-live artifacts show:

- planned, evidenced, and generated coverage enhancement gates all pass together
  in one fresh hierarchical run;
- wrapper scripts expose/pass `--coverage-mode enhancement` for Phase 2
  normalization, Phase 3 retrieval, and Phase 4 writing where applicable;
- the run uses an expanded multi-family hierarchical plan, not only the compact
  two-page generated-coverage unit fixture;
- Phase 4 uses fake-provider or deterministic responses only; no live/billed model
  is called;
- `wiki/metadata/generated-coverage.json`,
  `wiki/validation/generated-coverage-report.md`, nested `wiki/index.md`, and
  generated-section/document metadata are present and passing;
- `NON_LIVE_HIERARCHICAL_E2E_RESULT.md` records exact commands, exit codes, gate
  statuses, coverage counts, evidence counts, determinism/rerun notes, and whether
  any wrapper/code changes were required;
- benchmark-only comparison against `ragflow-deepwiki.md` identifies remaining
  coverage/structure gaps without using it as evidence or chasing line count;
- focused tests and full suite pass using `uv run python -m pytest -q`;
- protected Phase 3 spec is unchanged, validators remain strict, no historical
  generated wiki is edited, and no generic healing/synthetic-evidence/filler path
  is introduced.

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
uv run python -m pytest -q tests/test_phase4_generated_coverage.py tests/test_phase4.py
uv run python -m pytest -q tests/test_phase3_evidenced_coverage.py tests/test_phase2_enhancement_gate.py
uv run python -m pytest -q
```
