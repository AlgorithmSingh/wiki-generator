# Source index

Grounding sources for this TDD. Each item is marked **sourced** (read directly),
**inferred** (derived from sourced material), or **comparator** (isolation-only).

## Prior design docs (sourced; preserved)

- `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`
- `docs/technical-design/deepwiki-coverage-expansion/final/technical-design-document.md`
- `docs/product-requirements/deepwiki-scale-parity-next-phase/artifacts/final_prd.md`
- `docs/technical-design/deepwiki-scale-parity-next-phase/final/technical-design-document.md`
- `docs/technical-design/deepwiki-scale-parity-next-phase/adr/0001-deepwiki-scale-anti-compression-mode.md`

## Implementation surfaces (sourced)

- `src/wiki_generator/libs/coverage/validate.py` — coverage modes + `enforces_breadth`/`is_expanded_family`.
- `src/wiki_generator/libs/coverage/anti_compression.py` — breadth gate, promotion contract.
- `src/wiki_generator/libs/coverage/topic_catalog.py` — `derived/planning-topic-catalog.md` rendering.
- `src/wiki_generator/libs/commands/normalize_plan.py` — Phase 2 gate wiring.
- `src/wiki_generator/libs/commands/plan.py` — embedded planner system/kickoff prompts.
- `gemini-gem/GEM_INSTRUCTIONS.md`, `gemini-gem/KICKOFF_PROMPT.md` — Gem prompt files.
- `src/wiki_generator/libs/evidence/evidenced_coverage.py` — Phase 3 `catalog_topic_id` linkage.
- `src/wiki_generator/libs/writing/generated_coverage.py` — Phase 4 obligations + generated coverage.
- `src/wiki_generator/cli.py` — `--coverage-mode` help/choices.

## Real-run evidence (sourced; read-only)

- `.../20260629-152217-real-ragflow-gpt54-expanded-681b900-.../EXPANDED_REAL_RAGFLOW_GPT54_E2E_RESULT.md`
- `.../bundle/plans/page-planning-report.md`, `.../bundle/plans/section-plans.jsonl`
- `.../bundle/derived/topic-catalog.json` — 147 topics / 94 must / 12 must-families /
  82 must-subsystems. The previous expanded build collapsed this to 21 flat pages / 42 TERs.

## Comparator (isolation-only)

- `/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md` — **comparison only**.
  Never read as evidence, prompt seed, headings, or copied structure.

## Methodology + rules (sourced)

- TDD phase series at `/Users/ankitsingh/Documents/my-pi-ai-tts-setup/5-Technical-Design-document/2-TDD-Phases/tdd-phase-series`.
- Python rules at `/Users/ankitsingh/Documents/SKILLS/python-typescript-swift-sequence/python` (HARD-RULES.md).
