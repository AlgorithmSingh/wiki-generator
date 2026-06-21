# Phase 1 Decomposition Plan — Artifact Bundle

## Goal

Phase 1 takes a Python repo directory and creates a deterministic **repo-analysis artifact bundle**.

It does **not** create a custom DeepWiki DSL as the primary output. It produces standard or standard-adjacent artifacts that later phases can use for planning, retrieval, EvidencePackets, and writing.

No LLM calls in Phase 1.

## Command shape

```bash
python -m wiki_generator decompose \
  --repo /path/to/python/repo \
  --out /path/to/phase1-output
```

## Output directory shape

```text
phase1-output/
  ARTIFACT_GUIDE.md
  inventory/
    files.jsonl
    git-tracked-files.txt
    source-coverage.json
  symbols/
    symbols.jsonl
    imports.jsonl
    occurrences.jsonl
    tags
    tags.jsonl
  rag/
    spans.jsonl
    chunks.jsonl
    bm25.sqlite
    rg-results.jsonl
    vectors.faiss
    vector-metadata.json
  static/
    nodes.jsonl
    edges.jsonl
  queries/
    rules/
      rg/*.json
    results/
      rg.jsonl
      semgrep.json
      semgrep.sarif
      ast-grep.json
      grep-ast/*.md
  contracts/
    openapi.json
    contract-sources.md
  tests/
    pytest-collect.txt
    test-files.jsonl
  derived/
    repo-summary.md
    artifact-index.md
```

`ARTIFACT_GUIDE.md` replaces a custom JSON manifest. It should explain what repo was decomposed, what each directory contains, which tools produced each artifact, artifact counts, warnings/skipped areas, and the recommended reading order for the planning LLM.

## V1 principle

V1 should include whatever is required to produce a high-quality decomposition artifact bundle.

The default lane is Python-first and artifact-first: start with the simplest reliable tool for each artifact, but do not exclude stronger tools if artifact quality requires them. If embeddings, Semgrep, ast-grep, Tree-sitter, CodeQL, Joern, SCIP, LSP, or another standard tool is needed to produce the required artifact for a target repo, it belongs in V1.

## Dependencies and tool responsibilities

The implementation is a Python CLI. Most implementation code can use the Python standard library, plus external command-line tools where those tools are the industry-practice artifact producer.

Recommended Python package dependencies:

```text
PyYAML
packaging
```

Likely external tools:

```text
git
rg / ripgrep
pytest
universal-ctags
local grep-ast: /Users/ankitsingh/Documents/deep-wiki/4-graph-based-grep/grep-ast
```

Quality-driven tools to include when needed:

```text
faiss-cpu
numpy
model2vec
semgrep
ast-grep CLI
Tree-sitter
CodeQL CLI
Joern
SCIP/LSP tooling
```

| Lane | Library/tool | What it helps with |
|---|---|---|
| Inventory | `git ls-files`, `git status` | canonical tracked-file list and repo state |
| Inventory | Python `pathlib`, `os` | filesystem traversal and path normalization |
| Inventory | Python `hashlib` | stable content hashes for files/chunks |
| Inventory | Python `mimetypes`, suffix rules | language/category guessing |
| Inventory/config | Python `tomllib` | parse `pyproject.toml` and TOML config |
| Inventory/config | PyYAML | parse YAML config/deployment files |
| Symbols | Python stdlib `ast` | parse Python modules, functions, classes, imports, decorators, docstrings, line ranges |
| Symbols | Universal Ctags | emit standard `tags`/JSON tags as an industry-practice symbol index sidecar |
| RAG/BM25 | Python chunker | build citeable source spans/chunks from files and AST symbols |
| RAG/BM25 | SQLite `sqlite3` with FTS5 | local lexical/BM25-style search index over chunks |
| RAG/vector | FAISS + local embeddings, when needed | local semantic retrieval without chat LLM calls |
| RAG/exact | `ripgrep --json` | exact/regex search results in machine-readable form |
| Static graph | Python `ast` + JSONL writer | property-graph projection: `CONTAINS`, `IMPORTS`, `CALLS_APPROX`, etc. |
| Static graph | CodeQL/Joern/Tree-sitter, when needed | stronger static-analysis artifacts if Python AST is insufficient |
| Queries | `ripgrep --json` | machine-readable query-pack baseline |
| Queries | local `grep-ast` | contextual AST-aware/human-readable query output and evidence previews |
| Queries | Semgrep / ast-grep, when needed | structured static-pattern results, preferably JSON/SARIF |
| Contracts | safe static inspection first | discover existing OpenAPI/contracts without running arbitrary servers |
| Tests | `pytest --collect-only -q` | standard Python test discovery without executing tests |
| Derived | deterministic Python summarizer | human-readable artifact guide, artifact index, and repo summary |

