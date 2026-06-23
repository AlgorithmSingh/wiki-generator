# Phase 1/2/3 Readiness Iteration 2 Spec

## Status: Draft / incremental amendment

This document is **Iteration 2** of the Phase 1/2/3 readiness follow-up work. It is an **incremental amendment** on top of `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_SPEC.md` and does **not** replace that first readiness iteration spec.

It also does **not** replace or modify `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`. Phase 3 remains deterministic and LLM-free.

Current scope for this document: **Patch 1, Patch 2, and Patch 3**.

Final Phase 4 go/no-go material remains a placeholder at the end of this file. Patch 3 is now filled from the latest root-cause analysis.

## Patch 1 title

**Directory-like file anchors should become visible readiness warnings after successful routing to `search_hints[]`, not blocking readiness failures.**

## Non-expert explanation: neighborhood name vs house address

A value like `agent/component/` is a useful **neighborhood name**: it tells retrieval to look around the Agent Component area of the repository.

But `file_anchors[]` requires a citeable **house address**: a concrete file such as `agent/component/base.py`, ideally with a line range or span that Phase 3 can cite.

Patch 1 says:

- neighborhood names are real and useful;
- they are not hallucinations;
- they must not stay in exact citation lanes like `file_anchors[]`;
- once the normalizer moves them to `search_hints[]`, readiness should warn about them but should not fail solely because they existed in the planner's raw output.

## Relationship to existing specs

This Iteration 2 spec narrows and clarifies one readiness semantics issue discovered after the first readiness iteration.

It preserves these existing rules from the first readiness iteration and Phase 3 spec:

- exact lanes must contain exact, resolvable handles;
- broad retrieval intent belongs in `search_hints[]`;
- derived planner context is not citeable evidence;
- Phase 3 consumes normalized work orders deterministically;
- Phase 3 does not call an LLM;
- Phase 3 does not perform manual retry/debug loops;
- there is no product `--section` mode proposed here.

This spec only amends how readiness classifies a narrow case:

> A directory-like or trailing-slash path that the planner originally placed in `file_anchors[]`, but that the normalizer has already removed from exact lanes and preserved in `search_hints[]`.

## Patch 1 rationale

A fresh readiness report failed partly because the planner placed folder-like references in `file_anchors[]` for the `agent-subsystem` section, including:

```text
agent/component/
agent/plugin/
agent/sandbox/
```

These references are semantically meaningful for RAGFlow:

- `agent/component` contains component base/lifecycle abstractions and concrete components.
- `agent/plugin` contains plugin-system and LLM tool plugin material.
- `agent/sandbox` contains sandboxed code execution backend material.

The planner likely had a reasonable semantic reason for choosing them. The Agent Subsystem section is explicitly about components, plugins, and sandboxed execution, and Gemini likely generalized from path prefixes and upload-bundle signals.

However, the output was still a lane/format mistake:

- `file_anchors[]` is an exact citation lane.
- It requires exact citeable file handles, such as `agent/component/base.py`.
- Directory/neighborhood paths such as `agent/component/` are not exact file anchors.

The normalizer then performed the correct defensive action: it moved these broad directory references out of active exact lanes and into `search_hints[]`, where Phase 3 can use them as recall text for BM25/vector retrieval instead of as direct citation evidence.

Phase 3 subsequently found useful evidence through exact handles, graph traversal, BM25, and vector retrieval, including examples such as:

```text
agent/component/base.py
agent/plugin/llm_tool_plugin.py
agent/sandbox/sandbox_spec.md
agent/plugin/README.md
internal/agent/tool/code_exec_sandbox_design.md
docs/guides/agent/agent_component_reference/agent.mdx
```

Therefore, this is not a retriever bug and not evidence that the first readiness iteration failed broadly. It is a narrow readiness semantics and planner-guidance patch.

## Problem statement

The readiness gate currently risks over-classifying already-normalized directory-like file-anchor mistakes as blocking failures.

For Patch 1, the problematic pattern is:

1. The planner emits a broad path-like reference in `file_anchors[]`, commonly ending in `/`.
2. The reference is a real repository area and useful retrieval intent.
3. The reference is not a citeable file.
4. The normalizer removes it from exact file lanes.
5. The normalizer preserves it in `search_hints[]`.
6. The readiness report still treats the original broad reference as a blocking failure.

The readiness report should distinguish between two cases:

- **Blocking failure:** a directory-like reference remains in an active exact lane, or the broad intent is dropped entirely.
- **Warning only:** a directory-like reference was removed from the exact lane and preserved in `search_hints[]` for deterministic recall.

## Observed evidence

### Raw planner behavior

For the `agent-subsystem` section, the planner used directory-like values as file anchors:

```text
agent/component/
agent/plugin/
agent/sandbox/
```

These are invalid as exact file anchors because they do not identify individual citeable files.

### Semantic validity

The references were not hallucinated. They point to meaningful RAGFlow neighborhoods relevant to the section:

- `agent/component/` corresponds to the component subsystem.
- `agent/plugin/` corresponds to plugin and LLM tool plugin code/docs.
- `agent/sandbox/` corresponds to sandboxed code execution design/backend material.

### Normalizer behavior

The normalizer defensively moved the directory-like values out of active exact lanes and into `search_hints[]`.

That is the desired normalization strategy because it preserves planner intent while keeping exact lanes citeable.

### Phase 3 retrieval behavior

Phase 3 found useful evidence through deterministic retrieval paths, including exact handles, graph, BM25, and vector search. Representative evidence included:

```text
agent/component/base.py
agent/plugin/llm_tool_plugin.py
agent/sandbox/sandbox_spec.md
agent/plugin/README.md
internal/agent/tool/code_exec_sandbox_design.md
docs/guides/agent/agent_component_reference/agent.mdx
```

This confirms the broad references were useful recall hints, but they still were not exact citations.

## Expected behavior after Patch 1

### Planner behavior

The planner must be told more explicitly:

- `file_anchors[]` accepts exact files only.
- Directory paths are invalid in `file_anchors[]`, including values ending in `/`.
- If the planner knows a broad subsystem but not a specific file, it must use `search_hints[]`.
- If the planner can name representative files, it should use those exact files in `file_anchors[]` and optionally keep broad wording in `search_hints[]`.

Good examples:

```json
{
  "file_anchors": [
    "agent/component/base.py",
    "agent/plugin/llm_tool_plugin.py",
    "agent/sandbox/sandbox_spec.md"
  ],
  "search_hints": [
    "agent component lifecycle and concrete components",
    "agent plugin system and LLM tool plugins",
    "agent sandboxed code execution backend"
  ]
}
```

Bad examples:

```json
{
  "file_anchors": [
    "agent/component/",
    "agent/plugin/",
    "agent/sandbox/"
  ]
}
```

### Normalizer behavior

When the normalizer sees a directory-like value in `file_anchors[]` or the equivalent normalized file lane, it must classify it deterministically.

A value is directory-like when any of the following is true:

- it ends with `/`;
- it resolves to a repository directory rather than a file;
- it is a known path prefix that matches multiple files and does not name an exact file;
- it is explicitly marked by the planner as a subsystem/path neighborhood rather than a file.

For directory-like values, the normalizer must:

1. Remove the value from active exact file lanes.
2. Add or merge a corresponding entry in `retrieval_needs.search_hints[]`.
3. Preserve traceability to the original field and value.
4. Emit a readiness warning, not a failure, if and only if the value is absent from active exact lanes and present in `search_hints[]`.
5. Fail readiness if the value remains in any active exact citation lane.
6. Fail readiness if the value is removed from exact lanes but not preserved in `search_hints[]`, `context_artifacts[]`, or another explicit trace field.

Recommended normalized warning record shape:

```json
{
  "section_id": "agent-subsystem",
  "severity": "warning",
  "code": "broad_directory_ref_routed_to_search_hints",
  "source_field": "file_anchors[]",
  "input": "agent/component/",
  "normalized_to": "retrieval_needs.search_hints[]",
  "reason": "Directory-like path is useful recall text but not an exact citeable file handle."
}
```

Recommended `search_hints[]` entry shape:

```json
{
  "text": "agent/component/ component base lifecycle concrete components",
  "scope": ["source", "bm25", "vector"],
  "reason": "Planner supplied a directory-like file anchor; routed to recall hint because file_anchors[] requires exact files.",
  "source_field": "file_anchors[]",
  "source_input": "agent/component/"
}
```

### Readiness behavior

The readiness gate must apply these classifications:

| Case | Readiness result |
| --- | --- |
| Directory-like ref remains in `file_anchors[]` / exact files lane | `FAIL` |
| Directory-like ref is removed from exact lane and appears in `search_hints[]` | `PASS` with warning, assuming no other failures |
| Directory-like ref is removed but not preserved anywhere traceable | `FAIL` |
| Exact file such as `agent/component/base.py` appears in file lane and exists | `PASS` |
| Nonexistent exact-looking file remains in file lane | `FAIL` |

If the current readiness report format supports only `PASS` and `FAIL`, Patch 1 should keep that binary status and add warning counts/details. A plan with only successfully routed directory-like refs should have:

```text
Status: PASS
Warnings: N
Failures: 0
```

It should not require a new top-level `PASS_WITH_WARNINGS` status unless the implementation already has that concept.

### Phase 3 behavior

Phase 3 remains unchanged in principle:

- Phase 3 must not cite `search_hints[]` as evidence.
- Phase 3 may use `search_hints[]` as deterministic BM25/vector recall text.
- Phase 3 must cite only concrete retrieved evidence: files, spans, chunks, symbols, graph nodes/edges, contracts, tests, or equivalent exact artifacts.
- Phase 3 must not call an LLM.
- Phase 3 must not add retry/debug loops.
- This patch does not propose product `--section` mode.

