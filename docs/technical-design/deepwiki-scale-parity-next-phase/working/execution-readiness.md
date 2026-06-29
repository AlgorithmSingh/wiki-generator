# Execution Readiness — DeepWiki Scale-Parity (Anti-Compression)

## Implementation order (Slice 1)
1. `libs/coverage/validate.py`: add `MODE_DEEPWIKI_SCALE`, extend `_MODES` +
   `_ENFORCING_MODES`, add `EXPANDED_MODES`, `is_expanded_family`, `enforces_breadth`.
2. `libs/coverage/anti_compression.py`: new module (policy, promotion, evaluation,
   gate, render).
3. `libs/coverage/__init__.py`: re-export new symbols.
4. `libs/commands/normalize_plan.py`: thread real mode through expanded gates; run
   anti-compression gate + write artifacts when `enforces_breadth(mode)`.
5. `cli.py`: add `deepwiki-scale` to the four `--coverage-mode` choices + help.
6. `libs/evidence/options.py` + `evidenced_coverage.py`; `libs/writing/options.py` +
   `grounded.py` + `packet.py` + `generated_coverage.py`: accept and treat the new
   mode as expanded-family.
7. `tests/test_phase2_anti_compression.py`.

## Test-to-requirement traceability
| Test | AC | DOD |
|---|---|---|
| promotion contract / tiers | AC-S7 | DOD-7 |
| overloaded leaf / missing TER / flat / family-not-split / floor | AC-S1 | DOD-1 |
| fanned pass | AC-S2 | DOD-2 |
| overview exemption + only-on-overview fail | AC-S3 | DOD-3 |
| baseline/expanded report-only + suite | AC-S4 | DOD-4 |
| determinism | AC-S5 | DOD-5 |
| option/CLI coherence | AC-S6 | DOD-6 |

## Validation commands
```
cd <repo>
git diff --check
git diff --exit-code -- docs/specs/protected/PHASE3_EVIDENCE_RETRIEVAL_SPEC.md
python3 -m json.tool docs/technical-design/deepwiki-scale-parity-next-phase/definition-of-done.json >/dev/null
uv run python -m pytest -q tests/test_phase2_topic_catalog_planning.py tests/test_coverage_validation.py tests/test_relevant_source_map.py tests/test_coverage_traceability.py tests/test_phase2_anti_compression.py
# full suite if affordable:
uv run python -m pytest -q
```

## Rollback
Remove the mode from CLI `choices` / stop passing it. All other modes untouched.

## Sign-offs required before live
OD-S1 (promotion threshold), OD-S2 (breadth policy numbers), OD-S3 (high-risk family
sign-off), OD-S4 (default-vs-opt-in). No live billed call without explicit approval.
