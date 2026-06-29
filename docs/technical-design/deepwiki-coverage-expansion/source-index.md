# Source Index — DeepWiki Coverage Expansion TDD

This index records the sources used to assemble the TDD and how claims are grounded.

## Grounding labels

- **Sourced:** directly supported by an input source or inspected repository file.
- **Inferred:** reasoned from sourced inputs or existing code shape; implementation names may need adjustment.
- **Open:** requires product or engineering decision before implementation.

## Primary product sources

| ID | Source | Use in TDD | Grounding notes |
| --- | --- | --- | --- |
| SRC-PRD | `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md` | Goals, non-goals, requirements, business rules, success metrics, validation gates, target behavior. | Sourced. |
| SRC-TRACE | `docs/product-requirements/deepwiki-coverage-expansion/artifacts/traceability_matrix.md` | Requirement-to-acceptance/gate mapping and source-fact traceability. | Sourced. |
| SRC-REV | `/Users/ankitsingh/Documents/deep-wiki/reverse-engineer.md` | DeepWiki export observations: 62 page blocks, per-page relevant source files, source-aware planning inference, commit mismatch caveat. | Sourced for comparator analysis only; not citeable evidence for generated wiki content. |
| SRC-COVX | `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_GPT55_XHIGH.md` | Current run state, gap taxonomy, implementation slices, metrics, anti-patterns. | Sourced. |
| SRC-DR | `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_DEEP_RESEARCH.md` | Research synthesis: upstream phase changes, topic catalog, evidence-backed discovery, rollout stages. | Sourced. |
| SRC-SPEC | `docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md` | Existing enhancement implementation status and constraints: Phase 2/3 gates, generated coverage, grounded claim/token plan, no live calls without approval. | Sourced. |

## TDD process sources

| ID | Source | Use in TDD | Grounding notes |
| --- | --- | --- | --- |
| SRC-TDD-GUIDE | `/Users/ankitsingh/Documents/my-pi-ai-tts-setup/5-Technical-Design-document/2-TDD-Phases/tdd-phase-series/README.md` | Workspace layout, phase process, full formal TDD section target, validation/repair separation. | Sourced. |
| SRC-TDD-RULES | `/Users/ankitsingh/Documents/my-pi-ai-tts-setup/5-Technical-Design-document/2-TDD-Phases/tdd-phase-series/tdd-phase-agents/_GLOBAL-TDD-PHASE-RULES.md` | Grounding, right-sizing, table of contents, definition of done, maintenance loop. | Sourced. |
| SRC-TDD-PHASES | `tdd-phase-agents/tdd-phase-1..7-*.md` | Required intermediate artifacts and phase responsibilities. | Sourced. |

## Existing code inspected

