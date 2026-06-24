# Phase 1/2/3 Readiness Iteration 3 Spec

## Status / source of truth

**Status: SPEC ONLY.** This document records the Iteration 3 amendment needed after a live Phase 4 run exposed a Phase 3 evidence coverage bug. It is not an implementation patch.

This document is an incremental amendment on top of:

- `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_SPEC.md`
- `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md`
- `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`

`PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md` remains the baseline readiness spec. `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` remains unchanged and must not be edited for this amendment.

Scope for Iteration 3: fix Phase 3 aggregation, capping, coverage reporting, and validation so exact requested evidence cannot be lost after lane retrieval succeeds and exact-lane caps are allocated fairly across requests.

## Problem statement

A live Phase 4 Vertex run correctly failed closed because the generated section cited an unsupported identifier:

```text
rag/llm/embedding_model.py
```

The failure occurred in section:

```text
subsystem-rag-core
```

Relevant artifacts:

```text
Accepted Phase 1-3 bundle:
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038

Second live Phase 4 run:
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-100421
```

The file `rag/llm/embedding_model.py` was not hallucinated as a repository path:

- it exists in inventory/chunks/spans;
- it was requested by `subsystem-rag-core` in `retrieval_needs.files[]`;
- normalization resolved it as `file_exists`;
- the Phase 3 file-anchor lane found candidates for it before aggregation.

But the final EvidencePacket did not include a citeable item whose `source.path` was `rag/llm/embedding_model.py`. This was an unbalanced exact-lane aggregation/capping bug, not a legitimate cap-infeasibility case. The section had four exact file requests and an effective file-anchor cap of 8:

- `rag/flow/parser/parser.py`
- `rag/nlp/search.py`
- `deepdoc/parser/pdf_parser.py`
- `rag/llm/embedding_model.py`

With candidates available for each requested file, that cap should have retained a balanced distribution, roughly 2 citeable items per requested file, including `rag/llm/embedding_model.py`. Instead, aggregation/capping kept all 8 `file_anchor` items from the first requested file, `rag/flow/parser/parser.py`, and 0 from the others.

The packet summary was misleading:

```text
file_anchor: requested 4, returned 8, status pass
```

That lane-level status hid the fact that multiple requested files with available candidates received zero final citeable evidence.

## Root cause

Phase 3 treated file-anchor success as lane-level coverage instead of per-request coverage.

Current aggregation behavior can produce this failure mode:

1. A lane emits candidates for multiple exact requests.
2. Candidates are sorted primarily by confidence/lane/rank/path.
3. Per-lane and per-section caps are applied to the globally sorted list instead of first allocating per-request exact budgets.
4. Early candidates from one request consume the exact-lane cap.
5. Later exact requests receive zero kept items even though they had pre-aggregation hits and the cap was feasible.
6. `lane_summary` reports the lane as passing because the lane returned some evidence.

This is a coverage bug, not a Phase 4 validation bug and not normal `starved_by_cap` behavior. Phase 4 did the correct thing by rejecting an unsupported identifier. Because four requested files under cap 8 is feasible, the Phase 3 packet should have included citeable evidence for `rag/llm/embedding_model.py` and the other requested files instead of allowing ordinary sorting to consume the exact-lane budget.

## Non-goals

Iteration 3 must not introduce any of the following:

- no Phase 3 LLM calls;
- no Phase 3 retry/debug loop;
- no product `--section` mode;
- no generic BM25/vector fallback to rescue missing exact evidence;
- no weakening of Phase 4 unsupported-identifier validation;
- no treating `derived/`, `plans/`, prompt, repair, or other context artifacts as citeable evidence;
- no change to the rule that Phase 4 never reruns Phase 3 or invents fallback evidence.

Prompt hardening in Phase 4 may be a secondary patch, but the primary fix is Phase 3 evidence coverage.

## Required behavior

Exact retrieval requests must have per-request coverage after aggregation and capping.

For each direct exact request in these normalized `retrieval_needs` lanes:

- `files[]`
- `symbols[]`
- `tests[]`
- `contracts[]`
- `graph_nodes[]`
- `query_packs[]`

Phase 3 must report one of these outcomes in the final EvidencePacket:

- `covered` — at least one final citeable evidence item covers the request;
- `miss` / `no_hits` — the request resolved but produced no citeable candidates;
- `starved_by_cap` — hard-cap infeasibility: exact requests with candidates could not all receive their required minimum citeable item because a hard section cap made the obligations impossible, for example when the number of exact requests needing at least one item exceeds `max_total_per_section`; if emitted when caps are otherwise feasible, it is an implementation-failure sentinel and must fail closed;
- `unresolved` — the request was not resolved and should already have been caught by readiness/normalization.

