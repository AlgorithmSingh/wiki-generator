# Status

- **Slug:** `deepwiki-scale-core-fanout`
- **Weight:** full
- **Audience:** pipeline implementers, planner-prompt owners, Phase 3/4 maintainers, release owner
- **State:** Implemented & validated (non-live). Phases 1–6 complete.

## Phase log

| Phase | Outcome |
|---|---|
| 1 — Setup & framing | Workspace created; intent, readers, full-weight rightsize plan written. |
| 2 — Problem & success | Problem framed (expanded shipping compressed output); G1–G5 + SM1–SM6; `definition-of-done.json` written. |
| 3 — Technical design | Components A (mode), B (budget + prompt), C (contract + Phase 4 granularity); data/interfaces/behaviour. |
| 4 — Design judgment | Quality attributes, 5 alternatives, accepted trade-offs; ADR 0001 accepted. |
| 5 — Execution readiness | Implementation plan, test traceability, rollout/rollback, risks. |
| 6 — Finalization | Final TDD assembled; `validation-report.json` verdict **pass**; one test-only repair (no design/prod change). |

## Definition of done

DOD-1..DOD-7 **pass**; DOD-8 **deferred** (explicitly staged). See `definition-of-done.json`.

## Validation snapshot

- `uv run python -m pytest -q` → **687 passed, 1 skipped, 21 subtests passed**.
- Targeted coverage tests → 69 passed; new `tests/test_deepwiki_scale_core.py` → 15 passed.
- `git diff --check` clean; `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` unchanged.
- Real RAGFlow catalog budget: ≥ 36 pages / ≥ 94 required topics (vs the 21-page / 42-TER collapse).

## Implemented vs deferred

**Implemented this slice**
- A: `expanded` enforces anti-compression by default; `deepwiki-scale` = compatibility alias.
- B: source-derived breadth budget rendered into `planning-topic-catalog.md`; hardened
  embedded + Gem planner prompts (fan-out, TER-per-promoted-topic, no-broad-page, budget).
- C: `plans/promoted-topic-contract.json` emitted + loader; `catalog_topic_id` carried into
  Phase 4 obligations + generated-coverage rows; proof that an omitted promoted topic fails.

**Deferred (next slice, clearly marked — not a failure)**
- A standalone Phase 4 gate that loads `plans/promoted-topic-contract.json` and fails
  end-to-end when a promoted leaf topic with evidence is missing from generated output
  (the data-contract plumbing + passthrough + omitted-topic failure proof are shipped; the
  dedicated cross-referencing gate is the next slice).
- A billed live RAGFlow E2E to confirm the hardened prompt + budget reach the source-derived
  page/topic targets (requires explicit user approval; no live calls in this run).

## Open decisions for the release owner

1. Confirm `expanded` is the official/core scale path; `deepwiki-scale` stays alias-only.
2. Approve BreadthPolicy defaults before any billed live run.
3. Approve the deferred standalone Phase 4 end-to-end enforcement slice.
