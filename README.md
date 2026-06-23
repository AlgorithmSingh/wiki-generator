# wiki-generator

Plan a documentation Wiki for a Python repository. `wiki-generator` turns a repo
into a deterministic **repo-analysis artifact bundle** (Step 1), **condenses** it
into small planner-facing digests an LLM can actually read (Steps 2/3), **bundles**
those into one uploadable file (Step 4), **builds the retrieval substrate** Phase 3
queries (Step 5), runs a **planning LLM** over the upload bundle (Phase 2 Step 1),
**normalizes** the LLM's plan into machine-resolvable artifacts (Phase 2 Step 2),
and **retrieves exact, citeable evidence** for every planned section (Phase 3).
The implemented pipeline currently stops at Phase 3. Phase 2 planning and the
optional bounded Phase 2 repair are LLM-backed; Phase 1 and Phase 3 remain
deterministic and **LLM-free**. Phase 4 writing/synthesis is currently
**spec-only / future implementation** and will be LLM-backed when implemented.

```text
Phase 1  Step 1 decompose  -> raw artifact bundle
         Step 2 condense    -> derived/planning-*.md condensates
         Step 3 digest      -> derived/planning-digest.md
         Step 4 bundle      -> planner-digest/planner-upload-bundle.md (one upload)
         Step 5 build-retrieval -> rag/retrieval-capabilities.json (BM25 + optional vectors)
Phase 2  Step 1 plan        -> Gemini/Kimi plan: plans/phase2-<provider>-response.md
                               (Vertex AI Gemini 2.5 Pro, or run the Gem by hand
                                and save the reply)
         Step 1b plan-repair -> optional bounded/audited Gemini repair on
                                readiness FAIL only
         Step 2 normalize-plan -> plans/document-plan.json + section-plans.jsonl
Phase 3  retrieve-evidence  -> evidence/packets/<section_id>.json (+ manifest,
                               validation, report) — deterministic, no LLM
Phase 4  write/synthesize   -> SPEC ONLY in PHASE4_WRITING_SYNTHESIS_SPEC.md
                               (not implemented; no command yet)
```

Step 5 is numbered after Step 4 because it is **not** needed for the planner
upload; its only hard dependency is Step 1's corpus, so it can run any time after
`decompose` (in practice, before Phase 3).

This implements `PHASE1_DECOMPOSITION_PLAN.md` (Step 1),
`PHASE1_STEP2_STEP3_PLANNING_CONDENSATES.md` (Steps 2/3),
`PHASE1_STEP4_PLANNER_UPLOAD_BUNDLE_SPEC.md` (Step 4),
`PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md` (Step 5),
`PHASE2_PLAN_NORMALIZATION_SPEC.md` (Phase 2 Step 2), and
`PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` (Phase 3). Phase 4 writing/synthesis is
specified in `PHASE4_WRITING_SYNTHESIS_SPEC.md` as **SPEC ONLY / future
implementation**; it defines both Gemini Gem/direct Gemini mode and Vertex AI
`gemini-2.5-pro` mode, but no Phase 4 command exists yet.

> **Current readiness note (2026-06-22):** The `PHASE1_PHASE2_PHASE3_READINESS_ITERATION_2_SPEC.md` patches are **implemented and validated** — Patch 1 (directory anchors → `search_hints[]` warnings), Patch 2 (malformed `SectionPlan` JSONL: deterministic repair + bounded `plan-repair`), Patch 3 (planning diagnostics are not normal sections; no generic Phase 3 fallback). `PHASE3_EVIDENCE_RETRIEVAL_SPEC.md` is unchanged and Phase 3 stays deterministic/LLM-free. A clean fresh validation run (readiness `PASS` → `phase3_retrieve_evidence.sh` without `--force` → evidence validation `pass`, 16/16 sections, 569 items) is at `13-e2e-allphases/runs/20260622-234038`. Phase 4 is **ready to reopen for that fresh bundle** and is **SPEC ONLY / not implemented** in `PHASE4_WRITING_SYNTHESIS_SPEC.md`; never treat stale pre-patch normalized artifacts or forced Phase-3-after-`FAIL` output as a Phase 4 GO.

## Architecture

`src/` layout with a **thin entry / deep libs** split:

