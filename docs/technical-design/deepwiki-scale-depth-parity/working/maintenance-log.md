# Maintenance Log — deepwiki-scale-depth-parity (Phase 7)

## Reconciliation: design vs. implementation (M1)

| Question | Finding |
|---|---|
| Did the implementation match the TDD? | Yes, with one in-loop scope refinement: the content-block depth dimension was removed because it preempted the existing generated-coverage content-block gate (repair R6). Per-topic claim density + section floor — the design's core — shipped as specified. |
| Did any public API change vs. the design? | `DepthPolicy.min_claims_per_content_block`, `BlockDepthTarget`, and `CODE_BLOCK_UNDERFILLED` were removed before commit; `derive_section_depth_budget` keeps its `content_block_obligations` parameter (now an informational count only). No other signature changed. |
| Was a component removed? | No new service/store. |
| Did rollout reveal a new risk? | No live run was performed; the live-calibration risk (OD1) remains open and is owned by the release owner. |
| Was a decision superseded? | ADR-0001 stands (Accepted). The R6 scope refinement is consistent with it (ADR-0001 already scoped depth to "claims proportional to mapped evidence"; content blocks were always secondary). No new ADR needed; if M2 changes the depth contract shape, a new ADR will reference 0001. |

## Applied updates

- `final/technical-design-document.md` §7.1/§8 updated to the per-topic + section scope.
- `definition-of-done.json` DoD2 updated (defect codes).
- `working/{09,11,16}` annotated with the R6 refinement.
- `working/validation-report.json` finalized: all DoD gates pass with implementation evidence.
- `status.md` reflects all phases done; no `revisit`.

## Next refresh triggers

See `working/maintenance-policy.md`. The next expected refresh is M2 (heading-density depth)
or a billed live run (M3) that re-calibrates `DepthPolicy`.
