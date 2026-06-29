"""Phase F: catalog→plan→source→evidence→output traceability + artifact freshness.

After the expanded pipeline runs, this module proves the lineage the PRD requires
(UR-07 / QA-03): every blocking required topic / content block traces from a
source-derived **catalog topic** → a planned **page** → a selected **source handle**
→ retrieved **evidence ids** → a generated **markdown anchor / citation**. It writes:

- ``coverage/coverage-traceability.json`` (schema ``deepwiki-coverage-traceability-v1``)
- ``coverage/coverage-traceability-report.md``

It also enforces **artifact freshness** (PRD M-06 / BR-09 / VG-08): the relevant
source map records the catalog + plan fingerprints it consumed, so a downstream PASS
that was built from a stale plan/catalog/evidence/generated artifact **fails closed**
rather than silently passing. Benchmark material never enters this gate.

It is deterministic, LLM-free, network-free, read-only: it joins already-produced
artifacts (topic catalog, normalized plan, relevant source map, evidenced coverage,
generated coverage, citation manifest) and reports lineage + freshness; it never
edits an artifact, retrieves evidence, or generates output.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..util import read_json
from . import source_selection
from .page_planning import (
    TOPIC_DEFERRED,
    TOPIC_UNCOVERED,
    evaluate_page_planning,
)
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_INPUT_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    MODE_EXPANDED,
)

TRACEABILITY_SCHEMA_VERSION = "deepwiki-coverage-traceability-v1"
FAILURE_CATEGORY = "stale_or_incomplete_coverage_lineage"

# Per-row lineage statuses.
PLAN_PLANNED = "planned"
PLAN_DEFERRED = "deferred"
PLAN_UNCOVERED = "uncovered"


# --- data model ---------------------------------------------------------------
@dataclass
class TraceabilityRow:
    catalog_topic_id: str | None
    section_id: str | None
    content_block_id: str | None
    topic: str | None
    plan_status: str
    source_selection_status: str
    evidence_status: str
    generated_status: str
    source_handle_ids: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)
    markdown_path: str | None = None
    markdown_anchor: str | None = None
    citation_status: str = "n/a"
    deferral_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "catalog_topic_id": self.catalog_topic_id,
            "section_id": self.section_id,
            "content_block_id": self.content_block_id,
            "topic": self.topic,
            "plan_status": self.plan_status,
            "source_selection_status": self.source_selection_status,
            "evidence_status": self.evidence_status,
            "generated_status": self.generated_status,
            "source_handle_ids": list(self.source_handle_ids),
            "evidence_ids": list(self.evidence_ids),
            "markdown_path": self.markdown_path,
            "markdown_anchor": self.markdown_anchor,
            "citation_status": self.citation_status,
            "deferral_reason": self.deferral_reason,
        }


@dataclass
class FreshnessCheck:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class TraceabilityReport:
    schema_version: str
    status: str                                  # pass | fail
    failure_category: str | None
    catalog_fingerprint: str
    plan_fingerprint: str
    fresh: bool
    freshness: list = field(default_factory=list)        # FreshnessCheck
    rows: list = field(default_factory=list)             # TraceabilityRow
    diagnostics: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "failure_category": self.failure_category,
            "role": "coverage_traceability",
            "fingerprints": {
                "catalog": self.catalog_fingerprint,
                "plan": self.plan_fingerprint,
            },
            "fresh": self.fresh,
            "freshness": [c.to_dict() for c in self.freshness],
            "counts": dict(self.counts),
            "diagnostics": list(self.diagnostics),
            "rows": [r.to_dict() for r in self.rows],
        }


# --- artifact loading ---------------------------------------------------------
def load_traceability_inputs(bundle_dir: str) -> dict:
    """Read every artifact the traceability join consumes from ``bundle_dir``.

    Each value is the parsed dict/list, or ``None`` when the artifact is absent
    (the caller fails closed on a required missing input). Read-only."""
    def at(*p):
        path = os.path.join(bundle_dir, *p)
        return read_json(path) if os.path.isfile(path) else None

    sections_path = os.path.join(bundle_dir, "plans", "section-plans.jsonl")
    sections = None
    if os.path.isfile(sections_path):
        from .. import util
        sections = list(util.read_jsonl(sections_path))
    return {
        "catalog": at("derived", "topic-catalog.json"),
        "document_plan": at("plans", "document-plan.json"),
        "sections": sections,
        "source_map": at("plans", "relevant-source-map.json"),
        "evidenced": at("evidence", "evidenced-coverage.json"),
        "generated_coverage": at("wiki", "metadata", "generated-coverage.json"),
        "manifest": at("wiki", "metadata", "citation-manifest.json"),
        "document": at("wiki", "metadata", "document.json"),
    }


# --- freshness ----------------------------------------------------------------
def _freshness_checks(*, catalog, document_plan, sections, source_map, evidenced,
                      generated_coverage) -> list:
    """Deterministic artifact-freshness checks. A PASS report must have been built
    from the CURRENT catalog/plan/evidence/generated artifacts; a stale fingerprint
    or a non-enforced/failed upstream artifact fails closed."""
    checks: list = []
    cat_fp = (catalog or {}).get("source_fingerprint") or ""
    plan_fp = source_selection.plan_fingerprint(document_plan, sections or [])

    sm_cat = (source_map or {}).get("catalog_fingerprint")
    checks.append(FreshnessCheck(
        "source_map_matches_catalog", bool(source_map) and sm_cat == cat_fp,
        f"relevant-source-map catalog_fingerprint={sm_cat!r} vs current "
        f"catalog={cat_fp!r}"))
    sm_plan = (source_map or {}).get("plan_fingerprint")
    checks.append(FreshnessCheck(
        "source_map_matches_plan", bool(source_map) and sm_plan == plan_fp,
        f"relevant-source-map plan_fingerprint={sm_plan!r} vs current plan={plan_fp!r}"))
    ev_mode = (evidenced or {}).get("coverage_mode")
    checks.append(FreshnessCheck(
        "evidenced_enforced_pass",
        bool(evidenced) and ev_mode == MODE_EXPANDED
        and (evidenced or {}).get("status") == "pass",
        f"evidenced-coverage coverage_mode={ev_mode!r}, status="
        f"{(evidenced or {}).get('status')!r}"))
    gc_mode = (generated_coverage or {}).get("coverage_mode")
    checks.append(FreshnessCheck(
        "generated_enforced_pass",
        bool(generated_coverage) and gc_mode == MODE_EXPANDED
        and (generated_coverage or {}).get("status") == "pass",
        f"generated-coverage coverage_mode={gc_mode!r}, status="
        f"{(generated_coverage or {}).get('status')!r}"))
    return checks, cat_fp, plan_fp


# --- lineage join -------------------------------------------------------------
def _source_handles_by_topic(source_map) -> dict:
    """``(section_id, topic) -> [handle_id]`` from the relevant source map."""
    out: dict = {}
    for page in (source_map or {}).get("pages") or []:
        sid = page.get("section_id")
        for h in page.get("selected_handles") or []:
            for topic in h.get("topics") or []:
                out.setdefault((sid, topic), []).append(h.get("handle_id"))
    return out


def _handles_by_block(source_map) -> dict:
    """``(section_id, content_block_id) -> [handle_id]`` from the source map."""
    out: dict = {}
    for page in (source_map or {}).get("pages") or []:
        sid = page.get("section_id")
        for h in page.get("selected_handles") or []:
            for bid in h.get("content_block_ids") or []:
                out.setdefault((sid, bid), []).append(h.get("handle_id"))
    return out


def _generated_topic_index(generated_coverage) -> dict:
    """``(section_id, topic) -> generated row`` from the generated-coverage matrix."""
    out: dict = {}
    for sec in (generated_coverage or {}).get("sections") or []:
        sid = sec.get("section_id")
        for t in sec.get("topics") or []:
            out[(sid, t.get("topic"))] = t
    return out


def _generated_block_index(generated_coverage) -> dict:
    out: dict = {}
    for sec in (generated_coverage or {}).get("sections") or []:
        sid = sec.get("section_id")
        for b in sec.get("content_blocks") or []:
            out[(sid, b.get("content_block_id"))] = b
    return out


def _markdown_paths(document) -> dict:
    """``section_id -> markdown path`` from ``wiki/metadata/document.json`` (best
    effort; the section file is conventionally ``sections/<NNN>-<sid>.md``)."""
    out: dict = {}
    for p in (document or {}).get("section_paths") or []:
        base = os.path.basename(p)
        # strip the NNN- order prefix and .md suffix to recover the section id.
        stem = base[:-3] if base.endswith(".md") else base
        if "-" in stem and stem.split("-", 1)[0].isdigit():
            stem = stem.split("-", 1)[1]
        out[stem] = p
    return out


def build_traceability(*, catalog, document_plan, sections, source_map, evidenced,
                       generated_coverage, manifest, document=None
                       ) -> TraceabilityReport:
    """Join the expanded artifacts into a catalog→plan→source→evidence→output
    traceability report + freshness verdict. Deterministic; consumes parsed dicts so
    it is unit-testable without disk. Fails closed on a stale fingerprint, a
    non-enforced/failed upstream artifact, an uncovered high-signal catalog topic, or
    a generated obligation that was not covered."""
    checks, cat_fp, plan_fp = _freshness_checks(
        catalog=catalog, document_plan=document_plan, sections=sections,
        source_map=source_map, evidenced=evidenced,
        generated_coverage=generated_coverage)
    fresh = all(c.ok for c in checks)

    handles_by_topic = _source_handles_by_topic(source_map)
    handles_by_block = _handles_by_block(source_map)
    gen_topics = _generated_topic_index(generated_coverage)
    gen_blocks = _generated_block_index(generated_coverage)
    md_paths = _markdown_paths(document)
    manifest_ids = {c.get("evidence_id") for c in (manifest or {}).get("citations", [])}

    rows: list = []
    diagnostics: list = []

    # 1) deferred / uncovered catalog topics (lineage stops at the plan).
    pp = evaluate_page_planning(catalog, document_plan, sections or [],
                                mode=MODE_EXPANDED)
    for t in pp.catalog_topics:
        if t.coverage_status == TOPIC_DEFERRED:
            rows.append(TraceabilityRow(
                catalog_topic_id=t.topic_id, section_id=None, content_block_id=None,
                topic=None, plan_status=PLAN_DEFERRED,
                source_selection_status="n/a", evidence_status="n/a",
                generated_status="n/a", deferral_reason=t.deferral_reason))
        elif t.coverage_status == TOPIC_UNCOVERED:
            rows.append(TraceabilityRow(
                catalog_topic_id=t.topic_id, section_id=None, content_block_id=None,
                topic=None, plan_status=PLAN_UNCOVERED,
                source_selection_status="n/a", evidence_status="missing",
                generated_status="omitted"))
            diagnostics.append(
                f"catalog topic {t.topic_id!r} is uncovered (no plan/source/evidence/"
                "output lineage)")

    # 2) evidenced topics -> the main lineage spine.
    for sec in (evidenced or {}).get("sections") or []:
        sid = sec.get("section_id")
        for t in sec.get("topics") or []:
            if not t.get("required"):
                continue
            topic = t.get("topic")
            ev_status = t.get("status")
            g = gen_topics.get((sid, topic)) or {}
            gen_status = g.get("generated_status") or "omitted"
            anchor = g.get("markdown_anchor")
            ev_ids = list(t.get("mapped_evidence_ids") or [])
            handles = sorted(set(handles_by_topic.get((sid, topic), [])))
            cited = bool(g.get("cited")) and all(e in manifest_ids
                                                 for e in (g.get("evidence_ids") or []))
            citation_status = ("valid" if gen_status == "covered" and cited
                               else ("invalid" if gen_status == "invalid" else "n/a"))
            row = TraceabilityRow(
                catalog_topic_id=t.get("catalog_topic_id"), section_id=sid,
                content_block_id=t.get("content_block_id"), topic=topic,
                plan_status=PLAN_PLANNED,
                source_selection_status="selected" if handles else "not_selected",
                evidence_status=ev_status or "missing",
                generated_status=gen_status, source_handle_ids=handles,
                evidence_ids=ev_ids, markdown_path=md_paths.get(sid),
                markdown_anchor=anchor, citation_status=citation_status)
            rows.append(row)
            if ev_status == "sufficient" and gen_status != "covered":
                diagnostics.append(
                    f"{sid}/{topic!r}: evidenced sufficient but generated "
                    f"{gen_status} (broken lineage)")

    # 3) content-block lineage rows (expanded).
    for sec in (evidenced or {}).get("sections") or []:
        sid = sec.get("section_id")
        for b in sec.get("content_blocks") or []:
            bid = b.get("content_block_id")
            g = gen_blocks.get((sid, bid)) or {}
            gen_status = g.get("generated_status") or "omitted"
            handles = sorted(set(handles_by_block.get((sid, bid), [])))
            rows.append(TraceabilityRow(
                catalog_topic_id=None, section_id=sid, content_block_id=bid,
                topic=None, plan_status=PLAN_PLANNED,
                source_selection_status="selected" if handles else "not_selected",
                evidence_status=b.get("status") or "missing",
                generated_status=gen_status, source_handle_ids=handles,
                evidence_ids=list(g.get("evidence_ids") or []),
                markdown_path=md_paths.get(sid),
                markdown_anchor=g.get("markdown_anchor"),
                citation_status="valid" if gen_status == "covered" else "n/a"))
            if b.get("status") == "sufficient" and gen_status != "covered":
                diagnostics.append(
                    f"{sid}/block {bid!r}: evidenced sufficient but generated "
                    f"{gen_status} (broken lineage)")

    lineage_ok = not diagnostics
    status = "pass" if (fresh and lineage_ok) else "fail"
    counts = {
        "rows": len(rows),
        "planned": sum(1 for r in rows if r.plan_status == PLAN_PLANNED),
        "deferred": sum(1 for r in rows if r.plan_status == PLAN_DEFERRED),
        "uncovered": sum(1 for r in rows if r.plan_status == PLAN_UNCOVERED),
        "generated_covered": sum(1 for r in rows if r.generated_status == "covered"),
    }
    return TraceabilityReport(
        schema_version=TRACEABILITY_SCHEMA_VERSION, status=status,
        failure_category=FAILURE_CATEGORY if status == "fail" else None,
        catalog_fingerprint=cat_fp, plan_fingerprint=plan_fp, fresh=fresh,
        freshness=checks, rows=rows, diagnostics=diagnostics, counts=counts)


# --- the traceability gate ----------------------------------------------------
@dataclass
class TraceabilityGate:
    report: TraceabilityReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code,
                "report": self.report.to_dict()}

    def summary_lines(self) -> list:
        r = self.report
        lines = [
            f"traceability gate: {r.counts.get('rows', 0)} lineage row(s); "
            f"fresh={r.fresh}",
            f"traceability gate: catalog={r.catalog_fingerprint} "
            f"plan={r.plan_fingerprint}",
        ]
        for c in r.freshness:
            if not c.ok:
                lines.append(f"  - STALE [{c.name}]: {c.detail}")
        for d in r.diagnostics:
            lines.append(f"  - {d}")
        lines.append(f"traceability gate: {'PASS' if self.passed else 'FAIL'}")
        return lines


def gate_traceability(report: TraceabilityReport) -> TraceabilityGate:
    """Map a traceability report to a fail-closed gate (exit ``0`` pass / ``3`` fail).
    A stale fingerprint or a broken/uncovered lineage fails closed."""
    passed = report.status == "pass"
    return TraceabilityGate(
        report=report, passed=passed,
        exit_code=COVERAGE_GATE_PASS_EXIT if passed else COVERAGE_GATE_FAIL_EXIT)


def build_and_gate_from_bundle(bundle_dir: str):
    """Load the expanded artifacts from ``bundle_dir``, build traceability, and gate.

    Returns ``(report, gate)``. Raises ``FileNotFoundError`` when a required upstream
    artifact (catalog / plan / source map / evidenced / generated coverage) is absent
    so the caller fails closed (exit 2)."""
    inputs = load_traceability_inputs(bundle_dir)
    required = ("catalog", "document_plan", "sections", "source_map", "evidenced",
                "generated_coverage")
    missing = [k for k in required if not inputs.get(k)]
    if missing:
        raise FileNotFoundError(
            "missing required expanded artifact(s) for traceability: "
            + ", ".join(missing))
    report = build_traceability(
        catalog=inputs["catalog"], document_plan=inputs["document_plan"],
        sections=inputs["sections"], source_map=inputs["source_map"],
        evidenced=inputs["evidenced"],
        generated_coverage=inputs["generated_coverage"],
        manifest=inputs["manifest"] or {}, document=inputs["document"])
    return report, gate_traceability(report)


# --- markdown report ----------------------------------------------------------
def render_traceability_markdown(report: TraceabilityReport, *,
                                 title: str = "DeepWiki Coverage Traceability") -> str:
    """Render ``coverage/coverage-traceability-report.md``."""
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Status: **{report.status.upper()}**",
        f"- Fresh: **{report.fresh}**",
        f"- Catalog fingerprint: `{report.catalog_fingerprint or '(none)'}`",
        f"- Plan fingerprint: `{report.plan_fingerprint}`",
        f"- Rows: {report.counts.get('rows', 0)} "
        f"(planned {report.counts.get('planned', 0)}, deferred "
        f"{report.counts.get('deferred', 0)}, uncovered "
        f"{report.counts.get('uncovered', 0)})",
        "",
        "> Lineage: catalog topic → page → content block → source handle → evidence",
        "> ids → generated markdown anchor/citation. PASS requires fresh upstream",
        "> fingerprints and unbroken lineage; benchmark material is never an input.",
        "",
        "## Artifact freshness",
        "",
    ]
    for c in report.freshness:
        mark = "✅" if c.ok else "❌"
        lines.append(f"- {mark} `{c.name}` — {c.detail}")
    lines.append("")
    if report.diagnostics:
        lines += ["## Lineage diagnostics", ""]
        for d in report.diagnostics:
            lines.append(f"- {d}")
        lines.append("")
    lines += ["## Lineage rows", "",
              "| catalog topic | page | block | topic | plan | source | evidence | "
              "generated | citation |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in report.rows:
        lines.append(
            f"| `{r.catalog_topic_id or '—'}` | `{r.section_id or '—'}` | "
            f"`{r.content_block_id or '—'}` | {r.topic or '—'} | {r.plan_status} | "
            f"{r.source_selection_status} | {r.evidence_status} | "
            f"{r.generated_status} | {r.citation_status} |")
    return "\n".join(lines).rstrip() + "\n"
