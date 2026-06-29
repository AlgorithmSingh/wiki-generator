"""Phase C: deterministic per-page relevant-source map (expanded coverage).

Between Phase 2 normalization and Phase 3 retrieval, the ``expanded`` coverage mode
materializes a deterministic **relevant source map**: for every planned page, the
exact citeable source handles selected to ground it, mapped to the catalog topics and
content blocks they serve. It is the artifact PRD UR-04 / VG-03 require — *each page
has deterministic relevant files/symbols/spans/contracts/tests selected before
Phase 3 retrieval* — written to ``plans/relevant-source-map.json``.

Selection is **deterministic, LLM-free, network-free, read-only**. It draws ONLY
from the normalized plan's already-resolved exact lanes (``retrieval_needs.files``,
``.symbols``, ``.contracts``, ``.tests``, ``.query_packs``) — the same exact citeable
handles Phase 3 retrieves — plus the topic/content-block links the plan's
``topic_evidence_requirements[]`` declare. It never reads benchmark material, never
reads generated-wiki artifacts, never invents a handle, and never promotes broad
recall (``search_hints`` / ``graph_nodes``) to a citeable selected handle.

The map fingerprints the exact catalog and normalized plan it consumed, so a later
freshness gate (Phase F) can prove a downstream PASS used the current upstream
artifacts and fail closed on a stale map.

The source-selection gate fails closed (expanded mode) when a page's page-profile
evidence floor, a blocking required topic, or an evidence-bearing content block has
no citeable selected handle — a deterministic plan/substrate defect visible before
retrieval, reported with an actionable remediation. It never edits the plan.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..context_docs import is_provenance_section
from ..util import sha256_text
from . import page_profiles
from .obligations import (
    EXACT_FIELD_LANES,
    citeable_handle,
    enumerate_section_topics,
    parse_source_field,
    resolve_source_handle,
)
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    MODE_EXPANDED,
    _MODES,
    is_enforcing,
)

RELEVANT_SOURCE_MAP_SCHEMA_VERSION = "deepwiki-relevant-source-map-v1"
SOURCE_MAP_GATE_SCHEMA_VERSION = "phase2-source-selection-gate-v1"

# Same blocking category the rest of the Phase 2 → Phase 3 boundary speaks.
FAILURE_CATEGORY = "bad_underspecified_normalized_plan"

# Deterministic, documented per-lane base relevance weight (higher = a more precise
# citeable handle). Contracts/symbols are the most precise technical anchors; a
# query pack is the weakest exact lane. Bonuses below are also fixed integers, so
# the score is a pure function of the plan + substrate.
_LANE_WEIGHT = {
    "contract": 5, "symbol_anchor": 4, "file_anchor": 4, "test": 3, "query_pack": 2,
}
_TER_BONUS = 2        # the handle is named by a required topic's TER source field
_CITEABLE_BONUS = 1   # the substrate proved the handle citeable

# Source-map gate defect codes.
CODE_PAGE_NO_FLOOR_HANDLE = "page_no_citeable_floor_handle"
CODE_TOPIC_NO_HANDLE = "blocking_topic_no_citeable_selected_handle"
CODE_BLOCK_NO_HANDLE = "content_block_no_citeable_selected_handle"


# --- data model ---------------------------------------------------------------
@dataclass(frozen=True)
class SelectedHandle:
    """One exact citeable source handle selected for a page."""

    handle_id: str
    lane: str
    source_field: str
    path: str | None
    symbol: str | None
    catalog_topic_ids: tuple = field(default_factory=tuple)
    content_block_ids: tuple = field(default_factory=tuple)
    topics: tuple = field(default_factory=tuple)
    selection_reason: str = ""
    score: int = 0
    citeable: bool | None = None      # tri-state (None == undecidable lane / no corpus)

    def to_dict(self) -> dict:
        return {
            "handle_id": self.handle_id, "lane": self.lane,
            "source_field": self.source_field, "path": self.path,
            "symbol": self.symbol,
            "catalog_topic_ids": list(self.catalog_topic_ids),
            "content_block_ids": list(self.content_block_ids),
            "topics": list(self.topics),
            "selection_reason": self.selection_reason, "score": self.score,
            "citeable": self.citeable,
        }


@dataclass
class PageSourceSelection:
    """The selected source portfolio for one page."""

    section_id: str
    page_profile: str | None
    catalog_topic_ids: list = field(default_factory=list)
    selected_handles: list = field(default_factory=list)   # SelectedHandle

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id, "page_profile": self.page_profile,
            "catalog_topic_ids": list(self.catalog_topic_ids),
            "selected_handles": [h.to_dict() for h in self.selected_handles],
        }


@dataclass
class RelevantSourceMap:
    """The whole deterministic relevant-source map (one entry per planned page)."""

    schema_version: str
    plan_fingerprint: str
    catalog_fingerprint: str
    page_count: int
    handle_count: int
    pages: list = field(default_factory=list)              # PageSourceSelection

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "plan_fingerprint": self.plan_fingerprint,
            "catalog_fingerprint": self.catalog_fingerprint,
            "role": "source_selection",
            "citeable_as_evidence": False,
            "page_count": self.page_count,
            "handle_count": self.handle_count,
            "pages": [p.to_dict() for p in self.pages],
        }


# --- fingerprints -------------------------------------------------------------
def plan_fingerprint(document_plan: dict | None, sections: list) -> str:
    """A deterministic fingerprint over the normalized plan the map consumed.

    Covers the section ids + the retrieval/obligation/hierarchy fields the source
    selection reads, so a downstream freshness gate can detect a map built from a
    different plan. Timestamp-free and stable across runs."""
    basis = [{
        "section_id": s.get("section_id"),
        "page_profile": s.get("page_profile"),
        "parent_section_id": s.get("parent_section_id"),
        "catalog_topic_ids": s.get("catalog_topic_ids") or [],
        "required_topics": s.get("required_topics") or [],
        "topic_evidence_requirements": s.get("topic_evidence_requirements") or [],
        "required_content_blocks": s.get("required_content_blocks") or [],
        "retrieval_needs": s.get("retrieval_needs") or {},
    } for s in sections]
    payload = json.dumps(basis, sort_keys=True, ensure_ascii=False)
    return "sha256:" + sha256_text(payload)


def _catalog_fingerprint(catalog: dict | None) -> str:
    if isinstance(catalog, dict):
        fp = catalog.get("source_fingerprint")
        if isinstance(fp, str) and fp:
            return fp
    return ""


# --- selection ----------------------------------------------------------------
def _ter_links_for_handle(section: dict, source_field: str):
    """``(catalog_topic_ids, content_block_ids, topics, ter_referenced)`` linking a
    handle's ``source_field`` to the topics/blocks its TERs ground it for."""
    cat_ids: list = []
    block_ids: list = []
    topics: list = []
    referenced = False
    for topic, ter, required in enumerate_section_topics(section):
        if not isinstance(ter, dict):
            continue
        if source_field not in (ter.get("source_fields") or []):
            continue
        referenced = referenced or bool(required)
        if topic not in topics:
            topics.append(topic)
        cid = ter.get("catalog_topic_id")
        if cid and cid not in cat_ids:
            cat_ids.append(cid)
        bid = ter.get("content_block_id")
        if bid and bid not in block_ids:
            block_ids.append(bid)
    return cat_ids, block_ids, topics, referenced