## Detailed implementation plan for Patch 1

### 1. Tighten planner instructions

Update the Phase 2 planner prompt/template so the exact-file rule is unambiguous.

Required language:

```text
file_anchors[] requires exact citeable repository file paths.
Do not put directories, trailing-slash paths, package prefixes, or subsystem names in file_anchors[].
Examples of invalid file_anchors[] values: agent/component/, agent/plugin/, agent/sandbox/.
If you only know a broad area, put it in search_hints[] instead.
If you know representative exact files, put those exact files in file_anchors[].
```

Required examples:

```text
Invalid file_anchors[]:
- agent/component/
- agent/plugin/
- agent/sandbox/

Valid file_anchors[]:
- agent/component/base.py
- agent/plugin/llm_tool_plugin.py
- agent/sandbox/sandbox_spec.md

Valid search_hints[]:
- agent component lifecycle and concrete components
- agent plugin system and LLM tool plugins
- agent sandboxed code execution backend
```

The prompt should explicitly say that exact lanes are for copyable handles, while `search_hints[]` is for broad recall intent.

### 2. Tighten handle catalog guidance

Update the planner-facing handle catalog guidance from Phase 1 so directory names are not accidentally presented as exact file handles.

For broad subsystems, the catalog should present both:

1. representative exact files; and
2. a clearly labeled broad search hint.

Recommended handle catalog pattern:

```text
Agent component subsystem
Exact file handles:
- agent/component/base.py
- docs/guides/agent/agent_component_reference/agent.mdx
Search hint, not a file anchor:
- agent/component/ component lifecycle concrete components

Agent plugin subsystem
Exact file handles:
- agent/plugin/llm_tool_plugin.py
- agent/plugin/README.md
Search hint, not a file anchor:
- agent/plugin/ plugin system LLM tool plugins

Agent sandbox subsystem
Exact file handles:
- agent/sandbox/sandbox_spec.md
- internal/agent/tool/code_exec_sandbox_design.md
Search hint, not a file anchor:
- agent/sandbox/ sandboxed code execution backend
```

The catalog must avoid formatting directory paths in a way that looks copyable into `file_anchors[]`.

### 3. Add deterministic normalizer classification

Implement a classification path for directory-like file refs before readiness failure generation.

Pseudo-logic:

```text
for each raw file_anchor input:
  if is_exact_existing_file(input):
    emit exact file work item
  else if is_directory_like(input):
    remove from exact file lane
    emit search_hints[] entry with source trace
    emit readiness warning broad_directory_ref_routed_to_search_hints
  else:
    remove from exact file lane
    emit unresolved reference or readiness failure according to existing rules
```

`is_directory_like(input)` should be deterministic. It should not call an LLM and should not infer semantics from prose beyond simple path classification and known bundle metadata.

Suggested checks:

- `input.endswith("/")`;
- `input` appears in a source-tree directory listing if available;
- normalizing away the trailing slash produces a prefix for two or more known files;
- `input` is a path prefix in `inventory/files.jsonl` but not itself a file.

### 4. Refine readiness failure generation

The readiness report should generate failures from the normalized active lanes, not solely from raw planner mistakes that have already been routed safely.

Patch 1 readiness rules:

```text
FAIL if active exact file lane contains directory-like ref.
FAIL if active exact file lane contains nonexistent exact-looking file.
FAIL if directory-like ref was removed from exact lane but no trace/search hint remains.
WARN if directory-like ref was removed from exact lane and preserved in search_hints[].
PASS if all exact lanes are valid and only warnings remain.
```

This means readiness should inspect both:

- active normalized work items; and
- normalization actions/warnings.

It should not silently hide the raw planner mistake. It should keep the warning visible.

### 5. Keep expected evidence derivation strict

A routed directory-like ref must not satisfy `expected_evidence_types: ["files"]` by itself.

Allowed behavior:

- It may support `bm25` and/or `vector` expected evidence, because it is recall text.
- It may coexist with exact file evidence if representative exact files are present separately.
- It may lead Phase 3 to retrieve exact file/chunk evidence through BM25/vector, but the search hint itself is never evidence.

Blocking cases:

- `files` expected solely because `agent/component/` existed in raw `file_anchors[]`.
- Readiness passing while `agent/component/` remains in an exact files lane.
- Readiness passing after the broad intent was dropped without trace.

### 6. Update readiness report contents

Add or strengthen a warning section in `plans/phase3-readiness-report.md`.

Minimum recommended content:

```text
## Warnings

### Broad directory refs routed to search_hints[]
- section_id: agent-subsystem
  source_field: file_anchors[]
  input: agent/component/
  normalized_to: retrieval_needs.search_hints[]
  reason: Directory-like path is useful recall text but not a citeable file anchor.

- section_id: agent-subsystem
  source_field: file_anchors[]
  input: agent/plugin/
  normalized_to: retrieval_needs.search_hints[]
  reason: Directory-like path is useful recall text but not a citeable file anchor.

- section_id: agent-subsystem
  source_field: file_anchors[]
  input: agent/sandbox/
  normalized_to: retrieval_needs.search_hints[]
  reason: Directory-like path is useful recall text but not a citeable file anchor.
```

The report should also include summary counts:

```text
Failures: 0
Warnings: 3
Broad directory refs routed to search_hints[]: 3
```

### 7. Preserve traceability in machine-readable outputs

If a machine-readable normalization report or unresolved/warnings artifact exists, it should preserve enough traceability for tests and handoff review.

Recommended fields:

```json
{
  "section_id": "agent-subsystem",
  "code": "broad_directory_ref_routed_to_search_hints",
  "severity": "warning",
  "source_field": "file_anchors[]",
  "source_input": "agent/plugin/",
  "normalized_field": "retrieval_needs.search_hints[]",
  "blocking": false
}
```

If the implementation only has `unresolved-references.jsonl`, do not put successfully routed directory hints there as unresolved failures. Prefer a warnings section/artifact. If they must be included for compatibility, mark them clearly as non-blocking and routed.

## Validation gates for Patch 1

Patch 1 is acceptable when all of the following are true.

### Planner/catalog gates

- Planner instructions explicitly forbid directory/trailing-slash paths in `file_anchors[]`.
- Planner instructions show `agent/component/`, `agent/plugin/`, and `agent/sandbox/` as invalid file anchors.
- Planner instructions show representative exact file alternatives.
- Planner instructions direct broad subsystem intent to `search_hints[]`.
- Handle catalog presents representative exact files separately from broad search hints.

### Normalizer gates

- Directory-like refs in raw `file_anchors[]` are removed from active exact file lanes.
- The original broad intent is preserved in `search_hints[]` with traceability.
- Exact files such as `agent/component/base.py` remain valid exact file work items.
- Nonexistent exact-looking files still fail readiness unless resolved by existing exact-handle rules.
- Expected evidence types are derived from normalized resolvable work, not from raw directory anchors.

### Readiness report gates

- A plan containing only successfully routed directory-like file refs, and no other readiness errors, reports `Status: PASS` with warnings.
- The same refs remaining in exact file lanes report `Status: FAIL`.
- The report keeps routed refs visible in a warning section.
- Warning counts are included in summary output.
- Failures and warnings are clearly separated.

### Phase 3 gates

- Phase 3 remains deterministic and LLM-free.
- Phase 3 uses `search_hints[]` only as recall text.
- Phase 3 does not cite `search_hints[]` directly.
- Phase 3 does not add retries, debug loops, or product `--section` behavior.

## Test plan for Patch 1

### Unit tests: directory-like classification

Add tests for deterministic classification of directory-like values.

Cases that should classify as `directory_like`:

```text
agent/component/
agent/plugin/
agent/sandbox/
```

Additional useful cases:

```text
agent/component
agent/plugin
agent/sandbox
```

The no-trailing-slash cases should classify as directory-like only when repository metadata proves they are directories or path prefixes, not merely because they lack file extensions.

### Unit tests: exact file pass-through

Exact files should remain exact file anchors when present in the inventory/source metadata:

```text
agent/component/base.py
agent/plugin/llm_tool_plugin.py
agent/sandbox/sandbox_spec.md
agent/plugin/README.md
internal/agent/tool/code_exec_sandbox_design.md
docs/guides/agent/agent_component_reference/agent.mdx
```

Expected result:

- active exact file lane contains the exact file;
- no broad-directory warning for that file;
- readiness does not fail on that item.

### Unit tests: routed directory refs become warnings

Fixture input:

```json
{
  "section_id": "agent-subsystem",
  "file_anchors": [
    "agent/component/",
    "agent/plugin/",
    "agent/sandbox/"
  ]
}
```

Expected normalized output:

- `file_anchors[]` or normalized exact files lane does not contain those three directory refs;
- `retrieval_needs.search_hints[]` contains equivalent text for all three refs;
- warnings contain `broad_directory_ref_routed_to_search_hints` for all three refs;
- readiness status is `PASS` if no other failures exist;
- warning count is `3`.

### Unit tests: directory refs left in exact lanes fail

Fixture input or forced normalized state:

```json
{
  "section_id": "agent-subsystem",
  "retrieval_needs": {
    "files": [
      {"path": "agent/component/"}
    ]
  }
}
```

Expected result:

- readiness status is `FAIL`;
- failure code identifies a directory-like ref in an exact file lane;
- suggested fix says to use an exact file such as `agent/component/base.py` or move broad intent to `search_hints[]`.

### Unit tests: dropped broad intent fails

Fixture behavior:

