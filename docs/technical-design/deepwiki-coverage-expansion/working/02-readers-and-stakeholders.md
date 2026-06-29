# Readers and Stakeholders

## Primary readers

### Implementers

**Need:** Concrete module boundaries, data contracts, CLI behavior, and tests.
**Concern:** Avoid broad rewrites and preserve the existing Phase 1–4 pipeline.
**Grounding:** Sourced from PRD stakeholders and existing code inspection.

### Reviewers and maintainers

**Need:** Clear rationale for why coverage expansion belongs upstream in catalog/planning/source selection rather than Phase 4 prose length.
**Concern:** No benchmark leakage, no validator weakening, and no output patching.
**Grounding:** Sourced from PRD business rules and traceability matrix.

### Documentation pipeline owners

**Need:** Deterministic artifacts that prove planned, evidenced, generated, citation, and freshness status per page/topic/content block.
**Concern:** Artifacts must be auditable and reproducible across reruns.
**Grounding:** Sourced from PRD DI and VG requirements.

### Operators / release owners

**Need:** Safe rollout path, rollback behavior, live-provider policy, and failure diagnostics.
**Concern:** Vertex/Gemini live runs must remain explicit, controlled, and final-provider-compatible.
**Grounding:** Sourced from user constraints and existing README/CLI.

## Secondary readers

### Future maintainers

**Need:** A durable explanation of why a hierarchical topic catalog was chosen and how to update it after implementation drift.
**Concern:** Avoid hidden decisions and stale design artifacts.
**Grounding:** TDD guide maintenance loop; ADR required.

### Product/release decision makers

**Need:** Success metrics that distinguish a shareable broad engineering wiki from a concise grounded overview.
**Concern:** Page count alone must not become the launch criterion.
**Grounding:** Sourced from PRD metrics and non-goals.

### Test authors

**Need:** Requirement-to-test traceability, fixture strategy, non-live E2E scope, and live-run approval boundaries.
**Concern:** Tests must prove strictness and negative failure paths, not just happy-path expansion.
**Grounding:** Sourced from PRD validation gates and existing test modules.

## Stakeholder decision responsibilities

| Decision | Primary owner | Reader impact | Status |
| --- | --- | --- | --- |
| Promote which source-derived facets to required pages | Product/engineering lead with evaluator input | Determines blocking catalog/planning obligations | Open |
| Roll out expanded catalog enforcement under existing `--coverage-mode enhancement` or behind a temporary catalog flag | Engineering lead | Determines CLI compatibility and adoption speed | Open |
| Decide first real target breadth after catalog generation | Product/release owner | Prevents benchmark page-count chasing | Open |
| Approve any future live/billed Vertex/Gemini validation run | User/release owner | Controls cost and production-path proof | Open |
| Sign off high-risk page families such as deployment, auth, API, migrations, storage, retrieval, LLM providers, and operations | Maintainers/domain owners | Reduces risk of misleading generated docs | Open |

## Writing expectations

- Use plain language and stable artifact names.
- Mark sourced, inferred, and open claims.
- Name likely files/modules to create or modify; mark proposed new names as inferred.
- Avoid benchmark-derived wording except as comparator context.
