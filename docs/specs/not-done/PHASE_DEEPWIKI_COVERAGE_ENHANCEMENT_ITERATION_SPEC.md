# DeepWiki-Informed Coverage Enhancement Iteration Spec

## Status and source of truth

Status: **Milestone 1 implemented. Milestone 2 is in progress: coverage
taxonomy/validation, Phase 2 planning/PagePlan obligation preservation, Phase 1
deterministic coverage-signal expansion, the Phase 2 enhancement-mode
planned-coverage upstream-prevention gate, the Phase 3 evidenced-coverage gate,
the Phase 4 enhancement-mode hierarchical writing + generated-coverage gate, the
non-live hierarchical E2E + benchmark-only comparison, the Phase 2 required-topic
evidence-obligation alignment gate, the Phase 2 TER source-field
canonicalization + enhancement-repair diagnostics, and the **Phase 2/3 TER
evidence-alignment** slice (lane/type consistency + citeable-substrate viability)
are implemented and tested non-live. The latest user-approved live/billed RAGFlow
retry at
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-try-f9ad424`
ran against `f9ad424`: Phase 1 and live Phase 2 planning completed, planned coverage
passed `13/13`, and the stricter Phase 2 topic-obligation/citeable-substrate gate
correctly stopped before Phase 3 (`45/58` complete). Bounded live repair attempt 1
improved the plan to `53/58` complete but was rejected by the same strict gate;
attempt 2 hit `RemoteProtocolError: Server disconnected without sending a response`.
Phase 3 and Phase 4 did not run. No further live/billed retry unless the user
explicitly approves it. The Phase 4 claim/token planning and grounded rendering
slice is now implemented and tested non-live as the opt-in
`write-wiki --grounded-claim-plan` path (deterministic per-section token bank →
LLM-authored claim plan → deterministic plan validation → deterministic
token-substitution render → the same strict writing/generated-coverage validators).
The large grounded temp validation over the existing green RAGFlow Phase 1-3 bundle
passed at `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260627-231309-phase4-temp-pi-gpt54-0f5734d`
after one audited bounded claim-plan re-prompt for an LLM-authored invalid evidence
id; generated coverage passed `58/58`, writing validation passed, and benchmark-only
comparison was written. The user then explicitly approved an official live/billed
Vertex/Gemini retry. The official grounded enhancement-mode E2E passed at
`/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e`
with Phase 2 live planning + bounded repair, Phase 3 deterministic retrieval,
Phase 4 live Vertex grounded generation, writing validation pass, generated
coverage `53/53`, and benchmark-only comparison written. Active next decision:
review/sign off the generated wiki and decide whether grounded mode should remain
opt-in or become default.**

## Phase 4 Grounded Claim/Token Planning and Rendering — implemented non-live slice

The recurring Phase 4 failure mode was the writer transforming evidence into
convenient-but-ungrounded shorthand — `from quart_auth import AuthUser` →
`quart_auth.AuthUser`, `class Parser` + `def _pdf` → `Parser._pdf`, f-string route
bases → `/api/{api_version}`, nested JSON keys → `data.graph`, exact route families →
`/api/v1/...` — and the prior fix (accreting one-shot prompt examples) did not scale.
This slice prevents the invention upstream instead of chasing it.

Artifact: an opt-in `write-wiki --grounded-claim-plan` two-stage path:

1. **Token bank (`libs/writing/token_bank.py`).** A deterministic per-section bank of
   the exact terminal technical tokens (routes, file paths, imports, module/class/
   function/method names, env vars, commands, JSON pointers, package names,
   literals) extracted from that section's validated EvidencePacket items. Each entry
   has a stable `tok:<section_id>:NNNN` id, exact string, kind, evidence ids, and
   per-evidence provenance. Invariant: every token is a **verbatim** substring of the
   excerpt or serialized source/provenance of one of its evidence ids. A composite is
   banked only when the exact composite appears verbatim — an import yields the module
   and the name separately, never their dotted join.
2. **Claim plan (`libs/writing/claim_plan.py`).** Plain JSON `phase4-claim-plan-v1`
   (not a DSL): claims with `claim_id`, `claim_kind`, `evidence_ids[]`, `token_ids[]`,
   optional `required_topic`, `intent`, and a `skeleton` that references terminal
   strings only by `{{tok:...}}` placeholder and contains no inline citations.
3. **Deterministic plan validation.** Rejects, before any Markdown is rendered:
   unknown/duplicate claim ids, invalid claim kind, uncited claims, evidence outside
   the section allowlist, unknown token ids, broken token↔evidence linkage,
   undeclared/unknown placeholders, **free-typed terminal technical tokens** in a
   skeleton, inline citations in a skeleton, and (enhancement) an unplanned required
   topic. Actionable diagnostics; never mutates the plan.
4. **Deterministic rendering.** Substitutes each placeholder with the backtick-wrapped
   exact bank string and appends citations from the claim's evidence ids, so accepted
   technical strings come only from deterministic substitution. Enhancement mode
   derives a `covered_topics[]` declaration that passes the generated-coverage
   evaluator.
5. **Same strict validators.** The rendered draft is re-validated by the unchanged
   `validate_section_draft` / `validate_document`; a strict-validator failure on
   grounded output is a deterministic defect (raised, not re-prompted).

Failure policy: a bounded, audited re-prompt (capped by `--max-rewrite-attempts`,
exact machine-checked plan diagnostics fed forward) is allowed only for the
LLM-authored claim plan — no retry-until-green, no post-hoc patching of Markdown,
identifiers, routes, citations, or coverage declarations, and no validator weakening.
Audit artifacts (`wiki/audit/token-banks/`, `wiki/audit/plans/`, claim-plan
prompts/responses, re-prompts) are persisted. Baseline/freeform remains the default
and is non-breaking. Proven non-live by `tests/test_phase4_grounded.py` (token
extraction + verbatim invariant, the full plan-validation matrix, the six
composite-synthesis regressions rejected-unless-verbatim, deterministic rendering
through the strict validator, enhancement covered-topics derivation, and a
fake-provider write-wiki E2E with bounded re-prompt + fail-closed). Remaining: a
grounded `--coverage-mode enhancement` CLI E2E, and — only with explicit user
approval — a billed live retry.

This is the single canonical iteration spec for the DeepWiki-informed coverage
enhancement track. It consolidates the immediate malformed-citation validator
patch and the broader coverage enhancement into one plan so coding agents have
one source of truth.

The framing is **coverage enhancement**, not parody, not copying the reference,
and not blind line-count parity. The reference DeepWiki export is a benchmark for
coverage and structure gaps only; it is not citeable evidence for generated repo
claims.

Source artifacts:

- Successful live Phase 4 run:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730`
- Generated wiki root:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki`
- Generated wiki index:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki/index.md`
- Comparison report:
  `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/COMPARISON_WITH_RAGFLOW_DEEPWIKI.md`
- Reference benchmark, not citeable evidence:
  `/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md`
- Read-only for this iteration:
  `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`

## Plain-language root cause

The live run proved that the current pipeline can produce a valid, grounded
baseline wiki. It did **not** prove that the output is broad enough to be a
DeepWiki-informed repository guide.

The scale gap is this:

- generated wiki sections: roughly **749 lines across 16 sections**;
- reference DeepWiki export: roughly **14,717 lines**.

That does not mean we generated 14,000 lines and still missed content. It means
we generated a compact baseline while expecting a much richer guide.

Blame allocation:

- **Main cause: pipeline/spec/planning/evidence scope.** Phase 1 did not expose
  enough planner-facing topic signals, Phase 2 planned 16 broad sections, Phase 3
  retrieved evidence for those broad sections, and Phase 4 wrote within those
  constraints.
- **LLM local defects:** the model can over-compress and did emit a malformed
  citation token, `[ev:data-models:010]`.
- **Validator defect:** validation missed that malformed `ev:` token because it
  recognized valid-looking citations but did not reject malformed evidence-like
  tokens.

The next iteration must fix both the immediate validation gap and the broader
coverage target. It must not chase length with filler.

## Target artifact

The target artifact is a **DeepWiki-informed, citation-grounded repository guide**
for RAGFlow.

It should be broader and more useful than the current compact 16-section wiki by
covering the repository's major product, architecture, subsystem, developer, and
operator topics with a planned hierarchy and manifest-resolving evidence
citations.

Line count is a warning signal, not the objective. The objective is topic
coverage, hierarchy, implementation usefulness, and grounding quality.

## Quality bar

A successful enhanced wiki must:

- cover the major topic families surfaced by repository evidence and the
  reference benchmark;
- use a hierarchy of pages or child sections where topics need depth, instead of
  hiding everything in 16 broad summaries;
- explain implementation details, runtime flows, APIs, storage, operations, and
  developer surfaces when evidence supports them;
- include a planned-topic taxonomy and coverage matrix showing planned,
  evidenced, and generated status;
- attach repo-specific claims to exact EvidencePacket citations;
- reject malformed evidence-like tokens such as `[ev:data-models:010]`;
- fail closed on missing evidence, unsupported identifiers, context-artifact
  citations, placeholders, truncation, malformed citations, or under-planned
  mandatory topics;
- treat `ragflow-deepwiki.md` only as a benchmark, not as source evidence.

## Coverage sufficiency model

The pipeline answers “is this enough?” in three explicit layers. No single phase is
allowed to imply final sufficiency by itself.

1. **Planned coverage — Phase 2.** The normalized plan must include the required
   topic families, stable pages/child pages, `coverage_labels[]`, and
   `required_topics[]`. This prevents a compact 16-section plan from silently
   skipping important areas. It is necessary but not sufficient: it does not prove
   evidence exists and does not prove the final wiki covered the topic.
2. **Evidenced coverage — Phase 3.** Retrieval must map citeable EvidencePacket
   items to each planned page and required topic. This is the next missing layer.
   It should answer, for every planned topic: `sufficient`, `weak`, or `missing`,
   with exact citeable evidence IDs/handles and remediation. In enhancement mode,
   required topics must be `sufficient` before Phase 4 may run. `weak` or
   `missing` required-topic evidence is a **pipeline failure before Phase 4**, not
   something to heal, synthesize, auto-retry-until-green, or pass to the writer as
   if supported. Context artifacts, `derived/`, `plans/`, generated wiki files,
   and `ragflow-deepwiki.md` remain non-citeable.
3. **Generated coverage — Phase 4.** The writer must actually explain the planned
   and evidenced topics in the generated page, with valid citations and without
   unsupported identifiers, malformed citations, placeholders, or filler.

The intelligence comes from LLM planning and writing constrained by deterministic
artifact contracts and gates. Phase 1 supplies deterministic repo signals, Phase 2
uses LLM judgment to plan coverage, Phase 3 deterministically validates evidence
sufficiency and fails closed on weak/missing required evidence, and Phase 4 uses
LLM synthesis under strict validation. The benchmark comparison against
`ragflow-deepwiki.md` is a warning system for coverage/structure gaps, never
citeable evidence and never the sole quality bar.

## Phase 2 Required-Topic Evidence-Obligation Alignment Contract — implemented non-live slice; live retry exposed next upstream refinement

The live RAGFlow enhancement run exposed a producer-contract mismatch between
Phase 2 planning/normalization and Phase 3 evidenced coverage.

Implemented artifact: a **normalized enhancement-mode SectionPlan** gate in which
every Phase-3-blocking required topic must have a deterministic, exact, citeable
evidence obligation before retrieval runs.

### Failure evidence from the live run

