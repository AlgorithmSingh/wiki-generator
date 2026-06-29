# Technical Design — DeepWiki Scale-Parity (Anti-Compression)

| | |
|---|---|
| Status | Draft → Slice 1 ready to implement |
| Audience | Coverage-gate maintainers, future implementation agents, pipeline operator |
| Weight | Standard (focused single-subsystem change with a new gate + opt-in mode) |
| Source PRD | `docs/product-requirements/deepwiki-scale-parity-next-phase/artifacts/final_prd.md` |
| Phase relation | Next phase of `docs/technical-design/deepwiki-coverage-expansion/` (preserved unchanged) |
| Grounding | *(sourced)* code/run artifact, *(inferred)* design judgment, *(open)* decision |

---

## 1. Summary

Add an opt-in coverage mode **`deepwiki-scale`** (a strict superset of `expanded`)
and a new deterministic Phase 2 gate that closes the anti-compression loophole proven
by the real RAGFlow run. The gate computes a **catalog promotion contract** (tiers
per catalog topic) and enforces that promoted leaf topics fan out into their own
hierarchically-linked, evidence-obligated leaf pages instead of collapsing onto a few
broad pages. It is LLM-free, network-free, read-only, and fails closed (exit 3) before
Phase 3, mirroring the existing coverage gates. Slice 1 delivers the Phase 2 gate, its
data contract, CLI wiring, and tests; downstream phases accept the mode and behave as
`expanded` until their slices land.

---

## 2. Context & Background

*(sourced)* The `deepwiki-coverage-expansion` wave added a 4-phase pipeline with the
`expanded` mode and gates VG-01…VG-10 (catalog, page-planning, source-selection,
evidence sufficiency, grounded rendering, generated coverage, validators, freshness,
benchmark isolation, traceability). The real non-live RAGFlow GPT-5.4-low E2E
(`20260629-152217-…-681b900-ragflow-3f805a64f`) passed all gates yet produced 21 flat
pages / 42 TERs from a 147-topic / 94-`must` / 13-family catalog. The defect is in
`page_planning._eval_catalog_coverage`: a topic is "planned" if its id appears in any
page's `catalog_topic_ids[]`. There is no density ceiling, no distributive TER
obligation, no required hierarchy, and no catalog-derived breadth floor.

---

## 3. Requirements, Constraints, Assumptions & Dependencies

### Requirements (from PRD)
- UR-S1 opt-in `deepwiki-scale` mode; UR-S2 promotion contract; UR-S3 own-leaf-page;
  UR-S4 density cap; UR-S5 TER per promoted topic; UR-S6 family fan-out; UR-S7 breadth
  floor; UR-S8 data contract; UR-S11 non-regression; UR-S12 known-gap deferral;
  UR-S13 deterministic/read-only; UR-S14 injectable policy; UR-S15 non-live path.

### Constraints
- *(sourced)* Python HARD-RULES: explicit typing on public APIs; no mutable default
  args; no import-time side effects; dependency injection (policy object); no broad
  `except`; deterministic; clean working tree; `uv run`/`python -m` validation.
- *(sourced)* Do not modify the protected Phase 3 spec
  (`docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`).
- *(sourced)* Do not weaken any existing validator; do not change `expanded` behavior.

### Assumptions
- A-S1 `topic_kind=="family"` ⇒ index-level; subsystem ⇒ leaf. A-S2 `priority=="must"`
  ⇒ promoted. A-S3 `overview` is the only default index profile (tunable).

### Dependencies
- Reads `derived/topic-catalog.json`, `plans/section-plans.jsonl`,
  `plans/document-plan.json`. Reuses `context_docs.is_provenance_section`,
  `coverage.page_profiles`, `coverage.validate` mode constants. No new third-party
  deps.

---

## 4. Architecture Overview

```
normalize-plan --coverage-mode deepwiki-scale
        │
        ▼  (commands/normalize_plan.py)
 _run_coverage_gates(mode)            # existing: planned-coverage + topic-obligation
        │   mode ∈ {expanded, deepwiki-scale}
        ▼
 _run_expanded_gates(mode)            # existing: page-planning + relevant-source-map
        │   coverage.enforces_breadth(mode)?  (deepwiki-scale only)
        ▼
 gate_anti_compression(catalog, doc_plan, sections, mode, policy)   # NEW
        │
        ▼
 plans/anti-compression-gate.json  +  plans/anti-compression-report.md
        │  promoted_topics[] (tier, has_ter, leaf_pages, status)  → Phase 3/4 (later)
```

