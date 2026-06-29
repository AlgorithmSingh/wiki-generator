# Phases B–F — Coverage Expansion Wave: Implementation Result

**Date:** 2026-06-29
**Slice:** Phases B, C, D, E, F of the DeepWiki coverage-expansion wave (TDD Milestones
B–F), implemented in one autonomous run on top of the existing Phase A catalog
foundation.
**Status:** Implemented and validated **non-live**. Backward-compatible. **No
live/billed provider calls.** Final status: **`ok`** after follow-up closure of the
previously deferred fake-provider `write-wiki --coverage-mode expanded` command E2E.
Follow-up report: `docs/technical-design/deepwiki-coverage-expansion/working/phase-b-f-expanded-write-e2e-result.md`.

This run followed the Python implementation-sequence skill's discipline (explicit
types, no import-time side effects, no hidden dependency lookup, deterministic +
isolated tests, `uv`-managed commands, honest validation, clean working tree) adapted
to an existing codebase, with the real gate being the focused + full `pytest` runs and
the `git diff` checks below.

---

## 1. Summary of what changed

The wave adds the opt-in **`expanded`** DeepWiki-style hierarchical coverage mode — a
strict superset of the existing `enhancement` mode — across the whole Phase 2→4
pipeline, plus a Phase F traceability/freshness gate. Every change is additive and
gated on the new mode (or the existing enforcing modes), so **`baseline` and
`enhancement` runs are byte-for-byte unchanged**.

- A new third coverage mode `expanded` is accepted by `normalize-plan`,
  `retrieve-evidence`, `write-wiki`, `plan-repair`, and `validate-coverage`
  (`--mode expanded`). `baseline` (default) and `enhancement` are untouched.
- **Phase B** plans a hierarchy from the Phase A topic catalog: normalization carries
  `page_profile`, `catalog_topic_ids[]`, `required_content_blocks[]`, and extended
  `topic_evidence_requirements[].catalog_topic_id`/`.content_block_id`; a deterministic
  page-planning gate validates acyclic resolved hierarchy, valid page profiles + their
  required content blocks, and high-signal catalog-topic coverage (planned or
  explicitly deferred — a broad parent never covers a child).
- **Phase C** writes `plans/relevant-source-map.json`: a deterministic per-page
  selection of exact citeable source handles, scored, mapped to catalog topics /
  content blocks, fingerprinting the catalog + plan it consumed; the source-selection
  gate fails closed when a page-profile floor / blocking topic / content block has no
  citeable selected handle. Benchmark/generated-wiki artifacts are never inputs.
- **Phase D** makes Phase 3 evidenced coverage profile-aware: it carries
  page/profile/content-block linkage onto the matrix and enforces a per-page evidence
  **portfolio** (a sufficient exact handle in a profile floor lane + the profile's
  minimum exact-item count) plus TER-linked content-block sufficiency — still
  deterministic and LLM-free, reusing the existing exit-3 path.
- **Phase E** carries the page profile, catalog topics, content blocks, content-block
  obligations, and relevant-source-map rows into the writing packet; the grounded
  claim plan accepts `content_block_id` and the renderer derives
  `covered_content_blocks[]`; generated-coverage validates content blocks as well as
  topics (exit 5), with the existing strict citation/placeholder/token validators
  unchanged.
- **Phase F** adds `coverage/traceability.py`: `coverage/coverage-traceability.json` +
  `coverage-traceability-report.md` join catalog topic → page → content block → source
  handle → evidence → output anchor/citation, and a **freshness** gate fails closed on
  a stale plan/catalog fingerprint or a non-enforced/failed upstream artifact.

---

## 2. Phase-by-phase completion status

| Phase | Status | Notes |
| --- | --- | --- |
| **B** | **complete** | Page-profile registry + page-planning gate + additive normalization fields; wired into `normalize-plan --coverage-mode expanded`; 20 focused tests + integrated command E2E. |
| **C** | **complete** | `plans/relevant-source-map.json` + source-selection gate + fingerprints; wired into the same command; 13 focused tests. |
| **D** | **complete** | Profile-aware evidence portfolios + content-block linkage on the evidenced-coverage matrix; `expanded` accepted by `retrieve-evidence`; 8 focused tests; enhancement/baseline byte-unchanged. |
| **E** | **complete** | Packet enrichment + claim-plan `content_block_id` + `covered_content_blocks` rendering + generated content-block coverage gate; wired through bundle/validate/assemble/packet/grounded; focused tests plus the follow-up fake-provider expanded `write-wiki` command E2E are green. |
| **F** | **complete** | Traceability + freshness gate + `validate-coverage --mode expanded`; non-live artifact-chain E2E (`test_artifact_consistency`) + 9 traceability tests; staleness fails closed. |

