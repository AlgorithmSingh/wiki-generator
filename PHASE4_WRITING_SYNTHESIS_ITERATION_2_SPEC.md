# Phase 4 Writing / Synthesis Iteration 2 Spec

## Status and source of truth

Status: **SPEC ONLY / amendment / no implementation yet**.

This document amends `PHASE4_WRITING_SYNTHESIS_SPEC.md` after live Phase 4
failures. It is **not** a replacement for the Phase 4 baseline spec. The
baseline Phase 4 writing/synthesis spec remains the source of truth except where
this amendment explicitly tightens prompt wording and defines a narrow validation
classification for shell-variable path-synthesis near-misses.

Source-of-truth boundaries:

- `PHASE4_WRITING_SYNTHESIS_SPEC.md` remains the baseline Phase 4 spec.
- `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` is unchanged and must not be modified for
  this issue.
- Phase 3 remains deterministic, all-sections only, LLM-free, with no retry loop
  and no `--section` product mode.
- This spec does not implement code, run Phase 3/4, run live models, weaken
  validators, or authorize another billed live retry.

Current code baseline when this failure was observed:

- HEAD: `7026cee2b2313998e26c51b72da6275e3708fa37`
  (`Support documented public API route evidence`).

## Problem statement

Latest live Phase 4 run:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934
```

Key artifacts from that run:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/LIVE_VERTEX_PHASE4_RESULT.md
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/wiki/PHASE4_RUN_REPORT.md
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/wiki/audit/responses/deployment.raw.txt
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/wiki/audit/responses/deployment.parsed.json
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/bundle/evidence/packets/deployment.json
```

The run refreshed deterministic Phase 3 successfully and verified that the prior
blockers were resolved:

- `rag/llm/embedding_model.py` citeable evidence is present in
  `evidence/packets/subsystem-rag-core.json`.
- Public API route evidence is present: `ev:api-datasets-and-documents:0011`
  has `source.public_route == "/api/v1/datasets/{dataset_id}/documents/{document_id}/chunks"`.

Phase 4 still failed closed:

- Exit code: `5`.
- Failure category: `writing_validation_failure`.
- Failure section: `deployment`.
- Unsupported identifier:

```text
/ragflow/conf/service_conf.yaml
```

The run report error was:

```text
section 'deployment' failed writing validation after 0 rewrite(s):
["invented_identifier: identifier(s) not supported by any cited/available evidence: ['/ragflow/conf/service_conf.yaml']"]
```

## Evidence snippet and exact supported identifiers

The relevant citeable evidence item is `ev:deployment:0005` from
`docker/entrypoint.sh`:

```sh
# -----------------------------------------------------------------------------
# Replace env variables in the service_conf.yaml file
# -----------------------------------------------------------------------------
CONF_DIR="/ragflow/conf"
TEMPLATE_FILE="${CONF_DIR}/service_conf.yaml.template"
CONF_FILE="${CONF_DIR}/service_conf.yaml"

rm -f "${CONF_FILE}"
# ...
done < "${TEMPLATE_FILE}"
```

Exact supported tokens in this evidence include:

- `CONF_DIR`
- `/ragflow/conf`
- `TEMPLATE_FILE`
- `${CONF_DIR}/service_conf.yaml.template`
- `CONF_FILE`
- `${CONF_DIR}/service_conf.yaml`
- `${CONF_FILE}`
- `${TEMPLATE_FILE}`
- `docker/entrypoint.sh` from source metadata

The generated literal `/ragflow/conf/service_conf.yaml` is different. It is not a
single exact token in the excerpt or source metadata. It is a synthesized string
created by substituting `CONF_DIR="/ragflow/conf"` into
`CONF_FILE="${CONF_DIR}/service_conf.yaml"`.

Therefore safer grounded phrasing is one of the exact evidence tokens, for
example:

- `CONF_FILE`
- `${CONF_DIR}/service_conf.yaml`
- `${CONF_FILE}`

The full expanded literal `/ragflow/conf/service_conf.yaml` must not pass unless
one cited evidence item explicitly contains that exact literal, or trusted audited
metadata explicitly exposes that exact expanded literal as citeable support.
This live packet does neither.

## Root cause

This was not a validator false positive. The model performed shell-variable/path
expansion from multiple evidence tokens and wrote the expanded path as if it were
an exact evidenced identifier. The Phase 4 validator correctly failed closed
because the expanded identifier was absent from the cited/available evidence.

The failure is mainly a Phase 4 model-compliance and rewrite-policy issue:
Phase 4 must instruct the model not to synthesize paths from shell variables, and
it may optionally distinguish deterministic shell-expanded near-misses from true
inventions for bounded rewrite feedback. It must not accept the synthesized path
as grounded.

## Non-goals

This amendment explicitly does **not** authorize:

- weakening unsupported-identifier validation;
- blanket support for derived paths;
- making normalized plans, context artifacts, derived artifacts, planner
  diagnostics, or run-result notes citeable as source evidence;
