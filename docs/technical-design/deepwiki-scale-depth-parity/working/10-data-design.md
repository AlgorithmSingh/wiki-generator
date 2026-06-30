# Data Design — deepwiki-scale-depth-parity

No persisted store, no migration, no PII. All depth data is in-memory and threaded through
the existing grounded loop; the only on-disk effect is an **additive** field in the
per-section grounded audit block.

## Inputs (all already present in Phase 4; source of truth unchanged)

| Field | Source | Used for |
|---|---|---|
| `mapped_evidence_ids[]` per sufficient required topic | Phase 3 evidenced matrix via `generated_coverage.build_topic_obligations` | per-topic claim target |
| `supporting_evidence_ids[]` per content block | `generated_coverage.build_content_block_obligations` | per-block claim target |
| `allowed_evidence_ids[]` | `WritingPacket` | section counts / audit |
| token bank size | `token_bank.build_token_bank` | section counts / audit |
| `relevant_source_handles[]` | `WritingPacket` (expanded) | section counts / audit (source-file density) |
| normalized `claims[]` (`required_topic`, `content_block_id`) | parsed claim plan, normalized by `validate_claim_plan` | measured claim counts |

## New in-memory shapes (`phase4-depth-budget-v1`)

```jsonc
// SectionDepthBudget.to_dict()
{
  "schema_version": "phase4-depth-budget-v1",
  "section_id": "memory-implementation",
  "policy": {"evidence_per_claim": 1, "min_claims_per_required_topic": 1,
             "max_claims_per_required_topic": 8, "min_claims_per_content_block": 1,
             "min_section_claims": 1},
  "counts": {"required_topics": 6, "content_blocks": 2, "allowed_evidence": 22,
             "token_count": 130, "source_handles": 18},
  "min_section_claims": 11,
  "topic_targets": [
    {"topic": "memory.internal-service", "mapped_evidence_count": 3, "min_claims": 3}
  ],
  "content_block_targets": [
    {"content_block_id": "memory-impl", "supporting_evidence_count": 5, "min_claims": 1}
  ]
}
```

```jsonc
// PlanDepthReport.to_dict()  (what the gate produces)
{
  "section_id": "memory-implementation",
  "status": "fail",
  "measured": {"total_claims": 6, "claims_by_topic": {"memory.internal-service": 1},
               "claims_by_content_block": {"memory-impl": 1}},
  "shortfalls": [
    {"scope": "topic", "id": "memory.internal-service",
     "code": "required_topic_underfilled_for_mapped_evidence",
     "measured": 1, "required": 3,
     "detail": "required topic 'memory.internal-service' grounds 1 claim but Phase 3 mapped 3 evidence ids; the source-derived target is 3.",
     "remediation": "add claim(s) for this topic, each citing a distinct mapped evidence id; do not pad — use the evidence already retrieved."}
  ]
}
```

```jsonc
// per-section grounded audit block, ADDITIVE field (generated-sections.jsonl -> grounded)
"grounded": {
  "token_count": 130, "claim_count": 14, "rewrite_attempts": 0,
  "depth": {
    "min_section_claims": 11, "total_claims": 14,
    "topic_targets": {"memory.internal-service": 3},
    "topic_measured": {"memory.internal-service": 3},
    "satisfied": true
  }
}
```

## Determinism & provenance

Every count comes from a Phase 1–3 artifact or the parsed claim plan; nothing derives from
`ragflow-deepwiki.md`. Sorted iteration over topics/blocks gives byte-stable output. The
effective `policy` is serialized in both the budget and the audit so a run records exactly
what depth it enforced (auditability), exactly like the breadth budget records its policy.