def select_page_sources(section: dict, *, substrate=None) -> PageSourceSelection:
    """Deterministically select a page's exact citeable source handles.

    One :class:`SelectedHandle` per resolved exact lane item, scored by lane weight
    + TER reference + citeability, and mapped to the catalog topics / content blocks
    its TERs declare. Sorted by descending score then ``source_field`` for a stable
    portfolio."""
    sid = section.get("section_id") or "?"
    needs = section.get("retrieval_needs") or {}
    handles: list = []
    seq = 0
    for field_name, lane in EXACT_FIELD_LANES.items():
        items = needs.get(field_name)
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            source_field = f"retrieval_needs.{field_name}[{idx}]"
            handle = resolve_source_handle(section, field_name, idx)
            cite = citeable_handle(substrate, lane, handle)
            cat_ids, block_ids, topics, ter_referenced = _ter_links_for_handle(
                section, source_field)
            score = _LANE_WEIGHT.get(lane, 1)
            reasons = [f"exact {lane} handle"]
            if ter_referenced:
                score += _TER_BONUS
                reasons.append("named by a required topic obligation")
            if cite is True:
                score += _CITEABLE_BONUS
                reasons.append("citeable in retrieval substrate")
            path = handle if field_name in ("files", "tests") else None
            symbol = handle if field_name == "symbols" else None
            handles.append(SelectedHandle(
                handle_id=f"{sid}:{field_name}:{idx}", lane=lane,
                source_field=source_field, path=path, symbol=symbol,
                catalog_topic_ids=tuple(cat_ids),
                content_block_ids=tuple(block_ids), topics=tuple(topics),
                selection_reason="; ".join(reasons), score=score, citeable=cite))
            seq += 1
    handles.sort(key=lambda h: (-h.score, h.source_field))
    return PageSourceSelection(
        section_id=sid, page_profile=section.get("page_profile"),
        catalog_topic_ids=list(section.get("catalog_topic_ids") or []),
        selected_handles=handles)


