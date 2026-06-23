# Phase 1/2/3 Readiness Iteration Spec

> **Status note (2026-06-22):** This remains the baseline readiness-iteration spec, but current implementation work must start with `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md`. Iteration 2 is an incremental amendment and supersedes this file where they conflict: Patch 1 broad directory refs become visible `search_hints[]` warnings when safely routed; Patch 2 malformed SectionPlan JSONL requires bounded Phase 2 repair/re-prompt or loud failure; Patch 3 diagnostic-only/known-gaps sections are not normal source-evidence sections and must not be rescued by generic BM25/vector fallback. Do not treat any forced Phase 3 run against readiness `FAIL` as Phase 4 GO.

## Amendment status: iteration on `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`

This spec is an **iteration/amendment** on the existing `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`; it is **not a replacement**. The existing Phase 3 spec is done and must remain unchanged.

This amendment tightens the upstream Phase 1 and Phase 2 contracts so Phase 3 receives a genuinely Phase-3-ready normalized plan instead of a syntactically valid plan with unresolved work orders.

## Artifact being designed

The target artifact is **not the Wiki** and not a Phase 3 `EvidencePacket`. The target artifact is a **Phase-3-ready normalized plan** whose `SectionPlan` rows are valid deterministic retrieval work orders.

Canonical readiness artifact set:

```text
plans/document-plan.json
plans/section-plans.jsonl
plans/normalization-report.md
plans/unresolved-references.jsonl
plans/phase3-readiness-report.md
```

A plan is Phase-3-ready only if Phase 3 can consume every exact retrieval lane without an LLM, guessing, per-section retries, or manual interpretation.

## Current evidence from the RAGFlow run

Phase 3 `retrieve-evidence` has been implemented and run against RAGFlow in:

```text
/Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2
```

Observed result:

- Phase 3 processed **13/13 sections**.
- Retrieval mode was **hybrid**.
- Phase 3 wrote **411 evidence items**.
- Output schemas, evidence anchors, BM25, vector files, and all-section deterministic behavior worked.
- Validation failed as `bad_underspecified_normalized_plan` for these sections:
  - `overview`
  - `architecture-subsystems`
  - `api-routes`
  - `testing`
  - `known-gaps`

Conclusion: this is an **upstream plan-quality issue**, not a Phase 3 retry-loop issue.

Concrete bad normalized-plan examples from the run:

```text
symbols[] unresolved work items:
- ragflow (/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow)
- retrieve: module layout and primary imports
- retrieve: api.apps.*
- retrieve: test function markers
- retrieve: general application code

contracts[] hint instead of operation:
- contracts/openapi.json

graph_nodes[] display label instead of node_id:
- pytest [Dependency]

derived planner artifacts treated as citeable source evidence:
- derived/planning-digest.md
- derived/planning-gaps.md
- derived/repo-summary.md
```

`derived/*` planning files are useful planner context, but they are not citeable repo evidence for Phase 3.

## Vertex AI planning status

Vertex AI integration has been smoke-tested successfully with:

- `google-genai`
- Application Default Credentials
- the Phase 2 script wrapper
- `gemini-2.5-flash`
- `gemini-2.5-pro`

Important token note:

- `gemini-2.5-pro` with **32 output tokens** failed with `MAX_TOKENS`.
- `gemini-2.5-pro` with **1024 output tokens** succeeded.
- Future planning runs should set a realistic output cap; do not use tiny caps for full plans.

Fresh test output target:

```text
/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline
```

## Quality bar for a Phase-3-ready normalized plan

A normalized plan is Phase-3-ready when every `SectionPlan` satisfies all of the following:

1. **Exact lanes contain only resolvable handles**
   - `retrieval_needs.symbols[]` contains exact `symbol_id` values only.
   - `retrieval_needs.files[]` contains real repo source paths, with valid anchors when anchors are claimed.
   - `retrieval_needs.contracts[]` contains exact `METHOD /path` operations only.
   - `retrieval_needs.tests[]` contains exact test files and, when available, test function/node identifiers.
   - `retrieval_needs.graph_nodes[]` contains exact `node_id` values from `static/nodes.jsonl` only.
   - `retrieval_needs.query_packs[]` contains canonical query-pack keys only.

