# Design Judgment

## Quality attributes

| Attribute | Target | Design decision | Grounding |
| --- | --- | --- | --- |
| Grounding | 100% of repo-specific generated claims cite valid EvidencePacket IDs; no context-only or benchmark citations. | Keep Phase 3 citeable evidence as the only source for claims; Phase 4 renders from grounded claim/token plans. | Sourced: PRD QA-01 |
| Determinism | Same inputs produce same catalog, source map, evidence matrix, generated coverage, and traceability reports. | Catalog/source selection/evidence/validation are deterministic; LLM is limited to planning and claim plans. | Sourced: PRD QA-02 |
| Traceability | Every blocking topic/content block traces from catalog to final Markdown/citation. | Add `coverage/coverage-traceability.json`. | Sourced: PRD QA-03 |
| Breadth without filler | High-signal facets become pages/blocks or explicit gaps; page count is not the goal. | Use source-derived catalog and profile-aware content blocks. | Sourced: PRD QA-04 |
| Citation integrity | Zero unresolved/malformed/context citations and zero unsupported identifiers. | Preserve existing strict validators and grounded token bank. | Sourced: PRD QA-05 |
| Evidence sufficiency | Broad recall cannot satisfy precise required obligations. | Enforce exact lane portfolios per profile/block. | Sourced: PRD QA-06 |
| Usability | Nested navigation and audience paths help readers find subsystem pages. | Preserve hierarchy in index and metadata. | Sourced: PRD QA-07 |
| Failure transparency | Gate failures name page, topic, block, source field/evidence issue, and owner. | Extend diagnostics in plan/evidence/generated coverage gates. | Sourced: PRD QA-08 |
| Repair discipline | Repair has exact diagnostics, attempt caps, audit, and strict revalidation. | Limit repair to LLM-authored page plans and claim plans. | Sourced: PRD QA-09 |
| Benchmark safety | Benchmark comparison cannot create evidence IDs, headings, or claims. | Keep comparator report outside source gates; validate no benchmark-derived artifacts. | Sourced: PRD QA-10 |

## Key trade-offs

### Catalog before planning vs. bigger planner prompt only

**Decision:** Add a deterministic topic catalog before Phase 2.
**Why:** A bigger prompt over current family signals would still let the LLM under-plan or over-require unsupported topics. A catalog gives the planner bounded, source-derived candidates and creates deterministic gates.
**Cost:** More Phase 1/2 artifact work and calibration.

### Extend existing SectionPlan vs. introduce a separate PagePlan store

**Decision:** Extend SectionPlan additively while treating `section_id` as page ID in expanded mode.
**Why:** Existing Phase 3/4 already key packets, evidence, citations, generated metadata, and validation by `section_id`. Additive fields preserve compatibility.
**Cost:** The term “section” remains in some code artifacts even when the product concept is “page.” Documentation must clarify the alias.

### Integrate relevant-source map into normalize-plan vs. add a new command

**Decision:** Prefer writing `plans/relevant-source-map.json` from the Phase 2 normalization/enhancement gate path.
**Why:** The source map is a Phase 2→3 contract and should be current with the exact normalized plan. This avoids a new required operator command.
**Cost:** `normalize-plan --coverage-mode enhancement` becomes heavier. If implementation proves this too large, a separate `select-sources` command can be added later with freshness fingerprints.

### Profile-aware evidence portfolios vs. global retrieval cap increase

**Decision:** Add profile/block-specific evidence floors rather than only increasing `max_total_per_section`.
**Why:** Evidence breadth must match page obligations. A larger cap alone can still starve the exact topic/block that matters.
**Cost:** More rules and fixtures per page profile.

### Grounded claim-plan rendering vs. freeform writing with validators

**Decision:** Use existing grounded claim/token plan path for expanded pages.
**Why:** Expanded output increases opportunities for invented terminal tokens; token-bank substitution prevents unsupported identifiers upstream.
**Cost:** Requires page-profile-aware claim grouping and may be more verbose to prompt/audit.

## Alternatives considered

| Alternative | Outcome | Reason |
| --- | --- | --- |
| Ask Phase 4 to write longer pages over the same 22 sections | Rejected | Does not create missing page/topic/source/evidence obligations; risks filler. |
| Copy benchmark hierarchy/headings as a plan seed | Rejected | Violates benchmark-is-comparator-only rule and commit mismatch caveat. |
| Replace deterministic Phase 3 with LLM retrieval | Rejected | Violates deterministic retrieval and fail-closed constraints. |
| Relax validators for expanded output | Rejected | Violates PRD and would make breadth untrustworthy. |
| Treat the 13 mandatory families as sufficient | Rejected | Existing evidence shows 13-family coverage can still compress major subtopics. |
| Build a graph database or Tree-sitter/SCIP dependency first | Deferred | Reverse-engineering does not prove these are required; first slice can use existing deterministic artifacts and add optional extractors later. |
| Add generic retry-until-green around planning/writing | Rejected | Violates repair discipline; would hide producer defects. |
| Hard-code a 62-page target | Rejected | Page count must be calibrated from source-derived catalog, not benchmark parity. |

## ADR summary

ADR 0001 records the central decision: represent expanded coverage as a repository-derived hierarchical topic catalog that constrains planning, source selection, evidence, rendering, and traceability.

## Open decisions

| ID | Decision | Why it matters |
| --- | --- | --- |
| OD-01 | Thresholds for promoting catalog topics to required pages. | Balances breadth with evidence sufficiency and avoids over-requiring unsupported topics. |
| OD-02 | Temporary rollout flag vs. immediate enforcement under `--coverage-mode enhancement`. | Controls compatibility and rollout risk. |
| OD-03 | First implementation profile set. | Defines test fixture scope and first user-visible breadth. |
| OD-04 | High-risk page-family human sign-off requirements. | Reduces risk for deployment, auth, API, storage, migration, LLM, and operations pages. |
| OD-05 | Whether and when grounded claim-plan mode becomes default for expanded runs. | Affects CLI defaults and live-run stability. |