The new module `libs/coverage/anti_compression.py` sits beside `page_planning.py` and
`source_selection.py`, shares their dataclass/gate/render shape, and is orchestrated
by `normalize_plan` after the existing expanded gates. It does not alter any existing
gate; it adds one more failing condition in `deepwiki-scale` mode only.

---

## 5. Detailed Design (Component / Module)

### 5.1 New: `libs/coverage/anti_compression.py`
*(inferred; deterministic, read-only)*

**Constants**
- `ANTI_COMPRESSION_SCHEMA_VERSION = "phase2-anti-compression-v1"`
- `FAILURE_CATEGORY = "bad_compressed_normalized_plan"`
- Tier strings: `TIER_PAGE`, `TIER_OVERVIEW`, `TIER_OPTIONAL`, `TIER_KNOWN_GAP`.
- Promoted-topic statuses: `STATUS_COVERED`, `STATUS_UNCOVERED`, `STATUS_DEFERRED`,
  `STATUS_OPTIONAL`.
- Defect codes: `CODE_TOPIC_NO_TER`, `CODE_TOPIC_NO_LEAF_PAGE`,
  `CODE_LEAF_PAGE_OVERLOADED`, `CODE_FAMILY_NOT_SPLIT`, `CODE_FLAT_HIERARCHY`,
  `CODE_INSUFFICIENT_BREADTH`.

**Policy (dependency injection — UR-S14, HARD-RULES)**
```python
@dataclass(frozen=True)
class BreadthPolicy:
    max_promoted_topics_per_leaf_page: int = 4   # density cap (BR-S7 / OD-S2)
    family_split_threshold: int = 6              # families above this must fan out
    flat_plan_family_threshold: int = 3          # ≥ this many promoted families ⇒ non-flat required
    overview_profiles: tuple = ("overview",)     # index/overview profiles (A-S3)
    require_ter_per_promoted_topic: bool = True
    require_leaf_page_per_promoted_topic: bool = True
DEFAULT_BREADTH_POLICY = BreadthPolicy()
```
`required_leaf_pages(n)` = `ceil(n / max_promoted_topics_per_leaf_page)`.

**Promotion contract** `classify_promotion(topic, deferred) -> tier`:
- deferred (id in any `known_gaps[]`) → `TIER_KNOWN_GAP`
- `priority=="must"` & `topic_kind=="family"` → `TIER_OVERVIEW`
- `priority=="must"` & non-family → `TIER_PAGE`
- else → `TIER_OPTIONAL`

**Result model** (each `to_dict()`): `PromotedTopic` (topic_id, family, tier,
priority, signal_strength, topic_kind, has_ter, leaf_pages[], status, defects[]),
`FamilyBreadth` (family, promoted_leaf_count, required_leaf_pages, actual_leaf_pages,
leaf_page_ids[], status, defects[]), `AntiCompressionReport`, `AntiCompressionGate`.

**Public API** (explicit typing; keyword-only mode/policy):
- `evaluate_anti_compression(catalog, document_plan, sections, *, mode, policy=None) -> AntiCompressionReport`
- `gate_anti_compression(catalog, document_plan, sections, *, mode, policy=None) -> AntiCompressionGate`
- `render_anti_compression_markdown(report, *, title=...) -> str`

**Evaluation order** (over non-provenance sections only):
1. Build promoted set from catalog; partition `page`-tier (leaf) vs `overview`.
2. Classify each non-provenance section as leaf vs overview by `page_profile`.
3. Collect `ter_catalog_ids` = `{ter.catalog_topic_id for sections, ter required}`.
4. Per promoted leaf topic, compute `leaf_pages` (non-overview pages listing its id)
   and `has_ter`; assign defects:
   - no leaf page → `CODE_TOPIC_NO_LEAF_PAGE`
   - no TER → `CODE_TOPIC_NO_TER`
5. Per leaf page, count distinct promoted-leaf ids; `> cap` → `CODE_LEAF_PAGE_OVERLOADED`.
6. Per family with `promoted_leaf > split_threshold`: actual leaf pages covering it
   `< required_leaf_pages` → `CODE_FAMILY_NOT_SPLIT`.