2. **Broad retrieval intent is explicit but not misfiled**
   - Broad instructions like `retrieve: api.apps.*` or `retrieve: module layout and primary imports` live in `search_hints[]`, not in `symbols[]`, `contracts[]`, `files[]`, `tests[]`, or `graph_nodes[]`.

3. **Planner context is separated from evidence**
   - Digest/condensate docs such as `derived/planning-digest.md` live in `context_artifacts[]`.
   - They must not appear as active `files[]` evidence work items.

4. **Expected evidence is derived from resolvable work**
   - `expected_evidence_types[]` may require `symbols`, `contracts`, `tests`, `graph`, `files`, `queries`, `bm25`, or `vector` only when there is at least one resolvable work item or deterministic retrieval path for that type.

5. **Readiness is checked before Phase 3**
   - `plans/phase3-readiness-report.md` is written by normalization.
   - Phase 3 should be run only when the readiness gate passes, unless intentionally testing failure behavior.

## Required `SectionPlan` shape amendments

Keep the existing `SectionPlan` fields, but extend `retrieval_needs` with two explicit non-exact lanes:

```json
{
  "retrieval_needs": {
    "query_packs": ["web_routes"],
    "symbols": [
      {
        "input": "python api.apps.base_app/BaseApi#",
        "symbol_id": "python api.apps.base_app/BaseApi#",
        "resolution": "exact",
        "candidates": []
      }
    ],
    "files": [
      {
        "input": "api/apps/base_app.py",
        "path": "api/apps/base_app.py",
        "anchor": {"start_line": 1, "end_line": 80},
        "anchor_confidence": "exact_range",
        "resolution": "file_exists"
      }
    ],
    "contracts": [
      {
        "input": "GET /agents",
        "method": "GET",
        "path": "/agents",
        "operation_ref": "GET /agents",
        "json_pointer": "/paths/~1agents/get",
        "resolution": "exact"
      }
    ],
    "tests": [
      {
        "input": "test/playwright/conftest.py::pytest_sessionstart",
        "path": "test/playwright/conftest.py",
        "function": "pytest_sessionstart",
        "resolution": "exact_or_unique"
      }
    ],
    "graph_nodes": [
      {
        "input": "repo:ragflow",
        "node_id": "repo:ragflow",
        "resolution": "exact"
      }
    ],
    "search_hints": [
      {
        "text": "api.apps route handlers and FastAPI/Flask route registration",
        "scope": ["source", "query_pack:web_routes"],
        "reason": "broad recall query; not an exact symbol"
      }
    ],
    "context_artifacts": [
      {
        "path": "derived/planning-digest.md",
        "role": "planner_context",
        "citeable_as_evidence": false
      }
    ]
  }
}
```

The normalizer may preserve original LLM text in `input`, but unresolved text must not become an active exact-lane work item.

## Phase 1 Step 2/3/4 planner-facing artifact changes

### Add a compact retrieval handle catalog

Phase 1 should add or strengthen a compact planner-facing handles artifact, recommended path:

```text
derived/planning-handles.md
planner-digest/planning-handles.md
```

Purpose: give the planning LLM copyable exact handles, without uploading raw million-token indexes.

`planning-handles.md` should include compact, ranked, budget-aware sections for:

- canonical query pack keys from `queries/rules/rg/*.json`;
- representative exact `symbol_id` values from `symbols/symbols.jsonl`;
- exact source file anchors from `inventory/files.jsonl` and spans/chunks when useful;
- OpenAPI operations as exact `METHOD /path`, with operation IDs/json pointers when available;
- exact graph node IDs from `static/nodes.jsonl`, not display labels;
- test files and functions from `tests/test-files.jsonl` and `tests/pytest-collect.txt` when present;
- search-hint examples for broad topics that should not be placed in exact lanes;
- a short warning that digest artifacts are planner context, not evidence.

Example entries should be copyable:

```text
Query packs:
- web_routes
- task_workers
- cli_commands
- models_schemas
- config_keys
- config_file_keys
- env_vars
- datastore
- auth_security
- entrypoints
- llm_integrations
- plugin_registries

Symbols:
- python admin.client.http_client/HttpClient#  -> admin/client/http_client.py:26-182
- python admin.client.http_client/HttpClient#__init__(). -> admin/client/http_client.py:27-44

Contracts:
- GET /agents
- POST /agents
- GET /agents/<agent_id>
- DELETE /agents/<agent_id>

Graph nodes:
- repo:ragflow
- file:api/apps/restful_apis/agent_api.py
- sym:python test.playwright.conftest/pytest_sessionstart().

Tests:
- test/playwright/conftest.py::pytest_sessionstart
- test/playwright/conftest.py::pytest_collection_modifyitems

Search-hint examples:
- module layout and primary imports
- general application code entrypoints
- api.apps route handler family
```

### Strengthen existing Step 2/3 condensates

Existing files should expose exact handles wherever they discuss a source item:

```text
derived/planning-symbols.md
derived/planning-graph.md
derived/planning-runtime-surfaces.md
derived/planning-tests.md
derived/planning-gaps.md
derived/planning-digest.md
```

Rules:

- If a symbol is mentioned, include its exact `symbol_id` when available.
- If a route/contract is mentioned, include exact `METHOD /path`.
- If graph structure is mentioned, include exact `node_id` alongside any display label.
- If tests are mentioned, include exact test path and function/node ID when available.
- If a source file is mentioned, use repo-relative paths and anchors.
- If a broad topic has no exact handle, label it as a `search_hints[]` candidate.
- If a digest file is mentioned, label it as `context_artifact`, not evidence.

### Step 4 bundle changes

`planner-digest/planner-upload-bundle.md` should include `planning-handles.md` in deterministic order near the front, after `README_FOR_PLANNER.md` and before broad summaries.

`planner-digest/README_FOR_PLANNER.md` must explicitly tell the LLM:

- exact lanes require exact handles from `planning-handles.md` or the other condensates;
- broad requests belong in `search_hints[]`;
- digest/condensate docs belong in `context_artifacts[]` and are not citeable repo evidence;
- `contracts/openapi.json` by itself is not a contract work item; use `METHOD /path` operations.

## Phase 2 Step 1 planner prompt / Vertex instruction changes

The planner prompt must forbid vague references in exact lanes.

Required instructions:

```text
You are producing a retrieval work order, not final Wiki prose.
Use exact handles when filling exact retrieval lanes.
If you cannot name an exact handle, do not place the item in that exact lane.
Move broad or fuzzy retrieval requests into search_hints[].
Move planning digest/condensate documents into context_artifacts[].
```

Lane-specific rules:

- `symbols[]`: exact `symbol_id` only. Do not write dotted guesses, repo names, globs, or `retrieve: ...` requests.
- `files[]`: exact repo source files only. Do not put `derived/planning-*.md` here.
- `contracts[]`: exact `METHOD /path` only. Do not write `contracts/openapi.json` as a contract.
- `tests[]`: exact test file and function/node ID when available. Broad test topics go to `search_hints[]`.
- `graph_nodes[]`: exact `node_id` only. Do not write display labels such as `pytest [Dependency]`.
- `query_packs[]`: canonical keys only.
- `search_hints[]`: broad recall text such as `retrieve: api.apps.*`, `module layout`, or `test function markers`.
- `context_artifacts[]`: digest/planning files used to understand the repo, never citeable source evidence.

Vertex defaults/recommendations:

- Prefer `gemini-2.5-pro` for full planning when available.
- `gemini-2.5-flash` is acceptable for smoke tests or smaller bundles.
- Set `--max-output-tokens` high enough for the full JSON/JSONL plan; use at least `1024` for smoke tests and a larger cap for full e2e runs.
- Treat `MAX_TOKENS` on a tiny cap as a test configuration failure, not a planner-quality result.

## Phase 2 Step 2 `normalize-plan` changes

`normalize-plan` must become the deterministic owner of Phase 3 readiness.

### Schema and normalization additions

Add or normalize these fields:

```text
retrieval_needs.search_hints[]
retrieval_needs.context_artifacts[]
plans/phase3-readiness-report.md
```

Rules:

