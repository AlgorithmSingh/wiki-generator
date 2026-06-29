# Phase B–F Follow-up — Expanded `write-wiki` Command E2E Result

**Date:** 2026-06-29  
**Status:** `ok`  
**Scope:** Close the one deferred Phase B–F follow-up: a fake-provider / non-live command-level E2E for `write-wiki --coverage-mode expanded`.

## Summary of what changed

Added a true command-path expanded-writing E2E in `tests/test_phase4_generated_coverage.py`.

The new fixture writes a tiny schema-faithful expanded bundle with:

- `page_profile: operations-page`;
- `catalog_topic_ids[]` and `derived/topic-catalog.json`;
- `required_content_blocks[]`;
- a content-block-linked TER with `catalog_topic_id` and `content_block_id`;
- `plans/relevant-source-map.json` rows surfaced into the writing packet;
- enforced/passing `plans/coverage-gate.json` and `evidence/evidenced-coverage.json`;
- a real `write-wiki --coverage-mode expanded --grounded-claim-plan` CLI invocation using `--provider gemini-gem --responses-in`.

The happy path imports a fake Gem claim-plan response, exercises grounded `content_block_id` handling, derives `covered_content_blocks[]`, writes `generated-coverage.json`, and passes the expanded content-block coverage validator.

The negative path omits the claim-plan `content_block_id`, so the required expanded content block is omitted from generated coverage and the real command fails closed with exit code `5` at the existing generated-coverage / writing-validation boundary.

No production validator was weakened. No retry/heal loop was added. No generated output was patched.

## Exact tests added

In `tests/test_phase4_generated_coverage.py`:

- `ExpandedWriteWikiCommandE2ETests.test_expanded_grounded_command_happy_path_writes_block_coverage`
- `ExpandedWriteWikiCommandE2ETests.test_expanded_grounded_command_omitted_block_fails_exit_5`

## Tests and checks run

- `uv run python -m pytest -q tests/test_phase4_generated_coverage.py tests/test_phase4_depth_profiles.py tests/test_phase4_grounded.py` — **pass**, 73 passed, 12 subtests passed.
- `uv run python -m pytest -q tests/test_coverage_facets.py tests/test_topic_catalog.py tests/test_phase2_topic_catalog_planning.py tests/test_relevant_source_map.py tests/test_phase3_evidence_portfolios.py tests/test_coverage_traceability.py tests/test_artifact_consistency.py` — **pass**, 96 passed.
- `uv run python -m pytest -q` — **pass**, 643 passed, 1 skipped, 21 subtests passed.
- `git diff --check` — **pass**.
- `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` — **pass**; protected Phase 3 spec unchanged.

## Deferred E2E closure

Closed. The deferred fake-provider / non-live expanded `write-wiki` command E2E now exists, covers the happy and fail-closed paths, and runs through the real CLI command path with `--coverage-mode expanded`.

## PRD compliance check

Checked against `docs/product-requirements/deepwiki-coverage-expansion/artifacts/final_prd.md`:

- **UR-02 / UR-03 / DI-03:** covered by the expanded fixture's page profile, hierarchy-compatible section plan, catalog topic IDs, and required content blocks.
- **UR-05 / DI-06:** evidenced coverage carries page/topic/content-block linkage and exact supporting evidence IDs into writing.
- **UR-06 / DI-07 / VG-05:** the command uses grounded claim-plan rendering in expanded mode.
- **UR-07 / DI-08 / VG-06:** generated coverage records and validates both required topics and content blocks.
- **UR-09 / VG-07 / BR-06:** strict validators remain intact; missing content-block coverage fails.
- **UR-10:** the negative command E2E fails closed with exit code `5` when an expanded required content block is omitted.
- **BR-07 / BR-08 / NG-03:** no output patching and no generic retry/heal loop.
- **BR-05:** Phase 3 remains deterministic; this slice did not modify the protected Phase 3 spec.

PRD verdict for this follow-up: **pass**.

## Remaining risks

No known blocker for the deferred non-live expanded command E2E. Live expanded Vertex/Gemini validation remains out of scope and still requires explicit approval.

## Live/billed provider statement

No live or billed Vertex / Gemini / API provider calls were made. The command E2E uses the non-live `gemini-gem` response-import path with local fake responses only.