Run path:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-081444
```

Observed sequence:

- Phase 1 completed and built hybrid retrieval substrate.
- Phase 2 Step 1 live Vertex planning completed.
- Phase 2 `normalize-plan --coverage-mode enhancement --strict` initially failed
  on one unresolved file reference, `configuration` → `conf/config.toml.template`.
- Phase 2 Step 1b bounded audited `plan-repair` fixed that file-reference defect
  in one Vertex attempt.
- Re-running strict normalization on the accepted repair output passed with `0`
  unresolved references and the planned-coverage gate passed `13/13` families.
- Phase 3 `retrieve-evidence --coverage-mode enhancement` retrieved all `23/23`
  packets and `707` evidence items, then failed closed before Phase 4:
  `bad_underspecified_normalized_plan`.
- `evidence/evidenced-coverage.json` reports `112` required topics: `11`
  sufficient, `12` weak, `89` missing.

A direct plan diagnostic showed:

```text
sections: 23
required_topics: 112
topic_evidence_requirements: 45
required topics without matching topic_evidence_requirements: 67
```

The immediate root cause is not Phase 4. It is an upstream Phase 2 obligation
contract mismatch: current normalization merges `coverage_requirements[]` into
normalized `required_topics[]`, while the planner prompt asks for
`topic_evidence_requirements[]` only for authored `required_topics[]`. That creates
Phase-3-blocking required topics with no exact source-field bridge. Other failures
show required topics mapped only to broad recall (`search_hints`) or to source
fields that do not yield citeable exact evidence.

### Desired contract

In enhancement mode, a normal source section must not reach Phase 3 unless every
normalized required topic is either:

1. backed by one matching `topic_evidence_requirements[]` row with:
   - the exact same topic string after normalization;
   - `required: true`;
   - non-empty `source_fields[]`;
   - at least one source field pointing at a citeable exact lane:
     `retrieval_needs.files[]`, `retrieval_needs.symbols[]`,
     `retrieval_needs.contracts[]`, `retrieval_needs.tests[]`, or
     `retrieval_needs.query_packs[]`;
   - `acceptable_lanes[]` that can produce sufficient citeable evidence
     (`file_anchor`, `symbol_anchor`, `contract`, `test`, `query_pack`), not
     broad-only `search_hints` / `bm25` / `vector` / `graph_neighbors`; or
2. explicitly not a source-evidence obligation because the section is a controlled
   non-source/meta/provenance section already exempted by existing rules.

`coverage_requirements[]` and `required_topics[]` must be aligned. The implemented
design keeps `coverage_requirements[]` merged into normalized `required_topics[]`,
updates planner prompt/schema text so matching topic-evidence rows are required for
entries in both fields, and adds a deterministic Phase 2 gate so enhancement-mode
normalization fails before Phase 3 when required-topic obligations are incomplete,
invalid, or broad-only.

### Implemented behavior

The implementation:

- updated planner instructions and kickoff prompt so the planner understands that
  every Phase-3-required topic, including any normalized coverage requirement, must
  have exact source-field evidence requirements;
- added a deterministic enhancement-mode Phase 2 obligation-completeness check at
  `normalize-plan --coverage-mode enhancement`, with machine-readable and
  human-readable diagnostics under `plans/`;
- makes the check fail closed before Phase 3 on missing topic evidence rows,
  broad-only source fields, invalid source-field references, or acceptable lanes
  that cannot be sufficient;
- keeps baseline/default behavior non-breaking;
- does not extend bounded audited Phase 2 plan repair; any future repair remains
  limited to LLM-authored plan artifacts, exact diagnostics, a hard attempt cap,
  audit files, and strict final validation;
- added focused tests using small fixtures that reproduce the live failure pattern:
  `coverage_requirements[]` merged into required topics but missing matching
  `topic_evidence_requirements[]`;
- added tests for broad-only/search-hint-only required-topic evidence being rejected
  before Phase 3 in enhancement mode;
- added passing fixtures where all normalized required topics have exact citeable
  source-field obligations;
- preserves Phase 3 and Phase 4 validators unchanged or stricter.

### Completed non-live boundary

No Vertex, Gemini API, Gemini Gem live/manual production flow, or billed provider
was called for implementation or verification of this slice. The failed live run
artifacts above were diagnostic inputs only. The fix was proven with deterministic
unit/CLI fixtures and `uv run python -m pytest -q`.

### Failure policy

- Deterministic planner-prompt/schema/normalizer defects must be fixed upstream.
- LLM-authored plan defects may use bounded audited repair only after prompt/schema
  improvements, with exact diagnostics and a strict cap.
- Do not add generic retry-until-green, synthetic evidence, source-field guessing,
  silent required-to-optional downgrades, benchmark-derived evidence, or validator
  weakening.
- Do not use `ragflow-deepwiki.md`, `derived/`, `plans/`, generated wiki files, or
  historical generated artifacts as citeable evidence.

### Completed-slice acceptance — Phase 2 obligation alignment

This slice is accepted because non-live artifacts/tests prove:

- `normalize-plan --coverage-mode enhancement` fails before Phase 3 for the live
  failure pattern: normalized required topics with missing matching
  `topic_evidence_requirements[]`;
- it also fails for broad-only/search-hint-only required-topic support;
- it passes for an expanded hierarchical fixture where every normalized required
  topic has exact source-field evidence obligations;
- planner prompt/schema text no longer creates the `coverage_requirements[]` vs
  `required_topics[]` mismatch;
- any bounded repair behavior remains narrow, audited, capped, LLM-artifact-only,
  and followed by the same deterministic strict validation;
- baseline mode remains non-breaking;
- protected Phase 3 spec content is unchanged;
- focused tests and the full suite pass with `uv run python -m pytest -q`;
- docs/handoff/status record whether another live RAGFlow retry is justified.

### Live retry result after this slice

The approved retry at
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-141745`
proved the new gate is enforcing the intended boundary on real RAGFlow planning.
Phase 2 planned-family coverage passed (`13/13`), but strict enhancement
normalization failed before Phase 3 after bounded Step 1b repair:

- `plans/topic-obligations-gate.json`: `passed=false`, `exit_code=3`,
  `failure_category=bad_underspecified_normalized_plan`.
- Counts: `46` required topics, `0` complete, `46` incomplete, `21` blocking
  sections.
- Diagnostics: `21` missing `topic_evidence_requirements[]` rows; `25` invalid or
  broad-only source-field mappings.
- Common invalid mapping: the planner/repair output used raw-plan source-field
  names such as `evidence_needs.file_anchors[0]`, `evidence_needs.symbol_ids[0]`,
  and `evidence_needs.query_packs[0]`, while the normalized gate consumes
  canonical `retrieval_needs.files[0]`, `retrieval_needs.symbols[0]`, and
  `retrieval_needs.query_packs[0]`.

## Phase 2 TER Source-Field Canonicalization and Enhancement Repair Diagnostics — implemented non-live slice

### Implemented (non-live)

This slice is implemented and tested non-live:

- `plan_normalization/normalize.py` now stores each
  `topic_evidence_requirements[].source_fields[]` entry in canonical
  `retrieval_needs.*` form. `_resolve_needs` returns a per-section, per-lane
  raw-index → normalized-index map (`None` when a raw item was
  pruned/unresolved/routed), built while resolving needs so it follows pruning index
  shifts exactly. `_canonicalize_ter_source_field` rewrites a documented raw
  `evidence_needs.<alias>[N]` to `retrieval_needs.<lane>[M]` ONLY when raw item `N`
  resolved to normalized item `M`; otherwise it leaves the raw alias verbatim (the
  gate then fails loudly) and records a traceable normalization warning. A lane
  authored under BOTH raw keys (`files`+`file_anchors` / `symbols`+`symbol_ids`) is
  ambiguous and is left uncanonicalized rather than guessed. Bare and already-canonical
  `retrieval_needs.*` source fields are unchanged. No guessing from topic text, prose,
  filenames, or the benchmark.
- `coverage/obligations.py` adds a dedicated, more actionable diagnostic
  (`topic_evidence_requirement_raw_alias_source_field`) for a leftover raw alias that
  could not be canonicalized; raw aliases remain blocking (the gate is not weakened).
- `plan_normalization/repair.py` + `plan-repair --coverage-mode enhancement` accept a
  repair only when readiness AND the planned-coverage gate AND the topic-obligation
  gate all pass. A repair that passes only old readiness but fails topic obligations is
  rejected; the exact topic-obligation diagnostics are written to the audit
  (`repair/attempt-N/obligation-diagnostics-fed.json`) and fed into the next attempt's
  prompt; the final post-repair gate verdict is recorded
  (`repair/attempt-N/enhancement-gates.json`); after the hard cap it fails loudly.
  Baseline mode is unchanged (old readiness gate only).
- Planner prompts (`plan.py`, `gemini-gem/GEM_INSTRUCTIONS.md`,
  `gemini-gem/KICKOFF_PROMPT.md`) explain that raw `evidence_needs.*` aliases are
  compatibility input canonicalized only when the exact raw handle resolves, and keep
  asking for canonical `retrieval_needs.*` names and forbidding broad-only support.
- `scripts/phase2_step1b_repair_plan.sh` exposes/passes `--coverage-mode`.
- `tests/test_phase2_obligation_gate.py` proves raw file/symbol alias canonicalization,
  the non-naïve pruned-index remap (raw `[1]`→normalized `[0]`) with the pruned item
  left invalid, dual-key ambiguity left invalid, broad-alias canonicalization that
  stays blocking, a live-style raw-alias plan passing after canonicalization, and
  fake-client bounded enhancement repair (rejects old-readiness-only, feeds diagnostics
  forward, accepts only on strict enhancement-gate pass, fails loudly after the cap,
  baseline non-breaking). `tests/test_phase1.py` exercises the `_resolve_needs` tuple
  return. No Vertex/Gemini/API/network; protected Phase 3 spec unchanged; validators
  unchanged or stricter; baseline non-breaking; full suite passes with
  `uv run python -m pytest -q`.

### Artifact and quality bar

Artifact being designed: an enhancement-mode Phase 2 normalized plan boundary that
makes each `topic_evidence_requirements[].source_fields[]` entry canonical,
traceable, and gateable before Phase 3.

A good artifact has three properties:

1. The normalized SectionPlan stores TER `source_fields[]` in canonical
   `retrieval_needs.*` form, never ambiguous raw planner aliases.
2. Any compatibility handling for raw planner aliases is deterministic and
   trace-preserving: it rewrites only documented raw exact-lane aliases when the
   raw item actually resolved to a concrete normalized exact lane.
3. Bounded Step 1b plan repair in enhancement mode does not declare success unless
   the same strict post-repair normalization plus planned-coverage and
   topic-obligation gates pass.

### Failure classification

- Raw `evidence_needs.*` source-field aliases inside TER rows are an LLM-authored
  plan-shape defect exposed by deterministic normalization. The normalizer may
  canonicalize documented aliases only when the mapping is exact and traceable;
  otherwise the gate must fail loudly.
- Missing TER rows for normalized required topics are LLM-authored plan defects.
  Bounded repair is allowed only as the existing audited Step 1b flow, but it must
  consume the new topic-obligation diagnostics and rerun strict enhancement
  validation before accepting output.
- Broad-only support (`search_hints`, `bm25`, `vector`, `graph_neighbors`) remains
  a hard plan-quality failure for required topics in enhancement mode. Do not
  convert broad lanes into exact lanes.

### Source-field canonicalization contract

Documented raw aliases that may be canonicalized when exact and unambiguous:

- `evidence_needs.file_anchors[N]` or `evidence_needs.files[N]` →
  `retrieval_needs.files[M]`
- `evidence_needs.symbol_ids[N]` or `evidence_needs.symbols[N]` →
  `retrieval_needs.symbols[M]`
- `evidence_needs.contracts[N]` → `retrieval_needs.contracts[M]`
- `evidence_needs.tests[N]` → `retrieval_needs.tests[M]`
- `evidence_needs.query_packs[N]` → `retrieval_needs.query_packs[M]`

`M` must refer to the normalized exact lane item produced from the raw lane item
`N`. If earlier raw items were pruned, unresolved, routed to `search_hints[]`, or
moved to `context_artifacts[]`, a naive same-index rewrite may be wrong. The
implementation should either preserve an explicit raw-index → normalized-index map
while resolving needs, or leave the source field invalid with an actionable
diagnostic. Do not guess by topic text, fuzzy prose, nearby files, or benchmark
content.

Raw broad aliases may be normalized only to their broad canonical fields and must
remain insufficient for required topics:

- `evidence_needs.search_hints[N]` → `retrieval_needs.search_hints[M]`
- `evidence_needs.graph_nodes[N]` → `retrieval_needs.graph_nodes[M]`

Those broad fields must still fail the topic-obligation gate if they are the only
support for a required topic.

### Enhancement repair contract

`plan-repair` / `scripts/phase2_step1b_repair_plan.sh` should gain an explicit
way to run in enhancement mode or otherwise be invoked by the enhancement path so
that repair success means:

- parse/normalization readiness passes;
- `plans/coverage-gate.json` would pass in enhancement mode;
- `plans/topic-obligations-gate.json` would pass in enhancement mode;
- accepted repair audit artifacts record the topic-obligation diagnostics that were
  fed to the model and the final post-repair gate verdict.

A repair attempt that only passes old Phase-3 readiness but fails
`topic-obligations` must be rejected and, if attempts remain, re-prompted with the
exact topic-obligation diagnostics. After the hard cap, it must fail loudly.

### Non-live implementation boundary

