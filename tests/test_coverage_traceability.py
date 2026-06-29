"""Phase F — coverage traceability + artifact freshness.

Deterministic, LLM-free, network-free tests for ``coverage.traceability``:

- ``build_traceability`` joins catalog → plan → relevant source map → evidenced
  coverage → generated coverage → citation manifest into per-topic / per-content-block
  lineage rows (catalog topic → page → block → source handle → evidence → anchor →
  citation);
- a fresh, fully-traced expanded run PASSES; a stale plan/catalog fingerprint, a
  non-enforced/failed upstream artifact, a broken lineage (evidenced sufficient but
  generated omitted), or an uncovered high-signal catalog topic FAILS CLOSED;
- deferred catalog topics surface as deferred lineage rows (with their reason) and do
  not break the gate.

No Gemini/Vertex/API/network.
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402

_CAT_FP = "sha256:catalogfp"


def _catalog(*topics):
    return {"schema_version": "deepwiki-topic-catalog-v1",
            "source_fingerprint": _CAT_FP, "topics": list(topics)}


def _topic(tid, *, priority="must"):
    return {"topic_id": tid, "parent_topic_id": None, "family": tid.split(".")[0],
            "label": tid, "topic_kind": "subsystem", "priority": priority,
            "signal_strength": "high", "status": "present"}


def _section(sid, *, catalog_ids=("doc.parsers",), topic="flow", block="flow",
             known_gaps=()):
    return {
        "section_id": sid, "section_role": "source", "title": sid,
        "page_profile": "subsystem-deep-dive", "parent_section_id": None,
        "catalog_topic_ids": list(catalog_ids),
        "required_content_blocks": [
            {"block_id": b} for b in cov.required_block_ids("subsystem-deep-dive")],
        "required_topics": [topic],
        "topic_evidence_requirements": [
            {"topic": topic, "required": True,
             "source_fields": ["retrieval_needs.files[0]"], "min_items": 1,
             "acceptable_lanes": ["file_anchor"],
             "catalog_topic_id": list(catalog_ids)[0] if catalog_ids else None,
             "content_block_id": block}],
        "known_gaps": list(known_gaps),
        "retrieval_needs": {"files": [{"path": "a.py"}]},
    }


def _doc(section_ids):
    return {"schema_version": "phase2-plan-v1", "section_order": list(section_ids)}


def _source_map(document_plan, sections, *, plan_fp=None, catalog_fp=_CAT_FP):
    return {
        "schema_version": "deepwiki-relevant-source-map-v1",
        "plan_fingerprint": plan_fp if plan_fp is not None
        else cov.plan_fingerprint(document_plan, sections),
        "catalog_fingerprint": catalog_fp,
        "pages": [{"section_id": s["section_id"], "selected_handles": [
            {"handle_id": f"{s['section_id']}:files:0", "lane": "file_anchor",
             "path": "a.py",
             "catalog_topic_ids": list(s.get("catalog_topic_ids") or []),
             "content_block_ids": ["flow"], "topics": ["flow"]}]}
            for s in sections]}


def _evidenced(sid, *, status="pass", topic_status="sufficient",
               block_status="sufficient"):
    return {"schema_version": "phase3-evidenced-coverage-v1",
            "coverage_mode": "expanded", "enforced": True, "status": status,
            "sections": [{"section_id": sid, "topics": [
                {"topic": "flow", "required": True, "status": topic_status,
                 "catalog_topic_id": "doc.parsers", "content_block_id": "flow",
                 "mapped_evidence_ids": ["ev:sub:0001"]}],
                "content_blocks": [{"content_block_id": "flow",
                                    "status": block_status, "topics": ["flow"]}]}]}


def _generated(sid, *, status="pass", topic_status="covered", block_status="covered"):
    return {"schema_version": "phase4-generated-coverage-v1",
            "coverage_mode": "expanded", "status": status,
            "sections": [{"section_id": sid, "topics": [
                {"topic": "flow", "generated_status": topic_status,
                 "evidence_ids": ["ev:sub:0001"], "markdown_anchor": "flow",
                 "cited": True}],
                "content_blocks": [{"content_block_id": "flow",
                                    "generated_status": block_status,
                                    "evidence_ids": ["ev:sub:0001"],
                                    "markdown_anchor": "flow"}]}]}


def _manifest():
    return {"citations": [{"evidence_id": "ev:sub:0001"}]}


def _build(*, catalog=None, sections=None, source_map=None, evidenced=None,
           generated=None, manifest=None):
    sections = sections if sections is not None else [_section("sub")]
    document_plan = _doc([s["section_id"] for s in sections])
    catalog = catalog if catalog is not None else _catalog(_topic("doc.parsers"))
    source_map = (source_map if source_map is not None
                  else _source_map(document_plan, sections))
    evidenced = evidenced if evidenced is not None else _evidenced("sub")
    generated = generated if generated is not None else _generated("sub")
    return cov.build_traceability(
        catalog=catalog, document_plan=document_plan, sections=sections,
        source_map=source_map, evidenced=evidenced, generated_coverage=generated,
        manifest=manifest if manifest is not None else _manifest())


# ===========================================================================
class TraceabilityLineageTests(unittest.TestCase):
    def test_full_lineage_passes(self):
        report = _build()
        self.assertEqual(report.status, "pass", report.diagnostics)
        self.assertTrue(report.fresh)
        gate = cov.gate_traceability(report)
        self.assertTrue(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_PASS_EXIT)

    def test_row_links_full_chain(self):
        report = _build()
        row = next(r for r in report.rows if r.topic == "flow")
        self.assertEqual(row.catalog_topic_id, "doc.parsers")
        self.assertEqual(row.section_id, "sub")
        self.assertEqual(row.content_block_id, "flow")
        self.assertEqual(row.source_handle_ids, ["sub:files:0"])
        self.assertEqual(row.evidence_ids, ["ev:sub:0001"])
        self.assertEqual(row.generated_status, "covered")
        self.assertEqual(row.markdown_anchor, "flow")
        self.assertEqual(row.citation_status, "valid")


class FreshnessTests(unittest.TestCase):
    def test_stale_plan_fingerprint_fails(self):
        sections = [_section("sub")]
        document_plan = _doc(["sub"])
        sm = _source_map(document_plan, sections, plan_fp="sha256:STALE")
        report = _build(sections=sections, source_map=sm)
        self.assertFalse(report.fresh)
        self.assertEqual(report.status, "fail")
        self.assertFalse(cov.gate_traceability(report).passed)
        self.assertTrue(any(c.name == "source_map_matches_plan" and not c.ok
                            for c in report.freshness))

    def test_stale_catalog_fingerprint_fails(self):
        sections = [_section("sub")]
        document_plan = _doc(["sub"])
        sm = _source_map(document_plan, sections, catalog_fp="sha256:OLDCAT")
        report = _build(sections=sections, source_map=sm)
        self.assertFalse(report.fresh)
        self.assertEqual(report.status, "fail")

    def test_evidenced_report_only_fails(self):
        ev = _evidenced("sub")
        ev["coverage_mode"] = "baseline"      # not enforced/expanded
        report = _build(evidenced=ev)
        self.assertFalse(report.fresh)
        self.assertEqual(report.status, "fail")

    def test_generated_failed_fails(self):
        gc = _generated("sub", status="fail")
        report = _build(generated=gc)
        self.assertEqual(report.status, "fail")


class LineageBreakTests(unittest.TestCase):
    def test_sufficient_but_omitted_is_broken(self):
        gc = _generated("sub", topic_status="omitted")
        report = _build(generated=gc)
        self.assertEqual(report.status, "fail")
        self.assertTrue(any("broken lineage" in d for d in report.diagnostics))

    def test_uncovered_catalog_topic_fails(self):
        catalog = _catalog(_topic("doc.parsers"), _topic("frontend"))
        report = _build(catalog=catalog)            # frontend never planned
        self.assertEqual(report.status, "fail")
        uncovered = [r for r in report.rows if r.plan_status == "uncovered"]
        self.assertTrue(any(r.catalog_topic_id == "frontend" for r in uncovered))

    def test_deferred_catalog_topic_passes_with_reason(self):
        catalog = _catalog(_topic("doc.parsers"), _topic("frontend"))
        sections = [_section("sub",
                             known_gaps=["frontend has no source in this snapshot"])]
        report = _build(catalog=catalog, sections=sections)
        self.assertEqual(report.status, "pass", report.diagnostics)
        deferred = next(r for r in report.rows if r.plan_status == "deferred")
        self.assertEqual(deferred.catalog_topic_id, "frontend")
        self.assertIsNotNone(deferred.deferral_reason)


if __name__ == "__main__":
    unittest.main()
