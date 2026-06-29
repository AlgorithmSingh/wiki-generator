"""Deterministic Phase 2 hierarchical page-planning gate (expanded coverage).

The planned-coverage gate (:mod:`.validate`) asks *"does the plan name every
mandatory topic family?"* and the topic-obligation gate (:mod:`.obligations`) asks
*"does every required topic carry a complete exact citeable evidence obligation?"*.
This module adds the **expanded (DeepWiki-style) hierarchical contract** the
``expanded`` coverage mode enforces, purely from the normalized plan and the Phase A
topic catalog, before Phase 3 retrieval:

1. **Hierarchy** — every ``parent_section_id`` resolves to a planned section, and
   the parent graph is acyclic (no page is its own ancestor).
2. **Page profile** — every normal source-evidence page declares a *valid* page
   profile (:mod:`.page_profiles`); an unknown profile is a plan defect.
3. **Content blocks** — a profile-bearing page declares every required content
   block of its profile (a broad page cannot silently drop a profile's flow / key
   files / API matrix block).
4. **Catalog coverage** — every high-signal (priority ``must``) catalog topic is
   either *planned* (named in some page's ``catalog_topic_ids[]``) or *explicitly
   deferred* (named in a page or document ``known_gaps[]`` with a source-derived
   reason). A broad parent page does **not** satisfy a child subsystem topic: each
   catalog topic id must be planned or deferred on its own (PRD BR-03).

It is **LLM-free, network-free, read-only**: it never edits the plan, never
synthesizes a page/profile/block, never downgrades a required topic, and never
invents a catalog topic. A defect is reported with an actionable remediation
pointing back at the LLM-authored Phase 2 plan / prompt / schema.

``expanded`` mode fails closed (a defect blocks before Phase 3, ``status == "fail"``,
exit ``3``, ``bad_underspecified_normalized_plan``); ``baseline``/``enhancement``
report the same matrix without gating (so the expanded contract never surprises an
existing baseline or enhancement run).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_docs import is_provenance_section
from . import page_profiles
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    MODE_ENHANCEMENT,
    _MODES,
    is_enforcing,
)

PAGE_PLANNING_SCHEMA_VERSION = "phase2-page-planning-v1"

# Same blocking category Phase 2/3 use, so the boundary speaks one language.
FAILURE_CATEGORY = "bad_underspecified_normalized_plan"

# Catalog-topic coverage statuses.
TOPIC_PLANNED = "planned"
TOPIC_DEFERRED = "deferred"
TOPIC_UNCOVERED = "uncovered"
TOPIC_OPTIONAL = "optional"   # a should/could catalog topic (reported, never blocks)

# Defect codes (one per distinct, actionable plan-shape defect).
CODE_UNRESOLVED_PARENT = "page_parent_section_unresolved"
CODE_HIERARCHY_CYCLE = "page_hierarchy_cycle"
CODE_MISSING_PROFILE = "page_missing_profile"
CODE_INVALID_PROFILE = "page_invalid_profile"
CODE_MISSING_CONTENT_BLOCK = "page_missing_required_content_block"
CODE_UNKNOWN_CATALOG_TOPIC_REF = "page_unknown_catalog_topic_ref"
CODE_UNCOVERED_CATALOG_TOPIC = "catalog_topic_not_planned_or_deferred"

# The catalog priority that makes a topic a blocking expanded-coverage obligation.
_BLOCKING_PRIORITY = "must"


# --- result model -------------------------------------------------------------
@dataclass
class PageDefect:
    """One page-planning defect on a section or catalog topic."""

    code: str
    detail: str
    remediation: str

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail,
                "remediation": self.remediation}


@dataclass
class PagePlanningSection:
    """A page's hierarchy/profile/content-block verdict."""

    section_id: str
    page_profile: str | None
    parent_section_id: str | None
    catalog_topic_ids: list = field(default_factory=list)
    status: str = "pass"                                  # pass | fail | not_applicable
    defects: list = field(default_factory=list)          # PageDefect

    @property
    def blocking(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id, "page_profile": self.page_profile,
            "parent_section_id": self.parent_section_id,
            "catalog_topic_ids": list(self.catalog_topic_ids),
            "status": self.status,
            "defects": [d.to_dict() for d in self.defects],
        }


