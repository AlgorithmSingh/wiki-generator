# Runtime Behavior — deepwiki-scale-depth-parity

## Success path (expanded grounded, sufficiently detailed plan)

1. `run()` builds the packet, token bank, topic obligations, and block obligations.
2. `derive_section_depth_budget(...)` computes per-topic targets from each sufficient
   topic's mapped-evidence count, plus the section floor.
3. The claim-plan prompt carries the depth budget; the planner returns a plan that grounds
   ≥ `target.min_claims` claims per topic.
4. `validate_claim_plan(..., depth_budget)` runs grounding checks (pass) then depth checks
   (pass) → `ok`.
5. `render_section` renders the (now denser) claims; the strict section validator passes.
6. The grounded audit block records the depth budget + measured claim counts (`satisfied:
   true`). The section file is written.

## Failure path (shallow plan)

1–3 as above, but the planner returns one claim per topic.
4. `validate_claim_plan(..., depth_budget)`: grounding passes, depth fails →
   `claim_plan_topic_underfilled` for each under-filled topic (e.g. measured 1, required 3).
5. Live model: a bounded audited re-prompt (≤ `max_rewrite_attempts`) is issued with the
   exact shortfall lines; the planner adds claims; on success → pass. Non-live (gem import)
   or exhausted attempts → fail-closed `WritingValidationFailure` (exit 5); the failure
   report names the under-filled topics and their measured-vs-required counts. The plan is
   never mutated; no output is patched.

## Mode matrix

| coverage_mode | grounded? | depth budget computed | depth gate enforced |
|---|---|---|---|
| baseline | any | no | no |
| enhancement | any | no | no |
| expanded / deepwiki-scale | no (freeform) | no | no (no claim plan exists) |
| expanded / deepwiki-scale | yes (`--grounded-claim-plan`) | **yes** | **yes** |

## Concurrency / state

Stateless and deterministic. No clock, no randomness, no shared mutable state. Sections are
processed in document order exactly as today; the budget is computed per section from that
section's own obligations.

## Edge cases

- Topic mapped to exactly 1 evidence id → target 1 → a single grounded claim passes
  (matches the `ops` expanded grounded command E2E; no padding demanded).
- Topic with 0 sufficient mapped evidence → not an obligation → no target.
- Overview/provenance section with no obligations → empty topic targets → depth cannot
  fail; section floor defaults to the policy minimum.
- A topic mapped to many evidence ids → target capped at `max_claims_per_required_topic`
  (bounded, never explodes).
