# Alternatives & Trade-offs — deepwiki-scale-depth-parity

| # | Alternative | Verdict | Rationale |
|---|---|---|---|
| A1 | Per-topic claim target derived from **mapped-evidence density** (chosen) | **Chosen** | Purely source-derived and satisfiable: a topic mapped to N evidence ids owes ~N grounded claims. Adds real depth exactly where evidence supports it; a 1-evidence topic still passes with one claim (no padding). Mirrors the breadth budget's catalog-derived floor. |
| A2 | A flat minimum (e.g. "≥3 claims per topic" or "≥800 words per section") | Rejected | Not source-derived; forces padding on thin topics; risks word-count inflation the task forbids; would break the legitimately-thin `ops` fixture. |
| A3 | Copy a per-page word/heading target from the benchmark | Rejected | Violates benchmark quarantine; the comparator must never seed generation. |
| A4 | Enforce depth by **patching/regenerating** shallow output until it grows | Rejected | Output patching and heal/retry loops are explicitly forbidden; non-deterministic; hides the real planner deficiency. The bounded audited claim-plan re-prompt (existing) is the only re-prompt and is grounded-and-capped. |
| A5 | Put the depth check **inside** the renderer (fail after rendering on word count) | Rejected | Renderer is deterministic; failing there is a post-hoc word gate, not a source contract. Failing on the **plan** (before render) gives the planner precise, actionable diagnostics and keeps the renderer simple. |
| A6 | Add depth to a **new gate module under `coverage/`** | Rejected | Depth acts on the Phase 4 claim plan (writing-time, per-section, post-provider), not on the Phase 2 plan; it belongs beside the claim-plan machinery in `writing/`. |
| A7 | Also render **content-block `####` headings** in this slice (heading-density depth) | Deferred to M2 | Touches `_derive_covered_content_blocks` and the content-block-coverage grounding evaluator; larger blast radius. The depth budget already increases paragraphs/words per topic. Staged to keep this slice low-risk and validators unweakened. |
| A8 | Make depth a separate opt-in CLI flag | Rejected this slice | `expanded` is the core scale path; depth should be on by default there (like the breadth gate became core). The policy is injectable for tuning; a flag adds surface without need. |

## Accepted trade-off

A previously-"passing" fanned-out-but-shallow **expanded grounded** claim plan now fails the
depth gate. This is the intended correction — the direct analogue of the prior phase's
accepted trade-off ("a compressed expanded plan now fails at Phase 2"). It is off by default
at the command level (baseline), opt-in via expanded + `--grounded-claim-plan`, the policy
is injectable, and rollback is a one-line guard. Documented in rollout.