```
wiki-generator/            repo root (distribution name: wiki-generator)
  src/
    wiki_generator/        import package
      cli.py               thin argument parser + dispatcher — no logic
      __main__.py          python -m wiki_generator
      libs/                every deep module lives here
        util · ids · config · paths · tools · chunker · rgpacks · context · pipeline
        lanes/               Step 1 decomposition lanes (inventory…derived)
        digest/              Step 2/3 condensates: loader, ranking, planning_*  + upload_package (Step 4)
        retrieval/           Step 5 substrate: loader · fingerprints · bm25 · vectors · capabilities · report · smoke
        plan_normalization/  Phase 2 Step 2: parse · lookups · normalize · writer
        commands/            command bodies: decompose · condense · digest · bundle · build_retrieval · plan · normalize_plan
  tests/  pyproject.toml  README.md  RUNBOOK.md  gemini-gem/
```

`cli.py` only knows how to parse flags and call a command in `libs.commands`;
`libs` never imports `cli`. Each digest summarizer reads the bundle through one
seam (`libs/digest/loader.py`) and ranks through one seam
(`libs/digest/ranking.py`). Plan normalization resolves every reference through
one seam (`libs/plan_normalization/lookups.py`, the `Lookups` class). The Step 5
retrieval substrate owns BM25 in one place (`libs/retrieval/bm25.py` — the
decompose `rag` lane delegates to it, so the FTS5 schema never drifts) and hides
the optional embedding libraries behind an injectable `VectorBackend`
(`libs/retrieval/vectors.py`), so the whole build/skip/fail path is testable
without faiss installed.

## Install / run

This is a `src/`-layout package, so **install it first** (editable is fine). It
uses the Python standard library plus `PyYAML` and `packaging`; some lanes use
external tools **when present** and degrade gracefully when not.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .                      # required (src layout)
```

After install, run with the `wiki-generator` console command (equivalent to
`python -m wiki_generator`):

```bash
# Step 1 — raw artifact bundle
wiki-generator decompose --repo /path/to/python/repo --out /path/to/phase1-output

# Step 2 — planning condensates into <bundle>/derived/
wiki-generator condense --in /path/to/phase1-output --budget-tokens 250000

# Step 3 — derived/planning-digest.md (also runs Step 4 by default)
wiki-generator digest --in /path/to/phase1-output --budget-tokens 250000

# Step 4 — the single-file planner upload bundle
wiki-generator bundle --in /path/to/phase1-output --budget-tokens 250000

# Step 5 — build/verify the retrieval substrate for Phase 3 (deterministic, no LLM).
# BM25 is rebuilt/verified; vectors are built only if the embeddings extra is
# installed (--vectors auto), otherwise skipped with an explicit reason.
wiki-generator build-retrieval --in /path/to/phase1-output --vectors auto

# Phase 2 Step 1 — run the planning LLM (Vertex AI Gemini 2.5 Pro; needs the
# [vertex] extra + GCP credentials — see below). Optional: run the Gem by hand
# instead and save the reply to plans/phase2-gemini-response.md.
wiki-generator plan --bundle /path/to/phase1-output --project my-gcp-project --location us-central1

# Phase 2 Step 2 — normalize the planning response (deterministic, no LLM)
wiki-generator normalize-plan --bundle /path/to/phase1-output \
  --raw-response /path/to/phase1-output/plans/phase2-gemini-response.md

# Phase 2 Step 1b — bounded planner-artifact repair (only if readiness FAILs for a
# planner-quality reason; re-prompts Vertex/Gemini, re-validates, fails loudly).
wiki-generator plan-repair --bundle /path/to/phase1-output \
  --raw-response /path/to/phase1-output/plans/phase2-gemini-response.md