@dataclass
class CatalogTopicCoverage:
    """Whether one catalog topic is planned, deferred, or uncovered by the plan."""

    topic_id: str
    label: str
    priority: str
    signal_strength: str
    topic_kind: str
    coverage_status: str                                 # planned | deferred | uncovered | optional
    planned_in: list = field(default_factory=list)       # section_ids
    deferral_reason: str | None = None

    @property
    def blocking(self) -> bool:
        return self.coverage_status == TOPIC_UNCOVERED

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id, "label": self.label,
            "priority": self.priority, "signal_strength": self.signal_strength,
            "topic_kind": self.topic_kind,
            "coverage_status": self.coverage_status,
            "planned_in": list(self.planned_in),
            "deferral_reason": self.deferral_reason,
        }


@dataclass
class PagePlanningReport:
    """A whole-plan hierarchical page-planning verdict."""

    schema_version: str
    mode: str
    status: str                                          # pass | fail
    enforced: bool
    failure_category: str | None
    catalog_present: bool
    section_count: int
    catalog_topic_count: int
    blocking_topic_count: int
    planned_topic_count: int
    deferred_topic_count: int
    uncovered_topic_count: int
    blocking_sections: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)      # actionable dicts
    sections: list = field(default_factory=list)         # PagePlanningSection
    catalog_topics: list = field(default_factory=list)   # CatalogTopicCoverage

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version, "mode": self.mode,
            "status": self.status, "enforced": self.enforced,
            "failure_category": self.failure_category,
            "catalog_present": self.catalog_present,
            "counts": {
                "sections": self.section_count,
                "catalog_topics": self.catalog_topic_count,
                "blocking_catalog_topics": self.blocking_topic_count,
                "planned": self.planned_topic_count,
                "deferred": self.deferred_topic_count,
                "uncovered": self.uncovered_topic_count,
            },
            "blocking_sections": list(self.blocking_sections),
            "diagnostics": list(self.diagnostics),
            "sections": [s.to_dict() for s in self.sections],
            "catalog_topics": [t.to_dict() for t in self.catalog_topics],
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
    """The text of every known-gap entry on a section (string or dict form)."""
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


def _detect_cycles(parent_of: dict) -> set:
    """The set of section ids that lie on a parent-pointer cycle (a page that is
    its own ancestor). Deterministic walk per node; a chain that revisits a node it
    has already touched on this walk is a cycle."""
    cyclic: set = set()
    for start in parent_of:
        seen: list = []
        node = start
        guard = 0
        while node is not None and guard <= len(parent_of):
            if node in seen:
                # everything from the first sighting of ``node`` onward is cyclic.
                idx = seen.index(node)
                cyclic.update(seen[idx:])
                break
            seen.append(node)
            node = parent_of.get(node)
            guard += 1
    return cyclic


# --- evaluation ---------------------------------------------------------------
def _eval_hierarchy(sections: list, planned_ids: set) -> dict:
    """Per-section hierarchy defects: unresolved parent + membership in a cycle."""
    parent_of: dict = {}
    for s in sections:
        sid = s.get("section_id")
        parent = s.get("parent_section_id")
        parent_of[sid] = parent if isinstance(parent, str) and parent in planned_ids else None
    cyclic = _detect_cycles(parent_of)

    defects: dict = {}
    for s in sections:
        sid = s.get("section_id")
        rows: list = []
        parent = s.get("parent_section_id")
        if isinstance(parent, str) and parent.strip() and parent not in planned_ids:
            rows.append(PageDefect(
                code=CODE_UNRESOLVED_PARENT,
                detail=(f"parent_section_id {parent!r} does not match any planned "
                        "section id"),
                remediation=("point parent_section_id at a real planned section_id "
                             "(the parent page must itself be planned), or drop the "
                             "parent link if this page is a root.")))
        if sid in cyclic:
            rows.append(PageDefect(
                code=CODE_HIERARCHY_CYCLE,
                detail="this page is its own ancestor (parent_section_id cycle)",
                remediation=("break the parent_section_id cycle so the page tree is "
                             "acyclic; a page cannot be a descendant of itself.")))
        defects[sid] = rows
    return defects


