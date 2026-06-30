# Component / Module Design — deepwiki-scale-depth-parity

## New: `libs/writing/depth_budget.py` *(inferred; deterministic, pure)*

> **Implementation note (repair R6):** the content-block depth dimension below was descoped
> during the build because it preempted the existing generated-coverage content-block gate.
> The shipped gate enforces **per-topic claim density + a section floor only**; content-block
> *coverage* stays the downstream generated-coverage gate's job. `BlockDepthTarget`,
> `CODE_BLOCK_UNDERFILLED`, and `DepthPolicy.min_claims_per_content_block` were removed;
> `content_block_obligations` now feeds only an informational count. The text below is the
> original design intent.

Mirrors `libs/coverage/anti_compression.py` (policy + budget + gate + render).

### Constants

- `DEPTH_BUDGET_SCHEMA_VERSION = "phase4-depth-budget-v1"`
- Defect codes (one per distinct, actionable shortfall):
  - `CODE_TOPIC_UNDERFILLED = "required_topic_underfilled_for_mapped_evidence"`
  - `CODE_BLOCK_UNDERFILLED = "content_block_underfilled_for_mapped_evidence"`
  - `CODE_SECTION_UNDERFILLED = "section_claim_density_below_source_floor"`

### Policy (dependency injection; frozen; validated bounds)

```python
@dataclass(frozen=True)
class DepthPolicy:
    evidence_per_claim: int = 1               # source density: ~1 grounded claim per mapped evidence id
    min_claims_per_required_topic: int = 1    # absolute floor (a thin 1-evidence topic stays satisfiable)
    max_claims_per_required_topic: int = 8    # bound so a richly-mapped topic cannot demand unboundedly
    min_claims_per_content_block: int = 1     # each evidenced content block must ground >= this many linked claims
    min_section_claims: int = 1               # backstop floor for a content section
    def __post_init__(self): ...              # every field >= 1 (>= 0 for min_section_claims) else ValueError
    def topic_target(self, mapped_count: int) -> int:
        # clamp(ceil(mapped_count / evidence_per_claim), min_per_topic, max_per_topic)
    def to_dict(self) -> dict: ...
DEFAULT_DEPTH_POLICY = DepthPolicy()
```

`topic_target` is the **only** place the per-topic number is computed, so planner guidance
(prompt) and gate enforcement (validator) derive identically — the same discipline the
breadth budget/gate use.

### Result model (each `to_dict()`)

- `TopicDepthTarget(topic, mapped_evidence_count, min_claims)` — per sufficient required
  topic obligation.
- `BlockDepthTarget(content_block_id, supporting_evidence_count, min_claims)` — per
  evidenced content-block obligation.
- `SectionDepthBudget(schema_version, policy, section_id, topic_targets[], block_targets[],
  min_section_claims, counts{required_topics, content_blocks, allowed_evidence, token_count,
  source_handles})`.
- `DepthShortfall(scope, id, code, measured, required, detail, remediation)` and
  `PlanDepthReport(section_id, status, shortfalls[], measured{...})`.

### Public API (explicit typing; keyword-only policy)

- `derive_section_depth_budget(*, section_id, obligations, content_block_obligations,
  allowed_evidence_ids, token_count, source_handle_count, policy=None) -> SectionDepthBudget`
  — builds per-topic/per-block targets from the **sufficient** obligations only; a thin
  catalog yields small targets; an empty obligation set yields a budget with `min_section_claims`
  from the policy floor and no topic/block targets.
- `evaluate_plan_depth(budget, claims) -> PlanDepthReport` — deterministic, read-only.
  Counts claims by `required_topic` and by `content_block_id` and total, compares against
  the budget, emits one shortfall per under-filled topic/block and a section backstop.
- `render_depth_budget_lines(budget) -> list[str]` — markdown guidance for the prompt
  (per-topic claim targets + the section floor + the source-derived rationale). Returns
  `[]` when there is nothing to plan for.

### Boundaries

Pure and deterministic: no model call, no file read, no mutation of inputs, no benchmark
read. Sorted iteration over topics/blocks for byte-stable output.

## Changed: `libs/writing/claim_plan.py` *(sourced seam)*

- `validate_claim_plan(..., depth_budget=None)`: after the existing checks, when
  `depth_budget is not None`, call `depth_budget_mod.evaluate_plan_depth(depth_budget,
  norm_claims)` and append its shortfalls as violations (codes above). `ok = not violations`
  still holds, so a shallow plan fails. When `depth_budget is None`, output is byte-identical
  to today.
- `build_claim_plan_prompt(..., depth_budget=None)` / `build_claim_plan_rewrite_prompt(...,
  depth_budget=None)`: insert `render_depth_budget_lines(depth_budget)` after the required-topic
  lines; harden `CLAIM_PLAN_SYSTEM_INSTRUCTION` with a "ground enough claims for the evidence"
  rule. No change when `depth_budget is None`.

## Changed: `libs/writing/grounded.py` *(sourced seam)*

- `generate_grounded_section(..., depth_budget=None)`: pass `depth_budget` to both
  `validate_claim_plan` calls and to `build_claim_plan_rewrite_prompt`; add a `depth` field
  to `grounded_meta` (the budget summary + measured per-topic/total claim counts via
  `evaluate_plan_depth(...).measured`).

## Changed: `libs/writing/__init__.py` *(sourced seam)*

- In `run()`, for the expanded grounded path, compute `depth_budgets[sid]` with
  `derive_section_depth_budget(...)` (token bank size from `token_banks[sid]`, source handles
  from the packet), use it when building the grounded prompt, and pass it into
  `generate_grounded_section`. Non-expanded or non-grounded runs compute nothing.

## Explicitly NOT changed this slice

`render_section` / `_render_claim_paragraph` / `_derive_covered_content_blocks` and the
generated-coverage evaluators are untouched: more claims already render as more paragraphs.
Content-block `####` heading rendering (heading-density depth) is deferred to M2 to avoid
touching the content-block-coverage grounding evaluator in the same slice.
