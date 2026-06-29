# DeepWiki Scale-Parity (Anti-Compression) — PRD (Final)

- Status: **Draft / ready for implementation of Slice 1**
- Phase relation: **Next phase of**, not replacement for,
  `docs/product-requirements/deepwiki-coverage-expansion/` (which stays unchanged).
- Benchmark policy: `ragflow-deepwiki.md` is a **comparator/dashboard only** — never
  source truth, evidence, or copied structure (see §13).
- Grounding legend: every requirement is tagged *(sourced)* = grounded in a read
  artifact or the real run, *(inferred)* = derived design judgment, *(open)* = an
  unresolved decision recorded in §12.

---

## 1. Executive Summary

The `expanded` coverage mode added the *mechanism* for source-derived,
hierarchical, profile-aware, evidence-backed DeepWiki-style coverage — and it works:
the real non-live RAGFlow GPT-5.4-low run passed all eight gates. But it is **not
DeepWiki-scale**. A 147-topic catalog with 94 high-signal (`must`) topics collapsed
into **21 flat pages and 42 topic-evidence requirements**, with whole 13-topic
families mapped 1:1 onto a single page and `parent_section_id` null everywhere.

The root cause is a single under-enforced rule: a catalog topic was treated as
"planned" the instant its id appeared in *any* page's `catalog_topic_ids[]`. A broad
page could therefore claim a dozen high-signal child topics for free, with no
obligation to give each its own page, its own required topic, its own TER, its own
evidence obligation, or its own generated-coverage row.

This phase closes that loophole. It introduces an opt-in, strict-superset coverage
mode (**`deepwiki-scale`**) and a **catalog promotion contract** plus
**anti-compression gates** that make it impossible for a 94-`must` catalog to pass as
21 flat pages. Breadth is enforced from the *source-derived catalog*, never from the
benchmark. The first delivered slice is the Phase 2 planning-time gate set that
deterministically fails the observed collapse; later slices push the same
promoted-topic granularity into source-selection, evidence sufficiency, and
generated coverage.

---

## 2. Problem Statement — why `expanded` passed but is not DeepWiki-scale

*(sourced: real run reports + `page_planning.py:_eval_catalog_coverage`)*

1. **Planning coverage was existential, not distributive.** `_eval_catalog_coverage`
   marks a topic *planned* if `topic_id ∈ some page.catalog_topic_ids[]`. One page
   can list 13 ids and satisfy 13 `must` topics. 94 topics → 21 pages all passed.
2. **No density ceiling.** Nothing bounded how many high-signal catalog topics a
   single leaf page may absorb, so families collapsed 1:1 onto one page each.
3. **No distributive TER obligation.** The topic-obligation gate validates the
   *shape* of each `required_topics[]` entry's TER, but nothing required **one TER
   per promoted catalog topic**. The run reached Phase 3 with 42 TERs for 94 `must`
   topics.
4. **Hierarchy was optional in practice.** The page-planning gate validates that a
   *declared* `parent_section_id` resolves and is acyclic, but never requires
   hierarchy to *exist*. The whole plan was flat.
5. **Breadth target M-07 was advisory.** The 45–70 page / 150–250 topic band was a
   success metric, not a gate; nothing failed a 21-page plan.
6. **Downstream granularity matched planning.** Evidenced and generated coverage are
   keyed on broad required topics / content blocks, so a compressed plan also passed
   Phase 3/4 by construction.

Net: the pipeline rewards a planner that lists many catalog ids on few broad pages.
DeepWiki scale requires the opposite — broad catalogs must *fan out* into many
evidence-backed leaf pages.

---

## 3. Goals & Non-Goals

### 3.1 Goals
- **G-S1** *(sourced)*: Make it deterministically impossible for a high-signal
  catalog to pass as a small flat plan. A 94-`must`, 13-family catalog compressed
  into 21 flat pages / 42 TERs must **fail** the new mode before Phase 3.
- **G-S2** *(sourced)*: Define a **source-derived catalog promotion contract** with
  explicit tiers (page, overview/index, required topic, optional/context, known gap)
  that decides which catalog topics become *blocking distributive* obligations.
- **G-S3** *(inferred)*: Enforce breadth, density, distributive TER coverage, and
  non-flat hierarchy from the **catalog**, not the benchmark.
- **G-S4** *(inferred)*: Carry promoted-topic granularity downstream as a data
  contract Phase 3 (source-selection/evidence) and Phase 4 (generated coverage) can
  consume in later slices.
- **G-S5** *(sourced)*: Preserve every existing mode (`baseline`, `enhancement`,
  `expanded`) and all strict validators byte-for-byte. New behavior is opt-in.
