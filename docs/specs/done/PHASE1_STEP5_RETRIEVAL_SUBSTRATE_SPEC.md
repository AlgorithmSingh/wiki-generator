# Phase 1 Step 5 — Retrieval Substrate Spec

## Artifact being designed

Phase 1 Step 5 creates the **retrieval substrate** that Phase 3 will query section-by-section to build EvidencePackets.

This is not the target repository's own RAG system. This is the Wiki generator's local retrieval layer over the decomposed repository.

The retrieval substrate is deterministic and LLM-free. It builds or verifies search indexes over the Phase 1 corpus so later code can retrieve exact, citeable evidence for each normalized `SectionPlan`.

## Pipeline position

```text
Phase 1 Step 1: decompose
  -> raw repo facts + citeable corpus
  -> inventory/, symbols/, static/, rag/spans.jsonl, rag/chunks.jsonl, queries/, contracts/, tests/

Phase 1 Step 2: condense
  -> derived/planning-*.md condensates

Phase 1 Step 3: digest
  -> derived/planning-digest.md

Phase 1 Step 4: bundle
  -> planner-digest/planner-upload-bundle.md

Phase 1 Step 5: build-retrieval
  -> BM25 / exact / vector retrieval substrate for Phase 3

Phase 2 Step 1: plan
  -> raw Gemini/Kimi planning response

Phase 2 Step 2: normalize-plan
  -> plans/document-plan.json
  -> plans/section-plans.jsonl

Phase 3: retrieve-evidence
  -> section-by-section EvidencePackets
```

Step 5 is numbered after Step 4 because it is **not needed for planner upload**. Its only hard dependency is Step 1's corpus artifacts, so it can be run any time after `decompose`; in practice it should be complete before Phase 3 starts.

## Current RAG/retrieval state from the RAGFlow run

The current bundle already has a partial retrieval substrate:

```text
rag/spans.jsonl          24,482 citeable spans
rag/chunks.jsonl         22,429 retrieval chunks
rag/bm25.sqlite          22,429 BM25 / SQLite FTS rows
rag/rg-results.jsonl     9,366 raw ripgrep matches
queries/results/rg.jsonl 892 digested query-pack hits
symbols/symbols.jsonl    15,618 symbols
static/edges.jsonl       52,349 graph edges
```

So the current system can support:

- exact file/path retrieval;
- symbol-to-span retrieval;
- BM25 lexical retrieval over chunks;
- ripgrep / exact regex retrieval;
- query-pack retrieval;
- static graph neighbor expansion;
- OpenAPI/contract retrieval;
- test inventory retrieval.

The current system does **not** have vector retrieval for that run:

```text
rag/vectors.faiss        not written
rag/vector-metadata.json placeholder / skip metadata only
```

Reason recorded in `run-metadata.json` and `derived/planning-gaps.md`:

```text
faiss/numpy/model2vec not importable (ModuleNotFoundError: No module named 'faiss')
```

Deep-research conclusion: this was most likely because the optional `.[embeddings]` extra was not installed in the Python environment used for the run. The repo keeps vector dependencies opt-in:

```text
faiss-cpu
numpy
model2vec
```

This is not evidence that FAISS or model2vec are impossible on this machine. Current upstream metadata indicates modern `faiss-cpu` and `model2vec` support Python 3.10+ and macOS wheels exist for common architectures. The main local risk is FAISS wheel/platform resolution: Python version, macOS version, arm64 vs x86_64/Rosetta, or pip falling back to a source build.

The current system also does **not** yet have:

- a Phase 3 section retriever;
- EvidencePacket generation;
- hybrid scoring across symbols + BM25 + vectors + graph;
- reranking;
- final Wiki drafting.

## Quality bar

A good retrieval substrate must let Phase 3 answer this question for every normalized section:

> Given this `SectionPlan`, what exact code/docs/contracts/tests should be cited as evidence?

It is good if:

