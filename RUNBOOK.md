# Runbook — generate a DeepWiki plan for any repo

End-to-end commands for the full pipeline. Phase 1 is deterministic and LLM-free;
Phase 2 Step 1 is the only LLM call (a Gemini/Kimi Gem) and happens outside this
tool; Phase 2 Step 2 (`normalize-plan`) is deterministic again.

```
Phase 1  Step 1 decompose   -> raw artifact bundle
         Step 2 condense     -> derived/planning-*.md condensates
         Step 3 digest       -> derived/planning-digest.md (also runs Step 4)
         Step 4 bundle       -> planner-digest/planner-upload-bundle.md (one upload)
         Step 5 build-retrieval -> rag/retrieval-capabilities.json (+ BM25 / optional vectors)
Phase 2  Step 1 (external)   -> Gemini/Kimi plan -> plans/phase2-<provider>-response.md
         Step 2 normalize-plan -> plans/document-plan.json + section-plans.jsonl
Phase 3  (later)             -> deterministic section evidence retrieval
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

## 1. Pick the repo and an output directory

```bash
REPO=/absolute/path/to/the/repo/to/document
OUT=/absolute/path/to/output/bundle        # created if missing
```

## 2. Phase 1 — decompose, condense, digest, bundle

```bash
# Step 1 — raw artifact bundle (inventory, symbols, RAG/BM25, static graph,
#          queries, contracts, tests, derived summaries). No LLM.
python3 -m wiki_generator decompose --repo "$REPO" --out "$OUT"

# Step 2 — planner-facing condensates into <OUT>/derived/
python3 -m wiki_generator condense --in "$OUT" --budget-tokens 250000

# Step 3 — derived/planning-digest.md (this also runs Step 4 by default)
python3 -m wiki_generator digest --in "$OUT" --budget-tokens 250000

# Step 4 — the single upload file (idempotent; only needed if you ran digest
#          with --no-bundle, or want to rebuild it on its own)
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
# Lexical-symbolic (default): BM25 verified/rebuilt; vectors skipped if the
# embeddings extra isn't installed (recorded with the exact reason).
python3 -m wiki_generator build-retrieval --in "$OUT" --vectors auto

# Hybrid: require local vectors (fails non-zero if faiss/model2vec are missing).
pip install -e '.[embeddings]'
python3 -m wiki_generator build-retrieval --in "$OUT" --vectors on

# Optional: prove the substrate answers a query, and force a clean rebuild.
python3 -m wiki_generator build-retrieval --in "$OUT" --rebuild \
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
document-plan.json        normalized DocumentPlan (schema phase2-plan-v1)
document-plan.md          human-readable plan
section-plans.jsonl       one normalized SectionPlan per line
normalization-report.md   resolution counts + notes for Phase 3
unresolved-references.jsonl  every reference that did not resolve (+candidates)
raw-extracted-*.{json,jsonl} raw blocks pulled from the response (debug)
```

Review `normalization-report.md` (resolution counts) and
`unresolved-references.jsonl`. Unresolved items are usually `retrieve: <query>`
hints (intentional) or genuinely ambiguous names (kept with candidates — never
guessed). Phase 3 will consume `document-plan.json` + `section-plans.jsonl`.

Before Phase 3, run **Step 5 (`build-retrieval`, section 2.5)** so the bundle has
an explicit retrieval readiness contract (`rag/retrieval-capabilities.json`). It
verifies/rebuilds BM25 over the corpus and adds vectors when FAISS/model2vec are
available, then reports whether Phase 3 will run in `hybrid` or `lexical-symbolic`
mode.

---

## Appendix — exact commands used for RAGFlow

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator

python3 -m wiki_generator decompose \
  --repo /Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow \
  --out  /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2

python3 -m wiki_generator condense \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

python3 -m wiki_generator digest \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

python3 -m wiki_generator bundle \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

# Step 5 — build/verify the retrieval substrate (lexical-symbolic unless the
# embeddings extra is installed).
python3 -m wiki_generator build-retrieval \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --vectors auto

# Phase 2 Step 1 — either run the Gem by hand (save reply to
# plans/phase2-gemini-response.md), or use Vertex AI:
python3 -m wiki_generator plan \
  --bundle /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --project "$GOOGLE_CLOUD_PROJECT" --location us-central1

python3 -m wiki_generator normalize-plan \
  --bundle       /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --raw-response /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/plans/phase2-gemini-response.md
```

RAGFlow scale (reference): 3,928 files, 15,618 symbols, 52,349 graph edges,
22,429 chunks; upload bundle ~109K tokens; plan = 13 sections.