def _eval_profile_and_blocks(section: dict) -> list:
    """Page-profile validity + required content-block presence defects."""
    rows: list = []
    profile = section.get("page_profile")
    if not profile:
        rows.append(PageDefect(
            code=CODE_MISSING_PROFILE,
            detail="normal source page declares no page_profile",
            remediation=("assign a page_profile from the known set "
                         f"({', '.join(sorted(page_profiles.VALID_PROFILES))}); "
                         "every normal page needs a profile and its required "
                         "content blocks in expanded mode.")))
        return rows
    if not page_profiles.is_valid_profile(profile):
        rows.append(PageDefect(
            code=CODE_INVALID_PROFILE,
            detail=f"page_profile {profile!r} is not a known page profile",
            remediation=("use one of the known page profiles: "
                         f"{', '.join(sorted(page_profiles.VALID_PROFILES))}.")))
        return rows
    declared = {b.get("block_id") for b in _as_list(section.get("required_content_blocks"))
                if isinstance(b, dict) and b.get("block_id")}
    for block_id in page_profiles.required_block_ids(profile):
        if block_id not in declared:
            rows.append(PageDefect(
                code=CODE_MISSING_CONTENT_BLOCK,
                detail=(f"profile {profile!r} requires content block {block_id!r}, "
                        "which the page does not declare"),
                remediation=(f"add a required_content_blocks[] entry with block_id "
                             f"'{block_id}' for this {profile} page (the profile's "
                             "required blocks are "
                             f"{', '.join(page_profiles.required_block_ids(profile))}).")))
    return rows


def _eval_catalog_coverage(catalog_topics: list, sections: list) -> list:
    """Per-catalog-topic coverage verdict (planned / deferred / uncovered).

    A topic is *planned* when its exact ``topic_id`` appears in some page's
    ``catalog_topic_ids[]`` (a parent id never covers a child id — exact match
    only), *deferred* when its ``topic_id`` appears in some page/document
    known-gap text, else *uncovered*. Only ``must``-priority topics block."""
    planned_by_topic: dict = {}
    for s in sections:
        sid = s.get("section_id")
        for tid in _as_list(s.get("catalog_topic_ids")):
            if isinstance(tid, str) and tid:
                planned_by_topic.setdefault(tid, []).append(sid)

    gap_text_by_topic: dict = {}
    all_gap_strings: list = []
    for s in sections:
        all_gap_strings.extend(_known_gap_strings(s))

    def deferral_reason(topic_id: str) -> str | None:
        for g in all_gap_strings:
            if topic_id in g:
                return g
        return None

    out: list = []
    for t in catalog_topics:
        tid = t.get("topic_id")
        if not isinstance(tid, str) or not tid:
            continue
        priority = t.get("priority") or "could"
        planned_in = planned_by_topic.get(tid, [])
        if planned_in:
            status = TOPIC_PLANNED
            reason = None
        else:
            reason = deferral_reason(tid)
            if reason is not None:
                status = TOPIC_DEFERRED
            elif priority == _BLOCKING_PRIORITY:
                status = TOPIC_UNCOVERED
            else:
                status = TOPIC_OPTIONAL
        out.append(CatalogTopicCoverage(
            topic_id=tid, label=t.get("label") or tid, priority=priority,
            signal_strength=t.get("signal_strength") or "none",
            topic_kind=t.get("topic_kind") or "family",
            coverage_status=status, planned_in=sorted(planned_in),
            deferral_reason=reason))
    return out


def _eval_unknown_catalog_refs(section: dict, known_topic_ids: set) -> list:
    """A page that claims to cover a catalog topic id that does not exist."""
    rows: list = []
    if not known_topic_ids:
        return rows  # no catalog to validate against
    for tid in _as_list(section.get("catalog_topic_ids")):
        if isinstance(tid, str) and tid and tid not in known_topic_ids:
            rows.append(PageDefect(
                code=CODE_UNKNOWN_CATALOG_TOPIC_REF,
                detail=(f"catalog_topic_ids[] names {tid!r}, which is not a topic in "
                        "derived/topic-catalog.json"),
                remediation=("reference only catalog topic ids that exist in the "
                             "Phase A topic catalog; fix the typo or regenerate the "
                             "catalog from current Phase 1 artifacts.")))
    return rows


