# DeepWiki Coverage Expansion — Technical Design Workspace

**Status:** Final TDD assembled and locally validated
**Workspace:** `docs/technical-design/deepwiki-coverage-expansion/`
**Document weight:** Full technical design
**Primary input:** `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`

## Purpose

This workspace contains the technical design for expanding `wiki-generator` from a concise, grounded 22-section wiki toward a broader DeepWiki-style hierarchical wiki generated from repository evidence.

The design follows the TDD phase-series process from:

`/Users/ankitsingh/Documents/my-pi-ai-tts-setup/5-Technical-Design-document/2-TDD-Phases/tdd-phase-series`

## Reader orientation

- Start with `final/technical-design-document.md` for the formal TDD.
- Use `adr/0001-expanded-coverage-as-hierarchical-topic-catalog.md` for the key architecture decision.
- Use `definition-of-done.json` and `working/validation-report.json` to check readiness.
- Use `source-index.md` to see which claims are sourced, inferred, or open.

## Workspace map

```text
docs/technical-design/deepwiki-coverage-expansion/
  README.md
  manifest.json
  status.md
  source-index.md
  definition-of-done.json
  working/
    01-intent.json
    02-readers-and-stakeholders.md
    03-rightsize-plan.json
    problem-success.md
    technical-design.md
    design-judgment.md
    execution-readiness.md
    validation-report.json
    repair-log.md
  adr/
    0001-expanded-coverage-as-hierarchical-topic-catalog.md
  final/
    technical-design-document.md
```

## Key design premise

Coverage expansion is treated as an upstream catalog, planning, source-selection, and evidence-traceability problem. Phase 3 remains deterministic, and Phase 4 remains a grounded renderer using the existing claim/token plan path.

## Boundary

This workspace only adds documentation. It does not edit code and does not commit changes.