---

## 3. Files changed

### New source modules
- `src/wiki_generator/libs/coverage/page_profiles.py` — closed registry of 10 page
  profiles, their required content blocks (evidence-bearing vs narrative), and exact
  evidence-floor lanes; single source of truth for Phase B/D/E.
- `src/wiki_generator/libs/coverage/page_planning.py` — deterministic Phase B
  hierarchical page-planning gate (hierarchy/profile/content-block/catalog-coverage).
- `src/wiki_generator/libs/coverage/source_selection.py` — deterministic Phase C
  relevant-source map + source-selection gate (scoring, fingerprints, citeability).
- `src/wiki_generator/libs/coverage/traceability.py` — Phase F traceability join +
  freshness gate + report.

### Modified source
- `src/wiki_generator/cli.py` — add `expanded` to `--coverage-mode` choices on
  normalize-plan/plan-repair/retrieve-evidence/write-wiki and to `validate-coverage
  --mode`.
- `src/wiki_generator/libs/coverage/__init__.py` — export the new surfaces.
- `src/wiki_generator/libs/coverage/validate.py` — add `MODE_EXPANDED`,
  `_ENFORCING_MODES`, `is_enforcing()`; planned-coverage gate enforces for expanded.
- `src/wiki_generator/libs/coverage/obligations.py` — topic-obligation gate enforces
  for expanded (via `is_enforcing`).
- `src/wiki_generator/libs/coverage/topic_catalog.py` — `load_topic_catalog()` +
  `TOPIC_CATALOG_REL_PATH`.
- `src/wiki_generator/libs/plan_normalization/normalize.py` — additive
  `page_profile` / `catalog_topic_ids[]` / `required_content_blocks[]` fields and the
  extended TER `catalog_topic_id`/`content_block_id`.
- `src/wiki_generator/libs/commands/normalize_plan.py` — mode-aware
  `_run_coverage_gates`; expanded runs the page-planning + source-map gates and writes
  their artifacts.
- `src/wiki_generator/libs/commands/validate_coverage.py` — `--mode expanded` builds +
  gates traceability and writes the coverage artifacts.
- `src/wiki_generator/libs/evidence/options.py` — add `COVERAGE_MODE_EXPANDED`.
- `src/wiki_generator/libs/evidence/evidenced_coverage.py` — profile-aware portfolio +
  content-block evaluation + additive expanded linkage (mode-gated).
- `src/wiki_generator/libs/writing/options.py` — `COVERAGE_MODE_EXPANDED`,
  `ENFORCING_COVERAGE_MODES`, `is_expanded`/`enforces_coverage`.
- `src/wiki_generator/libs/writing/bundle.py` — gate 6 + obligations for the enforcing
  modes; `content_block_obligations` on the bundle.
- `src/wiki_generator/libs/writing/generated_coverage.py` — accept expanded gates;
  `build_content_block_obligations`, `normalize_covered_content_blocks`,
  `evaluate_section_block_coverage`; content-block coverage in the matrix.
- `src/wiki_generator/libs/writing/packet.py` — expanded packet enrichment (profile,
  catalog topics, content blocks, content-block obligations, relevant-source-map rows).
- `src/wiki_generator/libs/writing/claim_plan.py` — claim `content_block_id`;
  `covered_content_blocks[]` derivation; `RenderedSection`/`rendered_draft` extension.
- `src/wiki_generator/libs/writing/grounded.py` — `section_block_obligations`; pass
  content-block obligations into render.
- `src/wiki_generator/libs/writing/validate.py` — accept enforcing modes; thread
  `covered_content_blocks`; named content-block coverage check.
- `src/wiki_generator/libs/writing/assemble.py` — record `covered_content_blocks` +
  `page_profile` for the enforcing modes.

### New tests (70 tests across 6 files plus follow-up command E2E coverage)
- `tests/test_phase2_topic_catalog_planning.py` (20)
- `tests/test_relevant_source_map.py` (13)
- `tests/test_phase3_evidence_portfolios.py` (8)
- `tests/test_phase4_depth_profiles.py` (13)
- `tests/test_coverage_traceability.py` (9)
- `tests/test_artifact_consistency.py` (5)