- raw planner input includes `agent/plugin/` in `file_anchors[]`;
- normalized exact file lane omits it;
- `search_hints[]` does not contain it;
- no trace field records where it went.

Expected result:

- readiness status is `FAIL`;
- failure reason indicates broad retrieval intent was dropped during normalization.

### Unit tests: expected evidence derivation

Fixture input:

```json
{
  "section_id": "agent-subsystem",
  "file_anchors": ["agent/component/"],
  "search_hints": []
}
```

After normalization:

- the directory ref is in `search_hints[]`;
- `expected_evidence_types` may include `bm25` and/or `vector` if supported;
- `expected_evidence_types` must not include `files` solely because of `agent/component/`.

Add a paired fixture where `agent/component/base.py` is present as an exact file. In that case, `files` may be expected because a real exact file exists.

### Prompt/catalog snapshot tests

Add snapshot or golden tests that verify planner-facing text contains the new exact-lane guidance.

Assertions:

- `file_anchors[] requires exact citeable repository file paths` appears.
- `agent/component/` appears as an invalid `file_anchors[]` example.
- `agent/component/base.py` appears as a valid exact file example.
- `search_hints[]` appears as the destination for broad subsystem intent.
- The handle catalog does not list trailing-slash directory paths under an "exact file handles" heading.

### Integration test: RAGFlow agent subsystem fixture

Use a small RAGFlow-derived fixture for the `agent-subsystem` section.

Input should include planner-style broad refs:

```text
agent/component/
agent/plugin/
agent/sandbox/
```

Expected outputs:

- normalization succeeds;
- readiness report is `PASS` with warnings if no unrelated failures exist;
- warnings list all three routed directory refs;
- normalized active exact file lanes contain no trailing-slash directory paths;
- `search_hints[]` includes all three broad areas;
- Phase 3 can use those hints for deterministic BM25/vector recall;
- Phase 3 evidence, if run, cites concrete files/chunks such as `agent/component/base.py` or `agent/plugin/llm_tool_plugin.py`, not the directory hints.

### Regression test: no masking of real exact-lane failures

Create a fixture with both:

```text
agent/component/
not/a/real/file.py
```

Expected result:

- `agent/component/` becomes a warning if routed to `search_hints[]`;
- `not/a/real/file.py` remains a readiness failure unless resolved by an existing exact-handle rule;
- overall readiness status is `FAIL` because a real exact-lane failure remains.

## Non-goals for Patch 1

Patch 1 does not:

- make directory paths valid citation evidence;
- allow `file_anchors[]` to contain directories;
- suppress or hide planner mistakes;
- weaken exact-lane validation;
- change Phase 3 into an LLM-based retriever;
- add Phase 3 retries or manual debug loops;
- add product `--section` mode;
- reinterpret all readiness failures as warnings;
- replace the first readiness iteration spec;
- replace the Phase 3 evidence retrieval spec;
- define Patch 2, Patch 3, or final go/no-go decisions.

## Patch 1 acceptance criteria

Patch 1 is complete when:

1. Planner guidance forbids directories/trailing-slash paths in `file_anchors[]`.
2. Handle catalog guidance separates exact file handles from broad search hints.
3. The normalizer routes directory-like file anchors to `search_hints[]` with traceability.
4. Readiness reports routed directory-like refs as warnings, not failures.
5. Readiness still fails if directory-like refs remain in exact lanes.
6. Readiness still fails if broad intent is dropped without trace.
7. Expected evidence derivation does not count routed directory refs as file evidence.
8. Tests cover successful routing, failure when left in exact lanes, failure when dropped, exact-file pass-through, prompt/catalog guidance, and a RAGFlow agent-subsystem fixture.

## Handoff notes for implementers

- Treat this as a narrow semantics patch, not a redesign.
- The planner made a reasonable semantic association but used the wrong output lane.
- The normalizer's defensive move to `search_hints[]` is the behavior to preserve.
- The readiness report should educate the user: "this was a neighborhood name, not a house address."
- A warning is still important because it indicates planner guidance should improve.
- Do not weaken Phase 3 validation or cite broad hints directly.

## Patch 2 title

**Malformed required `SectionPlan` JSONL rows must not silently disappear during parsing or normalization.**

## Patch 2 summary

Patch 2 covers a different failure mode from Patch 1.

Patch 1 is about a semantically useful value being placed in the wrong lane and then correctly routed to `search_hints[]`.

Patch 2 is about a semantically useful whole `SectionPlan` row being lost because one JSONL line was malformed. The normalizer then synthesized an empty normalized section from `DocumentPlan` metadata, which hid the useful planner content and surfaced later as a retrieval-signal failure.

The core rule for Patch 2 is:

> If a required section's `SectionPlan` row is malformed, parsing/normalization must not skip the whole row and proceed as if the planner provided no retrieval signal. It must enter a Phase 2 repair gate before canonical normalization: use a narrow deterministic repair when safe, otherwise run the required bounded Vertex/Gemini repair step when available. If repair cannot run or the repaired artifacts still fail validation, fail loudly with a clear parse/readiness failure tied to the raw line and section.

## Patch 2 concrete observed case

The raw Gemini response contained a useful `llm-integration` `SectionPlan`. It included meaningful retrieval intent, including `evidence_needs`, that should have helped Phase 3 retrieve evidence for the LLM integration section.

However, the JSONL row was invalid. After this valid field:

```json
"verification_needs": []
```

Gemini emitted a bare string sentence inside the object:

```json
"Lexical query hits for LLM integrations need to be verified to confirm the exact nature of the integration."
```

That sentence was useful planner intent, but it was not valid JSON object syntax. It should have been placed as an array item under `verification_needs[]` or possibly under `known_gaps[]`.

The required one-shot examples for planner guidance are:

BAD invalid JSONL:

```json
{"section_id":"llm-integration","verification_needs":[],"Lexical query hits for LLM integrations need to be verified.","estimated_size":"M"}
```

GOOD valid JSONL:

```json
{"section_id":"llm-integration","verification_needs":["Lexical query hits for LLM integrations need to be verified."],"known_gaps":[],"estimated_size":"M"}
```

The observed normalization log reported:

```text
section-plans.jsonl: skipped unparseable line 13
```

After skipping that line, normalization created an empty normalized `llm-integration` section from `DocumentPlan` metadata. That empty synthesized section had no useful retrieval signals, producing `no_retrieval_signal` for `llm-integration`.

This was not a deterministic Phase 3 retrieval bug. Phase 3 did not invent or drop the retrieval signal. The malformed row came from the one LLM planning step, Phase 2 Step 1. The deterministic bug is that parsing/normalization skipped a whole required section too leniently and let the pipeline continue with a misleading empty normalized section.

## Patch 2 relationship to existing specs

Patch 2 preserves the existing architecture:

- Phase 2 Step 1 may use an LLM to produce planning artifacts.
- When raw Phase 2 planner artifacts are malformed and Vertex/Gemini is available, Phase 2 must run a bounded, auditable repair step before canonical normalization.
- Phase 2 parsing, schema validation, and normalization remain deterministic validation layers around the original or repaired artifacts.
- Phase 3 remains deterministic and LLM-free.
- Phase 3 consumes normalized work orders and must not perform LLM repair, retry, or manual debug loops.
- Product `--section` mode is still not proposed.

Patch 2 does not weaken JSONL correctness. Planner outputs should still be valid JSONL. The change is that malformed required rows must be surfaced or repaired explicitly instead of silently disappearing.

## Patch 2 problem statement

The current parser/normalizer behavior is too permissive for malformed `SectionPlan` rows.

Problem pattern:

1. Phase 2 Step 1 emits a required `SectionPlan` JSONL row.
2. The row contains useful planning content, but it is syntactically invalid JSON.
3. The JSONL reader logs a skipped unparseable line.
4. Normalization continues without the row.
5. A fallback empty normalized section is created from `DocumentPlan` metadata.
6. Readiness later reports `no_retrieval_signal`, which is true of the synthesized section but hides the real root cause: the section plan row failed to parse.

The pipeline should instead distinguish these cases:

- **Valid row:** parse and normalize normally.
- **Malformed optional/non-required row:** record a parse warning or failure according to artifact rules.
- **Malformed required section row:** apply a narrow deterministic repair when safe; otherwise, if Vertex/Gemini is available, run the required bounded Phase 2 repair step before canonical normalization; if repair cannot run or validation still fails, fail readiness with a clear `SectionPlan` parse error.
- **Missing required section row:** fail readiness as a missing `SectionPlan`, not as an empty section with no retrieval signal.

## Prompt surfaces that must change for Patch 2

Planner prompt-engineering changes must be added to all planner prompt surfaces, not only the main Gemini gem files.

Required prompt surfaces:

- `gemini-gem/GEM_INSTRUCTIONS.md`
- `gemini-gem/KICKOFF_PROMPT.md`
- fallback `_DEFAULT_SYSTEM` and `_DEFAULT_KICKOFF` strings in `src/wiki_generator/libs/commands/plan.py`
- generated bundle planner guidance in `src/wiki_generator/libs/digest/upload_package.py`

Important script/Vertex note:

- The usual Vertex/script path runs `scripts/phase2_step1_plan.sh`, which invokes `python -m wiki_generator plan`.
- When run from the repository root, that path usually reads the same `gemini-gem` instruction and kickoff files listed above.
- However, `plan.py` contains embedded fallback `_DEFAULT_SYSTEM` / `_DEFAULT_KICKOFF` prompt text for cases where those files are not found.
- Therefore, the `gemini-gem` files and the embedded fallbacks must both be updated, or the stricter JSONL guidance can disappear in fallback environments.

