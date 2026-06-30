# Maintenance Policy — deepwiki-scale-depth-parity (Phase 7)

This change is production-impacting (it can flip the pass/fail outcome of expanded grounded
runs), so a maintenance loop applies.

## Ownership

- Phase 4 writing maintainers own `libs/writing/depth_budget.py`, the `claim_plan` gate, and
  the prompt guidance.
- The release owner owns the `DepthPolicy` default values and signs off before any billed
  live run.

## Refresh triggers (when this TDD / ADR-0001 must be revisited)

- The per-topic target formula or `DepthPolicy` defaults change.
- M2 lands (content-block `####` heading depth) — update §7.4 and supersede ADR-0001 if the
  depth contract changes shape (new ADR referencing 0001; never silently edit it).
- The Phase 3 evidenced-matrix contract changes how `mapped_evidence_ids[]` is produced.
- A billed live run (M3) shows the budget is mis-calibrated (too strict / too lenient).
- `generated_coverage` obligations or the grounded audit schema change.

## Review cadence

Reviewed alongside any change to the grounded claim-plan path and before any billed live run.
ADRs are superseded, never silently edited.
