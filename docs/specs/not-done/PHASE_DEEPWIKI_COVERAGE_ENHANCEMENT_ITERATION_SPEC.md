# DeepWiki-Informed Coverage Enhancement Iteration Spec

## Status and source of truth

Status: **Milestone 1 implemented. Milestone 2 is in progress: coverage
taxonomy/validation, Phase 2 planning/PagePlan obligation preservation, Phase 1
deterministic coverage-signal expansion, the Phase 2 enhancement-mode
planned-coverage upstream-prevention gate (deterministic `normalize-plan --coverage-mode
enhancement` boundary plus coverage-signal-aware planner prompts), the Phase 3
evidenced-coverage gate (deterministic `retrieve-evidence --coverage-mode enhancement`
boundary mapping required topics through `topic_evidence_requirements[]` to exact
source-field evidence IDs), and the Phase 4 enhancement-mode hierarchical writing +
generated-coverage gate (`write-wiki --coverage-mode enhancement`: pre-provider
planned/evidenced upstream gates, hierarchy-preserving prompts/index/metadata,
WritingPackets carrying Phase 3 mapped evidence IDs, and deterministic
`generated_required_topics_covered` validation) are implemented and tested non-live.
Pending next: non-live hierarchical E2E and benchmark-only comparison before any
approved live retry**.

This is the single canonical iteration spec for the DeepWiki-informed coverage
enhancement track. It consolidates the immediate malformed-citation validator
patch and the broader coverage enhancement into one plan so coding agents have
one source of truth.

The framing is **coverage enhancement**, not parody, not copying the reference,
and not blind line-count parity. The reference DeepWiki export is a benchmark for
coverage and structure gaps only; it is not citeable evidence for generated repo
claims.

Source artifacts:

- Successful live Phase 4 run:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730`
- Generated wiki root:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki`
- Generated wiki index:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki/index.md`
- Comparison report:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/COMPARISON_WITH_RAGFLOW_DEEPWIKI.md`
- Reference benchmark, not citeable evidence:
  `/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md`
- Read-only for this iteration:
  `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`

## Plain-language root cause

The live run proved that the current pipeline can produce a valid, grounded
baseline wiki. It did **not** prove that the output is broad enough to be a
DeepWiki-informed repository guide.

The scale gap is this:

- generated wiki sections: roughly **749 lines across 16 sections**;
- reference DeepWiki export: roughly **14,717 lines**.

That does not mean we generated 14,000 lines and still missed content. It means
we generated a compact baseline while expecting a much richer guide.

Blame allocation:

- **Main cause: pipeline/spec/planning/evidence scope.** Phase 1 did not expose
  enough planner-facing topic signals, Phase 2 planned 16 broad sections, Phase 3
  retrieved evidence for those broad sections, and Phase 4 wrote within those
  constraints.
- **LLM local defects:** the model can over-compress and did emit a malformed
  citation token, `[ev:data-models:010]`.
- **Validator defect:** validation missed that malformed `ev:` token because it
  recognized valid-looking citations but did not reject malformed evidence-like
  tokens.

The next iteration must fix both the immediate validation gap and the broader
coverage target. It must not chase length with filler.

## Target artifact

The target artifact is a **DeepWiki-informed, citation-grounded repository guide**
for RAGFlow.

It should be broader and more useful than the current compact 16-section wiki by
covering the repository's major product, architecture, subsystem, developer, and
operator topics with a planned hierarchy and manifest-resolving evidence
citations.

Line count is a warning signal, not the objective. The objective is topic
coverage, hierarchy, implementation usefulness, and grounding quality.

## Quality bar

A successful enhanced wiki must:

- cover the major topic families surfaced by repository evidence and the
  reference benchmark;
- use a hierarchy of pages or child sections where topics need depth, instead of
  hiding everything in 16 broad summaries;
- explain implementation details, runtime flows, APIs, storage, operations, and
  developer surfaces when evidence supports them;
- include a planned-topic taxonomy and coverage matrix showing planned,
  evidenced, and generated status;
- attach repo-specific claims to exact EvidencePacket citations;
- reject malformed evidence-like tokens such as `[ev:data-models:010]`;
- fail closed on missing evidence, unsupported identifiers, context-artifact
  citations, placeholders, truncation, malformed citations, or under-planned
  mandatory topics;
- treat `ragflow-deepwiki.md` only as a benchmark, not as source evidence.

## Coverage sufficiency model

The pipeline answers “is this enough?” in three explicit layers. No single phase is
allowed to imply final sufficiency by itself.

1. **Planned coverage — Phase 2.** The normalized plan must include the required
   topic families, stable pages/child pages, `coverage_labels[]`, and
   `required_topics[]`. This prevents a compact 16-section plan from silently
   skipping important areas. It is necessary but not sufficient: it does not prove
   evidence exists and does not prove the final wiki covered the topic.
2. **Evidenced coverage — Phase 3.** Retrieval must map citeable EvidencePacket
   items to each planned page and required topic. This is the next missing layer.
   It should answer, for every planned topic: `sufficient`, `weak`, or `missing`,
   with exact citeable evidence IDs/handles and remediation. In enhancement mode,
   required topics must be `sufficient` before Phase 4 may run. `weak` or
   `missing` required-topic evidence is a **pipeline failure before Phase 4**, not
   something to heal, synthesize, auto-retry-until-green, or pass to the writer as
   if supported. Context artifacts, `derived/`, `plans/`, generated wiki files,
   and `ragflow-deepwiki.md` remain non-citeable.
3. **Generated coverage — Phase 4.** The writer must actually explain the planned
   and evidenced topics in the generated page, with valid citations and without
   unsupported identifiers, malformed citations, placeholders, or filler.

The intelligence comes from LLM planning and writing constrained by deterministic
artifact contracts and gates. Phase 1 supplies deterministic repo signals, Phase 2
uses LLM judgment to plan coverage, Phase 3 deterministically validates evidence
sufficiency and fails closed on weak/missing required evidence, and Phase 4 uses
LLM synthesis under strict validation. The benchmark comparison against
`ragflow-deepwiki.md` is a warning system for coverage/structure gaps, never
citeable evidence and never the sole quality bar.

## Phase 3 Evidence Sufficiency Contract — implemented non-live slice

This slice must make Phase 3 answer a narrow, deterministic question:

```text
For each planned required topic, did retrieval produce enough citeable repo
evidence to let Phase 4 write that topic?
```

It must **not** make evidence exist. It validates and reports evidence sufficiency.
In enhancement mode, weak or missing required evidence is a blocking pipeline
failure before Phase 4.

### Artifact being designed

Phase 3 should add evidenced-coverage artifacts alongside the existing evidence
packet set:

- `evidence/evidenced-coverage.json` — machine-readable per-section/per-topic
  status matrix;
- `evidence/evidenced-coverage-report.md` — human-readable summary and
  remediation;
- `evidence/retrieval-validation.json` — should include a named contract check
  such as `required_topic_evidence_sufficient`;
- `evidence/evidence-manifest.json` — should reference the new artifacts if they
  are written.

These artifacts must be deterministic and timestamp-free like the existing Phase 3
outputs.

### Deterministic topic-to-evidence mapping