1. **Unresolved refs must not be active exact-lane work items**
   - If a symbol does not resolve to a `symbol_id`, remove it from active `symbols[]` and write it to `search_hints[]` or `unresolved-references.jsonl`.
   - If a file does not resolve to a repo source file, do not emit it in active `files[]`.
   - If a graph label does not resolve to a `node_id`, do not emit it in active `graph_nodes[]`.

2. **Contract hints must not count as contracts**
   - `contracts/openapi.json`, `API routes`, or `all routes` are hints/context only.
   - They become active `contracts[]` only if resolved to exact operations such as `GET /agents`.

3. **Graph labels must not count as graph nodes**
   - `pytest [Dependency]` is a display label, not a node ID.
   - It may become a graph node only if deterministically resolved to one exact `node_id`.

4. **Digest docs must not be emitted as source files**
   - `derived/planning-digest.md`, `derived/planning-gaps.md`, and similar files go to `context_artifacts[]`.
   - They must not satisfy `expected_evidence_types: ["files"]`.

5. **`expected_evidence_types[]` must be derived from resolvable work items**
   - Include `symbols` only if at least one exact symbol work item exists.
   - Include `contracts` only if at least one exact operation exists.
   - Include `graph` only if at least one exact graph node seed exists or a resolvable symbol/file can seed graph lookup.
   - Include `tests` only if exact test files/functions exist.
   - Include `files` only if real source files exist; context artifacts do not count.
   - Include `queries`, `bm25`, or `vector` when query packs or search hints support deterministic recall.

6. **Readiness gate**
   - Write `plans/phase3-readiness-report.md` on every normalization run.
   - The report status is `PASS` only when no exact lane contains unresolved, ambiguous, hint-only, display-label-only, or context-only items.
   - The report must list per-section readiness failures with source fields and suggested fix path.
   - Phase 3 scripts should check this report before calling `retrieve-evidence`.

### Readiness report minimum contents

```text
# Phase 3 Readiness Report

Status: PASS|FAIL
Bundle: /path/to/bundle
Document plan: plans/document-plan.json
Section plans: plans/section-plans.jsonl
Sections: N

## Exact-lane checks
- symbols: pass/fail counts
- files: pass/fail counts
- contracts: pass/fail counts
- tests: pass/fail counts
- graph_nodes: pass/fail counts
- query_packs: pass/fail counts

## Search hints
- count by section
- broad requests moved out of exact lanes

## Context artifacts
- paths by section
- all marked non-citeable

## Expected evidence derivation
- evidence types retained/dropped by section

## Failures
- section_id
- field
- invalid input
- reason
- suggested upstream fix
```

## Phase 3 consumption amendments

This section amends Phase 3 consumption only; it does not rewrite the original Phase 3 spec.

Phase 3 should consume the new fields as follows:

- `search_hints[]` are BM25/vector recall query text.
  - They may also constrain recall by scope, for example `query_pack:web_routes` or `tests`.
  - They never become exact symbol/file/contract/test/graph evidence by themselves.
- `context_artifacts[]` are non-citeable planner context.
  - Phase 3 may include their paths in `work_order.context_artifacts` for traceability.
  - Phase 3 must not cite them as repo evidence and must not count them as `files` evidence.
- All-sections deterministic behavior remains unchanged.
- There is still no Phase 3 retry loop and no product per-section retry mode.
- If readiness passes but Phase 3 still fails with `bad_underspecified_normalized_plan`, treat that as a readiness-gate bug or missing normalization rule.

## Failure categories retained from Phase 3

The existing Phase 3 spec defines three product failure categories. This iteration keeps them:

1. **`bad_missing_input_artifact`**
   - Bundle, retrieval substrate, BM25, vectors, plan files, or source artifacts are missing, corrupt, stale, or inconsistent.

2. **`bad_underspecified_normalized_plan`**
   - The normalized plan is syntactically valid but not a sufficient retrieval work order.
   - The RAGFlow failure above is category #2.

3. **`retriever_implementation_bug`**
   - Inputs satisfy contracts, but Phase 3 crashes, writes invalid packets, cites nonexistent anchors, or behaves nondeterministically.

This iteration specifically reduces category #2 by:

- giving the planner exact handles before it writes the plan;
- forbidding vague items in exact lanes;
- moving broad requests into `search_hints[]`;
- moving digest docs into `context_artifacts[]`;
- deriving `expected_evidence_types[]` only from resolvable work;
- adding `plans/phase3-readiness-report.md` and a pre-Phase-3 readiness gate.

## Acceptance criteria

This amendment is satisfied when:

- `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` remains unchanged.
- A new spec file exists at `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_SPEC.md`.
- Phase 1 Step 2/3/4 produce or package a compact retrieval handle catalog.
- Planner-facing artifacts expose exact symbol IDs, source anchors, query pack keys, OpenAPI `METHOD /path` operations, graph node IDs, test files/functions, and search-hint examples.
- Phase 2 Step 1 prompt/instructions forbid vague references in exact lanes.
- `normalize-plan` emits `search_hints[]` and `context_artifacts[]`.
- `normalize-plan` does not emit unresolved refs as active exact-lane work items.
- `normalize-plan` does not count `contracts/openapi.json` as a contract unless exact operations are selected.
- `normalize-plan` does not count graph display labels as graph nodes unless they resolve to exact `node_id` values.
- `normalize-plan` does not place `derived/planning-*.md` files in `files[]` or count them as citeable evidence.
- `expected_evidence_types[]` is consistent with resolvable work items.
- `plans/phase3-readiness-report.md` is written and checked before Phase 3.
- Phase 3 consumes `search_hints[]` for BM25/vector recall.
- Phase 3 treats `context_artifacts[]` as non-citeable context.
- Phase 3 continues all-section deterministic behavior with no retry loop.

Negative acceptance checks for the RAGFlow-style bad plan:

```text
FAIL if symbols[] contains: retrieve: api.apps.*
FAIL if symbols[] contains: retrieve: module layout and primary imports
FAIL if contracts[] contains only: contracts/openapi.json
FAIL if graph_nodes[] contains: pytest [Dependency]
FAIL if files[] contains: derived/planning-digest.md
FAIL if expected_evidence_types includes symbols/contracts/graph/files solely because of those invalid entries
```

## Fresh end-to-end testing plan

Use fresh output under:

```text
/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline
```

Recommended target repo for parity with the failed run:

```text
/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow
```

Run from the implementation repo:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
export TARGET_REPO=/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow
export OUT=/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline
```

Clean setup, if intentionally starting over:

```bash
rm -rf "$OUT"
mkdir -p "$OUT"
```

### 1. Phase 1 Step 1 — decompose

```bash
scripts/phase1_step1_decompose.sh \
  --repo "$TARGET_REPO" \
  --out "$OUT"
```

Expected gate:

- required raw artifacts exist;
- warnings are recorded but do not hide missing required artifacts.

### 2. Phase 1 Step 2 — condense, including handles

```bash
scripts/phase1_step2_condense.sh \
  --out "$OUT" \
  --budget-tokens 250000
```

Expected gate:

- existing `derived/planning-*.md` files exist;
- new/strengthened handle catalog exists, recommended `derived/planning-handles.md`;
- handle catalog includes symbol IDs, operations, graph node IDs, tests, query pack keys, and search-hint examples.

### 3. Phase 1 Step 3 — digest

```bash
scripts/phase1_step3_digest.sh \
  --out "$OUT" \
  --budget-tokens 250000
```

Expected gate:

- `derived/planning-digest.md` exists;
- it labels digest content as planner context, not source evidence.

### 4. Phase 1 Step 4 — planner bundle

```bash
scripts/phase1_step4_bundle.sh \
  --out "$OUT" \
  --budget-tokens 250000
```

Expected gate:

- `planner-digest/planner-upload-bundle.md` exists;
- `planner-digest/upload-list.md` passes budget;
- handle catalog is included in the planner bundle;
- raw giant artifacts remain excluded.

### 5. Phase 2 Step 1 — Vertex plan

Use ADC and a realistic output cap. Example:

```bash
scripts/phase2_step1_plan.sh \
  --out "$OUT" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --location "${GOOGLE_CLOUD_LOCATION:-us-central1}" \
  --model gemini-2.5-pro \
  --max-output-tokens 8192
