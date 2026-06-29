# Problem & Success — DeepWiki Scale-Parity (Anti-Compression)

## Context / current state
The `expanded` coverage mode (deepwiki-coverage-expansion wave) added the full
hierarchical/profile/evidence mechanism and passes the real non-live RAGFlow GPT-5.4
E2E. But the real run compressed a 147-topic / 94-`must` / 13-family catalog into 21
flat pages and 42 TERs.

## Problem statement
`page_planning._eval_catalog_coverage` treats a catalog topic as "planned" if its id
appears in any page's `catalog_topic_ids[]`. There is no density ceiling, no
distributive TER obligation, no required hierarchy, and no catalog-derived breadth
floor. A broad page can absorb a whole family's high-signal topics for free, so a
high-signal catalog passes as a tiny flat plan. This is the exact anti-compression
loophole.

## Scope / non-scope
- **In (Slice 1)**: opt-in `deepwiki-scale` mode; deterministic Phase 2 promotion
  contract + anti-compression gate; `promoted_topics[]` data contract; CLI wiring;
  tests.
- **In (later)**: promoted-topic granularity in source-selection, evidence, generated
  coverage (VG-13).
- **Out**: longer prose, benchmark-copied structure, Phase 3 determinism changes,
  output patching, live billed runs.

## Goals → success
- A 94-`must`/13-family collapse into 21 flat pages / 42 TERs **fails** before Phase 3.
- The same catalog fanned into linked, evidence-obligated leaf pages **passes**.
- Existing modes and validators are byte-for-byte unchanged.

## Definition of done
See `definition-of-done.json` (DOD-1…DOD-10), derived from this problem, the readers
(operator + maintainers + future agent), the constraints (Python HARD-RULES, protected
spec, non-live), and the risks (over-strict thresholds, family-heavy catalogs,
benchmark leakage).