Do not solve topic coverage with fuzzy prose matching. The contract should be
based on explicit planned evidence obligations.

The preferred normalized SectionPlan field is additive and optional in baseline
mode:

```json
"topic_evidence_requirements": [
  {
    "topic": "Redis Streams lifecycle",
    "required": true,
    "source_fields": ["retrieval_needs.files[0]", "retrieval_needs.symbols[1]"],
    "min_items": 1,
    "acceptable_lanes": ["file_anchor", "symbol_anchor", "contract", "test", "query_pack"]
  }
]
```

Rules:

- This is plain structured JSON, not a DSL.
- Phase 2 normalization should preserve `topic_evidence_requirements[]` when the
  planner or a fixture provides it, and planner prompt surfaces should ask for it
  in enhancement mode.
- `source_fields[]` must reference real normalized `retrieval_needs.*` entries.
  It is a deterministic bridge from a required topic to exact retrieval requests.
- Evidence is mapped through existing Phase 3 exact-request coverage records and
  final `evidence_id`s, not by comparing generated prose.
- Broad recall (`bm25`, `vector`, `graph_neighbors`, search hints without exact
  source fields) may be reported as supporting context but must not by itself make
  a required topic `sufficient` in enhancement mode.
- If a section has `required_topics[]` but lacks deterministic topic evidence
  requirements, enhancement mode should fail with remediation to fix the Phase 2
  plan/prompt/schema upstream. Do not guess that all section evidence supports all
  topics.

### Status definitions

For each required topic:

- `sufficient` — the topic has at least `min_items` citeable evidence IDs mapped
  from covered exact source fields on acceptable lanes, and those evidence items
  pass the existing anchor/context/plan-only validation.
- `weak` — some related evidence exists but it is below threshold, only broad
  recall, low-confidence/non-exact, unmapped to explicit source fields, or
  otherwise not enough to safely write the required topic.
- `missing` — no citeable evidence maps to the topic, no valid source fields are
  present, or the section lacks topic evidence requirements in enhancement mode.
- `not_applicable` — permitted only for explicitly non-source sections such as
  `section_role: provenance` / meta sections that are already handled outside the
  normal evidence lanes.

In enhancement mode, every required topic in a normal source-evidence section must
be `sufficient`. Any `weak` or `missing` required topic is exit-code `3` using the
existing `bad_underspecified_normalized_plan` category, with a diagnostic code
such as `required_topic_evidence_weak` or `required_topic_evidence_missing`.

### Failure policy: no healing

This gate is upstream prevention by failure, not a healing loop:

- no generic retry-until-green;
- no product `--section` rescue/debug mode;
- no `--force` after readiness failure;
- no synthetic evidence;
- no silent downgrade from required to optional;
- no automatic mutation of the plan to attach convenient sources;
- no use of `derived/`, `plans/`, generated wiki files, or
  `ragflow-deepwiki.md` as citeable evidence;
- no validator weakening.

If the gate fails, the correct remediation is to fix the upstream deterministic or
LLM-authored producer: improve Phase 2 topic/source obligations, improve retrieval
lanes/indexing/source mapping, or explicitly accept a human-reviewed known gap.
Phase 4 must not run in enhancement mode while required evidence is weak or
missing.

### CLI and mode behavior

The implementation should add an opt-in Phase 3 gate, for example:

```text
wiki-generator retrieve-evidence --bundle <bundle> --coverage-mode enhancement
```

Expected behavior:

- default `baseline` mode remains backward-compatible and non-breaking;
- baseline mode may write evidenced-coverage reports when enough metadata exists,
  but it must not fail legacy compact fixtures only because topic-level
  obligations are absent;
- `enhancement` mode fails before Phase 4 on weak/missing required-topic evidence;
- the command remains all-sections only; do not add product `--section` or retry
  loops.

## Phase 4 Generated Coverage Contract — implemented non-live slice

This slice must make Phase 4 answer the final coverage question:

```text
For each planned and evidenced required topic, did the generated wiki actually
cover it with valid citations, while preserving the planned hierarchy?
```

The target artifact is a **hierarchical, citation-grounded generated wiki** plus
machine-readable generated-coverage metadata. The quality bar is not line count;
it is that every planned/evidenced required topic is represented in generated
output, backed by valid EvidencePacket citations, and independently validated.

### Artifact being designed

Phase 4 should extend the existing wiki output set with generated-coverage
artifacts:

- hierarchical `wiki/index.md` navigation derived from `parent_section_id`, while
  still generating one page for every planned `section_id`;
- `wiki/metadata/generated-sections.jsonl` rows augmented with `parent_section_id`,
  `coverage_labels[]`, `required_topics[]`, evidenced topic status, and generated
  topic status;
- `wiki/metadata/generated-document.json` including generated-coverage artifact
  paths and enhancement-mode status;
- `wiki/metadata/generated-coverage.json` — machine-readable planned/evidenced
  vs generated topic matrix;
- `wiki/validation/generated-coverage-report.md` — human-readable coverage report;
- `wiki/validation/writing-validation.json` with a named check such as
  `generated_required_topics_covered`.

These artifacts must be deterministic and timestamp-free. They must not modify
historical generated wiki runs in place.

### Enhancement-mode upstream gates before provider calls

Phase 4 should gain an opt-in mode, for example:

```text
wiki-generator write-wiki --bundle <bundle> --provider fake-or-gem --coverage-mode enhancement
```

Expected behavior:

- default `baseline` mode remains backward-compatible and non-breaking for compact
  fixtures;
- enhancement mode fails before any provider/model call unless Phase 2 planned
  coverage passed and Phase 3 evidenced coverage passed;
- Phase 2 planned coverage should be established from `plans/coverage-gate.json`
  written by `normalize-plan --coverage-mode enhancement` (or an equivalent
  existing deterministic gate artifact if the implementation already provides one);
- Phase 3 evidenced coverage should be established from
  `evidence/evidenced-coverage.json` and/or the
  `required_topic_evidence_sufficient` retrieval-validation contract check;
- if either upstream gate is absent, baseline/report-only, stale, or failed,
  enhancement-mode Phase 4 exits as an upstream gate failure (`3`) with remediation
  to rerun/fix the owning upstream phase. It must not rerun Phase 2 or Phase 3,
  repair plans, retrieve evidence, or synthesize evidence.

### Deterministic generated-topic coverage validation

Do not validate generated topic coverage with vague line-count, section-count, or
fuzzy prose similarity.

The preferred deterministic contract is:

1. The WritingPacket includes each section's hierarchy fields and the Phase 3
   evidenced topic rows for that section. For each `sufficient` required topic,
   the packet tells the writer which exact `evidence_id`s support that topic.
2. The section response schema is extended in a backward-compatible way to include
   a structured topic coverage declaration, for example:

   ```json
   "covered_topics": [
     {
       "topic": "Redis Streams lifecycle",
       "status": "covered",
       "evidence_ids": ["ev:task-queues:0002"],
       "markdown_anchor": "redis-streams-lifecycle"
     }
   ]
   ```

