# Variables to set

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
export REPO=/Users/ankitsingh/Documents/deep-wiki/ragflow
export OUT=/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/$(date +%Y%m%d-%H%M%S)
```

# Runbook — generate a DeepWiki plan for any repo

End-to-end commands for the implemented Phase 1-4 pipeline. Phase 1 and Phase 3
are deterministic and LLM-free. Phase 2 Step 1 (`plan`), optional Step 1b
(`plan-repair`), and Phase 4 (`write-wiki`) are the LLM-backed steps. Phase 4
writing/synthesis is **implemented** per `docs/specs/done/PHASE4_WRITING_SYNTHESIS_SPEC.md`
(§6 below).

> **Current readiness status (2026-06-24):** Phase 1-4 can produce a grounded baseline wiki with the Iteration 3 exact-coverage/public-route fixes and the Phase 4 shell-variable path-synthesis fix. The successful live run is `/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/phase4-live-vertex-runs/20260623-183730`, but strict sign-off is not complete: follow-up review found a malformed evidence-like token (`[ev:data-models:010]`) in the historical artifact and a broader coverage-target gap versus the DeepWiki benchmark. The active enhancement spec is `docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md`: Milestone 1 plus the Milestone 2 coverage taxonomy/validation, Phase 2 planning-obligation preservation, Phase 1 deterministic coverage-signal, Phase 2 planned-coverage gate, and the Phase 3 evidenced-coverage gate slices are implemented and tested. Phase 3 enhancement mode (`retrieve-evidence --coverage-mode enhancement`) now maps required topics through explicit `topic_evidence_requirements[]` to exact source-field evidence IDs and fails the pipeline (exit 3, `bad_underspecified_normalized_plan`) on weak/missing required evidence before Phase 4. Phase 4 hierarchical writing/generated coverage and non-live hierarchical E2E remain pending. Do not run another live/billed retry until the non-live enhancement work passes and the user explicitly approves it.

```
Phase 1  Step 1 decompose   -> raw artifact bundle
         Step 2 condense     -> derived/planning-*.md condensates
                                (incl. planning-handles.md — the exact-handle catalog)
         Step 3 digest       -> derived/planning-digest.md (also runs Step 4)
         Step 4 bundle       -> planner-digest/planner-upload-bundle.md (one upload)
         Step 5 build-retrieval -> rag/retrieval-capabilities.json (+ BM25 / optional vectors)
Phase 2  Step 1 plan         -> Gemini/Kimi plan -> plans/phase2-<provider>-response.md
         Step 1b plan-repair  -> optional bounded/audited Gemini repair on
                                  readiness FAIL only
         Step 2 normalize-plan -> plans/document-plan.json + section-plans.jsonl
                                  + plans/phase3-readiness-report.md (PASS/FAIL gate)
Phase 3  retrieve-evidence   -> evidence/packets/<section_id>.json (+ manifest,
                                validation, report) — deterministic, no LLM
                                (refuses to run if readiness report is not PASS)
Phase 4  write-wiki          -> wiki/index.md + sections/ + metadata/citation-
                                manifest.json + audit/ + validation/ +
                                PHASE4_RUN_REPORT.md (LLM-backed; gates + fails
                                closed; gemini-gem | gemini-api | vertex)
```

Step 5 (`build-retrieval`) is independent of the planner upload — it only needs
Step 1's corpus, so run it any time after `decompose`, but before Phase 3.

## 0. Setup (once)

Requires Python 3.11+. This is a `src/`-layout package, so **install it first**
(editable). `git` and `ripgrep` (`rg`) on PATH are recommended; everything else
degrades gracefully.

```bash
cd /path/to/wiki-generator           # the repo root
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                     # required (src layout)
python -m unittest discover -s tests # optional sanity check (expect: OK)
```

After install you can use either `wiki-generator <cmd>` (console script) or
`python -m wiki_generator <cmd>`. The commands below use the latter; both work.

### Python 3.12 + vectors-required scripts

For the current preferred workflow, use the per-step scripts in `scripts/`. They
create/use a Python 3.12 venv. Step 5 installs `.[embeddings]`, verifies
`faiss` / `numpy` / `model2vec`, and runs with `--vectors on`, so vectors are
**not optional**.

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

scripts/00_setup_python312_vectors.sh --recreate-venv

scripts/phase1_step1_decompose.sh --repo "$REPO" --out "$OUT"
scripts/phase1_step2_condense.sh --out "$OUT"
scripts/phase1_step3_digest.sh --out "$OUT"
scripts/phase1_step4_bundle.sh --out "$OUT"
scripts/phase1_step5_build_retrieval.sh --out "$OUT" --rebuild \
  --smoke-query "authentication and login flow"

# Phase 2 Step 1 is optional/LLM-backed. Use either the browser Gem, or:
scripts/phase2_step1_plan.sh --out "$OUT" --project my-gcp-project --location us-central1

# After a raw planner response exists:
scripts/phase2_step2_normalize_plan.sh --out "$OUT" \
  --raw-response "$OUT/plans/phase2-gemini-response.md"

scripts/phase3_retrieve_evidence.sh --out "$OUT" --with-vectors
```

