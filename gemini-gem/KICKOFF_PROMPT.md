# Kickoff prompt

Send this as your first message in the Gem chat, with the Phase 1 upload attached
(see `UPLOAD_LIST.md`) — normally the single file `planner-upload-bundle.md`. If
you put the instructions in the Gem config, you can send just this.

---

You are planning the DeepWiki for the repository summarized in the attached Phase 1
decomposition digest. The repo is **RAGFlow**.

Work only from the attached upload — normally one file, `planner-upload-bundle.md`,
which concatenates the digest set with `<!-- BEGIN/END INCLUDED FILE: <path> -->`
markers. Read its sections in this order: `planning-handles.md`,
`planning-digest.md`, `planning-symbols.md`, `planning-graph.md`,
`planning-runtime-surfaces.md`, `planning-tests.md`, `planning-gaps.md`, then the
supporting bundle files. `planning-handles.md` holds the exact handles to copy
into exact lanes.

Produce exactly three artifacts, each in its own fenced code block labeled with its
filename:

1. `plans/document-plan.json` — the Wiki structure (sections, order, purpose,
   rationale, priority).
2. `plans/document-plan.md` — the same plan as a readable outline.
3. `plans/section-plans.jsonl` — one JSON object per line, one per section, with
   coverage requirements, key questions, evidence needs (exact symbol ids / file
   anchors / canonical query packs / exact graph node ids / `METHOD /path`
   contracts / tests / search_hints / context_artifacts), dependencies,
   verification needs, and estimated size.

Constraints (repeat of the Gem rules, in case they aren't loaded):
- You are producing a retrieval **work order**, not final Wiki prose.
- Do **not** write the Wiki content. Plans only.
- Do **not** invent evidence.
- **Use exact handles when filling exact retrieval lanes.** Take them from
  `planning-handles.md`.
- **If you cannot name an exact handle, do not place the item in that exact lane.**
  Move broad or fuzzy retrieval requests into `search_hints[]`.
- **Move planning digest/condensate documents into `context_artifacts[]`.** They
  are never citeable evidence.
- Lane rules: `symbol_ids[]` exact `symbol_id` only; `file_anchors[]` real repo
  paths only (never `derived/planning-*.md`); `contracts[]` exact `METHOD /path`
  only (`contracts/openapi.json` alone is not a contract); `graph_nodes[]` exact
  `node_id` only (never a display label like `pytest [Dependency]`);
  `query_packs[]` canonical keys only.
- Treat `CALLS_APPROX` edges, lexical query hits, the derived OpenAPI contract, and
  the static-only test scan as approximate — any section relying on them must list a
  `verification_needs` entry.
- `section-plans.jsonl` must be 1:1 with the sections in `document-plan.json`
  (`section_id` must match a `document-plan.json` `id` exactly). Use stable
  lowercase kebab-case ids. Canonical `query_packs` keys: `web_routes`,
  `task_workers`, `cli_commands`, `models_schemas`, `config_keys`,
  `config_file_keys`, `env_vars`, `auth_security`, `datastore`, `llm_integrations`,
  `entrypoints`, `plugin_registries`.

Begin by listing the major runtime surfaces and subsystems you see in the digest,
then produce the three artifacts.
