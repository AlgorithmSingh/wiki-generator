# Technical Design — DeepWiki Scale: Depth Parity

| | |
|---|---|
| Slug | `deepwiki-scale-depth-parity` |
| Audience | Phase 4 writing maintainers, coverage-gate maintainers, future implementation agents, pipeline operator |
| Status | Final — validated (Phase 6) |
| Weight | Standard (focused single-subsystem change: a new deterministic depth budget + claim-plan gate, opt-in via expanded grounded mode) |
| Phase relation | Next phase after `deepwiki-scale-core-fanout` (preserved unchanged). Builds on it; does not replace it. |
| Comparator isolation | `ragflow-deepwiki.md` is **comparison-only** — never read as evidence, prompt seed, headings, copied prose/structure, or generated required topics. It only explains the scale gap and serves as a post-generation dashboard. |

## Orientation

The previous phase (`deepwiki-scale-core-fanout`) made the `expanded` path enforce
source-derived **breadth** (anti-compression): a 94-`must` catalog can no longer
collapse onto 21 flat pages. The latest real RAGFlow non-live E2E proves breadth is
solved — 56 sections, 169/169 required topics, 82/82 promoted leaf topics, 96/96
content blocks.

But the generated wiki is still far below DeepWiki benchmark **depth**: ~530 words and
~4 headings per section, ~7.3 claims per page, 45,038 words total against a ~98,271-word
benchmark. The renderer turns one claim into one paragraph and one required topic into
one `###` heading; there is no source-derived **detail/depth budget** and no gate that
fails a fanned-out-but-shallow plan.

This TDD designs a **source-grounded depth/detail-density quality contract** for the
Phase 4 grounded claim plan: a deterministic, source-derived per-section depth budget
that obliges each required topic to ground enough claims for the evidence Phase 3
actually mapped to it, a claim-plan validation gate that fails a shallow plan with
precise diagnostics, prompt hardening so the planner produces enough claims, and depth
metrics in the audit trail. Strict grounding, citation validation, benchmark
quarantine, and the deterministic LLM-free Phase 3 are all preserved.

## Workspace layout

```text
docs/technical-design/deepwiki-scale-depth-parity/
  README.md                      (this file)
  manifest.json                  intended weight + targets
  status.md                      phase-by-phase status
  source-index.md                grounded sources (sourced/inferred/open)
  definition-of-done.json        design-specific DoD (Phase 6 validates against it)
  working/
    01-intent.json
    02-readers-and-stakeholders.md
    03-rightsize-plan.json
    04-context-problem.md
    05-goals-metrics.md
    06-requirements-constraints.md
    07-view-selection.json
    08-architecture-overview.md
    09-component-module.md
    10-data-design.md
    11-interfaces.md
    12-behavior.md
    13-quality-attributes.md
    14-alternatives-tradeoffs.md
    15-implementation-plan.md
    16-test-traceability.md
    17-rollout-ops-risk.md
    validation-report.json
    repair-log.md
    execution-readiness.md
    implementation-result.md
    maintenance-policy.md
    maintenance-log.md
  adr/
    0001-source-derived-phase4-depth-budget.md
  final/
    technical-design-document.md
```