Required planner guidance:

```text
Every line in section-plans.jsonl must be one complete valid JSON object.
Do not emit bare strings, comments, prose sentences, Markdown bullets, or trailing explanatory text inside a JSON object.
All prose must be assigned to a named field.
If a verification sentence is needed, put it in verification_needs[].
If a limitation or uncertainty is needed, put it in known_gaps[].
A malformed JSONL line invalidates that section plan.
```

Required BAD/GOOD one-shot to include in prompt surfaces:

```text
BAD invalid JSONL:
{"section_id":"llm-integration","verification_needs":[],"Lexical query hits for LLM integrations need to be verified.","estimated_size":"M"}

GOOD valid JSONL:
{"section_id":"llm-integration","verification_needs":["Lexical query hits for LLM integrations need to be verified."],"known_gaps":[],"estimated_size":"M"}
```

## Expected behavior after Patch 2

### Planner behavior

The planner should emit strictly valid JSONL:

- one JSON object per line;
- no Markdown fences in JSONL artifacts;
- no comments;
- no bare strings inside objects;
- no trailing prose before or after an object on the same line;
- every prose sentence assigned to a schema field such as `evidence_needs[]`, `verification_needs[]`, `known_gaps[]`, `search_hints[]`, or another allowed field.

For the concrete `llm-integration` sentence, the planner should emit either:

```json
"verification_needs": ["Lexical query hits for LLM integrations need to be verified to confirm the exact nature of the integration."]
```

or, if the sentence is framed as uncertainty rather than verification work:

```json
"known_gaps": ["Lexical query hits for LLM integrations need to be verified to confirm the exact nature of the integration."]
```

### Parser behavior

The JSONL parser must not silently skip malformed required `SectionPlan` rows.

Minimum required behavior:

1. Preserve the raw line number, raw text, artifact path, and parse error.
2. Determine whether the row corresponds to a required section whenever possible.
3. If the malformed row can be repaired by a narrow deterministic rule, emit a repaired row and a visible warning.
4. If deterministic repair is not safe or sufficient and Vertex/Gemini is available, run the required bounded Phase 2 repair step before normalization proceeds to produce canonical `plans/document-plan.json` and `plans/section-plans.jsonl`.
5. Validate repaired artifacts with the same strict parser/schema rules and 1:1 section-id checks before normalization proceeds.
6. If repair cannot run, exceeds the capped attempts, or still produces invalid artifacts, stop normalization or mark readiness failed with a clear parse error.
7. Do not replace a malformed required row with an empty normalized section without preserving the parse failure as the primary blocking issue.

Recommended parse error record shape:

```json
{
  "artifact": "section-plans.jsonl",
  "line": 13,
  "section_id": "llm-integration",
  "severity": "failure",
  "code": "section_plan_jsonl_parse_error",
  "message": "Malformed SectionPlan JSONL row; required section plan was not parsed.",
  "raw_excerpt": "...",
  "parse_error": "..."
}
```

### Normalizer behavior

Normalization may synthesize section shells from `DocumentPlan` metadata only when that synthesis does not hide malformed required planner content.

Allowed behavior:

- produce canonical normalized plans only from parser-valid raw artifacts or validated repaired artifacts;
- hold `plans/document-plan.json` and `plans/section-plans.jsonl` generation until required malformed `SectionPlan` rows have been repaired and validated, or until the pipeline has failed loudly;
- create section shells for sections that are legitimately absent from optional downstream artifacts, while reporting missing required inputs when applicable;
- use `DocumentPlan` metadata for ordering, titles, and expected sections;
- carry parse diagnostics forward into normalization/readiness reports.

Blocking behavior:

- skip `section-plans.jsonl: line 13` and then create an empty `llm-integration` normalized section with only `no_retrieval_signal`;
- write canonical `plans/document-plan.json` or `plans/section-plans.jsonl` after silently dropping a malformed required row;
- treat malformed required `SectionPlan` content as if the planner simply provided no retrieval needs;
- allow parse errors to appear only in transient logs while machine-readable outputs lose the root cause.

### Readiness behavior

Readiness should report the root cause as a parse/normalization failure, not merely as absent retrieval signal.

For the observed case, expected readiness output should include a failure like:

```text
section_plan_jsonl_parse_error: section-plans.jsonl line 13 for section_id=llm-integration could not be parsed.
```

If a repair was applied successfully, whether by a narrow deterministic rule or by the bounded Phase 2 Vertex/Gemini repair step, readiness may pass that section only if the repaired normalized section has valid retrieval signal. In that case, readiness must still include a visible warning/audit entry such as:

```text
section_plan_jsonl_deterministically_repaired: section-plans.jsonl line 13 for section_id=llm-integration repaired a bare string into verification_needs[].
section_plan_jsonl_phase2_repaired: section-plans.jsonl line 13 for section_id=llm-integration was repaired by bounded Phase 2 planner-artifact repair and revalidated before normalization.
```

`no_retrieval_signal` may still be emitted if the final normalized section truly lacks retrieval signal, but it must not be the only or primary diagnostic when a required section row failed to parse.

### Phase 3 behavior

Phase 3 remains unchanged in principle:

- Phase 3 must not call an LLM to repair malformed planning artifacts.
- Phase 3 must not trigger or resume the Phase 2 repair step.
- Phase 3 must not retry planning or parsing.
- Phase 3 must not infer hidden retrieval needs from raw malformed planner text.
- Phase 3 must consume only validated normalized work orders.
- If readiness fails on `section_plan_jsonl_parse_error`, Phase 3 should not proceed as though the section was valid.

## Patch 2 healing policy

Healing must be layered and explicit.

1. **Prevention: stronger prompt/one-shot.** The first line of defense is better planner instructions and examples across every planner prompt surface. The BAD/GOOD one-shot above should make clear that bare strings inside JSON objects are invalid and that verification sentences belong under `verification_needs[]` or `known_gaps[]`.

2. **Deterministic safety: no silent skips.** The parser/normalizer must not silently skip required `SectionPlan` rows. It may apply narrow deterministic repairs only when the structure is obvious and safe. Every parse error and deterministic repair must preserve artifact path, line number, section id if recoverable, raw excerpt, parser message, and repair/validation outcome.

3. **Required contingent Phase 2 repair.** If raw planner output is malformed and deterministic repair does not produce valid artifacts, Phase 2 must run a bounded planner-artifact repair step when Vertex/Gemini is available. This is no longer optional or a future-only idea. The repair must happen before normalization proceeds to produce canonical `plans/document-plan.json` and `plans/section-plans.jsonl`.

4. **Bounded and auditable repair.** The Phase 2 repair step must ask for corrected planning artifacts only, using the raw bad planner artifact/response and the exact structured parse errors. Attempts must be capped at an implementation-chosen maximum of 1 or 2 attempts, with a hard upper bound of 2. For every attempt, save the repair request, raw bad artifact or raw bad response, exact parse errors, repair response, validation report, and any diff or mapping needed to review section changes. Validate all `section_id`s 1:1 against the original `DocumentPlan`; reject added, removed, or renamed sections unless the user explicitly requests plan regeneration. Run the same strict parser and schema validation after repair.

5. **Fail loudly when repair cannot make valid artifacts.** If bounded Phase 2 repair is needed but Vertex/Gemini is unavailable, credentials/quota fail, repair is disabled by the environment, the attempt cap is exhausted, or the repaired artifacts still fail parsing/schema/section-id validation, normalization/readiness must fail loudly with the original parse diagnostics and repair failure details. It must not silently continue with skipped rows or synthesized empty sections.

6. **Strict scope boundaries.** This repair gate is a Phase 2 planner-artifact repair before canonical normalization. It is not a Phase 3 retry loop, not product `--section` mode, not a one-section content rewrite, and not an unbounded manual debug loop. Phase 3 never invokes it.

7. **Concrete bare-string case.** For the observed bare-string sentence after `"verification_needs": []`, deterministic repair may be enough because the intended field is structurally obvious. Even if that repair is implemented, prompt hardening, parser safety, and the contingent Phase 2 repair/fail-loud path are still required so future malformed rows do not disappear silently.

## Detailed implementation plan for Patch 2

### 1. Add strict JSONL validity guidance to planner prompts

Update every prompt surface listed above with the JSONL validity rules and BAD/GOOD one-shot.

The wording should emphasize:

- JSONL means one complete valid JSON object per line;
- every sentence must belong to a named field;
- `verification_needs[]` is the correct field for verification work;
- `known_gaps[]` is the correct field for uncertainty, missing evidence, or caveats;
- a single malformed line can invalidate the corresponding section plan.

### 2. Make JSONL parsing produce structured diagnostics

The JSONL reader for `section-plans.jsonl` should return both parsed rows and parse diagnostics, or raise a structured exception that can be converted into readiness output.

Diagnostics should include:

- artifact path;
- line number;
- raw line or redacted raw excerpt;
- parser exception/message;
- recoverable `section_id`, if it can be extracted safely;
- whether the line was repaired, skipped, or fatal;
- whether the section is required by `DocumentPlan`.

A plain log line such as `skipped unparseable line 13` is not sufficient for a required section plan.

### 3. Correlate malformed rows with required sections

When a `section-plans.jsonl` line fails to parse, the pipeline should attempt a safe correlation to `DocumentPlan` sections.

Suggested deterministic extraction:

- if the raw line contains a valid-looking `"section_id":"..."` or `"section_id": "..."` string before the parse error, extract that value;
- verify that the extracted value exists exactly once in the `DocumentPlan` section list;
- if matched, attach the parse diagnostic to that section;
- if not matched, report an artifact-level parse error and avoid guessing.

