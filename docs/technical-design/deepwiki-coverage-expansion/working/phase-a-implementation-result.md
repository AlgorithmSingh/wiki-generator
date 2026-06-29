# Phase A — Catalog Foundation (Shadow Mode): Implementation Result

**Date:** 2026-06-29
**Slice:** Phase A — deterministic source-derived topic catalog in shadow mode (first authorized
coverage-expansion slice; TDD Milestone A).
**Status:** Implemented and validated non-live. Backward-compatible. No live/billed provider calls.

This is the **only** authorized slice. Phase B+ (hierarchical planning enforcement, relevant-source
map, evidence portfolios, Phase 4 content blocks, traceability/freshness gates, live validation) was
**not** implemented. No Phase B+ gate was wired.

---

## 1. Summary of what changed

Phase A adds a deterministic, repository-derived **hierarchical topic catalog** to the existing
Phase 1 condense/digest/bundle flow, in **shadow mode**:

- A new catalog builder turns the existing per-family coverage signal
  (`libs/coverage/signals.py`) into a shallow parent/child topic catalog: one **parent topic** per
  mandatory DeepWiki family, plus source-derived **child subsystem topics** (clustered by leaf
  directory) under high-signal families.
- It emits two artifacts under the existing run output structure:
  `derived/topic-catalog.json` (schema `deepwiki-topic-catalog-v1`) and
  `derived/planning-topic-catalog.md` (planner-facing summary).
- The markdown ships in the planner upload bundle as **planner context, never citeable evidence**;
  the JSON sidecar stays on disk (not uploaded), like the existing `coverage-signals.json`.
- The catalog is **deterministic and timestamp-free** (a `source_fingerprint` over the topics is the
  stable identity for later freshness/traceability milestones), **benchmark-isolated** (every signal
  `source == "repo"`; no benchmark export is read), and makes **gaps explicit** (a family with no
  Phase-1 signal becomes a deferred known-gap topic with a source-derived reason — never an invented
  page).

Shadow-mode guarantees held: no existing validator pass/fail behavior changed, no live model is
required, and generated wiki output is untouched. The whole pipeline (Phase 1–4) test suite remains
green.

### Design approach vs. the Python sequence skill

The work used the Python sequence skill's **discipline** (explicit types, no import-time
service/IO side effects, no hidden dependency lookup, deterministic + isolated tests, `uv`-managed
commands, honest validation, clean working tree) adapted to an *existing* codebase rather than a
greenfield 27-stage dossier build. Intake → grounding → requirements → planning → routing were
performed by reading the PRD/TDD/ADR/spec and the existing seams; writing reused the established
condensate/sidecar pattern; the gate (stage 27) is the real focused + full test runs below. No
`.sequence/` scratch files were written (they would be stray artifacts in this repo); the required
artifact is this report.

---

## 2. Files changed

### New modules (source)
- `src/wiki_generator/libs/coverage/facets.py` — deterministic facet (subsystem) clustering of a
  family's candidate files by leaf directory; stable, family-unique facet keys with collision
  breaking; bounded; pure/LLM-free/network-free.
- `src/wiki_generator/libs/coverage/topic_catalog.py` — the catalog data model
  (`TopicCatalog` / `CatalogTopic` / `TopicSignal` / `SourceHandle`), the deterministic
  `build_topic_catalog(bundle)` builder (parent families + child subsystems, profile/block/lane
  suggestions, signal strength/priority/min-exact, deferred known gaps, `source_fingerprint`), and
  `render_catalog_markdown(catalog)`.
- `src/wiki_generator/libs/digest/planning_topic_catalog.py` — thin condensate wrapper exposing the
  `build(bundle) -> str` contract.

### New tests
- `tests/test_coverage_facets.py` — 18 tests for facet clustering.
- `tests/test_topic_catalog.py` — 23 tests for the catalog (shape, source derivation, determinism,
  benchmark isolation, markdown, condense/upload integration).

### Modified (source)
- `src/wiki_generator/libs/coverage/signals.py` — extracted the existing inline candidate-file scan
  into a shared public `family_candidates(files, det)` helper (uncapped) that both the per-family
  detector and the catalog facet builder use, so they can never disagree; added a public
  `status_for(...)` wrapper over the canonical signal-strength thresholds. Behavior-preserving
  refactor (existing `test_coverage_signals.py` still passes).
- `src/wiki_generator/libs/coverage/__init__.py` — export the new public surface (`facets`,
  `topic_catalog`, `family_candidates`, `status_for`).
- `src/wiki_generator/libs/commands/condense.py` — register the `planning-topic-catalog.md`
  condensate and write the isolated `topic-catalog.json` sidecar (failure isolated like the others).
- `src/wiki_generator/libs/digest/upload_package.py` — include `planning-topic-catalog.md` in the
  required condensate set (copied + concatenated into the upload bundle) and document it in the
  planner README as non-citeable, benchmark-isolated catalog context.