A request with pre-aggregation hits must not disappear silently. If hits exist and hard caps are feasible, the final packet must keep at least one citeable item for that request. Ordinary sorting, lane ranking, or broad recall fill must not be allowed to produce a zero-kept exact request. Only true hard-cap infeasibility, or an implementation failure detected by validation, may produce fail-closed `starved_by_cap`.

Broad recall lanes are not exact coverage obligations. `search_hints[]`, BM25, and vector retrieval may improve recall, but they must not be used to claim coverage for an exact requested file/symbol/test/contract/graph node/query pack unless the final evidence item also satisfies that request's exact coverage rule.

## Specific file-anchor rule

For every resolved `retrieval_needs.files[]` item whose resolution is `file_exists`, `unique_suffix`, or another exact resolved file status, and whose pre-aggregation file-anchor lane produced candidates, the final EvidencePacket must keep at least one citeable evidence item with:

```text
item.source.path == resolved file path
```

For the live failure, the packet for `subsystem-rag-core` must therefore include at least one final evidence item where:

```text
source.path == "rag/llm/embedding_model.py"
```

A basename match, textual mention, BM25 hit in another file, vector hit in another file, or synthesized path in model output does not count. A merged/deduped item may count only if its final `source.path` equals the resolved path and its preserved provenance/coverage claim ties it to that request.

If `max_total_per_section` is too small to retain one protected item for every exact request with candidates, Phase 3 must mark the deterministically omitted requests `starved_by_cap`, set the section validation to fail, and make the run fail closed. The packet may keep as many protected items as fit, but it must not report a clean pass. This is the intended narrow meaning of `starved_by_cap`.

The known four-file, cap-8 failure is not such a case. With candidates for all four requested files, the expected file-anchor result is approximately 2 kept citeable items per requested file, including `rag/llm/embedding_model.py`, not 8 from `rag/flow/parser/parser.py` and 0 from the others.

`max_per_lane` must not starve protected exact-request minima. Implementations should apply an effective per-lane cap of at least the number of protected exact requests for that lane, while `max_total_per_section` remains the hard section-level limit. When a lane has remaining exact-lane capacity after minima, those additional slots must be distributed fairly across exact requests before broad recall lanes consume section budget.

## Recommended deterministic aggregation algorithm

Implement the fix as deterministic, balanced exact-evidence allocation before any broad recall fill. Exact requests are obligations. Do not select one best hit per exact request and then hand the remaining budget back to an arbitrary global sort; that can still recreate the 8-from-one-file failure.

1. **Attach request identity in each exact lane.** Each lane hit should preserve a stable request key, source field, requested input, and resolved handle. Example: `file_anchor|retrieval_needs.files[2]|rag/llm/embedding_model.py`.
2. **Build per-request exact candidate pools.** Count citeable candidates per exact request before final capping. Counts should be deterministic and should not include non-citeable context artifacts, broad recall hits, or synthetic path mentions.
3. **Dedupe and prefer spans as today.** Exact dedupe and span-over-chunk preference may still run, but merged provenance must preserve every request identity covered by the surviving representative. A representative may satisfy multiple exact requests only when that provenance is preserved in the coverage records.
4. **Check hard-cap feasibility.** Let `E` be the set of exact requests with at least one citeable candidate, and let `M` be the deterministic set of minimum representatives needed to give every request in `E` at least one citeable item after valid dedupe/provenance preservation. If `len(M) > max_total_per_section`, the section is hard-cap infeasible: keep a deterministic subset that fits, mark the deterministically omitted requests `starved_by_cap`, and fail validation. This is a fail-closed condition, not a normal sorting outcome.
5. **Reserve exact minima.** When caps are feasible, allocate at least one citeable item to every request in `E` before any broad recall lane receives budget. `max_per_lane` must be treated as an effective exact-lane budget that is at least the number of exact requests with candidates for that lane, bounded only by the hard section cap.
6. **Allocate balanced exact depth.** If cap remains after exact minima, distribute additional exact-lane slots fairly and deterministically across exact requests before BM25, vector, `search_hints[]`, or other broad recall lanes consume section budget. Use a water-fill/round-robin policy: complete depth `k` for every eligible exact request before giving any request depth `k + 1`; skip exhausted requests and redistribute their unused depth; within each round use stable request order and stable per-request candidate order. For the known file-anchor case with four requested files, candidates for each, and cap 8, the expected kept file-anchor evidence is roughly 2 items per requested file, including `rag/llm/embedding_model.py`, not 8/0/0/0.
7. **Fill broad recall lanes last.** Only after exact obligations and balanced exact depth are satisfied may BM25, vector, `search_hints[]`, graph-neighbor broad recall, or other non-exact representatives fill remaining section budget using the existing deterministic sort and lane policy.
8. **Assign evidence IDs last.** Evidence IDs must be assigned after the final kept list is known, preserving byte-stable output for identical inputs.