- every searchable item maps back to stable `chunk_id`, `span_id`, file path, and line range where possible;
- BM25 / lexical search is available for all chunks;
- exact regex / query-pack results are available for framework/runtime surfaces;
- symbol and file references from `section-plans.jsonl` can be resolved to source spans;
- graph expansion can find local neighbors without treating approximate edges as truth;
- vector retrieval is available when dependencies are installed, and its absence is explicit when not;
- a machine-readable capability file tells Phase 3 which retrieval modes are available;
- a human-readable report tells the user whether Phase 3 will run in lexical-only or hybrid mode;
- rerunning the command on the same inputs is deterministic.

## Failure modes

Step 5 fails if:

- it cannot read `rag/chunks.jsonl` or `rag/spans.jsonl`;
- BM25 row count does not match the indexed chunk count;
- vector metadata count does not match the FAISS vector count when vectors are enabled;
- `--vectors on` is requested but dependencies are unavailable;
- stale indexes are left in place after chunk IDs or content hashes changed;
- chunk/vector metadata cannot map search hits back to citeable source anchors;
- it writes EvidencePackets or generated Wiki prose;
- it uses an LLM or a network service.

## Command

Canonical command:

```bash
wiki-generator build-retrieval \
  --in /path/to/phase1-output \
  --bm25 on \
  --vectors auto \
  --embedding-model minishlab/potion-base-8M
```

Equivalent module form:

```bash
python3 -m wiki_generator build-retrieval \
  --in /path/to/phase1-output \
  --bm25 on \
  --vectors auto \
  --embedding-model minishlab/potion-base-8M
```

Suggested flags:

```text
--bm25 auto|on|off           default: on
--vectors auto|on|off        default: auto
--embedding-model NAME       default: minishlab/potion-base-8M or existing project default
--batch-size N               default: deterministic implementation choice
--rebuild                    delete and rebuild existing retrieval indexes
--smoke-query TEXT           optional query to test substrate after build
--fail-without-vectors       alias for --vectors on
```

Vector mode semantics:

```text
--vectors auto
  Probe faiss/numpy/model2vec. If available, build vectors. If unavailable, skip
  vectors, record the exact import/install reason, and pass in lexical-symbolic mode.

--vectors on
  Require vectors. If faiss/numpy/model2vec cannot import, model loading fails,
  FAISS writing fails, or vector/metadata counts diverge, exit non-zero.

--vectors off
  Do not probe or build vectors. Record vectors as disabled_by_user and pass in
  lexical-symbolic mode.
```

Compatibility note: the existing `decompose` command already writes `rag/spans.jsonl`, `rag/chunks.jsonl`, `rag/bm25.sqlite`, and `rag/rg-results.jsonl`. The Step 5 implementation may initially wrap/rebuild/verify those existing outputs rather than moving all code at once. Long term, the clean split is:

```text
decompose         -> corpus + raw facts
build-retrieval   -> searchable indexes over that corpus
retrieve-evidence -> section-specific EvidencePackets
```

## Preflight and local verification

Before blaming the code, verify the exact Python environment used to run `wiki-generator`:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
python -V
python -c "import sys, platform, sysconfig; print(sys.executable); print(platform.platform()); print(platform.machine()); print(sysconfig.get_platform())"
python -m pip show wiki-generator faiss-cpu numpy model2vec
python - <<'PY'
import faiss, numpy, model2vec
print('embeddings imports ok')
print('faiss', getattr(faiss, '__version__', 'unknown'))
print('numpy', numpy.__version__)
PY
```

Correct install command from repo root:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
python -m pip install -e '.[embeddings]'
```

If FAISS installation fails, capture the verbose pip log:

```bash
python -m pip install -vvv -U 'faiss-cpu' 'numpy>=1.25' packaging model2vec
```

Common FAISS gotchas to report in `retrieval-substrate-report.md`:

- `faiss-cpu` wheel not available for this Python/macOS/architecture combination;
- accidental Rosetta/x86_64 versus arm64 environment mismatch;
- pip falling back to source build;
- older pinned `faiss-cpu` versions with missing Python 3.11+ wheels;
- native runtime issues such as OpenMP/libomp. If FAISS imports but has runtime CPU-instruction issues, try `FAISS_OPT_LEVEL=generic` as a diagnostic.

