# Technical Design — DeepWiki Scale: Depth Parity

| | |
|---|---|
| Slug | `deepwiki-scale-depth-parity` |
| Status | Final — validated (non-live) |
| Weight | Standard |
| Audience | Phase 4 writing maintainers, coverage-gate maintainers, future implementation agents, pipeline operator, release owner |
| Phase relation | Next phase after `deepwiki-scale-core-fanout` (commit `35d5d6f`); builds on, does not replace, the breadth anti-compression work |
| Author role | TDD phase series (phases 1–6); writer ≠ approver simulated in finalization |
| Comparator isolation | `ragflow-deepwiki.md` is comparison-only — never evidence, prompt seed, headings, prose, structure, or generated required topics |
| Grounding | *(sourced)* code/run artifact, *(inferred)* design judgment, *(open)* unresolved decision |

## Table of contents

1. Summary
2. Context & background
3. Goals, non-goals & future goals
4. Success metrics
5. Requirements, constraints, assumptions & dependencies
6. Architecture overview
7. Detailed design
8. Interfaces, data contracts & behavior
9. Non-functional requirements & quality attributes
10. Alternatives considered & trade-offs
11. Key architecture decisions
12. Implementation plan, milestones & test plan
13. Rollout, migration, rollback & operations
14. Risks, open questions & failure modes
15. Appendices, glossary & references

---

## 1. Summary

The prior phase made the `expanded` path enforce source-derived **breadth**
(anti-compression): a high-signal catalog can no longer collapse onto a few flat pages. The
latest real RAGFlow non-live E2E proves breadth is solved — 56 sections, 169/169 required
topics, 82/82 promoted leaf topics, 96/96 content blocks. *(sourced)*

But the generated wiki is far below DeepWiki **depth**: ~530 words and ~4 headings per
section, ~7.3 claims/page, 45,038 words against a ~98,271-word comparison-only benchmark.
The grounded renderer turns one claim into one paragraph and one required topic into one
`###` heading, and **no gate fails a fanned-out-but-shallow plan**. *(sourced)*

This phase adds a deterministic, **source-derived per-section depth budget** to the Phase 4
grounded claim plan. Each sufficient required topic must ground claims proportional to the
Phase 3 evidence actually mapped to it (`topic_target = clamp(ceil(mapped_evidence /
evidence_per_claim), floor, cap)`); a shallow plan fails before assembly with precise
diagnostics; the planner is shown the budget; and depth metrics are recorded per section.
Strict grounding, citation validation, benchmark quarantine, and the deterministic LLM-free
Phase 3 are all preserved. It is opt-in (expanded grounded mode), off by default at the
command level, injectable, and reversible. *(inferred)*

## 2. Context & background

*(sourced)* The DeepWiki pipeline is Phase 1 (decompose) → Phase 2 (plan + coverage gates) →
Phase 3 (deterministic evidence retrieval) → Phase 4 (grounded writing). `expanded` is the
core DeepWiki-scale hierarchical mode. Its grounded sub-path (`--grounded-claim-plan`) asks
the model for a structured **claim plan**, validates it deterministically against a
per-section **token bank**, and renders the Markdown itself: one claim → one paragraph
(`_skeleton_paragraph_template`, `_render_claim_paragraph`), one sufficient required topic →
one `###` heading (`render_section`), content blocks → no new heading
(`_derive_covered_content_blocks`).

The latest real run (`20260629-201218-…-35d5d6f`) PASSED every gate with strong breadth yet
shallow depth (section files 139–474 words, ≤6 headings; e.g. `017-memory-implementation.md`
renders each required/catalog topic as a single `###` heading with one paragraph). The
previous TDD defined the finish line as breadth only (`>= 36 pages / >= 94 required topics`)
and explicitly scoped out longer prose / parity generation.