Stable request order and candidate order must be explicit and byte-stable: lane priority, request source field/index, normalized resolved handle, confidence rank, lane rank, source path, start line, stable anchor id/json pointer, and dedupe key. Tie-breakers must never depend on Python object identity, dictionary iteration order, filesystem traversal order, timestamps, random seeds, live model output, or process-local nondeterminism.

## Coverage reporting schema additions

EvidencePacket coverage must become per-request auditable. The exact placement can be `coverage.exact_requests[]`, `lane_summary.<lane>.requests[]`, or both, but the final packet must expose records equivalent to:

```json
{
  "lane": "file_anchor",
  "source_field": "retrieval_needs.files[2]",
  "requested_input": "rag/llm/embedding_model.py",
  "resolved_path": "rag/llm/embedding_model.py",
  "resolution": "file_exists",
  "candidate_count": 6,
  "kept_count": 1,
  "evidence_ids": ["ev:subsystem-rag-core:0003"],
  "status": "covered"
}
```

Required fields for every exact-request coverage record:

- `lane`
- `source_field`
- `requested_input`
- one resolved handle field, such as `resolved_path`, `resolved_symbol_id`, `operation_ref`, `resolved_test`, `resolved_node_id`, or `query_pack`
- `candidate_count`
- `kept_count`
- `evidence_ids`
- `status`: `covered`, `miss`, `no_hits`, `starved_by_cap`, or `unresolved`

Optional but recommended fields:

- `reason`
- `resolution`
- `cap`: the hard cap that made exact obligations infeasible, when applicable
- `candidate_sample`: stable, short, sorted sample only when useful for debugging

The existing `coverage.satisfied`, `coverage.missing`, and `coverage.warnings` fields may remain, but they are not sufficient by themselves. `lane_summary` may still report lane totals, but it must not be the only place coverage can be audited.

## Readiness and retrieval validation behavior

Readiness remains responsible for static plan hygiene: exact lanes must contain resolvable handles, directory-like references must be routed to `search_hints[]`, diagnostics/context artifacts must not be citeable, and broad search hints must not be treated as exact obligations.

Retrieval validation is responsible for post-retrieval coverage:

- `covered`: pass.
- `starved_by_cap`: fail the section and fail the run. This status is valid only for hard-cap infeasibility, such as exact requests with candidates outnumbering `max_total_per_section`, or as a fail-closed implementation-failure sentinel when validation detects that feasible exact obligations were not preserved.
- feasible-cap omission: if an exact resolved request has `candidate_count > 0`, `kept_count == 0`, and the minimum obligations fit under hard caps, validation must fail as an aggregation/allocation implementation failure. Ordinary sorting, lane rank, configured `max_per_lane`, or broad recall fill must not be accepted as the cause.
- `no_hits` / `miss`: report explicitly. Treat as a warning unless the section's `expected_evidence_types[]`, section validation, or existing Phase 3 rules require that evidence type to be present; in that case fail as a bad/underspecified plan or retrieval miss per the existing category policy.
- `unresolved`: readiness/normalization should normally have failed earlier. If present in Phase 3 output, report it explicitly and preserve existing bad-plan behavior.
- `search_hints[]` with no BM25/vector result: warning or informational only, never an exact coverage failure.

If the current failure taxonomy is not extended, `starved_by_cap` should still make the run non-pass. It should be classified loudly as hard-cap infeasibility or implementation failure to preserve exact obligations, not hidden as a lane-level pass.

## Interaction with Phase 4

Phase 4 behavior must remain fail-closed:

- Phase 4 may cite only EvidencePacket evidence ids.
- Unsupported identifiers must remain terminal validation failures.
- Phase 4 must not accept a path merely because it exists in the repo, appears in a prompt, appears in a plan, or is semantically plausible.
- Context artifacts are still not citeable evidence.

Phase 4 prompt hardening can be added as defense in depth: tell the model not to expand partial file names or synthesize full paths unless the exact path is present in cited evidence. But this is secondary. The primary acceptance fix is that Phase 3 must include citeable evidence for every exact request it resolved and found candidates for, including `rag/llm/embedding_model.py` in `subsystem-rag-core`.

