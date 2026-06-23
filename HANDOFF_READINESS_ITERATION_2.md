# Handoff — Phase 1/2/3 Readiness Iteration 2 (CURRENT)

> **This is the current readiness handoff.** It supersedes `HANDOFF_READINESS_ITERATION.md` and `HANDOFF_STEP5.md` as the source of truth for readiness/Phase-3 state. Source spec: `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md` (do not modify `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`).

Status: **implemented, tested (175 passed / 1 skipped), and validated end-to-end on RAGFlow through Phase 3 without `--force`.** Phase 4 not started (out of scope).

## 1. Problem and context

Make Phase 3 receive a genuinely *Phase-3-ready* normalized plan by implementing the three Iteration 2 patches. The driving run failed readiness on real planner mistakes:

- **Patch 1** — directory-like `file_anchors` (`agent/component/`, `rag/graphrag/`, `test/unit_test/`…) were blocking failures. They are valid *neighbourhoods*, not citeable files: route them to `search_hints[]` as visible **warnings**, not failures.
- **Patch 2** — a malformed `SectionPlan` JSONL row (`llm-integration`, a bare string after `"verification_needs":[]`) was silently skipped, then masked as `no_retrieval_signal`. Malformed required rows must never silently disappear: deterministic repair when obvious, else a bounded Vertex/Gemini repair, else fail loudly.
- **Patch 3** — `derived/planning-gaps.md` (an internal *diagnostic*) became a normal `known-gaps` wiki section with no real evidence. Diagnostics are not source evidence; no-signal sections must not be rescued by generic BM25/vector fallback.

**Constraints / decisions (held):** `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` unchanged; Phase 3 stays deterministic + LLM-free with no retry/debug loop and no `--section` mode; Phase 3 never invokes repair; the only LLM is the Phase 2 `plan-repair` step (bounded ≤2 attempts, audited, fails loudly); no tiny Gemini output caps; no raw giant indexes uploaded. Two genuine planner near-misses in the existing raw plan (`conf/config.yaml`, `rag.flow.parser/Parser#`) cannot resolve deterministically — they require the bounded LLM repair, which is why `plan-repair` exists.

## 2. Approach and work completed

Deterministic patches in the normalizer/parser/readiness; one bounded LLM repair as the escape hatch; hardened all four planner prompt surfaces; then validated on the real RAGFlow bundle. **4 files created, 14 modified** (+ 3 handoff docs in this commit).

**Created (4):**
- `src/wiki_generator/libs/plan_normalization/repair.py` — bounded Phase 2 Gemini repair (verbatim raw + structured errors + handle catalog → corrected artifacts; ≤2 attempts; 1:1 sections, diagnostic-only removable/convertible; strict re-validate; audited under `plans/repair/`; fails loudly). Client injectable for tests.
- `src/wiki_generator/libs/commands/plan_repair.py` — `plan-repair` CLI command.
- `scripts/phase2_step1b_repair_plan.sh` — repair script wrapper.
- `tests/test_phase2_readiness.py` — Patch 1/2/3 + bounded-repair + prompt-snapshot unit tests.

**Modified (key):**
- `libs/context_docs.py` — shared predicates (producer+checker, no drift): `is_diagnostic_artifact`, `section_role`/`is_provenance_section`, `section_has_retrieval_signal`.
- `libs/plan_normalization/lookups.py` — `is_directory_like` (inventory-only, deterministic).
- `libs/plan_normalization/normalize.py` — Patch 1 directory routing to `search_hints[]` w/ traceability; `section_role`; threads parse diagnostics.
- `libs/plan_normalization/parse.py` — Patch 2 structured diagnostics, no silent skip, deterministic bare-string repair.
- `libs/plan_normalization/writer.py` — readiness gate: dir-routed = warnings; `section_plan_jsonl_parse_error` primary; `diagnostic_only_user_section`; provenance excluded; directory-in-active-lane defense-in-depth; new report sections.
- `libs/evidence/__init__.py` — Phase 3: no generic fallback for no-signal sections; provenance packet handled outside evidence lanes.
- `cli.py`, `libs/commands/plan.py`, `libs/digest/upload_package.py`, `gemini-gem/{GEM_INSTRUCTIONS,KICKOFF_PROMPT}.md` — register `plan-repair`; Patch 1/2/3 prompt guidance on all four planner surfaces.
- `tests/test_phase3.py`, `README.md`, `RUNBOOK.md` (see §4b), and the status notes.

**Validated run:** `/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline/runs/iter2-validation-20260622`
`normalize-plan` (FAIL: 4 genuine errors, 6 dir warnings, 1 deterministic repair) → `plan-repair` (gemini-2.5-pro, 1 attempt: 3 refs fixed surgically, known-gaps → `role: provenance`) → readiness **PASS** (0 failures, 6 warnings) → Phase 3 without `--force` → **PASS** (hybrid, 16/16, 512 items, all contract checks pass, no `derived/`/`plans/` citations, known-gaps = 0 evidence/no fallback).

## 3. Suggested review

**Read first:** `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md`, then `libs/plan_normalization/writer.py` (`_readiness_failures`), `parse.py` (`_loads_jsonl`, `_repair_bare_string_after_empty_array`), `repair.py` (`repair_plan` loop + `build_repair_user`), `libs/evidence/__init__.py` (`_build_packet`/`_provenance_packet`).

**Verify (commands):**
```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
source .venv/bin/activate && python -m pytest -q          # expect 175 passed, 1 skipped
git diff --stat PHASE3_EVIDENCE_RETRIEVAL_SPEC.md          # expect empty (unchanged)

# Re-validate end-to-end (needs GEMINI_API_KEY for plan-repair):
FRESH=/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline/runs/iter2-validation-20260622
python -m wiki_generator normalize-plan --bundle "$FRESH" --raw-response "$FRESH/plans/phase2-gemini-response.md"  # FAIL (expected)
python -m wiki_generator plan-repair    --bundle "$FRESH" --raw-response "$FRESH/plans/phase2-gemini-response.md"  # readiness PASS
bash scripts/phase3_retrieve_evidence.sh --out "$FRESH" --with-vectors   # PASS, no --force
```

**Extra attention / follow-up:**
- `plan-repair` makes a live Gemini call; reruns are non-deterministic. The deterministic patches (1, 2-bare-string, 3-detection) need no LLM — only the two genuine planner near-misses do.
- Adversarial review (18 agents) found **0 blockers**; the one major (verbatim raw must reach the repair model) is fixed. Two minors consciously left, both **fail loudly** (cannot cause a silent pass): the format-#4 markdown-heading fallback pre-filters non-`{` lines; malformed-row→section attachment uses the raw (not slugified) id and falls to the artifact bucket.
- Phase 4 is **unblocked** for the validated bundle but **not started**. Do not treat stale pre-patch artifacts or any forced Phase-3-after-`FAIL` output as a Phase 4 GO.
