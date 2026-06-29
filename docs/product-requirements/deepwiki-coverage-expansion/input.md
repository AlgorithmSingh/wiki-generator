# Captured Input

## Original user request

```text
Task: Create a PRD for increasing generated wiki coverage toward a DeepWiki-style hierarchical page plan.

Use the PRD Companion phase guide as the format/process reference:
/Users/ankitsingh/Documents/my-pi-ai-tts-setup/4-PRD-Companion/3-phases/round-2

Output location in this repo:
/Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator/docs/product-requirements/deepwiki-coverage-expansion/

Required output files:
- README.md — brief workspace index.
- input.md — captured user/context input.
- artifacts/final_prd.md — final PRD.
- artifacts/traceability_matrix.md — map requirements to sources, acceptance criteria, and evaluation gates.
- eval/findings.md — PRD review/validation findings.
- phase_state.json — concise phase/gate state.
- traces/assumptions.jsonl, traces/decisions.jsonl, traces/harness_trace.jsonl — minimal durable traces.

Primary product idea to capture:
We should not just make the current 22 sections longer. Move toward a DeepWiki-style hierarchical page plan.
- Current generated wiki: 22 sections, concise, grounded.
- Benchmark DeepWiki export: 62 page blocks, subsystem-planned, with per-page “Relevant source files.”
- Likely missing ingredient: repo-derived page/subtopic discovery + per-page source selection before Phase 3 evidence retrieval.
- Best next direction:
  1. Build a repo-derived expanded topic/page catalog.
  2. Plan parent/child pages such as Deployment, Frontend, LLM Integration, Document Processing, Backend API, Agents/Workflow, Retrieval/Search, Memory, Admin/Ops.
  3. For each page, deterministically select relevant files/symbols/spans.
  4. Retrieve evidence per page.
  5. Use the grounded claim-plan renderer per page.
  6. Evaluate coverage by page/topic traceability, not benchmark copying.
- Important caveat from reverse-engineer.md: benchmark was indexed at commit d32e05d5 while local RAGFlow run used a different commit, so benchmark headings are breadth signals only, not source truth.
- Big implication: coverage expansion is primarily a Phase 1/Phase 2 planning problem, not a Phase 4 writing problem.

Read and use these project inputs:
- /Users/ankitsingh/Documents/deep-wiki/reverse-engineer.md
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/GPT55_XHIGH_BENCHMARK_COMPARISON.md
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_GPT55_XHIGH.md
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/COVERAGE_EXPANSION_DEEP_RESEARCH.md
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/OFFICIAL_LIVE_E2E_RESULT.md
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/wiki/metadata/generated-coverage.json
- /Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e/wiki/metadata/citation-manifest.json
- /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator/docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md
- /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator/docs/handoffs/not-done/HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md

Constraints:
- Treat /Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md as benchmark-only, not citeable evidence and not source truth.
- Do not propose copying benchmark headings into final generated output without repo evidence.
- Do not propose output patching or generic heal/retry loops.
- Preserve strict validators and deterministic Phase 3 retrieval.
- Bounded repair is allowed only for LLM-authored plans/claim plans with exact diagnostics and hard caps.
- The PRD is product/requirements focused, not a detailed implementation design. Leave module-level architecture to the later TDD.

PRD content requirements:
- Executive summary.
- Problem statement and opportunity.
- Stakeholders/users.
- Goals, non-goals, and success metrics.
- Scope: in-scope/out-of-scope.
- User/product requirements with IDs.
- Business/product rules with IDs.
- Quality attributes with measurable acceptance criteria.
- Data/interface requirements at product level.
- Acceptance criteria and validation gates.
- Risks, assumptions, open decisions.
- Traceability back to the input sources above.

Keep it practical and implementation-ready, but do not edit code. Do not commit.
```

## Source inventory read for this PRD

- `reverse-engineer.md` — establishes the 62-page benchmark shape, per-page relevant source files, exact-line citation pattern, likely source-aware planning pipeline, and commit mismatch caveat.
- `GPT55_XHIGH_BENCHMARK_COMPARISON.md` — establishes current generated wiki scale, validation status, 22 sections, 53/53 generated topics, 425 distinct citations, and breadth/depth gaps.
- `COVERAGE_EXPANSION_GPT55_XHIGH.md` — provides artifact-first recommendations: source-derived facets/page profiles, hierarchical planning, evidence portfolios, strict validators, no output patching.
- `COVERAGE_EXPANSION_DEEP_RESEARCH.md` — synthesizes upstream producer changes, repository-derived topic catalog, topic→plan→evidence→output traceability, and staged evaluation.
- `OFFICIAL_LIVE_E2E_RESULT.md` — records official live Vertex/Gemini grounded E2E status: PASS, enhancement mode, deterministic Phase 3 retrieval, grounded Phase 4, 22 sections, 53/53 generated coverage, 425 citations.
- `wiki/metadata/generated-coverage.json` — confirms generated-coverage schema/status and the section/topic matrix: 22 sections, 53 required topics, all covered.
- `wiki/metadata/citation-manifest.json` — confirms citation manifest schema/counts: 425 distinct citations and 725 total occurrences, with evidence lanes and confidence levels.
- `PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md` — supplies existing enhancement contracts and guardrails: planned coverage, evidenced coverage, generated coverage, grounded claim-plan rendering, strict validators, no benchmark evidence.
- `HANDOFF_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION.md` — supplies current status, implemented slices, live-run outcomes, remaining decisions, and hard guardrails.
- PRD Companion phase guide `round-2` — used as process/format reference: run folder, evidence before advancement, gates 0–9, traceability, validation, repair discipline, and eval findings.

## Key captured facts

- Current official generated wiki is valid and grounded for its planned scope, but concise: `index.md` plus 22 section files, 53/53 generated topics covered, 425 distinct citations.
- Benchmark DeepWiki export has 62 page blocks and is much larger/deeper, but it is benchmark-only and was indexed at a different commit (`d32e05d5`), so it is not source truth.
- The coverage gap is primarily caused by coarse upstream planning and page/topic discovery, not by insufficient Phase 4 prose length.
- The desired next product direction is a repository-derived expanded topic/page catalog, hierarchical parent/child planning, deterministic per-page source selection, per-page evidence retrieval, grounded claim-plan rendering, and source-derived coverage evaluation.