def evaluate_page_planning(catalog: dict | None, document_plan: dict | None,
                           sections: list, *, mode: str = MODE_ENHANCEMENT
                           ) -> PagePlanningReport:
    """Evaluate the hierarchical page-planning contract over a normalized plan.

    Deterministic and read-only. In an enforcing mode (``expanded``/``enhancement``)
    a defect on a normal source page, or a ``must``-priority catalog topic that is
    neither planned nor deferred, fails before Phase 3; ``baseline`` reports the same
    matrix without gating. ``catalog`` may be ``None`` (the catalog-coverage and
    unknown-ref dimensions are then skipped; the command decides whether an absent
    catalog is fatal in expanded mode).

    Raises ``ValueError`` for an unknown mode or non-list ``sections`` (mirrors
    :func:`.validate.evaluate_plan_coverage`)."""
    if mode not in _MODES:
        raise ValueError(f"unknown coverage mode {mode!r}; expected one of {_MODES}")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list of normalized section-plan dicts")

    enforced = is_enforcing(mode)
    planned_ids = {s.get("section_id") for s in sections if s.get("section_id")}
    catalog_topics = _catalog_topics(catalog)
    known_topic_ids = {t.get("topic_id") for t in catalog_topics if t.get("topic_id")}

    hierarchy_defects = _eval_hierarchy(sections, planned_ids)

    section_rows: list = []
    diagnostics: list = []
    blocking_sids: list = []
    for s in sections:
        sid = s.get("section_id") or "?"
        provenance = is_provenance_section(s)
        rows: list = list(hierarchy_defects.get(sid, []))
        if not provenance:
            rows += _eval_profile_and_blocks(s)
            rows += _eval_unknown_catalog_refs(s, known_topic_ids)

        if provenance:
            status = "not_applicable"
        elif enforced and rows:
            status = "fail"
        else:
            status = "pass"
        if rows and sid not in blocking_sids:
            blocking_sids.append(sid)
        for d in rows:
            diagnostics.append({"section_id": sid, "code": d.code,
                                "detail": d.detail, "remediation": d.remediation})
        section_rows.append(PagePlanningSection(
            section_id=sid, page_profile=s.get("page_profile"),
            parent_section_id=s.get("parent_section_id"),
            catalog_topic_ids=list(_as_list(s.get("catalog_topic_ids"))),
            status=status, defects=rows))

    topic_rows = _eval_catalog_coverage(catalog_topics, sections)
    uncovered = [t for t in topic_rows if t.coverage_status == TOPIC_UNCOVERED]
    for t in uncovered:
        diagnostics.append({
            "section_id": None, "code": CODE_UNCOVERED_CATALOG_TOPIC,
            "detail": (f"high-signal catalog topic {t.topic_id!r} ({t.label}, "
                       f"priority {t.priority}) is neither planned nor deferred"),
            "remediation": (f"plan a page for catalog topic '{t.topic_id}' (name it "
                            "in that page's catalog_topic_ids[]), or record an "
                            "explicit known_gaps[] entry naming this topic id with a "
                            "source-derived reason. A broad parent page does not "
                            "cover a child subsystem topic.")})

    planned = sum(1 for t in topic_rows if t.coverage_status == TOPIC_PLANNED)
    deferred = sum(1 for t in topic_rows if t.coverage_status == TOPIC_DEFERRED)
    blocking_topics = sum(1 for t in topic_rows
                          if t.priority == _BLOCKING_PRIORITY)

    section_blocking = enforced and bool(blocking_sids)
    topic_blocking = enforced and bool(uncovered)
    failed = section_blocking or topic_blocking
    return PagePlanningReport(
        schema_version=PAGE_PLANNING_SCHEMA_VERSION, mode=mode,
        status="fail" if failed else "pass", enforced=enforced,
        failure_category=FAILURE_CATEGORY if failed else None,
        catalog_present=isinstance(catalog, dict),
        section_count=len(section_rows), catalog_topic_count=len(topic_rows),
        blocking_topic_count=blocking_topics, planned_topic_count=planned,
        deferred_topic_count=deferred, uncovered_topic_count=len(uncovered),
        blocking_sections=sorted(blocking_sids), diagnostics=diagnostics,
        sections=section_rows, catalog_topics=topic_rows)


