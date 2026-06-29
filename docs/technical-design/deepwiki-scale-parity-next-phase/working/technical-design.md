# Technical Design (working) — module/symbol plan

This is the module/symbol/test plan the Python agent-sequence planning stages
produce, recorded here (kept out of the repo's `.sequence/` to preserve a clean tree).

## Module plan
| module | layer | responsibility | may_do_io | import-time policy |
|---|---|---|---|---|
| `libs/coverage/anti_compression.py` (new) | domain (coverage gate) | promotion contract + anti-compression breadth/density/TER/hierarchy/floor evaluation + gate + markdown | no | imports + constants + dataclasses + functions only |
| `libs/coverage/validate.py` | domain | add `MODE_DEEPWIKI_SCALE`, `_MODES`/`_ENFORCING_MODES`, `EXPANDED_MODES`, `enforces_breadth`, `is_expanded_family` | no | unchanged shape |
| `libs/coverage/__init__.py` | domain facade | re-export new symbols | no | imports only |
| `libs/commands/normalize_plan.py` | interface/CLI orchestration | run anti-compression gate in deepwiki-scale; write artifacts | yes (writes plan files; CLI layer) | unchanged |
| `cli.py` | interface | add mode to argparse choices | yes (argparse) | unchanged |
| `libs/evidence/options.py`, `libs/writing/options.py` | application config | accept new mode; treat as expanded-family | no | constants/dataclasses only |
| `libs/evidence/evidenced_coverage.py`, `libs/writing/{grounded,packet,generated_coverage}.py` | application | membership checks include new mode | no/yes per existing | unchanged |

## Symbol plan (new module)
- Constants: schema version, failure category, tier strings, status strings, 6 defect
  codes.
- `BreadthPolicy` (frozen dataclass, all explicit-typed fields, no mutable defaults;
  tuple default for `overview_profiles` is immutable → safe) + `DEFAULT_BREADTH_POLICY`.
- `required_leaf_pages(n: int, policy: BreadthPolicy) -> int` (= ceil(n/cap)).
- `classify_promotion(topic: dict, deferred: bool) -> str`.
- Result dataclasses: `PromotedTopic`, `FamilyBreadth`, `AntiCompressionReport`,
  `AntiCompressionGate`, each with `to_dict()`.
- `evaluate_anti_compression(catalog, document_plan, sections, *, mode, policy=None)`.
- `gate_anti_compression(catalog, document_plan, sections, *, mode, policy=None)`.
- `render_anti_compression_markdown(report, *, title=...)`.

## Determinism notes
- Iterate catalog topics in input order; sort `leaf_pages`, `blocking_sections`,
  `families` by id; never serialize a Python `set` directly.
- No clock/random/network; policy injected (default constant instance, immutable).

## Import policy
- `anti_compression.py` may import: `math`, `dataclasses`, `..context_docs`
  (`is_provenance_section`), `.page_profiles`, `.validate` (`MODE_*`,
  `enforces_breadth`, `_MODES`, exit-code constants). It must NOT import commands,
  writing, evidence, or CLI modules.

## Test plan (`tests/test_phase2_anti_compression.py`)
- Promotion contract: family→overview, subsystem→page, should→optional, deferred→known_gap.
- Each defect in isolation: overloaded leaf; missing TER; topic only on overview
  (no leaf page); family not split; flat hierarchy; breadth floor.
- Pass case (fanned, linked, TER per topic) → no diagnostics, exit 0.
- Overview exemption: index page lists many ids but each has its own leaf page+TER → pass.
- Report-only in baseline/expanded direct calls (`enforces_breadth` False).
- Determinism: identical serialized gate dict across two evaluations.
- Integration: `normalize-plan --coverage-mode deepwiki-scale` collapse fails (exit 3,
  artifact written); fan passes; enhancement/expanded do not write the artifact.
- Option coherence: `EvidenceOptions`/`WritingOptions` accept the new mode.
