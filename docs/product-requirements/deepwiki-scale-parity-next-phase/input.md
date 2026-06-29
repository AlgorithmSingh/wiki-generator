# Original User Request

Create a NEW next-phase PRD for closing the remaining DeepWiki-scale/parity gap in
the wiki-generator pipeline.

The existing `expanded` coverage mode works mechanically but is not DeepWiki-scale.
The real non-live RAGFlow GPT-5.4-low E2E run
(`20260629-152217-real-ragflow-gpt54-expanded-681b900-ragflow-3f805a64f`) PASSED all
eight gates yet produced a wiki that is far below benchmark breadth:

- Generated: 21 sections, ~17,554 words, 66 headings, 42/42 required topics,
  38/38 content blocks, 490 distinct citations.
- Benchmark comparator (comparison-only, never source truth): ~98,271 words,
  ~899 headings, ~74 page-like headings.

Most important diagnostic: the source-derived topic catalog had 147 topics, 94 of
them high-signal/`must`. The page-planning gate counted all 94 as "planned", but
Phase 2 compressed them into only 21 pages and 42 topic-evidence requirements
(TERs). Whole families collapsed 1:1 into a single page:

- `frontend`: 13 catalog topics → 1 page
- `go-native`: 13 → 1
- `sandbox-executor`: 13 → 1
- `doc-processing`: 13 → 1
- `auth-admin-health` (`user-tenant-admin-health`): 13 → 1

The plan was effectively flat: `parent_section_id` was null for every page.

The loophole: "`catalog_topic_id` is listed on a page" was treated as sufficient
planning coverage. It did not require that topic to become its own page/subpage, its
own required topic, its own TER, its own evidence obligation, and its own generated
coverage row.

The previous PRD/TDD were conceptually correct but under-enforced breadth:
- M-07 named a 45–70 page / 150–250 topic target band, but it was not a hard gate.
- OD-02/OD-03 promotion thresholds and target counts were left open.
- No max high-signal catalog topics per page.
- No minimum child-page count for high-signal families.
- No requirement of one TER per high-signal catalog topic.
- Generated coverage was by required topic / content block, not by every promoted
  catalog topic.
- A broad page could list many catalog ids and still pass.

Objective: define the next phase that turns expanded mode from "mechanism exists"
into "DeepWiki-scale breadth is actually enforced" — by hardening Phase 1/2 planning,
source-selection, evidence, and generated-coverage contracts so large source-derived
catalogs cannot collapse into 21 flat pages. This is NOT about writing longer
sections; it is about a stricter source-derived breadth mode/gate set.

Constraints: remain benchmark-safe (the DeepWiki export is a comparator only, never
copied structure/prose/evidence); preserve all strict validators; keep Phase 3
deterministic; no output patching; bounded repair only for LLM-authored plan/claim
artifacts; keep the non-live GPT-5.4-low worker path as the mandatory pre-live
validation method; no live/billed Vertex/Gemini calls without explicit approval.

This is the NEXT PHASE of, not a replacement for, the deepwiki-coverage-expansion
PRD/TDD, which must be preserved unchanged.
