# Runbook — generate a DeepWiki plan for any repo

End-to-end commands for the full pipeline. Phase 1 is deterministic and LLM-free;
Phase 2 Step 1 is the only LLM call (a Gemini/Kimi Gem) and happens outside this
tool; Phase 2 Step 2 (`normalize-plan`) is deterministic again.

```
Phase 1  Step 1 decompose   -> raw artifact bundle
         Step 2 condense     -> derived/planning-*.md condensates
         Step 3 digest       -> derived/planning-digest.md (also runs Step 4)
         Step 4 bundle       -> planner-digest/planner-upload-bundle.md (one upload)
Phase 2  Step 1 (external)   -> Gemini/Kimi plan -> plans/phase2-<provider>-response.md
         Step 2 normalize-plan -> plans/document-plan.json + section-plans.jsonl
Phase 3  (later)             -> deterministic section evidence retrieval
```

## 0. Setup (once)

Requires Python 3.11+ (`python3`), plus PyYAML + packaging. `git` and `ripgrep`
(`rg`) on PATH are recommended; everything else degrades gracefully.

```bash
cd /path/to/wiki-generator           # this tool's directory
python3 -m venv .venv
.venv/bin/pip install -e .           # or: pip install pyyaml packaging
python3 -m unittest discover -s tests   # optional sanity check (expect: OK)
```

You can run with a plain `python3` (stdlib only) if you don't want a venv.

## 1. Pick the repo and an output directory

```bash
REPO=/absolute/path/to/the/repo/to/document
OUT=/absolute/path/to/output/bundle        # created if missing
```

## 2. Phase 1 — decompose, condense, digest, bundle

```bash
# Step 1 — raw artifact bundle (inventory, symbols, RAG/BM25, static graph,
#          queries, contracts, tests, derived summaries). No LLM.
python3 -m phase1_decomposition decompose --repo "$REPO" --out "$OUT"

# Step 2 — planner-facing condensates into <OUT>/derived/
python3 -m phase1_decomposition condense --in "$OUT" --budget-tokens 250000

# Step 3 — derived/planning-digest.md (this also runs Step 4 by default)
python3 -m phase1_decomposition digest --in "$OUT" --budget-tokens 250000

# Step 4 — the single upload file (idempotent; only needed if you ran digest
#          with --no-bundle, or want to rebuild it on its own)
python3 -m phase1_decomposition bundle --in "$OUT" --budget-tokens 250000
```

Result to upload: **`$OUT/planner-digest/planner-upload-bundle.md`**
(per-file token table: `$OUT/planner-digest/upload-list.md`).

## 3. Phase 2 Step 1 — run the planning Gem (external, the only LLM step)

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
python3 -m phase1_decomposition normalize-plan \
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

---

## Appendix — exact commands used for RAGFlow

```bash
cd /Users/ankitsingh/Documents/deep-wiki/7-phase1-decomposition-2

python3 -m phase1_decomposition decompose \
  --repo /Users/ankitsingh/Documents/deep-wiki/6-repo-analysis-packet-test/ragflow \
  --out  /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2

python3 -m phase1_decomposition condense \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

python3 -m phase1_decomposition digest \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

python3 -m phase1_decomposition bundle \
  --in /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 --budget-tokens 250000

# (upload planner-digest/planner-upload-bundle.md to the Gem, save reply to
#  plans/phase2-gemini-response.md, then:)

python3 -m phase1_decomposition normalize-plan \
  --bundle       /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2 \
  --raw-response /Users/ankitsingh/Documents/deep-wiki/8-phase1-decomposition-diy-test2/plans/phase2-gemini-response.md
```

RAGFlow scale (reference): 3,928 files, 15,618 symbols, 52,349 graph edges,
22,429 chunks; upload bundle ~109K tokens; plan = 13 sections.
