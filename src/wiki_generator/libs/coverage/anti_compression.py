"""Deterministic Phase 2 anti-compression / breadth gate (core ``expanded`` path).

The hierarchical page-planning gate (:mod:`.page_planning`) marks a catalog topic
*planned* the moment its ``topic_id`` appears in **any** page's ``catalog_topic_ids[]``.
That is *existential* coverage: a single broad page can list a whole family's
high-signal topics for free. The real RAGFlow non-live run exploited exactly this — a
147-topic / 94-``must`` / 13-family catalog passed an early ``expanded`` build as **21
flat pages and 42 topic-evidence requirements**, with every ``parent_section_id`` null
and families collapsed 1:1 onto a single page each.

This module adds the **distributive** breadth contract that the core ``expanded``
DeepWiki-scale path now enforces by default (``deepwiki-scale`` is a compatibility
alias for the same behaviour), purely from the normalized plan and the Phase A topic
catalog, before Phase 3 retrieval. It computes a source-derived **promotion contract**
(a tier per catalog topic) and then holds promoted *leaf* topics to six deterministic
obligations:

1. **Own leaf page** — each ``page``-tier topic must be planned on its own
   non-overview leaf page; an overview/index page listing it does NOT count.
2. **Own TER** — each ``page``-tier topic must have at least one
   ``topic_evidence_requirements[]`` row keyed by its ``catalog_topic_id``.
3. **Leaf-page density** — a leaf page must not absorb more than
   ``policy.max_promoted_topics_per_leaf_page`` promoted leaf topics.
4. **Family fan-out** — a family with more than ``policy.family_split_threshold``
   promoted leaf topics must spread them across at least ``ceil(n / cap)`` leaf pages.
5. **Non-flat hierarchy** — when at least ``policy.flat_plan_family_threshold``
   families carry promoted leaf topics, the plan must declare a resolving
   ``parent_section_id`` somewhere (a wholly flat plan fails).
6. **Breadth floor** — the number of leaf pages must meet the catalog-derived floor
   ``Σ_family ceil(promoted_leaf / cap)``.

It is **LLM-free, network-free, read-only**: it never edits the plan, never
synthesizes a page/topic/TER, never downgrades a topic, and never reads the benchmark.
Thresholds live in an injectable :class:`BreadthPolicy` (no scattered magic numbers).
A defect is reported with an actionable remediation pointing back at the LLM-authored
Phase 2 plan / prompt / schema, and the measured-vs-required numbers.

The core ``expanded`` path (and its ``deepwiki-scale`` alias) fails closed (a defect
blocks before Phase 3, ``status == "fail"``, exit ``3``,
``bad_compressed_normalized_plan``). ``baseline`` and ``enhancement`` are report-only
here, so the gate never surprises a non-expanded run; the expanded family runs it for
real (via :func:`.enforces_breadth`).

The ``promoted_topics[]`` block of the report is the plan-time data contract. A
normalized projection of it is written to ``plans/promoted-topic-contract.json`` (see
:func:`build_promoted_topic_contract`) so the downstream Phase 3 (evidence
sufficiency) and Phase 4 (generated coverage) stages carry the same promoted
catalog-topic granularity instead of regressing to broad-topic-only acceptance.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from ..context_docs import is_provenance_section
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    MODE_DEEPWIKI_SCALE,
    _MODES,
    enforces_breadth,
)

ANTI_COMPRESSION_SCHEMA_VERSION = "phase2-anti-compression-v1"

# Distinct, actionable blocking category for a compressed (under-fanned) plan — kept
# separate from the page-planning gate's bad_underspecified_normalized_plan so the
# failure surface tells operators *which* contract broke.
FAILURE_CATEGORY = "bad_compressed_normalized_plan"

# The catalog priority that makes a topic a promotion candidate (mirrors
# page_planning._BLOCKING_PRIORITY).
_BLOCKING_PRIORITY = "must"
# Catalog topic kind that denotes an index/family-level topic (vs. a leaf subsystem).
_FAMILY_KIND = "family"

# Promotion tiers (the source-derived promotion contract).
TIER_PAGE = "page"            # blocking leaf topic: needs its own leaf page + TER
TIER_OVERVIEW = "overview"    # blocking family/index topic: satisfied by an index page
TIER_OPTIONAL = "optional"    # should/could topic: context, never blocks
TIER_KNOWN_GAP = "known_gap"  # explicitly deferred with a source-derived reason

# Per-promoted-topic coverage statuses.
STATUS_COVERED = "covered"
STATUS_UNCOVERED = "uncovered"
STATUS_DEFERRED = "deferred"
STATUS_OPTIONAL = "optional"

# Defect codes (one per distinct, actionable anti-compression defect).
CODE_TOPIC_NO_LEAF_PAGE = "promoted_topic_not_on_leaf_page"
CODE_TOPIC_NO_TER = "promoted_topic_missing_topic_evidence_requirement"
CODE_LEAF_PAGE_OVERLOADED = "leaf_page_overloaded_with_promoted_topics"
CODE_FAMILY_NOT_SPLIT = "high_signal_family_not_split_into_child_pages"
CODE_FLAT_HIERARCHY = "source_catalog_plan_is_flat"
CODE_INSUFFICIENT_BREADTH = "plan_breadth_below_catalog_floor"


# --- policy (dependency injection; tunable, auditable) ------------------------
@dataclass(frozen=True)
class BreadthPolicy:
    """Tunable thresholds for the anti-compression gate (PRD BR-S7 / OD-S2).

    Defaults are conservative seeds chosen so the observed real-run collapse fails and
    a reasonably fanned-out plan passes. They are a single injectable object (never
    scattered constants) so a run records exactly what it enforced and a release owner
    can sign off on numbers before any live run.
    """

    max_promoted_topics_per_leaf_page: int = 4
    family_split_threshold: int = 6
    flat_plan_family_threshold: int = 3
    overview_profiles: tuple = ("overview",)
    require_ter_per_promoted_topic: bool = True
    require_leaf_page_per_promoted_topic: bool = True

    def __post_init__(self) -> None:
        if self.max_promoted_topics_per_leaf_page < 1:
            raise ValueError("max_promoted_topics_per_leaf_page must be >= 1")
        if self.family_split_threshold < 1:
            raise ValueError("family_split_threshold must be >= 1")
        if self.flat_plan_family_threshold < 1:
            raise ValueError("flat_plan_family_threshold must be >= 1")

    def required_leaf_pages(self, promoted_leaf_count: int) -> int:
        """The minimum leaf pages needed to host ``promoted_leaf_count`` promoted leaf
        topics at the density cap (``ceil(n / cap)``)."""
        if promoted_leaf_count <= 0:
            return 0
        return math.ceil(promoted_leaf_count / self.max_promoted_topics_per_leaf_page)

    def to_dict(self) -> dict:
        return {
            "max_promoted_topics_per_leaf_page": self.max_promoted_topics_per_leaf_page,
            "family_split_threshold": self.family_split_threshold,
            "flat_plan_family_threshold": self.flat_plan_family_threshold,
            "overview_profiles": list(self.overview_profiles),
            "require_ter_per_promoted_topic": self.require_ter_per_promoted_topic,
            "require_leaf_page_per_promoted_topic":
                self.require_leaf_page_per_promoted_topic,
        }


DEFAULT_BREADTH_POLICY = BreadthPolicy()


# --- result model -------------------------------------------------------------
@dataclass
class PromotedTopic:
    """One catalog topic's promotion verdict (the downstream data contract row)."""

    topic_id: str
    family: str
    tier: str
    priority: str
    signal_strength: str
    topic_kind: str
    has_ter: bool
    leaf_pages: list = field(default_factory=list)   # non-overview section ids
    status: str = STATUS_COVERED
    defects: list = field(default_factory=list)       # defect-code strings

    @property
    def blocking(self) -> bool:
        return self.tier == TIER_PAGE and bool(self.defects)

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id, "family": self.family, "tier": self.tier,
            "priority": self.priority, "signal_strength": self.signal_strength,
            "topic_kind": self.topic_kind, "has_ter": self.has_ter,
            "leaf_pages": list(self.leaf_pages), "status": self.status,
            "defects": list(self.defects),
        }