### Modified (tests)
- `tests/test_coverage_signals.py` — added `SharedHelperTests` for the `family_candidates` /
  `status_for` seams.
- `tests/test_phase1.py` — added three `DigestTests` cases asserting the catalog artifacts are
  produced by the real `condense`/`digest` E2E, are deterministic across runs, and that the markdown
  (not the JSON) is shipped in the upload bundle.

### Not touched (preserved)
- `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` — **unchanged** (verified by hash
  `0dff5566c29d81f4ab1ece7a20499a29a92f3dae`, identical before and after; `git diff --exit-code`
  exit 0).
- Pre-existing uncommitted user docs (`docs/README.md`, `docs/product-requirements/`,
  `docs/technical-design/`, `docs/specs/not-done/DEEPWIKI_COVERAGE_EXPANSION_IMPLEMENTATION_SPEC.md`)
  — preserved, not clobbered.
- No live provider behavior, no generated wiki output, no validators were modified.

---

## 3. Artifacts added (per run, deterministic)

```text
derived/topic-catalog.json          # schema deepwiki-topic-catalog-v1; role=planner_context;
                                     # citeable_as_evidence=false; source_fingerprint=sha256:...
derived/planning-topic-catalog.md    # planner-facing summary; loud non-citeable + benchmark-isolated
                                     # warning; strong vs. weak/deferred sections; compact handles
planner-digest/planning-topic-catalog.md   # byte-identical copy shipped as planner context in the
                                           # upload bundle (the JSON sidecar is NOT uploaded)
```

`topic-catalog.json` topic fields: `topic_id`, `parent_topic_id`, `family`, `label`, `topic_kind`
(`family`|`subsystem`), `suggested_page_profile`, `status` (`present`|`low`|`missing`|`synthesized`),
`signal_strength`, `priority`, `source_signals[]` (`{kind,value,weight,source="repo"}`),
`candidate_source_handles[]` (`{kind,path,symbol,line_start,line_end}`),
`required_content_blocks[]`, `expected_evidence_lanes[]`, `min_exact_items`, `known_gap_reason`.

---

## 4. Tests and checks run

Runner: `uv` (project pins Python 3.12; suite is stdlib `unittest`, also runnable under `pytest`).

| Command | Status | Notes |
| --- | --- | --- |
| `uv run python -m pytest -q tests/test_coverage_signals.py tests/test_phase1.py` | **pass** | 125 passed, 1 skipped (pre-existing embeddings skip). |
| `uv run python -m pytest -q tests/test_coverage_facets.py tests/test_topic_catalog.py` | **pass** | 41 passed. |
| `uv run python -m pytest -q` (full suite) | **pass** | 573 passed, 1 skipped, 21 subtests passed. |
| `uv run python -m unittest tests.test_coverage_facets tests.test_topic_catalog tests.test_coverage_signals` | **pass** | 65 tests OK (project-native runner). |
| `git diff --check` | **pass** | exit 0 — no whitespace errors. |
| `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` | **pass** | exit 0 — protected spec unchanged. |

The single skip is the pre-existing optional vector-embeddings test, unrelated to this slice. No
checks were `not_run`. No live/billed provider calls were made.

---

## 5. PRD compliance

Checked against `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`.
Phase A is the upstream-most slice, so it satisfies the *catalog* requirements and stays clear of
(does not regress) the rest.

| PRD item | Phase A outcome |
| --- | --- |
| **UR-01** build repository-derived topic/page catalog before planning | **Met** — `derived/topic-catalog.json` + markdown, built from Phase-1 artifacts, before Phase 2. |
| **DI-02** machine-readable catalog: stable IDs, source-derived facets, signal strength, suggested profiles, candidate handles, known gaps | **Met** — all fields present in `deepwiki-topic-catalog-v1`. |
| **VG-01** catalog gate: source-derived; every high-signal facet present, or deferred with reason; benchmark text not used | **Met in spirit (shadow)** — catalog is source-derived and benchmark-isolated; missing families are explicit deferred known-gaps with reasons. The *enforcing* gate is Phase B (intentionally not wired). |
| **G-06 / UR-12 / BR-01 / BR-02 / NG-01 / M-08 / QA-10 / VG-09** benchmark isolation | **Met** — every signal `source=="repo"`; no benchmark export is read or referenced; tests assert no benchmark path leaks into JSON/markdown. |
| **QA-02 / M-06 (determinism/freshness substrate)** | **Met** — byte-stable JSON/markdown; timestamp-free; `source_fingerprint` provides the stable identity later freshness/traceability gates consume. |
| **UR-11 / BR-11 / R-03** record known gaps instead of invention | **Met** — no-signal families become deferred known-gap topics, not invented pages. |
| **UR-09 / G-02 / BR-06 / NG-04** preserve strict validators | **Met** — no validator touched; full suite green; catalog marked `citeable_as_evidence=false` and excluded from upload-as-evidence. |
| **NG-02 / NG-03 / BR-07 / BR-08** no length-padding, no output patching, no heal/retry loops | **Met** — no generated output or validators changed; no retry/heal logic added. |
| **UR-02..UR-08, UR-10, UR-13..UR-15** hierarchical enforcement, source map, evidence portfolios, rendering, traceability, repair | **Deferred by design** — these are Phase B–G; Phase A only seeds the catalog substrate they will consume. |