## 1. Inventory lane

Purpose: know what files exist and what role they play.

Tools/libraries:

- `git ls-files` when repo is a git repo.
- Python `pathlib` fallback for non-git repos.
- Python classifiers for source/test/docs/config/deployment/vendor/generated.
- Python `hashlib` for content hashes.
- Python `tomllib` / PyYAML for metadata/config parsing.

Artifacts:

```text
inventory/files.jsonl
inventory/git-tracked-files.txt
inventory/source-coverage.json
```

Example `files.jsonl` row:

```json
{"path":"app/main.py","language":"python","category":"source","size_bytes":1234,"line_count":88,"sha256":"...","git_tracked":true}
```

## 2. Symbols lane

Purpose: produce an industry-practice symbol/code-intelligence index.

Tools/libraries:

- Python stdlib `ast` for Python symbols.
- Universal Ctags for `tags` and JSON tags.
- Shape the JSONL output like known code-intelligence systems: symbol, kind, file, range, signature, parent, documentation.

Artifacts:

```text
symbols/symbols.jsonl
symbols/imports.jsonl
symbols/occurrences.jsonl
symbols/tags
symbols/tags.jsonl
```

Example `symbols.jsonl` row:

```json
{"symbol_id":"python app.api.users/list_users().","name":"list_users","kind":"function","path":"app/api/users.py","range":{"start_line":24,"end_line":41},"signature":"def list_users(...)"}
```

## 3. RAG / BM25 lane

Purpose: create the local retrieval corpus and indexes.

Tools/libraries:

- Python chunker over inventory + AST symbols.
- SQLite FTS5 for BM25/lexical search.
- `ripgrep --json` for exact search result capture.
- FAISS/local embeddings when semantic retrieval quality is needed.

Artifacts:

```text
rag/spans.jsonl
rag/chunks.jsonl
rag/bm25.sqlite
rag/rg-results.jsonl
rag/vectors.faiss
rag/vector-metadata.json
```

Example `chunks.jsonl` row:

```json
{"chunk_id":"chunk:app/api/users.py:24-41","path":"app/api/users.py","range":{"start_line":24,"end_line":41},"chunk_type":"function","text":"def list_users(...):\n    ..."}
```

## 4. Static analysis graph lane

Purpose: represent code relationships in a standard property-graph style.

Tools/libraries:

- Python AST-derived property graph for Python repos.
- JSONL nodes/edges as the portable graph projection.
- CodeQL, Joern, Tree-sitter, SCIP/LSP only when required for artifact quality.

Artifacts:

```text
static/nodes.jsonl
static/edges.jsonl
```

Node types:

```text
Repository, File, Module, Class, Function, Method, Import, Dependency, Test, ConfigFile, DocSection
```

Edge types:

```text
CONTAINS
IMPORTS
CALLS_APPROX
INHERITS
DECORATED_BY
MENTIONS
TESTS_APPROX
```

Edges should include confidence/provenance when approximate.

## 5. Queries lane

Purpose: capture common deterministic pattern searches without inventing `framework-facts.json`.

Tools/libraries:

- `ripgrep --json` for machine-readable exact/regex results.
- local `grep-ast` for contextual AST-aware/human-readable output.
- Semgrep/ast-grep when reliable structured framework/static-pattern results are needed.

Artifacts:

```text
queries/rules/rg/*.json
queries/results/rg.jsonl
queries/results/grep-ast/*.md
queries/results/semgrep.json
queries/results/semgrep.sarif
queries/results/ast-grep.json
```

Query packs should target common Python repo surfaces:

- FastAPI/Flask/Django route decorators
- Celery/RQ/Dramatiq task decorators
- Click/Typer/argparse command definitions
- SQLAlchemy/Django/Pydantic model patterns
- env var usage
- settings/config keys
- plugin registries/factories
- database/session/cache/storage usage
- auth/security middleware/dependencies

Important: these are query results, not a custom canonical `framework-facts` schema.

## 6. Contracts lane

Purpose: capture framework-native interface contracts where available.

Tools/libraries:

- Static discovery of existing contract files.
- Conservative OpenAPI extraction when the repo exposes it safely.
- No arbitrary server startup by default.

Artifacts:

```text
contracts/openapi.json
contracts/contract-sources.md
```

If contract extraction requires importing app code, do it only in a documented safe mode and record the method in `contracts/contract-sources.md`.

## 7. Tests lane

Purpose: capture test inventory in a known test-runner format.

Tools/libraries:

- `pytest --collect-only -q` for test collection.
- Python file scanning for `test-files.jsonl`.

Artifacts:

```text
tests/pytest-collect.txt
tests/test-files.jsonl
```

Do not run the full test suite in Phase 1 unless explicitly requested.

## 8. Derived lane

Purpose: provide human-readable summaries and a bridge for later DeepWiki phases.

Tools/libraries:

- Deterministic Python summarizer over the above artifacts.

Artifacts:

```text
derived/repo-summary.md
derived/artifact-index.md
```

Do not make `repo-decomposition.json` the canonical product. If later phases need a compact planning packet, create it in Phase 2 or as a derived bridge from these standard artifacts.

## Non-goals

Phase 1 does not:

- call an LLM
- create DocumentPlan
- create SectionPlans
- create EvidencePackets
- generate Wiki prose
- run agentic repo browsing
- perform a healing loop

## Next phase after decomposition

After this Phase 1 tool, the next planned work proceeds in **two phases**:

```text
Phase 1: Decomposition artifact bundle
Phase 2: LLM planning via API -> DocumentPlan + SectionPlans
```

Phase 2 should use an LLM API, not an interactive agent browsing the repo. The API call should consume the Phase 1 artifact bundle and produce planning artifacts only.

Planned Phase 2 API provider:

```text
Provider: Moonshot / Kimi
Model: Kimi K2.5
Credential: MOONSHOT_API_KEY environment variable
Mode: streaming API output, following Moonshot/Kimi streaming guidance
```

Phase 2 should read `MOONSHOT_API_KEY` from the environment. Do not hard-code the key in files, prompts, logs, or generated artifacts.

Phase 2 should support streaming output so long planning responses can be written incrementally to disk. The streamed response should be assembled into validated final artifacts:

```text
plans/document-plan.json
plans/document-plan.md
plans/section-plans.jsonl
```

The implementation should keep the API call bounded: no tool browsing, no live repo file reads by the LLM, and no web search unless explicitly added as a separate, documented capability. The API input should come from the Phase 1 artifact bundle.

Reference for implementation: Moonshot/Kimi API streaming docs, including the guide at `https://platform.kimi.ai/docs/guide/utilize-the-streaming-output-feature-of-kimi-api`.

Phase 2 input is the Phase 1 artifact bundle, especially:

```text
ARTIFACT_GUIDE.md
derived/repo-summary.md
derived/artifact-index.md
inventory/source-coverage.json
symbols/symbols.jsonl
rag/chunks.jsonl
static/nodes.jsonl
static/edges.jsonl
queries/results/rg.jsonl
queries/results/grep-ast/*.md
contracts/openapi.json
tests/pytest-collect.txt
```

Phase 2 API output should be:

```text
plans/document-plan.json
plans/document-plan.md
plans/section-plans.jsonl
```

The planner's job is not to write the Wiki yet. It should decide:

- what pages/sections the Wiki should contain
- what each section must explain
- which artifact families likely support each section
- which routes, CLIs, workers, models, configs, tests, docs, and workflows must be covered
- what evidence will need to be retrieved in Phase 3

Immediate implementation flow:

```text
Phase 1: Decomposition artifact bundle
Phase 2: LLM planning API -> DocumentPlan + SectionPlans
```

Later document-generation flow, after these two phases are working:

```text
Phase 3: deterministic retrieval -> EvidencePackets
Phase 4: LLM writing -> GeneratedSections + final Wiki
```