This slice must be implemented and verified without Vertex, Gemini API, Gemini Gem
live/manual production flows, or any billed provider. Use deterministic fixtures
and injected/fake repair clients. The live run at
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260625-141745`
is read-only diagnostic input only.

### Acceptance — implemented slice

This slice is accepted when non-live artifacts/tests prove:

- a TER source field authored as `evidence_needs.file_anchors[0]` normalizes to the
  correct `retrieval_needs.files[0]` when that raw file anchor resolves to the
  first normalized file exact lane;
- a TER source field authored as `evidence_needs.symbol_ids[0]` normalizes to the
  correct `retrieval_needs.symbols[0]` when that raw symbol resolves exactly;
- raw aliases are not naively same-index rewritten when raw lane pruning would make
  the normalized index ambiguous or wrong; such cases fail with an actionable
  topic-obligation diagnostic;
- broad aliases such as `evidence_needs.search_hints[0]` remain broad-only and fail
  required-topic obligations in enhancement mode;
- `normalize-plan --coverage-mode enhancement` passes for a fixture reproducing the
  live raw-alias pattern once every required topic has a matching exact TER row;
- `normalize-plan --coverage-mode enhancement` still fails for missing TER rows;
- bounded `plan-repair` tested with a fake client rejects an attempted repair that
  passes old readiness but fails topic obligations, feeds the new diagnostics into
  the next attempt, and accepts only when strict enhancement gates pass;
- baseline/default behavior remains non-breaking;
- Phase 3 and Phase 4 validators remain strict; no `--force`, product `--section`,
  synthetic evidence, benchmark-derived evidence, silent required-topic downgrade,
  or generic healing/retry-until-green loop is added;
- `git diff --check`, protected-spec diff check, focused tests, and the full suite
  pass with `uv run python -m pytest -q`.

## Phase 2/3 TER Evidence-Alignment — implemented non-live slice

### Implemented (non-live)

This slice is implemented and tested non-live. The shared Phase 2 topic-obligation
gate (`coverage/obligations.py`, consumed by `normalize-plan` and bounded
`plan-repair`) now enforces, in enhancement mode, two additional defect classes per
required topic on top of the existing shape checks:

- **Lane/type consistency** — for each valid exact `source_fields[]` entry, its lane
  (`files → file_anchor`, `symbols → symbol_anchor`, `contracts → contract`,
  `tests → test`, `query_packs → query_pack`) must be present in the TER's
  `acceptable_lanes[]`. If no valid exact source field is both present and acceptable
  (while `acceptable_lanes[]` does contain an exact lane), the topic is incomplete
  with `topic_evidence_requirement_lane_not_acceptable`. This catches the live
  `testing` blocker (`retrieval_needs.tests[0]` vs `acceptable_lanes:["file_anchor"]`).
- **Citeable-substrate viability** — a new read-only `CiteableSubstrate`
  (`coverage/substrate.py`) streams `rag/chunks.jsonl` and `rag/spans.jsonl` once
  into the set of citeable repo paths. Citeability is lane-specific, mirroring what
  the evidence lanes draw from: `file_anchor` cites a path via a chunk OR a span
  (`evidence/lanes/files.py` emits `overlapping_spans` + `overlapping_chunks` +
  `file_repr_chunks`; note `lanes/rag.py` always emits a `module_header` span for a
  Python file even when the chunker produced no chunk), and `test` cites via a chunk
  only (`tests.py` uses only `file_repr_chunks`). A lane-acceptable exact file/test
  source field whose resolved path is not citeable on its lane is incomplete with
  `topic_evidence_requirement_source_not_citeable`. This catches the live `go.mod` /
  `Dockerfile` blockers (resolved in inventory, zero chunks and zero spans, since for
  non-Python files spans are derived from chunks). `symbol_anchor` / `contract` /
  `query_pack` citeability is left undecidable (tri-state `None`, treated as "not
  proven non-citeable"), so those lanes never produce a false citeability failure.
  When the corpus is absent or empty the citeability check is skipped (report-only);
  the gate records `citeability_checked` either way.

`normalize-plan --coverage-mode enhancement` builds the substrate from the bundle and
passes it to the gate (exit `3` before Phase 3 on a lane/type or citeability defect;
baseline unchanged). Bounded `plan-repair --coverage-mode enhancement` builds the
substrate once and threads it into every enhancement-gate evaluation, so a repair
that only fixes the older shape defects but still points a required topic at a
non-citeable file or a lane-mismatched source field is **rejected**, its diagnostics
fed into the next attempt, and after the hard cap it fails loudly. Phase 3 evidenced
coverage and Phase 4 generated coverage are unchanged and remain strict — the fix is
purely upstream prevention. Planner prompts (`plan.py`, `gemini-gem/GEM_INSTRUCTIONS.md`,
`gemini-gem/KICKOFF_PROMPT.md`) now explain lane/type matching and the
citeable-exact-handle requirement. Tests live in `tests/test_phase2_obligation_gate.py`
(lane/type units, citeability units + substrate loader, integrated `normalize-plan`
with a chunk corpus, and a live-style 3-blocker bounded-repair E2E using a fake
client). No Vertex/Gemini/API/network; protected Phase 3 spec unchanged; validators
unchanged or stricter; baseline non-breaking; full suite passes with
`uv run python -m pytest -q`.

### Artifact and quality bar

Artifact being designed: an enhancement-mode Phase 2/3 alignment boundary that
prevents a normalized plan from passing Phase 2 with TER source fields that Phase 3
cannot turn into sufficient citeable evidence for required topics.

A good artifact has four properties:

1. A TER `source_fields[]` entry's normalized lane type is compatible with the TER's
   `acceptable_lanes[]`; e.g. `retrieval_needs.tests[0]` cannot be treated as
   sufficient when `acceptable_lanes[]` contains only `file_anchor`.
2. A TER exact file/source field that passes Phase 2 is viable for citeable Phase 3
   evidence: either the retrieval substrate can produce citeable evidence for that
   exact source field, or Phase 2 fails with an actionable diagnostic before Phase 3.
3. Bounded Step 1b repair diagnostics teach the LLM to replace non-citeable or
   lane-incompatible source fields with real exact, citeable lanes; it must not
   invent evidence or downgrade required topics.
4. Phase 3 remains a strict consumer gate. It still fails on weak/missing required
   topic evidence; the fix is upstream in Phase 2 planning/normalization/retrieval
   substrate viability, not a Phase 3 healing loop.

### Latest live failure being addressed

Read-only diagnostic run:
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-160914`

This run made progress: live Phase 2 bounded repair succeeded, planned coverage was
`13/13`, topic obligations were `59/59`, and Phase 3 retrieved `22/22` packets with
`704` evidence items. It then correctly failed before Phase 4 with evidenced coverage
`56/59` sufficient, `1` weak, and `2` missing.

Blocking examples to reproduce non-live:

- `architecture-go-backend` / **Explain the build process for the Go components.**
  mapped to `retrieval_needs.files[1]` (`go.mod`). `go.mod` existed in the inventory
  but produced no citeable evidence in the packet; `build.sh` produced citeable
  evidence but was not the topic's source field.
- `ops-build-cicd` / **Explain how to build the RAGFlow Docker images locally.**
  mapped to `retrieval_needs.files[0]` (`Dockerfile`). `Dockerfile` existed in the
  inventory but produced no citeable evidence in the packet; `docs/develop/build_docker_image.mdx`
  and `README.md` produced citeable build-image evidence but were not exact TER
  source fields.
- `testing` / **Explain where to add new tests for a new feature.** mapped to
  `retrieval_needs.tests[0]`, while `acceptable_lanes[]` listed `file_anchor`; Phase
  3 therefore treated the topic as weak even though the Phase 2 obligation gate had
  marked it complete.

### Failure classification

- The `acceptable_lanes[]` / source-field lane mismatch is a deterministic Phase 2
  obligation-contract defect. The producer-side obligation gate and the Phase 3
  consumer must agree on lane semantics. Fix the shared Phase 2 gate/diagnostics so
  this mismatch fails before Phase 3.
- Exact file lanes that resolve in inventory but have no citeable retrieval coverage
  are a Phase 2/Phase 1 retrieval-substrate viability defect. Do not make Phase 3
  synthesize fallback evidence. Either make the deterministic retrieval substrate able
  to cite those source files, or make Phase 2 fail loudly and feed repair the exact
  non-citeable source-field diagnostics so it chooses a citeable exact source field.
- If the bad source-field choice is LLM-authored, bounded Step 1b repair may re-prompt
  with the deterministic diagnostics, but success still requires strict normalization,
  planned coverage, topic obligations, and — where this slice adds a non-live viability
  check — TER evidence viability. Generic retry-until-green is forbidden.

### Required implementation contract

The implementation should add a deterministic producer-side check, or strengthen the
existing topic-obligation gate, so enhancement mode catches the live failure classes
before Phase 3 when possible.

Minimum required checks:

1. **Lane/type consistency**: for each valid exact `source_fields[]` entry, the exact
   lane implied by the field (`files → file_anchor`, `symbols → symbol_anchor`,
   `contracts → contract`, `tests → test`, `query_packs → query_pack`) must be present
   in `acceptable_lanes[]`. If no valid exact source field is both present and
   acceptable, the topic is incomplete.
2. **Citeable source availability**: for exact file/source fields, Phase 2 should be
   able to identify whether the retrieval substrate can produce citeable evidence for
   the referenced handle. At minimum, non-live fixtures must cover files that exist in
   inventory but have no `rag/chunks.jsonl` coverage, and those TER source fields must
   fail with an actionable diagnostic rather than passing Phase 2 and failing later in
   Phase 3.
3. **Repair diagnostics**: `plan-repair --coverage-mode enhancement` must include the
   lane/type and citeable-availability diagnostics in its audited prompt and must not
   accept a repair that only satisfies the older topic-obligation checks while still
   containing non-citeable or lane-incompatible TER source fields.
4. **Strict consumers preserved**: Phase 3 evidenced coverage and Phase 4 generated
   coverage must remain strict. Do not add fallback evidence, fuzzy topic matching,
   synthetic citations, `--force`, product `--section`, or post-hoc wiki/evidence
   mutation.

### Candidate diagnostics

Names are not mandatory, but diagnostics should be machine-readable and actionable.
Suggested codes:

- `topic_evidence_requirement_lane_not_acceptable`: a source field points at an exact
  lane not listed in `acceptable_lanes[]`.
- `topic_evidence_requirement_no_acceptable_exact_source_field`: the TER has exact
  fields, but none are both valid and acceptable.
- `topic_evidence_requirement_source_not_citeable`: the source field resolves to an
  exact handle that the retrieval substrate cannot cite.

Diagnostics should name the section, topic, source field, normalized lane, referenced
handle/path, why it is not sufficient, and the remediation: point the TER at an exact
`retrieval_needs.*` lane that is both acceptable and citeable, or improve the
retrieval substrate upstream.

### Non-live implementation boundary

This slice must be implemented and verified without Vertex, Gemini API, Gemini Gem
live/manual production flows, or any billed provider. Use deterministic fixtures,
existing read-only live artifacts, and injected/fake repair clients. The live run
`20260626-160914` is diagnostic input only. Do not rerun live/billed RAGFlow until
this non-live slice passes and the user explicitly approves a later retry.

### Acceptance — next slice

Accept this slice only when non-live artifacts/tests prove:

- a TER using `retrieval_needs.tests[0]` with `acceptable_lanes:["file_anchor"]`
  fails the Phase 2 enhancement obligation/viability gate before Phase 3 with an
  actionable lane/type diagnostic;
- a TER using `retrieval_needs.tests[0]` with `acceptable_lanes:["test"]` remains
  valid when the referenced test lane is otherwise citeable;
- an exact file field pointing at a file that exists in inventory but has no citeable
  retrieval substrate coverage fails before Phase 3 in enhancement mode;
- an exact file field pointing at a file with citeable chunk/evidence availability
  passes the new viability check;
- a live-style fixture for the three `20260626-160914` blockers fails pre-Phase3
  before repair and passes after a fake-client bounded repair points the topics at
  lane-compatible, citeable exact source fields;
- `plan-repair --coverage-mode enhancement` audits the new diagnostics and rejects an
  old-style repair that still has lane/type or non-citeable source-field defects;
- baseline/default behavior remains non-breaking/report-only;
- Phase 3 and Phase 4 validators remain strict; no synthetic evidence, benchmark-derived
  evidence, silent downgrade, generic healing loop, `--force`, or product `--section`
  mode is added;
- `git diff --check`, protected-spec diff check, focused Phase 2/3/repair tests, and
  the full suite pass with `uv run python -m pytest -q`.

## Phase 3 Evidence Sufficiency Contract — implemented non-live slice

This slice must make Phase 3 answer a narrow, deterministic question:

```text
For each planned required topic, did retrieval produce enough citeable repo
evidence to let Phase 4 write that topic?
```

It must **not** make evidence exist. It validates and reports evidence sufficiency.
In enhancement mode, weak or missing required evidence is a blocking pipeline
failure before Phase 4.

### Artifact being designed

Phase 3 should add evidenced-coverage artifacts alongside the existing evidence
packet set:

- `evidence/evidenced-coverage.json` — machine-readable per-section/per-topic
  status matrix;
- `evidence/evidenced-coverage-report.md` — human-readable summary and
  remediation;
- `evidence/retrieval-validation.json` — should include a named contract check
  such as `required_topic_evidence_sufficient`;
- `evidence/evidence-manifest.json` — should reference the new artifacts if they
  are written.

These artifacts must be deterministic and timestamp-free like the existing Phase 3
outputs.

### Deterministic topic-to-evidence mapping

Do not solve topic coverage with fuzzy prose matching. The contract should be
based on explicit planned evidence obligations.

The preferred normalized SectionPlan field is additive and optional in baseline
mode:

```json
"topic_evidence_requirements": [
  {
    "topic": "Redis Streams lifecycle",
    "required": true,
    "source_fields": ["retrieval_needs.files[0]", "retrieval_needs.symbols[1]"],
    "min_items": 1,
    "acceptable_lanes": ["file_anchor", "symbol_anchor", "contract", "test", "query_pack"]
  }
]
```

Rules:

- This is plain structured JSON, not a DSL.
- Phase 2 normalization should preserve `topic_evidence_requirements[]` when the
  planner or a fixture provides it, and planner prompt surfaces should ask for it
  in enhancement mode.
- `source_fields[]` must reference real normalized `retrieval_needs.*` entries.
  It is a deterministic bridge from a required topic to exact retrieval requests.
- Evidence is mapped through existing Phase 3 exact-request coverage records and
  final `evidence_id`s, not by comparing generated prose.
- Broad recall (`bm25`, `vector`, `graph_neighbors`, search hints without exact
  source fields) may be reported as supporting context but must not by itself make
  a required topic `sufficient` in enhancement mode.
- If a section has `required_topics[]` but lacks deterministic topic evidence
  requirements, enhancement mode should fail with remediation to fix the Phase 2
  plan/prompt/schema upstream. Do not guess that all section evidence supports all
  topics.

### Status definitions

For each required topic:

- `sufficient` — the topic has at least `min_items` citeable evidence IDs mapped
  from covered exact source fields on acceptable lanes, and those evidence items
  pass the existing anchor/context/plan-only validation.
- `weak` — some related evidence exists but it is below threshold, only broad
  recall, low-confidence/non-exact, unmapped to explicit source fields, or
  otherwise not enough to safely write the required topic.
- `missing` — no citeable evidence maps to the topic, no valid source fields are
  present, or the section lacks topic evidence requirements in enhancement mode.
- `not_applicable` — permitted only for explicitly non-source sections such as
  `section_role: provenance` / meta sections that are already handled outside the
  normal evidence lanes.

In enhancement mode, every required topic in a normal source-evidence section must
be `sufficient`. Any `weak` or `missing` required topic is exit-code `3` using the
existing `bad_underspecified_normalized_plan` category, with a diagnostic code
such as `required_topic_evidence_weak` or `required_topic_evidence_missing`.

### Failure policy: no healing

This gate is upstream prevention by failure, not a healing loop:

- no generic retry-until-green;
- no product `--section` rescue/debug mode;
- no `--force` after readiness failure;
- no synthetic evidence;
- no silent downgrade from required to optional;
- no automatic mutation of the plan to attach convenient sources;
- no use of `derived/`, `plans/`, generated wiki files, or
  `ragflow-deepwiki.md` as citeable evidence;
- no validator weakening.

If the gate fails, the correct remediation is to fix the upstream deterministic or
LLM-authored producer: improve Phase 2 topic/source obligations, improve retrieval
lanes/indexing/source mapping, or explicitly accept a human-reviewed known gap.
Phase 4 must not run in enhancement mode while required evidence is weak or
missing.

### CLI and mode behavior

The implementation should add an opt-in Phase 3 gate, for example:

```text
wiki-generator retrieve-evidence --bundle <bundle> --coverage-mode enhancement
```

Expected behavior:

- default `baseline` mode remains backward-compatible and non-breaking;
- baseline mode may write evidenced-coverage reports when enough metadata exists,
  but it must not fail legacy compact fixtures only because topic-level
  obligations are absent;
- `enhancement` mode fails before Phase 4 on weak/missing required-topic evidence;
- the command remains all-sections only; do not add product `--section` or retry
  loops.

## Phase 4 Generated Coverage Contract — implemented non-live slice

This slice must make Phase 4 answer the final coverage question:

```text
For each planned and evidenced required topic, did the generated wiki actually
cover it with valid citations, while preserving the planned hierarchy?
```

The target artifact is a **hierarchical, citation-grounded generated wiki** plus
machine-readable generated-coverage metadata. The quality bar is not line count;
it is that every planned/evidenced required topic is represented in generated
output, backed by valid EvidencePacket citations, and independently validated.

### Artifact being designed

Phase 4 should extend the existing wiki output set with generated-coverage
artifacts:

- hierarchical `wiki/index.md` navigation derived from `parent_section_id`, while
  still generating one page for every planned `section_id`;
- `wiki/metadata/generated-sections.jsonl` rows augmented with `parent_section_id`,
  `coverage_labels[]`, `required_topics[]`, evidenced topic status, and generated
  topic status;
- `wiki/metadata/generated-document.json` including generated-coverage artifact
  paths and enhancement-mode status;
- `wiki/metadata/generated-coverage.json` — machine-readable planned/evidenced
  vs generated topic matrix;
- `wiki/validation/generated-coverage-report.md` — human-readable coverage report;
- `wiki/validation/writing-validation.json` with a named check such as
  `generated_required_topics_covered`.

These artifacts must be deterministic and timestamp-free. They must not modify
historical generated wiki runs in place.

### Enhancement-mode upstream gates before provider calls

Phase 4 should gain an opt-in mode, for example:

```text
wiki-generator write-wiki --bundle <bundle> --provider fake-or-gem --coverage-mode enhancement
```

Expected behavior:

- default `baseline` mode remains backward-compatible and non-breaking for compact
  fixtures;
- enhancement mode fails before any provider/model call unless Phase 2 planned
  coverage passed and Phase 3 evidenced coverage passed;
- Phase 2 planned coverage should be established from `plans/coverage-gate.json`
  written by `normalize-plan --coverage-mode enhancement` (or an equivalent
  existing deterministic gate artifact if the implementation already provides one);
- Phase 3 evidenced coverage should be established from
  `evidence/evidenced-coverage.json` and/or the
  `required_topic_evidence_sufficient` retrieval-validation contract check;
- if either upstream gate is absent, baseline/report-only, stale, or failed,
  enhancement-mode Phase 4 exits as an upstream gate failure (`3`) with remediation
  to rerun/fix the owning upstream phase. It must not rerun Phase 2 or Phase 3,
  repair plans, retrieve evidence, or synthesize evidence.

### Deterministic generated-topic coverage validation

Do not validate generated topic coverage with vague line-count, section-count, or
fuzzy prose similarity.

The preferred deterministic contract is:

1. The WritingPacket includes each section's hierarchy fields and the Phase 3
   evidenced topic rows for that section. For each `sufficient` required topic,
   the packet tells the writer which exact `evidence_id`s support that topic.
2. The section response schema is extended in a backward-compatible way to include
   a structured topic coverage declaration, for example:

   ```json
   "covered_topics": [
     {
       "topic": "Redis Streams lifecycle",
       "status": "covered",
       "evidence_ids": ["ev:task-queues:0002"],
       "markdown_anchor": "redis-streams-lifecycle"
     }
   ]
   ```

3. Final validation checks this declaration deterministically:
   - every planned/evidenced `sufficient` required topic has a generated coverage
     row with status `covered`;
   - every listed `evidence_id` is in the Phase 3 evidenced topic's mapped IDs or
     the section's allowed evidence IDs, resolves through the citation manifest,
     and is actually cited in the generated markdown;
   - the generated markdown contains the topic text or declared markdown anchor in
     a non-empty paragraph/list item/heading with valid citations;
   - no generated coverage row may rely on context artifacts, `derived/`, `plans/`,
     generated wiki files, or `ragflow-deepwiki.md`;
   - omitted topics, empty placeholders, malformed citations, unsupported
     identifiers, and context-artifact citations fail final validation.

This validation can check the writer's structured declaration and citation usage;
it should not attempt semantic fuzzy matching against the benchmark DeepWiki.

### Hierarchical writing behavior

Phase 4 must treat parent/child section metadata as first-class:

- prompts should include `parent_section_id`, sibling/child context, coverage
  labels, required topics, and evidenced topic rows;
- `index.md` should render nested contents rather than a flat-only numbered list;
- metadata should preserve parent/child relationships for every generated page;
- broad parent pages alone must not be counted as generated coverage for child
  families or child required topics;
- baseline fixtures may keep existing flat behavior unless enhancement mode is
  explicitly requested.

Filesystem layout may remain backward-compatible (`sections/NNN-section-id.md`) if
metadata and navigation preserve hierarchy. Do not force a path migration unless it
is necessary and covered by tests.

### Failure policy: no healing

Generated coverage failures are not repair targets for deterministic code:

- no generic retry-until-green loop;
- no synthetic filler or topic stubs to satisfy coverage;
- no automatic mutation of `covered_topics[]` after the model returns;
- no downgrading required topics to optional;
- no weakening citation, malformed-token, unsupported-identifier, placeholder,
  truncation, no-context, or no-`--force` validators.

A bounded LLM rewrite may remain only for the existing narrow format/citation
failure categories already covered by strict validation. It must not add evidence,
change topic obligations, or paper over missing generated coverage.

### Non-live implementation boundary

This slice was proven with fake-provider or deterministic non-live fixtures.
It did not call Vertex, Gemini API, Gemini Gem live/manual production flows, or any
billed model. Later non-live hierarchical E2E also completed; the current blocker
is the Phase 2 required-topic evidence-obligation alignment described above.

## Non-live Hierarchical E2E and Benchmark-Only Comparison Contract — completed slice

This completed slice proved the enhancement pipeline as a whole, not merely isolated
unit fixtures:

```text
expanded hierarchical plan -> planned coverage gate -> evidenced coverage gate
-> generated coverage gate -> benchmark-only coverage/structure review
```

The target artifact was a **fresh, non-live hierarchical E2E run directory** plus a
human-readable result report. It demonstrated that the enhanced gates can work
together over an expanded multi-family plan before any billed/live retry is
requested.

### Artifact being designed