7. If `≥ flat_plan_family_threshold` families have promoted leaf topics AND no
   non-provenance section declares a resolving `parent_section_id` → `CODE_FLAT_HIERARCHY`.
8. Breadth floor: `Σ_family required_leaf_pages(promoted_leaf)`; actual non-overview
   leaf pages `< floor` → `CODE_INSUFFICIENT_BREADTH`.

`enforced = enforces_breadth(mode)` (deepwiki-scale only). When not enforced the
report is computed and returned report-only (`passed=True`), so `expanded`/`baseline`
direct calls never block. `catalog is None` ⇒ `catalog_present=False`, report-only.

### 5.2 Changed: `libs/coverage/validate.py`
*(sourced)* Add `MODE_DEEPWIKI_SCALE = "deepwiki-scale"`; extend `_MODES` and
`_ENFORCING_MODES`; add `EXPANDED_MODES = frozenset({MODE_EXPANDED, MODE_DEEPWIKI_SCALE})`
and predicates `is_expanded_family(mode)` and `enforces_breadth(mode)` (True only for
`deepwiki-scale`). No change to existing behavior for the three current modes.

### 5.3 Changed: `libs/coverage/__init__.py`
Re-export `MODE_DEEPWIKI_SCALE`, `enforces_breadth`, `is_expanded_family`, the
`anti_compression` module symbols (`gate_anti_compression`,
`evaluate_anti_compression`, `render_anti_compression_markdown`,
`AntiCompressionGate`, `AntiCompressionReport`, `BreadthPolicy`,
`DEFAULT_BREADTH_POLICY`, `ANTI_COMPRESSION_SCHEMA_VERSION`, defect-code constants).

### 5.4 Changed: `libs/commands/normalize_plan.py`
- `_run_coverage_gates`: run expanded gates when `mode in (EXPANDED, DEEPWIKI_SCALE)`.
- `_run_expanded_gates`/`_run_source_map_gate`: thread the real `mode` (instead of the
  hardcoded `MODE_EXPANDED`) so reports carry the right label and enforce (both are
  enforcing). After the source-map gate, when `coverage.enforces_breadth(mode)`, run
  `gate_anti_compression`, write `anti-compression-gate.json` +
  `anti-compression-report.md`, log summary, and return its exit code if it fails.
- `run`: gate-trigger guard `coverage_mode in (ENHANCEMENT, EXPANDED, DEEPWIKI_SCALE)`.

### 5.5 Changed: CLI + downstream option modules (mode coherence)
- `cli.py`: add `"deepwiki-scale"` to the `choices=` of `normalize-plan`,
  `plan-repair`, `retrieve-evidence`, `write-wiki`; extend help text.
- `libs/evidence/options.py`: add `COVERAGE_MODE_DEEPWIKI_SCALE`; add to
  `COVERAGE_MODES`; add `EXPANDED_COVERAGE_MODES`.
- `libs/evidence/evidenced_coverage.py`: `enforced`/`expanded` checks include the new
  mode via `EXPANDED_COVERAGE_MODES`/membership.
- `libs/writing/options.py`: add constant; add to `COVERAGE_MODES`,
  `ENFORCING_COVERAGE_MODES`; add `EXPANDED_COVERAGE_MODES`; `is_expanded` returns
  membership in it.
- `libs/writing/{grounded,packet}.py`: replace `== COVERAGE_MODE_EXPANDED` with
  membership in `EXPANDED_COVERAGE_MODES`.
- `libs/writing/generated_coverage.py`: extend `_ENFORCING_MODES` with `"deepwiki-scale"`.

These keep a full-pipeline `deepwiki-scale` run valid and behaving as `expanded`
downstream (Slice 1); promoted-topic enforcement (VG-13) is a later slice.

---

## 6. Data Contracts / Artifacts