def build_relevant_source_map(catalog: dict | None, document_plan: dict | None,
                              sections: list, *, substrate=None) -> RelevantSourceMap:
    """Build the deterministic relevant-source map for every planned page.

    Pure and deterministic: identical plan + catalog + substrate → byte-identical
    map. ``substrate`` (optional :class:`~.substrate.CiteableSubstrate`) decides
    file/test citeability; without it those lanes are recorded ``citeable: null``
    (undecidable) and never produce a false non-citeable failure."""
    if not isinstance(sections, list):
        raise ValueError("sections must be a list of normalized section-plan dicts")
    pages = [select_page_sources(s, substrate=substrate) for s in sections]
    handle_count = sum(len(p.selected_handles) for p in pages)
    return RelevantSourceMap(
        schema_version=RELEVANT_SOURCE_MAP_SCHEMA_VERSION,
        plan_fingerprint=plan_fingerprint(document_plan, sections),
        catalog_fingerprint=_catalog_fingerprint(catalog),
        page_count=len(pages), handle_count=handle_count, pages=pages)


# --- source-selection gate ----------------------------------------------------
@dataclass
class SourceMapDiagnostic:
    section_id: str
    code: str
    detail: str
    remediation: str

    def to_dict(self) -> dict:
        return {"section_id": self.section_id, "code": self.code,
                "detail": self.detail, "remediation": self.remediation}


@dataclass
class SourceMapGateReport:
    schema_version: str
    mode: str
    status: str
    enforced: bool
    failure_category: str | None
    page_count: int
    handle_count: int
    blocking_sections: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version, "mode": self.mode,
            "status": self.status, "enforced": self.enforced,
            "failure_category": self.failure_category,
            "counts": {"pages": self.page_count, "handles": self.handle_count},
            "blocking_sections": list(self.blocking_sections),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def _page_floor_defect(page: PageSourceSelection) -> SourceMapDiagnostic | None:
    """The page-profile evidence-floor check: a profile-bearing page must carry ≥1
    citeable selected handle in one of its profile's floor lanes."""
    floor = page_profiles.profile_evidence_floor(page.page_profile)
    if not floor:
        return None  # unknown profile / glossary (no exact floor)
    for h in page.selected_handles:
        if h.lane in floor and h.citeable is not False:
            return None
    return SourceMapDiagnostic(
        section_id=page.section_id, code=CODE_PAGE_NO_FLOOR_HANDLE,
        detail=(f"page profile {page.page_profile!r} requires a citeable exact handle "
                f"in one of {sorted(floor)}, but no selected handle qualifies"),
        remediation=("add an exact citeable handle in a profile-floor lane "
                     f"({', '.join(floor)}) to this page's evidence_needs, or change "
                     "the page profile to match the evidence the repository supports."))