@dataclass
class FamilyBreadth:
    """One family's fan-out verdict across the plan's leaf pages."""

    family: str
    promoted_leaf_count: int
    required_leaf_pages: int
    actual_leaf_pages: int
    leaf_page_ids: list = field(default_factory=list)
    status: str = "pass"                              # pass | fail
    defects: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "promoted_leaf_count": self.promoted_leaf_count,
            "required_leaf_pages": self.required_leaf_pages,
            "actual_leaf_pages": self.actual_leaf_pages,
            "leaf_page_ids": list(self.leaf_page_ids),
            "status": self.status, "defects": list(self.defects),
        }


@dataclass
class AntiCompressionReport:
    """A whole-plan anti-compression / breadth verdict."""

    schema_version: str
    mode: str
    status: str                                       # pass | fail
    enforced: bool
    failure_category: str | None
    catalog_present: bool
    policy: dict
    section_count: int
    leaf_page_count: int
    overview_page_count: int
    promoted_leaf_topic_count: int
    covered_topic_count: int
    uncovered_topic_count: int
    required_leaf_pages: int
    actual_leaf_pages: int
    flat_hierarchy: bool
    blocking_sections: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)   # actionable dicts
    promoted_topics: list = field(default_factory=list)   # PromotedTopic
    families: list = field(default_factory=list)       # FamilyBreadth

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version, "mode": self.mode,
            "status": self.status, "enforced": self.enforced,
            "failure_category": self.failure_category,
            "catalog_present": self.catalog_present, "policy": self.policy,
            "counts": {
                "sections": self.section_count,
                "leaf_pages": self.leaf_page_count,
                "overview_pages": self.overview_page_count,
                "promoted_leaf_topics": self.promoted_leaf_topic_count,
                "covered_topics": self.covered_topic_count,
                "uncovered_topics": self.uncovered_topic_count,
                "required_leaf_pages": self.required_leaf_pages,
                "actual_leaf_pages": self.actual_leaf_pages,
            },
            "flat_hierarchy": self.flat_hierarchy,
            "blocking_sections": list(self.blocking_sections),
            "diagnostics": list(self.diagnostics),
            "promoted_topics": [t.to_dict() for t in self.promoted_topics],
            "families": [f.to_dict() for f in self.families],
        }