Create a fresh run under a non-live workspace such as:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/non-live-hierarchical-runs/<timestamp-or-run-id>/
```

The run should contain, at minimum:

- `command-manifest.tsv` with exact commands and exit codes;
- `command-transcript.log` with stdout/stderr snippets sufficient for review;
- an expanded hierarchical bundle or fixture plan covering multiple mandatory
  topic families, with `parent_section_id`, `coverage_labels[]`,
  `required_topics[]`, and `topic_evidence_requirements[]` preserved;
- `plans/coverage-gate.json` + `plans/coverage-gate-report.md` from the real
  planned-coverage gate where possible;
- `evidence/evidenced-coverage.json` + report from
  `retrieve-evidence --coverage-mode enhancement`;
- `wiki/metadata/generated-coverage.json` +
  `wiki/validation/generated-coverage-report.md` from
  `write-wiki --coverage-mode enhancement`;
- a nested `wiki/index.md` and generated-section/document metadata preserving
  hierarchy;
- `NON_LIVE_HIERARCHICAL_E2E_RESULT.md` summarizing verdict, commands, gate
  statuses, coverage counts, known gaps, and whether any live retry is justified;
- a benchmark-only comparison note/report against `ragflow-deepwiki.md` that
  discusses coverage/structure gaps without citing it as evidence.

Generated bulky run artifacts should not be committed unless they are small,
intentional, and already consistent with repository tracking policy. The durable
implementation backlog and final status must be mirrored in this spec/handoff and
`docs/README.md`.

### Required command/path behavior

The E2E task must use the real CLI/script surfaces that a future operator would
use. If a wrapper is missing an implemented flag, fix the wrapper upstream rather
than bypassing it silently. In particular, verify and, if necessary, update:

- `scripts/phase2_step2_normalize_plan.sh` supports/passes
  `--coverage-mode enhancement` to `normalize-plan`;
- `scripts/phase3_retrieve_evidence.sh` supports/passes
  `--coverage-mode enhancement` to `retrieve-evidence`;
- `scripts/phase4_write_wiki.sh` supports/passes
  `--coverage-mode enhancement` to `write-wiki`.

A wrapper gap is a deterministic upstream defect. Fix the script/help/tests and
rerun from the affected phase; do not hand-edit downstream artifacts to compensate.

### Non-live provider boundary

Do not call Vertex, Gemini API, Gemini Gem live/manual production flows, or any
billed model for this slice.

Acceptable approaches:

- deterministic fixture or synthetic mini-repo that exercises multiple mandatory
  topic families and hierarchy;
- a fake provider injected through Python-level Phase 4 wiring;
- gemini-gem prepare/validate mode only if no model is called and responses are
  deterministic fixtures.

If the current shell wrapper cannot inject a fake provider, the agent may add a
small non-live harness or test-oriented script, but it must keep production CLI
behavior honest and documented.

### Gate behavior to prove

The run/report must prove:

- planned coverage passes in enhancement mode for an expanded multi-family plan;
- a compact/broad-parent-only plan would still fail where required by existing
  tests (do not weaken the gate to make the E2E pass);
- evidenced coverage passes with exact mapped `evidence_id`s for required topics;
- Phase 4 refuses to start in enhancement mode if upstream planned/evidenced gates
  are missing/baseline/failed;
- generated coverage passes only when each evidenced sufficient required topic is
  actually covered and locally cited;
- generated coverage artifacts are deterministic on rerun for the same inputs;
- all existing citation, malformed evidence token, unsupported identifier,
  context-artifact, placeholder, truncation, stale/no-`--force`, and coverage
  validators remain strict.

### Benchmark-only comparison

Compare the non-live generated hierarchy/coverage matrix against:

```text
/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md
```

Rules:

- benchmark-only; never citeable evidence;
- no copying sections, headings, prose, or claims into generated output;
- no line-count parity target;
- report coverage/structure gaps by topic family and planned/evidenced/generated
  status;
- explicitly state whether the non-live E2E is enough to request user approval for
  a live/billed retry. The default should remain **no live retry** unless all gates
  pass cleanly and the user explicitly approves.

### Failure policy: fix upstream, not heal

- Deterministic wrapper/validator/artifact defects must be fixed upstream and
  tested.
- Weak/missing planned or evidenced required-topic coverage remains a pipeline
  failure before Phase 4 in enhancement mode.
- Missing generated coverage remains a Phase 4 writing-validation failure after
  provider/fake-provider output.
- Do not add retry-until-green, synthetic evidence, filler topics, silent
  required-to-optional downgrades, benchmark-derived evidence, or validator
  weakening.
- If the fake provider or fixture is insufficient, improve the fixture/harness or
  prompt contract; do not mutate generated coverage declarations post hoc.

### Completed-slice acceptance — non-live hierarchical E2E

This slice is accepted because the agent reported and committed evidence that:

- all three enhancement gates were exercised together in one fresh non-live run;
- wrapper help/behavior exposes the enhancement flags needed to reproduce the run;
- run artifacts and `NON_LIVE_HIERARCHICAL_E2E_RESULT.md` exist in the non-live
  workspace;
- the benchmark-only comparison exists and does not treat `ragflow-deepwiki.md` as
  evidence;
- relevant focused tests and the full suite pass via `uv run python -m pytest -q`;
- protected Phase 3 spec content is unchanged;
- no live/billed provider was called;
- docs/handoff/status are updated with verdict, run path, risks, and remaining
  live-retry approval status.

## Milestone 1 — immediate writing-validation enhancement

This milestone is implemented locally and tested. It was the first implementation
target because it is small, non-live, and required before any further strict
sign-off claim.

### Problem

The generated live wiki contains this malformed evidence-like token:

```text
[ev:data-models:010]
```

Affected generated artifact:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki/sections/010-data-models.md
```

The canonical citation format uses four-digit ordinals:

```text
[ev:<section_id>:<NNNN>]
```

The malformed token escaped validation. That is unacceptable for strict sign-off.

### Required behavior

1. The only valid citation syntax remains `[ev:<section_id>:<NNNN>]`, with the
   section-id grammar matching existing code and the ordinal exactly four digits.
2. Valid-looking citations must still resolve through
   `wiki/metadata/citation-manifest.json`.
3. Any bracketed evidence-like token beginning with `[ev:` that does not match
   canonical syntax must fail validation loudly.
4. Dangling `[ev:` sequences must fail validation loudly.
5. During bounded section drafting, malformed evidence-token failures are
   **rewriteable**: the rewrite prompt may ask the model to replace the malformed
   token with an exact manifest citation or remove the unsupported claim.
6. In final validation, any remaining malformed evidence-token failure is
   terminal: the artifact must not be silently edited or auto-corrected.
7. Diagnostics must include token text, section id, section file/path when
   available, line/column when available, failure category, and remediation.
8. Suggested nearby IDs may be shown only when deterministic and safe. Example:
   suggest `[ev:data-models:0010]` for `[ev:data-models:010]` only if that exact
   manifest ID exists and the difference is simple zero-padding.
9. Existing validators must not be weakened: unsupported identifiers, manifest
   resolution, unused citations, context-artifact citations, placeholders, and
   truncation checks remain strict.

### Malformed examples that must fail

- `[ev:data-models:010]` — three-digit ordinal.
- `[ev:data-models:00010]` — five-digit ordinal.
- `[ev:data-models:]` — missing ordinal.
- `[ev:data-models]` — missing ordinal separator.
- `[ev:data models:0010]` — invalid section-id characters if spaces are outside
  the existing grammar.
- `[ev:data-models:0010` — dangling opener / missing close.
- `[ev:data-models:0010 extra]` — extra text.
- `[ev:data-models:0010:extra]` — extra field.

### Likely implementation targets

- `src/wiki_generator/libs/writing/citations.py`
- `src/wiki_generator/libs/writing/validate.py`
- Phase 4 bounded rewrite feedback/prompt plumbing
- `tests/test_phase4.py`

### Tests required

Unit tests:

- `[ev:data-models:010]` fails as malformed.
- `[ev:data-models:0010]` can pass when the manifest contains that exact ID.
- Well-formed but unknown citations still fail manifest resolution.
- Existing valid citations continue to pass.
- The malformed examples above all fail with useful diagnostics.

Fake-provider integration tests:

1. First draft contains a malformed citation.
2. Draft validation detects it.
3. Bounded rewrite receives clear feedback.
4. Fake provider returns a corrected section using a valid manifest citation.
5. Final validation passes.

Also test the failure path where rewrite leaves the malformed token and final
validation fails.