- **G-S6** *(sourced)*: Keep the non-live GPT-5.4-low worker path as the mandatory
  pre-live validation route; no billed provider calls without explicit approval.

### 3.2 Non-Goals
- **NG-S1**: Writing longer prose / inflating word count. Breadth is page/topic
  fan-out backed by evidence, not verbosity.
- **NG-S2**: Copying benchmark page counts, headings, structure, or prose as a
  target. The benchmark stays a dashboard.
- **NG-S3**: Changing Phase 3 retrieval determinism or adding LLM calls to any gate.
- **NG-S4**: Auto-healing / output patching. Gates fail loudly; only LLM-authored
  plan/claim artifacts may be repaired, bounded and audited.
- **NG-S5** *(this phase)*: Full DeepWiki-parity *generation*. This phase enforces
  the *plan/evidence/coverage contracts*; achieving the 45–70 page band on a live
  run is gated by source support and a separate approved live run.

### 3.3 Future Goals
- **FG-S1**: Tree-sitter/SCIP-grade catalog so subsystem topics are even finer.
- **FG-S2**: Promoted-topic-granular sampled quality checks after deterministic
  gates.

---

## 4. Users / Stakeholders
*(sourced + inferred)*

| Class | Role | Concern |
|---|---|---|
| Pipeline operator (the user) | Runs the non-live worker E2E, decides on live runs | Breadth is real and enforced; no surprise regressions to existing modes; no billed calls |
| Future implementation agent | Builds later slices | Self-contained PRD/TDD; stable data contracts |
| Coverage gate maintainers | Own `libs/coverage/*` | Deterministic, read-only, testable gates that share one taxonomy |
| Release owner | Signs off high-risk breadth families and policy thresholds | Tunable, auditable policy; explicit open decisions |

---

## 5. Problem / Vision

**Current state:** `expanded` proves the mechanism but rewards compression.
**Desired state:** an opt-in `deepwiki-scale` mode where the source-derived catalog
*drives* the plan's breadth — every promoted catalog topic earns its own
leaf page, required topic, TER, evidence obligation, and (in later slices) generated
coverage row — and any attempt to consolidate many high-signal topics onto a few
flat pages fails closed with actionable diagnostics.

---

## 6. Scope

### 6.1 In scope (this PRD)
- A new opt-in coverage mode `deepwiki-scale` (strict superset of `expanded`).
- A catalog **promotion contract** (tiers) computed deterministically from the
  catalog.
- Phase 2 **anti-compression gates**: leaf-page density cap, distributive
  leaf-page coverage, distributive TER coverage per promoted topic, family-split,
  non-flat-hierarchy, and a catalog-derived breadth floor.
- A plan-time **promoted-topics data contract** emitted for downstream consumption.
- CLI acceptance of the new mode end-to-end (no pipeline breakage).

### 6.2 In scope (later slices, specified here, built later)
- Source-selection and evidence sufficiency evaluated at promoted-topic granularity.
- Generated coverage proving each promoted catalog topic is rendered with valid
  local citations.

### 6.3 Out of scope
- Benchmark-derived targets/structure; Phase 3 determinism changes; output patching;
  live billed runs.

### 6.4 Deferred / first-slice boundary
- **Slice 1 (this delivery):** Phase 2 promotion contract + anti-compression gates +
  data contract + CLI wiring + tests. Downstream phases treat `deepwiki-scale` as
  `expanded` until their slices land.

---

## 7. User / Product Requirements (MoSCoW)