## Inputs

Required:

```text
run-metadata.json
inventory/files.jsonl
rag/spans.jsonl
rag/chunks.jsonl
symbols/symbols.jsonl
symbols/occurrences.jsonl
static/nodes.jsonl
static/edges.jsonl
queries/rules/rg/*.json
queries/results/rg.jsonl
contracts/openapi.json
tests/test-files.jsonl
```

Useful optional inputs:

```text
rag/rg-results.jsonl
queries/results/grep-ast/*.md
contracts/contract-sources.md
tests/pytest-collect.txt
```

Step 5 must not require Phase 2 outputs. It builds a repo-wide substrate before section-specific retrieval happens.

## Outputs

Canonical outputs:

```text
rag/bm25.sqlite
rag/retrieval-capabilities.json
rag/retrieval-substrate-report.md
```

Vector outputs, when enabled and available:

```text
rag/vectors.faiss
rag/vector-metadata.json
rag/vector-build-report.md
```

Optional smoke-test output:

```text
rag/retrieval-smoke-tests.jsonl
```

## `rag/retrieval-capabilities.json`

Purpose: machine-readable contract for Phase 3.

Minimum shape:

```json
{
  "schema_version": "retrieval-substrate-v1",
  "bundle_root": "/path/to/phase1-output",
  "chunk_count": 22429,
  "span_count": 24482,
  "capabilities": {
    "file_lookup": true,
    "symbol_lookup": true,
    "bm25": true,
    "ripgrep_results": true,
    "query_packs": true,
    "static_graph": true,
    "contracts": true,
    "tests": true,
    "vectors": false
  },
  "indexes": {
    "bm25": {
      "path": "rag/bm25.sqlite",
      "row_count": 22429,
      "content_fingerprint": "sha256:..."
    },
    "vectors": {
      "path": null,
      "metadata_path": "rag/vector-metadata.json",
      "row_count": 0,
      "model": null,
      "status": "skipped",
      "reason": "faiss/numpy/model2vec not importable"
    }
  },
  "warnings": []
}
```

This is not a replacement for `ARTIFACT_GUIDE.md`; it is a small machine-readable capability contract for Phase 3.

## `rag/retrieval-substrate-report.md`

Purpose: human-readable readiness report.

Must include:

- input bundle path;
- chunk and span counts;
- BM25 status and row count;
- vector status, model, row count, or skip reason;
- exact/query-pack retrieval status;
- symbol/static graph availability;
- known caveats;
- recommended Phase 3 retrieval mode:
  - `hybrid` if vectors are available;
  - `lexical-symbolic` if vectors are unavailable;
- PASS/FAIL status.

## Vector indexing requirements

If vectors are enabled:

- embed the same chunk text used by `rag/chunks.jsonl`;
- preserve stable chunk ordering;
- write a metadata row for every vector;
- include `chunk_id`, `span_ids`, `path`, range, language/category when available;
- do not store API keys or external service configuration;
- use local embeddings only;
- no network calls;
- fail if metadata and vector count diverge.

Recommended metadata shape:

```json
{
  "schema_version": "vector-metadata-v1",
  "model": "minishlab/potion-base-8M",
  "distance": "cosine",
  "vectors": [
    {
      "ordinal": 0,
      "chunk_id": "chunk:app/api/users.py:9-42",
      "span_ids": ["span:app/api/users.py:9-42:function"],
      "path": "app/api/users.py",
      "range": {"start_line": 9, "end_line": 42},
      "sha256": "..."
    }
  ]
}
```

If the metadata file would become too large, use JSONL instead:

```text
rag/vector-metadata.jsonl
```

and record that path in `retrieval-capabilities.json`.

## BM25 requirements

BM25 / SQLite FTS must:

- index every row in `rag/chunks.jsonl` unless explicitly filtered;
- retain `chunk_id`, path, start/end lines, and text;
- support deterministic top-k search;
- record indexed row count;
- be rebuilt when chunk content changes;
- expose enough metadata for Phase 3 to recover citeable spans.