3. Final validation checks this declaration deterministically:
   - every planned/evidenced `sufficient` required topic has a generated coverage
     row with status `covered`;
   - every listed `evidence_id` is in the Phase 3 evidenced topic's mapped IDs or
     the section's allowed evidence IDs, resolves through the citation manifest,
     and is actually cited in the generated markdown;
   - the generated markdown contains the topic text or declared markdown anchor in
     a non-empty paragraph/list item/heading with valid citations;
   - no generated coverage row may rely on context artifacts, `derived/`, `plans/`,
     generated wiki files, or `ragflow-deepwiki.md`;
   - omitted topics, empty placeholders, malformed citations, unsupported
     identifiers, and context-artifact citations fail final validation.

This validation can check the writer's structured declaration and citation usage;
it should not attempt semantic fuzzy matching against the benchmark DeepWiki.

### Hierarchical writing behavior

Phase 4 must treat parent/child section metadata as first-class:

- prompts should include `parent_section_id`, sibling/child context, coverage
  labels, required topics, and evidenced topic rows;
- `index.md` should render nested contents rather than a flat-only numbered list;
- metadata should preserve parent/child relationships for every generated page;
- broad parent pages alone must not be counted as generated coverage for child
  families or child required topics;
- baseline fixtures may keep existing flat behavior unless enhancement mode is
  explicitly requested.

Filesystem layout may remain backward-compatible (`sections/NNN-section-id.md`) if
metadata and navigation preserve hierarchy. Do not force a path migration unless it
is necessary and covered by tests.

### Failure policy: no healing

Generated coverage failures are not repair targets for deterministic code:

- no generic retry-until-green loop;
- no synthetic filler or topic stubs to satisfy coverage;
- no automatic mutation of `covered_topics[]` after the model returns;
- no downgrading required topics to optional;
- no weakening citation, malformed-token, unsupported-identifier, placeholder,
  truncation, no-context, or no-`--force` validators.

A bounded LLM rewrite may remain only for the existing narrow format/citation
failure categories already covered by strict validation. It must not add evidence,
change topic obligations, or paper over missing generated coverage.

### Non-live implementation boundary

This slice must be proven with fake-provider or deterministic non-live fixtures.
Do not call Vertex, Gemini API, Gemini Gem live/manual production flows, or any
billed model. Do not run a live retry after this slice; the next step is non-live
hierarchical E2E.

## Non-live Hierarchical E2E and Benchmark-Only Comparison Contract — next implementation slice

This slice must prove the enhancement pipeline as a whole, not merely isolated
unit fixtures:

```text
expanded hierarchical plan -> planned coverage gate -> evidenced coverage gate
-> generated coverage gate -> benchmark-only coverage/structure review
```

The target artifact is a **fresh, non-live hierarchical E2E run directory** plus a
human-readable result report. It should demonstrate that the enhanced gates can
work together over an expanded multi-family plan before any billed/live retry is
requested.

### Artifact being designed

Create a fresh run under a non-live workspace such as:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/non-live-hierarchical-runs/<timestamp-or-run-id>/
```

The run should contain, at minimum:

- `command-manifest.tsv` with exact commands and exit codes;
- `command-transcript.log` with stdout/stderr snippets sufficient for review;
- an expanded hierarchical bundle or fixture plan covering multiple mandatory
  topic families, with `parent_section_id`, `coverage_labels[]`,
  `required_topics[]`, and `topic_evidence_requirements[]` preserved;
- `plans/coverage-gate.json` + `plans/coverage-gate-report.md` from the real
  planned-coverage gate where possible;
- `evidence/evidenced-coverage.json` + report from
  `retrieve-evidence --coverage-mode enhancement`;
- `wiki/metadata/generated-coverage.json` +
  `wiki/validation/generated-coverage-report.md` from
  `write-wiki --coverage-mode enhancement`;
- a nested `wiki/index.md` and generated-section/document metadata preserving
  hierarchy;
- `NON_LIVE_HIERARCHICAL_E2E_RESULT.md` summarizing verdict, commands, gate
  statuses, coverage counts, known gaps, and whether any live retry is justified;
- a benchmark-only comparison note/report against `ragflow-deepwiki.md` that
  discusses coverage/structure gaps without citing it as evidence.

Generated bulky run artifacts should not be committed unless they are small,
intentional, and already consistent with repository tracking policy. The durable
implementation backlog and final status must be mirrored in this spec/handoff and
`docs/README.md`.

### Required command/path behavior

The E2E task must use the real CLI/script surfaces that a future operator would
use. If a wrapper is missing an implemented flag, fix the wrapper upstream rather
than bypassing it silently. In particular, verify and, if necessary, update:

- `scripts/phase2_step2_normalize_plan.sh` supports/passes
  `--coverage-mode enhancement` to `normalize-plan`;
- `scripts/phase3_retrieve_evidence.sh` supports/passes
  `--coverage-mode enhancement` to `retrieve-evidence`;
- `scripts/phase4_write_wiki.sh` supports/passes
  `--coverage-mode enhancement` to `write-wiki`.

A wrapper gap is a deterministic upstream defect. Fix the script/help/tests and
rerun from the affected phase; do not hand-edit downstream artifacts to compensate.

### Non-live provider boundary

Do not call Vertex, Gemini API, Gemini Gem live/manual production flows, or any
billed model for this slice.

Acceptable approaches:

- deterministic fixture or synthetic mini-repo that exercises multiple mandatory
  topic families and hierarchy;
- a fake provider injected through Python-level Phase 4 wiring;
- gemini-gem prepare/validate mode only if no model is called and responses are
  deterministic fixtures.

If the current shell wrapper cannot inject a fake provider, the agent may add a
small non-live harness or test-oriented script, but it must keep production CLI
behavior honest and documented.

### Gate behavior to prove

The run/report must prove:

- planned coverage passes in enhancement mode for an expanded multi-family plan;
- a compact/broad-parent-only plan would still fail where required by existing
  tests (do not weaken the gate to make the E2E pass);
- evidenced coverage passes with exact mapped `evidence_id`s for required topics;
- Phase 4 refuses to start in enhancement mode if upstream planned/evidenced gates
  are missing/baseline/failed;
- generated coverage passes only when each evidenced sufficient required topic is
  actually covered and locally cited;
- generated coverage artifacts are deterministic on rerun for the same inputs;
- all existing citation, malformed evidence token, unsupported identifier,
  context-artifact, placeholder, truncation, stale/no-`--force`, and coverage
  validators remain strict.

### Benchmark-only comparison

Compare the non-live generated hierarchy/coverage matrix against:

```text
/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md
```

Rules:

- benchmark-only; never citeable evidence;
- no copying sections, headings, prose, or claims into generated output;
- no line-count parity target;
- report coverage/structure gaps by topic family and planned/evidenced/generated
  status;
- explicitly state whether the non-live E2E is enough to request user approval for
  a live/billed retry. The default should remain **no live retry** unless all gates
  pass cleanly and the user explicitly approves.

### Failure policy: fix upstream, not heal

- Deterministic wrapper/validator/artifact defects must be fixed upstream and
  tested.
- Weak/missing planned or evidenced required-topic coverage remains a pipeline
  failure before Phase 4 in enhancement mode.
- Missing generated coverage remains a Phase 4 writing-validation failure after
  provider/fake-provider output.
- Do not add retry-until-green, synthetic evidence, filler topics, silent
  required-to-optional downgrades, benchmark-derived evidence, or validator
  weakening.
- If the fake provider or fixture is insufficient, improve the fixture/harness or
  prompt contract; do not mutate generated coverage declarations post hoc.

### Next-slice acceptance — non-live hierarchical E2E

Accept the next slice only when the agent reports and/or commits evidence that:

- all three enhancement gates were exercised together in one fresh non-live run;
- wrapper help/behavior exposes the enhancement flags needed to reproduce the run;
- run artifacts and `NON_LIVE_HIERARCHICAL_E2E_RESULT.md` exist in the non-live
  workspace;
- the benchmark-only comparison exists and does not treat `ragflow-deepwiki.md` as
  evidence;
- relevant focused tests and the full suite pass via `uv run python -m pytest -q`;
- protected Phase 3 spec content is unchanged;
- no live/billed provider was called;
- docs/handoff/status are updated with verdict, run path, risks, and remaining
  live-retry approval status.

## Milestone 1 — immediate writing-validation enhancement

This milestone is implemented locally and tested. It was the first implementation
target because it is small, non-live, and required before any further strict
sign-off claim.

### Problem

The generated live wiki contains this malformed evidence-like token:

```text
[ev:data-models:010]
```

Affected generated artifact:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki/sections/010-data-models.md
```

