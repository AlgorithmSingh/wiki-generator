# Implementation Result — deepwiki-scale-depth-parity (M1)

## Outcome

**PASSED (non-live).** The first depth/detail-density enforcement slice is implemented,
tested, and validated. A fanned-out-but-shallow expanded **grounded** claim plan now fails
the source-derived depth gate before assembly; a plan that grounds claims proportional to its
Phase 3 mapped-evidence density passes. `baseline`/`enhancement` and the existing expanded
grounded pass cases are unchanged.

## Files changed

| File | Change |
|---|---|
| `src/wiki_generator/libs/writing/depth_budget.py` | **NEW** (315 lines). Frozen, injectable `DepthPolicy` (bounds-validated, `topic_target`), `TopicDepthTarget`, `SectionDepthBudget`, `DepthShortfall`, `PlanDepthReport`; `derive_section_depth_budget`, `evaluate_plan_depth`, `render_depth_budget_lines`. stdlib only (`math`, `dataclasses`); pure, deterministic, benchmark-quarantined. |
| `src/wiki_generator/libs/writing/claim_plan.py` | `validate_claim_plan(depth_budget=None)` appends depth shortfalls **after** the existing grounding/required-topic checks; `build_claim_plan_prompt` / `build_claim_plan_rewrite_prompt(depth_budget=None)` embed `render_depth_budget_lines`; hardened `CLAIM_PLAN_SYSTEM_INSTRUCTION`. `None` ⇒ byte-identical. |
| `src/wiki_generator/libs/writing/grounded.py` | `generate_grounded_section(depth_budget=None)` threads the budget into validation + the bounded re-prompt and records `grounded_meta['depth']` (budget + measured per-topic/total claim counts + `satisfied`). |
| `src/wiki_generator/libs/writing/__init__.py` | `run()` derives a per-section depth budget for the **expanded grounded** path only (`EXPANDED_COVERAGE_MODES` + `grounded_claim_plan`) and threads it into the prompt build + section loop. |
| `tests/test_phase4_depth_budget.py` | **NEW** (370 lines, 21 tests + 4 subtests): policy bounds/clamp, derivation, determinism, shallow-fails / detailed-passes / single-evidence-passes, none-byte-identical, grounding-not-masked, no-mutation, prompt-carries-targets / no-benchmark-leak, expanded grounded command E2E (depth audit recorded + shallow fails closed exit 5). |
| `.gitignore` | added `.sequence/` (build-sequence run dossier). |

## Behavior

- Per-topic claim target = `clamp(ceil(mapped_evidence_count / evidence_per_claim),
  min_claims_per_required_topic, max_claims_per_required_topic)` — source-derived, satisfiable,
  bounded. A 1-mapped topic targets 1 claim (no padding); a topic mapped to N ids owes ~N
  claims (capped at 8).
- Section floor = `max(min_section_claims, Σ per-topic targets)` (backstop).
- The depth gate is active **only** for `--coverage-mode expanded`/`deepwiki-scale` +
  `--grounded-claim-plan`. baseline/enhancement and freeform expanded compute nothing.
- A shallow plan fails closed (`WritingValidationFailure`, exit 5) after the bounded audited
  re-prompt (live only); no output is patched, no plan mutated.

## Scope decision recorded during implementation (repair R6)

The depth gate enforces **per-topic claim density + a section floor**. A content-block depth
dimension was removed: it preempted the existing, well-tested generated-coverage content-block
gate (it fired at claim-plan time, so `generated-coverage.json` was never written, breaking
`test_expanded_grounded_command_omitted_block_fails_exit_5`). Content-block *coverage* stays
the downstream generated-coverage gate's responsibility; the depth gate records content blocks
only as an informational count. Content-block *density* (heading depth) is M2.

## Tests run (all non-live)

| Command | Result |
|---|---|
| `uv run python -m pytest -q tests/test_phase4_depth_budget.py` | **21 passed, 4 subtests** |
| `uv run python -m pytest -q tests/test_phase4_depth_budget.py tests/test_phase4_grounded.py tests/test_phase4_generated_coverage.py tests/test_deepwiki_scale_core.py tests/test_phase2_anti_compression.py` | **125 passed, 16 subtests** |
| `uv run python -m pytest -q` (full suite) | **708 passed, 1 skipped, 25 subtests** (was 687 → +21) |
| `git diff --check` | clean |
| `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` | unchanged |
| AST scans (mutable defaults / import-time / layer / benchmark read) | clean (see `.sequence/static-analysis.json`) |

## Remaining risks / open items

- **OD1 (open):** `DepthPolicy` default thresholds are conservative seeds; release-owner
  sign-off required before any billed live run (M3).
- **M2:** content-block-level `####` heading depth + a document-level depth dashboard.
- The slice's effect on a *live* run is not asserted here (no live calls this slice); the
  non-live tests prove the gate fires, fails closed, and records depth — they do not prove the
  live planner reaches the budget on the real catalog.

## Checks not run (honest)

- `mypy`/`ruff`: not configured as required project checks → `not_run` (never promoted to
  passed) in `.sequence/static-analysis.json`. The project is not type/lint-gated.
- No live GPT/Pi/Vertex/Gemini E2E (out of scope this slice).
