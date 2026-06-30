"""Deterministic Phase 4 *depth budget* for the grounded claim plan.

The prior phase closed the Phase 2 *breadth* loophole (:mod:`libs.coverage.anti_compression`):
a high-signal catalog can no longer collapse onto a few flat pages. But the grounded
renderer still turns one claim into one paragraph and one sufficient required topic into one
``###`` heading, so a plan that names every required topic with a *single* claim — leaving
most of the evidence Phase 3 mapped to that topic unused — passes every gate while producing
a shallow page. Coverage was modeled **existentially** ("is the topic present?"); depth needs
the **distributive density** analogue ("does each topic ground enough claims for its mapped
evidence?").

This module computes a source-derived per-section **depth budget** and evaluates a claim plan
against it. It is the depth twin of the breadth budget/gate and is intentionally shaped like
it:

- a frozen, injectable :class:`DepthPolicy` (no scattered magic numbers);
- a per-topic claim target derived **only** from that topic's Phase 3 mapped-evidence count
  (``clamp(ceil(mapped / evidence_per_claim), floor, cap)``) — so the guidance shown to the
  planner and the gate that enforces it derive identically, and a thin topic (one mapped
  evidence id) stays satisfiable with a single grounded claim (no padding);
- a deterministic, read-only :func:`evaluate_plan_depth` that fails a shallow plan with
  precise, actionable per-topic / per-section diagnostics;
- :func:`render_depth_budget_lines` for the claim-plan prompt.

Scope is deliberately **claim density**: the depth gate enforces per-required-topic claim
counts plus a section floor. Content-block *coverage* (whether each evidenced content block is
written at all) stays the responsibility of the existing downstream generated-coverage gate;
the depth gate does not duplicate or preempt it. Content-block counts are recorded only as
informational budget context.

It is **pure**: stdlib only, no model call, no file read, no mutation of inputs, and — by
construction — it never reads the comparison-only benchmark. Every number derives from the
section's own obligations (mapped evidence), packet, token bank, and source handles.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

DEPTH_BUDGET_SCHEMA_VERSION = "phase4-depth-budget-v1"

# Defect codes (one per distinct, actionable depth shortfall).
CODE_TOPIC_UNDERFILLED = "required_topic_underfilled_for_mapped_evidence"
CODE_SECTION_UNDERFILLED = "section_claim_density_below_source_floor"


# --- policy (dependency injection; tunable, auditable) ------------------------
@dataclass(frozen=True)
class DepthPolicy:
    """Tunable thresholds for the Phase 4 depth gate.

    Defaults are conservative seeds chosen so a fanned-out-but-shallow plan fails while a plan
    that simply *uses the evidence it was given* passes. They are a single injectable object
    (never scattered constants), so a run records exactly what depth it enforced and a release
    owner can sign off on the numbers before any billed live run.

    ``evidence_per_claim`` ties claim density to the source: roughly one grounded claim per
    this many distinct mapped evidence ids. ``min_claims_per_required_topic`` is the absolute
    floor (a 1-evidence topic stays satisfiable with one claim).
    ``max_claims_per_required_topic`` bounds a richly-mapped topic so it can never demand
    unboundedly many claims.
    """

    evidence_per_claim: int = 1
    min_claims_per_required_topic: int = 1
    max_claims_per_required_topic: int = 8
    min_section_claims: int = 1

    def __post_init__(self) -> None:
        if self.evidence_per_claim < 1:
            raise ValueError("evidence_per_claim must be >= 1")
        if self.min_claims_per_required_topic < 1:
            raise ValueError("min_claims_per_required_topic must be >= 1")
        if self.max_claims_per_required_topic < self.min_claims_per_required_topic:
            raise ValueError(
                "max_claims_per_required_topic must be >= min_claims_per_required_topic")
        if self.min_section_claims < 0:
            raise ValueError("min_section_claims must be >= 0")

    def topic_target(self, mapped_count: int) -> int:
        """The source-derived minimum claims a required topic owes, given the count of distinct
        evidence ids Phase 3 mapped to it: ``clamp(ceil(mapped / evidence_per_claim), floor,
        cap)``. A 1-mapped topic targets the floor; a richly-mapped topic is capped."""
        raw = math.ceil(max(0, mapped_count) / self.evidence_per_claim)
        lo = self.min_claims_per_required_topic
        hi = self.max_claims_per_required_topic
        return max(lo, min(hi, raw))

    def to_dict(self) -> dict:
        return {
            "evidence_per_claim": self.evidence_per_claim,
            "min_claims_per_required_topic": self.min_claims_per_required_topic,
            "max_claims_per_required_topic": self.max_claims_per_required_topic,
            "min_section_claims": self.min_section_claims,
        }


DEFAULT_DEPTH_POLICY = DepthPolicy()


# --- budget model -------------------------------------------------------------
@dataclass
class TopicDepthTarget:
    """One sufficient required topic's source-derived claim-density target."""

    topic: str
    mapped_evidence_count: int
    min_claims: int

    def to_dict(self) -> dict:
        return {"topic": self.topic,
                "mapped_evidence_count": self.mapped_evidence_count,
                "min_claims": self.min_claims}


