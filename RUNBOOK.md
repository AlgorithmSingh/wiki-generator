# Variables to set
   cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator                                                      
                                                                                                                           
   export REPO=/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow                                   
   export OUT=/Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2                                       


# Runbook — generate a DeepWiki plan for any repo

End-to-end commands for the full pipeline. Phase 1 is deterministic and LLM-free;
Phase 2 Step 1 is the only LLM call (a Gemini/Kimi Gem) and happens outside this
tool; Phase 2 Step 2 (`normalize-plan`) is deterministic again.

```
Phase 1  Step 1 decompose   -> raw artifact bundle
         Step 2 condense     -> derived/planning-*.md condensates
                                (incl. planning-handles.md — the exact-handle catalog)
         Step 3 digest       -> derived/planning-digest.md (also runs Step 4)
         Step 4 bundle       -> planner-digest/planner-upload-bundle.md (one upload)
         Step 5 build-retrieval -> rag/retrieval-capabilities.json (+ BM25 / optional vectors)
Phase 2  Step 1 (external)   -> Gemini/Kimi plan -> plans/phase2-<provider>-response.md
         Step 2 normalize-plan -> plans/document-plan.json + section-plans.jsonl
                                  + plans/phase3-readiness-report.md (PASS/FAIL gate)
Phase 3  retrieve-evidence   -> evidence/packets/<section_id>.json (+ manifest,
                                validation, report) — deterministic, no LLM
                                (refuses to run if readiness report is not PASS)
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
the preflight in `PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md`.

Quick handoff verification on an existing bundle, with vectors required:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

scripts/phase1_step5_build_retrieval.sh \
  --out /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --rebuild \
  --run-tests-first \
  --smoke-query "authentication and login flow"

cat /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/rag/retrieval-substrate-report.md
cat /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/rag/retrieval-capabilities.json
```

## 3. Phase 2 Step 1 — run the planning LLM (the only LLM step)

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

---

## Appendix — exact commands used for RAGFlow

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

export REPO=/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow
export OUT=/Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2

scripts/00_setup_python312_vectors.sh --recreate-venv
scripts/phase1_step1_decompose.sh --repo "$REPO" --out "$OUT"
scripts/phase1_step2_condense.sh --out "$OUT" --budget-tokens 250000
scripts/phase1_step3_digest.sh --out "$OUT" --budget-tokens 250000
scripts/phase1_step4_bundle.sh --out "$OUT" --budget-tokens 250000
scripts/phase1_step5_build_retrieval.sh --out "$OUT" --rebuild \
  --smoke-query "authentication and login flow"

# Phase 2 Step 1 — either run the Gem by hand (save reply to
# plans/phase2-gemini-response.md), or use Vertex AI:
scripts/phase2_step1_plan.sh --out "$OUT" \
  --project "$GOOGLE_CLOUD_PROJECT" --location us-central1

scripts/phase2_step2_normalize_plan.sh --out "$OUT" \
  --raw-response "$OUT/plans/phase2-gemini-response.md"

scripts/phase3_retrieve_evidence.sh --out "$OUT" --with-vectors
```

RAGFlow scale (reference): 3,928 files, 15,618 symbols, 52,349 graph edges,
22,429 chunks; upload bundle ~109K tokens; plan = 13 sections.

## Appendix — fresh end-to-end run (readiness iteration)

A clean run that exercises the readiness gate, under a fresh output dir.

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

export TARGET_REPO=/Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow
export OUT=/Users/ankitsingh/Documents/deep-wiki/11-testing-pipeline

# Clean start (intentional):
rm -rf "$OUT"; mkdir -p "$OUT"

scripts/00_setup_python312_vectors.sh --recreate-venv

# Phase 1
scripts/phase1_step1_decompose.sh --repo "$TARGET_REPO" --out "$OUT"
scripts/phase1_step2_condense.sh   --out "$OUT" --budget-tokens 250000   # writes planning-handles.md
scripts/phase1_step3_digest.sh     --out "$OUT" --budget-tokens 250000
scripts/phase1_step4_bundle.sh     --out "$OUT" --budget-tokens 250000   # planning-handles.md near the front
scripts/phase1_step5_build_retrieval.sh --out "$OUT" --rebuild \
  --smoke-query "api routes"

# Phase 2 Step 1 — Vertex (use a realistic output cap; tiny caps fail with MAX_TOKENS)
scripts/phase2_step1_plan.sh --out "$OUT" \
  --project "$GOOGLE_CLOUD_PROJECT" --location "${GOOGLE_CLOUD_LOCATION:-us-central1}" \
  --model gemini-2.5-pro --max-output-tokens 8192
#  smoke alternative: --model gemini-2.5-flash --max-output-tokens 4096

# Phase 2 Step 2 — normalize + readiness gate
scripts/phase2_step2_normalize_plan.sh --out "$OUT" --provider gemini
cat "$OUT/plans/phase3-readiness-report.md"   # require Status: PASS before Phase 3

# Phase 3 — only when readiness is PASS (the script enforces this; --force overrides)
scripts/phase3_retrieve_evidence.sh --out "$OUT" --with-vectors
```

If `phase3-readiness-report.md` is `FAIL`, stop and fix Phase 1 planner artifacts,
the Phase 2 prompt instructions, or the normalization rules — do not proceed to
Phase 3 as a normal product run. No evidence item may cite `plans/*` or
`derived/planning-*.md` as repo evidence.