## 1. Pick the repo and an output directory

```bash
REPO=/absolute/path/to/the/repo/to/document
OUT=/absolute/path/to/output/bundle        # created if missing
```

## 2. Phase 1 — decompose, condense, digest, bundle

```bash
# Step 1 — raw artifact bundle (inventory, symbols, RAG/BM25, static graph,
#          queries, contracts, tests, derived summaries). No LLM.
#          Vectors are built in Step 5, so keep decomposition embeddings off.
python3 -m wiki_generator decompose --repo "$REPO" --out "$OUT" --embeddings off

# Step 2 — planner-facing condensates into <OUT>/derived/ (includes
#          planning-handles.md, the exact-handle catalog the planner copies from)
python3 -m wiki_generator condense --in "$OUT" --budget-tokens 250000

# Step 3 — derived/planning-digest.md only. Step 4 stays separate.
python3 -m wiki_generator digest --in "$OUT" --budget-tokens 250000 --no-bundle

# Step 4 — the single upload file
python3 -m wiki_generator bundle --in "$OUT" --budget-tokens 250000
```

Result to upload: **`$OUT/planner-digest/planner-upload-bundle.md`**
(per-file token table: `$OUT/planner-digest/upload-list.md`).

## 2.5 Phase 1 Step 5 — build the retrieval substrate (deterministic, no LLM)

Verifies or rebuilds the BM25 index over the corpus, optionally builds local
vectors, and writes the Phase 3 capability contract + readiness report. Not
needed for the planner upload, so it can run independently of Step 4 — its only
dependency is Step 1's `rag/chunks.jsonl` + `rag/spans.jsonl`.

```bash
# Hybrid/vector mode is required in this workflow.
pip install -e '.[embeddings]'
python3 - <<'PY'
import faiss, numpy, model2vec
print('vector deps ok')
PY

python3 -m wiki_generator build-retrieval --in "$OUT" --vectors on --rebuild \
  --smoke-query "authentication and login flow"
```

Outputs in `$OUT/rag/`:

```
retrieval-capabilities.json   machine-readable contract for Phase 3 (modes + counts + fingerprint)
retrieval-substrate-report.md PASS/FAIL + recommended mode (hybrid | lexical-symbolic)
vector-build-report.md        vector status, model, count, or skip/fail reason
vectors.faiss + vector-metadata.json[l]   only when vectors are built
retrieval-smoke-tests.jsonl   only with --smoke-query
```

Exit codes: `0` PASS, `1` FAIL (e.g. `--vectors on` with no backend, or a BM25
row-count mismatch), `2` missing/unreadable corpus. Review the report's
recommended mode before starting Phase 3.

If FAISS won't install, verify the environment first (Python/arch/wheel) — see
the preflight in `docs/specs/done/PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md`.

Quick handoff verification on an existing clean bundle, with vectors required:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

scripts/phase1_step5_build_retrieval.sh \
  --out "$OUT" \
  --rebuild \
  --run-tests-first \
  --smoke-query "authentication and login flow"

cat "$OUT/rag/retrieval-substrate-report.md"
cat "$OUT/rag/retrieval-capabilities.json"
```

## 3. Phase 2 Step 1 — run the planning LLM

Two ways; pick one.

### Option A — automated: Vertex AI Gemini 2.5 Pro (`plan` command)

One-time setup: the optional SDK + GCP credentials.

```bash
pip install -e '.[vertex]'                  # google-genai SDK
gcloud auth application-default login        # Application Default Credentials
export GOOGLE_CLOUD_PROJECT=my-gcp-project
export GOOGLE_CLOUD_LOCATION=us-central1
```

```bash
python3 -m wiki_generator plan --bundle "$OUT"
# or: --project my-gcp-project --location us-central1
```

This sends the planner instructions + kickoff + the upload bundle to
`gemini-2.5-pro` and writes `$OUT/plans/phase2-gemini-response.md`. It does NOT
auto-run normalize-plan.

### Option B — manual: a Gemini Gem in the browser

1. Create/open the Gemini Gem with `gemini-gem/GEM_INSTRUCTIONS.md` as its
   Instructions (one-time).
2. Start a chat: paste `gemini-gem/KICKOFF_PROMPT.md` and **attach the one file**
   `$OUT/planner-digest/planner-upload-bundle.md` (see `gemini-gem/UPLOAD_LIST.md`).
3. Save the Gem's **entire reply verbatim** (do not hand-split it) to:

```bash
mkdir -p "$OUT/plans"
# paste the response into:
#   $OUT/plans/phase2-gemini-response.md
```

## 4. Phase 2 Step 2 — normalize the plan (deterministic, no LLM)

```bash
python3 -m wiki_generator normalize-plan \
  --bundle       "$OUT" \
  --raw-response "$OUT/plans/phase2-gemini-response.md"
