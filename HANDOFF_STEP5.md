# Handoff — Phase 1 Step 5: `build-retrieval`

Branch: `feat/phase1-step5-build-retrieval` · Commit: `f4db835` · Pushed to `origin`.

## 1. Problem and context

Implement **Phase 1 Step 5** of the wiki-generator pipeline per
`PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md`: a `build-retrieval` command that
builds the **retrieval substrate** Phase 3 will query section-by-section.

It verifies/rebuilds the BM25 index over the Step 1 corpus, optionally builds
local vectors, and writes a machine-readable capability contract plus a
human-readable readiness report. It is **deterministic and LLM-free** — no
network, no API keys, no EvidencePackets/Wiki prose (those belong to Phase 3).

Constraints / decisions:
- **Deep modules + single source of truth** (per the requested design discipline).
  The FTS5 BM25 schema and the model2vec→FAISS vector mechanism each now live in
  exactly one place; `lanes/rag.py` (decompose) **delegates** to them, so the two
  producers cannot drift.
- **Vector libs are optional and injected.** The faiss/numpy/model2vec backend is
  behind a `VectorBackend` Protocol, imported lazily — the whole build/skip/fail
  path is testable without faiss installed (it is not installed in this env).
- `--vectors auto` skips with an exact reason; `--vectors on`
  (alias `--fail-without-vectors`) exits non-zero if vectors can't be built or the
  vector/metadata counts diverge.
- Reruns on the same corpus are byte-identical (capabilities.json + report).

## 2. Approach and work completed

Read the spec + existing code, implemented the package, ran an **adversarial
review workflow** (5 dimensions, each finding independently verified): 22 raw →
19 confirmed findings, **all fixed**; a second **verification workflow** confirmed
every fix `fixed_correct` with no regressions. The biggest fix was unifying
decompose's inline vector lane with the shared Step 5 module (mirroring the BM25
refactor) to kill schema/embed-text/ordering drift.

**Files created: 10. Files modified: 6** (plus the spec was added to git).

Created — `src/wiki_generator/libs/retrieval/` (deep modules):
- `__init__.py` — `run(options)` facade: orchestrates + decides PASS/FAIL.
- `options.py` — `BuildOptions` frozen contract (validated).
- `loader.py` — load corpus + probe optional surfaces; validates chunks (raises
  `MissingCorpusError` on missing keys / duplicate `chunk_id`).
- `fingerprints.py` — deterministic corpus fingerprint for stale detection.
- `bm25.py` — **single owner** of the FTS5 schema + `build_index` /
  `ensure_index` (build/verify/rebuild) + deterministic `search`.
- `vectors.py` — auto/on/off policy + `VectorBackend` Protocol +
  `FaissModel2VecBackend` (atomic write, orphan cleanup, count verification).
- `capabilities.py` — `retrieval-capabilities.json` (schema `retrieval-substrate-v1`).
- `report.py` — `retrieval-substrate-report.md` + `vector-build-report.md`.
- `smoke.py` — optional `--smoke-query` top-k probe.
- `src/wiki_generator/libs/commands/build_retrieval.py` — CLI wrapper (exit 0/1/2).

Modified:
- `src/wiki_generator/cli.py` — `build-retrieval` subparser + dispatch.
- `src/wiki_generator/libs/paths.py` — Step 5 output path properties.
- `src/wiki_generator/libs/lanes/rag.py` — delegate BM25 **and** vectors to
  `libs/retrieval` (no duplicated schema/mechanism).
- `tests/test_phase1.py` — 28 new tests (58 → 86).
- `README.md`, `RUNBOOK.md` — Step 5 section, outputs, flags, pipeline diagram.

Outputs written into `<bundle>/rag/`: `retrieval-capabilities.json`,
`retrieval-substrate-report.md`, `vector-build-report.md`, and (when vectors are
built) `vectors.faiss` + `vector-metadata.json[l]`, and (with `--smoke-query`)
`retrieval-smoke-tests.jsonl`.

## 3. Suggested review

Read in this order: `PHASE1_STEP5_RETRIEVAL_SUBSTRATE_SPEC.md` →
`libs/retrieval/__init__.py` (the facade shows the whole flow) → `bm25.py` and
`vectors.py` (the two seams) → the `lanes/rag.py` diff (delegation).

Validate locally:
```bash
cd /Users/ankitsingh/Documents/deep-wiki/10-porting/wiki-generator
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
python -m unittest discover -s tests          # expect: OK (86 tests)

# real end-to-end on the existing RAGFlow bundle (lexical-symbolic; no faiss here)
python3 -m wiki_generator build-retrieval \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --smoke-query "authentication and login flow"
# expect: bm25 verified, vectors skipped (reason), retrieval mode lexical-symbolic, PASS (rc 0)
cat /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/rag/retrieval-capabilities.json
```

Deserves extra attention / follow-up:
- **Hybrid (vector) path is untested on real faiss** — this environment has no
  `faiss`/`model2vec`, so vectors are exercised only via a fake backend in tests.
  Before relying on hybrid mode, `pip install -e '.[embeddings]'` and run
  `build-retrieval --in <bundle> --vectors on` on a real bundle; confirm
  `vectors.faiss` + `vector-metadata.json` are written and counts match.
- **Decompose vector parity** — `lanes/rag.py` now emits `vector-metadata-v1`
  (was a different shape). Anything downstream that read the old
  `{built, ids, meta}` shape must move to the v1 contract.
- **Phase 3 reads `rag/retrieval-capabilities.json`** — it is the contract; treat
  `capabilities.vectors` / `retrieval_mode` as authoritative (don't read
  `vectors.faiss` directly without checking it).