# --- helpers ------------------------------------------------------------------
def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _catalog_topics(catalog: dict | None) -> list:
    if not isinstance(catalog, dict):
        return []
    topics = catalog.get("topics")
    return [t for t in topics if isinstance(t, dict)] if isinstance(topics, list) else []


def _known_gap_strings(section: dict) -> list:
    """The text of every known-gap entry on a section (string or dict form). Mirrors
    :func:`page_planning._known_gap_strings` so deferral is decided identically."""
    out: list = []
    for g in _as_list(section.get("known_gaps")):
        if isinstance(g, str):
            out.append(g)
        elif isinstance(g, dict):
            cid = g.get("catalog_topic_id")
            if cid:
                out.append(str(cid))
            reason = g.get("reason") or g.get("text")
            if reason:
                out.append(str(reason))
    return out


def classify_promotion(topic: dict, deferred: bool) -> str:
    """The source-derived promotion tier of one catalog topic.

    ``deferred`` (its id named in a source-derived ``known_gaps[]`` entry) wins, then
    ``must`` family topics are ``overview`` tier, ``must`` non-family topics are
    ``page`` tier (a leaf obligation), and everything else is ``optional``."""
    if deferred:
        return TIER_KNOWN_GAP
    priority = topic.get("priority") or "could"
    if priority != _BLOCKING_PRIORITY:
        return TIER_OPTIONAL
    kind = topic.get("topic_kind") or _FAMILY_KIND
    return TIER_OVERVIEW if kind == _FAMILY_KIND else TIER_PAGE


