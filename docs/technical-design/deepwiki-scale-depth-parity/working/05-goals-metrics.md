# Goals, Non-Goals & Success Metrics — deepwiki-scale-depth-parity

## Goals (each paired with an explicit non-goal)

| # | Goal | Non-goal |
|---|---|---|
| G1 | A deterministic, **source-derived per-section depth budget** obliges each sufficient required topic to ground claims proportional to its Phase 3 mapped-evidence density. | Any word/heading/claim target copied or derived from `ragflow-deepwiki.md`. |
| G2 | The claim-plan validator **fails a shallow plan** (required topics covered only existentially) with precise per-topic / per-content-block / per-section diagnostics (measured vs required). | Patching generated output, auto-padding, or a heal/retry loop to reach the budget. |
| G3 | The claim-plan **prompt** carries the depth budget so the planner produces enough claims, and the system instruction asks for it. | Putting benchmark numbers, headings, or prose into the prompt. |
| G4 | Depth **metrics** appear in the per-section grounded audit block so an operator sees why a section passed/failed depth. | A new persisted artifact schema or a document-level rewrite. |
| G5 | The budget is **injectable** (`DepthPolicy`) and **bounded**, so it is auditable, tunable, and cannot explode. | Scattered magic numbers; an unbounded per-topic claim demand. |
| G6 | `baseline` and `enhancement` behavior is **unchanged**; depth applies only to the **expanded grounded** path; `deepwiki-scale` stays a behavior-identical alias. | Reintroducing `deepwiki-scale` as a separate product. |
| G7 | Strict grounding, citation validation, benchmark quarantine, and the deterministic LLM-free Phase 3 are **preserved**; no validator weakened. | Relaxing any existing claim-plan or section validator to make depth pass. |

## Future goals

- A live RAGFlow run (separately approved, billed) to confirm the planner reaches the
  depth budget on the real catalog.
- Content-block-level `####` heading rendering for heading-density depth (M2).
- A document-level depth dashboard (generated vs benchmark words/headings, comparison-only).

## Success metrics (measurable)

- **SM1** A claim plan that names every sufficient required topic with a single claim but
  leaves most of its Phase 3 mapped evidence unused **FAILS** depth validation
  (`claim_plan_topic_underfilled`), in expanded grounded mode.
- **SM2** A claim plan that grounds claims proportional to each topic's mapped-evidence
  density **PASSES**.
- **SM3** The same single-claim plan **PASSES** when the topic has exactly one mapped
  evidence id (target is satisfiable, not padding) — the existing expanded grounded
  command E2E (`ops`, 1 mapped evidence id) still passes.
- **SM4** `baseline` and `enhancement` runs never compute or enforce the depth budget;
  the full suite stays green.
- **SM5** Every depth threshold and per-topic target derives only from catalog/plan/
  evidence inputs (mapped evidence, packets, content blocks, required topics, token bank,
  source handles); the comparator is never read by the pipeline. Determinism: identical
  inputs → byte-identical depth budget/report.
- **SM6** The per-section grounded audit block records the depth budget and the measured
  claim counts (per topic + total), and a failing plan's diagnostics name the topic, its
  mapped-evidence count, the measured claim count, and the required count.
- **SM7** `DepthPolicy` is a frozen, injectable dataclass with validated bounds; the
  effective policy is serialized in the depth budget/report.

All seven are validated by `tests/test_phase4_depth_budget.py` and the existing suites;
see `working/16-test-traceability.md`.
