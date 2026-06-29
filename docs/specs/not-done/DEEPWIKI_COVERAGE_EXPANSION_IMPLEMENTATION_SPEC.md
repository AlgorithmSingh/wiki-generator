# DeepWiki Coverage Expansion Implementation Spec

## Status

Status: **active / Phase A–F implemented non-live; broader E2E pending**.

This spec converts the coverage-expansion PRD and TDD into implementation work for `wiki-generator`.

Current implementation state:

- **Phase A — catalog foundation in shadow mode:** implemented locally by the prior Claude run and validated non-live. It adds deterministic source-derived catalog artifacts:
  - `derived/topic-catalog.json`
  - `derived/planning-topic-catalog.md`
  - planner bundle inclusion of the Markdown as non-citeable context
  - completion report: `docs/technical-design/deepwiki-coverage-expansion/working/phase-a-implementation-result.md`
- **Phase B–F:** implemented locally and validated non-live. The follow-up expanded `write-wiki` fake-provider command E2E is closed.
- **Phase G live validation:** not authorized by this spec. No live/billed Vertex/Gemini/API calls are allowed without a new explicit user approval.

Primary sources of truth:

- PRD: `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`
- TDD: `docs/technical-design/deepwiki-coverage-expansion/final/technical-design-document.md`
- Working design notes: `docs/technical-design/deepwiki-coverage-expansion/working/`
- ADR: `docs/technical-design/deepwiki-coverage-expansion/adr/0001-expanded-coverage-as-hierarchical-topic-catalog.md`
- Phase A result: `docs/technical-design/deepwiki-coverage-expansion/working/phase-a-implementation-result.md`

Historical and benchmark context:

- Official live grounded RAGFlow E2E passed at `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e`.
- Existing generated wiki is valid for its planned scope: 22 sections, 53/53 generated coverage, 425 distinct citations.
- `/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md` is benchmark-only. It is not citeable evidence, not source truth, and must not be copied from.
- `reverse-engineer.md` says the benchmark was indexed at commit `d32e05d5`, while local RAGFlow validation used a different commit. Treat benchmark headings as breadth signals only.

## Product objective

Increase generated wiki coverage from a concise grounded wiki toward a broader DeepWiki-style hierarchical wiki without weakening grounding.

Do **not** make the existing 22 sections merely longer. The target behavior is upstream coverage expansion:

1. Build a repository-derived expanded topic/page catalog.
2. Plan parent/child pages such as Deployment, Frontend, LLM Integration, Document Processing, Backend API, Agents/Workflow, Retrieval/Search, Memory, and Admin/Ops.
3. Deterministically select relevant files, symbols, contracts, tests, docs, configs, and source spans for each page.
4. Retrieve evidence per page/topic/content block.
5. Render pages through the grounded claim/token plan path.
6. Evaluate coverage by topic→plan→source→evidence→output traceability, not benchmark copying.

The main architecture implication is that coverage expansion is primarily a Phase 1 / Phase 2 planning and source-selection problem, not a Phase 4 prose-generation problem.

## Non-negotiable constraints

- Preserve protected Phase 3 spec: `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Phase 3 remains deterministic and LLM-free.
- Do not use benchmark material as citeable evidence.
- Do not copy benchmark headings/prose/claims into generated output unless independently produced from repository evidence.
- Do not patch generated output to pass validation.
- Do not add generic heal/retry-until-green loops.
- Bounded repair is allowed only for LLM-authored plans or claim plans, with exact diagnostics, audit artifacts, and hard caps.
- Do not weaken citation, placeholder, truncation, malformed-token, unsupported-identifier, context-artifact, evidence, generated-coverage, or freshness validators.
- No live/billed Vertex/Gemini/API calls without explicit user approval.
- Official final provider path remains Vertex/Gemini.
- Preserve backward compatibility: baseline mode and existing enhancement behavior must remain available unless an explicitly documented expanded-coverage flag/mode is used.
- Do not commit changes from autonomous implementation runs unless the user separately asks.

## Full target architecture

```text
Phase 1 deterministic repo bundle
  inventory / symbols / contracts / tests / query packs / runtime surfaces / chunks / spans
    |
    v