- broadly exposing shell-expanded paths as evidence;
- live retries before a non-live patch and tests;
- Phase 3 LLM use, retry/debug loops, or section mode;
- changing `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`;
- treating public-route synthesis, directory+filename synthesis, or arbitrary
  path joining as grounded evidence.

## Required behavior

### Prompt behavior

Phase 4 prompts must explicitly forbid shell-variable expansion and path
interpolation unless the exact expanded string appears in one cited evidence item
or in trusted audited citeable metadata.

The writer must copy identifiers exactly from cited evidence. For shell snippets,
that means output should use exact tokens such as:

- `CONF_FILE`
- `${CONF_DIR}/service_conf.yaml`
- `${CONF_FILE}`

The writer must not output `/ragflow/conf/service_conf.yaml` for the deployment
case unless that exact literal is added to citeable evidence or audited citeable
metadata by a later trusted deterministic process.

### Validation behavior

The validator must continue to reject unsupported identifiers. The generated
expanded path is not supported merely because it can be derived by variable
substitution.

Allowed final states:

- **Pass:** every identifier is present exactly in cited evidence or trusted
  audited citeable metadata.
- **Rewriteable near-miss:** an unsupported identifier is classified as
  `synthesized_identifier` under the narrow policy below, rewrite feedback lists
  exact evidenced alternatives, and a bounded rewrite succeeds.
- **Fail terminally:** true invented identifiers and non-narrow derivations remain
  terminal `invented_identifier` failures.

## Policy decision: `invented_identifier` vs `synthesized_identifier`

True invented identifiers stay terminal. Examples include paths, routes, modules,
classes, env vars, or API names that are absent from evidence and cannot be
mapped to a conservative deterministic shell-variable expansion with safe exact
alternatives.

This amendment permits an optional narrow classification:

```text
synthesized_identifier
```

Use it only for deterministic derived-from-evidence near-misses where:

1. the unsupported generated identifier equals a conservative shell-variable
   expansion derived from cited/available evidence;
2. the exact expanded identifier itself is not present as evidence;
3. safe exact alternatives are present in evidence and can be suggested; and
4. rewriting to those exact alternatives would preserve the claim without adding
   new facts.

A `synthesized_identifier` is **rewriteable, not passable**. It never makes the
identifier grounded. The final validator must still pass after rewrite, using
only exact evidence tokens or explicit audited citeable metadata.

## Guardrails for rewriteable synthesized identifiers

If implemented, `synthesized_identifier` rewrite handling must obey all baseline
Phase 4 rewrite guardrails plus the stricter rules below:

- No new evidence may be retrieved, generated, or added.
- Use at most the existing maximum rewrite attempts and never exceed the hard cap
  already defined by Phase 4.
- Rewrite feedback must list exact alternatives found in evidence, such as
  `CONF_FILE`, `${CONF_FILE}`, or `${CONF_DIR}/service_conf.yaml`.
- The rewrite prompt must tell the model to replace or omit the unsupported
  identifier, not to justify it.
- Ambiguous, multi-step, untrusted, cross-file, or semantic derivations remain
  terminal `invented_identifier` failures.
- Routes and file paths not matching this narrow shell-variable pattern remain
  terminal. In particular, public-route synthesis and directory+filename
  synthesis are not covered by this rewriteable subtype.
- A repeated synthesized identifier after rewrite remains a validation failure;
  do not silently downgrade or pass it.

## Recommended algorithm for shell-expanded near-miss detection

This algorithm is recommended for implementation in the Phase 4 validator. It is
for classification and rewrite feedback only; it must not add grounded support.

1. Build the normal exact-support index from evidence excerpts and citeable
   source metadata as the baseline validator already does.
2. If a generated identifier is exactly supported, validate normally.
3. For an unsupported path-like identifier, inspect only cited/available evidence
   in the current `WritingPacket`.
4. Conservatively parse inline shell assignments from evidence excerpts, such as:

```sh
VAR="literal"
VAR='literal'
VAR=literal
VAR="${OTHER}/suffix"
VAR='${OTHER}/suffix'
VAR=${OTHER}/suffix
VAR="$OTHER/suffix"
```

5. Ignore assignments with command substitution, arithmetic, globbing,
   concatenation from multiple unrelated variables, conditionals, subshells,
   runtime mutation, untrusted quoting, or values spanning multiple evidence
   items.
6. Record exact evidence tokens from the assignment lines, including the variable
   name, the raw right-hand side, and `${VAR}` references that appear verbatim.
7. Build deterministic one-step expansions only when a variable has a literal
   value in the same conservative assignment map. For the live failure:

```text
CONF_DIR -> /ragflow/conf
CONF_FILE raw RHS -> ${CONF_DIR}/service_conf.yaml
one-step expansion -> /ragflow/conf/service_conf.yaml
```