# --- evaluation ---------------------------------------------------------------
def evaluate_anti_compression(catalog: dict | None, document_plan: dict | None,
                              sections: list, *, mode: str = MODE_DEEPWIKI_SCALE,
                              policy: BreadthPolicy | None = None
                              ) -> AntiCompressionReport:
    """Evaluate the distributive anti-compression contract over a normalized plan.

    Deterministic and read-only. In the core ``expanded`` path (and its
    ``deepwiki-scale`` alias) a promoted leaf topic with no own leaf page / no own TER,
    an overloaded leaf page, an unsplit large family, a wholly flat plan, or a
    leaf-page count below the catalog floor fails before Phase 3 (``status == "fail"``,
    exit ``3``). ``baseline``/``enhancement`` are report-only (the same matrix without
    gating). ``catalog`` may be ``None`` (nothing to enforce).

    Raises ``ValueError`` for an unknown mode or non-list ``sections`` (mirrors
    :func:`.validate.evaluate_plan_coverage`)."""
    if mode not in _MODES:
        raise ValueError(f"unknown coverage mode {mode!r}; expected one of {_MODES}")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list of normalized section-plan dicts")
    pol = policy if policy is not None else DEFAULT_BREADTH_POLICY
    enforced = enforces_breadth(mode)

    catalog_topics = _catalog_topics(catalog)
    if not isinstance(catalog, dict):
        # No catalog -> nothing to enforce (the command fails earlier on a missing
        # catalog in expanded/deepwiki-scale; this keeps direct calls graceful).
        return AntiCompressionReport(
            schema_version=ANTI_COMPRESSION_SCHEMA_VERSION, mode=mode, status="pass",
            enforced=enforced, failure_category=None, catalog_present=False,
            policy=pol.to_dict(), section_count=len(sections), leaf_page_count=0,
            overview_page_count=0, promoted_leaf_topic_count=0, covered_topic_count=0,
            uncovered_topic_count=0, required_leaf_pages=0, actual_leaf_pages=0,
            flat_hierarchy=False)

    # 1) sections: exclude provenance/meta; partition leaf vs overview by profile.
    overview_profiles = set(pol.overview_profiles)
    planned_ids = {s.get("section_id") for s in sections if s.get("section_id")}
    content_sections = [s for s in sections if not is_provenance_section(s)]
    leaf_sections: list = []
    overview_count = 0
    for s in content_sections:
        if (s.get("page_profile") in overview_profiles):
            overview_count += 1
        else:
            leaf_sections.append(s)

    # 2) deferral set (mirrors page_planning): a topic id named in any known-gap text.
    gap_strings: list = []
    for s in sections:
        gap_strings.extend(_known_gap_strings(s))
    if isinstance(document_plan, dict):
        gap_strings.extend(_known_gap_strings(document_plan))

    def is_deferred(topic_id: str) -> bool:
        return any(topic_id in g for g in gap_strings)

    # 3) promotion contract: a tier per catalog topic; collect promoted leaf set.
    promoted_leaf_ids: set = set()
    leaf_topic_family: dict = {}
    promoted_rows: list = []
    for t in catalog_topics:
        tid = t.get("topic_id")
        if not isinstance(tid, str) or not tid:
            continue
        tier = classify_promotion(t, is_deferred(tid))
        family = t.get("family") or (tid.split(".")[0] if "." in tid else tid)
        row = PromotedTopic(
            topic_id=tid, family=family, tier=tier,
            priority=t.get("priority") or "could",
            signal_strength=t.get("signal_strength") or "none",
            topic_kind=t.get("topic_kind") or _FAMILY_KIND, has_ter=False)
        if tier == TIER_PAGE:
            promoted_leaf_ids.add(tid)
            leaf_topic_family[tid] = family
        elif tier == TIER_KNOWN_GAP:
            row.status = STATUS_DEFERRED
        elif tier == TIER_OPTIONAL:
            row.status = STATUS_OPTIONAL
        else:  # overview tier is informational here (page_planning owns family coverage)
            row.status = STATUS_COVERED
        promoted_rows.append(row)

    # 4) which leaf pages list each promoted leaf topic (overview pages never count).
    leaf_pages_by_topic: dict = {tid: [] for tid in promoted_leaf_ids}
    promoted_on_leaf_page: dict = {}   # section_id -> set of promoted leaf ids
    for s in leaf_sections:
        sid = s.get("section_id") or "?"
        here: set = set()
        for tid in _as_list(s.get("catalog_topic_ids")):
            if tid in promoted_leaf_ids:
                here.add(tid)
                leaf_pages_by_topic[tid].append(sid)
        promoted_on_leaf_page[sid] = here

    # 5) which promoted leaf topics carry their own TER (keyed by catalog_topic_id).
    ter_catalog_ids: set = set()
    for s in content_sections:
        for ter in _as_list(s.get("topic_evidence_requirements")):
            if not isinstance(ter, dict):
                continue
            cid = ter.get("catalog_topic_id")
            if isinstance(cid, str) and cid:
                ter_catalog_ids.add(cid)

    # 6) per-promoted-leaf-topic defects (own leaf page + own TER).
    diagnostics: list = []
    by_topic_id = {r.topic_id: r for r in promoted_rows}
    for tid in sorted(promoted_leaf_ids):
        row = by_topic_id[tid]
        row.leaf_pages = sorted(leaf_pages_by_topic.get(tid, []))
        row.has_ter = tid in ter_catalog_ids
        if pol.require_leaf_page_per_promoted_topic and not row.leaf_pages:
            row.defects.append(CODE_TOPIC_NO_LEAF_PAGE)
            diagnostics.append({
                "scope": "topic", "id": tid, "code": CODE_TOPIC_NO_LEAF_PAGE,
                "detail": (f"promoted leaf catalog topic {tid!r} is not planned on its "
                           "own non-overview leaf page (an overview/index page listing "
                           "it does not count)"),
                "remediation": (f"add a dedicated leaf page for {tid!r} and name it in "
                                "that page's catalog_topic_ids[], or record an explicit "
                                "source-derived known_gaps[] deferral for this topic.")})
        if pol.require_ter_per_promoted_topic and not row.has_ter:
            row.defects.append(CODE_TOPIC_NO_TER)
            diagnostics.append({
                "scope": "topic", "id": tid, "code": CODE_TOPIC_NO_TER,
                "detail": (f"promoted leaf catalog topic {tid!r} has no "
                           "topic_evidence_requirements[] row keyed by its "
                           "catalog_topic_id"),
                "remediation": (f"add a topic_evidence_requirements[] entry with "
                                f"catalog_topic_id '{tid}' (required:true, exact "
                                "source_fields[]) on the leaf page that covers it; "
                                "every promoted topic needs its own evidence obligation.")})
        row.status = STATUS_UNCOVERED if row.defects else STATUS_COVERED

    # 7) per-leaf-page density.
    blocking_sids: list = []
    for s in leaf_sections:
        sid = s.get("section_id") or "?"
        count = len(promoted_on_leaf_page.get(sid, set()))
        if count > pol.max_promoted_topics_per_leaf_page:
            if sid not in blocking_sids:
                blocking_sids.append(sid)
            diagnostics.append({
                "scope": "section", "id": sid, "code": CODE_LEAF_PAGE_OVERLOADED,
                "detail": (f"leaf page {sid!r} claims {count} promoted leaf catalog "
                           f"topics; the density cap is "
                           f"{pol.max_promoted_topics_per_leaf_page}"),
                "remediation": (f"split {sid!r} into child/subpages so no leaf page "
                                f"absorbs more than {pol.max_promoted_topics_per_leaf_page} "
                                "promoted leaf topics, or mark it an overview/index "
                                "page (overview pages do not count as leaf coverage).")})

    # 8) per-family fan-out + flat-hierarchy + breadth floor.
    family_leaf_counts: dict = {}
    for tid in promoted_leaf_ids:
        family_leaf_counts.setdefault(leaf_topic_family[tid], 0)
        family_leaf_counts[leaf_topic_family[tid]] += 1
    family_leaf_pages: dict = {}
    for s in leaf_sections:
        sid = s.get("section_id") or "?"
        fams = {leaf_topic_family[tid] for tid in promoted_on_leaf_page.get(sid, set())}
        for fam in fams:
            family_leaf_pages.setdefault(fam, set()).add(sid)

    family_rows: list = []
    required_floor = 0
    for fam in sorted(family_leaf_counts):
        n = family_leaf_counts[fam]
        required = pol.required_leaf_pages(n)
        required_floor += required
        actual = len(family_leaf_pages.get(fam, set()))
        defects: list = []
        if n > pol.family_split_threshold and actual < required:
            defects.append(CODE_FAMILY_NOT_SPLIT)
            diagnostics.append({
                "scope": "family", "id": fam, "code": CODE_FAMILY_NOT_SPLIT,
                "detail": (f"family {fam!r} has {n} promoted leaf topics but spreads "
                           f"them across only {actual} leaf page(s); at the density cap "
                           f"it needs at least {required}"),
                "remediation": (f"fan family {fam!r} out into at least {required} "
                                "hierarchically-linked leaf pages (one parent overview "
                                "page plus child subsystem pages), instead of a single "
                                "broad page.")})
        family_rows.append(FamilyBreadth(
            family=fam, promoted_leaf_count=n, required_leaf_pages=required,
            actual_leaf_pages=actual, leaf_page_ids=sorted(family_leaf_pages.get(fam, set())),
            status="fail" if defects else "pass", defects=defects))

    families_with_promoted = len(family_leaf_counts)
    any_resolving_parent = any(
        isinstance(s.get("parent_section_id"), str)
        and s.get("parent_section_id") in planned_ids
        for s in content_sections)
    flat_hierarchy = (families_with_promoted >= pol.flat_plan_family_threshold
                      and not any_resolving_parent)
    if flat_hierarchy:
        diagnostics.append({
            "scope": "plan", "id": None, "code": CODE_FLAT_HIERARCHY,
            "detail": (f"{families_with_promoted} families carry promoted leaf topics "
                       "but the plan declares no resolving parent_section_id (it is "
                       "wholly flat)"),
            "remediation": ("introduce parent/child hierarchy: give each large family "
                            "an overview/index page and link its child subsystem pages "
                            "via parent_section_id.")})

    actual_leaf_pages = len(leaf_sections)
    breadth_short = actual_leaf_pages < required_floor
    if breadth_short:
        diagnostics.append({
            "scope": "plan", "id": None, "code": CODE_INSUFFICIENT_BREADTH,
            "detail": (f"the plan has {actual_leaf_pages} leaf page(s) but the catalog "
                       f"floor (Σ ceil(promoted_leaf/cap)) requires at least "
                       f"{required_floor}"),
            "remediation": ("plan more leaf pages so the high-signal catalog fans out; "
                            "the floor is derived from the source catalog, never the "
                            "benchmark. Defer unsupported topics via known_gaps[] if "
                            "source evidence is genuinely absent.")})

    promoted_leaf_count = len(promoted_leaf_ids)
    uncovered = sum(1 for r in promoted_rows
                    if r.tier == TIER_PAGE and r.status == STATUS_UNCOVERED)
    covered = promoted_leaf_count - uncovered
    has_blocking = bool(diagnostics)
    failed = enforced and has_blocking
    return AntiCompressionReport(
        schema_version=ANTI_COMPRESSION_SCHEMA_VERSION, mode=mode,
        status="fail" if failed else "pass", enforced=enforced,
        failure_category=FAILURE_CATEGORY if failed else None, catalog_present=True,
        policy=pol.to_dict(), section_count=len(sections),
        leaf_page_count=len(leaf_sections), overview_page_count=overview_count,
        promoted_leaf_topic_count=promoted_leaf_count, covered_topic_count=covered,
        uncovered_topic_count=uncovered, required_leaf_pages=required_floor,
        actual_leaf_pages=actual_leaf_pages, flat_hierarchy=flat_hierarchy,
        blocking_sections=sorted(blocking_sids), diagnostics=diagnostics,
        promoted_topics=promoted_rows, families=family_rows)


