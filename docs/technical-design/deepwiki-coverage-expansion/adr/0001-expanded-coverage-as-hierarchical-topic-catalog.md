# ADR 0001: Represent Expanded Coverage as a Hierarchical Topic Catalog

## Status

Accepted for TDD.

## Date

2026-06-29

## Context

The current official grounded wiki is valid for its planned scope, but its plan is too coarse for DeepWiki-style breadth. The PRD requires a broader hierarchical wiki generated from repository evidence, with strict grounding preserved.

The benchmark DeepWiki export shows a larger hierarchy and per-page relevant source files, but it is comparator-only. It was indexed at a different commit and must not become source truth, citeable evidence, copied headings, copied prose, or copied claims.

Existing `wiki-generator` already has useful foundations:

- deterministic Phase 1 artifacts and coverage-family signals;
- Phase 2 normalized SectionPlan fields and enhancement gates;
- Phase 3 deterministic EvidencePackets and evidenced coverage;
- Phase 4 generated coverage and grounded claim/token rendering;
- strict validators and failure policies.

The gap is not primarily writing length. It is that source-derived subtopics are not cataloged, promoted, planned, source-selected, evidenced, and traced at page/content-block granularity.

## Decision

Represent expanded coverage as a repository-derived hierarchical topic catalog before Phase 2 planning.

The catalog will:

- be generated deterministically from repository artifacts;
- be marked planner context and non-citeable;
- include stable topic IDs, parent/child topic relationships, source-derived signals, suggested page profiles, required content blocks, candidate source handles, evidence-lane expectations, signal strength, priority, and known-gap/defer reasons;
- constrain the Phase 2 LLM planner to produce hierarchical parent/child page plans from repository-backed topic candidates;
- feed deterministic per-page relevant-source selection before Phase 3;
- connect to evidence sufficiency, grounded rendering, generated coverage, and coverage traceability gates.

Existing `section_id` remains the implementation key for compatibility; in expanded mode it is treated as the page ID. New PagePlan fields are additive to normalized SectionPlan rows.

## Consequences

### Positive

- Moves coverage expansion upstream, where missing pages and topics can be detected before writing.
- Keeps Phase 3 deterministic and fail-closed.
- Gives validators explicit source-derived obligations instead of relying on section count or prose length.
- Prevents broad parent pages from satisfying child obligations.
- Enables topic→plan→source→evidence→output traceability.
- Preserves existing pipeline structure and baseline compatibility.

### Negative / costs

- Adds new artifacts and schema versions to maintain.
- Requires calibrated thresholds for topic promotion and deferral.
- Increases Phase 2 planning contract complexity.
- Requires more fixtures and negative tests to prove strictness.
- May increase live provider cost after non-live validation because more pages are rendered.

### Neutral

- The benchmark remains useful as a breadth dashboard, but not as evidence or plan source.
- Optional richer static-analysis tools may be added later, but the first design does not depend on proving DeepWiki used any specific tool.

## Alternatives considered

| Alternative | Decision | Reason |
| --- | --- | --- |
| Ask Phase 4 to write longer pages | Rejected | Does not create missing source-derived obligations and risks filler. |
| Copy benchmark hierarchy | Rejected | Violates comparator-only rule and commit mismatch caveat. |
| Use 13 mandatory families as the final catalog | Rejected | Existing evidence shows broad families still compress important subtopics. |
| Replace deterministic retrieval with LLM retrieval | Rejected | Violates Phase 3 determinism. |
| Build graph/AST stack first | Deferred | Useful later, but not required for the first catalog slice; existing artifacts can seed deterministic cataloging. |

## Validation implications

Implementation must prove:

- catalog generation is deterministic and timestamp-free;
- catalog artifacts are non-citeable and excluded from citation/evidence gates;
- every high-signal catalog topic is planned, evidenced, generated, or explicitly deferred with source-derived reason;
- topic catalog fingerprints flow into plan/source/evidence/generated traceability;
- strict validators remain unchanged or stricter;
- repair remains bounded to LLM-authored page plans or claim plans.

## Supersession policy

If implementation later replaces the catalog architecture with another upstream coverage substrate, create a new ADR that supersedes this one. Do not silently rewrite this accepted decision.