def _block_defects(section: dict, page: PageSourceSelection) -> list:
    """Per evidence-bearing content block that is TER-linked: require ≥1 citeable
    selected handle mapped to it. A block no TER references is left to the page floor
    + topic checks (reported, not failed here — the plan declared no exact link)."""
    profile = page.page_profile
    evidence_blocks = set(page_profiles.evidence_block_ids(profile))
    if not evidence_blocks:
        return []
    citeable_by_block: dict = {}
    linked_blocks: set = set()
    for h in page.selected_handles:
        for bid in h.content_block_ids:
            linked_blocks.add(bid)
            if h.citeable is not False:
                citeable_by_block[bid] = citeable_by_block.get(bid, 0) + 1
    out: list = []
    for bid in sorted(linked_blocks & evidence_blocks):
        if citeable_by_block.get(bid, 0) == 0:
            out.append(SourceMapDiagnostic(
                section_id=page.section_id, code=CODE_BLOCK_NO_HANDLE,
                detail=(f"content block {bid!r} is linked by a topic obligation but "
                        "no citeable selected handle grounds it"),
                remediation=(f"point a topic_evidence_requirements[] row "
                             f"(content_block_id '{bid}') at an exact citeable "
                             "retrieval_needs.* handle, or improve Phase 1 indexing so "
                             "the linked handle is chunked.")))
    return out


def _topic_defects(section: dict, page: PageSourceSelection) -> list:
    """Per blocking required topic: require ≥1 citeable selected handle mapped to it
    via its TER source fields. (Reinforces the obligation gate at the selection
    level; usually already satisfied once the obligation gate passes.)"""
    citeable_topics: set = set()
    for h in page.selected_handles:
        if h.citeable is not False:
            citeable_topics.update(h.topics)
    out: list = []
    for topic, ter, required in enumerate_section_topics(section):
        if not required or not isinstance(ter, dict):
            continue
        if topic not in citeable_topics:
            out.append(SourceMapDiagnostic(
                section_id=page.section_id, code=CODE_TOPIC_NO_HANDLE,
                detail=(f"required topic {topic!r} has no citeable selected source "
                        "handle"),
                remediation=("point this topic's topic_evidence_requirements[] "
                             "source_fields[] at an exact citeable retrieval_needs.* "
                             "handle that the source map selects.")))
    return out


def gate_source_map(source_map: RelevantSourceMap, sections: list, *,
                    mode: str = MODE_EXPANDED) -> "SourceMapGate":
    """Evaluate the relevant-source map and map the verdict to a gate.

    Deterministic and read-only. In an enforcing mode a page whose profile floor,
    blocking topic, or evidence-bearing content block lacks a citeable selected
    handle fails before Phase 3 (``exit_code`` ``3``); ``baseline`` reports without
    gating."""
    if mode not in _MODES:
        raise ValueError(f"unknown coverage mode {mode!r}; expected one of {_MODES}")
    enforced = is_enforcing(mode)
    page_by_id = {p.section_id: p for p in source_map.pages}
    diagnostics: list = []
    blocking: list = []
    for section in sections:
        sid = section.get("section_id") or "?"
        if is_provenance_section(section):
            continue
        page = page_by_id.get(sid)
        if page is None:
            continue
        rows: list = []
        floor = _page_floor_defect(page)
        if floor is not None:
            rows.append(floor)
        rows += _block_defects(section, page)
        rows += _topic_defects(section, page)
        if rows and sid not in blocking:
            blocking.append(sid)
        diagnostics.extend(rows)

    failed = enforced and bool(blocking)
    report = SourceMapGateReport(
        schema_version=SOURCE_MAP_GATE_SCHEMA_VERSION, mode=mode,
        status="fail" if failed else "pass", enforced=enforced,
        failure_category=FAILURE_CATEGORY if failed else None,
        page_count=source_map.page_count, handle_count=source_map.handle_count,
        blocking_sections=sorted(blocking), diagnostics=diagnostics)
    return SourceMapGate(
        report=report, passed=not failed,
        exit_code=COVERAGE_GATE_PASS_EXIT if not failed else COVERAGE_GATE_FAIL_EXIT)