# --- the deepwiki-scale gate --------------------------------------------------
@dataclass
class AntiCompressionGate:
    """Verdict of the deterministic Phase 2 anti-compression / breadth gate.

    Like the other coverage gates it never edits/synthesizes/heals the plan: it reports
    the verdict and the exit code a caller fails on (``0`` pass, ``3`` expanded-path
    fail)."""

    report: AntiCompressionReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code,
                "report": self.report.to_dict()}

    def summary_lines(self) -> list:
        r = self.report
        lines = [
            f"anti-compression gate: mode={r.mode} "
            f"({'enforced' if r.enforced else 'report-only'})",
            f"anti-compression gate: catalog "
            + ("present" if r.catalog_present else "ABSENT (breadth check skipped)"),
            f"anti-compression gate: {r.covered_topic_count}/{r.promoted_leaf_topic_count} "
            f"promoted leaf topic(s) on their own leaf page with a TER; "
            f"{r.actual_leaf_pages}/{r.required_leaf_pages} leaf pages vs catalog floor; "
            f"flat_hierarchy={r.flat_hierarchy}",
        ]
        if r.blocking_sections:
            lines.append("anti-compression gate: overloaded leaf pages: "
                         + ", ".join(r.blocking_sections))
        for d in r.diagnostics:
            where = d.get("id") or f"({d.get('scope')})"
            lines.append(f"  - {where} [{d['code']}]: {d['remediation']}")
        verdict = "PASS" if self.passed else "FAIL"
        if not self.passed:
            lines.append(
                f"anti-compression gate: {verdict} — the plan compresses a high-signal "
                "source catalog into too few flat pages. This deterministic gate does "
                "NOT add pages, TERs, or hierarchy; fix the LLM-authored Phase 2 plan "
                "(stronger prompt/schema, or a bounded audited re-prompt) and re-run "
                "before Phase 3 retrieval.")
        else:
            lines.append(f"anti-compression gate: {verdict}")
        return lines


