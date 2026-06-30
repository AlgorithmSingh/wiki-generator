# Readers & Stakeholders — deepwiki-scale-depth-parity

| Reader / stakeholder | Concern | What they need from this TDD |
|---|---|---|
| Phase 4 writing maintainers | The claim-plan validator and renderer stay correct and grounded | Exact contract of the new `depth_budget` gate; that it is additive/optional, deterministic, and never weakens existing checks |
| Coverage-gate maintainers | Consistency with the Phase 2 breadth (anti-compression) pattern | That `DepthPolicy`/depth budget mirror `BreadthPolicy`/breadth budget (injectable, source-derived, fail-closed with remediation) |
| Future implementation agents | Where to add code and what tests prove it | Component/module design, data contracts, test traceability, implementation milestones |
| Pipeline operator | Why a section passed/failed depth; how to act | Depth metrics in the per-section audit block; loud, actionable diagnostics; rollout/rollback |
| Release owner | Risk of a behavior change on the expanded path before billed runs | Explicit accepted trade-off (a shallow expanded grounded plan now fails); injectable policy + sign-off open decision; one-line rollback |
| Reviewers | Benchmark quarantine and grounding are preserved | Statement that every depth number is source-derived and the comparator is never read by the pipeline |

## Decision makers / approvers

- **Writer role (assembler):** drafts the TDD and the implementation.
- **Approver/validator role:** gates the TDD against `definition-of-done.json` and gates
  the implementation against the test suite. Simulated as a separate Phase 6 internal
  step (writer ≠ approver), recorded in `working/validation-report.json` and
  `working/repair-log.md`.
- **Release owner:** signs off on `DepthPolicy` defaults before any billed live run
  (out of scope for this non-live slice).