The canonical citation format uses four-digit ordinals:

```text
[ev:<section_id>:<NNNN>]
```

The malformed token escaped validation. That is unacceptable for strict sign-off.

### Required behavior

1. The only valid citation syntax remains `[ev:<section_id>:<NNNN>]`, with the
   section-id grammar matching existing code and the ordinal exactly four digits.
2. Valid-looking citations must still resolve through
   `wiki/metadata/citation-manifest.json`.
3. Any bracketed evidence-like token beginning with `[ev:` that does not match
   canonical syntax must fail validation loudly.
4. Dangling `[ev:` sequences must fail validation loudly.
5. During bounded section drafting, malformed evidence-token failures are
   **rewriteable**: the rewrite prompt may ask the model to replace the malformed
   token with an exact manifest citation or remove the unsupported claim.
6. In final validation, any remaining malformed evidence-token failure is
   terminal: the artifact must not be silently edited or auto-corrected.
7. Diagnostics must include token text, section id, section file/path when
   available, line/column when available, failure category, and remediation.
8. Suggested nearby IDs may be shown only when deterministic and safe. Example:
   suggest `[ev:data-models:0010]` for `[ev:data-models:010]` only if that exact
   manifest ID exists and the difference is simple zero-padding.
9. Existing validators must not be weakened: unsupported identifiers, manifest
   resolution, unused citations, context-artifact citations, placeholders, and
   truncation checks remain strict.

### Malformed examples that must fail

- `[ev:data-models:010]` — three-digit ordinal.
- `[ev:data-models:00010]` — five-digit ordinal.
- `[ev:data-models:]` — missing ordinal.
- `[ev:data-models]` — missing ordinal separator.
- `[ev:data models:0010]` — invalid section-id characters if spaces are outside
  the existing grammar.
- `[ev:data-models:0010` — dangling opener / missing close.
- `[ev:data-models:0010 extra]` — extra text.
- `[ev:data-models:0010:extra]` — extra field.

### Likely implementation targets

- `src/wiki_generator/libs/writing/citations.py`
- `src/wiki_generator/libs/writing/validate.py`
- Phase 4 bounded rewrite feedback/prompt plumbing
- `tests/test_phase4.py`

### Tests required

Unit tests:

- `[ev:data-models:010]` fails as malformed.
- `[ev:data-models:0010]` can pass when the manifest contains that exact ID.
- Well-formed but unknown citations still fail manifest resolution.
- Existing valid citations continue to pass.
- The malformed examples above all fail with useful diagnostics.

Fake-provider integration tests:

1. First draft contains a malformed citation.
2. Draft validation detects it.
3. Bounded rewrite receives clear feedback.
4. Fake provider returns a corrected section using a valid manifest citation.
5. Final validation passes.

Also test the failure path where rewrite leaves the malformed token and final
validation fails.