def gate_anti_compression(catalog: dict | None, document_plan: dict | None,
                          sections: list, *, mode: str = MODE_DEEPWIKI_SCALE,
                          policy: BreadthPolicy | None = None) -> AntiCompressionGate:
    """Evaluate ``sections`` against the anti-compression contract and map the verdict
    to an :class:`AntiCompressionGate` (``exit_code`` ``0`` pass / ``3`` fail in the
    core ``expanded`` path and its ``deepwiki-scale`` alias). It never mutates the
    plan."""
    report = evaluate_anti_compression(catalog, document_plan, sections, mode=mode,
                                       policy=policy)
    passed = report.status == "pass"
    return AntiCompressionGate(
        report=report, passed=passed,
        exit_code=COVERAGE_GATE_PASS_EXIT if passed else COVERAGE_GATE_FAIL_EXIT)


def render_anti_compression_markdown(report: AntiCompressionReport, *,
                                     title: str = "Phase 2 Anti-Compression Gate"
                                     ) -> str:
    """Render the human-readable ``anti-compression-report.md`` artifact."""
    verdict = "PASS" if report.status == "pass" else "FAIL"
    pol = report.policy
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Mode: **{report.mode}** "
        f"({'enforced' if report.enforced else 'report-only'})",
        f"- Status: **{verdict}**",
        f"- Topic catalog: " + ("present" if report.catalog_present else "**absent**"),
        f"- Promoted leaf topics covered: {report.covered_topic_count}/"
        f"{report.promoted_leaf_topic_count} (own leaf page + own TER)",
        f"- Leaf pages: {report.actual_leaf_pages} (catalog floor "
        f"{report.required_leaf_pages}); overview pages: {report.overview_page_count}",
        f"- Flat hierarchy: {report.flat_hierarchy}",
        f"- Policy: cap={pol['max_promoted_topics_per_leaf_page']}, "
        f"family_split={pol['family_split_threshold']}, "
        f"flat_threshold={pol['flat_plan_family_threshold']}, "
        f"overview_profiles={pol['overview_profiles']}",
        "",
        "> deepwiki-scale enforces distributive breadth: every promoted leaf catalog",
        "> topic must earn its own non-overview leaf page and its own topic-evidence",
        "> requirement, large families must fan out, the plan must not be flat, and the",
        "> leaf-page count must meet the catalog-derived floor. Thresholds derive from",
        "> the source catalog, never the benchmark.",
        "",
    ]
    if report.diagnostics:
        lines += ["## Defects", ""]
        for d in report.diagnostics:
            where = d.get("id") or f"({d.get('scope')})"
            lines.append(f"### `{where}` — `{d['code']}`")
            lines.append("")
            lines.append(f"- {d['detail']}")
            lines.append(f"- Remediation: {d['remediation']}")
            lines.append("")
    else:
        lines += ["The plan fans the source catalog out into evidence-backed leaf "
                  "pages; no compression defects.", ""]
    lines += ["## Family fan-out", "",
              "| family | promoted leaf topics | required leaf pages | actual | status |",
              "|---|---|---|---|---|"]
    for f in report.families:
        mark = "✅" if f.status == "pass" else "❌"
        lines.append(f"| `{f.family}` | {f.promoted_leaf_count} | "
                     f"{f.required_leaf_pages} | {f.actual_leaf_pages} | {mark} |")
    return "\n".join(lines).rstrip() + "\n"


# --- source-derived breadth budget (planner guidance) ------------------------
# A deterministic, source-derived page / required-topic target the Phase 2 planner is
# given as CONTEXT (rendered into planning-topic-catalog.md). It is NOT a gate — the
# anti-compression gate enforces the same floors after planning — but it tells the
# LLM planner the breadth this repository's catalog actually supports, so it fans out
# instead of compressing. Every number derives from the catalog counts and the breadth
# policy; none of it derives from the benchmark.
BREADTH_BUDGET_SCHEMA_VERSION = "deepwiki-breadth-budget-v1"