# add --strict to exit non-zero on any unresolved reference
# add --provider kimi (and name the file phase2-kimi-response.md) for a different planner
```

Produces in `$OUT/plans/`:

```
document-plan.json          normalized DocumentPlan (schema phase2-plan-v1)
document-plan.md            human-readable plan
section-plans.jsonl         one normalized SectionPlan per line
normalization-report.md     resolution counts + notes for Phase 3
phase3-readiness-report.md  Phase 3 readiness gate: Status PASS|FAIL + per-section failures
unresolved-references.jsonl every reference that did not resolve (+candidates)
raw-extracted-*.{json,jsonl} raw blocks pulled from the response (debug)
```

`normalize-plan` is the deterministic owner of Phase 3 readiness. It keeps **only
resolvable handles** in the exact lanes — unresolved symbols/files, non-exact
contracts (`contracts/openapi.json` alone), graph display labels (`pytest
[Dependency]`), and digest docs (`derived/planning-*.md`) are removed and routed
to `retrieval_needs.search_hints[]` (recall text) or
`retrieval_needs.context_artifacts[]` (non-citeable context). `expected_evidence_types`
is derived only from the resolvable work that remains.

Check **`phase3-readiness-report.md`** before Phase 3. `Status: PASS` means every
section is a clean retrieval work order. `Status: FAIL` lists the per-section
fields, invalid inputs, and the suggested upstream fix — fix the planner
instructions / plan / normalization rules and re-run, rather than proceeding to
Phase 3 (the Phase 3 script refuses a non-PASS plan unless `--force`). Also review
`normalization-report.md` (resolution counts) and `unresolved-references.jsonl`.

Before Phase 3, run **Step 5 (`build-retrieval`, section 2.5)** so the bundle has
an explicit retrieval readiness contract (`rag/retrieval-capabilities.json`). In
the preferred script workflow, Step 5 requires FAISS/model2vec and fails if
vectors cannot be built; a passing run should report `hybrid` mode.

## 4b. Phase 2 Step 1b — bounded planner-artifact repair (only if readiness FAILs)

`normalize-plan` stays deterministic and LLM-free. When it reports `Status: FAIL`
for a planner-quality reason — a malformed required `SectionPlan` JSONL row, an
unresolved exact-lane handle (a wrong file path / symbol), or a diagnostic-only
section — and Vertex/Gemini is available, run the **bounded repair** (Readiness
Iteration 2). It re-prompts the planner for *corrected planning artifacts only*,
re-validates with the same strict gate, and writes the canonical plan artifacts
only when readiness passes:

```bash
scripts/phase2_step1b_repair_plan.sh --out "$OUT" \
  --raw-response "$OUT/plans/phase2-gemini-response.md"