### 6.1 `plans/anti-compression-gate.json` (`phase2-anti-compression-v1`)
```jsonc
{
  "passed": false,
  "exit_code": 3,
  "report": {
    "schema_version": "phase2-anti-compression-v1",
    "mode": "deepwiki-scale",
    "status": "fail",
    "enforced": true,
    "failure_category": "bad_compressed_normalized_plan",
    "catalog_present": true,
    "policy": {"max_promoted_topics_per_leaf_page": 4, "family_split_threshold": 6,
               "flat_plan_family_threshold": 3, "overview_profiles": ["overview"]},
    "counts": {"sections": 21, "leaf_pages": 20, "overview_pages": 1,
               "promoted_leaf_topics": 81, "covered_topics": 81, "uncovered_topics": 0,
               "required_leaf_pages": 28, "actual_leaf_pages": 20},
    "flat_hierarchy": true,
    "blocking_sections": ["frontend", "go-native", "sandbox-executor"],
    "diagnostics": [{"scope": "section|family|plan", "id": "frontend",
                     "code": "leaf_page_overloaded_with_promoted_topics",
                     "detail": "...", "remediation": "..."}],
    "promoted_topics": [{"topic_id": "frontend.i18n", "family": "frontend",
                         "tier": "page", "has_ter": false, "leaf_pages": ["frontend"],
                         "status": "uncovered", "defects": ["promoted_topic_missing_topic_evidence_requirement"]}],
    "families": [{"family": "frontend", "promoted_leaf_count": 12,
                  "required_leaf_pages": 3, "actual_leaf_pages": 1,
                  "leaf_page_ids": ["frontend"], "status": "fail",
                  "defects": ["high_signal_family_not_split_into_child_pages"]}]
  }
}
```
`promoted_topics[]` is the UR-S8 downstream contract.

### 6.2 No changes to existing artifact schemas. The catalog, section-plans, source
map, evidenced/generated coverage, and traceability schemas are read as-is.

---

## 7. CLI Behavior & Compatibility Strategy

- New value `deepwiki-scale` on all four `--coverage-mode` commands. Default stays
  `baseline`. `baseline`/`enhancement`/`expanded` are byte-for-byte unchanged.
- `normalize-plan --coverage-mode deepwiki-scale`: expanded gates + anti-compression
  gate; absent catalog still exit 2; first failing gate's exit code returned.
- Downstream commands accept the mode and behave as `expanded` (Slice 1).
- Compatibility is additive: new constants and a new module; no signature removed; no
  existing default changed.

---

## 8. Runtime Behavior & Failure Paths

| Condition | Outcome |
|---|---|
| Collapse plan (overloaded leaves / missing TERs / flat / under-floor) | exit 3, `bad_compressed_normalized_plan`, diagnostics name topic/page/family + numbers |
| Catalog absent in deepwiki-scale | exit 2 (existing expanded missing-input path, before anti-compression) |
| Mode not enforcing (baseline/expanded direct call) | report computed, `passed=True` (report-only) |
| Promoted topic deferred via source-derived `known_gaps[]` | tier `known_gap`, not blocking |
| Unknown mode string | `ValueError` (validated against `_MODES`) |

No gate mutates the plan, swallows exceptions, or calls a model/network.

---

## 9. Validation / Evaluation Design

- **Unit**: `tests/test_phase2_anti_compression.py` (stdlib `unittest`, dict
  fixtures matching `test_phase2_topic_catalog_planning.py`): promotion contract;
  each defect code in isolation; pass case; overview-exemption + only-on-overview
  failure; deferral; determinism; report-only modes.
- **Integration**: `normalize-plan --coverage-mode deepwiki-scale` over a temp
  bundle — collapse fixture fails (exit 3, artifact written), fanned fixture passes,
  `enhancement`/`expanded` do not emit `anti-compression-gate.json`.
- **Regression**: full suite via `uv run python -m pytest -q` (pytest runs the
  unittest classes); existing coverage/planning/evidence/writing tests unchanged.
- **Anti-compression acceptance**: a fixture mirroring the real 94-`must`/13-family
  collapse must FAIL; the fanned equivalent must PASS (AC-S1/AC-S2).

---

## 10. Quality Attributes (made measurable)

- **Determinism**: sorted iteration over topics/sections/families; no set-ordering in
  output; identical `anti-compression-gate.json` across runs (AC-S5).
- **Isolation**: `BreadthPolicy` injected; module top level holds only imports,
  constants, dataclasses, functions; no import-time work.
- **Performance**: O(topics + sections·catalog_ids); trivial for ≤ a few thousand
  topics.
- **Non-regression**: measured by the unchanged existing suites passing.

---