@dataclass
class FamilyBudget:
    """One must-family's source-derived fan-out target (leaf pages it should host)."""

    family: str
    promoted_leaf_count: int
    min_leaf_pages: int

    def to_dict(self) -> dict:
        return {"family": self.family,
                "promoted_leaf_count": self.promoted_leaf_count,
                "min_leaf_pages": self.min_leaf_pages}


@dataclass
class BreadthBudget:
    """A source-derived page / required-topic breadth target for the Phase 2 planner.

    ``min_leaf_pages`` is the catalog floor (``Σ ceil(promoted_leaf/cap)``) — the exact
    number the anti-compression gate later enforces; ``max_leaf_pages`` is one page per
    promoted leaf topic. ``min_required_topics`` is one required topic + TER per
    promoted leaf topic plus one per fanned family overview. All counts are derived
    from THIS repository's catalog; never from the benchmark."""

    schema_version: str
    catalog_present: bool
    policy: dict
    must_family_count: int
    families_with_promoted: int
    promoted_leaf_count: int
    optional_topic_count: int
    min_overview_pages: int
    min_leaf_pages: int
    max_leaf_pages: int
    min_total_pages: int
    max_total_pages: int
    min_required_topics: int
    families: list = field(default_factory=list)   # FamilyBudget

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "catalog_present": self.catalog_present,
            "policy": self.policy,
            "counts": {
                "must_families": self.must_family_count,
                "families_with_promoted": self.families_with_promoted,
                "promoted_leaf_topics": self.promoted_leaf_count,
                "optional_topics": self.optional_topic_count,
            },
            "targets": {
                "min_overview_pages": self.min_overview_pages,
                "min_leaf_pages": self.min_leaf_pages,
                "max_leaf_pages": self.max_leaf_pages,
                "min_total_pages": self.min_total_pages,
                "max_total_pages": self.max_total_pages,
                "min_required_topics": self.min_required_topics,
            },
            "families": [f.to_dict() for f in self.families],
        }


def derive_breadth_budget(catalog: dict | None, *,
                          policy: BreadthPolicy | None = None) -> BreadthBudget:
    """Compute the source-derived breadth budget from a topic catalog.

    Deterministic and read-only. Uses the same promotion classification the gate uses
    (``must`` family topics → overview tier, ``must`` non-family topics → page/leaf
    tier), so the planner's guidance and the gate's enforcement are derived
    identically. An absent/empty catalog yields an all-zero budget (nothing to plan
    for)."""
    pol = policy if policy is not None else DEFAULT_BREADTH_POLICY
    topics = _catalog_topics(catalog)
    family_leaf: dict = {}
    must_families: set = set()
    optional = 0
    for t in topics:
        tid = t.get("topic_id")
        if not isinstance(tid, str) or not tid:
            continue
        fam = t.get("family") or (tid.split(".")[0] if "." in tid else tid)
        tier = classify_promotion(t, False)
        if tier == TIER_PAGE:
            family_leaf[fam] = family_leaf.get(fam, 0) + 1
        elif tier == TIER_OVERVIEW:
            must_families.add(fam)
        elif tier == TIER_OPTIONAL:
            optional += 1

    promoted_leaf = sum(family_leaf.values())
    families_with_promoted = len(family_leaf)
    min_leaf = sum(pol.required_leaf_pages(n) for n in family_leaf.values())
    max_leaf = promoted_leaf
    # one top index/overview page + one family-index page per fanned family.
    if families_with_promoted:
        min_overview = families_with_promoted + 1
    elif must_families:
        min_overview = 1
    else:
        min_overview = 0
    min_required = promoted_leaf + families_with_promoted
    fam_rows = [FamilyBudget(family=f, promoted_leaf_count=family_leaf[f],
                             min_leaf_pages=pol.required_leaf_pages(family_leaf[f]))
                for f in sorted(family_leaf)]
    return BreadthBudget(
        schema_version=BREADTH_BUDGET_SCHEMA_VERSION,
        catalog_present=isinstance(catalog, dict),
        policy=pol.to_dict(),
        must_family_count=len(must_families | set(family_leaf)),
        families_with_promoted=families_with_promoted,
        promoted_leaf_count=promoted_leaf, optional_topic_count=optional,
        min_overview_pages=min_overview, min_leaf_pages=min_leaf,
        max_leaf_pages=max_leaf, min_total_pages=min_overview + min_leaf,
        max_total_pages=min_overview + max_leaf, min_required_topics=min_required,
        families=fam_rows)