## Testing plan

Add deterministic tests that do not call live models and do not rerun live Phase 3 artifacts unless explicitly part of a later validation run.

Required cases:

1. **Four requested files, cap 8, candidates for all.** A synthetic lane result or fixture should request `rag/flow/parser/parser.py`, `rag/nlp/search.py`, `deepdoc/parser/pdf_parser.py`, and `rag/llm/embedding_model.py`, with at least two candidates each and an effective file-anchor cap of 8. Final file-anchor evidence must be balanced at roughly 2 items per requested file, including `rag/llm/embedding_model.py`; it must not keep eight items from the first file and zero from the others.
2. **Balanced exact depth before broad recall.** Add high-scoring BM25/vector/search-hint candidates to the same fixture and assert that exact minima and balanced exact-lane depth are allocated before broad recall consumes budget.
3. **Feasible-cap exact path absent from final evidence.** If a resolved exact file has pre-aggregation candidates, no final `source.path` match, and the minimum obligations fit under hard caps, validation must fail as an implementation/allocation error. It must not report pass or treat ordinary sorting as legitimate `starved_by_cap` behavior.
4. **Resolved file with no chunks.** A `file_exists` request whose file has no chunks/spans must report `no_hits`/`miss` in per-request coverage and unresolved sidecar/reporting, rather than disappearing.
5. **Search hints are not exact obligations.** A `search_hints[]` entry with no result must not create `starved_by_cap` or exact coverage failure.
6. **Total cap too small.** If exact requests with candidates outnumber `max_total_per_section`, retain a deterministic subset, mark the rest `starved_by_cap`, and fail closed. This is the canonical cap-infeasibility case.
7. **Regression for live failure.** If practical, use saved artifacts from `subsystem-rag-core` and assert that the four requested files receive balanced file-anchor evidence after the fix, including `rag/llm/embedding_model.py`.
8. **Merged evidence coverage.** If two requests dedupe to one representative, the kept evidence item may cover both only when merged provenance/coverage records preserve both request identities.
9. **Byte stability.** Two runs over identical synthetic inputs must produce byte-identical packets/reports.

Likely test locations:

- `tests/test_phase3.py` for aggregation/coverage unit tests and small end-to-end bundle tests;
- Phase 4 tests only for optional prompt hardening or to assert fail-closed behavior remains unchanged.

## Implementation plan

Likely affected modules:

- `src/wiki_generator/libs/evidence/aggregate.py` — add request-aware balanced exact allocation (minima plus fair exact depth) before broad recall fill; preserve deterministic sorting and evidence id assignment.
- `src/wiki_generator/libs/evidence/model.py` — add stable request/coverage metadata to `RawHit` or `LaneResult` if needed.
- `src/wiki_generator/libs/evidence/lanes/files.py` — emit per-file coverage identity and candidate/no-hit records.
- Other exact lanes as needed: `lanes/symbols.py`, `lanes/tests.py`, `lanes/contracts.py`, `lanes/graph.py`, `lanes/query_packs.py`.
- `src/wiki_generator/libs/evidence/validate.py` — fail on `starved_by_cap` and expose section-level results.
- `src/wiki_generator/libs/evidence/writer.py` — include per-request coverage in packet/report output.
- `tests/test_phase3.py` — add the concrete regression, balanced allocation, and cap-infeasibility tests.
- Optional Phase 4 prompt/tests — harden against synthesizing full paths from partial evidence without weakening validation.

Do not implement this spec by adding a generic BM25/vector fallback. The fix belongs in exact-lane coverage preservation and validation.

## Acceptance criteria before retrying live Phase 4

Live Phase 4 must remain blocked until all of the following are true:

1. Iteration 3 is implemented and tested without live model calls.
2. A fresh Phase 1-3 run, or at minimum a fresh Phase 3 rerun on the accepted Phase 1/2 bundle, completes with readiness/retrieval validation pass.
3. The `subsystem-rag-core` EvidencePacket includes at least one citeable evidence item whose `source.path` is `rag/llm/embedding_model.py`.
4. Per-request coverage reporting shows all resolved exact requests with candidates as `covered`, with no feasible request lost to ordinary sorting and no `starved_by_cap` except true hard-cap infeasibility.
5. Phase 4 validation remains strict for unsupported identifiers and context artifacts.
6. Only after those gates pass should the live Phase 4 Vertex/Gemini run be retried.