## Retrieval modes exposed to Phase 3

Step 5 builds indexes only. It does not retrieve section evidence. But it should make these retrieval modes available:

```text
file_anchor       exact file/path/range lookup
symbol_anchor     symbol_id -> symbol range/span/chunk lookup
query_pack        canonical query-pack hits from queries/results/rg.jsonl
bm25              lexical search over chunks
vector            semantic search over chunks, if vectors are available
graph_neighbors   static graph expansion from symbols/files/modules
contract_lookup   OpenAPI route/path/method lookup
test_lookup       test file/function lookup
```

Phase 3 will combine these per section. Step 5 should not decide which evidence belongs to which section.

## Interaction with Phase 2 normalized plan

Step 5 does not need `plans/section-plans.jsonl`.

Phase 3 will read:

```text
plans/document-plan.json
plans/section-plans.jsonl
rag/retrieval-capabilities.json
```

Then it will choose retrieval tactics per section:

- resolved `symbol_id` -> `symbol_anchor`;
- verified file path/range -> `file_anchor`;
- canonical query pack -> `query_pack`;
- free-text retrieval hint -> `bm25` and `vector` if available;
- related files/classes -> `graph_neighbors`;
- routes -> `contract_lookup` and `query_pack`;
- tests -> `test_lookup`.

## Implementation location

Recommended package shape:

```text
src/wiki_generator/
  cli.py                              # add build-retrieval subcommand
  libs/commands/build_retrieval.py    # command wrapper
  libs/retrieval/
    __init__.py
    loader.py                         # load chunks/spans/symbols/files/capabilities
    bm25.py                           # build/verify SQLite FTS index
    vectors.py                        # build/verify FAISS + metadata
    fingerprints.py                   # input fingerprints / stale-index detection
    report.py                         # retrieval-capabilities + markdown report
    smoke.py                          # optional smoke queries
```

Do not put Phase 3 EvidencePacket logic in this package area. Use a later `libs/evidence/` or `libs/phase3/` package for section retrieval.

## Tests to require

Unit tests should cover:

- command argument parsing for `build-retrieval`;
- missing `rag/chunks.jsonl` fails clearly;
- BM25 row count equals chunk count;
- stale index detection when chunk fingerprints change;
- `--vectors auto` skips gracefully when FAISS/model2vec are unavailable;
- `--vectors on` fails clearly when FAISS/model2vec are unavailable;
- vector metadata count equals FAISS index count when vectors are available;
- `retrieval-capabilities.json` accurately reports enabled/disabled modes;
- report says `lexical-symbolic` when vectors are unavailable;
- report says `hybrid` when vectors are available;
- optional smoke query writes deterministic results.

## Acceptance criteria

A successful Step 5 run in lexical-only mode:

- writes or verifies `rag/bm25.sqlite`;
- writes `rag/retrieval-capabilities.json`;
- writes `rag/retrieval-substrate-report.md`;
- records `vectors: false` with the exact skip reason;
- reports `lexical-symbolic` retrieval mode;
- passes BM25 row-count checks;
- does not write EvidencePackets.

A successful Step 5 run in hybrid mode:

- writes or verifies all lexical outputs;
- writes `rag/vectors.faiss`;
- writes `rag/vector-metadata.json` or `rag/vector-metadata.jsonl`;
- verifies vector count equals metadata count;
- records model name and vector count;
- reports `hybrid` retrieval mode;
- does not write EvidencePackets.

## Recommended next decision before Phase 3

Before starting Phase 3, decide whether the first EvidencePacket implementation should run in:

```text
lexical-symbolic mode: BM25 + ripgrep + symbols + graph + contracts + tests
```

or wait for:

```text
hybrid mode: lexical-symbolic + vector retrieval
```

The current RAGFlow bundle can support lexical-symbolic Phase 3 now. Hybrid Phase 3 requires installing the embeddings dependencies and running Step 5 with vectors enabled.