**Root cause:** coverage was modeled **existentially** ("is each topic present?"). Depth
needs a **distributive density** model ("does each topic ground enough claims for its mapped
evidence?") — the direct analogue of how the Phase 2 anti-compression gate replaced
existential page-planning with a distributive breadth contract.

## 3. Goals, non-goals & future goals

| # | Goal | Non-goal |
|---|---|---|
| G1 | Source-derived per-section depth budget proportional to Phase 3 mapped-evidence density. | Any target derived from `ragflow-deepwiki.md`. |
| G2 | Claim-plan validator fails a shallow plan with precise diagnostics. | Output patching, padding, or a heal/retry loop. |
| G3 | Prompt carries the depth budget; system instruction asks for enough claims. | Benchmark numbers/headings/prose in the prompt. |
| G4 | Depth metrics in the per-section grounded audit block. | A new persisted artifact schema or doc rewrite. |
| G5 | Injectable, bounded `DepthPolicy`. | Scattered magic numbers; unbounded per-topic demand. |
| G6 | `baseline`/`enhancement` unchanged; depth applies only to expanded grounded. | Reintroducing `deepwiki-scale` as a separate product (stays an alias). |
| G7 | Strict grounding, citation validation, benchmark quarantine, deterministic Phase 3 preserved. | Weakening any existing validator. |

**Future goals:** content-block-level `####` heading depth (M2); a document-level depth
dashboard (comparison-only); a separately-approved billed live run confirming the planner
reaches the budget on the real catalog (M3).

## 4. Success metrics

- **SM1** A plan that names every sufficient required topic with a single claim but leaves
  most of its Phase 3 mapped evidence unused **fails** (`claim_plan_topic_underfilled`).
- **SM2** A plan grounding claims proportional to mapped-evidence density **passes**.
- **SM3** A topic with exactly one mapped evidence id passes with one claim (satisfiable, no
  padding) — the existing `ops` expanded grounded command E2E still passes.
- **SM4** `baseline`/`enhancement` never compute/enforce the budget; full suite green.
- **SM5** Every threshold/target derives only from catalog/plan/evidence; comparator never
  read; identical inputs → byte-identical budget/report.
- **SM6** The grounded audit records the budget + measured per-topic and total claim counts;
  a failing plan's diagnostics name topic, mapped-evidence count, measured, and required.
- **SM7** `DepthPolicy` is a frozen, injectable, bounds-validated dataclass; the effective
  policy is serialized in the budget/report.

## 5. Requirements, constraints, assumptions & dependencies

**Functional** *(see `working/06-requirements-constraints.md`)*: FR1 new
`libs/writing/depth_budget.py` (policy + budget + gate + render); FR2 source-derived per-topic
target from mapped-evidence density; FR3 optional additive depth gate in
`validate_claim_plan`; FR4 prompt + system-instruction hardening; FR5 expanded-grounded-only
derivation + threading + depth audit; FR6 deterministic, read-only.

**Constraints:** C1 no live calls; C2 no validator weakened; C3 Phase 3 protected spec
untouched / LLM-free; C4 benchmark quarantine; C5 baseline/enhancement compatible; C6 Python
HARD-RULES (typing, no mutable defaults, no import-time side effects, dependency injection,
narrow exceptions, layered imports, clean tree, `uv run`); C7 no output patching / no generic
heal loops.

**Assumptions:** A1 Phase 3 supplies precise `mapped_evidence_ids[]` per sufficient required
topic *(sourced: `build_topic_obligations`)*; A2 a topic mapped to N evidence ids can ground
N grounded claims *(inferred)*; A3 the DeepWiki-scale path uses `--grounded-claim-plan`
*(sourced: real E2E)*.

**Dependencies:** D1 reads only in-memory Phase 4 data (packet, obligations, token bank);
no new file/dep. D2 `EXPANDED_COVERAGE_MODES` decides when the budget is active.

## 6. Architecture overview

No new services. A new pure module sits beside the claim-plan machinery and is orchestrated
by the per-section grounded loop — mirroring how the Phase 2 anti-compression gate sits beside
page-planning.

```
write-wiki --coverage-mode expanded --grounded-claim-plan
  run(): packet + token_bank + topic_obligations + block_obligations
     │
     ▼ NEW (expanded grounded only)
  depth_budget.derive_section_depth_budget(obligations, block_obligations,
        allowed_evidence_ids, token_count, source_handle_count, policy)
     ├─ build_claim_plan_prompt(..., depth_budget)        ◀ prompt carries depth guidance
     ▼
  grounded.generate_grounded_section(..., depth_budget)
     │  provider -> claim plan (LLM)
     ▼
  claim_plan.validate_claim_plan(..., depth_budget)       ◀ NEW additive depth gate
     │   existing grounding checks  +  evaluate_plan_depth(budget, claims)
     ├─ shallow -> violations -> (bounded audited re-prompt if live) -> fail-closed (exit 5)
     ▼ pass
  render_section(...) [unchanged]  ->  validate_section_draft(...) [unchanged]
  grounded_meta["depth"] = budget + measured claim counts ◀ NEW audit metric
```

**Layering (HARD-RULES):** `depth_budget.py` imports only stdlib (`math`, `dataclasses`);
`claim_plan.py`/`grounded.py`/`__init__.py` import it; nothing imports the comparator.

## 7. Detailed design

### 7.1 New module `libs/writing/depth_budget.py` *(inferred; pure, deterministic)*

Mirrors `libs/coverage/anti_compression.py`.

- `DEPTH_BUDGET_SCHEMA_VERSION = "phase4-depth-budget-v1"`.
- Defect codes: `CODE_TOPIC_UNDERFILLED`, `CODE_SECTION_UNDERFILLED`.
- **Policy (dependency injection; frozen; bounds-validated):**

```python
@dataclass(frozen=True)
class DepthPolicy:
    evidence_per_claim: int = 1               # ~1 grounded claim per mapped evidence id
    min_claims_per_required_topic: int = 1    # floor: a 1-evidence topic stays satisfiable
    max_claims_per_required_topic: int = 8    # cap: a richly-mapped topic cannot demand unboundedly
    min_section_claims: int = 1               # backstop floor
    def topic_target(self, mapped_count: int) -> int:
        # clamp(ceil(mapped_count / evidence_per_claim), floor, cap)
```

`topic_target` is the single place the per-topic number is computed, so planner guidance and
gate enforcement derive identically (the breadth budget/gate discipline).

- **Result model:** `TopicDepthTarget`, `SectionDepthBudget`, `DepthShortfall`,
  `PlanDepthReport` (each `to_dict()`).
- **API:** `derive_section_depth_budget(*, section_id, obligations,
  content_block_obligations, allowed_evidence_ids, token_count, source_handle_count,
  policy=None)`; `evaluate_plan_depth(budget, claims)`; `render_depth_budget_lines(budget)`.
- Per-topic `min_claims = policy.topic_target(len(distinct mapped_evidence_ids))`; section
  floor `= max(policy.min_section_claims, Σ topic targets)`. Empty obligations → no targets
  (no spurious pressure). **Scope:** the depth gate enforces per-topic claim density + the
  section floor. Content-block *coverage* stays the existing downstream generated-coverage
  gate's job — the depth gate does not duplicate or preempt it; `content_block_obligations`
  feeds only an informational count (see ADR-0001 / repair-log R6).

### 7.2 Changed `libs/writing/claim_plan.py` *(sourced seam)*

`validate_claim_plan(..., depth_budget=None)`: after the existing grounding/required-topic
checks, when `depth_budget is not None`, append the shortfalls from
`evaluate_plan_depth(depth_budget, norm_claims)` as violations. `ok = not violations`
unchanged, so a shallow plan fails. `None` → byte-identical to today. `build_claim_plan_prompt`
/ `build_claim_plan_rewrite_prompt` gain `depth_budget=None`: insert
`render_depth_budget_lines(...)` and harden `CLAIM_PLAN_SYSTEM_INSTRUCTION` ("ground enough
claims for the evidence; do not pad").

### 7.3 Changed `libs/writing/grounded.py` + `__init__.py` *(sourced seam)*

`generate_grounded_section(..., depth_budget=None)` threads the budget into both
`validate_claim_plan` calls and the rewrite prompt, and adds `grounded_meta["depth"]`.
`run()` computes `depth_budgets[sid]` for the expanded grounded path and passes it to the
prompt build and the section loop. Non-expanded / non-grounded runs compute nothing.

### 7.4 Explicitly not changed this slice

`render_section`, `_render_claim_paragraph`, `_derive_covered_content_blocks`, and the
generated-coverage evaluators are untouched — more claims already render as more paragraphs.
Content-block `####` heading rendering is M2 (bounds blast radius on the content-block-coverage
evaluator).

## 8. Interfaces, data contracts & behavior

See `working/11-interfaces.md` and `working/10-data-design.md`. Key points:

- Every new parameter is optional with a behavior-preserving default (`None`).
- `phase4-depth-budget-v1`: `SectionDepthBudget` (policy + counts + per-topic targets +
  section floor) and `PlanDepthReport` (status + measured + shortfalls with measured-vs-required
  detail). An **additive** `grounded.depth` audit field carries the budget + measured counts.
- **Behavior matrix:** depth budget computed/enforced **only** for `coverage_mode ∈
  {expanded, deepwiki-scale}` AND `--grounded-claim-plan`. All other combinations unchanged.
- **Failure path:** shallow plan → depth violations → (≤ `max_rewrite_attempts` bounded
  audited re-prompt, live only) → fail-closed `WritingValidationFailure` (exit 5), naming the
  under-filled topics. Plan never mutated; no output patched. Depth runs **after** grounding
  checks, so it never masks a grounding violation.
- **Edge cases:** 1-mapped-evidence topic → target 1 → single claim passes; no-obligation
  section → cannot fail on depth; richly-mapped topic → target capped.

## 9. Non-functional requirements & quality attributes

| Attribute | Definition | How met |
|---|---|---|
| Determinism | identical inputs → byte-identical budget/report | no clock/random; sorted iteration; derived purely from obligations/packet/token bank |
| Source-fidelity | targets derive from source, never benchmark | `depth_budget.py` stdlib-only; comparator never read |
| Non-regression | baseline/enhancement + existing expanded pass cases unchanged | `depth_budget` optional; expanded-grounded-only |
| Validator strength | no existing check relaxed | depth additive, runs after grounding checks |
| Satisfiability | target never exceeds evidence available | `clamp(ceil(mapped/epc), floor, cap)`; 1-mapped → 1 claim |
| Auditability | run records enforced depth + result | policy serialized; `grounded.depth` block |
| Bounded | richly-mapped topic cannot explode | `max_claims_per_required_topic` cap |
| Safety | read-only; no mutation, patch, or heal | report-only `evaluate_plan_depth`; existing bounded re-prompt only |

See `working/13-quality-attributes.md` for the per-attribute verification.

## 10. Alternatives considered & trade-offs

Chosen: per-topic target from **mapped-evidence density** (source-derived, satisfiable).
Rejected: flat word/claim minimum (padding); benchmark-derived targets (quarantine); output
patching / heal loops (forbidden, non-deterministic); post-render word gate (no planner
feedback); a `coverage/` gate (wrong phase). Deferred: content-block `####` headings (M2,
blast radius). See `working/14-alternatives-tradeoffs.md`.

**Accepted trade-off:** a previously-passing fanned-out-but-shallow expanded grounded plan now
fails — the intended correction, analogous to the prior phase's breadth trade-off. Off by
default (baseline), opt-in via expanded + grounded, injectable, one-line rollback.

## 11. Key architecture decisions

**ADR-0001 (Accepted)** — Source-derived Phase 4 depth budget for the grounded claim plan;
see `adr/0001-source-derived-phase4-depth-budget.md`.

## 12. Implementation plan, milestones & test plan

**M1 (this slice):** `depth_budget.py`; `validate_claim_plan` + prompt wiring; `grounded.py` +
`__init__.py` threading + depth audit; `tests/test_phase4_depth_budget.py`. **Done =** shallow
fails, detailed passes, single-evidence passes, existing suites green, static checks clean,
protected spec unchanged. **M2:** content-block `####` heading depth + doc-level dashboard.
**M3:** separately-approved billed live run + `DepthPolicy` sign-off.

Test traceability maps every FR/SM to a test in `working/16-test-traceability.md`. No
live-model evidence is claimed this slice.

## 13. Rollout, migration, rollback & operations

- **Rollout:** off by default (`baseline`); only expanded + `--grounded-claim-plan` affected;
  staged behind non-live tests; a billed run is separately approved (M3).
- **Migration:** none (no persisted schema change); the `grounded.depth` field is additive.
- **Rollback:** one-line guard — stop computing/passing `depth_budget`; the module + optional
  params are inert without it.
- **Operations:** loud, actionable per-topic diagnostics (measured vs required vs
  mapped-evidence count); the `grounded.depth` audit shows why a section passed; tuning via
  the injectable `DepthPolicy`. See `working/17-rollout-ops-risk.md`.

## 14. Risks, open questions & failure modes

Risks and mitigations in `working/17-rollout-ops-risk.md` (policy too strict/lenient → target
tracks mapped-evidence density + injectable + sign-off; planner cannot reach budget →
fail-closed, no padding; padding temptation → grounding validators unchanged + "do not pad"
remediation; benchmark leakage → stdlib-only module + prompt assertion).

- **OD1 (open):** `DepthPolicy` default values — release-owner sign-off before any billed run.
- **OD2 (open):** M2 heading-depth rendering approach, revisited after M3 measurement.

## 15. Appendices, glossary & references

- **Depth budget** — deterministic, source-derived per-section claim-density targets (per
  required topic and content block) plus a section floor; the Phase 4 analogue of the Phase 2
  breadth budget.
- **Per-topic claim target** — `clamp(ceil(mapped_evidence / evidence_per_claim),
  min_claims_per_required_topic, max_claims_per_required_topic)`.
- **Existential vs distributive coverage** — "is the topic present?" vs "does it ground enough
  claims for its mapped evidence?".
- **Compatibility alias** — `deepwiki-scale`: behavior-identical to `expanded`.
- **References:** `working/*.md`, `adr/0001-…md`, `source-index.md`, `definition-of-done.json`;
  prior `deepwiki-scale-core-fanout` and `deepwiki-scale-parity-next-phase` TDDs; the real run
  report `EXPANDED_REAL_RAGFLOW_GPT54_E2E_RESULT.md`; comparison-only `ragflow-deepwiki.md`.
