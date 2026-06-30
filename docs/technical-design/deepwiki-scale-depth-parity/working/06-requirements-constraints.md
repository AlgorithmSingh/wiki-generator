# Requirements, Constraints, Assumptions & Dependencies

## Functional requirements

- **FR1** *(inferred)* A new module `libs/writing/depth_budget.py` provides a frozen,
  injectable `DepthPolicy`, a `SectionDepthBudget` (with per-topic and per-content-block
  targets), `derive_section_depth_budget(...)`, a deterministic `evaluate_plan_depth(...)`
  over normalized claims, and `render_depth_budget_lines(budget)` for the prompt — mirroring
  `libs/coverage/anti_compression.py`.
- **FR2** *(inferred)* The per-topic claim target is **source-derived**: a function of the
  count of distinct Phase 3 `mapped_evidence_ids` for that sufficient required topic,
  divided by `policy.evidence_per_claim`, floored at `policy.min_claims_per_required_topic`,
  capped at `policy.max_claims_per_required_topic`. Content-block and section targets are
  derived analogously / from per-topic targets.
- **FR3** *(sourced seam)* `claim_plan.validate_claim_plan` accepts an optional
  `depth_budget` keyword (default `None`). When present it runs the depth gate **after**
  the existing checks and appends `claim_plan_topic_underfilled` /
  `claim_plan_content_block_underfilled` / `claim_plan_section_underfilled` violations with
  measured-vs-required detail. When `None`, behavior is byte-identical to today.
- **FR4** *(sourced seam)* `build_claim_plan_prompt` and `build_claim_plan_rewrite_prompt`
  accept an optional `depth_budget` and render its guidance lines; the system instruction
  asks the planner to ground enough claims to meet the per-topic budget. No prompt change
  when `depth_budget` is `None`.
- **FR5** *(sourced seam)* `grounded.generate_grounded_section` + `writing.run` compute the
  depth budget **only in expanded grounded mode**, thread it into the prompt and the
  validator, and record depth metrics (budget summary + measured per-topic / total claim
  counts) in the per-section `grounded` audit block.
- **FR6** *(inferred)* The depth gate is deterministic and read-only: it never mutates the
  plan, never adds claims, never downgrades a topic, never reads the benchmark.

## Constraints

- **C1** *(sourced)* No live Vertex/Gemini/API calls; this slice uses unit/integration
  tests only. Do not run `wiki_generator plan` or any live provider.
- **C2** *(sourced)* Do not weaken any existing validator. The depth gate is strictly
  additive; existing pass cases (when no depth shortfall) keep passing.
- **C3** *(sourced)* Preserve the protected Phase 3 spec
  `docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md`; Phase 3 stays deterministic,
  LLM-free; no Phase 1/2/3 code changes.
- **C4** *(sourced)* Benchmark quarantine: every depth number is source-derived; the
  comparator is never evidence, prompt, headings, prose, structure, or generated topics.
- **C5** *(sourced)* Keep `baseline` and `enhancement` byte-for-byte compatible; depth runs
  only for the expanded grounded path.
- **C6** *(sourced)* Python HARD-RULES: explicit public typing, no mutable default args,
  no import-time side effects, dependency injection (policy object), no bare/broad except,
  layered imports (writing depends on writing/util, not on commands), deterministic tests,
  clean working tree, `uv run` validation.
- **C7** *(sourced)* No output patching; no generic heal/retry loops. The existing bounded,
  audited claim-plan re-prompt (≤ `max_rewrite_attempts`, live-model only) is the only
  re-prompt and is unchanged; depth violations feed it the same way other plan violations do.

## Assumptions

- **A1** *(sourced)* The Phase 3 evidenced matrix already supplies precise
  `mapped_evidence_ids[]` per sufficient required topic
  (`generated_coverage.build_topic_obligations`).
- **A2** *(inferred)* A topic mapped to N distinct evidence ids can ground at least N
  grounded claims (one per distinct source span), so an evidence-density target is
  satisfiable without padding.
- **A3** *(inferred)* The DeepWiki-scale generation path uses `--grounded-claim-plan`
  (the real E2E does), so acting on the claim plan is sufficient for this slice.

## Dependencies

- **D1** Reads only in-memory data already present in Phase 4: the `WritingPacket`
  (`allowed_evidence_ids`), the topic obligations (`mapped_evidence_ids`), the content-block
  obligations (`supporting_evidence_ids`), and the per-section token bank. No new third-party
  dependency, no new file read.
- **D2** Mode predicates from `libs/writing/options.py` (`EXPANDED_COVERAGE_MODES`) decide
  when the budget is active.
