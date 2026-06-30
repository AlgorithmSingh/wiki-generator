# Interfaces & Behavior Contracts — deepwiki-scale-depth-parity

All interfaces are in-process Python functions (no network, no CLI surface change). Every
new parameter is optional and defaults to a value that preserves current behavior.

## `depth_budget.derive_section_depth_budget`

```python
def derive_section_depth_budget(
    *, section_id: str,
    obligations: list | None,               # sufficient required-topic obligations (mapped_evidence_ids)
    content_block_obligations: list | None,  # evidenced content-block obligations (supporting_evidence_ids)
    allowed_evidence_ids: list,
    token_count: int,
    source_handle_count: int,
    policy: DepthPolicy | None = None,
) -> SectionDepthBudget
```

- Considers only obligations with `is_obligation` true (sufficient topics / evidenced
  blocks). Per-topic `min_claims = policy.topic_target(len(distinct mapped_evidence_ids))`.
- `min_section_claims = max(policy.min_section_claims, Σ topic_targets.min_claims)`.
- Empty obligations → a budget with `min_section_claims = policy.min_section_claims` and no
  topic/block targets (no spurious depth pressure).

## `depth_budget.evaluate_plan_depth`

```python
def evaluate_plan_depth(budget: SectionDepthBudget, claims: list) -> PlanDepthReport
```

- `claims` are normalized claim dicts (`required_topic`, `content_block_id`).
- Counts claims per `required_topic` and per `content_block_id` and the total.
- Emits `CODE_TOPIC_UNDERFILLED` when `measured < target.min_claims`; `CODE_SECTION_UNDERFILLED`
  when `total < budget.min_section_claims`. (A content-block depth dimension was descoped per
  repair R6 — content-block coverage stays the downstream generated-coverage gate.)
- `status == "pass"` iff `shortfalls == []`. Read-only; never mutates `claims`.

## `claim_plan.validate_claim_plan(..., depth_budget=None)`

| Condition | Behavior |
|---|---|
| `depth_budget is None` (baseline/enhancement, or non-grounded) | byte-identical to today; no depth check |
| `depth_budget` given, plan meets it | passes (no new violations) |
| `depth_budget` given, plan is shallow | `ok == False`; one violation per under-filled topic/block + a section backstop, each with measured-vs-required detail; in a live run the existing bounded audited re-prompt is offered, else fail-closed (`WritingValidationFailure`, exit 5) |

The depth check runs **after** all existing grounding checks, so a plan that is both
ungrounded and shallow still reports the grounding violations first; depth never masks or
relaxes a grounding violation.

## `claim_plan.build_claim_plan_prompt(..., depth_budget=None)`

- `depth_budget is None` → unchanged prompt bytes.
- given → inserts `render_depth_budget_lines(depth_budget)` after the required-topic block;
  the system instruction gains a rule: "Ground enough claims to meet each required topic's
  source-derived claim target shown below; one grounded claim per mapped evidence id is the
  intended density. Do not pad or repeat — use the evidence already retrieved." No benchmark
  string appears.

## Failure paths

- A shallow grounded plan in expanded mode → depth violations → (≤ `max_rewrite_attempts`
  bounded audited re-prompt, live model only) → if still shallow, fail-closed
  `WritingValidationFailure` (exit 5), with the failure report naming the under-filled
  topics. No output is patched; no plan is mutated.
- A budget over an empty/thin obligation set → no topic targets → cannot fail on depth
  (graceful for overview/provenance sections).