| ID | Requirement | Priority | Grounding |
|---|---|---|---|
| UR-S1 | Provide an opt-in `deepwiki-scale` coverage mode, a strict superset of `expanded`, that adds anti-compression enforcement. | Must | sourced |
| UR-S2 | Compute a deterministic, source-derived **promotion contract** assigning each catalog topic a tier: `page` (blocking leaf), `overview` (blocking family/index), `optional` (should/could), or `known_gap` (explicitly deferred). | Must | sourced |
| UR-S3 | Require every `page`-tier (promoted leaf) topic to be planned on its **own non-overview leaf page** — a broad/overview page listing it does NOT satisfy it. | Must | sourced |
| UR-S4 | Cap the number of promoted leaf topics a single leaf page may claim (density ceiling); overview/index pages are exempt but their listings never count as leaf coverage. | Must | sourced |
| UR-S5 | Require **≥1 topic-evidence requirement (TER) per promoted leaf topic**, keyed by `catalog_topic_id`. | Must | sourced |
| UR-S6 | Require high-signal families above a split threshold to fan out into **≥ ceil(n / density-cap) leaf pages**, hierarchically linked (non-flat). | Must | sourced |
| UR-S7 | Enforce a **catalog-derived breadth floor** on leaf-page count; a flat 21-page plan for a 94-`must` catalog must fail. | Must | sourced |
| UR-S8 | Emit a plan-time **`promoted_topics[]` data contract** (topic id, family, tier, has-TER, leaf pages, status) for Phase 3/4 to consume in later slices. | Must | inferred |
| UR-S9 | Evaluate source-selection and Phase 3 evidence sufficiency at **promoted-topic granularity** (later slice). | Should | inferred |
| UR-S10 | Validate generated coverage **per promoted catalog topic** with valid local citations (later slice). | Should | inferred |
| UR-S11 | Keep `baseline`/`enhancement`/`expanded` and all strict validators unchanged; `deepwiki-scale` is the only behavior change. | Must | sourced |
| UR-S12 | Allow explicit, source-derived **known-gap deferral** of a promoted topic instead of forcing invented pages/claims. | Must | sourced |
| UR-S13 | Make all new gates **deterministic, LLM-free, network-free, read-only**; fail closed with actionable remediation pointing back at the LLM-authored plan. | Must | sourced |
| UR-S14 | Make breadth thresholds a **single injectable policy** object (tunable, auditable), not scattered magic numbers. | Must | inferred |
| UR-S15 | Keep the non-live GPT-5.4-low worker path the mandatory pre-live validation route. | Must | sourced |

---

## 8. Business Rules

- **BR-S1**: A catalog topic is **promoted (blocking)** iff `priority == "must"` and
  it is not explicitly deferred via a source-derived `known_gaps[]` entry naming its
  `topic_id`. *(sourced)*
- **BR-S2**: Promotion **tier** is source-derived from `topic_kind`: `family` →
  `overview` tier (satisfied by an index/overview page); non-family (subsystem) →
  `page` tier (a leaf obligation). `should`/`could` → `optional`. *(inferred — see
  OD-S1)*
- **BR-S3**: A page with `page_profile ∈ overview_profiles` is an **index/overview
  page**: exempt from the density cap, and its `catalog_topic_ids[]` **do not** count
  as leaf coverage for any topic. *(sourced)*
- **BR-S4**: A broad/parent page never satisfies a child subsystem (`page`-tier)
  topic. Leaf coverage requires a non-overview leaf page. *(sourced — extends prior
  BR-03)*
- **BR-S5**: Breadth, density, family-split, and floor thresholds derive only from
  the **catalog**; the benchmark is never an input to any gate. *(sourced)*
- **BR-S6**: Every gate is **upstream prevention by loud failure** — it never edits,
  synthesizes, downgrades, or invents plan content. *(sourced)*
- **BR-S7**: Default breadth policy (tunable, OD-S2): `max_promoted_topics_per_leaf_page
  = 4`, `family_split_threshold = 6`, breadth floor = `Σ_family ceil(promoted_leaf /
  4)`. These are conservative defaults chosen so the observed collapse fails and a
  reasonable fanned-out plan passes; they require release-owner sign-off before live
  use. *(open → see §12)*

---

## 9. Quality Attributes

- **QR-S1 Determinism**: identical inputs → byte-identical gate artifacts; no clock,
  randomness, or network. *(sourced)*
- **QR-S2 Isolation**: new gates are read-only; no plan mutation; no import-time side
  effects; thresholds injected via a policy object. *(sourced — Python HARD-RULES)*
- **QR-S3 Non-regression**: existing `baseline`/`enhancement`/`expanded` runs and
  their tests are unaffected. *(sourced)*
- **QR-S4 Diagnosability**: every failure names the offending topic/page/family,
  the measured vs required number, and a remediation that targets the LLM-authored
  Phase 2 plan/prompt/schema. *(sourced)*
- **QR-S5 Composability**: the new mode shares the existing lane/profile/catalog
  taxonomy so producer and consumer gates cannot drift. *(sourced)*
- **QR-S6 Tunability/Auditability**: policy thresholds are surfaced in the gate
  report so a run records exactly what it enforced. *(inferred)*

---

## 10. Data / Interface Requirements

### 10.1 Inputs (unchanged artifacts, read-only)
- `derived/topic-catalog.json` (`deepwiki-topic-catalog-v1`): topics with
  `topic_id`, `parent_topic_id`, `family`, `topic_kind`, `priority`,
  `signal_strength`, `suggested_page_profile`, `status`.
- `plans/section-plans.jsonl` (`phase2-section-plan-v1`): normalized sections with
  `section_id`, `section_role`, `page_profile`, `parent_section_id`,
  `catalog_topic_ids[]`, `required_content_blocks[]`, `required_topics[]`,
  `topic_evidence_requirements[]` (each with `catalog_topic_id`, `content_block_id`),
  `known_gaps[]`.