# Phase 3 — retrieve exact, citeable evidence for every planned section
# (deterministic, no LLM). All-sections producer; writes evidence/packets/<id>.json
# plus a manifest, validation, and report. Exit 0 PASS / 2 bad input / 3 bad plan.
wiki-generator retrieve-evidence --bundle /path/to/phase1-output
```

`digest` regenerates the Step 2 condensates first and then runs Step 4, so running
it alone produces the whole upload package; pass `--no-bundle` to stop after the
digest, or run `bundle` on its own. `normalize-plan` never calls an LLM — it only
resolves the planner's references against the Phase 1 indexes.

Optional capabilities:

```bash
pip install -e '.[embeddings]'   # rag/vectors.faiss (faiss + model2vec)
pip install -e '.[grepast]'      # AST-context query previews
pip install -e '.[vertex]'       # Vertex/Gemini LLM commands (`plan`, `plan-repair`)
# brew install universal-ctags semgrep ast-grep   # richer symbol/query lanes
```

### Phase 2 Step 1 — `plan` (Vertex AI Gemini 2.5 Pro)

`plan` is the primary LLM-backed planning command. It sends the planner
instructions + kickoff prompt + the Step 4 upload bundle to `gemini-2.5-pro` on
Vertex AI and writes the raw response to `plans/phase2-gemini-response.md`.
`plan-repair` is the only other implemented LLM-backed command, and it is bounded,
audited, and used only after a readiness `FAIL` for planner-quality issues.

```bash
pip install -e '.[vertex]'                     # the google-genai SDK
gcloud auth application-default login           # Application Default Credentials
export GOOGLE_CLOUD_PROJECT=my-gcp-project      # or pass --project
export GOOGLE_CLOUD_LOCATION=us-central1         # or pass --location
wiki-generator plan --bundle /path/to/phase1-output
```

Nothing GCP-specific is hardcoded — project/location come from `--project` /
`--location` or those env vars, and auth uses ADC. By default it picks up
`gemini-gem/GEM_INSTRUCTIONS.md` and `gemini-gem/KICKOFF_PROMPT.md` if present
(override with `--system` / `--prompt`), else uses built-in defaults. It does not
auto-run `normalize-plan` — run that next.

## What it produces

```
phase1-output/
  ARTIFACT_GUIDE.md            orientation: repo, tools, artifact table, warnings, reading order
  run-metadata.json            tools, counts, timings, warnings (machine-readable)
  inventory/
    files.jsonl                one row per file (path/language/category/size/sha256/git_tracked)
    git-tracked-files.txt      git ls-files
    source-coverage.json       counts by category/language/dir + coverage notes
  symbols/
    symbols.jsonl              SCIP-style symbol index (id/kind/range/signature/parent/doc)
    imports.jsonl              imports with internal-target resolution
    occurrences.jsonl          definitions (exact) + approximate references (confidence)
    tags  /  tags.jsonl        ctags (universal-ctags if present, else AST-derived)
  rag/
    spans.jsonl                citeable source spans (symbol-linked where Python)
    chunks.jsonl               retrieval chunks (link back to span_ids)
    bm25.sqlite                SQLite FTS5 / BM25 index over chunks
    rg-results.jsonl           raw ripgrep --json match capture
    vectors.faiss + vector-metadata.json    optional local embeddings
  static/
    nodes.jsonl / edges.jsonl  property graph (CONTAINS/IMPORTS/CALLS_APPROX/INHERITS/…)
  queries/
    rules/rg/*.json            query-pack rule definitions
    results/rg.jsonl           digested per-match rows
    results/grep-ast/*.md      AST-context previews (grep-ast or built-in fallback)
    results/semgrep.{json,sarif}, results/ast-grep.json    (when those tools are installed)
  contracts/
    openapi.json               discovered spec, or one derived statically from routes
    contract-sources.md        how the contract was produced + discovered specs + routes
  tests/
    pytest-collect.txt         pytest --collect-only (best effort)
    test-files.jsonl           static test-file scan + test/fixture counts
  derived/
    repo-summary.md            deterministic human-readable overview (with file anchors)
    artifact-index.md          machine index of every artifact + counts
```

### Planner-facing outputs (Steps 2/3/4)

`condense`/`digest` add compact, LLM-readable summaries derived from the (huge) raw
artifacts — the raw `symbols/`, `static/`, and `rag/` files are far too large to upload.
`bundle` then packages them for upload:

```
phase1-output/
  derived/
    planning-symbols.md          ranked symbol tables + anchored examples
    planning-graph.md            node/edge counts, degree rankings, hubs, clusters
    planning-runtime-surfaces.md routes/workers/CLI/models/config/auth/… + API contract
    planning-tests.md            test counts, directories, collection status
    planning-gaps.md             skipped tools, unresolved counts, approximation notes
    planning-digest.md           one compact brief — read this first (Step 3)
  planner-digest/                upload-ready package (Step 4)
    README_FOR_PLANNER.md        what it is + the Phase 2 output contract
    planning-*.md                byte-identical copies of the condensates above
    upload-list.md               exactly what to upload, per-file chars/tokens + budget check
    planner-upload-bundle.md     the whole upload set in ONE file, each part wrapped in
                                 <!-- BEGIN/END INCLUDED FILE: <path> --> markers
```

The target upload budget is **≤ 250K tokens** (configurable via `--budget-tokens`); the
raw backend indexes are deliberately excluded and kept for Phase 3 retrieval. If the
budget is exceeded, `bundle` trims optional/supporting files first (never the README or
the six condensates); if those required files alone exceed the budget it fails loudly.

### Retrieval substrate outputs (Step 5 `build-retrieval`)

`build-retrieval` verifies or rebuilds the searchable indexes over the Step 1
corpus and writes the contract Phase 3 reads to choose retrieval tactics per
section. It never writes EvidencePackets or Wiki prose, never calls an LLM, and
never makes a network call.

```
phase1-output/rag/
  bm25.sqlite                    verified, or rebuilt if missing/stale/row-count mismatch
  retrieval-capabilities.json    machine-readable contract: chunk/span counts, which retrieval
                                 modes are available, index row counts + content fingerprint
  retrieval-substrate-report.md  human-readable readiness: PASS/FAIL + recommended Phase 3 mode
                                 (hybrid if vectors built, else lexical-symbolic)
  vector-build-report.md         vector lane status, model, count, or exact skip/fail reason
  vectors.faiss                  only when vectors are built (--vectors on/auto with faiss)
  vector-metadata.json[l]        one metadata row per vector (chunk_id/span_ids/path/range/sha256);
                                 JSONL past ~20k vectors (path recorded in capabilities)
  retrieval-smoke-tests.jsonl    only with --smoke-query: top-k hits proving the substrate answers
```

A run is **lexical-symbolic** (BM25 + ripgrep + symbols + graph + contracts +
tests) when the embedding libraries are absent, and **hybrid** (adds vector
retrieval) when they are installed. `--vectors auto` skips vectors with a recorded
reason; `--vectors on` (alias `--fail-without-vectors`) exits non-zero if faiss/
model2vec are unavailable or the vector/metadata counts diverge. Reruns on the
same corpus are deterministic.

### Phase 2 normalization outputs (`normalize-plan`)

After the planning LLM responds (saved as `plans/phase2-<provider>-response.md`),
`normalize-plan` parses it deterministically and resolves every reference against the
Phase 1 indexes — human query-pack titles → canonical keys, dotted symbol names →
`symbol_id`, file anchors → verified paths with anchor confidence. It never guesses
ambiguous references; they are recorded as unresolved.

```
phase1-output/plans/
  document-plan.json             normalized DocumentPlan (schema phase2-plan-v1)
  document-plan.md               human-readable plan
  section-plans.jsonl            one normalized SectionPlan per line (phase2-section-plan-v1)
  normalization-report.md        resolution counts + notes for Phase 3
  unresolved-references.jsonl    every reference that did not resolve (with candidates)
  raw-extracted-*.{json,jsonl}   the raw blocks pulled from the response (debug)
```

Use `--strict` to exit non-zero when anything is unresolved.

## Identifier scheme

All lanes share one id scheme (`wiki_generator/libs/ids.py`) so artifacts cross-link:

| id | shape | example |
|---|---|---|
| `symbol_id` | `python <dotted.module>/<descriptors>` | `python app.api.users/list_users().` |
| | class `Name#`, method `Name#name().` | `python app.db/User#save().` |
| `span_id` | `span:<path>:<start>-<end>:<kind>` | `span:app/api/users.py:9-11:function` |
| `chunk_id` | `chunk:<path>:<start>-<end>` | `chunk:app/api/users.py:9-11` |
| node ids | `file:`, `module:`, `sym:<symbol_id>`, `dep:`, `repo:` | `sym:python app.db/User#` |

A chunk references the `span_ids` it overlaps; a Python span carries its
`symbol_id`; a symbol node is `sym:<symbol_id>`.

## Design notes

- **Python-first.** Only `.py` files get AST-level structure. Other source is
  inventoried and chunked by line windows for retrieval, but not parsed for symbols.
- **Approximate edges are marked.** `CALLS_APPROX`, `MENTIONS`, and `TESTS_APPROX`
  edges and reference occurrences are name-resolved and carry a `confidence` field;
  unresolved call sites are counted and surfaced as a warning.
- **Tools are optional and self-tested.** Each external tool is probed at startup
  (grep-ast is run on a throwaway snippet to confirm it actually works). When a tool
  is missing or broken, the lane writes a well-formed skip note and records a warning
  in `ARTIFACT_GUIDE.md` rather than failing.
- **Lane isolation.** If one lane raises, the failure is recorded and the run
  continues, so a single broken lane never costs the whole bundle.
- **Deterministic.** Re-running on the same repo produces byte-identical data
  artifacts; only the timestamp/timing in `ARTIFACT_GUIDE.md` / `run-metadata.json`
  changes.
- **One LLM step.** Phase 1 (decompose/condense/digest/bundle) and Phase 2
  normalization are deterministic and LLM-free; only the `plan` command calls an
  LLM (Vertex AI Gemini). The normalized `DocumentPlan` is produced by
  `normalize-plan` from that response — the tool never invents plan content.

## Flags

| flag | default | meaning |
|---|---|---|
| `--embeddings auto\|on\|off` | auto | vector lane; auto = use if faiss+model2vec importable |
| `--grep-ast auto\|on\|off` | auto | grep-ast previews; auto = use if it self-tests, else built-in |
| `--semgrep auto\|on\|off` | auto | semgrep results; auto = use if installed |
| `--ast-grep auto\|on\|off` | auto | ast-grep results; auto = use if installed |
| `--pytest-collect auto\|on\|off` | auto | pytest --collect-only; auto = attempt if importable |
| `--contracts-import` | off | UNSAFE: import the app to extract a live OpenAPI schema |
| `--rg-cap N` | 80 | max digested hits captured per ripgrep query pack |

`condense` / `digest` / `bundle` flags:

| flag | default | meaning |
|---|---|---|
| `--in <bundle>` | — | path to an existing decomposition bundle (required) |
| `--out <dir>` | `<bundle>/planner-digest` | upload-package directory (`digest`/`bundle`) |
| `--budget-tokens N` | 250000 | target upload token budget (`ceil(chars/4)` estimate) |
| `--no-bundle` | off | (`digest` only) stop after `planning-digest.md`; skip Step 4 |

`build-retrieval` flags (Step 5):

| flag | default | meaning |
|---|---|---|
| `--in <bundle>` | — | path to an existing decomposition bundle (required) |
| `--bm25 auto\|on\|off` | on | BM25 index; on/auto = build or verify, off = skip |
| `--vectors auto\|on\|off` | auto | vectors; auto = build if faiss+model2vec importable else skip with reason, on = require (fail if unavailable), off = disabled by user |
| `--embedding-model NAME` | minishlab/potion-base-8M | local embedding model |
| `--batch-size N` | 2048 | embedding batch size |
| `--rebuild` | off | delete and rebuild existing retrieval indexes |
| `--smoke-query TEXT` | — | run a query against the substrate after build and record top hits |
| `--fail-without-vectors` | off | alias for `--vectors on` |

`plan` flags (Phase 2 Step 1; needs the `[vertex]` extra + GCP credentials):

| flag | default | meaning |
|---|---|---|
| `--bundle <dir>` | — | path to the Phase 1 decomposition bundle (required) |
| `--bundle-file <f>` | `<bundle>/planner-digest/planner-upload-bundle.md` | explicit upload file |
| `--out <dir>` | `<bundle>/plans` | where to write `phase2-<provider>-response.md` |
| `--model <id>` | gemini-2.5-pro | Vertex AI model id |
| `--project <id>` | `$GOOGLE_CLOUD_PROJECT` | GCP project (required, via flag or env) |
| `--location <loc>` | `$GOOGLE_CLOUD_LOCATION` or us-central1 | Vertex AI location |
| `--system <file>` | gemini-gem/GEM_INSTRUCTIONS.md or built-in | system instructions |
| `--prompt <file>` | gemini-gem/KICKOFF_PROMPT.md or built-in | kickoff prompt |
| `--provider <name>` | gemini | label used in the output filename |
| `--temperature N` | 0.2 | sampling temperature |
| `--max-output-tokens N` | 65535 | response cap |

`normalize-plan` flags:

| flag | default | meaning |
|---|---|---|
| `--bundle <dir>` | — | path to the Phase 1 decomposition bundle (required) |
| `--raw-response <file>` | — | raw Gemini/Kimi planning response, markdown (required) |
| `--out <dir>` | `<bundle>/plans` | output directory for the plan artifacts |
| `--strict` | off | exit non-zero if any symbol/file/query-pack is unresolved |
| `--provider <name>` | gemini | planning provider, recorded as metadata only |

## Tests

Stdlib-only; run after `pip install -e .`:

```bash
python -m unittest discover -s tests -v     # or: pytest
```
