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
gate (`retrieve-evidence --coverage-mode enhancement`), the Phase 4
enhancement-mode hierarchical writing + generated-coverage gate
(`write-wiki --coverage-mode enhancement`), the non-live hierarchical E2E +
benchmark-only comparison, and the Phase 2 required-topic evidence-obligation
alignment gate are implemented and tested non-live. A live/billed RAGFlow retry at
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-141745`
against `35bdc18` failed closed before Phase 3: planned coverage passed 13/13, but
the Phase 2 topic-obligation gate failed after bounded Step 1b repair (`0/46`
complete required-topic obligations; 21 missing TER rows and 25 invalid/broad-only
source-field mappings, commonly raw `evidence_needs.*` names where canonical
`retrieval_needs.*` fields are expected). Phase 3 and Phase 4 did not run. The
**Phase 2 TER source-field canonicalization + enhancement-repair diagnostics** slice
is now implemented and tested non-live (see the implemented-slice section below).
Pending next: explicit user approval for any further live/billed RAGFlow retry; no
further live/billed retry unless the user explicitly approves it.**

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

### Milestone 2 — Phase 2 required-topic evidence-obligation alignment gate (implemented, non-live)

Implemented after the failed live RAGFlow diagnostic run. This upstream Phase 2
gate prevents required topics from reaching Phase 3 without exact citeable evidence
obligations. The failed live run remains diagnostic input only.

Implemented contract:

- Diagnosed the mismatch shown by live run
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-081444`:
  `coverage_requirements[]` are merged into normalized `required_topics[]`, but
  the planner prompt required `topic_evidence_requirements[]` only for authored
  `required_topics[]`.
- Updated planner prompt/schema wording so every Phase-3-required topic,
  including any normalized coverage requirement, must have a matching exact
  source-field `topic_evidence_requirements[]` row.
- Added deterministic enhancement-mode Phase 2 obligation-completeness gating to
  `normalize-plan --coverage-mode enhancement`. It writes
  `plans/topic-obligations-gate.json` and `plans/topic-obligations-report.md`, and
  exits `3` before Phase 3 for missing topic evidence rows, broad-only source
  fields, invalid source-field references, or acceptable lanes that cannot produce
  citeable sufficient evidence.
- Kept baseline/default behavior non-breaking; baseline writes no obligation gate.
- Did not extend bounded `plan-repair`.
- Added focused tests for the live failure pattern: merged
  `coverage_requirements[]` becoming required topics without matching
  `topic_evidence_requirements[]`.
- Added tests proving broad-only/search-hint-only required-topic support fails
  before Phase 3 in enhancement mode.
- Added passing fixtures proving an expanded hierarchical plan with exact
  source-field obligations still passes.
- No Vertex, Gemini API, Gemini Gem live/manual production flow, or billed model
  was run.
- Phase 3/4 validators remain strict; no synthetic evidence, benchmark-derived
  evidence, silent downgrade, downstream artifact edit, or generic healing path was
  introduced.

## Implementation log / completed work

Milestone 1 from the canonical spec is complete:

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

### Milestone 2 — non-live hierarchical E2E + benchmark-only comparison (implemented, non-live)

The final non-live validation slice is complete: all three enhancement gates were
proven to interoperate over one fresh, expanded, multi-family, hierarchical plan
using the real production CLI, plus a benchmark-only structure comparison.

- **Shell wrapper fix (deterministic upstream defect).** The three phase wrappers
  did not expose/pass the implemented `--coverage-mode` flag. Fixed
  `scripts/phase2_step2_normalize_plan.sh`, `scripts/phase3_retrieve_evidence.sh`,
  and `scripts/phase4_write_wiki.sh` to add `--coverage-mode {baseline,enhancement}`
  (usage + arg parse + pass-through; omitted when unset so the CLI default stays
  authoritative). `tests/test_phase_wrappers.py` proves the surface deterministically
  (the `--help` path exits before any venv install, so the test is fast/offline).
- **Non-live E2E harness.** `scripts/nonlive_hierarchical_e2e.py` (no model calls)
  builds a synthetic 13-family `ragdemo` repo with one real class symbol per
  mandatory family, authors a raw Phase 2 planner response, and drives the **real**
  `normalize-plan` / `retrieve-evidence` / `write-wiki --provider gemini-gem`, all
  `--coverage-mode enhancement`. Phase 4 uses the real gemini-gem import path with
  per-section response fixtures synthesized deterministically from the **real** Phase
  3 evidenced-coverage matrix (the exact mapped `evidence_id`s — no synthetic
  evidence, no model). It includes a non-destructive negative probe (Phase 4 refuses
  pre-provider, exit 3, when the planned gate is moved aside) and a same-inputs rerun
  determinism check.

