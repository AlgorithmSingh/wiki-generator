# Rollout, Operations & Risk — deepwiki-scale-depth-parity

## Rollout

- **Off by default at the command level.** `--coverage-mode` defaults to `baseline`; only
  callers passing `--coverage-mode expanded` (or the `deepwiki-scale` alias) **and**
  `--grounded-claim-plan` are affected. baseline/enhancement and freeform expanded are
  untouched.
- **Staged, gated:** validated first with the non-live unit/integration tests (this slice).
  A billed live run is a separate, release-owner-approved step (M3).
- The effective `DepthPolicy` is serialized into the per-section grounded audit block, so a
  run records exactly the depth it enforced.

## Operations

- Failures are **loud and actionable**: each `claim_plan_*_underfilled` violation names the
  topic/block/section, the measured claim count, the required count, and the mapped-evidence
  count, with a remediation that says "add grounded claims using the evidence already
  retrieved; do not pad."
- The depth audit (`grounded.depth`) lets an operator see, per section, the budget and the
  measured counts and whether it was satisfied.
- Tuning lever: the injectable `DepthPolicy` (`evidence_per_claim`,
  `max_claims_per_required_topic`, floors). No code edit needed to retune within bounds.

## Rollback

- One-line guard: stop computing/passing `depth_budget` in `writing.run()` (or pass `None`),
  which disables depth enforcement everywhere. The new module and the optional parameters are
  inert without it. No persisted schema is broken. Rollback is a no-op for baseline/enhancement.

## Risks & mitigations

| Risk / failure mode | Mitigation |
|---|---|
| `DepthPolicy` defaults too strict → wrongly fails legitimately-thin sections | Target derives from mapped-evidence count, so a thin topic owes few claims; floor is 1; injectable + serialized; release-owner sign-off before billed runs |
| `DepthPolicy` too lenient → little depth gained | `evidence_per_claim=1` default ties claim count to mapped-evidence density; measurable in M3; tunable |
| Live planner cannot reach the budget | Bounded audited re-prompt feeds exact shortfalls; if still short, fail-closed (no padding); measured in M3, not this slice |
| Depth pressure tempts the model to pad/repeat | Strict grounding + claim-plan validators unchanged; padded/free-typed claims still fail those checks; remediation explicitly says "do not pad" |
| A section legitimately has no obligations | Empty topic targets → depth cannot fail; section floor defaults to policy minimum |
| Benchmark leakage | `depth_budget.py` imports only stdlib; prompt test asserts no benchmark string; comparator never read by the pipeline |

## Open questions

- **OD1 (open):** `DepthPolicy` default values (`evidence_per_claim`,
  `max_claims_per_required_topic`) — seeded conservatively; require release-owner sign-off
  before any billed live run.
- **OD2 (open):** whether heading-density depth (content-block `####`) lands in M2 as
  designed or needs a different rendering approach after M3 measurement.