# needs the [vertex] extra + GCP ADC (GOOGLE_CLOUD_PROJECT) or a GEMINI_API_KEY
```

It is bounded (≤2 attempts), keeps `section_id`s 1:1 with the original plan (a
diagnostic-only section may be removed or converted to `role: provenance`), and
audits every attempt under `$OUT/plans/repair/` (request, raw bad artifacts, exact
errors, response, validation). It **fails loudly** if Gemini is unavailable or the
plan cannot be made Phase-3-ready — it never silently continues. Patch 1
directory-anchor warnings and the Patch 2 bare-string deterministic repair are
handled inside `normalize-plan` itself and do **not** require this step. Phase 3
never invokes repair.

## 5. Phase 3 — retrieve evidence (deterministic, no LLM)

```bash
python3 -m wiki_generator retrieve-evidence --bundle "$OUT"
# or:  scripts/phase3_retrieve_evidence.sh --out "$OUT"   (--with-vectors for hybrid)
```

**Readiness gate:** `scripts/phase3_retrieve_evidence.sh` reads
`plans/phase3-readiness-report.md` first and fails early (before any install) if
its status is not `PASS`. Pass `--force` only to run Phase 3 against a non-ready
plan on purpose (failure testing). The bare `python -m wiki_generator
retrieve-evidence` command does not gate; it just classifies the result.

Reads the normalized plan (`plans/`) + the Step 5 substrate (`rag/`) and writes
one EvidencePacket per planned section. `search_hints[]` feed BM25/vector recall;
`context_artifacts[]` are preserved in each packet's `work_order` for traceability
but are **never** cited as evidence. All-sections producer — there is no
per-section mode. Produces in `$OUT/evidence/`:

```
packets/<section_id>.json    one EvidencePacket per section (schema phase3-evidence-packet-v1)
evidence-packets.jsonl       all packets, one per line, in document order
evidence-manifest.json       machine-readable index of the artifact set
retrieval-validation.json    deterministic contract checks + section results
retrieval-report.md          human-readable PASS/FAIL + evidence-by-lane + fix path
unresolved-evidence.jsonl    deterministic retrieval misses (not evidence)
```

Exit codes: `0` PASS · `2` bad/missing input artifact · `3` bad/underspecified
normalized plan · `1` retriever bug. A failure is not a retry loop: fix the named
upstream artifact / plan / code per `retrieval-report.md`, then rerun the same
all-sections command. The vector lane runs only when capabilities report `hybrid`;
in `lexical-symbolic` mode it is skipped (not a failure).

## 6. Phase 4 — writing/synthesis (`write-wiki`)

Phase 4 is **implemented** (`docs/specs/done/PHASE4_WRITING_SYNTHESIS_SPEC.md`). It consumes a
clean accepted Phase 1-3 bundle such as:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038
```

It gates on Phase 1-3 success before any model call — readiness `PASS`/Failures 0,
retrieval validation `pass` with all required contract checks, no forced/stale
provenance (packet `section_plan_sha256` must match the live section plans), no
evidence sourced from `plans/`/`derived/`/context artifacts, and one valid packet
per planned section — then writes `wiki/index.md`, per-section Markdown, a
citation manifest, a raw prompt/response audit, a writing-validation report, and
`PHASE4_RUN_REPORT.md`. It cites only Phase 3 EvidencePacket `evidence_id`s, and
fails closed on missing, stale, forced, or unsupported evidence. It never reruns
Phase 3, repairs the plan, or invents fallback evidence.

Three provider modes (all default to temperature `0.1` and `max_output_tokens`
`32768`; `8192` is warned against for `gemini-2.5-pro` because it can truncate):

```bash
export BUNDLE=/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038

# (A) Vertex AI Gemini 2.5 Pro
pip install -e '.[vertex]'
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=my-gcp-project GOOGLE_CLOUD_LOCATION=us-central1
scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider vertex
#   or: wiki-generator write-wiki --bundle "$BUNDLE" --provider vertex \
#         --project my-gcp-project --location us-central1

# (B) Direct Gemini API key (NOT Vertex)
export GEMINI_API_KEY=...
scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider gemini-api

# (C) Gemini Gem handoff (no API call): prepare prompts, paste into the Gem,
#     save verbatim responses, then validate + assemble.
scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider gemini-gem --prepare-prompts-only
#   ... paste wiki/audit/prompts/<section>.md into the Gem, save responses to
#       wiki/audit/responses/<section>.raw.txt ...
scripts/phase4_write_wiki.sh --out "$BUNDLE" --provider gemini-gem \
    --responses-in "$BUNDLE/wiki/audit/responses"
```

Exit codes: `0` PASS/prepared · `2` bad/missing input · `3` upstream gate failure
(fix readiness/Phase 2/Phase 3) · `4` provider failure · `5` writing-validation
failure · `1` internal bug. A bounded format/citation rewrite (`--max-rewrite-attempts`,
hard cap 2, every attempt audited under `wiki/audit/rewrites/`) may fix malformed
JSON or citation-syntax issues for the live-model providers; it never adds
evidence and never runs for terminal failures (cited context artifact, invented
identifier, placeholder, truncation). If the bundle carries no command manifest,
pass `--accept-no-force` to assert Phase 3 was not force-run.