### Milestone 1 acceptance commands

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
uv run python -m pytest -q tests/test_phase4.py
uv run python -m pytest -q
```

No Vertex/Gemini/API calls are allowed for Milestone 1.

## Milestone 2 — DeepWiki-informed coverage enhancement

This is the broader enhancement track. It should not start by increasing token
limits. It starts by changing the artifact target, planning, evidence, and
coverage validation.

### Required topic families

The enhanced guide must plan for and cover, when repository evidence supports it:

1. Frontend/i18n/UI architecture — frontend structure, routing, state management,
   internationalization, component architecture, theming, and build/runtime
   integration.
2. Memory system — memory APIs, internals, storage, use in agent workflows, and
   raw/semantic/episodic/procedural concepts where supported.
3. Task queues and Redis Streams — queue names, task lifecycle, workers,
   cancellation, retries, parsing/indexing jobs, RAPTOR/GraphRAG/memory queues,
   and operations.
4. Kubernetes/Helm — charts, values, manifests, services/deployments, ingress,
   config, secrets, and deployment workflow.
5. CI/CD/build system — package managers, Docker build flow, dependency
   pre-caching, GitHub workflows, release scripts, image build/publish behavior,
   and developer commands.
6. Go/native components — Go server/admin/native pieces, build modes,
   parser/lexer/native services, and Python integration points.
7. Retrieval/search internals — document store abstraction, index selection,
   query transformation, hybrid search, reranking, filters, pruning, response
   generation, and citation insertion.
8. Document parsing/OCR/layout/chunking — parser factories, DeepDoc, MinerU,
   OCR/layout operators, chunking strategies, content enhancement, embedding,
   connectors, and upload-to-index pipeline stages.
9. LLM provider internals/tool calling/retry/usage — LLMBundle, model
   registration, providers, error classes, retry/backoff, usage tracking, tenant
   configuration, tool/function schemas, and tool-call execution.
10. User/tenant/admin/system health — user and tenant management, admin
    routes/services, auth/authorization, status probes, health endpoints,
    settings, and operational dashboards/commands.
11. Sandbox/code executor — sandbox manager, provider registry, configuration,
    security boundaries, code execution tool, and admin/operator controls.
12. Migrations/operations — database migrations/schema sync, ES-to-OceanBase
    migration, utility scripts, reset/admin commands, runbooks, and upgrade paths.
13. Glossary — repo-specific terminology, acronyms, component names, service
    names, queue names, data-store terms, and concepts used throughout the guide.

Additional desirable expansions:

- document engine selection and tradeoffs;
- dynamic component loading;
- API SDK architecture and request validation utilities;
- endpoint coverage tables for public API groups;
- diagrams or Mermaid summaries only when evidence supports the flow and
  relationships.

### Pipeline changes required

1. **Phase 1 repo analysis expansion**
   - Add deterministic inventories for apps/packages, docs, frontend, deployment,
     CI/CD, queue/task signals, memory, Go/native, API routes/SDK/auth/admin/
     health, LLM providers, migrations, sandbox, CLI/admin utilities, and tests.
   - Rank candidate subsystems and report low-signal areas before planning.

2. **Phase 2 hierarchical planning**
   - Produce a planned topic taxonomy with parent pages, child pages, stable IDs,
     required topics, optional topics, source-category obligations, cross-links,
     and a coverage matrix.
   - Prevent mandatory-family omissions through better prompt/context/schema and
     deterministic gating; if the LLM-authored plan still misses mandatory
     families in coverage-enhanced mode, allow only bounded audited LLM re-prompt
     with exact diagnostics and loud failure after the cap. Do not add generic
     healing loops around deterministic normalization or validation.

3. **PagePlan obligations**
   - Each page/child section must state required topic bullets, expected source
     handles/files/routes/docs/tests/contracts, evidence expectations, intended
     depth, cross-link targets, and coverage labels such as `frontend`,
     `queue-system`, `helm-k8s`, `memory`, `llm-provider`,
     `retrieval-internals`, and `operations`.
   - A broad parent page must not count as coverage for a child topic unless that
     child topic has its own evidence and generated content.

4. **Phase 3 page-level evidence retrieval**
   - Retrieve evidence per planned page/child section while preserving existing
     constraints: deterministic and LLM-free retrieval, one product run for all
     planned pages, no product `--section` retry loop, no `--force` after
     readiness failure, no context/generated/reference files as citeable evidence,
     and fail-closed missing-evidence behavior.
   - Evidence validation should report per-page and per-required-topic
     sufficiency.

5. **Phase 4 hierarchical writing**
   - Generate per planned page/child section.
   - Support longer page budgets only when evidence density justifies them.
   - Preserve citation, unsupported-identifier, malformed-token,
     no-context-citation, no-placeholder, no-truncation, and no-synthesis
     validators.
   - Emit metadata for planned-vs-generated coverage.

6. **Coverage validation and benchmark comparison**
   - Validate required topic taxonomy vs planned pages.
   - Validate planned pages vs evidence packets.
   - Validate planned required topics vs generated headings/prose markers.
   - Validate all citations, including malformed evidence-like token detection.
   - Compare generated coverage against `ragflow-deepwiki.md` as benchmark-only.
   - Report remaining gaps with planned/evidenced/generated status.

### Milestone 2 progress — coverage-validation slice (implemented, non-live)

This slice implements the safest, testable, non-live foundation of Milestone 2:
the planned-topic taxonomy and the deterministic coverage validator. It does NOT
yet expand Phase 1 signals, Phase 2 hierarchical planning, Phase 3 page-level
retrieval, or Phase 4 hierarchical writing — those remain pending.

Implemented:

- `src/wiki_generator/libs/coverage/taxonomy.py` — `TopicFamily` plus the thirteen
  mandatory topic families (frontend, memory, queue-system, helm-k8s, ci-cd-build,
  go-native, retrieval-internals, doc-processing, llm-internals,
  user-tenant-admin-health, sandbox-executor, migrations-operations, glossary),
  each with explicit coverage-label aliases and distinctive keyword signals.
- `src/wiki_generator/libs/coverage/validate.py` — `evaluate_plan_coverage(...)`
  returning a `CoverageReport` (per-family `FamilyCoverage` matrix, missing
  mandatory families, actionable diagnostics), a markdown renderer, and a plan
  loader. `enhancement` mode fails closed on a missing mandatory family;
  `baseline` mode reports coverage without enforcing.
- `src/wiki_generator/libs/commands/validate_coverage.py` + the `validate-coverage`
  CLI subcommand — loads a bundle's normalized Phase 2 plan, writes
  `coverage/coverage-validation.json` + `coverage-validation-report.md`, and exits
  `0` (pass / baseline), `2` (no normalized plan), or `3` (planned-coverage enhancement gate fail).
- `tests/test_coverage_validation.py` — proves a faithful compact 16-section
  baseline fails enhancement-mode coverage (passes report-only baseline mode); an
  expanded plan with all families passes; dropping frontend/memory/queue fails with
  exactly those diagnostics; a broad parent page does not satisfy a deep child
  family; substring false matches are avoided; the CLI gate works; and Milestone 1
  malformed-token validation is intact.

Detection discipline: a broad parent page (one "Core RAG Pipeline" section whose
only topic is the word "retrieval") does NOT count as coverage for a deep child
family; the child must declare the family's coverage label or carry the family's
distinctive vocabulary. The "evidenced" and "generated" coverage dimensions
(per-page EvidencePacket sufficiency, per-required-topic generated-heading checks)
are explicit next steps and are not asserted by this slice. The validator is NOT
wired into the default Phase 4 path (that would fail the small fixture bundles);
it is exposed as the standalone `validate-coverage` command/library scaffold.

### Milestone 2 progress — Phase 2 planning/PagePlan obligations (implemented, non-live)

This slice made the normalized Phase 2 plan capable of carrying coverage-enhanced
planning obligations end-to-end, without making coverage enforcement part of the
default Phase 4 path.

Implemented:

- `coverage_labels[]` are preserved in normalized `section-plans.jsonl` and
  normalized to canonical kebab labels.
- `parent_section_id` is preserved/resolved so parent/child page hierarchy can be
  represented in the canonical plan artifact.
- `required_topics` merges planner `coverage_requirements[]` and
  `required_topics[]` so PagePlan obligations survive normalization.
- `expected_sources[]` is preserved as planner expectation metadata.
- `document-plan.md` shows coverage labels and parent/child hierarchy.
- `normalization-report.md` includes a baseline/report-only DeepWiki coverage
  matrix; it does not gate readiness unless `validate-coverage --mode
  enhancement` is explicitly run.
- Planner prompt surfaces ask for canonical `coverage_labels[]`,
  `parent_section_id`, and the rule that a broad parent page does not satisfy a
  deep child topic.
- `tests/test_phase2_coverage_planning.py` proves field preservation,
  hierarchy, normalized-plan coverage validation, non-enforcing reports, prompt
  guidance, and Milestone 1 behavior remain intact.

### Milestone 2 progress — Phase 1 coverage-signal expansion (implemented, non-live)

This slice gives Phase 2 deterministic planner-facing coverage signals for all
thirteen mandatory topic families. These signals are planner context, not citeable
Phase 3 evidence.

Implemented:

- `src/wiki_generator/libs/coverage/signals.py` derives per-family coverage
  signals from deterministic source artifacts such as file inventory, query-pack
  hits, and symbols.
- `src/wiki_generator/libs/digest/planning_coverage_signals.py` renders the
  planner-facing condensate.
- Phase 1 condense/digest emits `derived/planning-coverage-signals.md` and the
  machine-readable `derived/coverage-signals.json` sidecar.
- The planner upload bundle includes `planning-coverage-signals.md` with an
  explicit warning that it is context-only and not citeable evidence.
- Missing or low-signal families are reported rather than hidden. Glossary is
  synthesized as a planner obligation, not as a source-backed citation target.
- `tests/test_coverage_signals.py` proves deterministic family detection,
  missing/low-signal reporting, non-citeable markdown/JSON metadata, and upload
  integration.

### Milestone 2 progress — Phase 2 enhancement-mode planned-coverage upstream-prevention gate (implemented, non-live)

This slice adds the deterministic Phase 2 → Phase 3 planned-coverage boundary and
makes the planner prompt/context explicitly consume the Phase 1 coverage signals.
It is upstream prevention by **loud deterministic failure**, not a healing loop:
the gate never synthesizes, adds, or repairs pages/labels/source obligations.

Implemented:

- `src/wiki_generator/libs/coverage/validate.py` adds a shared deterministic gate:
  `gate_plan_coverage(...)` → `CoverageGate` (verdict + exit code + actionable
  `summary_lines()`), plus `load_plan_from_dir(...)`; exit codes
  `COVERAGE_GATE_PASS_EXIT=0` / `COVERAGE_GATE_INPUT_EXIT=2` /
  `COVERAGE_GATE_FAIL_EXIT=3`.
- `normalize-plan` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). `baseline` keeps the existing non-enforcing matrix in
  `normalization-report.md` and never gates the command. `enhancement` runs the
  deterministic gate over the just-written normalized plan, writes
  `plans/coverage-gate.json` + `plans/coverage-gate-report.md`, logs diagnostics
  naming missing families + remediation, and exits `3` before Phase 3 retrieval.
- The standalone `validate-coverage` command now shares the same `gate_plan_coverage`
  (identical enforcement). No generic healing loop is added; bounded LLM re-prompt
  remains the existing, separately-audited `plan-repair` step (prompt/context/schema
  improved first).
- Planner prompt surfaces (`gemini-gem/GEM_INSTRUCTIONS.md`,
  `gemini-gem/KICKOFF_PROMPT.md`, `plan._DEFAULT_SYSTEM`, `plan._DEFAULT_KICKOFF`;
  the upload README already did) now explicitly cite `planning-coverage-signals.md`
  as planner CONTEXT, not citeable evidence, and warn that a coverage-enhanced run
  gates the plan against all thirteen families before Phase 3.
- `coverage_labels[]`, `parent_section_id`, merged `required_topics[]`, and
  `expected_sources[]` continue to survive normalization end-to-end.
- `tests/test_phase2_enhancement_gate.py` proves: full expanded plan passes (exit 0);
  missing frontend/memory/queue fails (exit 3) with exactly those diagnostics; a
  broad parent page alone does not satisfy a deep child family; baseline default is
  non-breaking (and an arg namespace without `coverage_mode` defaults to baseline);
  the gate does not synthesize/heal the plan; planner surfaces cite the coverage
  signals as context-only; Milestone 1 malformed-token validation remains intact.

The gate is **not** wired into the default Phase 4 path (that would fail the compact
fixture bundles); it is the explicit Phase 2 enhancement boundary. Evidenced and
generated coverage dimensions remain the next pending slices.

### Milestone 2 progress — Phase 3 evidenced coverage (implemented, non-live)

This slice implements the Phase 3 Evidence Sufficiency Contract above as a
deterministic per-required-topic evidence gate (not a healing loop). It validates
and reports evidence sufficiency; it never makes evidence exist.

Implemented:

- Phase 2 normalization preserves the additive, baseline-compatible
  `topic_evidence_requirements[]` SectionPlan field. Each item normalizes to
  `{topic, required (default true), source_fields[], min_items (default 1),
  acceptable_lanes[] (default exact lanes)}`; a baseline/legacy plan that omits it
  normalizes to `[]` and is unaffected. Planner prompt surfaces
  (`GEM_INSTRUCTIONS.md`, `KICKOFF_PROMPT.md`, `plan._DEFAULT_SYSTEM`/`_DEFAULT_KICKOFF`)
  now ask for it, pointing at real `retrieval_needs.*` source fields, and warn that
  broad recall is never sufficient and over-requiring fails before Phase 4.
- `src/wiki_generator/libs/evidence/evidenced_coverage.py` —
  `evaluate_evidenced_coverage(bundle, packets, options)` reads the normalized
  hierarchical plan (`coverage_labels[]`, `parent_section_id`, `required_topics[]`,
  `topic_evidence_requirements[]`) and maps each planned required topic through its
  `source_fields[]` to the packet's `coverage.exact_requests[]` records and their
  final citeable `evidence_id`s. Statuses: `sufficient`, `weak`, `missing`,
  `not_applicable`, each with counts, evidence IDs, source categories, and
  remediation. Broad recall (`bm25`/`vector`/`graph_neighbors`/`search_hints`) is
  reported as supporting context (can yield `weak`) but never makes a required topic
  `sufficient`.
- `retrieve-evidence` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). Enhancement mode makes a `weak`/`missing` required topic in a normal
  source-evidence section a blocking pipeline failure BEFORE Phase 4: exit `3`,
  `bad_underspecified_normalized_plan`, surfaced as the
  `required_topic_evidence_sufficient` contract check in `retrieval-validation.json`
  and diagnostic codes `required_topic_evidence_weak`/`required_topic_evidence_missing`.
  Baseline mode is non-breaking (reports the matrix; adds no gate/contract check).
- Deterministic, timestamp-free artifacts `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`, referenced from `evidence-manifest.json`.
- No retrieval healing loop, no product `--section`/`--force`, no fallback rescue,
  no synthetic evidence, no silent required→optional downgrade, and no validator
  weakening. The gate is read-only and fails upstream. Context artifacts, `derived/`,
  `plans/`, generated wiki files, and `ragflow-deepwiki.md` remain non-citeable (a
  topic can only claim a real packet `evidence_id` from a covered exact request).
- `tests/test_phase3_evidenced_coverage.py` proves: an expanded fixture with
  explicit `topic_evidence_requirements[]` passes enhancement; a required topic with
  no mapped exact evidence fails before Phase 4 (exit 3,
  `bad_underspecified_normalized_plan`); a required topic supported only by broad
  recall is `weak` and blocking; baseline/default remains non-breaking; mapped IDs
  are real citeable packet IDs; normalization preservation; reruns are byte-identical;
  and the CLI exposes no `--section`/`--force`.

### Milestone 2 progress — Phase 4 hierarchical writing and generated coverage (implemented, non-live)

This slice implements the Phase 4 Generated Coverage Contract above as an opt-in
`write-wiki --coverage-mode {baseline,enhancement}` mode (default `baseline`,
fully non-breaking). It is upstream-trusting and deterministic: Phase 4 consumes the
Phase 2/3 enhancement gate artifacts and never reruns Phase 2/3, repairs plans,
retrieves evidence, or synthesizes evidence.

Implemented:

- `src/wiki_generator/libs/writing/options.py` adds `coverage_mode`
  (`baseline`/`enhancement`, validated); `src/wiki_generator/cli.py` +
  `libs/commands/write_wiki.py` add `--coverage-mode` (omitted-when-absent so an
  older arg namespace defaults to baseline).
- `src/wiki_generator/libs/writing/generated_coverage.py` — the enhancement engine:
  `read_enhancement_gates` verifies (pre-provider) that `plans/coverage-gate.json`
  is an enforced enhancement gate with `passed`/`status: pass`, that
  `evidence/evidenced-coverage.json` is `coverage_mode: enhancement` /
  `enforced: true` / `status: pass`, and that the
  `required_topic_evidence_sufficient` retrieval-validation contract check is
  present and passing; `build_topic_obligations` turns the evidenced matrix into
  per-section required-topic obligations carrying the exact Phase 3
  `mapped_evidence_ids`; `evaluate_generated_coverage` validates the writer's
  `covered_topics[]` declaration against the generated markdown (every sufficient
  required topic declared `covered`, evidence IDs within the topic's mapped set,
  resolving through the citation manifest, and cited within the topic's local
  markdown block near its text/anchor).
- `libs/writing/bundle.py` runs the enhancement gate inside `load_and_gate` as a
  sixth pre-provider gate (a missing/baseline/failed upstream gate raises
  `GateFailure`, exit 3) and attaches `evidenced_coverage` + `topic_obligations` to
  the `WritingBundle`.
- `libs/writing/packet.py` + `prompt.py` carry the planned hierarchy
  (`parent_section_id`, `coverage_labels`, child ids) and the evidenced topic rows
  (exact supporting `evidence_id`s) into each WritingPacket/prompt, and extend the
  section response contract with `covered_topics[]` (topic/status/evidence_ids/
  markdown_anchor) — backward-compatible (baseline packets/prompts are unchanged).
- `libs/writing/validate.py` carries the writer's `covered_topics[]` through
  section validation and adds the named final whole-document check
  `generated_required_topics_covered`; a failure is a writing-validation failure
  (exit 5) after provider output and is never papered over by the bounded rewrite.
- `libs/writing/assemble.py` renders a nested `index.md` from `parent_section_id`
  (flat when no hierarchy, so compact fixtures stay byte-identical), augments
  `generated-sections.jsonl` rows with hierarchy + evidenced/generated topic status,
  references the coverage artifacts + hierarchy from `generated-document.json`, and
  writes deterministic `wiki/metadata/generated-coverage.json` +
  `wiki/validation/generated-coverage-report.md`.
- All existing writing validators remain strict (citation resolution, malformed
  evidence tokens, unsupported/synthesized identifiers, context artifacts,
  placeholders, truncation, no-`--force`, stale/coherent packets). No generic
  healing loop, no synthetic filler, no required→optional downgrade, no post-hoc
  mutation of model-authored `covered_topics[]`, and `ragflow-deepwiki.md` is never
  citeable.
- `tests/test_phase4_generated_coverage.py` proves: enhancement happy path over a
  real decomposed+retrieval-built bundle writes a nested index + generated-coverage
  artifacts and passes; WritingPackets carry the exact mapped evidence IDs;
  pre-provider exit-3 gate failures for missing/baseline/failed planned gate,
  missing/baseline evidenced gate, and missing retrieval contract check (with NO
  provider call); post-provider exit-5 failures for an omitted topic, a topic
  declared without local citation, a topic cited with out-of-scope IDs, and a
  placeholder-only topic; baseline/default stays non-breaking (no gate, no
  generated-coverage artifact/check); rerun byte-identical; plus pure-evaluator
  units and CLI-surface checks (`--coverage-mode` present, no `--section`/`--force`).

### Remaining Milestone 2 work — active pending backlog

1. **Non-live hierarchical E2E.** Prove the expanded planning → evidence → writing
   path end-to-end with fake-provider or non-live fixtures (an expanded
   multi-family hierarchical plan) before requesting explicit user approval for any
   billed Vertex/Gemini retry.
2. **Benchmark-only comparison.** Compare against `ragflow-deepwiki.md` only as a
   structure/coverage benchmark, never as citeable evidence.

### Completed-slice acceptance — Phase 2 enhancement-mode planned-coverage upstream prevention

This implementation slice is accepted because it proves all of the following in
non-live tests:

- Phase 2 planning prompt/context explicitly includes and explains
  `planning-coverage-signals.md` as planner context, not citeable evidence.
- Enhancement mode has a deterministic planned-coverage gate that evaluates the normalized
  plan against all thirteen mandatory coverage families before Phase 3 retrieval. It does not claim evidence or generated-content readiness.
- A normalized plan missing mandatory families fails enhancement mode loudly with
  actionable diagnostics naming the missing families and remediation.
- Baseline mode remains non-breaking and report-only for compact or legacy plans.
- Deterministic code does **not** synthesize, silently add, or auto-heal missing
  pages, labels, or source obligations. Deterministic stages must prevent bad
  artifacts by stronger prompt contracts, schemas, normalization, validation, or
  explicit failure.
- If bounded LLM re-prompt/repair is added for the LLM-authored Phase 2 plan, it
  is narrow, audited, capped, fed exact coverage diagnostics, and followed by the
  same strict normalized-plan enhancement gate. It must not be retry-until-green.
- Planner outputs and normalized artifacts still preserve `coverage_labels[]`,
  `parent_section_id`, merged `required_topics[]`, and `expected_sources[]`.
- Tests prove: an expanded hierarchical plan with all families passes; a plan
  missing frontend/memory/queue fails enhancement mode; a broad parent page alone
  does not satisfy a deep child family; malformed citation validation from
  Milestone 1 remains intact.
- No live Vertex/Gemini/API calls, no real Phase 1/2/3/4 pipeline retry, no
  historical wiki artifact edits, no validator weakening, and no changes to
  `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.

