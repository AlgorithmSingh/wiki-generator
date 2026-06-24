# DeepWiki-Informed Coverage Enhancement Iteration Spec

## Status and source of truth

Status: **Milestone 1 implemented. Milestone 2 is in progress: coverage
taxonomy/validation, Phase 2 planning/PagePlan obligation preservation, and Phase
1 deterministic coverage-signal expansion are implemented and tested. Pending
next: Phase 2 enhancement-mode upstream prevention plus bounded LLM re-prompt
only where needed using coverage signals, Phase 3 page-level evidence and
evidenced coverage, Phase 4 hierarchical writing and generated coverage, and
non-live hierarchical E2E before any approved live retry**.

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
python -m pytest -q tests/test_phase4.py
python -m pytest -q
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
  `0` (pass / baseline), `2` (no normalized plan), or `3` (enhancement gate fail).
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

### Remaining Milestone 2 work — active pending backlog

1. **Phase 2 enhancement-mode upstream prevention using coverage signals.** The
   next implementation slice should consume `planning-coverage-signals.md`,
   require stable parent/child pages with `coverage_labels[]`, and prevent
   mandatory-family omissions by improving the Phase 2 prompt/context/schema and
   deterministic normalization/gating. Do not add a generic healing loop. If the
   LLM-authored plan still misses mandatory families, allow only a bounded,
   audited LLM re-prompt/repair with exact diagnostics and loud failure after the
   cap.
2. **Phase 3 page-level evidence and evidenced coverage.** Retrieve evidence per
   planned page/child section and report per-required-topic sufficiency while
   preserving deterministic, all-sections, no-force, no-retry-loop constraints.
3. **Phase 4 hierarchical writing and generated coverage.** Generate hierarchical
   pages from page-level evidence, emit planned-vs-generated coverage metadata,
   and keep all citation/identifier/malformed-token validators strict.
4. **Non-live hierarchical E2E.** Prove the expanded path with fake-provider or
   non-live fixtures before requesting explicit user approval for any billed
   Vertex/Gemini retry.
5. **Benchmark-only comparison.** Compare against `ragflow-deepwiki.md` only as a
   structure/coverage benchmark, never as citeable evidence.

### Next-slice acceptance — Phase 2 enhancement-mode upstream prevention

The next implementation slice is accepted only when it proves all of the
following in non-live tests:

- Phase 2 planning prompt/context explicitly includes and explains
  `planning-coverage-signals.md` as planner context, not citeable evidence.
- Enhancement mode has a deterministic gate that evaluates the normalized plan
  against all thirteen mandatory coverage families before Phase 3 retrieval.
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

Pending active sequence:

6. Implement Phase 2 enhancement-mode upstream prevention that consumes the
   coverage signals and fails loudly when mandatory families are absent. Bounded
   LLM re-prompt/repair is allowed only for the LLM-authored planning response,
   with exact diagnostics, audit artifacts, and a hard cap; deterministic stages
   must be fixed upstream rather than wrapped in healing loops.
7. Extend Phase 3 to retrieve per planned page/child section and report evidenced
   per-topic sufficiency.
8. Extend Phase 4 to write hierarchical pages and emit planned-vs-generated
   coverage metadata.
9. Run non-live/fake-provider hierarchical end-to-end validation.
10. Only after that, request explicit user approval for a live/billed retry.

## Coding-agent prompt summary

Milestone 1 and the first Milestone 2 foundation slices are implemented. Future
coding-agent work should keep validator behavior strict and proceed with the next
concrete non-live slice: **Phase 2 enhancement-mode upstream prevention using the
Phase 1 coverage signals, with bounded LLM re-prompt only if the LLM-authored plan
misses mandatory families**. Do not call Vertex/Gemini or any live model. Do not edit the
historical generated wiki in place. Do not modify
`docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`. Keep validators strict.
If a Milestone 2 slice is too large for one coding session, stop after a coherent
non-live increment and report the remaining work clearly.