@dataclass
class SourceMapGate:
    """Verdict of the deterministic Phase C source-selection gate."""

    report: SourceMapGateReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code,
                "report": self.report.to_dict()}

    def summary_lines(self) -> list:
        r = self.report
        lines = [
            f"source-selection gate: mode={r.mode} "
            f"({'enforced' if r.enforced else 'report-only'})",
            f"source-selection gate: {r.handle_count} selected handle(s) across "
            f"{r.page_count} page(s)",
        ]
        if r.blocking_sections:
            lines.append("source-selection gate: pages missing a citeable selected "
                         "handle: " + ", ".join(r.blocking_sections))
            for d in r.diagnostics:
                lines.append(f"  - {d.section_id} [{d.code}]: {d.remediation}")
        verdict = "PASS" if self.passed else "FAIL"
        if not self.passed:
            lines.append(
                f"source-selection gate: {verdict} — a page floor / topic / content "
                "block has no citeable selected source handle. This deterministic gate "
                "does NOT add handles; fix the Phase 2 plan/evidence_needs or Phase 1 "
                "indexing and re-run before Phase 3 retrieval.")
        else:
            lines.append(f"source-selection gate: {verdict}")
        return lines


def render_source_map_markdown(source_map: RelevantSourceMap,
                               gate: "SourceMapGate | None" = None, *,
                               title: str = "Phase 2 Relevant Source Map") -> str:
    """Render the human-readable ``relevant-source-map-report.md`` artifact."""
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{source_map.schema_version}`",
        f"- Plan fingerprint: `{source_map.plan_fingerprint}`",
        f"- Catalog fingerprint: `{source_map.catalog_fingerprint or '(none)'}`",
        f"- Pages: {source_map.page_count}; selected handles: {source_map.handle_count}",
        "",
        "> Deterministic per-page source selection from the normalized plan's exact",
        "> citeable lanes. Selection is planner context for retrieval; final claims",
        "> still cite Phase 3 EvidencePacket ids. Benchmark/generated-wiki artifacts",
        "> are never source-map inputs.",
        "",
    ]
    if gate is not None:
        lines.append(f"- Source-selection gate: "
                     f"**{'PASS' if gate.passed else 'FAIL'}** "
                     f"({'enforced' if gate.report.enforced else 'report-only'})")
        lines.append("")
        if gate.report.diagnostics:
            lines += ["## Source-selection defects", ""]
            for d in gate.report.diagnostics:
                lines.append(f"- `{d.section_id}` [`{d.code}`]: {d.detail} — "
                             f"{d.remediation}")
            lines.append("")
    lines += ["## Per-page selected handles", ""]
    for p in source_map.pages:
        lines.append(f"### `{p.section_id}` "
                     f"(profile `{p.page_profile or '—'}`)")
        lines.append("")
        if not p.selected_handles:
            lines.append("_no exact citeable handles selected_")
            lines.append("")
            continue
        lines.append("| handle | lane | source_field | citeable | score | topics |")
        lines.append("|---|---|---|---|---|---|")
        for h in p.selected_handles:
            ref = h.path or h.symbol or "—"
            cite = {True: "yes", False: "no", None: "n/a"}[h.citeable]
            topics = ", ".join(h.topics) or "—"
            lines.append(f"| `{ref}` | {h.lane} | `{h.source_field}` | {cite} | "
                         f"{h.score} | {topics} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
