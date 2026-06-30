# Context & Problem — deepwiki-scale-depth-parity

## Summary

Make a **source-derived depth/detail-density budget** a hard obligation of the Phase 4
grounded claim plan, so a fanned-out but shallow `expanded` wiki cannot pass as DeepWiki
scale parity. The previous phase enforced breadth; this phase enforces depth.

## Context

The DeepWiki pipeline runs Phase 1 (decompose) → Phase 2 (plan + normalize + coverage
gates) → Phase 3 (deterministic evidence retrieval) → Phase 4 (grounded writing). The
`expanded` coverage mode is the core DeepWiki-scale hierarchical path. Phase 4's grounded
sub-path (`--grounded-claim-plan`) asks the model for a structured **claim plan**,
validates it deterministically against a per-section **token bank**, and renders the
Markdown itself — one claim becomes one paragraph, one sufficient required topic becomes
one `###` heading.

## Current state *(sourced)*

The latest real RAGFlow non-live E2E (`20260629-201218-…-35d5d6f`) PASSED with strong
breadth:

- 56 sections, 169/169 required topics, 96/96 content blocks, 82/82 promoted leaf topics.
- Phase 2 anti-compression gate PASS: 48 leaf pages vs a catalog floor of 23.
- 1008 distinct citations; 45,038 generated words; 228 generated headings.

But the depth is shallow:

- ~530 words and ~4 headings per section; ~407 claims, ~7.3 claims/page.
- Sampled section files run 139–474 words with ≤6 headings.
- `017-memory-implementation.md`: each required topic / catalog topic renders as a single
  `###` heading with one paragraph.

The comparison-only benchmark `ragflow-deepwiki.md` is ~98,271 words and ~899 headings
(74 H1, 362 H2, 452 H3) — roughly 2.2× the words and ~4× the headings.

## Problem statement

The previous TDD defined the wrong finish line: it enforced **only breadth**
anti-compression (`>= 36 pages / >= 94 required topics`) and explicitly scoped out longer
prose and DeepWiki-parity generation. There is:

- no source-derived per-section detail/depth budget,
- no minimum claim-density obligation per required topic or content block,
- no claim-plan validation that fails a section that covers its required topics only
  *existentially* (one claim each) while leaving most of its Phase 3 mapped evidence
  unused,
- no depth metrics in the audit/report artifacts.

So the grounded renderer collapses each claim to one paragraph
(`_skeleton_paragraph_template`, `_render_claim_paragraph`) and each required topic to one
`###` heading (`render_section`), and content blocks invent no headings
(`_derive_covered_content_blocks`). A shallow plan that names every required topic with a
single claim passes every gate.

## Root cause

Coverage was modeled as **existential** ("is each required topic / content block present
at all?"). Depth requires a **distributive density** model ("does each required topic
ground enough claims for the evidence Phase 3 actually mapped to it?"), exactly analogous
to how the Phase 2 anti-compression gate replaced existential page-planning coverage with
a distributive breadth contract.

## Scope / Non-scope

**In scope:** a deterministic, source-derived per-section depth budget; a claim-plan
depth gate (fail a shallow plan with precise diagnostics); prompt hardening so the planner
grounds enough claims; depth metrics in the per-section audit. Expanded grounded path only.

**Out of scope (this slice):** content-block-level `####` heading rendering (follow-up
M2); any live model run; changing baseline/enhancement; changing Phase 1/2/3; any word/
heading target copied from the benchmark; output patching or heal/retry loops.