- `plans/document-plan.json`.

### 10.2 New output artifact (Slice 1)
- `plans/anti-compression-gate.json` (new schema `phase2-anti-compression-v1`) and
  `plans/anti-compression-report.md`. Carries: policy snapshot; per-promoted-topic
  rows (`topic_id`, `family`, `tier`, `has_ter`, `leaf_pages[]`, `status`,
  `defects[]`); per-family breadth rows; counts; flat-hierarchy flag; diagnostics;
  pass/fail + exit code. The `promoted_topics[]` block is the **downstream data
  contract** (UR-S8).

### 10.3 CLI
- `normalize-plan --coverage-mode deepwiki-scale` runs all `expanded` gates **plus**
  the anti-compression gate.
- `plan-repair`, `retrieve-evidence`, `write-wiki`, `validate-coverage` accept
  `deepwiki-scale` and, in Slice 1, behave exactly as `expanded` (documented
  superset; promoted-topic granularity arrives in later slices).

---

## 11. Acceptance Criteria & Validation Gates

Gate naming continues the prior series (VG-01…VG-10). New gates VG-11…VG-13.

| Gate | Owner phase | Checks | Exit |
|---|---|---|---|
| **VG-11 Promotion-contract gate** | Phase 2 | Every catalog topic is assigned a tier; promotion is deterministic and source-derived; `promoted_topics[]` emitted. | 3 on internal inconsistency; 0 pass |
| **VG-12 Anti-compression gate** | Phase 2 | (a) each `page`-tier topic on its own non-overview leaf page; (b) leaf-page density ≤ cap; (c) ≥1 TER per `page`-tier topic; (d) over-threshold families split into ≥ ceil(n/cap) linked leaf pages; (e) plan not flat when ≥ threshold families have promoted topics; (f) leaf-page count ≥ catalog breadth floor. | 3 fail / 0 pass |
| **VG-13 Promoted-topic downstream gate** | Phase 3/4 (later slices) | Source-selection, evidence sufficiency, and generated coverage evaluated per promoted catalog topic. | 3 / 5 / 0 |

**Binary acceptance criteria:**

| AC | Statement | Method |
|---|---|---|
| AC-S1 | A `deepwiki-scale` run over a fixture mirroring the real collapse (13-topic family → 1 leaf page, 94 `must` → 21 flat pages, 42 TERs) returns FAIL with exit 3 and emits ≥ one of `leaf_page_overloaded_with_promoted_topics`, `promoted_topic_missing_topic_evidence_requirement`, `source_catalog_plan_is_flat`, `high_signal_family_not_split_into_child_pages`, `plan_breadth_below_catalog_floor`. | automated unittest |
| AC-S2 | A fanned-out fixture (each promoted leaf topic on its own ≤cap leaf page, with a TER, hierarchically linked, ≥ floor pages) returns PASS exit 0. | automated unittest |
| AC-S3 | An overview/index page listing many promoted topic ids passes **only when** each of those topics also has its own non-overview leaf page + TER; if a topic appears only on the overview page it fails with `promoted_topic_not_on_leaf_page`. | automated unittest |
| AC-S4 | Running the same fixtures under `baseline` and `expanded` does **not** run the anti-compression gate (report-only / absent); existing `expanded` and `enhancement` test suites pass unchanged. | automated unittest + full suite |
| AC-S5 | All gates are deterministic: two runs over identical inputs produce identical `anti-compression-gate.json`. | automated unittest |
| AC-S6 | `retrieve-evidence`/`write-wiki`/`plan-repair`/`validate-coverage` accept `--coverage-mode deepwiki-scale` without error (Slice 1 = expanded-equivalent downstream). | automated unittest |
| AC-S7 | A promoted topic explicitly deferred via a source-derived `known_gaps[]` entry is tier `known_gap` and does not block. | automated unittest |

---

## 12. Risks, Assumptions & Open Decisions

### Risks
- **Risk-S1**: Over-strict thresholds force filler pages. *Mitigation*: thresholds
  are an injectable, auditable policy; defaults chosen conservatively; known-gap
  deferral always available (UR-S12).
- **Risk-S2**: A catalog whose topics are mostly family-level (few subsystems) yields
  a low floor and weak enforcement. *Mitigation*: track subsystem granularity in the
  catalog (FG-S1); the floor scales with promoted *leaf* topics, and the flat-plan
  check still fires.