## 11. Alternatives & Trade-offs

- **A1 Tighten `expanded` in place.** Rejected: breaks the passing real run and
  existing `expanded` tests; violates "opt-in, non-breaking" (UR-S11). Chosen: new
  superset mode.
- **A2 Fold checks into `page_planning._eval_catalog_coverage`.** Rejected: conflates
  existential planning with distributive breadth, bloats a stable function, and risks
  the `expanded` contract. Chosen: separate `anti_compression` module + gate.
- **A3 Hard-code thresholds.** Rejected: violates HARD-RULES (mutable/scattered
  config) and OD-S2 tunability. Chosen: injectable `BreadthPolicy`.
- **A4 Benchmark page count as the floor.** Rejected: benchmark quarantine (BR-S5).
  Chosen: catalog-derived floor.
- **A5 Enforce promoted-topic granularity in Phase 3/4 now.** Deferred: larger blast
  radius; Slice 1 establishes the contract; VG-13 is a later slice.

---

## 12. Key Architecture Decisions (ADRs)

- **ADR-0001**: Introduce `deepwiki-scale` as an opt-in strict-superset mode with a
  separate anti-compression gate module (see `adr/0001-deepwiki-scale-anti-compression-mode.md`).

---

## 13. Implementation Milestones

- **M1 (Slice 1, this delivery)**: `validate.py` mode + predicates; `anti_compression.py`;
  `__init__.py` exports; `normalize_plan` wiring; CLI + downstream option coherence;
  `tests/test_phase2_anti_compression.py`. **Definition: collapse fails, fan passes,
  existing suites green.**
- **M2**: Source-selection + Phase 3 evidence sufficiency at promoted-topic
  granularity (consume `promoted_topics[]`); VG-13 part 1.
- **M3**: Phase 4 generated coverage per promoted catalog topic; VG-13 part 2.
- **M4**: Non-live GPT-5.4-low worker E2E in `deepwiki-scale`; breadth dashboard vs
  benchmark; then (separately approved) a live run.

---

## 14. Test Strategy

Mapped to AC-S1…AC-S7 (PRD §11). Each defect code has a dedicated failing test and
the pass case has no diagnostics. Integration tests assert exit codes and artifact
presence/absence by mode. Determinism test compares serialized gate dicts across two
evaluations. Full-suite run proves non-regression.

---

## 15. Rollout / Rollback / Operations

- **Rollout**: opt-in; nobody is affected until `--coverage-mode deepwiki-scale` is
  used. Validate via the non-live worker path first.
- **Rollback**: remove the mode from CLI `choices` (or stop passing it); all other
  modes are untouched, so rollback is a no-op for existing runs.
- **Operations**: failures are self-describing (topic/page/family + measured vs
  required + remediation); the gate report records the exact policy enforced.

---

## 16. Risks, Open Questions & Failure Modes

- Risks Risk-S1…Risk-S4 (PRD §12). Open decisions OD-S1…OD-S4 require user sign-off
  before any live run; Slice 1 applies documented defaults and is non-live.
- Failure mode: a family-heavy catalog with few subsystems yields a low floor — the
  flat-plan check still fires, and FG-S1 (finer catalog) is the long-term fix.

---

## 17. Appendices

- **Glossary**: *promoted leaf topic* = `must`, non-family catalog topic that must own
  a leaf page; *leaf page* = non-provenance, non-overview planned page; *density cap* =
  max promoted leaf topics one leaf page may claim; *breadth floor* = Σ over families
  of ceil(promoted_leaf/cap).
- **Code seams**: `libs/coverage/{validate,page_planning,page_profiles,source_selection,
  obligations,traceability,__init__}.py`, new `libs/coverage/anti_compression.py`,
  `libs/commands/normalize_plan.py`, `cli.py`, `libs/evidence/{options,evidenced_coverage}.py`,
  `libs/writing/{options,grounded,packet,generated_coverage}.py`, plus later
  `evidence/evidenced_coverage.py`, `writing/generated_coverage.py`,
  `coverage/source_selection.py`, `coverage/traceability.py` (M2/M3).
- **References**: PRD (this slug), prior PRD/TDD (`deepwiki-coverage-expansion`), real
  run report `EXPANDED_REAL_RAGFLOW_GPT54_E2E_RESULT.md`.