This correlation is for diagnostics and repair routing only. It must not treat the malformed row as parsed content.

### 4. Add narrow deterministic repair only for obvious structures

The implementation may include a deterministic repair path, but it must be conservative.

Allowed repair shape for the concrete case:

- the raw line is otherwise a single JSON object for a known required `section_id`;
- the parser failure is caused by one or more unkeyed string tokens inside the object;
- an unkeyed string appears immediately after `"verification_needs": []` or another clearly related empty array field;
- moving that string into `verification_needs[]` produces valid JSON;
- all other fields remain unchanged;
- the repaired object passes schema validation.

If the unkeyed sentence is clearly a limitation rather than verification work, the deterministic repair may place it in `known_gaps[]`. If the destination field is ambiguous, do not apply deterministic repair; proceed to the required bounded Phase 2 repair step when Vertex/Gemini is available, otherwise fail with `section_plan_jsonl_parse_error`.

Every deterministic repair must be auditable:

```json
{
  "artifact": "section-plans.jsonl",
  "line": 13,
  "section_id": "llm-integration",
  "severity": "warning",
  "code": "section_plan_jsonl_deterministically_repaired",
  "repair": "moved unkeyed string token into verification_needs[]",
  "raw_excerpt": "...",
  "repaired_excerpt": "..."
}
```

### 5. Fail closed when repair cannot produce valid artifacts

If deterministic repair is unsafe or insufficient, the bounded Phase 2 repair step must be attempted when Vertex/Gemini is available. Normalization/readiness must fail closed only when repair cannot run or cannot produce valid artifacts within the attempt cap.

Expected failure behavior:

- do not silently skip the row;
- if Vertex/Gemini is available, attempt the required bounded Phase 2 repair before failing;
- do not create an empty normalized section as the only output for that section;
- include `section_plan_jsonl_parse_error` and repair failure details in machine-readable diagnostics;
- include the line number and recoverable `section_id` in human-readable readiness output;
- preserve `no_retrieval_signal` as a secondary symptom only if useful, not as the primary failure.

### 6. Preserve raw and normalized traceability

Patch 2 should preserve enough data for debugging without requiring access to transient logs.

Recommended artifacts or report sections:

- raw parse diagnostics JSON/JSONL for malformed rows;
- normalization warnings/failures carrying parse diagnostics forward;
- readiness report section for malformed planner artifacts;
- repair audit entries if deterministic or bounded Phase 2 repair was applied;
- pointers to the raw planner response location when available.

### 7. Add required contingent Phase 2 repair step

Add a Phase 2 planner-artifact repair entry point that runs after strict parse diagnostics are produced and before normalization writes canonical `plans/document-plan.json` and `plans/section-plans.jsonl`.

Possible implementation names include `scripts/phase2_step1b_repair_plan.sh`, a `plan-repair` command, or an equivalent Phase 2 subcommand. The exact script/CLI name is an implementation detail, but the UI must make clear that this is planner-artifact repair, not Phase 3 retrieval or product `--section` generation.

Required constraints:

- the step is required when raw planner output is malformed, deterministic repair is not sufficient, and Vertex/Gemini is available;
- input is the raw Phase 2 response or bad artifact plus exact structured parser diagnostics;
- output request asks for corrected artifacts only, not rewritten content or new plan semantics;
- attempts are capped at 1 or 2, with 2 as the hard maximum;
- the repair request, raw bad artifact/raw bad response, exact parse errors, repair response, validation report, and useful diff/mapping artifacts are saved for every attempt;
- repaired artifacts are diffable against originals;
- all `section_id`s are validated 1:1 against the original `DocumentPlan`;
- added, removed, or renamed sections fail unless the user explicitly requests plan regeneration;
- repaired JSONL is parsed with the same strict parser and schema validation;
- if Vertex/Gemini is unavailable or the repaired artifacts still fail validation, normalization/readiness fails loudly instead of proceeding;
- Phase 3 never triggers this automatically;
- this must not become a Phase 3 retry loop, product `--section` mode, or an unbounded debug loop.

## Validation gates for Patch 2

Patch 2 is acceptable when all of the following are true.

### Prompt gates

- `gemini-gem/GEM_INSTRUCTIONS.md` contains strict JSONL guidance and the BAD/GOOD one-shot.
- `gemini-gem/KICKOFF_PROMPT.md` contains or references the same strict JSONL guidance.
- `src/wiki_generator/libs/commands/plan.py` fallback `_DEFAULT_SYSTEM` / `_DEFAULT_KICKOFF` guidance contains the same strict JSONL constraints.
- `src/wiki_generator/libs/digest/upload_package.py` generated bundle planner guidance contains the same constraints.
- The guidance names `verification_needs[]` and `known_gaps[]` as destinations for prose that otherwise might be emitted as a bare string.

### Parser/normalizer gates

- A malformed required `SectionPlan` row cannot be skipped silently.
- Parse diagnostics are structured and survive into readiness output or normalization artifacts.
- The pipeline can identify `section_id=llm-integration` from the concrete malformed row, or otherwise reports an artifact-level parse error without guessing.
- A required section with a malformed row is not replaced by an empty normalized section as the only diagnostic.
- Narrow deterministic repair, if used, produces a warning and an audit record.
- If deterministic repair does not produce valid artifacts and Vertex/Gemini is available, the bounded Phase 2 repair step runs before canonical `plans/document-plan.json` and `plans/section-plans.jsonl` are produced.
- Phase 2 repair attempts are capped at 1 or 2 and save the repair request, raw bad artifact/response, exact parse errors, repair response, validation report, and useful diff/mapping artifacts.
- If repair cannot run or the repaired artifacts still fail strict parsing/schema/section-id validation, normalization/readiness fails loudly with `section_plan_jsonl_parse_error` and repair failure details.

### Readiness gates

- The observed case no longer appears only as `no_retrieval_signal`.
- Readiness output includes artifact path, line number, and section id when recoverable.
- Repaired rows are visible as warnings, not hidden success.
- Unrepaired malformed required rows are blocking failures.
- Missing required section rows are reported as missing section plans, not as parser success.

### Phase 3 gates

- Phase 3 remains deterministic and LLM-free.
- Phase 3 does not re-prompt Gemini or Vertex to repair section plans.
- Phase 3 does not trigger the Phase 2 repair command or script.
- Phase 3 does not consume malformed raw planner text.
- Phase 3 runs only after strict normalization/readiness validation passes.

## Test plan for Patch 2

### Unit test: BAD invalid JSONL does not silently skip

Fixture line:

```json
{"section_id":"llm-integration","verification_needs":[],"Lexical query hits for LLM integrations need to be verified.","estimated_size":"M"}
```

Expected result:

- parser records `section_plan_jsonl_parse_error` and either applies the allowed deterministic repair or enters the required Phase 2 repair gate when Vertex/Gemini is available;
- no code path reports only `skipped unparseable line` and proceeds silently;
- if repair cannot run or still fails validation, readiness fails with artifact path, line number, parse error, and repair failure details;
- if repaired, readiness includes `section_plan_jsonl_deterministically_repaired` or `section_plan_jsonl_phase2_repaired` warning.

### Unit test: GOOD valid JSONL parses normally

Fixture line:

```json
{"section_id":"llm-integration","verification_needs":["Lexical query hits for LLM integrations need to be verified."],"known_gaps":[],"estimated_size":"M"}
```

Expected result:

- parser accepts the row;
- `verification_needs[]` contains the sentence;
- no parse warning is emitted;
- normalized `llm-integration` keeps its retrieval/verification intent.

### Unit test: concrete observed row with longer sentence

Fixture includes the actual longer sentence:

```json
"Lexical query hits for LLM integrations need to be verified to confirm the exact nature of the integration."
```

Expected result:

- deterministic repair places it in `verification_needs[]` when that narrow rule is implemented and the rest of the object is structurally safe;
- otherwise, if Vertex/Gemini is available, the required bounded Phase 2 repair step is attempted before canonical normalization;
- if repair cannot run or still fails validation, readiness fails with `section_plan_jsonl_parse_error` plus repair failure details;
- in neither case is an empty `llm-integration` section the only normalized result.

### Unit/integration test: bounded Phase 2 repair audit

Fixture setup:

- raw Phase 2 output contains a malformed required `llm-integration` row;
- deterministic repair is disabled or unsafe;
- Vertex/Gemini repair is available in a mocked or test provider.

Expected result:

- the Phase 2 repair step runs before `plans/document-plan.json` and `plans/section-plans.jsonl` are produced;
- attempts are capped at the configured value of 1 or 2;
- the repair request, raw bad artifact/response, exact parse errors, repair response, validation report, and useful diff/mapping artifacts are saved;
- repaired artifacts are validated with the same strict parser/schema and 1:1 section-id checks;
- if the provider returns invalid artifacts through the final attempt, normalization/readiness fails loudly and does not silently skip the row.

### Unit test: malformed required row blocks fallback shell masking

Fixture setup:

- `DocumentPlan` contains `llm-integration`;
- `section-plans.jsonl` contains a malformed `llm-integration` line;
- normalizer has enough metadata to create section shells.

Expected result:

- parse diagnostic is attached to `llm-integration`;
- synthesized shell, if emitted, is marked invalid/blocked by parse error;
- readiness primary failure is `section_plan_jsonl_parse_error`, not only `no_retrieval_signal`.

### Unit test: missing required row is distinct from malformed row

Fixture setup:

- `DocumentPlan` contains `llm-integration`;
- `section-plans.jsonl` contains no `llm-integration` row.

Expected result:

- readiness reports `missing_section_plan` or equivalent;
- it does not report a JSON parse error unless malformed text exists;
- it does not silently synthesize a valid empty plan.

### Unit test: ambiguous unkeyed string fails closed

Fixture line contains an unkeyed string in a location where the target field is unclear.

Expected result:

- deterministic repair is not applied;
- if Vertex/Gemini is available, the required bounded Phase 2 repair step is attempted;
- if repair cannot run or still fails validation, readiness fails with `section_plan_jsonl_parse_error` and repair failure details;
- diagnostic explains that deterministic repair was unsafe or ambiguous.

### Prompt snapshot tests

Add snapshot or golden tests for every planner prompt surface.

Assertions:

- `Every line in section-plans.jsonl must be one complete valid JSON object` appears.
- `Do not emit bare strings` appears.
- The BAD invalid JSONL one-shot appears.
- The GOOD valid JSONL one-shot appears.
- `verification_needs[]` and `known_gaps[]` are mentioned as valid destinations for prose.
- `plan.py` fallback prompt text contains equivalent guidance when `gemini-gem` files are unavailable.
- generated bundle guidance from `upload_package.py` contains equivalent guidance.

### Integration test: readiness reports parse root cause

Use a small fixture that reproduces the observed failure:

- `DocumentPlan` includes `llm-integration`;
- `section-plans.jsonl` line 13 is malformed with the bare string after `"verification_needs": []`;
- raw content includes useful `evidence_needs` that would have provided retrieval signal if parsed.

Expected outputs:

- parser/normalizer does not silently drop line 13;
- readiness report names `section-plans.jsonl`, line `13`, and `llm-integration`;
- if deterministic repair is unsafe and Vertex/Gemini is available, bounded Phase 2 repair runs before canonical normalization;
- if unrepaired or still invalid after the capped attempts, status is `FAIL` due to `section_plan_jsonl_parse_error` plus repair failure details;
- if repaired, status may pass that issue but includes a deterministic repair or Phase 2 repair warning;
- the report does not mislead the user into thinking the only issue was `no_retrieval_signal`.

### Regression test: Phase 3 does not repair planner JSONL

Run or inspect the Phase 3 path with malformed `section-plans.jsonl` inputs.

Expected result:

- Phase 3 does not call Gemini, Vertex, or any LLM;
- Phase 3 does not attempt planner-artifact repair;
- Phase 3 does not trigger `phase2_step1b_repair_plan.sh`, `plan-repair`, or any equivalent Phase 2 repair entry point;
- Phase 3 only consumes validated normalized artifacts;
- malformed planner JSONL is repaired or rejected before Phase 3 evidence retrieval.

## Non-goals for Patch 2

Patch 2 does not:

- make malformed JSONL acceptable planner output;
- hide JSON parse errors behind empty normalized section shells;
- add LLM calls to Phase 3;
- add Phase 3 retry loops;
- add product `--section` mode;
- create an unbounded Phase 2 or Phase 3 debug loop;
- ask the LLM to rewrite only one product section during Phase 3;
- permit added, removed, or renamed section IDs during repair without explicit plan regeneration;
- replace schema validation with fuzzy parsing;
- make every malformed JSON row repairable;
- weaken strict validation for exact evidence lanes;
- replace Patch 1 or the first readiness iteration spec.

## Patch 2 acceptance criteria

Patch 2 is complete when:

1. All planner prompt surfaces include strict JSONL guidance and the BAD/GOOD one-shot.
2. `section-plans.jsonl` parsing produces structured diagnostics for malformed rows.
3. Required `SectionPlan` rows cannot be silently skipped.
4. Malformed required rows receive a narrow deterministic repair when safe; otherwise, when Vertex/Gemini is available, the bounded Phase 2 repair step is required before canonical normalization.
5. Repair attempts are capped at 1 or 2, auditable, and save the repair request, raw bad artifact/response, exact parse errors, repair response, validation report, and useful diff/mapping artifacts.
6. If repair cannot run or repaired artifacts remain invalid, normalization/readiness fails loudly with a clear parse error and repair failure details.
7. Normalization does not mask malformed required rows by creating apparently valid empty section shells.
8. The observed `llm-integration` case reports the parse root cause rather than only `no_retrieval_signal`.
9. Phase 3 remains deterministic, LLM-free, and uninvolved in planner repair.
10. Tests cover the BAD/GOOD one-shot, the observed bare-string case, contingent Phase 2 repair, audit artifacts, attempt bounds, prompt surfaces, fallback prompt behavior, readiness diagnostics, and Phase 3 non-repair behavior.

## Patch 2 open decisions

- Whether Patch 2 should implement deterministic repair immediately or rely on the required contingent Phase 2 repair/fail-loud path for malformed rows that are not safely repairable by parser rules.
- If deterministic repair is implemented, whether a bare string after `"verification_needs": []` always goes to `verification_needs[]` or can sometimes be routed to `known_gaps[]` by narrow rule.
- Exact names and locations for parse diagnostics and repair audit artifacts.
- Exact readiness codes for malformed rows, missing required rows, deterministic repairs, Phase 2 repairs, repair-unavailable failures, and repair-validation failures.
- Exact script/CLI naming for the Phase 2 repair entry point, such as `scripts/phase2_step1b_repair_plan.sh`, `plan-repair`, or an equivalent command.
- Whether the attempt cap is 1 or 2 for the Phase 2 repair step; it must not exceed 2.
- How much raw planner text to include in diagnostics and repair artifacts versus redacted excerpts.

## Patch 3 title

**Internal planning diagnostics must not become ordinary user-facing wiki sections or generic Phase 3 retrieval targets.**

## Patch 3 summary

Patch 3 covers the `known-gaps` failure mode discovered after Patch 1 and Patch 2.

The core rule for Patch 3 is:

> Pipeline diagnostics such as `planning-gaps.md` are not source evidence for normal wiki sections. They may inform planner uncertainty, verification needs, and controlled provenance metadata, but they must not be promoted into vague user-facing content or rescued by generic Phase 3 fallback retrieval.

This patch also captures the corrected framing from the user: when something goes wrong, the remedy belongs in one of two places:

1. **LLM planning quality:** the planner prompt, examples, and repair/re-prompt behavior must prevent or correct bad section planning.
2. **Deterministic pipeline resilience:** the normalizer, readiness gate, and Phase 3 retrieval must fail closed instead of turning internal diagnostics into weak user-facing evidence.

The remedy is not to let Phase 3 force a no-signal section through BM25/vector fallback and then cite unrelated files.

## Patch 3 problem statement

The current planning guidance allowed an internal diagnostic artifact, `derived/planning-gaps.md`, to become the basis for a normal wiki section named `known-gaps`.

That is the wrong boundary between internal pipeline state and user-facing wiki content.

Problem pattern:

1. The planner is encouraged to create a normal section about known gaps or unverified areas.
2. The only concrete anchor for that section is an internal diagnostic artifact such as `derived/planning-gaps.md`.
3. The normalizer correctly treats that artifact as non-citeable context rather than source evidence.
4. The normalized section has no real retrieval signal: no query packs, symbols, contracts, tests, graph nodes, or search hints.
5. Readiness correctly fails the section with `no_retrieval_signal`.
6. If Phase 3 is forced to run anyway, generic BM25/vector fallback retrieves noisy files that do not evidence the diagnostic claims.

The pipeline should not convert internal uncertainty into a vague public-facing wiki chapter. It should either attach uncertainty to the affected real sections, preserve diagnostics as controlled provenance, or require the planner/repair step to add real retrieval signals for any section that is genuinely about repository behavior.

## Patch 3 non-expert explanation: inspection notes vs published guide

`planning-gaps.md` is like an inspector's punch list for the wiki-building process. It can say, "we may not have verified this area enough," or "this tool output was approximate."

A punch list is useful, but it is not itself a chapter in the published guide. Readers need chapters supported by real source evidence: files, symbols, tests, contracts, graph nodes, and concrete search results.

So Patch 3 says:

- keep the punch list for auditability;
- attach its warnings to the real sections they affect;
- optionally publish a clearly marked provenance note if the product format wants one;
- do not create a normal source-evidence section from the punch list alone;
- do not let Phase 3 fill the gap with unrelated search hits.

## Patch 3 root cause

The `known-gaps` section was not randomly invented by Gemini.

The root cause is that existing planner guidance encouraged it:

- `gemini-gem/GEM_INSTRUCTIONS.md` asked for a **"Known gaps / unverified"** section from `planning-gaps.md`.
- The upload bundle and digest reinforced weak, uncertain, skipped, or approximate areas as planning material.
- Those instructions conflated internal pipeline diagnostics with the user-facing wiki structure.

The planner followed that guidance too literally. It created a normal `known-gaps` `SectionPlan` whose only concrete artifacts were internal diagnostics. That left deterministic retrieval with no legitimate source-evidence lane to use.

This is a planning-boundary and pipeline-resilience issue, not a reason to make Phase 3 more permissive.

## Patch 3 observed evidence

### Existing prompt guidance encouraged the bad section

The prompt surface in `gemini-gem/GEM_INSTRUCTIONS.md` instructed the planner to include a **"Known gaps / unverified"** section based on `planning-gaps.md`.

The bundle/digest material also emphasized weak or uncertain areas. That was useful as internal planning context, but it was not clearly separated from public section structure.

### Raw Gemini `known-gaps` plan had only diagnostics

The raw Gemini `known-gaps` `SectionPlan` used `derived/planning-gaps.md` in both exact and contextual lanes:

```json
{
  "section_id": "known-gaps",
  "file_anchors": ["derived/planning-gaps.md"],
  "context_artifacts": ["derived/planning-gaps.md"]
}
```