8. If the generated unsupported identifier equals a deterministic expansion but
   the exact expanded identifier is not itself in evidence, classify it as
   `synthesized_identifier`, not as supported.
9. Suggest exact alternatives from evidence, preferring the assignment variable
   and raw evidence tokens. For the live failure, suggestions should include:

```text
CONF_FILE
${CONF_FILE}
${CONF_DIR}/service_conf.yaml
```

10. If no safe exact alternative exists, or if more than one semantic target is
    possible, classify as terminal `invented_identifier`.
11. Do not accept the synthesized identifier as grounded at any stage. Only a
    rewritten draft that removes/replaces it with exact supported tokens can pass.

## Prompt hardening wording examples

Add wording like this to the initial section-writing prompt:

```text
Copy repo-specific identifiers exactly from cited evidence. Do not compute,
normalize, join, expand, or interpolate paths, routes, shell variables, env vars,
or placeholders.

For shell snippets, do not expand variables. If evidence says
CONF_FILE="${CONF_DIR}/service_conf.yaml", you may write `CONF_FILE`,
`${CONF_FILE}`, or `${CONF_DIR}/service_conf.yaml` only because those exact tokens
appear in evidence. Do not write `/ragflow/conf/service_conf.yaml` unless that
exact expanded string appears in the cited evidence item.

If a desired path, route, filename, module, symbol, env var, or command does not
appear exactly in cited evidence, omit that identifier or phrase the claim using
only exact cited tokens.
```

Add wording like this to rewrite feedback for this subtype:

```text
Validation found a synthesized identifier, not a grounded identifier:
`/ragflow/conf/service_conf.yaml`.

This appears to be a shell-variable expansion derived from evidence, but the
expanded literal does not appear exactly in cited evidence. Rewrite the claim to
use one of these exact evidence tokens instead: `CONF_FILE`, `${CONF_FILE}`, or
`${CONF_DIR}/service_conf.yaml`. Do not add evidence, do not introduce new paths,
and omit the claim if it cannot be stated with exact supported tokens.
```

## Testing plan

No live models and no Phase 3/4 reruns are required for these tests.

Validator/unit tests:

- `CONF_FILE` passes when available in cited evidence.
- `${CONF_DIR}/service_conf.yaml` passes when available in cited evidence.
- `/ragflow/conf/service_conf.yaml` from the `ev:deployment:0005` snippet becomes
  rewriteable `synthesized_identifier`, not pass.
- `/ragflow/conf/other.yaml` remains terminal `invented_identifier`.
- `app/ghost.py` remains terminal `invented_identifier`.
- Public-route synthesis remains terminal `invented_identifier` unless the exact
  public route is present in citeable evidence or audited citeable metadata.
- Directory+filename synthesis remains terminal `invented_identifier`.
- Ambiguous or multi-step shell derivations remain terminal `invented_identifier`.

Integration/fake-provider tests:

- First fake provider response for `deployment` uses
  `/ragflow/conf/service_conf.yaml`; validation classifies it as
  `synthesized_identifier` and triggers one bounded rewrite.
- Rewrite fake provider response uses `CONF_FILE` or
  `${CONF_DIR}/service_conf.yaml`; the run passes.
- Rewrite audit artifacts exist under `wiki/audit/rewrites/` and include the
  unsupported identifier plus exact suggested alternatives.
- No new evidence is added between the first response and rewrite.

Regression fixture:

- If practical, add a non-live fixture from the latest deployment response and
  packet:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/wiki/audit/responses/deployment.parsed.json
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-172934/bundle/evidence/packets/deployment.json
```

The fixture must be checked in only if it is reasonably small and scrubbed of any
irrelevant live-run noise. Otherwise encode the minimal snippet directly in unit
tests.

## Implementation plan

Likely files for a future non-live patch:

- `src/wiki_generator/libs/writing/prompt.py` — add prompt hardening and rewrite
  feedback wording.
- `src/wiki_generator/libs/writing/citations.py` — reuse or expose exact evidence
  token extraction if this is where support tokens are indexed.
- `src/wiki_generator/libs/writing/validate.py` — add narrow
  `synthesized_identifier` classification, conservative shell-assignment parsing,
  and rewrite feedback with exact alternatives while keeping final validation
  strict.
- `tests/test_phase4.py` — add validator and fake-provider rewrite regression
  tests.
- `RUNBOOK.md` and/or `HANDOFF_READINESS_ITERATION_2.md` — minimal status notes
  only, if needed.

Do not modify `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` for this work.

## Acceptance criteria before another billed live retry

Before any further live/billed Phase 4 retry:

- The non-live patch implementing this amendment exists.
- Relevant tests pass.
- `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` remains unchanged.
- Deterministic no-live validation or fake-provider rewrite proves the deployment
  case is handled: the expanded path is rejected as `synthesized_identifier`, the
  rewrite uses exact evidence tokens, and final validation passes.
- True invented identifiers remain terminal.
- Another live Phase 4 retry has explicit user approval.
