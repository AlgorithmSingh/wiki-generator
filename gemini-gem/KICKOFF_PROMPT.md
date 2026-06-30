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
- Lane rules: `symbol_ids[]` exact `symbol_id` only; `file_anchors[]` exact repo
  **files** only — never a directory or trailing-slash path (`agent/component/`,
  `rag/graphrag/` are INVALID; use `agent/component/base.py` or a `search_hints[]`
  entry) and never `derived/planning-*.md`; `contracts[]` exact `METHOD /path` only
  (`contracts/openapi.json` alone is not a contract); `graph_nodes[]` exact
  `node_id` only (never a display label like `pytest [Dependency]`);
  `query_packs[]` canonical keys only.
- **Valid JSONL is mandatory.** Every `section-plans.jsonl` line is exactly one
  complete JSON object — no bare strings, no comments, no Markdown, no prose
  between or inside objects. Every sentence belongs to a named field: verification
  work in `verification_needs[]`, uncertainty in `known_gaps[]`. One-shot:
  - BAD:  `{"section_id":"llm-integration","verification_needs":[],"Lexical query hits need verification.","estimated_size":"M"}`
  - GOOD: `{"section_id":"llm-integration","verification_needs":["Lexical query hits need verification."],"known_gaps":[],"estimated_size":"M"}`
- `planning-gaps.md` is internal planning/provenance context, not source evidence.
  Do **not** create a "Known gaps / unverified" section from it; attach uncertainty
  to the affected real sections via `verification_needs[]`. Every normal section
  needs real retrieval signals.
- **DeepWiki coverage enhancement.** Plan a broad, hierarchical guide. Where the
  digest has real signal, give each mandatory topic family its own page (or child
  page under a subsystem) and tag it with a canonical `coverage_labels[]` value:
  `frontend`, `memory`, `queue-system`, `helm-k8s`, `ci-cd-build`, `go-native`,
  `retrieval-internals`, `doc-processing`, `llm-internals`,
  `user-tenant-admin-health`, `sandbox-executor`, `migrations-operations`,
  `glossary`. Use `parent_section_id` for child pages. A broad parent page does
  **not** cover a deep child topic unless that child has its own page, label, and
  evidence. Do not invent a family the digest shows no signal for — note its absence
  in `known_gaps[]`. `planning-coverage-signals.md` maps where each family likely
  lives (candidate paths, present/low/missing status, suggested
  `coverage_labels[]`/`search_hints[]`); read it to decide which families deserve a
  page. It is **planner context only, never citeable evidence** — do not put its
  candidate paths in an exact `file_anchors[]` lane; cite exact handles from
  `planning-handles.md` instead. A coverage-enhanced run gates the normalized plan
  against all thirteen mandatory families before Phase 3, so omitting a supported
  family fails loudly — plan the page.
- **Fan out, do not compress (core expanded scale behavior).** `planning-topic-catalog.md`
  lists each family's high-signal **subsystem** topics and a **source-derived breadth
  budget** (target page range, target required-topic count, per-family fan-out floor)
  computed only from this repo's catalog — hit it. Use parent/index pages
  (`page_profile` `overview`/`architecture-flow`) plus **leaf** subsystem pages; a
  leaf page carries at most ~4 promoted `catalog_topic_ids[]`; split a dense family
  across multiple child pages via `parent_section_id`; give **each** promoted (`must`)
  subsystem catalog topic its own leaf page, its own `required_topics[]` entry, and its
  own `catalog_topic_id`-keyed `topic_evidence_requirements[]`. A broad page that only
  **lists** a family's subsystem `catalog_topic_ids[]` does **not** count as leaf
  coverage. A deterministic **anti-compression gate fails a compressed plan before
  Phase 3** (no own leaf page/TER per promoted topic, overloaded leaf page, unsplit
  large family, flat plan, or too few leaf pages vs the catalog floor).
- **Required-topic evidence.** The normalizer merges `coverage_requirements[]` and
  `required_topics[]` into one normalized required-topics list, so for **every entry
  in BOTH fields** add a matching `topic_evidence_requirements[]` object `{topic,
  required:true, source_fields[], min_items, acceptable_lanes[]}` whose
  `source_fields[]` name the exact `retrieval_needs.*` lanes (by index, e.g.
  `retrieval_needs.symbols[0]`, `retrieval_needs.files[1]`,
  `retrieval_needs.contracts[0]`, `retrieval_needs.tests[0]`,
  `retrieval_needs.query_packs[0]`) that ground the topic, with `acceptable_lanes[]`
  including at least one exact lane **and the lane of every exact source field**
  (a `files[]` field needs `file_anchor`, `tests[]` needs `test`, etc. — pointing at
  `retrieval_needs.tests[0]` while `acceptable_lanes` is `["file_anchor"]` is a
  lane/type mismatch the gate rejects). Each exact file/test source field must also be
  **citeable** — resolve to a file with real chunk coverage; a path that exists but has
  no extracted content (a tiny `go.mod`, a `Dockerfile` with no chunks) yields no
  citeable evidence, so ground the topic on a file with real content (`build.sh`,
  `docs/develop/build_docker_image.mdx`, `README.md`) instead. Plain JSON, not a query.
  Prefer the canonical `retrieval_needs.*` names; raw `evidence_needs.*` aliases are
  accepted only as compatibility input that Phase 2 canonicalizes when the exact raw
  handle resolves, so never name a raw handle you did not also place in
  `evidence_needs`. A deterministic **Phase 2 gate fails before Phase 3** if any merged
  required topic lacks a matching object, references a `retrieval_needs` lane that does
  not exist, points at an exact lane not in its `acceptable_lanes[]`, resolves to a file
  the substrate cannot cite, or is grounded only on broad recall; Phase 3 then maps
  required topics to citeable evidence and broad recall is never sufficient. A topic
  with weak/missing exact evidence fails **before Phase 4**, so only require what you
  can ground with exact, lane-matched, citeable handles, and record unavoidable gaps in
  `known_gaps[]`.
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