It did not include meaningful source-retrieval signals, such as:

- query packs;
- symbols;
- contracts;
- tests;
- graph nodes;
- graph edges;
- source-file anchors;
- search hints tied to actual repository behavior.

### Normalization behaved correctly

The normalizer correctly moved `derived/planning-gaps.md` out of citeable file lanes and kept it as non-citeable context.

That was the right behavior because derived planning diagnostics are not source evidence. But after that move, the `known-gaps` section had no remaining retrieval signal.

### Readiness behaved correctly

Readiness correctly failed `known-gaps` with `no_retrieval_signal`.

That failure was useful. It exposed that the section was not evidence-backed and should not proceed into Phase 3 as a normal source-evidence section.

### Forced Phase 3 produced noisy evidence

When Phase 3 was forced past readiness, it produced mostly noisy BM25/vector hits such as:

```text
agent/templates/deep_research.json
docs/basics/rag.md
internal/cpp/re2/onepass.cc
internal/cpp/re2/dfa.cc
```

Those hits do not evidence pipeline limitations such as derived OpenAPI limitations, approximate call graph quality, skipped tools, or unverified planner assumptions.

This confirms that generic fallback retrieval is the wrong remedy for a section with no real retrieval signal.

## Patch 3 desired behavior

After Patch 3, the pipeline should behave as follows.

### User-facing section behavior

Normal wiki sections must be about repository behavior and must be backed by real retrieval signals.

A normal section must not be created solely because internal diagnostics mention a gap, skipped tool, approximate artifact, or uncertainty.

If the planner wants to discuss a limitation as a normal section, it must provide real source-evidence retrieval signals that can support that section, such as exact files, symbols, tests, contracts, graph nodes, query packs, or precise search hints tied to repository behavior.

### Diagnostic/provenance behavior

`planning-gaps.md` and similar diagnostics should populate one or more of these non-source-evidence destinations:

- per-section `verification_needs[]`;
- provenance metadata;
- normalization/readiness diagnostics;
- a controlled provenance note or appendix, if the product explicitly supports it;
- internal audit artifacts used by implementers and reviewers.

A controlled provenance note must be clearly marked as non-source evidence. It may explain planning limitations or verification state, but it must not claim to be repository behavior unless supported by source evidence.

### Repair behavior

If the LLM creates a normal user-facing section backed only by diagnostics or context artifacts, Phase 2 repair/re-prompt must fix it before Phase 3 evidence retrieval.

Allowed repair outcomes:

1. **Remove the normal section** if it is only internal diagnostic content.
2. **Convert it into controlled provenance** if the output format supports a non-source provenance note/appendix.
3. **Add real retrieval signals** if the section is genuinely about repository behavior and can be evidence-backed.

If none of those outcomes can be produced and validated, readiness must fail.

### Phase 3 behavior

Phase 3 must not rescue no-signal sections with generic BM25/vector fallback.

No-signal sections must fail readiness/retrieval unless they are explicitly classified as controlled provenance/meta and handled outside normal evidence lanes.

Phase 3 remains deterministic and LLM-free.

## Detailed implementation plan for Patch 3

### 1. Separate internal diagnostics from user-facing structure

Define a deterministic classification for internal diagnostic artifacts. At minimum, this classification must include:

```text
derived/planning-gaps.md
```

It should also cover equivalent generated diagnostics when present, such as artifacts that summarize skipped analysis, approximate derived data, missing tools, planner uncertainty, or bundle coverage limitations.

These artifacts may inform planning and verification metadata, but they are not citeable source evidence for normal wiki sections.

### 2. Remove `known-gaps` as a default normal section

Planner prompts and bundle guidance must stop requiring or encouraging a default normal wiki section named `known-gaps`, `known gaps`, `Known gaps / unverified`, or equivalent.

The planner may still record uncertainty. It must do so by attaching it to affected real sections through `verification_needs[]` and provenance metadata, not by inventing a normal user-facing section backed only by diagnostics.

### 3. Add a diagnostic-only section detector

The normalizer/readiness layer must detect a normal section whose only support is internal diagnostics or non-citeable context artifacts.

A normal section should be classified as `diagnostic_only_user_section` or equivalent when all of the following are true:

- the section is marked or inferred as a normal user-facing source-evidence section;
- its exact citeable lanes are empty after normalization;
- its only anchors or artifacts are diagnostic/context artifacts such as `derived/planning-gaps.md`;
- it has no query packs, symbols, contracts, tests, graph nodes, graph edges, precise source-file anchors, or meaningful search hints tied to repository behavior.

That condition is blocking for normal sections.

### 4. Route diagnostics to allowed destinations

When diagnostics are found in planning artifacts, the pipeline should preserve them without treating them as source evidence.

Allowed destinations include:

- `verification_needs[]` on the affected real section;
- a `provenance` or `planning_diagnostics` metadata field;
- a readiness warning or audit entry;
- a controlled provenance/meta section outside the normal evidence lanes, if the product explicitly supports one.

Recommended audit record shape:

```json
{
  "section_id": "known-gaps",
  "severity": "failure",
  "code": "diagnostic_only_user_section",
  "source_artifacts": ["derived/planning-gaps.md"],
  "reason": "Normal wiki sections require source-evidence retrieval signals; planning diagnostics are non-citeable context.",
  "allowed_repairs": [
    "remove_section",
    "convert_to_controlled_provenance",
    "add_real_retrieval_signals"
  ]
}
```

### 5. Add Phase 2 repair/re-prompt behavior

When `diagnostic_only_user_section` is detected before canonical normalization or before readiness PASS, Phase 2 repair/re-prompt should be invoked when the normal repair path is available.

The repair prompt must ask for a constrained fix only:

- remove diagnostic-only normal sections;
- convert them to controlled provenance/meta if the document format supports that role;
- or add real retrieval signals if the section is genuinely about repository behavior.

The repair must not ask the LLM to write final wiki prose, rewrite unrelated sections, or add new sections unrelated to the original plan without explicit plan-regeneration intent.

If repair is unavailable or cannot produce a valid plan, readiness must fail loudly with the diagnostic-only section error.

### 6. Keep source-evidence sections strict

A normal section may pass only when it has at least one valid retrieval signal after normalization.

Examples of valid retrieval signals include:

- existing source files or documentation files;
- symbols;
- tests;
- contracts or API schemas that are citeable source artifacts;
- graph nodes or edges backed by repository artifacts;
- query packs;
- precise search hints tied to actual repository behavior.

Examples that do not satisfy normal-section retrieval signal by themselves:

- `derived/planning-gaps.md`;
- bundle summaries;
- upload digests;
- skipped-tool notes;
- approximate-call-graph caveats;
- generic statements such as "known gaps" or "unverified areas".

## Patch 3 prompt changes

Update all planner prompt surfaces that mention gaps, uncertainty, or planning diagnostics.

Required prompt changes:

- Remove any instruction to create a normal **"Known gaps / unverified"** wiki section from `planning-gaps.md`.
- State that `planning-gaps.md` and similar diagnostics are internal planning/provenance context, not source evidence.
- Instruct the planner to attach uncertainty to affected sections via `verification_needs[]`.
- Preserve pipeline diagnostics in provenance metadata or context-only fields.
- Permit a controlled provenance note/appendix only if explicitly supported by the product format, and require it to be marked as non-source evidence.
- Require real retrieval signals for any normal section that discusses repository behavior.
- Forbid `file_anchors[]` from containing derived diagnostics as citeable files.

Recommended prompt language:

```text
Do not create a normal user-facing wiki section named "Known gaps", "Known gaps / unverified", or similar solely from planning-gaps.md or other pipeline diagnostics.

planning-gaps.md is internal planning/provenance context. It is not source evidence for repository behavior.

If a diagnostic reveals uncertainty about a real section, attach that uncertainty to the affected section using verification_needs[]. Keep the diagnostic artifact in provenance/context metadata only.

If the output format explicitly supports a provenance note or appendix, diagnostics may be summarized there only as non-source provenance, clearly separated from source-evidence sections.

Any normal wiki section must have real retrieval signals: exact source/doc files, symbols, tests, contracts, graph nodes/edges, query packs, or precise search hints tied to repository behavior.
```

Prompt snapshot tests must cover the `gemini-gem` files, fallback prompt strings, and generated upload-bundle/digest guidance as applicable.

## Patch 3 normalizer/readiness changes

### Normalizer changes

The normalizer must treat derived planning diagnostics as non-citeable context.

Required behavior:

- remove diagnostic artifacts such as `derived/planning-gaps.md` from exact citeable lanes;
- preserve them in context/provenance metadata with traceability;
- attach diagnostic-derived uncertainty to `verification_needs[]` when the affected section is clear;
- do not synthesize a valid normal section from diagnostics alone;
- emit a blocking diagnostic when a normal section is supported only by diagnostics/context artifacts;
- allow a controlled provenance/meta section only when the plan explicitly marks it as such and the product format supports that role.

Recommended normalized warning/failure codes:

```text
diagnostic_artifact_routed_to_context
diagnostic_only_user_section
controlled_provenance_section_non_source
```

### Readiness changes

Readiness must enforce the distinction between normal source-evidence sections and controlled provenance/meta content.

Required behavior:

- fail normal sections with no retrieval signal after diagnostics are removed from citeable lanes;
- report `diagnostic_only_user_section` as the primary cause when applicable, not just generic `no_retrieval_signal`;
- require Phase 2 repair/re-prompt before Phase 3 for diagnostic-only normal sections;
- permit controlled provenance/meta content only outside normal evidence lanes;
- include the diagnostic artifacts and suggested repair options in the readiness report;
- keep `no_retrieval_signal` as a valid secondary symptom, but not the only explanation for diagnostic-only sections.