### Milestone 1 acceptance commands

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
uv run python -m pytest -q tests/test_phase4.py
uv run python -m pytest -q
```

No Vertex/Gemini/API calls are allowed for Milestone 1.

## Milestone 2 — DeepWiki-informed coverage enhancement

This is the broader enhancement track. It should not start by increasing token
limits. It starts by changing the artifact target, planning, evidence, and
coverage validation.

### Required topic families

The enhanced guide must plan for and cover, when repository evidence supports it:

1. Frontend/i18n/UI architecture — frontend structure, routing, state management,
   internationalization, component architecture, theming, and build/runtime
   integration.
2. Memory system — memory APIs, internals, storage, use in agent workflows, and
   raw/semantic/episodic/procedural concepts where supported.
3. Task queues and Redis Streams — queue names, task lifecycle, workers,
   cancellation, retries, parsing/indexing jobs, RAPTOR/GraphRAG/memory queues,
   and operations.
4. Kubernetes/Helm — charts, values, manifests, services/deployments, ingress,
   config, secrets, and deployment workflow.
5. CI/CD/build system — package managers, Docker build flow, dependency
   pre-caching, GitHub workflows, release scripts, image build/publish behavior,
   and developer commands.
6. Go/native components — Go server/admin/native pieces, build modes,
   parser/lexer/native services, and Python integration points.
7. Retrieval/search internals — document store abstraction, index selection,
   query transformation, hybrid search, reranking, filters, pruning, response
   generation, and citation insertion.
8. Document parsing/OCR/layout/chunking — parser factories, DeepDoc, MinerU,
   OCR/layout operators, chunking strategies, content enhancement, embedding,
   connectors, and upload-to-index pipeline stages.
9. LLM provider internals/tool calling/retry/usage — LLMBundle, model
   registration, providers, error classes, retry/backoff, usage tracking, tenant
   configuration, tool/function schemas, and tool-call execution.
10. User/tenant/admin/system health — user and tenant management, admin
    routes/services, auth/authorization, status probes, health endpoints,
    settings, and operational dashboards/commands.
11. Sandbox/code executor — sandbox manager, provider registry, configuration,
    security boundaries, code execution tool, and admin/operator controls.
12. Migrations/operations — database migrations/schema sync, ES-to-OceanBase
    migration, utility scripts, reset/admin commands, runbooks, and upgrade paths.
13. Glossary — repo-specific terminology, acronyms, component names, service
    names, queue names, data-store terms, and concepts used throughout the guide.

Additional desirable expansions:

- document engine selection and tradeoffs;
- dynamic component loading;
- API SDK architecture and request validation utilities;
- endpoint coverage tables for public API groups;
- diagrams or Mermaid summaries only when evidence supports the flow and
  relationships.

### Pipeline changes required

1. **Phase 1 repo analysis expansion**
   - Add deterministic inventories for apps/packages, docs, frontend, deployment,
     CI/CD, queue/task signals, memory, Go/native, API routes/SDK/auth/admin/
     health, LLM providers, migrations, sandbox, CLI/admin utilities, and tests.
   - Rank candidate subsystems and report low-signal areas before planning.

2. **Phase 2 hierarchical planning**
   - Produce a planned topic taxonomy with parent pages, child pages, stable IDs,
     required topics, optional topics, source-category obligations, cross-links,
     and a coverage matrix.
   - Prevent mandatory-family omissions through better prompt/context/schema and
     deterministic gating; if the LLM-authored plan still misses mandatory
     families in coverage-enhanced mode, allow only bounded audited LLM re-prompt
     with exact diagnostics and loud failure after the cap. Do not add generic
     healing loops around deterministic normalization or validation.

3. **PagePlan obligations**
   - Each page/child section must state required topic bullets, expected source
     handles/files/routes/docs/tests/contracts, evidence expectations, intended
     depth, cross-link targets, and coverage labels such as `frontend`,
     `queue-system`, `helm-k8s`, `memory`, `llm-provider`,
     `retrieval-internals`, and `operations`.
   - A broad parent page must not count as coverage for a child topic unless that
     child topic has its own evidence and generated content.

4. **Phase 3 page-level evidence retrieval**
   - Retrieve evidence per planned page/child section while preserving existing
     constraints: deterministic and LLM-free retrieval, one product run for all
     planned pages, no product `--section` retry loop, no `--force` after
     readiness failure, no context/generated/reference files as citeable evidence,
     and fail-closed missing-evidence behavior.
   - Evidence validation should report per-page and per-required-topic
     sufficiency.

5. **Phase 4 hierarchical writing**
   - Generate per planned page/child section.
   - Support longer page budgets only when evidence density justifies them.
   - Preserve citation, unsupported-identifier, malformed-token,
     no-context-citation, no-placeholder, no-truncation, and no-synthesis
     validators.
   - Emit metadata for planned-vs-generated coverage.

6. **Coverage validation and benchmark comparison**
   - Validate required topic taxonomy vs planned pages.
   - Validate planned pages vs evidence packets.
   - Validate planned required topics vs generated headings/prose markers.
   - Validate all citations, including malformed evidence-like token detection.
   - Compare generated coverage against `ragflow-deepwiki.md` as benchmark-only.
   - Report remaining gaps with planned/evidenced/generated status.

### Milestone 2 progress — coverage-validation slice (implemented, non-live)

This slice implements the safest, testable, non-live foundation of Milestone 2:
the planned-topic taxonomy and the deterministic coverage validator. It does NOT
yet expand Phase 1 signals, Phase 2 hierarchical planning, Phase 3 page-level
retrieval, or Phase 4 hierarchical writing — those remain pending.

Implemented:

- `src/wiki_generator/libs/coverage/taxonomy.py` — `TopicFamily` plus the thirteen
  mandatory topic families (frontend, memory, queue-system, helm-k8s, ci-cd-build,
  go-native, retrieval-internals, doc-processing, llm-internals,
  user-tenant-admin-health, sandbox-executor, migrations-operations, glossary),
  each with explicit coverage-label aliases and distinctive keyword signals.
- `src/wiki_generator/libs/coverage/validate.py` — `evaluate_plan_coverage(...)`
  returning a `CoverageReport` (per-family `FamilyCoverage` matrix, missing
  mandatory families, actionable diagnostics), a markdown renderer, and a plan
  loader. `enhancement` mode fails closed on a missing mandatory family;
  `baseline` mode reports coverage without enforcing.
- `src/wiki_generator/libs/commands/validate_coverage.py` + the `validate-coverage`
  CLI subcommand — loads a bundle's normalized Phase 2 plan, writes
  `coverage/coverage-validation.json` + `coverage-validation-report.md`, and exits
  `0` (pass / baseline), `2` (no normalized plan), or `3` (planned-coverage enhancement gate fail).
- `tests/test_coverage_validation.py` — proves a faithful compact 16-section
  baseline fails enhancement-mode coverage (passes report-only baseline mode); an
  expanded plan with all families passes; dropping frontend/memory/queue fails with
  exactly those diagnostics; a broad parent page does not satisfy a deep child
  family; substring false matches are avoided; the CLI gate works; and Milestone 1
  malformed-token validation is intact.

Detection discipline: a broad parent page (one "Core RAG Pipeline" section whose
only topic is the word "retrieval") does NOT count as coverage for a deep child
family; the child must declare the family's coverage label or carry the family's
distinctive vocabulary. The "evidenced" and "generated" coverage dimensions
(per-page EvidencePacket sufficiency, per-required-topic generated-heading checks)
are explicit next steps and are not asserted by this slice. The validator is NOT
wired into the default Phase 4 path (that would fail the small fixture bundles);
it is exposed as the standalone `validate-coverage` command/library scaffold.

### Milestone 2 progress — Phase 2 planning/PagePlan obligations (implemented, non-live)

This slice made the normalized Phase 2 plan capable of carrying coverage-enhanced
planning obligations end-to-end, without making coverage enforcement part of the
default Phase 4 path.

Implemented:

- `coverage_labels[]` are preserved in normalized `section-plans.jsonl` and
  normalized to canonical kebab labels.
- `parent_section_id` is preserved/resolved so parent/child page hierarchy can be
  represented in the canonical plan artifact.
- `required_topics` merges planner `coverage_requirements[]` and
  `required_topics[]` so PagePlan obligations survive normalization.
- `expected_sources[]` is preserved as planner expectation metadata.
- `document-plan.md` shows coverage labels and parent/child hierarchy.
- `normalization-report.md` includes a baseline/report-only DeepWiki coverage
  matrix; it does not gate readiness unless `validate-coverage --mode
  enhancement` is explicitly run.
- Planner prompt surfaces ask for canonical `coverage_labels[]`,
  `parent_section_id`, and the rule that a broad parent page does not satisfy a
  deep child topic.
- `tests/test_phase2_coverage_planning.py` proves field preservation,
  hierarchy, normalized-plan coverage validation, non-enforcing reports, prompt
  guidance, and Milestone 1 behavior remain intact.

### Milestone 2 progress — Phase 1 coverage-signal expansion (implemented, non-live)

This slice gives Phase 2 deterministic planner-facing coverage signals for all
thirteen mandatory topic families. These signals are planner context, not citeable
Phase 3 evidence.

Implemented:

- `src/wiki_generator/libs/coverage/signals.py` derives per-family coverage
  signals from deterministic source artifacts such as file inventory, query-pack
  hits, and symbols.
- `src/wiki_generator/libs/digest/planning_coverage_signals.py` renders the
  planner-facing condensate.
- Phase 1 condense/digest emits `derived/planning-coverage-signals.md` and the
  machine-readable `derived/coverage-signals.json` sidecar.
- The planner upload bundle includes `planning-coverage-signals.md` with an
  explicit warning that it is context-only and not citeable evidence.
- Missing or low-signal families are reported rather than hidden. Glossary is
  synthesized as a planner obligation, not as a source-backed citation target.
- `tests/test_coverage_signals.py` proves deterministic family detection,
  missing/low-signal reporting, non-citeable markdown/JSON metadata, and upload
  integration.

### Milestone 2 progress — Phase 2 enhancement-mode planned-coverage upstream-prevention gate (implemented, non-live)

This slice adds the deterministic Phase 2 → Phase 3 planned-coverage boundary and
makes the planner prompt/context explicitly consume the Phase 1 coverage signals.
It is upstream prevention by **loud deterministic failure**, not a healing loop:
the gate never synthesizes, adds, or repairs pages/labels/source obligations.

Implemented:

- `src/wiki_generator/libs/coverage/validate.py` adds a shared deterministic gate:
  `gate_plan_coverage(...)` → `CoverageGate` (verdict + exit code + actionable
  `summary_lines()`), plus `load_plan_from_dir(...)`; exit codes
  `COVERAGE_GATE_PASS_EXIT=0` / `COVERAGE_GATE_INPUT_EXIT=2` /
  `COVERAGE_GATE_FAIL_EXIT=3`.
- `normalize-plan` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). `baseline` keeps the existing non-enforcing matrix in
  `normalization-report.md` and never gates the command. `enhancement` runs the
  deterministic gate over the just-written normalized plan, writes
  `plans/coverage-gate.json` + `plans/coverage-gate-report.md`, logs diagnostics
  naming missing families + remediation, and exits `3` before Phase 3 retrieval.
- The standalone `validate-coverage` command now shares the same `gate_plan_coverage`
  (identical enforcement). No generic healing loop is added; bounded LLM re-prompt
  remains the existing, separately-audited `plan-repair` step (prompt/context/schema
  improved first).
- Planner prompt surfaces (`gemini-gem/GEM_INSTRUCTIONS.md`,
  `gemini-gem/KICKOFF_PROMPT.md`, `plan._DEFAULT_SYSTEM`, `plan._DEFAULT_KICKOFF`;
  the upload README already did) now explicitly cite `planning-coverage-signals.md`
  as planner CONTEXT, not citeable evidence, and warn that a coverage-enhanced run
  gates the plan against all thirteen families before Phase 3.
- `coverage_labels[]`, `parent_section_id`, merged `required_topics[]`, and
  `expected_sources[]` continue to survive normalization end-to-end.
- `tests/test_phase2_enhancement_gate.py` proves: full expanded plan passes (exit 0);
  missing frontend/memory/queue fails (exit 3) with exactly those diagnostics; a
  broad parent page alone does not satisfy a deep child family; baseline default is
  non-breaking (and an arg namespace without `coverage_mode` defaults to baseline);
  the gate does not synthesize/heal the plan; planner surfaces cite the coverage
  signals as context-only; Milestone 1 malformed-token validation remains intact.

The gate is **not** wired into the default Phase 4 path (that would fail the compact
fixture bundles); it is the explicit Phase 2 enhancement boundary. Evidenced and
generated coverage dimensions remain the next pending slices.

### Milestone 2 progress — Phase 3 evidenced coverage (implemented, non-live)

This slice implements the Phase 3 Evidence Sufficiency Contract above as a
deterministic per-required-topic evidence gate (not a healing loop). It validates
and reports evidence sufficiency; it never makes evidence exist.

Implemented:

- Phase 2 normalization preserves the additive, baseline-compatible
  `topic_evidence_requirements[]` SectionPlan field. Each item normalizes to
  `{topic, required (default true), source_fields[], min_items (default 1),
  acceptable_lanes[] (default exact lanes)}`; a baseline/legacy plan that omits it
  normalizes to `[]` and is unaffected. Planner prompt surfaces
  (`GEM_INSTRUCTIONS.md`, `KICKOFF_PROMPT.md`, `plan._DEFAULT_SYSTEM`/`_DEFAULT_KICKOFF`)
  now ask for it, pointing at real `retrieval_needs.*` source fields, and warn that
  broad recall is never sufficient and over-requiring fails before Phase 4.
- `src/wiki_generator/libs/evidence/evidenced_coverage.py` —
  `evaluate_evidenced_coverage(bundle, packets, options)` reads the normalized
  hierarchical plan (`coverage_labels[]`, `parent_section_id`, `required_topics[]`,
  `topic_evidence_requirements[]`) and maps each planned required topic through its
  `source_fields[]` to the packet's `coverage.exact_requests[]` records and their
  final citeable `evidence_id`s. Statuses: `sufficient`, `weak`, `missing`,
  `not_applicable`, each with counts, evidence IDs, source categories, and
  remediation. Broad recall (`bm25`/`vector`/`graph_neighbors`/`search_hints`) is
  reported as supporting context (can yield `weak`) but never makes a required topic
  `sufficient`.
- `retrieve-evidence` gains `--coverage-mode {baseline,enhancement}` (default
  `baseline`). Enhancement mode makes a `weak`/`missing` required topic in a normal
  source-evidence section a blocking pipeline failure BEFORE Phase 4: exit `3`,
  `bad_underspecified_normalized_plan`, surfaced as the
  `required_topic_evidence_sufficient` contract check in `retrieval-validation.json`
  and diagnostic codes `required_topic_evidence_weak`/`required_topic_evidence_missing`.
  Baseline mode is non-breaking (reports the matrix; adds no gate/contract check).
- Deterministic, timestamp-free artifacts `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`, referenced from `evidence-manifest.json`.
- No retrieval healing loop, no product `--section`/`--force`, no fallback rescue,
  no synthetic evidence, no silent required→optional downgrade, and no validator
  weakening. The gate is read-only and fails upstream. Context artifacts, `derived/`,
  `plans/`, generated wiki files, and `ragflow-deepwiki.md` remain non-citeable (a
  topic can only claim a real packet `evidence_id` from a covered exact request).
- `tests/test_phase3_evidenced_coverage.py` proves: an expanded fixture with
  explicit `topic_evidence_requirements[]` passes enhancement; a required topic with
  no mapped exact evidence fails before Phase 4 (exit 3,
  `bad_underspecified_normalized_plan`); a required topic supported only by broad
  recall is `weak` and blocking; baseline/default remains non-breaking; mapped IDs
  are real citeable packet IDs; normalization preservation; reruns are byte-identical;
  and the CLI exposes no `--section`/`--force`.

### Milestone 2 progress — Phase 4 hierarchical writing and generated coverage (implemented, non-live)

This slice implements the Phase 4 Generated Coverage Contract above as an opt-in
`write-wiki --coverage-mode {baseline,enhancement}` mode (default `baseline`,
fully non-breaking). It is upstream-trusting and deterministic: Phase 4 consumes the
Phase 2/3 enhancement gate artifacts and never reruns Phase 2/3, repairs plans,
retrieves evidence, or synthesizes evidence.

Implemented:

- `src/wiki_generator/libs/writing/options.py` adds `coverage_mode`
  (`baseline`/`enhancement`, validated); `src/wiki_generator/cli.py` +
  `libs/commands/write_wiki.py` add `--coverage-mode` (omitted-when-absent so an
  older arg namespace defaults to baseline).
- `src/wiki_generator/libs/writing/generated_coverage.py` — the enhancement engine:
  `read_enhancement_gates` verifies (pre-provider) that `plans/coverage-gate.json`
  is an enforced enhancement gate with `passed`/`status: pass`, that
  `evidence/evidenced-coverage.json` is `coverage_mode: enhancement` /
  `enforced: true` / `status: pass`, and that the
  `required_topic_evidence_sufficient` retrieval-validation contract check is
  present and passing; `build_topic_obligations` turns the evidenced matrix into
  per-section required-topic obligations carrying the exact Phase 3
  `mapped_evidence_ids`; `evaluate_generated_coverage` validates the writer's
  `covered_topics[]` declaration against the generated markdown (every sufficient
  required topic declared `covered`, evidence IDs within the topic's mapped set,
  resolving through the citation manifest, and cited within the topic's local
  markdown block near its text/anchor).
- `libs/writing/bundle.py` runs the enhancement gate inside `load_and_gate` as a
  sixth pre-provider gate (a missing/baseline/failed upstream gate raises
  `GateFailure`, exit 3) and attaches `evidenced_coverage` + `topic_obligations` to
  the `WritingBundle`.
- `libs/writing/packet.py` + `prompt.py` carry the planned hierarchy
  (`parent_section_id`, `coverage_labels`, child ids) and the evidenced topic rows
  (exact supporting `evidence_id`s) into each WritingPacket/prompt, and extend the
  section response contract with `covered_topics[]` (topic/status/evidence_ids/
  markdown_anchor) — backward-compatible (baseline packets/prompts are unchanged).
- `libs/writing/validate.py` carries the writer's `covered_topics[]` through
  section validation and adds the named final whole-document check
  `generated_required_topics_covered`; a failure is a writing-validation failure
  (exit 5) after provider output and is never papered over by the bounded rewrite.
- `libs/writing/assemble.py` renders a nested `index.md` from `parent_section_id`
  (flat when no hierarchy, so compact fixtures stay byte-identical), augments
  `generated-sections.jsonl` rows with hierarchy + evidenced/generated topic status,
  references the coverage artifacts + hierarchy from `generated-document.json`, and
  writes deterministic `wiki/metadata/generated-coverage.json` +
  `wiki/validation/generated-coverage-report.md`.
- All existing writing validators remain strict (citation resolution, malformed
  evidence tokens, unsupported/synthesized identifiers, context artifacts,
  placeholders, truncation, no-`--force`, stale/coherent packets). No generic
  healing loop, no synthetic filler, no required→optional downgrade, no post-hoc
  mutation of model-authored `covered_topics[]`, and `ragflow-deepwiki.md` is never
  citeable.
- `tests/test_phase4_generated_coverage.py` proves: enhancement happy path over a
  real decomposed+retrieval-built bundle writes a nested index + generated-coverage
  artifacts and passes; WritingPackets carry the exact mapped evidence IDs;
  pre-provider exit-3 gate failures for missing/baseline/failed planned gate,
  missing/baseline evidenced gate, and missing retrieval contract check (with NO
  provider call); post-provider exit-5 failures for an omitted topic, a topic
  declared without local citation, a topic cited with out-of-scope IDs, and a
  placeholder-only topic; baseline/default stays non-breaking (no gate, no
  generated-coverage artifact/check); rerun byte-identical; plus pure-evaluator
  units and CLI-surface checks (`--coverage-mode` present, no `--section`/`--force`).

### Milestone 2 progress — non-live hierarchical E2E + benchmark comparison (implemented, non-live)

This final non-live validation slice proves the three enhancement gates interoperate
over one fresh expanded multi-family hierarchical plan using the real production CLI.

Implemented:

- The three phase shell wrappers (`scripts/phase2_step2_normalize_plan.sh`,
  `scripts/phase3_retrieve_evidence.sh`, `scripts/phase4_write_wiki.sh`) now expose
  and pass `--coverage-mode {baseline,enhancement}` (a deterministic upstream wrapper
  defect: the CLI already supported the flag but the wrappers did not forward it).
  `tests/test_phase_wrappers.py` proves the surface (the `--help` path exits before any
  venv install, so it is fast/deterministic/offline).
- `scripts/nonlive_hierarchical_e2e.py` is a small, plain-Python, **no-model** harness
  that: builds a synthetic 13-family `ragdemo` repo (one real class symbol per
  mandatory family); runs `decompose`/`build-retrieval` (embeddings/vectors off);
  authors a raw Phase 2 planner response and runs the real `normalize-plan
  --coverage-mode enhancement` (producing `plans/coverage-gate.json`); runs the real
  `retrieve-evidence --coverage-mode enhancement` (producing
  `evidence/evidenced-coverage.json` with real mapped `evidence_id`s); then drives the
  real `write-wiki --provider gemini-gem --coverage-mode enhancement` via the genuine
  Gem import path, with per-section response fixtures synthesized **deterministically
  from the real Phase 3 evidenced-coverage matrix** (the exact mapped IDs — never
  synthetic evidence, never a model call). It adds a non-destructive negative probe
  (Phase 4 refuses pre-provider with exit 3 when the planned gate is absent) and a
  same-inputs rerun determinism check, and emits `command-manifest.tsv`,
  `command-transcript.log`, `NON_LIVE_HIERARCHICAL_E2E_RESULT.md`, and a benchmark-only
  `COMPARISON_WITH_RAGFLOW_DEEPWIKI.md`.

Validated run (non-live): planned 13/13 families, evidenced 13/13 sufficient,
generated 13/13 covered, whole-document writing-validation pass, nested hierarchical
`index.md`, byte-identical on rerun, negative probe exit 3. Benchmark
(`ragflow-deepwiki.md`, 909 headings / 14,717 lines) compared structurally only; no
prose copied; never citeable evidence. Run path (outside the repo, not committed):
`/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/non-live-hierarchical-runs/20260624-nonlive/`.

### Active pending slice — Phase 4 claim/token planning and grounded rendering

This is the next approved non-live implementation slice. It is an upstream
prevention change inside Phase 4 `write-wiki`, not a new top-level pipeline phase
and not a runtime healing loop.

Current top-level pipeline remains:

```text
Phase 1: decompose -> condense -> digest -> bundle -> build-retrieval
Phase 2: plan -> optional bounded plan-repair -> normalize-plan
Phase 3: retrieve-evidence
Phase 4: write-wiki
```

The Phase 4 internals should move from one-shot prompt hardening toward this
artifact flow:

```text
Phase 4 write-wiki
  4A derive allowed token bank from each WritingPacket/EvidencePacket
  4B ask the LLM for a structured claim/token plan with token references/placeholders
  4C deterministically validate that plan
  4D render accepted markdown with deterministic token substitution
  4E run the existing final writing/generated-coverage validation and assembly