# --- the expanded-mode gate ---------------------------------------------------
@dataclass
class PagePlanningGate:
    """Verdict of the deterministic Phase 2 hierarchical page-planning gate.

    Like the other coverage gates it never edits/synthesizes/heals the plan: it
    reports the verdict and the exit code a caller fails on (``0`` pass, ``3``
    enforcing-mode fail)."""

    report: PagePlanningReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code,
                "report": self.report.to_dict()}

    def summary_lines(self) -> list:
        r = self.report
        lines = [
            f"page-planning gate: mode={r.mode} "
            f"({'enforced' if r.enforced else 'report-only'})",
            f"page-planning gate: catalog "
            + ("present" if r.catalog_present else "ABSENT (catalog-coverage check "
               "skipped)"),
            f"page-planning gate: {r.planned_topic_count} planned, "
            f"{r.deferred_topic_count} deferred, {r.uncovered_topic_count} uncovered "
            f"of {r.blocking_topic_count} high-signal catalog topic(s)",
        ]
        if r.blocking_sections:
            lines.append("page-planning gate: pages with hierarchy/profile/block "
                         "defects: " + ", ".join(r.blocking_sections))
        for d in r.diagnostics:
            where = d.get("section_id") or "(catalog)"
            lines.append(f"  - {where} [{d['code']}]: {d['remediation']}")
        verdict = "PASS" if self.passed else "FAIL"
        if not self.passed:
            lines.append(
                f"page-planning gate: {verdict} — the hierarchical page-plan contract "
                "is incomplete. This deterministic gate does NOT add pages, profiles, "
                "content blocks, or catalog coverage; fix the LLM-authored Phase 2 "
                "plan (stronger prompt/schema, or a bounded audited re-prompt) and "
                "re-run before Phase 3 retrieval.")
        else:
            lines.append(f"page-planning gate: {verdict}")
        return lines


def gate_page_planning(catalog: dict | None, document_plan: dict | None,
                       sections: list, *, mode: str = MODE_ENHANCEMENT
                       ) -> PagePlanningGate:
    """Evaluate ``sections`` against the hierarchical page-plan contract and map the
    verdict to a :class:`PagePlanningGate` (``exit_code`` ``0`` pass / ``3`` fail in
    an enforcing mode). It never mutates the plan."""
    report = evaluate_page_planning(catalog, document_plan, sections, mode=mode)
    passed = report.status == "pass"
    return PagePlanningGate(
        report=report, passed=passed,
        exit_code=COVERAGE_GATE_PASS_EXIT if passed else COVERAGE_GATE_FAIL_EXIT)


def render_page_planning_markdown(report: PagePlanningReport, *,
                                  title: str = "Phase 2 Hierarchical Page-Planning Gate"
                                  ) -> str:
    """Render the human-readable ``page-planning-report.md`` artifact."""
    verdict = "PASS" if report.status == "pass" else "FAIL"
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Mode: **{report.mode}** "
        f"({'enforced' if report.enforced else 'report-only'})",
        f"- Status: **{verdict}**",
        f"- Topic catalog: "
        + ("present" if report.catalog_present else "**absent**"),
        f"- High-signal catalog topics: {report.planned_topic_count} planned, "
        f"{report.deferred_topic_count} deferred, {report.uncovered_topic_count} "
        f"uncovered (of {report.blocking_topic_count}).",
        f"- Pages: {report.section_count}",
        "",
        "> Expanded coverage requires a hierarchical page plan: resolved acyclic",
        "> parent/child links, a valid page profile and its required content blocks",
        "> per page, and every high-signal catalog topic planned or explicitly",
        "> deferred (a broad parent page never covers a child subsystem topic).",
        "",
    ]
    if report.diagnostics:
        lines += ["## Defects", ""]
        for d in report.diagnostics:
            where = d.get("section_id") or "(catalog)"
            lines.append(f"### `{where}` — `{d['code']}`")
            lines.append("")
            lines.append(f"- {d['detail']}")
            lines.append(f"- Remediation: {d['remediation']}")
            lines.append("")
    else:
        lines += ["The hierarchical page-plan contract is complete.", ""]
    lines += ["## Catalog-topic coverage", "",
              "| topic | priority | signal | status | pages |",
              "|---|---|---|---|---|"]
    for t in report.catalog_topics:
        mark = {TOPIC_PLANNED: "✅ planned", TOPIC_DEFERRED: "🟡 deferred",
                TOPIC_UNCOVERED: "❌ uncovered",
                TOPIC_OPTIONAL: "— optional"}.get(t.coverage_status, t.coverage_status)
        pages = ", ".join(f"`{s}`" for s in t.planned_in) or "—"
        lines.append(f"| `{t.topic_id}` | {t.priority} | {t.signal_strength} | "
                     f"{mark} | {pages} |")
    return "\n".join(lines).rstrip() + "\n"