| ID | Existing path | Existing role observed | TDD use |
| --- | --- | --- | --- |
| SRC-CODE-README | `README.md` | Describes Phase 1–4 pipeline, thin CLI/deep libs split, current enhancement gates, Vertex/Gemini provider path. | Architecture context. |
| SRC-CLI | `src/wiki_generator/cli.py` | Existing CLI flags for `normalize-plan`, `retrieve-evidence`, `write-wiki`, `--coverage-mode enhancement`, and `--grounded-claim-plan`. | CLI compatibility design. |
| SRC-CMD-NORM | `src/wiki_generator/libs/commands/normalize_plan.py` | Runs planned coverage and topic-obligation gates in enhancement mode. | Phase 2 boundary design. |
| SRC-CMD-EVIDENCE | `src/wiki_generator/libs/commands/retrieve_evidence.py` | Thin wrapper for deterministic all-sections Phase 3 retrieval. | Phase 3 compatibility. |
| SRC-CMD-WRITE | `src/wiki_generator/libs/commands/write_wiki.py` | Thin Phase 4 wrapper; maps gate/provider/validation failures; provider choices include Vertex. | Phase 4 behavior and exit-code design. |
| SRC-COV-TAXONOMY | `src/wiki_generator/libs/coverage/taxonomy.py` | Existing 13 mandatory topic-family taxonomy. | Baseline overlay and catalog expansion. |
| SRC-COV-SIGNALS | `src/wiki_generator/libs/coverage/signals.py` | Existing deterministic Phase 1 coverage-family signals. | Seed for expanded topic catalog design. |
| SRC-COV-VALIDATE | `src/wiki_generator/libs/coverage/validate.py` | Existing planned-coverage gate against mandatory families. | Expanded page/facet gate design. |
| SRC-COV-OBLIGATIONS | `src/wiki_generator/libs/coverage/obligations.py` | Existing topic evidence requirement gate, lane/type consistency, citeable-substrate viability. | Extended content-block obligation gate. |
| SRC-COV-SUBSTRATE | `src/wiki_generator/libs/coverage/substrate.py` | Existing citeable-path substrate view over chunks/spans. | Relevant-source and citeability checks. |
| SRC-DIGEST-UPLOAD | `src/wiki_generator/libs/digest/upload_package.py` | Existing planner upload package includes `planning-coverage-signals.md`. | Catalog digest inclusion. |
| SRC-DIGEST-HANDLES | `src/wiki_generator/libs/digest/planning_handles.py` | Existing exact handle catalog for planner. | Source-obligation constraints. |
| SRC-DIGEST-RUNTIME | `src/wiki_generator/libs/digest/planning_runtime_surfaces.py` | Existing route/worker/CLI/config/contract summaries. | Catalog detector inputs. |
| SRC-EVIDENCE-COVERAGE | `src/wiki_generator/libs/evidence/evidenced_coverage.py` | Existing per-required-topic evidence sufficiency matrix. | Per-page/content-block evidence design. |
| SRC-EVIDENCE-OPTIONS | `src/wiki_generator/libs/evidence/options.py` | Existing deterministic retrieval caps and coverage modes. | Profile-aware cap design. |
| SRC-WRITE-GENCOV | `src/wiki_generator/libs/writing/generated_coverage.py` | Existing generated coverage gate from evidenced topics to Markdown/citations. | Extended block/topic traceability. |
| SRC-WRITE-BUNDLE | `src/wiki_generator/libs/writing/bundle.py` | Existing Phase 4 pre-provider gates and evidence index. | Artifact freshness and upstream gate design. |
| SRC-WRITE-TOKEN | `src/wiki_generator/libs/writing/token_bank.py` | Existing deterministic token-bank extraction. | Grounded rendering design. |
| SRC-WRITE-CLAIM | `src/wiki_generator/libs/writing/claim_plan.py` | Existing claim-plan schema, validation, and rendering. | Page-profile-aware grounded claim groups. |

## Important source facts carried into the TDD

| Fact | Source IDs | Grounding |
| --- | --- | --- |
| The official current run passed for its planned scope: 22 sections, 53/53 required topics, and 425 distinct citations. | SRC-PRD, SRC-COVX, SRC-TRACE | Sourced. |
| The benchmark export shows 62 page blocks and per-page relevant source files, but was indexed at a different commit and must not be used as source truth. | SRC-PRD, SRC-REV, SRC-TRACE | Sourced. |
| The target expansion should move coverage upstream into catalog, planning, source selection, evidence sufficiency, and generated traceability rather than longer writing. | SRC-PRD, SRC-COVX, SRC-DR | Sourced. |
| Strict validators must remain unchanged or stricter; output patching and generic heal loops are forbidden. | SRC-PRD, SRC-TRACE, SRC-SPEC | Sourced. |
| Phase 3 remains deterministic and LLM-free; Phase 4 uses grounded claim/token rendering when expanded coverage is enabled. | SRC-PRD, SRC-SPEC, SRC-CODE-README | Sourced. |
| New module names such as `coverage/facets.py`, `coverage/topic_catalog.py`, `coverage/source_selection.py`, and `coverage/traceability.py` are proposed and therefore inferred unless implemented later. | SRC-CODE inspected paths + design synthesis | Inferred. |

## Comparator boundary

The DeepWiki benchmark and reverse-engineering notes are used only to understand breadth and structural patterns. The final design forbids benchmark-derived evidence IDs, copied headings, copied prose, copied claims, or benchmark-only required topics in generated wiki output.