Work log (this slice): files changed — `scripts/phase2_step2_normalize_plan.sh`,
`scripts/phase3_retrieve_evidence.sh`, `scripts/phase4_write_wiki.sh`,
new `scripts/nonlive_hierarchical_e2e.py`, new `tests/test_phase_wrappers.py`, plus
this handoff, the active spec, `docs/README.md`, `README.md`, and `RUNBOOK.md`.
Run path: `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/non-live-hierarchical-runs/20260624-nonlive/`
(outside the repo tree; bulky bundle/wiki NOT committed). Verdict: **PASS** —
planned 13/13 families, evidenced 13/13 sufficient, generated 13/13 covered,
whole-document writing-validation pass, byte-identical on rerun, negative probe
exit 3; benchmark (`ragflow-deepwiki.md`, 909 headings / 14,717 lines) compared as
structure-only with no prose copied. Tests run (non-live): `git diff --check` clean;
`git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`
unchanged; focused `tests/test_phase4_generated_coverage.py tests/test_phase4.py
tests/test_phase3_evidenced_coverage.py tests/test_phase2_enhancement_gate.py
tests/test_phase_wrappers.py` → 163 passed; full suite `415 passed, 1 skipped`
(pre-existing faiss skip). No Vertex/Gemini/API/network; no historical wiki edits;
protected spec untouched. Risks: the fixture repo is synthetic (proves gate interop +
strictness, not that real RAGFlow has sufficient evidence per family); enhancement
mode stays opt-in and is NOT wired into the default Phase 4 path.

### Live retry after Phase 2 obligation gate — failed closed at Phase 2

Run:
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-141745`

- Commit: `35bdc18`.
- Phase 1 completed.
- Phase 2 live planning completed.
- Initial `normalize-plan --coverage-mode enhancement --strict` failed at the new
  topic-obligation gate.
- Bounded Step 1b plan repair ran once and reported old Phase-3 readiness PASS.
- Re-running strict enhancement normalization on the accepted repair still failed
  at `plans/topic-obligations-gate.json`.
- Planned coverage passed: `13/13` mandatory families.
- Topic obligations failed: `0/46` required topics complete, `46/46` incomplete,
  `21` blocking sections; `21` missing TER rows and `25` invalid/broad-only
  source-field mappings.
- Common invalid pattern: planner/repair output used raw-plan field names such as
  `evidence_needs.file_anchors[0]`, `evidence_needs.symbol_ids[0]`, and
  `evidence_needs.query_packs[0]` inside TER `source_fields[]`, while the gate
  currently expects canonical normalized `retrieval_needs.files[0]`,
  `retrieval_needs.symbols[0]`, and `retrieval_needs.query_packs[0]`.
- Phase 3 and Phase 4 did not run.

### Milestone 2 — Phase 2 TER source-field canonicalization + enhancement repair (implemented, non-live)

Implemented after the live retry exposed raw `evidence_needs.*` TER source-field
aliases the topic-obligation gate could not read. The failed live run remains
diagnostic input only.

- `plan_normalization/normalize.py`: `_resolve_needs` now returns
  `(needs, lane_maps)` where `lane_maps` is the deterministic per-lane raw-index →
  normalized-index map (`None` for a pruned/unresolved/routed raw item), built while
  resolving needs so it follows pruning index shifts exactly.
  `_canonicalize_ter_source_field` rewrites a documented raw
  `evidence_needs.<alias>[N]` to canonical `retrieval_needs.<lane>[M]` ONLY when raw
  item `N` resolved to normalized item `M`; otherwise the raw alias is left verbatim
  (the gate fails loudly) with a traceable normalization warning. Broad aliases
  (`search_hints`/`graph_nodes`) canonicalize only to broad fields and stay
  insufficient. A lane authored under BOTH raw keys
  (`files`+`file_anchors` / `symbols`+`symbol_ids`) is ambiguous and is left
  uncanonicalized rather than guessed. Bare/already-canonical fields are unchanged.
- `coverage/obligations.py`: adds the dedicated, more actionable diagnostic
  `topic_evidence_requirement_raw_alias_source_field` for a leftover raw alias; raw
  aliases stay blocking (gate not weakened).
- `plan_normalization/repair.py` + `plan-repair --coverage-mode enhancement`: repair
  success now means readiness AND the planned-coverage gate AND the topic-obligation
  gate all pass. A repair that passes only old readiness but fails topic obligations is
  rejected; the exact topic-obligation diagnostics are written to the audit
  (`repair/attempt-N/obligation-diagnostics-fed.json`) and fed into the next attempt's
  prompt; the final post-repair verdict is recorded
  (`repair/attempt-N/enhancement-gates.json`); after the hard cap it fails loudly.
  Baseline mode is unchanged. `scripts/phase2_step1b_repair_plan.sh` exposes/passes
  `--coverage-mode`.
- Planner prompts (`plan.py`, `gemini-gem/GEM_INSTRUCTIONS.md`,
  `gemini-gem/KICKOFF_PROMPT.md`) explain that raw `evidence_needs.*` aliases are
  compatibility input canonicalized only when the exact raw handle resolves; canonical
  `retrieval_needs.*` is preferred and broad-only support stays forbidden.
- Tests: `tests/test_phase2_obligation_gate.py` adds raw file/symbol alias
  canonicalization, the non-naïve pruned-index remap (raw `[1]`→normalized `[0]`) with
  the pruned item left invalid, dual-key ambiguity left invalid, broad-alias
  canonicalization that stays blocking, a live-style raw-alias plan that passes after
  canonicalization, already-canonical/bare unchanged, and fake-client bounded
  enhancement repair (reject old-readiness-only, feed diagnostics forward, accept only
  on strict gate pass, fail loudly after cap, baseline non-breaking).
  `tests/test_phase1.py` updated for the `_resolve_needs` tuple return.

Verification (non-live): `git diff --check` clean; protected Phase 3 spec unchanged;
`pytest -q tests/test_phase2_obligation_gate.py tests/test_phase2_enhancement_gate.py
tests/test_phase2_readiness.py tests/test_phase2_coverage_planning.py
tests/test_phase3_evidenced_coverage.py tests/test_phase4_generated_coverage.py
tests/test_phase4.py`; full suite `450 passed, 1 skipped` (pre-existing faiss skip).
No Vertex/Gemini/API/network; no historical wiki edits; validators unchanged or
stricter; baseline non-breaking.

### Live retry after Milestone 2 — failed before Phase 3, parse-repair bug fixed non-live

A user-approved retry at
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-154907`
ran against `1ec2fc6`. Phase 1 and live Phase 2 planning completed. Strict
`normalize-plan --coverage-mode enhancement` failed with a deterministic parse
ambiguity: the raw planner response contained multiple JSONL fences, so the parser
refused to guess which block was `section-plans.jsonl`. Step 1b was correctly invoked
with `--coverage-mode enhancement`, but `plan-repair` crashed on that initial
`ParseError` before writing repair audit artifacts or making the bounded repair
model call. Phase 3 and Phase 4 did not run.