### Completed-slice acceptance — Phase 3 evidenced coverage

This implementation slice is accepted because non-live tests prove:

- Phase 2 normalization preserves `topic_evidence_requirements[]` without making
  it mandatory in baseline mode.
- Planner prompt surfaces explain that enhancement-mode required topics need
  deterministic `topic_evidence_requirements[]` pointing at real normalized
  `retrieval_needs.*` source fields.
- Phase 3 reads the normalized hierarchical plan, including `coverage_labels[]`,
  `parent_section_id`, `required_topics[]`, and `topic_evidence_requirements[]`.
- Phase 3 writes deterministic `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`, and references them from the manifest
  or retrieval validation artifacts.
- Evidence packets or validation reports map citeable evidence IDs back to each
  planned `section_id` and required topic through exact source-field coverage, not
  fuzzy prose matching.
- Each required topic receives deterministic `sufficient`, `weak`, `missing`, or
  `not_applicable` status with counts, evidence IDs/handles, source categories,
  and remediation.
- In enhancement mode, `weak` or `missing` evidence for a required topic is a
  blocking **pipeline failure before Phase 4** using exit code `3` and
  `bad_underspecified_normalized_plan`. Baseline/legacy behavior remains
  non-breaking only where explicitly requested.
- Context artifacts, `derived/`, `plans/`, generated wiki files, and
  `ragflow-deepwiki.md` are never counted as citeable evidence.
