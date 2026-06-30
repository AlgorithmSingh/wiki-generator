# Readers & stakeholders

| Reader | Concern | What they need from this TDD |
|---|---|---|
| Pipeline implementers | Where the mode semantics and gates live | Exact modules/functions changed, data contracts, test seams |
| Planner-prompt owners | The LLM authors a fanned-out hierarchy | The hardened prompt rules + the source-derived breadth budget the planner sees |
| Phase 3/4 maintainers | Promoted granularity does not regress downstream | The promoted-topic contract + `catalog_topic_id` passthrough and its enforcement boundary |
| Release owner | Safe rollout; no surprise breakage of existing runs | Compatibility analysis (baseline/enhancement unchanged; deepwiki-scale aliased), policy sign-off gate |
| Future maintainers | Why expanded became the core path | The ADR and the alternatives/trade-offs |
| Operators | What fails, with what exit code, and how to fix | Failure modes, exit codes, remediation strings |

## Decision makers / approvers

- Release owner approves: (a) expanded as the official/core scale path, (b) the
  BreadthPolicy defaults before any billed live run, (c) the deferred Phase 4
  end-to-end enforcement slice.

## Out of audience

- End users of the generated wiki (this is an internal pipeline change; no user-facing
  API surface beyond CLI `--coverage-mode` help text).