Recommended readiness output for the observed case:

```text
Status: FAIL
Failure: diagnostic_only_user_section
Section: known-gaps
Artifacts: derived/planning-gaps.md
Reason: The section is a normal user-facing wiki section backed only by internal planning diagnostics. Remove it, convert it to controlled provenance, or add real repository evidence signals.
Secondary: no_retrieval_signal
```

## Patch 3 Phase 3 changes

Phase 3 must fail closed for no-signal sections.

Required behavior:

- do not run generic BM25/vector fallback for a section with no retrieval signal;
- do not treat non-citeable diagnostics as search queries for normal evidence retrieval;
- do not use `--force` to turn a readiness failure into product evidence;
- do not cite diagnostic/context artifacts as source evidence;
- skip or block normal sections that readiness marked as `diagnostic_only_user_section` or `no_retrieval_signal`;
- handle explicitly classified controlled provenance/meta content outside normal evidence lanes;
- keep Phase 3 deterministic and LLM-free.

If a section has real `search_hints[]`, query packs, or other valid retrieval needs, Phase 3 may use the existing deterministic retrieval strategy. The prohibition is specifically against inventing a generic fallback retrieval path for a section whose normalized work order has no legitimate retrieval signal.

## Patch 3 test plan

### Prompt snapshot test: no default `known-gaps` section

Assertions:

- prompt surfaces no longer require a **"Known gaps / unverified"** normal wiki section;
- `planning-gaps.md` is described as internal planning/provenance context;
- `verification_needs[]` is named as the destination for uncertainty attached to affected sections;
- controlled provenance/meta output is allowed only when explicitly supported and clearly marked non-source;
- normal sections are required to include real retrieval signals.

### Unit test: diagnostic artifact is non-citeable

Fixture:

```json
{
  "section_id": "known-gaps",
  "file_anchors": ["derived/planning-gaps.md"],
  "context_artifacts": ["derived/planning-gaps.md"]
}
```

Expected result:

- `derived/planning-gaps.md` is removed from exact citeable lanes;
- it is preserved in context/provenance metadata;
- a `diagnostic_artifact_routed_to_context` warning or trace is emitted;
- it does not count as file evidence for a normal section.

### Unit test: diagnostic-only normal section fails readiness

Using the same fixture, with no query packs, symbols, contracts, tests, graph nodes, graph edges, or valid search hints.

Expected result:

- readiness status is `FAIL`;
- primary failure is `diagnostic_only_user_section` or equivalent;
- secondary symptom may include `no_retrieval_signal`;
- suggested repairs are remove, convert to controlled provenance, or add real retrieval signals.

### Unit test: controlled provenance/meta section is handled outside evidence lanes

Fixture marks the section explicitly as controlled provenance/meta and the product format supports that role.

Expected result:

- the section is not treated as a normal source-evidence section;
- it does not require normal source retrieval signals;
- diagnostics are clearly marked non-source;
- Phase 3 does not attempt source-evidence retrieval for it;
- product output, if later generated, can clearly separate it from evidence-backed sections.

### Unit test: genuine repository limitation section must have real signals

Fixture describes an actual repository behavior or limitation and includes real evidence signals, such as source files, docs, tests, contracts, graph nodes, query packs, or precise search hints.

Expected result:

- the section is allowed as a normal section only if those signals survive normalization;
- diagnostics may remain as verification/provenance metadata;
- readiness does not pass solely because `planning-gaps.md` was present.

### Phase 2 repair test: diagnostic-only section is fixed before Phase 3

Fixture contains a raw plan with normal section `known-gaps` backed only by `derived/planning-gaps.md`.

Expected result:

- Phase 2 repair/re-prompt is invoked when available;
- repaired output either removes the normal section, converts it to controlled provenance/meta, or adds real retrieval signals;
- repaired artifacts are revalidated before readiness PASS;
- if repair is unavailable or invalid, readiness fails loudly.

### Phase 3 regression test: no generic fallback rescue

Fixture contains a normalized normal section with no retrieval signal.

Expected result:

- Phase 3 does not issue generic BM25/vector queries for that section;
- Phase 3 does not retrieve unrelated files such as `agent/templates/deep_research.json`, `docs/basics/rag.md`, `internal/cpp/re2/onepass.cc`, or `internal/cpp/re2/dfa.cc` as a rescue path;
- the section remains blocked until the plan is repaired or classified as controlled provenance/meta.

### Integration test: existing raw plan recovery path

Use the existing raw plan that produced `known-gaps`.

Expected result:

- re-normalization or Phase 2 repair removes/converts/fixes the diagnostic-only normal section;
- readiness has no `diagnostic_only_user_section` or unresolved `no_retrieval_signal` failures;
- Phase 3 runs without `--force`;
- Phase 3 evidence contains only concrete evidence for normal sections;
- no generic fallback evidence is produced for `known-gaps`.

## Patch 3 validation gates

Patch 3 is acceptable when all of the following are true.

### Prompt gates

- Planner guidance no longer requires or encourages a default normal **"Known gaps / unverified"** section.
- `planning-gaps.md` and similar diagnostics are described as internal planning/provenance context, not source evidence.
- The planner is instructed to attach uncertainty to affected sections through `verification_needs[]`.
- Controlled provenance/meta output is allowed only when explicitly supported and marked non-source.
- Any normal section discussing repository behavior must include real retrieval signals.

### Normalizer/readiness gates

- Diagnostic artifacts are removed from exact citeable lanes and preserved only as context/provenance with traceability.
- Normal sections backed only by diagnostics/context artifacts are blocked with `diagnostic_only_user_section` or equivalent.
- The readiness report identifies diagnostic-only sections with source artifacts and repair options.
- `no_retrieval_signal` remains a failure for normal sections, not something Phase 3 can force through.
- Controlled provenance/meta content is separated from normal source-evidence sections.

### Phase 2 repair gates

- Phase 2 repair/re-prompt can fix diagnostic-only normal sections by removal, conversion to controlled provenance/meta, or adding real retrieval signals.
- Repaired artifacts are revalidated before readiness PASS.
- If repair cannot run or cannot produce a valid plan, readiness fails loudly.

### Phase 3 gates

- Phase 3 remains deterministic and LLM-free.
- Phase 3 does not perform generic fallback retrieval for sections with no retrieval signal.
- Phase 3 does not cite planning diagnostics or context artifacts as source evidence.
- Phase 3 is run without `--force` for the validation path before Phase 4.

## Patch 3 risks and tradeoffs

- Removing `known-gaps` entirely can reduce transparency unless uncertainty is retained in `verification_needs[]`, provenance metadata, readiness diagnostics, or a controlled provenance note.
- Keeping a controlled provenance note preserves auditability, but it must be clearly marked as non-source and kept separate from source-evidence sections.
- Strictly blocking diagnostic-only sections may require more Phase 2 repair work, but it prevents noisy Phase 3 evidence and vague final wiki content.
- Attaching every uncertainty to affected sections can make section metadata noisier; this is preferable to publishing a generic unsupported gaps chapter.
- If a real repository limitation deserves user-facing coverage, the planner must do the extra work to provide real retrieval signals instead of relying on pipeline diagnostics.

## Patch 3 non-goals

Patch 3 does not:

- add a Phase 3 retry loop;
- add product `--section` mode;
- allow generic BM25/vector fallback to rescue no-signal sections;
- make `planning-gaps.md` or similar diagnostics citeable source evidence;
- remove all transparency about uncertainty;
- forbid controlled provenance/meta notes when the product explicitly supports them;
- allow final wiki prose to be generated from pipeline diagnostics as if they were repository behavior;
- weaken Patch 1 exact-lane validation;
- weaken Patch 2 parse/repair validation;
- replace the Phase 3 evidence retrieval spec.

## Patch 3 acceptance criteria

Patch 3 is complete when:

1. Prompt guidance no longer asks for a default normal `known-gaps` or **"Known gaps / unverified"** section from `planning-gaps.md`.
2. Planner guidance routes uncertainty to `verification_needs[]` and provenance/context metadata.
3. The normalizer treats planning diagnostics as non-citeable context and preserves traceability.
4. Normal sections backed only by diagnostics fail readiness or enter Phase 2 repair before Phase 3.
5. Phase 2 repair can remove, convert, or add real retrieval signals for diagnostic-only normal sections.
6. Phase 3 does not perform generic fallback retrieval for no-signal sections.
7. Controlled provenance/meta content, if supported, is clearly separated from source-evidence sections.
8. Tests cover prompt guidance, diagnostic artifact routing, diagnostic-only readiness failure, controlled provenance, genuine evidence-backed limitation sections, Phase 2 repair, Phase 3 no-fallback behavior, and the existing raw-plan recovery path.

## Final Phase 4 go/no-go — placeholder

TBD after Patch 1, Patch 2, and Patch 3 are implemented and reviewed.

Expected validation path before Phase 4:

1. Re-normalize and/or repair the existing raw plan using the Patch 1, Patch 2, and Patch 3 rules.
2. Do not proceed from stale normalized artifacts that predate these patches.
3. Rerun readiness and require a clean `PASS` before Phase 4.
4. Rerun Phase 3 without `--force`.
5. Require Phase 3 evidence to come only from valid normalized retrieval signals, with no generic fallback rescue for no-signal sections.
6. Proceed to Phase 4 writing only after the readiness report and Phase 3 evidence outputs are clean enough to show that all normal sections are evidence-backed and all diagnostic/provenance material is handled outside normal source-evidence lanes.