- No generic retrieval healing loop, no product `--section` retry mode, no
  `--force` after readiness failure, no fallback rescue for no-signal sections,
  no synthetic evidence, no silent downgrade to optional, and no validator
  weakening.
- Tests include an expanded hierarchical fixture that passes evidenced coverage,
  a fixture where a required topic lacks mapped evidence and fails before Phase 4,
  a fixture where only broad recall exists and is `weak`/blocking, and a fixture
  proving baseline mode remains non-breaking.

### Completed-slice acceptance — Phase 4 hierarchical writing and generated coverage

The Phase 4 implementation slice is accepted as a non-live foundation because tests
prove:

- `write-wiki` supports opt-in `--coverage-mode enhancement`; baseline/default
  remains non-breaking.
- Enhancement-mode Phase 4 refuses to call any provider unless planned coverage
  and evidenced coverage artifacts are present, enforced, and passing.
- Phase 4 consumes hierarchical plans and page-level EvidencePackets without
  flattening child pages back into the compact 16-section baseline.
- WritingPackets and prompts include hierarchy fields plus evidenced topic rows.
- The wiki index, manifests, audit prompts/responses, generated-section metadata,
  generated-document metadata, and validation reports preserve parent/child
  structure.
- Phase 4 writes deterministic `wiki/metadata/generated-coverage.json` and
  `wiki/validation/generated-coverage-report.md`.
