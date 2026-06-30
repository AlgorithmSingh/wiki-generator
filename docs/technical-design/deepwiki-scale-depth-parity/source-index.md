# Source Index — deepwiki-scale-depth-parity

Every requirement, assumption, constraint, risk, and decision below is marked
*(sourced)* (read from a real artifact/code), *(inferred)* (design judgment), or
*(open)* (unresolved decision).

## Code seams (sourced)

- `src/wiki_generator/libs/writing/claim_plan.py` — claim-plan schema, deterministic
  `validate_claim_plan`, `render_section`, prompt construction. `_skeleton_paragraph_template`
  collapses a skeleton to one paragraph; `_render_claim_paragraph` renders one claim to
  one paragraph; `render_section` emits one `###` per sufficient required topic;
  `_derive_covered_content_blocks` invents **no** new headings for content blocks.
- `src/wiki_generator/libs/writing/grounded.py` — per-section grounded two-stage loop;
  calls `validate_claim_plan`, `render_section`, the strict section validator.
- `src/wiki_generator/libs/writing/generated_coverage.py` — topic/content-block
  obligations from the Phase 3 evidenced matrix; `mapped_evidence_ids` per required
  topic; generated-coverage validation.
- `src/wiki_generator/libs/writing/packet.py` — `WritingPacket`: `allowed_evidence_ids`,
  `required_topics_coverage` (with `supporting_evidence_ids`), `content_block_coverage`,
  `relevant_source_handles`.
- `src/wiki_generator/libs/writing/token_bank.py` — per-section verbatim token bank.
- `src/wiki_generator/libs/writing/validate.py` — strict section + whole-document
  validators (unchanged here).
- `src/wiki_generator/libs/writing/options.py` — `EXPANDED_COVERAGE_MODES`,
  `ENFORCING_COVERAGE_MODES`, `grounded_claim_plan`.
- `src/wiki_generator/libs/writing/__init__.py` — Phase 4 `run()` orchestration.
- `src/wiki_generator/libs/coverage/anti_compression.py` — the **pattern to mirror**:
  `BreadthPolicy` (injectable, frozen), `derive_breadth_budget`,
  `render_breadth_budget_lines`, gate dataclass, defect codes, remediation.

## Prior design artifacts (sourced)

- `docs/technical-design/deepwiki-scale-core-fanout/final/technical-design-document.md`
- `docs/technical-design/deepwiki-scale-core-fanout/definition-of-done.json`
- `docs/technical-design/deepwiki-scale-parity-next-phase/final/technical-design-document.md`
- `docs/product-requirements/deepwiki-scale-parity-next-phase/artifacts/final_prd.md`
- `docs/technical-design/deepwiki-coverage-expansion/final/technical-design-document.md`
- `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`

## Observed evidence of the gap (sourced)

Latest real non-live E2E
`19-do-it-e2e/runs/20260629-201218-real-ragflow-gpt54-expanded-35d5d6f-ragflow-3f805a64f/`:

- `EXPANDED_REAL_RAGFLOW_GPT54_E2E_RESULT.md`, `expanded-real-ragflow-gpt54-e2e-summary.json`
- `bundle/plans/anti-compression-gate.json` — breadth PASS (56 sections, 82/82
  promoted leaf, 48/23 leaf pages vs floor).
- `bundle/wiki/metadata/generated-coverage.json`, `bundle/coverage/coverage-traceability.json`,
  `bundle/wiki/PHASE4_RUN_REPORT.md`.
- Sampled section files (`bundle/wiki/sections/*.md`): word counts 139–474, ≤6 headings;
  e.g. `017-memory-implementation.md` renders each required topic / catalog topic as one
  `###` heading with a single paragraph.

Observed counts: Status PASSED; 56 sections; 169/169 required topics; 96/96 content
blocks; 82/82 promoted leaf topics; 1008 distinct citations; 45,038 generated words;
228 generated headings; ~530 words/page and ~4 headings/page; ~407 claims, ~7.3/page.

## Benchmark comparator (sourced; quarantine-only)

- `ragflow-deepwiki.md` — ~98,271 words; ~899 headings (74 H1, 362 H2, 452 H3).
  **Comparison-only.** Never evidence, prompt, headings, prose, structure, or generated
  required topics. Used only to explain the scale gap and as a post-generation dashboard.

## Methodology sources (sourced)

- TDD phase series:
  `my-pi-ai-tts-setup/5-Technical-Design-document/2-TDD-Phases/tdd-phase-series/` (phases 1–7).
- Python build sequence: `SKILLS/python-typescript-swift-sequence/python/` (README,
  HARD-RULES, SEQUENCE, 27 stage agents).

## Open items (open)

- *(open)* `DepthPolicy` default `evidence_per_claim` and `max_claims_per_required_topic`
  values: seeded conservatively; release-owner sign-off required before any billed live
  run (mirrors the `BreadthPolicy` open decision in the prior phase).
- *(open)* Whether content-block-level `####` headings (heading-density depth) are added
  now or in a follow-up milestone — decided in §11/§13: deferred to M2 to bound blast
  radius on the content-block-coverage evaluator.