- **Risk-S3**: Downstream "treat deepwiki-scale as expanded" in Slice 1 could mask a
  later contract mismatch. *Mitigation*: VG-13 specified now; data contract emitted
  now; later slices add enforcement, not new artifacts.
- **Risk-S4**: Benchmark leakage while chasing scale. *Mitigation*: BR-S5 — benchmark
  is never a gate input; quarantine rules §13.

### Assumptions
- **A-S1** *(medium)*: `topic_kind == "family"` reliably distinguishes index-level
  from leaf topics in the catalog. (Confirmed by the real catalog's 13 families /
  134 subsystems.)
- **A-S2** *(high)*: `priority == "must"` is the correct promotion signal (matches the
  prior gate's `_BLOCKING_PRIORITY`).
- **A-S3** *(medium)*: `page_profile == "overview"` is the only index profile by
  default; tunable via policy `overview_profiles`.

### Open Decisions (require user sign-off)
- **OD-S1** *(resolves prior OD-02)*: Promotion threshold = `priority "must"`, tier by
  `topic_kind`. **Proposed default; confirm or supply a richer signal mix
  (signal_strength, source_signal count).**
- **OD-S2** *(resolves prior OD-03)*: Default breadth policy = cap 4 / split-threshold
  6 / floor `Σ ceil(promoted_leaf/4)`. **Proposed; confirm numbers before any live
  run.** These make the real 94-`must` catalog require ≈24+ leaf pages, in the
  neighborhood of the prior 45–70 band once subsystem leaves and optional topics are
  added.
- **OD-S3**: Which high-risk families (e.g. `sandbox-executor`, `auth-admin-health`)
  require human sign-off before live release (carries prior OD-05 forward).
- **OD-S4**: Whether `deepwiki-scale` should eventually become the default for
  source-derived runs or stay opt-in (carries prior OD-01 forward).

---

## 13. Benchmark Quarantine Rules
*(sourced — carries prior G-06/UR-12/VG-09 forward, unchanged)*

- `ragflow-deepwiki.md` is **comparison-only**. No benchmark-derived required topics,
  headings, evidence ids, citations, page structure, or prose may enter any catalog,
  plan, evidence, or generated artifact.
- Breadth thresholds derive from the **source catalog**, never the benchmark page
  count. The benchmark may appear only in a separate breadth *dashboard*.
- The benchmark's ~899 headings / ~74 page-like headings are context for *why* breadth
  matters, never a copy target.

---

## 14. Success Metrics (with hard anti-compression criteria)

| ID | Metric | Target | Hard? |
|---|---|---|---|
| M-S1 | Promoted leaf topics on their own non-overview leaf page | 100% (else FAIL) | **Hard gate (VG-12a)** |
| M-S2 | Leaf-page density | ≤ policy cap (default 4) promoted leaf topics/leaf page | **Hard gate (VG-12b)** |
| M-S3 | TER per promoted leaf topic | ≥ 1 (else FAIL) | **Hard gate (VG-12c)** |
| M-S4 | High-signal family fan-out | ≥ ceil(promoted_leaf/cap) linked leaf pages per over-threshold family | **Hard gate (VG-12d)** |
| M-S5 | Hierarchy | non-flat when ≥ threshold families have promoted topics | **Hard gate (VG-12e)** |
| M-S6 | Leaf-page breadth floor | actual leaf pages ≥ catalog floor | **Hard gate (VG-12f)** |
| M-S7 | Regression | existing modes/validators unchanged | Hard (test suite) |
| M-S8 | Breadth neighborhood (carries M-07) | when source support exists, ≈45–70 pages / 150–250 required topics | Soft dashboard — *not* benchmark-copied |
| M-S9 | Benchmark leakage | 0 benchmark-derived ids/headings/prose | Hard (VG-09) |

**Anti-compression acceptance example (the bar):** the exact real-run shape — 147
catalog topics / 94 `must` / 13 families compressed into 21 flat pages and 42 TERs —
**must fail** `deepwiki-scale`. A plan that fans the same catalog into linked leaf
pages (each promoted topic with its own page + TER, ≤cap density, ≥ floor pages)
**must pass**.

---

## 15. Relation to the Previous PRD

This PRD is the **next phase**, not a replacement. It inherits and does not modify:
G-01…G-06, UR-01…UR-15, BR-01…BR-04, VG-01…VG-10, all `deepwiki-*-v1` schemas, and the
`baseline`/`enhancement`/`expanded` modes. It **resolves** prior open decisions OD-02
(promotion threshold) and OD-03 (page/topic target) with concrete, tunable defaults,
and it **upgrades** prior advisory M-07 into hard, catalog-derived anti-compression
gates. The previous PRD/TDD directories are preserved unchanged.