```

#### Why this slice exists

Temporary Phase 4 Pi-worker hardening showed that short one-shot examples can fix
individual failure classes but do not scale. For example, the one-shot route
example in commit `3eb72b6` removed the prior invented route tokens
`/{api_version}` and `/api/{api_version}` from the next fresh temp run:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260627-153414-phase4-temp-pi-gpt54-3eb72b6
```

That same run then failed on another synthesized token:

```text
HttpClient.request
```

The general failure class is that the writer converts evidence into convenient
technical shorthand that is not verbatim evidence: import-to-FQN synthesis,
class/member dotted names, route templates, nested JSON paths, file/path expansion,
and route-family ellipses. Validators are correctly rejecting these. The scalable
fix is to make unsupported terminal technical tokens unrepresentable in the normal
Phase 4 path.

Supporting research artifact:

```text
/Users/ankitsingh/Documents/deep-wiki/.deep-research-phase4-grounded-generation-strategy/synthesis.md
```

#### Target artifact

The target implementation artifact is a Phase 4 **GroundedSectionDraft** flow: each
generated section is backed by a deterministic token bank plus an LLM-authored
claim/token plan that is validated before accepted markdown is rendered.

A good output is still a readable DeepWiki-style `GeneratedSection`, but the final
accepted path must not depend on the model freely typing terminal technical strings.
The model may write prose intent/skeleton text and token placeholders/references;
deterministic code must substitute exact token strings from the validated token
bank. Identifiers, routes, paths, imports, JSON paths/keys, env vars, commands,
package names, and qualified names are terminal technical claims and must either:

1. appear as exact tokens in cited evidence or citeable metadata;
2. be emitted by a trusted deterministic alias/token table with provenance; or
3. be omitted / expressed as prose without creating a new terminal token.

#### Required behavior

1. **Deterministic token bank**
   - Build a per-section token bank from the existing Phase 4 WritingPacket and
     EvidencePacket data. This can happen inside Phase 4; do not modify
     `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` for this slice.
   - Each token entry should include a stable token id, exact string, token kind,
     supporting evidence id(s), and source/provenance metadata sufficient for audit.
   - Token kinds should cover at least routes/public routes, file paths, imports,
     module/class/function/method names, env vars, command names, JSON keys/paths
     when exact, package names, and code/config literal prefixes.
   - Composite tokens such as `Parser._pdf`, `quart_auth.AuthUser`,
     `HttpClient.request`, `/api/{api_version}`, `data.graph`, or `/api/v1/...`
     are allowed only when that exact composite appears in the token bank with
     provenance. Otherwise the validated plan must use separate exact token
     references or ordinary prose that does not introduce the composite token.
   - Persist token-bank audit artifacts under `wiki/audit/` or `wiki/metadata/` so
     validation failures can be inspected without reading model prompts.

2. **Structured claim/token plan before accepted markdown**
   - Add a simple JSON artifact, not a custom DSL, for the LLM-authored claim plan.
     A claim should identify its claim kind, cited evidence ids, selected token ids,
     and a short prose intent/skeleton that uses token ids/placeholders for terminal
     technical strings instead of spelling those strings freely.
   - The claim plan must not be considered grounded merely because it is JSON. It
     is grounded only after deterministic validation.
   - The plan prompt must teach the writer to select token ids or omit technical
     shorthand; it should not rely on an ever-growing list of negative examples.

3. **Deterministic plan validation**
   - Fail the plan before accepted markdown is rendered if it references unknown
     evidence ids, unknown token ids, required topics without claim coverage, or
     free-form terminal technical tokens outside the approved token references.
   - Token ids carry their own provenance, placeholders are authoritative, and
     required-topic linkage may be evidence-derived. If a skeleton uses a known token
     placeholder but omits it from `token_ids[]`, the validator should derive the
     token use and warn rather than fail; unknown placeholders still fail. If a claim
     uses a token id but does not manually include that token's provenance evidence
     id, the renderer must attach the token provenance citation deterministically. If
     a claim omits `required_topic` but uses evidence mapped to exactly one required
     topic, the validator may derive that topic linkage and warn. These are
     provenance-preserving structural normalizations, not output patching.
   - Fail closed on ambiguous compositions. If `HttpClient` and `request` are
     separately evidenced but `HttpClient.request` is absent from the token bank,
     the dotted token must be rejected.
   - Validation diagnostics must name exact claim ids, token ids/strings, evidence
     ids, and remediation. They should create executable upstream work, not mutate
     final output.

4. **Markdown rendering from accepted plan**
   - The final section markdown should be rendered from accepted claims, prose
     skeletons, exact token-bank references, and renderer-attached claim/token
     citations. Terminal technical strings should be inserted deterministically from
     validated token ids/placeholders, not copied from unconstrained model prose.
   - If any implementation path still asks the model to draft prose, that prose is
     not the accepted artifact until deterministic validation confirms that every
     terminal technical string is either an approved token substitution or exact
     cited evidence. Do not treat a prompt-included allowed list alone as sufficient.
   - The existing final Phase 4 validators remain mandatory and independent:
     citations, unsupported/synthesized identifiers, malformed evidence-like tokens,
     placeholder/filler text, empty headings, generated coverage, and context-only
     evidence rules must still run and stay strict.
   - This slice should preserve current baseline/default behavior unless a test
     explicitly exercises the new claim/token planning mode.

5. **Artifacts and auditability**
   - Store claim plan prompts/responses/parsed JSON/validation diagnostics in the
     existing Phase 4 audit tree or a clearly named subdirectory.
   - Make failure modes readable in `PHASE4_RUN_REPORT.md` or related validation
     reports.
   - Do not hand-edit generated responses or historical run artifacts.

#### Failure and repair policy

This design must not reintroduce a generic healing loop.

- Deterministic failures in token extraction, plan validation, rendering, or final
  validators must be fixed upstream in code, schema, prompt contract, or tests.
- LLM-authored claim plans may use at most a narrow, audited, capped re-prompt if
  implemented. The prompt must include the exact machine-checkable validation
  error and must fail loudly after the cap. No retry-until-green.
- Bounded LLM re-prompting is allowed only for LLM-authored artifacts. It is not
  allowed to compensate for a bad deterministic token bank, bad renderer, weak
  validator, or missing Phase 3 evidence.
- Final draft repair must not silently patch identifiers, routes, paths, citations,
  claims, or generated coverage declarations.

#### Non-goals

- No live/billed Vertex/Gemini/API calls for this slice.
- No use of `ragflow-deepwiki.md` as citeable evidence.
- No weakening citation, identifier, route/path, placeholder, malformed-token, or
  generated-coverage validators.
- No changes to the protected Phase 3 evidence retrieval spec.
- No broad provider rewrite or provider-specific schema dependency in the first
  slice. Provider-native JSON/schema/enum constraints can be future work.
- No custom mini-language beyond a small JSON schema and simple token references.

#### Acceptance criteria

A non-live implementation is acceptable when:

- token-bank extraction is deterministic, audited, and covered by tests for exact
  imports, class/function/method names, routes/public routes, file paths, env vars,
  JSON keys/paths, and command/package-like tokens;
- tests prove composite synthesis is rejected unless the exact composite token is
  present: `quart_auth.AuthUser`, `Parser._pdf`, `HttpClient.request`,
  `/api/{api_version}`, `data.graph`, and route-family ellipses;
- a fake-provider or fixture-backed Phase 4 test demonstrates claim-plan creation,
  deterministic plan validation, deterministic token substitution/rendering from the
  accepted plan, and final existing writing validation;
- invalid claim plans fail before accepted markdown is rendered, with actionable
  diagnostics and no output mutation;
- baseline/default Phase 4 fixtures remain non-breaking unless the new mode is
  explicitly enabled;
- `git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`
  passes;
- focused Phase 4 tests and the existing generated-coverage tests pass.

Required verification commands:

```bash
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
uv run python -m pytest -q tests/test_phase4.py tests/test_phase4_generated_coverage.py
```

### Remaining Milestone 2 work — active pending backlog

1. **Phase 4 claim/token planning is implemented, temp-validated, and live-E2E
   validated.** The grounded temp run passed after one audited bounded claim-plan
   re-prompt, and the official live Vertex/Gemini grounded E2E passed under
   `/Users/ankitsingh/Documents/deep-wiki/15-e2e/20260628-001925-official-live-vertex-grounded-e2e`.
2. **No unapproved live retry.** The latest approved live run stopped in Phase 2 at
   `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-try-f9ad424`.
   Request explicit user approval before any further billed Vertex/Gemini call over
   the real RAGFlow repo. Default remains **no live retry**.