The earlier live Vertex Phase 4 attempt failed closed on an unsupported
shell-expanded identifier, `/ragflow/conf/service_conf.yaml`, in the `deployment`
section. The Iteration 2 fix (`docs/specs/done/PHASE4_WRITING_SYNTHESIS_ITERATION_2_SPEC.md`) is
implemented: the prompt explicitly forbids expanding shell/env variables, and the
validator classifies a deterministic one-step shell-variable expansion absent
from evidence as a rewriteable `synthesized_identifier`, distinct from a terminal
`invented_identifier`. The successful live run at `20260623-183730` exercised
that path and passed the then-current validation. Follow-up review found a
separate malformed citation-token validator gap and broader coverage gap; the
malformed-token validator enhancement is now implemented locally under
`docs/specs/not-done/PHASE_DEEPWIKI_COVERAGE_ENHANCEMENT_ITERATION_SPEC.md` Milestone 1. Treat any
future live Phase 4 retry as blocked until Milestone 2/non-live enhancement work
passes and the user explicitly approves another billed run.

---

## Appendix — current accepted RAGFlow run

Accepted run artifacts and command transcript live under:

```text
/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/20260622-234038
```

The run recorded `command-manifest.tsv`, `command-transcript.log`, exit codes,
`validate_acceptance.py`, and `EXPERIMENT_RESULT.md`. It passed with readiness
`PASS`, Phase 3 hybrid retrieval `pass`, 16/16 sections, 569 evidence items, and
no `--force` in the command manifest.

To reproduce into a new run directory, use the fresh-run appendix below.

RAGFlow scale in the fresh accepted run (reference): 3,974 files, 15,668 symbols,
52,584 graph edges, 22,713 chunks; upload bundle ~115K tokens; plan = 16 sections.

## Appendix — fresh end-to-end run (readiness iteration)

A clean run that exercises the readiness gate, under a fresh output dir.

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

export TARGET_REPO=/Users/ankitsingh/Documents/deep-wiki/ragflow
export OUT=/Users/ankitsingh/Documents/deep-wiki/13-e2e-allphases/runs/$(date +%Y%m%d-%H%M%S)

# Clean start (intentional):
mkdir -p "$OUT"

scripts/00_setup_python312_vectors.sh --recreate-venv

# Phase 1
scripts/phase1_step1_decompose.sh --repo "$TARGET_REPO" --out "$OUT"
scripts/phase1_step2_condense.sh   --out "$OUT" --budget-tokens 250000   # writes planning-handles.md
scripts/phase1_step3_digest.sh     --out "$OUT" --budget-tokens 250000
scripts/phase1_step4_bundle.sh     --out "$OUT" --budget-tokens 250000   # planning-handles.md near the front
scripts/phase1_step5_build_retrieval.sh --out "$OUT" --rebuild \
  --smoke-query "api routes"

# Phase 2 Step 1 — Vertex (use a realistic output cap; tiny caps fail with MAX_TOKENS)
# gemini-2.5-pro is a thinking model and spends part of --max-output-tokens on
# reasoning, so keep the cap generous: 8192 truncated a full RAGFlow plan. Use
# 32768+ for full e2e runs (the CLI default is 65535). Treat any
# finish_reason=MAX_TOKENS response as truncated and rerun with a higher cap.
scripts/phase2_step1_plan.sh --out "$OUT" \
  --project "$GOOGLE_CLOUD_PROJECT" --location "${GOOGLE_CLOUD_LOCATION:-us-central1}" \
  --model gemini-2.5-pro --max-output-tokens 32768
#  smoke alternative: --model gemini-2.5-flash --max-output-tokens 8192

# Phase 2 Step 2 — normalize + readiness gate
scripts/phase2_step2_normalize_plan.sh --out "$OUT" --provider gemini
cat "$OUT/plans/phase3-readiness-report.md"   # require Status: PASS before Phase 3

# If readiness is FAIL for a repairable planner-quality issue, run bounded repair.
# Key this decision on the readiness report, not only on the normalize exit code.
if rg -q '^Status: FAIL' "$OUT/plans/phase3-readiness-report.md"; then
  scripts/phase2_step1b_repair_plan.sh --out "$OUT" \
    --provider gemini \
    --project "$GOOGLE_CLOUD_PROJECT" \
    --location "${GOOGLE_CLOUD_LOCATION:-us-central1}" \
    --model gemini-2.5-pro \
    --max-attempts 2
  cat "$OUT/plans/phase3-readiness-report.md"   # require Status: PASS after repair
fi

# Phase 3 — only when readiness is PASS (the script enforces this; do not use --force in product runs)
scripts/phase3_retrieve_evidence.sh --out "$OUT" --with-vectors
```

If `phase3-readiness-report.md` is `FAIL`, stop and fix Phase 1 planner artifacts,
the Phase 2 prompt instructions, or the normalization rules — do not proceed to
Phase 3 as a normal product run. No evidence item may cite `plans/*` or
`derived/planning-*.md` as repo evidence.