### Preserved (not touched)
- `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` — **unchanged**
  (`git diff --exit-code` exit 0). Phase 3 remains deterministic and LLM-free.
- All pre-existing uncommitted user/Phase-A work (PRD/TDD/spec docs, Phase A modules,
  `docs/README.md`) — preserved, not clobbered.

---

## 4. Artifacts added (per expanded run)

```text
plans/page-planning-gate.json / page-planning-report.md          # Phase B gate
plans/relevant-source-map.json                                   # Phase C source map
plans/source-selection-gate.json / relevant-source-map-report.md # Phase C gate
evidence/evidenced-coverage.json (extended)                      # Phase D portfolio rows
wiki/metadata/generated-coverage.json (extended)                 # Phase E content blocks
coverage/coverage-traceability.json / -report.md                 # Phase F lineage + freshness
```

`enhancement`/`baseline` runs do not emit the expanded-only artifacts.

---

## 5. Tests and checks run

Runner: `uv` (project pins Python 3.12; `unittest` suite, also run under `pytest`).

| Command | Status | Notes |
| --- | --- | --- |
| `uv run python -m pytest -q tests/test_coverage_facets.py tests/test_topic_catalog.py` | **pass** | Phase A foundation still green. |
| `uv run python -m pytest -q tests/test_phase2_topic_catalog_planning.py tests/test_relevant_source_map.py` | **pass** | 33 passed (Phase B + C). |
| `uv run python -m pytest -q tests/test_phase3_evidence_portfolios.py` | **pass** | 8 passed (Phase D). |
| `uv run python -m pytest -q tests/test_phase4_depth_profiles.py tests/test_phase4_grounded.py tests/test_phase4_generated_coverage.py` | **pass** | 73 passed, 12 subtests passed after the expanded `write-wiki` command E2E follow-up. |
| `uv run python -m pytest -q tests/test_coverage_traceability.py tests/test_artifact_consistency.py` | **pass** | 14 passed (Phase F). |
| `uv run python -m pytest -q` (full suite) | **pass** | **643 passed, 1 skipped, 21 subtests** after the follow-up E2E. Up from the 573 Phase-A baseline. |
| `python -m py_compile` (all 22 new/changed modules + 6 test files) | **pass** | All compile. |
| AST scan: mutable-default args + import-time side effects (new coverage modules) | **pass** | None found. |
| `git diff --check` | **pass** | exit 0 — no whitespace errors. |
| `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` | **pass** | exit 0 — protected spec unchanged. |
| `ruff check` | **not_run** | `ruff` is not a project dependency (suite is stdlib `unittest`); `py_compile` + AST scan used instead. |
| live Vertex/Gemini E2E | **not_run** | Out of scope (Phase G); no live/billed call made. |

No check was reported as passing unless it actually ran and returned success.

---

## 6. PRD compliance check

Checked against `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`.

| PRD item | Outcome |
| --- | --- |
| **UR-01** repo-derived catalog before planning | **Met** (Phase A; consumed by B). |
| **UR-02 / UR-03** hierarchical parent/child + page profile + content blocks | **Met** — normalization fields + Phase B gate. |
| **UR-04 / VG-03 / DI-04** deterministic per-page source selection before Phase 3 | **Met** — `plans/relevant-source-map.json` + source-selection gate. |
| **UR-05 / DI-05 / DI-06 / QA-06 / BR-04** per page/topic/block evidence sufficiency; broad recall insufficient | **Met** — Phase D profile-aware portfolio floors. |
| **UR-06 / DI-07 / VG-05** grounded claim-plan rendering | **Met** — claim plan + grounded renderer carry content blocks; strict validators unchanged. |
| **UR-07 / UR-08 / QA-03 / DI-08** planned→evidenced→generated traceability | **Met** — `coverage-traceability.json` lineage rows. |
| **UR-09 / VG-07 / BR-06 / NG-04** preserve strict validators | **Met** — no validator weakened; new gates added only. |
| **UR-10 / VG-04 / VG-06** fail closed on missing/weak/unsupported coverage | **Met** — exit 3 (Phase 2/3), exit 5 (Phase 4). |
| **UR-11 / BR-11 / R-03** known gaps instead of invention | **Met** — deferral via `known_gaps[]` with source-derived reasons. |
| **UR-12 / G-06 / BR-01 / BR-02 / M-08 / QA-10 / VG-09** benchmark isolation | **Met** — no benchmark/generated-wiki input to any gate; source map explicitly excludes them. |
| **BR-03** broad parent never satisfies child obligation | **Met** — catalog coverage matches exact topic ids; tested. |
| **M-06 / BR-09 / VG-08 / QA-02 / DI-10** artifact freshness + determinism | **Met** — fingerprints + freshness gate; byte-deterministic artifacts (tested). |
| **NG-02 / NG-03 / BR-07 / BR-08** no length-padding, output patching, heal/retry loops | **Met** — no output mutation, no generic retry; expanded gates only report + fail. |
| **UR-15 / QA-09** bounded repair only for LLM-authored plans/claim plans | **Met (unchanged)** — existing bounded claim-plan repair reused; no new heal loops. |
| **M-07 coverage breadth band (45–70 pages / 150–250 topics)** | **Enabled, not yet realized** — requires a live expanded run (Phase G); the mechanism is in place. |

