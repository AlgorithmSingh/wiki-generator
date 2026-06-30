# Architecture Overview — deepwiki-scale-depth-parity

No new services. The change is localized to the Phase 4 grounded writing path. A new
deterministic module sits beside the existing claim-plan machinery and is orchestrated by
the per-section grounded loop, exactly mirroring how the Phase 2 anti-compression gate sits
beside page-planning and is orchestrated by `normalize-plan`.

```
write-wiki --coverage-mode expanded --grounded-claim-plan
        │
        ▼  libs/writing/__init__.py: run()
  build_writing_packet(sid)            (allowed_evidence_ids, required_topics_coverage,
        │                               content_block_coverage, relevant_source_handles)
  build_token_bank(sid)
  section_obligations(sid)             (sufficient required topics + mapped_evidence_ids)
  section_block_obligations(sid)       (content blocks + supporting_evidence_ids)
        │
        ▼  NEW (expanded grounded only)
  depth_budget = depth_budget.derive_section_depth_budget(
        obligations, block_obligations, allowed_evidence_ids,
        token_count, source_handle_count, policy=DEFAULT_DEPTH_POLICY)
        │
        ├─ build_claim_plan_prompt(..., depth_budget)      ◀ prompt carries depth guidance
        ▼
  libs/writing/grounded.py: generate_grounded_section(..., depth_budget)
        │  provider.generate -> claim plan (LLM)
        ▼
  claim_plan.validate_claim_plan(..., depth_budget)        ◀ NEW depth gate (additive)
        │     existing grounding checks  +  depth.evaluate_plan_depth(budget, claims)
        ├─ shallow plan  -> violations -> (bounded audited re-prompt if live) -> fail-closed
        ▼  pass
  render_section(...)                                       (unchanged this slice)
  validate_section_draft(...)                               (strict validator, unchanged)
  grounded_meta["depth"] = budget + measured claim counts   ◀ NEW audit metric
```

## Module dependency direction *(layered, HARD-RULES C6)*

- `libs/writing/depth_budget.py` (new) depends only on stdlib (`math`, `dataclasses`) —
  pure, no I/O, no model, no import-time work. It does **not** import `claim_plan`,
  `grounded`, commands, or the comparator.
- `libs/writing/claim_plan.py` imports `depth_budget` (a leaf module) for the optional gate.
- `libs/writing/grounded.py` and `libs/writing/__init__.py` import `depth_budget` to derive
  the per-section budget and thread it through.
- No new dependency points from `coverage`/`evidence`/`commands` into `writing`.

## Why mirror the Phase 2 anti-compression module

The prior phase proved the shape works: an injectable frozen policy, a source-derived
budget the planner is shown, a deterministic gate that fails closed with actionable
remediation, and a downstream contract — all benchmark-quarantined. Depth is the
distributive-density analogue of breadth, so reusing the shape keeps the two gates
consistent and auditable for the same maintainers.