@dataclass
class SectionDepthBudget:
    """A whole-section, source-derived depth budget (per-topic targets + a section floor).

    Built by :func:`derive_section_depth_budget`; consumed by :func:`evaluate_plan_depth`
    (gate) and :func:`render_depth_budget_lines` (prompt)."""

    schema_version: str
    section_id: str
    policy: dict
    counts: dict
    min_section_claims: int
    topic_targets: list = field(default_factory=list)          # TopicDepthTarget

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "section_id": self.section_id,
            "policy": self.policy,
            "counts": self.counts,
            "min_section_claims": self.min_section_claims,
            "topic_targets": [t.to_dict() for t in self.topic_targets],
        }


@dataclass
class DepthShortfall:
    """One under-filled topic / section."""

    scope: str            # topic | section
    id: str | None
    code: str
    measured: int
    required: int
    detail: str
    remediation: str

    def to_dict(self) -> dict:
        return {"scope": self.scope, "id": self.id, "code": self.code,
                "measured": self.measured, "required": self.required,
                "detail": self.detail, "remediation": self.remediation}


@dataclass
class PlanDepthReport:
    """A claim plan's depth verdict against a :class:`SectionDepthBudget`."""

    section_id: str
    status: str           # pass | fail
    measured: dict        # {total_claims, claims_by_topic}
    shortfalls: list = field(default_factory=list)   # DepthShortfall

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def problem_lines(self) -> list:
        return [f"{s.code}: {s.detail}" for s in self.shortfalls]

    def to_dict(self) -> dict:
        return {"section_id": self.section_id, "status": self.status,
                "measured": self.measured,
                "shortfalls": [s.to_dict() for s in self.shortfalls]}


# --- helpers ------------------------------------------------------------------
def _obligation_rows(rows) -> list:
    """Only the entries that are real generation obligations (sufficient/evidenced)."""
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("is_obligation")]


def _distinct(values) -> int:
    return len({v for v in (values or []) if v})


# --- derivation ---------------------------------------------------------------
def derive_section_depth_budget(*, section_id: str, obligations: list | None,
                                content_block_obligations: list | None,
                                allowed_evidence_ids: list,
                                token_count: int, source_handle_count: int,
                                policy: DepthPolicy | None = None) -> SectionDepthBudget:
    """Compute the source-derived depth budget for one section.

    Deterministic and read-only. Each sufficient required topic owes
    ``policy.topic_target(len(distinct mapped_evidence_ids))`` claims; the section floor is
    ``max(policy.min_section_claims, Σ topic targets)``. An empty obligation set yields a
    budget with no topic targets (no spurious depth pressure on an overview/provenance page).
    ``content_block_obligations`` is recorded only as an informational count — content-block
    *coverage* stays the downstream generated-coverage gate's responsibility. Topic targets
    are sorted for byte-stable output."""
    pol = policy if policy is not None else DEFAULT_DEPTH_POLICY

    topic_targets: list = []
    for ob in _obligation_rows(obligations):
        topic = (ob.get("topic") or "").strip()
        if not topic:
            continue
        mapped = _distinct(ob.get("mapped_evidence_ids"))
        topic_targets.append(TopicDepthTarget(
            topic=topic, mapped_evidence_count=mapped,
            min_claims=pol.topic_target(mapped)))
    topic_targets.sort(key=lambda t: t.topic)

    sum_topic_targets = sum(t.min_claims for t in topic_targets)
    min_section_claims = max(pol.min_section_claims, sum_topic_targets)

    counts = {
        "required_topics": len(topic_targets),
        "content_blocks": len(_obligation_rows(content_block_obligations)),
        "allowed_evidence": len(allowed_evidence_ids or []),
        "token_count": int(token_count),
        "source_handles": int(source_handle_count),
    }
    return SectionDepthBudget(
        schema_version=DEPTH_BUDGET_SCHEMA_VERSION, section_id=section_id,
        policy=pol.to_dict(), counts=counts, min_section_claims=min_section_claims,
        topic_targets=topic_targets)


