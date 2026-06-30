# Quality Attributes (made measurable) — deepwiki-scale-depth-parity

| Attribute | Concrete definition | How met | How verified |
|---|---|---|---|
| Determinism | Identical inputs → byte-identical depth budget + report | No clock/random; sorted iteration over topics/blocks; derived purely from obligations/packet/token bank | Rerun byte-equality unit test |
| Source-fidelity (no benchmark leakage) | Every depth number derives from catalog/plan/evidence, never `ragflow-deepwiki.md` | `depth_budget.py` imports only stdlib; `topic_target` reads only mapped-evidence counts | `grep` shows no comparator import in `src/`; prompt test asserts no benchmark string |
| Non-regression | baseline/enhancement and existing expanded grounded pass cases unchanged | `depth_budget` optional (default `None`); computed only in expanded grounded mode | Full focused suites + full suite green; `ops` expanded E2E passes |
| Validator strength preserved | No existing check relaxed; depth is strictly additive and runs after grounding checks | New violations appended; `ok = not violations` unchanged | Existing claim-plan/section validator tests unchanged and green |
| Satisfiability (no padding) | A target never exceeds the evidence available to ground it | `topic_target = clamp(ceil(mapped/evidence_per_claim), floor, cap)`; 1-mapped topic → 1 claim | Single-evidence-topic test passes with one claim |
| Auditability | A run records what depth it enforced and the measured result | Effective `policy` serialized in budget; per-section `grounded.depth` audit block | Grounded E2E asserts the depth audit fields |
| Bounded resource | A richly-mapped topic cannot demand unbounded claims | `max_claims_per_required_topic` cap; `DepthPolicy.__post_init__` validates bounds | Cap unit test; invalid-policy `ValueError` test |
| Safety | Read-only; never mutates the plan, never patches output, never heals | `evaluate_plan_depth` returns a report; the existing bounded re-prompt is the only retry | Code review + "plan not mutated" test |
| Layering (HARD-RULES) | `domain` depth module imports no infra/CLI/comparator | `depth_budget.py` depends only on stdlib | Import-scan static check (.sequence) |

No attribute is left as a vague adjective ("deep", "rich"); each maps to a measurable
contract and a test.