**PRD compliance verdict for this slice: pass** (Phase A scope). Broader PRD goals remain open for
later authorized slices.

---

## 6. Deviations from the implementation spec

1. **No `generated_at` field in the catalog.** The spec's *minimal* example schema allowed
   `"generated_at": "<stable or explicitly marked runtime metadata>"`, but the TDD (§7.1, §8.1) and
   ADR validation require the catalog to be **deterministic and timestamp-free**. Determinism is a
   hard Phase-A acceptance criterion (#3), so the field is intentionally omitted; `source_fingerprint`
   carries identity instead. (TDD wins over the spec's looser example.)
2. **Schema version = `deepwiki-topic-catalog-v1`** (the TDD §8.1 contract name), not the spec's
   looser `topic-catalog-v1` placeholder. Chosen for forward-compatibility with the documented data
   contract.
3. **`bundle.py` not modified.** The spec listed it as a likely touch point; the upload bundle is
   actually assembled by `digest/upload_package.py` (which `bundle.py` delegates to), so the single
   change there was sufficient and lower-risk.
4. **Child-topic emission is conservative.** Subsystem children are emitted only for *present*
   (high-signal) families with ≥2 distinct leaf-directory subsystems, to avoid 1:1 parent/child noise
   and over-fragmentation. Low/missing families are represented by their parent topic alone. This is a
   defensible Phase-A calibration; promotion thresholds remain an open PRD decision (OD-02).
5. **Page-profile / content-block / evidence-lane values are catalog *suggestions* only.** A small
   deterministic family→profile and profile→blocks/lanes mapping lives in `topic_catalog.py`; no
   `page_profiles.py` with gates was created (that is Phase B, TDD §7.2). These fields satisfy the
   TDD data contract without enforcing anything.

No deviation weakens a constraint; all non-negotiables were honored.

---

## 7. Remaining risks

- **Threshold calibration (OD-02/OD-03).** "≥3 files ⇒ present" and "≥2 facets ⇒ children" are
  inherited/seeded heuristics. On a large real repo the catalog may surface many low-value subsystems
  or compress important ones. Mitigation deferred to Phase B promotion thresholds; Phase A keeps
  everything non-enforcing and explicit.
- **Recall overlap across families.** Detector tokens are intentionally recall-oriented (e.g. a
  `layout.tsx` frontend file also matches `doc-processing`'s "layout" token). This is by-design in
  `signals.py` and surfaces as overlapping candidate handles, not a defect — but it means catalog
  subsystem labels can be cross-cutting. Later source-selection (Phase C) must disambiguate.
- **Single-file subsystems.** A present family split across single-file directories yields several
  `low`-status child topics. Honest, but noisier than ideal; revisit when promotion thresholds land.
- **Catalog is not yet consumed downstream.** In shadow mode nothing reads the catalog, so a latent
  schema bug would not surface until Phase B. The fingerprint and tests reduce this risk.
- **Language/runtime blind spots (R-07).** Detection is path/symbol/query-pack based; non-Python/Go
  surfaces only appear if Phase-1 inventoried them. Deferred families make such gaps explicit.

---

## 8. Recommended next slice

**Phase B — Hierarchical planning contract and gates** (TDD Milestone B), the natural next step:

1. Feed `derived/topic-catalog.json` into the Phase 2 planner prompt (constrain page planning to
   catalog-backed parent/child topics; the upload bundle already carries the markdown).
2. Add additive normalized `PagePlan`/`SectionPlan` fields (`page_profile`, `catalog_topic_ids[]`,
   `required_content_blocks[]`, hierarchy via `parent_section_id`, and
   `topic_evidence_requirements[].catalog_topic_id`/`.content_block_id`).
3. Add **shadow-then-enforcing** catalog-coverage / hierarchy / page-profile / content-block gates
   under `--coverage-mode enhancement` only, keeping `baseline` non-breaking and Phase 3 deterministic
   and LLM-free.
4. Calibrate promotion thresholds (OD-02) and decide which page profiles ship first (OD-03/OD-04)
   from a real catalog before enforcement.

Defer Phase C–G (relevant-source map, evidence portfolios, content-block rendering,
traceability/freshness, live validation) to their own authorized specs. Any live Vertex/Gemini run
requires explicit user approval.