```

Smoke alternative:

```bash
scripts/phase2_step1_plan.sh \
  --out "$OUT" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --model gemini-2.5-flash \
  --max-output-tokens 4096
```

Expected gate:

- `plans/phase2-gemini-response.md` exists;
- provider response did not stop because of `MAX_TOKENS`;
- raw response includes `DocumentPlan` and `SectionPlan` data.

### 6. Phase 2 Step 2 — normalize plan and readiness gate

```bash
scripts/phase2_step2_normalize_plan.sh \
  --out "$OUT" \
  --provider gemini
```

Expected gate:

- `plans/document-plan.json` exists;
- `plans/section-plans.jsonl` exists;
- `plans/normalization-report.md` exists;
- `plans/phase3-readiness-report.md` exists;
- readiness status is `PASS` before proceeding.

If readiness fails, expected behavior is to stop here and fix Phase 1 planner artifacts, Phase 2 prompt instructions, or normalization rules. Do not proceed to Phase 3 as a normal product run.

### 7. Phase 1 Step 5 — hybrid retrieval substrate

```bash
scripts/phase1_step5_build_retrieval.sh \
  --out "$OUT" \
  --rebuild \
  --smoke-query "api routes"
```

Expected gate:

- `rag/retrieval-capabilities.json` reports `retrieval_mode: hybrid` or vectors enabled;
- `rag/bm25.sqlite` exists and is readable;
- `rag/vectors.faiss` exists;
- vector metadata exists and count matches FAISS;
- `rag/retrieval-substrate-report.md` reports pass.

### 8. Phase 3 — retrieve evidence

```bash
scripts/phase3_retrieve_evidence.sh \
  --out "$OUT" \
  --with-vectors
```

Expected gate:

- Phase 3 processes all sections;
- `evidence/evidence-manifest.json` exists;
- `evidence/evidence-packets.jsonl` exists;
- `evidence/packets/<section_id>.json` exists for every planned section;
- `evidence/retrieval-validation.json` status is `pass` if readiness passed;
- no evidence item cites `plans/*` or `derived/planning-*.md` as repo evidence;
- failures, if any, are categorized correctly:
  - missing/corrupt substrate -> `bad_missing_input_artifact`;
  - readiness passed but plan still underspecified -> readiness-gate/normalizer bug to fix;
  - invalid evidence output on valid inputs -> `retriever_implementation_bug`.

## Recommended script/code work items, not implemented here

Do not implement these in this spec-writing task. Recommended follow-up work:

1. **Phase 1 handles artifact**
   - Add `derived/planning-handles.md` generation.
   - Copy it into `planner-digest/`.
   - Include it in `planner-upload-bundle.md` and `upload-list.md`.
   - Add tests for exact handle presence and raw-artifact exclusion.

2. **Planner instructions**
   - Update `planner-digest/README_FOR_PLANNER.md`, Gemini Gem instructions, and kickoff prompt.
   - Add explicit exact-lane vs `search_hints[]` vs `context_artifacts[]` examples.
   - Raise script default/output guidance so full plans are not run with tiny token caps.

3. **Plan schema and normalization**
   - Extend `SectionPlan` schema with `search_hints[]` and `context_artifacts[]`.
   - Add resolvers for contracts, graph node IDs, tests, and digest/context artifacts.
   - Ensure unresolved/hint-only/display-label items are removed from active exact lanes.
   - Derive `expected_evidence_types[]` from resolvable items only.
   - Write `plans/phase3-readiness-report.md`.
   - Add strict readiness checks and tests.

4. **Scripts / runbook**
   - Add a readiness check to `scripts/phase2_step2_normalize_plan.sh` or a dedicated `phase2_step3_check_readiness.sh`.
   - Make `scripts/phase3_retrieve_evidence.sh` fail early if readiness report exists and is not `PASS`.
   - Update `RUNBOOK.md` with the fresh e2e flow under `11-testing-pipeline`.

5. **Phase 3 consumers**
   - Add `search_hints[]` query text into BM25/vector query construction.
   - Preserve `context_artifacts[]` in packet work-order metadata only.
   - Add validation that context artifacts are never cited as evidence.
   - Add regression tests using the five RAGFlow failure sections.