3. **Earlier live blockers remain diagnostic.** Repair attempt 1 still had five
   deterministic TER defects after improving the plan to `53/58` complete; repair
   attempt 2 failed with external `RemoteProtocolError: Server disconnected without
   sending a response`. Those were upstream Phase 2/3 diagnostics from an older live
   retry. The current green source bundle for grounded Phase 4 remains
   `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/live-ragflow-enhancement-runs/20260626-try-f9ad424-subagent-workaround`.

### Completed-slice acceptance — Phase 2 enhancement-mode planned-coverage upstream prevention

This implementation slice is accepted because it proves all of the following in
non-live tests:

- Phase 2 planning prompt/context explicitly includes and explains
  `planning-coverage-signals.md` as planner context, not citeable evidence.
- Enhancement mode has a deterministic planned-coverage gate that evaluates the normalized
  plan against all thirteen mandatory coverage families before Phase 3 retrieval. It does not claim evidence or generated-content readiness.
- A normalized plan missing mandatory families fails enhancement mode loudly with
  actionable diagnostics naming the missing families and remediation.
- Baseline mode remains non-breaking and report-only for compact or legacy plans.
- Deterministic code does **not** synthesize, silently add, or auto-heal missing
  pages, labels, or source obligations. Deterministic stages must prevent bad
  artifacts by stronger prompt contracts, schemas, normalization, validation, or
  explicit failure.
- If bounded LLM re-prompt/repair is added for the LLM-authored Phase 2 plan, it
  is narrow, audited, capped, fed exact coverage diagnostics, and followed by the
  same strict normalized-plan enhancement gate. It must not be retry-until-green.
- Planner outputs and normalized artifacts still preserve `coverage_labels[]`,
  `parent_section_id`, merged `required_topics[]`, and `expected_sources[]`.
- Tests prove: an expanded hierarchical plan with all families passes; a plan
  missing frontend/memory/queue fails enhancement mode; a broad parent page alone
  does not satisfy a deep child family; malformed citation validation from
  Milestone 1 remains intact.
- No live Vertex/Gemini/API calls, no real Phase 1/2/3/4 pipeline retry, no
  historical wiki artifact edits, no validator weakening, and no changes to
  `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.

### Completed-slice acceptance — Phase 3 evidenced coverage

This implementation slice is accepted because non-live tests prove:

- Phase 2 normalization preserves `topic_evidence_requirements[]` without making
  it mandatory in baseline mode.
- Planner prompt surfaces explain that enhancement-mode required topics need
  deterministic `topic_evidence_requirements[]` pointing at real normalized
  `retrieval_needs.*` source fields.
- Phase 3 reads the normalized hierarchical plan, including `coverage_labels[]`,
  `parent_section_id`, `required_topics[]`, and `topic_evidence_requirements[]`.
- Phase 3 writes deterministic `evidence/evidenced-coverage.json` and
  `evidence/evidenced-coverage-report.md`, and references them from the manifest
  or retrieval validation artifacts.
- Evidence packets or validation reports map citeable evidence IDs back to each
  planned `section_id` and required topic through exact source-field coverage, not
  fuzzy prose matching.
- Each required topic receives deterministic `sufficient`, `weak`, `missing`, or
  `not_applicable` status with counts, evidence IDs/handles, source categories,
  and remediation.
- In enhancement mode, `weak` or `missing` evidence for a required topic is a
  blocking **pipeline failure before Phase 4** using exit code `3` and
  `bad_underspecified_normalized_plan`. Baseline/legacy behavior remains
  non-breaking only where explicitly requested.
- Context artifacts, `derived/`, `plans/`, generated wiki files, and
  `ragflow-deepwiki.md` are never counted as citeable evidence.
- No generic retrieval healing loop, no product `--section` retry mode, no
  `--force` after readiness failure, no fallback rescue for no-signal sections,
  no synthetic evidence, no silent downgrade to optional, and no validator
  weakening.
- Tests include an expanded hierarchical fixture that passes evidenced coverage,
  a fixture where a required topic lacks mapped evidence and fails before Phase 4,
  a fixture where only broad recall exists and is `weak`/blocking, and a fixture
  proving baseline mode remains non-breaking.

### Completed-slice acceptance — Phase 4 hierarchical writing and generated coverage

The Phase 4 implementation slice is accepted as a non-live foundation because tests
prove:

- `write-wiki` supports opt-in `--coverage-mode enhancement`; baseline/default
  remains non-breaking.
- Enhancement-mode Phase 4 refuses to call any provider unless planned coverage
  and evidenced coverage artifacts are present, enforced, and passing.
- Phase 4 consumes hierarchical plans and page-level EvidencePackets without
  flattening child pages back into the compact 16-section baseline.
- WritingPackets and prompts include hierarchy fields plus evidenced topic rows.
- The wiki index, manifests, audit prompts/responses, generated-section metadata,
  generated-document metadata, and validation reports preserve parent/child
  structure.
- Phase 4 writes deterministic `wiki/metadata/generated-coverage.json` and
  `wiki/validation/generated-coverage-report.md`.
- Generated coverage metadata maps output pages back to planned `section_id`,
  `coverage_labels[]`, `required_topics[]`, and evidenced topic statuses.
- Generated coverage validation fails when a planned/evidenced required topic is
  omitted, only a placeholder/empty heading, declared without actual markdown
  coverage, malformed-cited, cited with IDs outside allowed/evidenced IDs, or
  supported by invalid/context/generated/reference artifacts.
- Generated coverage failures after provider output are writing-validation
  failures (`5`); missing/failed upstream enhancement gates are pre-provider gate
  failures (`3`).
- Existing writing validators remain strict; no generic healing loop, filler,
  synthetic evidence, validator weakening, live/billed calls, or use of
  `ragflow-deepwiki.md` as evidence.

### Completed-slice acceptance — non-live hierarchical E2E and benchmark-only review

This implementation/validation slice is accepted because non-live artifacts prove:

- planned, evidenced, and generated coverage enhancement gates all pass together
  in one fresh hierarchical run;
- wrapper scripts expose and pass `--coverage-mode enhancement` for Phase 2
  normalization, Phase 3 retrieval, and Phase 4 writing where applicable;
- an expanded multi-family hierarchical plan exercises parent/child pages and
  multiple mandatory topic families, not just the compact two-page fixture;
- Phase 4 uses fake-provider or deterministic responses only; no Vertex/Gemini/API
  live call is made;
- `wiki/metadata/generated-coverage.json`,
  `wiki/validation/generated-coverage-report.md`, nested `wiki/index.md`, and
  generated-section/document metadata are present and passing;
- the run report records exact commands, exit codes, gate statuses, coverage
  counts, evidence counts, determinism/rerun notes, and whether any wrapper/code
  changes were required;
- benchmark-only comparison against `ragflow-deepwiki.md` identifies remaining
  coverage/structure gaps without using it as evidence or chasing line count;
- focused tests and full suite pass using `uv run python -m pytest -q`;
- no protected Phase 3 spec changes, validator weakening, synthetic evidence,
  filler, silent downgrade, generic healing loop, or historical live artifact edit.

### Milestone 2 acceptance criteria

A later implementation must demonstrate:

- Milestone 1 malformed-token validation is complete and passing.
- A deterministic expanded plan includes all mandatory topic families.
- Coverage validation fails a compact 16-section-only plan when enhancement mode
  is requested.
- Expanded pages have matching EvidencePackets with per-topic sufficiency
  reporting.
- Fake-provider integration generates a hierarchical multi-page wiki with passing
  citation, malformed-token, unsupported-identifier, and coverage validation.
- Fixtures missing frontend/memory/queue topics fail coverage validation even if
  citation validation passes.
- A comparison report shows materially improved topic coverage over the
  `20260623-183730` run without treating line count as the sole metric.

## What not to do

- Do not create additional competing iteration specs for this work.
- Do not fix coverage by only increasing token limits.
- Do not chase line count with filler or repeated summaries.
- Do not copy the reference export.
- Do not make `ragflow-deepwiki.md` citeable evidence.
- Do not weaken validators.
- Do not silently edit the successful live wiki artifacts in place.
- Do not modify `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`.
- Do not run live/billed models until deterministic planning, evidence,
  validation, and fake-provider tests pass and the user explicitly approves a
  live retry.

## Recommended implementation sequence

Completed foundation:

1. Implement Milestone 1 malformed evidence-token validation and tests.
2. Update run reports/validation messaging so the old successful run is described
   as historical under the older validator, not strict final sign-off.
3. Add coverage taxonomy fixtures and validation for missing mandatory topic
   families.
4. Preserve Phase 2 coverage labels, PagePlan obligations, and parent/child
   hierarchy in normalized planning artifacts.
5. Expand Phase 1 deterministic coverage signals and include them in planner
   context as non-citeable condensates.
6. Implement the Phase 2 planned-coverage gate that consumes the coverage signals
   and fails loudly when mandatory planned families are absent, without adding a
   generic healing loop.

Completed foundation (continued):

7. Implemented the Phase 3 Evidence Sufficiency Contract above: preserve/consume
   explicit topic evidence requirements, map them to exact covered evidence IDs,
   write evidenced-coverage artifacts, and fail enhancement mode before Phase 4 on
   weak/missing required-topic evidence (`retrieve-evidence --coverage-mode
   enhancement`).

Completed foundation (continued):

8. Implemented the Phase 4 Generated Coverage Contract above: opt-in
   `write-wiki --coverage-mode enhancement` with pre-provider planned/evidenced
   upstream gates, hierarchy-preserving prompts/index/metadata, WritingPackets
   carrying the Phase 3 mapped evidence IDs, and deterministic
   `generated_required_topics_covered` validation (omitted/placeholder/out-of-scope/
   uncited topic → exit 5; missing/failed upstream gate → exit 3).

Completed foundation (continued):

9. Ran the non-live hierarchical end-to-end validation over an expanded 13-family
   plan via the real CLI (with the shell wrappers fixed to pass `--coverage-mode`),
   plus the benchmark-only comparison. All three enhancement gates pass together;
   determinism + strictness (negative probe) verified.

Pending active sequence:

10. Implement the Phase 4 claim/token planning and grounded-rendering slice above.
    This is a non-live upstream-prevention change inside `write-wiki`: derive exact
    token banks from existing WritingPackets/EvidencePackets, ask the LLM for a
    structured claim/token plan with token placeholders/references, validate it before
    accepted markdown is rendered, and keep final writing/generated-coverage validators
    strict. Do not perform live/billed
    calls, do not edit historical generated outputs, and do not modify the protected
    Phase 3 spec.
11. After the Phase 4 claim/token planning foundation is implemented and tested,
    revisit the Phase 2/3 evidence-alignment live diagnostics if needed. Any further
    live retry already requires explicit user approval; the latest live retry
    consumed approval and stopped before Phase 4.

## Coding-agent prompt summary

Milestone 1, the Milestone 2 foundation slices, the Phase 3 evidenced-coverage gate,
the Phase 4 enhancement-mode hierarchical writing + generated-coverage gate, the
non-live hierarchical E2E, the Phase 2 topic-obligation gate, TER source-field
canonicalization, enhancement-mode plan repair, initial parse-ambiguity repair
handling, and the current one-shot Phase 4 prompt hardening are implemented and
tested non-live. Future coding-agent work should keep validator behavior strict and
proceed with the next concrete non-live slice: **Phase 4 claim/token planning and
grounded rendering**.

Implement this inside `write-wiki` without changing the top-level Phase 1-4
pipeline: derive a deterministic token bank from each WritingPacket/EvidencePacket,
ask the LLM for a structured claim/token plan with token placeholders/references,
validate that plan before accepted markdown is rendered, and render final markdown
with deterministic token substitution from the validated token bank. The goal is to
make invented terminal technical tokens unrepresentable in the normal path, not to
keep adding one-shot negative examples forever.

Keep all citation/identifier/malformed-token/no-context/no-placeholder/no-truncation
validators strict, keep the Phase 3 evidenced-coverage gate intact (weak/missing
required evidence remains a pipeline failure before Phase 4 in enhancement mode), and
keep the Phase 4 generated-coverage gate intact (an omitted/placeholder/out-of-scope/
uncited evidenced sufficient required topic is a post-provider writing-validation
failure; a missing/failed upstream gate is a pre-provider gate failure). Do not use
fuzzy prose matching, synthetic evidence, silent downgrades, output patching, or
retry-until-green loops. Bounded LLM re-prompting is allowed only for LLM-authored
claim plans, with exact diagnostics, audit artifacts, a hard cap, and strict final
validation. Do not call Vertex/Gemini or any live/billed model for this next slice.
Do not edit historical generated wiki artifacts in place. Do not modify
`docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`. If this slice is too large
for one coding session, stop after a coherent non-live increment and report the
remaining work clearly.