def render_breadth_budget_lines(budget: BreadthBudget) -> list:
    """Markdown lines stating the source-derived breadth budget for the planner.

    Embedded in ``planning-topic-catalog.md`` so the LLM planner sees concrete,
    catalog-derived page / required-topic targets (and the per-family fan-out floor)
    and authors a fanned-out hierarchy instead of compressing. Returns ``[]`` when the
    catalog has no promotable signal."""
    if not budget.catalog_present or budget.must_family_count == 0:
        return []
    pol = budget.policy
    lines = [
        "## Source-derived breadth budget (planner guidance)",
        "",
        "These page and required-topic targets are derived **only** from this "
        "repository's catalog counts above (never from any benchmark). Plan a "
        "fanned-out hierarchy that meets them; the deterministic Phase 2 "
        "anti-compression gate enforces the same source floors after planning.",
        "",
        f"- Promoted **leaf** catalog topics (high-signal subsystems): "
        f"**{budget.promoted_leaf_count}** across "
        f"**{budget.families_with_promoted}** high-signal families "
        f"(plus {budget.must_family_count} mandatory families overall).",
        f"- Plan **at least {budget.min_total_pages}** and up to "
        f"~**{budget.max_total_pages}** pages: "
        f"{budget.min_overview_pages} overview/index page(s) + "
        f"{budget.min_leaf_pages}–{budget.max_leaf_pages} leaf subsystem pages "
        f"(cap {pol['max_promoted_topics_per_leaf_page']} promoted leaf topics per "
        "leaf page).",
        f"- Plan **at least {budget.min_required_topics}** required topics — one "
        "required topic AND one topic_evidence_requirements[] entry per promoted leaf "
        "catalog topic, plus one per fanned family overview page.",
        f"- A family with more than {pol['family_split_threshold']} promoted leaf "
        "topics must fan out into multiple child pages under a parent index page; a "
        "single broad page that merely lists a family's catalog_topic_ids[] does NOT "
        "count as leaf coverage.",
        "",
    ]
    if budget.families:
        lines += ["| family | promoted leaf topics | min leaf pages |",
                  "|---|---|---|"]
        for f in budget.families:
            lines.append(f"| `{f.family}` | {f.promoted_leaf_count} | "
                         f"{f.min_leaf_pages} |")
        lines.append("")
    return lines


# --- promoted-topic contract (Phase 3/4 downstream data contract) -------------
# The durable, downstream-facing projection of the promotion contract. Phase 3
# (evidence sufficiency) and Phase 4 (generated coverage) read this so promoted
# catalog-topic granularity is carried forward and cannot regress to broad-topic-only
# acceptance once a promoted topic has evidence.
PROMOTED_TOPIC_CONTRACT_SCHEMA_VERSION = "deepwiki-promoted-topic-contract-v1"
PROMOTED_TOPIC_CONTRACT_REL_PATH = os.path.join("plans", "promoted-topic-contract.json")


def build_promoted_topic_contract(report: AntiCompressionReport) -> dict:
    """A normalized, downstream-facing projection of the promotion contract.

    One row per promoted *leaf* catalog topic (``TIER_PAGE``) carrying the fields the
    downstream phases need: its ``catalog_topic_id``, family, whether it earned its own
    TER, the leaf pages that host it, and its plan-time status. Read-only — derived
    purely from the report; never edits the plan."""
    rows: list = []
    for r in report.promoted_topics:
        if r.tier != TIER_PAGE:
            continue
        rows.append({
            "catalog_topic_id": r.topic_id,
            "family": r.family,
            "tier": r.tier,
            "has_ter": r.has_ter,
            "leaf_pages": list(r.leaf_pages),
            "status": r.status,
        })
    rows.sort(key=lambda x: x["catalog_topic_id"])
    return {
        "schema_version": PROMOTED_TOPIC_CONTRACT_SCHEMA_VERSION,
        "mode": report.mode,
        "enforced": report.enforced,
        "source": "phase2-anti-compression-gate",
        "policy": report.policy,
        "counts": {
            "promoted_leaf_topics": report.promoted_leaf_topic_count,
            "covered": report.covered_topic_count,
            "uncovered": report.uncovered_topic_count,
        },
        "promoted_topics": rows,
    }


def load_promoted_topic_contract(plans_dir: str) -> dict | None:
    """Load ``plans/promoted-topic-contract.json`` from a plans directory, or ``None``
    when it is absent/unreadable (a deterministic miss the caller reports, never a
    crash). ``plans_dir`` is the directory that holds ``document-plan.json``."""
    from .. import util

    path = os.path.join(plans_dir, "promoted-topic-contract.json")
    if not os.path.isfile(path):
        return None
    try:
        return util.read_json(path)
    except (OSError, ValueError):
        return None


def promoted_catalog_topic_ids(contract: dict | None) -> set:
    """The set of promoted leaf ``catalog_topic_id`` values in a contract (empty when
    the contract is absent/malformed). The downstream granularity key."""
    if not isinstance(contract, dict):
        return set()
    out: set = set()
    for row in contract.get("promoted_topics") or []:
        if isinstance(row, dict):
            cid = row.get("catalog_topic_id")
            if isinstance(cid, str) and cid:
                out.add(cid)
    return out