# --- evaluation ---------------------------------------------------------------
def evaluate_plan_depth(budget: SectionDepthBudget, claims: list) -> PlanDepthReport:
    """Deterministically evaluate a normalized claim list against ``budget``.

    Read-only: never mutates ``claims``. ``claims`` are normalized claim dicts carrying
    ``required_topic``. A topic with fewer claims than its source-derived target is
    ``CODE_TOPIC_UNDERFILLED``; a total claim count below the section floor is
    ``CODE_SECTION_UNDERFILLED``. ``status == "pass"`` iff there are no shortfalls."""
    claims_by_topic: dict = {}
    total = 0
    for c in claims or []:
        if not isinstance(c, dict):
            continue
        total += 1
        rt = (c.get("required_topic") or "").strip()
        if rt:
            claims_by_topic[rt] = claims_by_topic.get(rt, 0) + 1

    shortfalls: list = []
    for t in budget.topic_targets:
        measured = claims_by_topic.get(t.topic, 0)
        if measured < t.min_claims:
            shortfalls.append(DepthShortfall(
                scope="topic", id=t.topic, code=CODE_TOPIC_UNDERFILLED,
                measured=measured, required=t.min_claims,
                detail=(f"required topic {t.topic!r} grounds {measured} claim(s) but Phase 3 "
                        f"mapped {t.mapped_evidence_count} evidence id(s); the source-derived "
                        f"target is {t.min_claims} claim(s)"),
                remediation=("add claim(s) for this topic, each citing a distinct mapped "
                             "evidence id; do not pad or repeat — ground the evidence already "
                             "retrieved, or this section stays shallow")))

    if total < budget.min_section_claims:
        shortfalls.append(DepthShortfall(
            scope="section", id=budget.section_id, code=CODE_SECTION_UNDERFILLED,
            measured=total, required=budget.min_section_claims,
            detail=(f"section {budget.section_id!r} has {total} claim(s) but its source-derived "
                    f"floor (Σ per-topic targets) is {budget.min_section_claims}"),
            remediation=("ground more claims for the section's required topics from their "
                         "mapped evidence; the floor derives from the source, never the "
                         "benchmark")))

    measured = {
        "total_claims": total,
        "claims_by_topic": dict(sorted(claims_by_topic.items())),
    }
    status = "fail" if shortfalls else "pass"
    return PlanDepthReport(section_id=budget.section_id, status=status,
                           measured=measured, shortfalls=shortfalls)


# --- planner guidance ---------------------------------------------------------
def render_depth_budget_lines(budget: SectionDepthBudget) -> list:
    """Markdown lines stating the source-derived depth budget for the claim-plan prompt.

    Embedded after the required-topic block so the planner grounds enough claims instead of
    naming each topic once. Every number derives from this section's mapped evidence / counts;
    none derives from any benchmark. Returns ``[]`` when there is nothing to plan for."""
    if not budget.topic_targets:
        return []
    lines = [
        "## Source-derived depth budget (claim-density obligations)",
        "",
        "These per-topic claim targets are derived **only** from the evidence Phase 3 mapped "
        "to each required topic (never from any benchmark). Ground enough claims to meet each "
        "target — one grounded claim per mapped evidence id is the intended density. Do NOT "
        "pad, repeat, or invent: use the evidence already retrieved. A required topic written "
        "with a single claim while several evidence ids were mapped to it is a shallow page "
        "and will be rejected before assembly.",
        "",
        f"- Plan **at least {budget.min_section_claims}** claim(s) for this section in total "
        f"(the sum of the per-topic targets below).",
        "",
        "| required topic | mapped evidence | min claims |",
        "| --- | --- | --- |",
    ]
    for t in budget.topic_targets:
        topic = t.topic.replace("|", "\\|")
        lines.append(f"| {topic} | {t.mapped_evidence_count} | {t.min_claims} |")
    lines.append("")
    return lines