expanded topic catalog, non-citeable planner context
  derived/topic-catalog.json
  derived/planning-topic-catalog.md
    |
    v
Phase 2 hierarchical planning
  page profiles + parent/child pages + content blocks + topic evidence requirements
    |
    v
Phase 2 deterministic normalization/gates
  document-plan.json
  section-plans.jsonl
  relevant-source-map.json
  coverage/topic-obligation gates
    |
    v
Phase 3 deterministic evidence retrieval
  evidence packets per page
  profile-aware evidence sufficiency
    |
    v
Phase 4 grounded claim/token rendering
  expanded wiki pages
  generated coverage by topics and content blocks
    |
    v
traceability and freshness gates
  catalog→plan→source→evidence→output lineage
```

## Phase A — catalog foundation in shadow mode

### Status

Implemented locally and validated by the prior autonomous Claude run.

Phase A added:

- `src/wiki_generator/libs/coverage/facets.py`
- `src/wiki_generator/libs/coverage/topic_catalog.py`
- `src/wiki_generator/libs/digest/planning_topic_catalog.py`
- Phase 1 `condense` integration for `derived/topic-catalog.json` and `derived/planning-topic-catalog.md`
- planner upload bundle inclusion of `planning-topic-catalog.md` as non-citeable context
- tests for deterministic facets/catalog behavior and Phase 1 integration

Phase A constraints remain binding:

- catalog is deterministic and timestamp-free;
- catalog is planner context, never citeable evidence;
- all catalog signals are repository-derived;
- weak/missing families become explicit known gaps;
- no Phase B+ gate was enforced in Phase A.

## Implemented local wave: Phases B–F

Phases B, C, D, E, and F are implemented locally and validated non-live. The prior `needs_review` caveat was closed by `docs/technical-design/deepwiki-coverage-expansion/working/phase-b-f-expanded-write-e2e-result.md`, which added the expanded `write-wiki --coverage-mode expanded --grounded-claim-plan` fake-provider command E2E.

This implementation remains pre-live:

- no live/billed provider call has been made for expanded mode;
- no Phase G live validation is authorized by this spec;
- the next step is a broader non-live expanded E2E under `/Users/ankitsingh/Documents/deep-wiki/19-do-it-e2e`.

### Phase B — hierarchical planning contract and gates

Goal: Make Phase 2 use the Phase A topic catalog to plan a hierarchical page tree with profiles, content blocks, topic linkage, and exact evidence obligations.

Expected behavior:

- The planner prompt/upload context includes the topic catalog and instructs the model to plan from source-derived topics.
- Normalization accepts and validates additive page fields while preserving existing SectionPlan compatibility:
  - `parent_section_id` or equivalent parent/child linkage;
  - `page_profile`;
  - `catalog_topic_ids[]`;
  - `required_content_blocks[]`;
  - `known_gaps[]`;
  - extended `topic_evidence_requirements[]` with optional `catalog_topic_id` and `content_block_id`.
- Gates validate hierarchy and page profile completeness in expanded/enhancement mode:
  - parent references resolve;
  - hierarchy is acyclic;
  - high-signal catalog topics are planned or explicitly deferred with a source-derived reason;
  - page profiles are valid;
  - required content blocks exist for profile-bearing pages;
  - broad parent pages do not satisfy child topic obligations by themselves.
- Baseline mode stays non-breaking.
- Any enforcement should be opt-in or limited to an explicit expanded/enhancement path until proven stable.

Likely files:

- `src/wiki_generator/libs/commands/plan.py`
- `gemini-gem/GEM_INSTRUCTIONS.md`
- `gemini-gem/KICKOFF_PROMPT.md`
- `src/wiki_generator/libs/plan_normalization/parse.py`
- `src/wiki_generator/libs/plan_normalization/normalize.py`
- `src/wiki_generator/libs/plan_normalization/writer.py`
- `src/wiki_generator/libs/plan_normalization/repair.py`
- `src/wiki_generator/libs/coverage/validate.py`
- `src/wiki_generator/libs/coverage/obligations.py`
- new or extended tests such as `tests/test_phase2_topic_catalog_planning.py`

### Phase C — deterministic relevant-source map before Phase 3

Goal: Select page-relevant source handles deterministically before retrieval.

Expected artifact:

```text
plans/relevant-source-map.json
```

Expected behavior:

- The source map links page IDs, catalog topic IDs, content block IDs, TERs, and candidate source handles.
- Selection uses exact handles when available: files, symbols, contracts, tests, docs, configs, query packs, chunks/spans.
- Scoring is deterministic and documented.
- Blocking topics/content blocks without citeable selected handles fail the expanded/enhancement gate.
- The source map fingerprints the catalog and normalized plan artifacts it consumed.
- Benchmark artifacts and generated wiki artifacts are never source-map inputs.

Likely files:

- new `src/wiki_generator/libs/coverage/source_selection.py`
- `src/wiki_generator/libs/coverage/substrate.py`
- `src/wiki_generator/libs/coverage/obligations.py`
- `src/wiki_generator/libs/plan_normalization/normalize.py`
- `src/wiki_generator/libs/plan_normalization/writer.py`
- `src/wiki_generator/libs/commands/normalize_plan.py`
- tests such as `tests/test_relevant_source_map.py`

### Phase D — profile-aware evidence portfolios

Goal: Phase 3 retrieves and validates sufficient evidence per page/topic/content block, still deterministically.

Expected behavior:

- Evidence packets and evidenced coverage preserve page/profile/content-block linkage.
- Portfolio requirements are profile-aware, for example:
  - API pages need route/contract plus handler evidence when available;
  - deployment pages need config/deployment docs or files;
  - subsystem deep dives need file/symbol/test or equivalent source evidence;
  - operations pages need command/config/health/migration/logging evidence when present.
- Broad recall alone is insufficient for blocking technical claims.
- Phase 3 remains deterministic and LLM-free.
- Existing Phase 3 exit-code semantics and strict gates are preserved.

Likely files:

- `src/wiki_generator/libs/evidence/options.py`
- `src/wiki_generator/libs/evidence/aggregate.py`
- `src/wiki_generator/libs/evidence/evidenced_coverage.py`
- `src/wiki_generator/libs/evidence/validate.py`
- `src/wiki_generator/libs/commands/retrieve_evidence.py`
- tests such as `tests/test_phase3_evidence_portfolios.py`

### Phase E — grounded page-profile rendering and content-block coverage

Goal: Render expanded pages through the existing grounded claim/token path, with validation by content blocks as well as topics.

Expected behavior:

- Writing packets carry page profile, catalog topics, required content blocks, source-map rows, and portfolio/evidenced-coverage rows.
- The grounded claim-plan schema can group or map claims by `content_block_id` and required topic.
- Deterministic rendering remains token-placeholder based, not free invention.
- Generated coverage validates:
  - covered topics;
  - covered content blocks;
  - valid local citations for every required coverage item;
  - no context-artifact citations;
  - no unsupported identifiers/tokens;
  - no placeholders/truncation.
- Existing grounded mode remains available; any expanded behavior is opt-in or tied to an explicit expanded/enhancement path.

Likely files:

- `src/wiki_generator/libs/writing/packet.py`
- `src/wiki_generator/libs/writing/bundle.py`
- `src/wiki_generator/libs/writing/claim_plan.py`
- `src/wiki_generator/libs/writing/grounded.py`
- `src/wiki_generator/libs/writing/validate.py`
- `src/wiki_generator/libs/commands/write_wiki.py`
- `tests/test_phase4_depth_profiles.py`
- extensions to `tests/test_phase4_grounded.py`, `tests/test_phase4_generated_coverage.py`, `tests/test_phase4.py`

### Phase F — traceability, freshness, and non-live E2E

Goal: Prove catalog→plan→source→evidence→output traceability and artifact freshness end-to-end without live/billed calls.

Expected artifacts:

```text
coverage/coverage-traceability.json
coverage/coverage-traceability-report.md
```

Expected behavior:

- Traceability rows link:
  - catalog topic ID;
  - page/section ID;
  - content block ID;
  - source-map handle(s);
  - evidence ID(s);
  - generated Markdown anchors/citations;
  - validation status;
  - defer/known-gap reason when applicable.
- PASS artifacts fingerprint the exact upstream catalog/plan/source-map/evidence artifacts consumed.
- Stale downstream artifacts fail closed.
- Benchmark comparison remains outside evidence gates.
- A non-live fixture or fake-provider E2E proves the expanded path without calling Vertex/Gemini.

Likely files:

- new `src/wiki_generator/libs/coverage/traceability.py`
- new or extended `src/wiki_generator/libs/coverage/metrics.py`
- phase wrapper and validation modules as needed
- `tests/test_coverage_traceability.py`
- `tests/test_artifact_consistency.py`
- wrapper/CLI tests for expanded mode

## B–F acceptance criteria

The B–F implementation wave is considered successful locally because:

1. Phase B adds hierarchical planning fields and validation without breaking existing plan normalization.
2. Phase C writes a deterministic `plans/relevant-source-map.json` for expanded runs.
3. Phase D carries page/profile/content-block linkage into deterministic evidence and evidenced coverage.
4. Phase E renders expanded pages through grounded claim/token planning and validates content-block coverage.
5. Phase F writes traceability/freshness artifacts and has tests for stale/mismatched upstream inputs.
6. Baseline behavior remains backward-compatible.
7. No protected Phase 3 spec changes occur.
8. No live/billed provider calls occur.
9. Benchmark material remains comparator-only and non-citeable.
10. Focused tests for each implemented phase pass.
11. Full test suite passes, or any not-run checks are honestly reported with reason.
12. A B–F completion report includes a PRD compliance check against `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`.

The remaining validation step is a broader non-live expanded E2E outside the focused unit/integration fixtures. If that E2E exposes deterministic failures, fix the owning upstream producer/schema/validator/test rather than patching generated output.

## Explicitly out of scope for B–F

- Live Vertex/Gemini validation or any live/billed model/API call.
- GitHub release/tag work.
- Output patching of generated Markdown.
- Benchmark-derived topic enforcement.
- Validator weakening.
- Rewriting Phase A from scratch unless a defect blocks B–F.
- Committing changes.

## Verification commands

The implementing agent should run the narrowest meaningful commands first, then broaden. Expected commands include, adjusted to actual test filenames:

```bash
uv run python -m pytest -q tests/test_coverage_facets.py tests/test_topic_catalog.py
uv run python -m pytest -q tests/test_phase2_topic_catalog_planning.py tests/test_relevant_source_map.py
uv run python -m pytest -q tests/test_phase3_evidence_portfolios.py
uv run python -m pytest -q tests/test_phase4_depth_profiles.py tests/test_phase4_grounded.py tests/test_phase4_generated_coverage.py
uv run python -m pytest -q tests/test_coverage_traceability.py tests/test_artifact_consistency.py
uv run python -m pytest -q
```

Also run:

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
```

No result may be reported as passing unless the command actually ran and returned success.

## Completion report requirements

B–F reports are written at:

```text
docs/technical-design/deepwiki-coverage-expansion/working/phase-b-f-implementation-result.md
docs/technical-design/deepwiki-coverage-expansion/working/phase-b-f-expanded-write-e2e-result.md
```

The report must include:

- summary of what changed;
- phase-by-phase completion status for B, C, D, E, and F;
- files changed;
- artifacts added;
- tests run and results;
- any not-run checks with reason;
- PRD compliance check against `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`;
- deviations from this spec or the TDD;
- remaining risks;
- recommended next slice;
- explicit statement that no live/billed provider calls were made.

## Phase G placeholder

Phase G — controlled live validation and rollout — remains future work. It requires explicit user approval because it may use live/billed Vertex/Gemini. It is not authorized by this spec.