- Generated coverage metadata maps output pages back to planned `section_id`,
  `coverage_labels[]`, `required_topics[]`, and evidenced topic statuses.
- Generated coverage validation fails when a planned/evidenced required topic is
  omitted, only a placeholder/empty heading, declared without actual markdown
  coverage, malformed-cited, cited with IDs outside allowed/evidenced IDs, or
  supported by invalid/context/generated/reference artifacts.
- Generated coverage failures after provider output are writing-validation
  failures (`5`); missing/failed upstream enhancement gates are pre-provider gate
  failures (`3`).
- Existing writing validators remain strict; no generic healing loop, filler,
  synthetic evidence, validator weakening, live/billed calls, or use of
  `ragflow-deepwiki.md` as evidence.

### Next-slice acceptance — non-live hierarchical E2E and benchmark-only review

The next implementation/validation slice should be accepted only when non-live
artifacts prove:

- planned, evidenced, and generated coverage enhancement gates all pass together
  in one fresh hierarchical run;
- wrapper scripts expose and pass `--coverage-mode enhancement` for Phase 2
  normalization, Phase 3 retrieval, and Phase 4 writing where applicable;
- an expanded multi-family hierarchical plan exercises parent/child pages and
  multiple mandatory topic families, not just the compact two-page fixture;
- Phase 4 uses fake-provider or deterministic responses only; no Vertex/Gemini/API
  live call is made;
- `wiki/metadata/generated-coverage.json`,
  `wiki/validation/generated-coverage-report.md`, nested `wiki/index.md`, and
  generated-section/document metadata are present and passing;
- the run report records exact commands, exit codes, gate statuses, coverage
  counts, evidence counts, determinism/rerun notes, and whether any wrapper/code
  changes were required;
- benchmark-only comparison against `ragflow-deepwiki.md` identifies remaining
  coverage/structure gaps without using it as evidence or chasing line count;
- focused tests and full suite pass using `uv run python -m pytest -q`;
- no protected Phase 3 spec changes, validator weakening, synthetic evidence,
  filler, silent downgrade, generic healing loop, or historical live artifact edit.

### Milestone 2 acceptance criteria

A later implementation must demonstrate:

- Milestone 1 malformed-token validation is complete and passing.
- A deterministic expanded plan includes all mandatory topic families.
- Coverage validation fails a compact 16-section-only plan when enhancement mode
  is requested.
- Expanded pages have matching EvidencePackets with per-topic sufficiency
  reporting.
- Fake-provider integration generates a hierarchical multi-page wiki with passing
  citation, malformed-token, unsupported-identifier, and coverage validation.
- Fixtures missing frontend/memory/queue topics fail coverage validation even if
  citation validation passes.
- A comparison report shows materially improved topic coverage over the
  `20260623-183730` run without treating line count as the sole metric.

## What not to do

- Do not create additional competing iteration specs for this work.
- Do not fix coverage by only increasing token limits.
- Do not chase line count with filler or repeated summaries.
- Do not copy the reference export.
- Do not make `ragflow-deepwiki.md` citeable evidence.
- Do not weaken validators.
- Do not silently edit the successful live wiki artifacts in place.
- Do not modify `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Do not run live/billed models until deterministic planning, evidence,
  validation, and fake-provider tests pass and the user explicitly approves a
  live retry.

## Recommended implementation sequence

Completed foundation:

1. Implement Milestone 1 malformed evidence-token validation and tests.
2. Update run reports/validation messaging so the old successful run is described
   as historical under the older validator, not strict final sign-off.
3. Add coverage taxonomy fixtures and validation for missing mandatory topic
   families.
4. Preserve Phase 2 coverage labels, PagePlan obligations, and parent/child
   hierarchy in normalized planning artifacts.
5. Expand Phase 1 deterministic coverage signals and include them in planner
   context as non-citeable condensates.
6. Implement the Phase 2 planned-coverage gate that consumes the coverage signals
   and fails loudly when mandatory planned families are absent, without adding a
   generic healing loop.

Completed foundation (continued):

7. Implemented the Phase 3 Evidence Sufficiency Contract above: preserve/consume
   explicit topic evidence requirements, map them to exact covered evidence IDs,
   write evidenced-coverage artifacts, and fail enhancement mode before Phase 4 on
   weak/missing required-topic evidence (`retrieve-evidence --coverage-mode
   enhancement`).

Completed foundation (continued):

8. Implemented the Phase 4 Generated Coverage Contract above: opt-in
   `write-wiki --coverage-mode enhancement` with pre-provider planned/evidenced
   upstream gates, hierarchy-preserving prompts/index/metadata, WritingPackets
   carrying the Phase 3 mapped evidence IDs, and deterministic
   `generated_required_topics_covered` validation (omitted/placeholder/out-of-scope/
   uncited topic → exit 5; missing/failed upstream gate → exit 3).

Pending active sequence:

9. Run non-live/fake-provider hierarchical end-to-end validation over an expanded
   multi-family plan, plus the benchmark-only comparison.
10. Only after that, request explicit user approval for a live/billed retry.

## Coding-agent prompt summary

Milestone 1, the Milestone 2 foundation slices, the Phase 3 evidenced-coverage gate,
and the Phase 4 enhancement-mode hierarchical writing + generated-coverage gate are
implemented and tested non-live. Future coding-agent work should keep validator
behavior strict and proceed with the next concrete non-live slice: **a non-live
hierarchical end-to-end run over an expanded multi-family plan, plus the
benchmark-only comparison against `ragflow-deepwiki.md`**. Keep
all citation/identifier/malformed-token/no-context/no-placeholder/no-truncation
validators strict, keep the Phase 3 evidenced-coverage gate intact (weak/missing
required evidence remains a pipeline failure before Phase 4 in enhancement mode), and
keep the Phase 4 generated-coverage gate intact (an omitted/placeholder/out-of-scope/
uncited evidenced sufficient required topic is a post-provider writing-validation
failure; a missing/failed upstream gate is a pre-provider gate failure). Do
not use fuzzy prose matching, synthetic evidence, silent downgrades, or
retry-until-green loops. Do not call Vertex/Gemini or any live model. Do not edit the
historical generated wiki in place. Do not modify
`docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`. If a Milestone 2 slice is
too large for one coding session, stop after a coherent non-live increment and report
the remaining work clearly.