**PRD compliance verdict: pass** for the non-live implementation scope of B–F. The
breadth *target* (M-07) and any live numbers depend on the unauthorized Phase G run.

---

## 7. Deviations from the implementation spec / TDD

1. **New `expanded` coverage mode instead of overloading `enhancement`.** The TDD (§9.1)
   describes `--coverage-mode enhancement` as the expanded-enforcement mode. To keep
   the **existing** `enhancement` (and `baseline`) runs and their test contracts
   byte-for-byte unchanged — the #1 backward-compatibility constraint, and the OD-02
   "stage behind a flag" open decision — the hierarchical catalog/profile/content-block
   gates were staged behind a new `expanded` mode that is a strict superset of
   `enhancement`. No constraint is weakened; the expanded path is fully opt-in.
2. **Phase 3 does not read `plans/relevant-source-map.json`.** To keep Phase 3
   self-contained and deterministic, the Phase D portfolio reads the page profile +
   content blocks from the normalized plan (and the page's exact evidence from the
   packet), not from the source map. The source-map→evidence handle linkage is
   materialized in Phase F traceability instead. (The TDD §7.5 suggested Phase 3
   consume the source map; this is a lower-coupling equivalent.)
3. **Content-block coverage is derived from the topic subsections that ground each
   block.** The grounded renderer reuses each block's linked topic subsections (rather
   than inventing block headings) so a block is proven covered by locatable,
   locally-cited topic content. Faithful to "render through the grounded claim/token
   path"; no new prose invention.

No deviation weakens a non-negotiable constraint.

---

## 8. Remaining risks

- **Fake-provider `write-wiki` *command* E2E in expanded mode is now closed.** The
  follow-up report `phase-b-f-expanded-write-e2e-result.md` adds happy-path and
  fail-closed command E2E coverage through the real `write-wiki --coverage-mode
  expanded --grounded-claim-plan` path using local fake responses.
- **Profile floors / `min_exact_items` are seeded heuristics** (e.g. subsystem-deep-dive
  requires 3 exact items). They are deliberately conservative; calibration on a real
  catalog (OD-02/OD-03) may adjust them. They are confined to the expanded path.
- **Catalog-topic deferral matches `known_gaps[]` by topic-id substring.** Deterministic
  and safe (topic ids are distinctive), but a structured `{catalog_topic_id, reason}`
  gap form is also supported and preferable for authored plans.
- **Breadth (M-07) is unproven** until a live expanded run; this wave builds the
  mechanism, not the numbers.

---

## 9. Recommended next slice

1. **Run one broader non-live expanded E2E** under a dedicated run directory to prove
   the committed expanded path outside unit-test fixtures, still without live/billed
   provider calls.
2. **Wire traceability into the `write-wiki` tail** (or a dedicated `traceability`
   step) so a single expanded run emits the lineage artifact without a separate
   `validate-coverage --mode expanded` invocation.
3. **Calibrate profile floors / promotion thresholds (OD-02/OD-03)** against a real
   generated catalog before any default-on rollout.
4. **Phase G — controlled live Vertex/Gemini expanded validation** — requires explicit
   user approval (out of scope here).

---

## 10. Live/billed provider statement

**No live or billed Vertex / Gemini / API provider calls were made during this run.**
All work is deterministic, local, and non-live; the official final provider path
(Vertex/Gemini) and any live validation remain gated behind explicit user approval
(Phase G).
