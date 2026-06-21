# Files to upload to the Gem

Bundle: `/Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2`

Build/refresh the upload with **Step 4**:

```bash
cd /Users/ankitsingh/Documents/deep-wiki/7-phase1-decomposition-2
python3 -m wiki_generator bundle \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --budget-tokens 250000
```

## Easiest: upload ONE file

```
8-phase1-decomposition-diy-test2/planner-digest/planner-upload-bundle.md
```

This single file concatenates the whole digest set (README + the six condensates +
supporting artifacts), each part wrapped in
`<!-- BEGIN INCLUDED FILE: <path> --> … <!-- END INCLUDED FILE: <path> -->` markers.
For the RAGFlow bundle it is ~109K estimated tokens — within the 250K budget. The
exact per-file token table is in `planner-digest/upload-list.md`.

## Or upload the individual files (same content, in bundle order)

```
8-phase1-decomposition-diy-test2/planner-digest/README_FOR_PLANNER.md
8-phase1-decomposition-diy-test2/planner-digest/planning-digest.md
8-phase1-decomposition-diy-test2/planner-digest/planning-symbols.md
8-phase1-decomposition-diy-test2/planner-digest/planning-graph.md
8-phase1-decomposition-diy-test2/planner-digest/planning-runtime-surfaces.md
8-phase1-decomposition-diy-test2/planner-digest/planning-tests.md
8-phase1-decomposition-diy-test2/planner-digest/planning-gaps.md
8-phase1-decomposition-diy-test2/ARTIFACT_GUIDE.md
8-phase1-decomposition-diy-test2/derived/repo-summary.md
8-phase1-decomposition-diy-test2/derived/artifact-index.md
8-phase1-decomposition-diy-test2/inventory/source-coverage.json
8-phase1-decomposition-diy-test2/contracts/contract-sources.md
8-phase1-decomposition-diy-test2/contracts/openapi.json
8-phase1-decomposition-diy-test2/tests/pytest-collect.txt
8-phase1-decomposition-diy-test2/tests/test-files.jsonl
```

## Do NOT upload (raw backend indexes — kept for Phase 3 retrieval)

```
symbols/symbols.jsonl
symbols/imports.jsonl
symbols/occurrences.jsonl
static/nodes.jsonl
static/edges.jsonl
rag/chunks.jsonl
rag/spans.jsonl
rag/bm25.sqlite
rag/vectors.faiss
rag/vector-metadata.json
queries/results/rg.jsonl
```

## After the Gem responds

Save the raw response to
`8-phase1-decomposition-diy-test2/plans/phase2-gemini-response.md`, then normalize
it deterministically (no LLM) into machine-resolvable plan artifacts:

```bash
python3 -m wiki_generator normalize-plan \
  --bundle /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --raw-response /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/plans/phase2-gemini-response.md
```
