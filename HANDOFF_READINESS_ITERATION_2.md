# Handoff — Phase 1/2/3 Readiness Iteration 2 (baseline; Phase 4 currently blocked)

> **This remains the Iteration 2 readiness baseline handoff.** It supersedes `HANDOFF_READINESS_ITERATION.md` and `HANDOFF_STEP5.md` for the implemented Iteration 2 state. Latest live-Phase-4 blocker/spec amendment: `PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md` (now **implemented and tested non-live**; do not modify `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`).

Status: **Iteration 2 is implemented, tested, and accepted end-to-end on RAGFlow through Phase 3 without `--force`; the Iteration 3 exact-coverage/public-route fixes and the Phase 4 Iteration 2 shell-variable path-synthesis fix are also in the current Phase 3/4 baseline.** The accepted Phase 1-3 bundle is `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038`. The Phase 4 shell-variable fix (`PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md`) is implemented: the expanded literal `/ragflow/conf/service_conf.yaml` is now a rewriteable `synthesized_identifier`, not a terminal `invented_identifier`, and a bounded rewrite to an exact evidence token passes. Live Phase 4 is now **blocked only on explicit user approval for another billed retry**.

## 1. Problem and context

Make Phase 3 receive a genuinely *Phase-3-ready* normalized plan by implementing the three Iteration 2 patches. The driving run failed readiness on real planner mistakes:

- **Patch 1** — directory-like `file_anchors` (`agent/component/`, `rag/graphrag/`, `test/unit_test/`…) were blocking failures. They are valid *neighbourhoods*, not citeable files: route them to `search_hints[]` as visible **warnings**, not failures.
- **Patch 2** — a malformed `SectionPlan` JSONL row (`llm-integration`, a bare string after `"verification_needs":[]`) was silently skipped, then masked as `no_retrieval_signal`. Malformed required rows must never silently disappear: deterministic repair when obvious, else a bounded Vertex/Gemini repair, else fail loudly.
- **Patch 3** — `derived/planning-gaps.md` (an internal *diagnostic*) became a normal `known-gaps` wiki section with no real evidence. Diagnostics are not source evidence; no-signal sections must not be rescued by generic BM25/vector fallback.

**Constraints / decisions (held):** `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` unchanged; Phase 3 stays deterministic + LLM-free with no retry/debug loop and no `--section` mode; Phase 3 never invokes repair; Phase 2 planning is LLM-backed and `plan-repair` is the only bounded/audited repair escape hatch (≤2 attempts, fails loudly); no tiny Gemini output caps; no raw giant indexes uploaded. Two genuine planner near-misses in the original raw plan (`conf/config.yaml`, `rag.flow.parser/Parser#`) cannot resolve deterministically — they require the bounded LLM repair, which is why `plan-repair` exists.

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

**Historical Iteration 2 validation run:** `/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline/runs/iter2-validation-20260622`
`normalize-plan` (FAIL: 4 genuine errors, 6 dir warnings, 1 deterministic repair) → `plan-repair` (gemini-2.5-pro, 1 attempt: 3 refs fixed surgically, known-gaps → `role: provenance`) → readiness **PASS** (0 failures, 6 warnings) → Phase 3 without `--force` → **PASS** (hybrid, 16/16, 512 items, all contract checks pass, no `derived/`/`plans/` citations, known-gaps = 0 evidence/no fallback). This run remains useful history, but it is no longer the preferred Phase 4 input.

**Current fresh acceptance run / Phase 4 gate:** `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038`
Fresh run artifacts include `command-manifest.tsv`, `command-transcript.log`, exit codes, `validate_acceptance.py`, and `EXPERIMENT_RESULT.md`. Result: tests **175 passed / 1 skipped**, readiness **PASS** (0 failures, 0 warnings, 16 sections), Phase 3 without `--force` **PASS** (hybrid, 16/16, 569 evidence items, `failure_category: null`), 0 source evidence from `derived/` or `plans/`, 0 `no_retrieval_signal` sections, no normal `known-gaps` evidence, and `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` unchanged. The latest live run at `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934` refreshed deterministic Phase 3 successfully and verified citeable `rag/llm/embedding_model.py` plus public-route evidence, but Phase 4 failed closed on shell-expanded `/ragflow/conf/service_conf.yaml`; do not retry live Phase 4 until `PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md` is implemented and tested.

## 3. Suggested review

**Read first:** `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md`, then `libs/plan_normalization/writer.py` (`_readiness_failures`), `parse.py` (`_loads_jsonl`, `_repair_bare_string_after_empty_array`), `repair.py` (`repair_plan` loop + `build_repair_user`), `libs/evidence/__init__.py` (`_build_packet`/`_provenance_packet`).

**Verify (commands):**
```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
source .venv/bin/activate && python -m pytest -q          # expect 175 passed, 1 skipped
git diff --stat PHASE3_EVIDENCE_RETRIEVAL_SPEC.md          # expect empty (unchanged)

# Inspect the fresh accepted Phase 1-3 bundle used to reopen Phase 4:
FRESH=/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038
sed -n '1,80p' "$FRESH/EXPERIMENT_RESULT.md"                         # expect Verdict PASS
sed -n '1,40p' "$FRESH/plans/phase3-readiness-report.md"              # expect Status PASS / Failures 0
python -m json.tool "$FRESH/evidence/retrieval-validation.json" | head # expect status pass / hybrid / 569 items
rg --fixed-strings -- '--force' "$FRESH/command-manifest.tsv"          # expect no matches
```

**Extra attention / follow-up:**
- `plan-repair` makes a live Gemini call; reruns are non-deterministic. The deterministic patches (1, 2-bare-string, 3-detection) need no LLM — only the two genuine planner near-misses do.
- Adversarial review (18 agents) found **0 blockers**; the one major (verbatim raw must reach the repair model) is fixed. Two minors consciously left, both **fail loudly** (cannot cause a silent pass): the format-#4 markdown-heading fallback pre-filters non-`{` lines; malformed-row→section attachment uses the raw (not slugified) id and falls to the artifact bucket.
- Phase 4 Iteration 2 (`PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md`) is **implemented and validated non-live**. The prompt forbids shell/env-variable expansion; the validator classifies a deterministic one-step shell-variable expansion absent from evidence as a rewriteable `synthesized_identifier` (distinct from terminal `invented_identifier`) and feeds the rewrite the exact evidence tokens to use instead. It is rewriteable but never passable — final validation still requires exact tokens, and true inventions, routes, directory+filename joins, and multi-step/ambiguous derivations stay terminal. Proven by unit tests plus a fake-provider rewrite, and re-checked against the real `20260623-172934` deployment artifacts. `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` is unchanged. Before retrying live Phase 4, obtain explicit user approval for another billed retry; do not treat stale pre-patch artifacts, old `11-testing-pipeline` outputs, or any forced Phase-3-after-`FAIL` output as a Phase 4 GO.