Non-live follow-up fix: `plan_normalization/repair.py` now catches an initial
raw-response `ParseError`, extracts only the unambiguous DocumentPlan when possible
for section-identity enforcement, feeds the parse failure as
`raw_planning_response_parse_error` diagnostics into the bounded repair prompt, and
keeps the strict parser fail-closed for normal acceptance. It still rejects repaired
outputs that add/remove non-diagnostic sections. Regression coverage in
`tests/test_phase2_readiness.py` exercises the exact multiple-JSONL-fence shape and
section-identity enforcement after an initial parse failure. Verification: `git diff
--check`; protected Phase 3 spec unchanged; focused Phase 2 suites `117 passed`; full
suite `453 passed, 1 skipped, 9 subtests passed`.

### Remaining Milestone 2 work — active pending backlog

Default remains **no live retry**. The next remaining step is **explicit user
approval for another billed Vertex/Gemini retry over the real RAGFlow repo** against
the stricter Phase 2 obligation gate + canonicalization/repair + parse-repair fix.
Do not run another live/billed retry without that explicit approval.

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

### Completed-slice acceptance summary — Phase 2 obligation alignment

This slice is accepted because non-live artifacts/tests show:

- `normalize-plan --coverage-mode enhancement` fails before Phase 3 for normalized
  required topics that lack matching `topic_evidence_requirements[]` rows;
- it also fails before Phase 3 for broad-only/search-hint-only required-topic
  support;
- it passes for an expanded hierarchical fixture where every normalized required
  topic has exact citeable source-field obligations;
- prompt/schema wording no longer creates a `coverage_requirements[]` versus
  `required_topics[]` evidence-obligation mismatch;
- any bounded repair remains narrow, audited, capped, LLM-plan-artifact-only, and
  followed by strict deterministic validation;
- baseline mode remains non-breaking;
- focused tests and full suite pass using `uv run python -m pytest -q`;
- protected Phase 3 spec is unchanged, validators remain strict, no historical
  generated wiki is edited, and no generic healing/synthetic-evidence/filler path
  is introduced.

## Required guardrails

- Do not modify `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Do not weaken validators.
- Do not use `ragflow-deepwiki.md` as citeable evidence.
- Do not chase line count with filler.
- Do not run Vertex/Gemini/API/live models without explicit approval.
- Do not perform another live/billed retry until the user explicitly approves a new
  retry against the stricter Phase 2 obligation gate.

## Acceptance commands

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
uv run python -m pytest -q tests/test_phase2_enhancement_gate.py tests/test_phase2_coverage_planning.py tests/test_phase3_evidenced_coverage.py
uv run python -m pytest -q tests/test_phase4_generated_coverage.py tests/test_phase4.py
uv run python -m pytest -q
```
