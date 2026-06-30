# ADR-0001 — Source-derived Phase 4 depth budget for the grounded claim plan

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** Writer (assembler) + Approver (validator), TDD phase series
- **Supersedes:** none
- **Related:** `deepwiki-scale-core-fanout` ADR-0001 (core expanded breadth gates);
  `deepwiki-scale-parity-next-phase` ADR-0001 (anti-compression mode)

## Context

The `expanded` path now enforces source-derived **breadth** (anti-compression); the latest
real RAGFlow E2E shows full breadth coverage (56 sections, 169/169 required topics, 82/82
promoted leaf topics) but shallow **depth** (~530 words and ~4 headings per section, ~7.3
claims/page, 45,038 words vs a ~98,271-word comparison-only benchmark). The grounded
renderer turns one claim into one paragraph and one required topic into one `###` heading,
and no gate fails a fanned-out-but-shallow plan. Coverage was modeled existentially ("is the
topic present?") rather than distributively ("does it ground enough claims for its mapped
evidence?").

## Decision

Add a deterministic, **source-derived per-section depth budget** to the Phase 4 grounded
claim-plan path, mirroring the Phase 2 anti-compression module:

1. A new pure module `libs/writing/depth_budget.py` with a frozen, injectable `DepthPolicy`,
   a `SectionDepthBudget` derived from each sufficient required topic's Phase 3
   mapped-evidence density (`topic_target = clamp(ceil(mapped/evidence_per_claim), floor,
   cap)`), a deterministic `evaluate_plan_depth`, and `render_depth_budget_lines` for the
   prompt.
2. An **optional, additive** depth gate in `claim_plan.validate_claim_plan(...,
   depth_budget=None)` that fails a shallow plan with precise per-topic/per-block/per-section
   diagnostics — running after the existing grounding checks, never relaxing them.
3. Prompt hardening so the planner is shown the per-topic targets and asked to ground enough
   claims; depth metrics recorded in the per-section grounded audit block.
4. Active **only** for the expanded grounded path; `baseline`/`enhancement` unchanged;
   `deepwiki-scale` remains a behavior-identical alias.

## Consequences

**Positive:** a shallow-but-covered wiki can no longer pass as scale parity; depth is now a
verifiable, source-derived contract; the gate is benchmark-quarantined, deterministic, and
auditable; it reuses the proven breadth-gate shape, so the same maintainers reason about
both consistently.

**Negative / accepted:** a previously-passing fanned-out-but-shallow expanded grounded plan
now fails (intended correction). The exact `DepthPolicy` defaults are seeds requiring
release-owner sign-off before any billed live run. Heading-density depth (content-block
`####`) is staged to M2.

**Neutral:** no new service, store, migration, or CLI surface; rollback is a one-line guard.

## Alternatives considered

Flat per-section word/claim minimum (padding risk); benchmark-derived targets (quarantine
violation); output patching / heal loops (forbidden); a post-render word gate (no actionable
planner feedback); a new `coverage/` gate (wrong phase). See `working/14-alternatives-tradeoffs.md`.
