# Kickoff prompt

Send this as your first message in the Gem chat, with the Phase 1 upload attached
(see `UPLOAD_LIST.md`) — normally the single file `planner-upload-bundle.md`. If
you put the instructions in the Gem config, you can send just this.

---

You are planning the DeepWiki for the repository summarized in the attached Phase 1
decomposition digest. The repo is **RAGFlow**.

Work only from the attached upload — normally one file, `planner-upload-bundle.md`,
which concatenates the digest set with `<!-- BEGIN/END INCLUDED FILE: <path> -->`
markers. Read its sections in this order: `planning-digest.md`,
`planning-symbols.md`, `planning-graph.md`, `planning-runtime-surfaces.md`,
`planning-tests.md`, `planning-gaps.md`, then the supporting bundle files.

Produce exactly three artifacts, each in its own fenced code block labeled with its
filename:

1. `plans/document-plan.json` — the Wiki structure (sections, order, purpose,
   rationale, priority).
2. `plans/document-plan.md` — the same plan as a readable outline.
3. `plans/section-plans.jsonl` — one JSON object per line, one per section, with
   coverage requirements, key questions, evidence needs (symbol ids / file anchors
   / query packs / graph nodes / contract paths), dependencies, verification needs,
   and estimated size.

Constraints (repeat of the Gem rules, in case they aren't loaded):
- Do **not** write the Wiki content. Plans only.
- Do **not** invent evidence. Cite only signals that appear in the digest; when an
  exact id isn't present, write `retrieve: <query>` instead of guessing.
- Treat `CALLS_APPROX` edges, lexical query hits, the derived OpenAPI contract, and
  the static-only test scan as approximate — any section relying on them must list a
  `verification_needs` entry.
- `section-plans.jsonl` must be 1:1 with the sections in `document-plan.json`
  (`section_id` must match a `document-plan.json` `id` exactly).
- Your output is consumed by a deterministic, LLM-free normalizer. Use stable
  lowercase kebab-case ids; prefer canonical `query_packs` keys (`web_routes`,
  `task_workers`, `cli_commands`, `models_schemas`, `config_keys`,
  `config_file_keys`, `env_vars`, `auth_security`, `datastore`, `llm_integrations`,
  `entrypoints`, `plugin_registries`); prefer real SCIP/dotted symbol ids and
  `path:start-end` file anchors so references resolve without guessing.

Begin by listing the major runtime surfaces and subsystems you see in the digest,
then produce the three artifacts.
