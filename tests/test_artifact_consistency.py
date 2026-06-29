"""Phase F — non-live expanded artifact consistency, freshness, and E2E.

A deterministic, LLM-free, network-free end-to-end proof of the expanded artifact
chain WITHOUT any provider call. It builds a real bundle's expanded artifacts with
the production builders/evaluators —

  topic catalog  →  normalized plan  →  relevant source map (Phase C builder)
                 →  evidenced coverage (Phase D evaluator)  →  generated coverage
                 →  coverage traceability (Phase F builder/gate)

writes them to disk, and proves:

- the whole chain joins into a fresh, fully-traced PASS via the on-disk loader
  (``build_and_gate_from_bundle``);
- the relevant-source-map and traceability artifacts are byte-deterministic across
  rebuilds (no timestamps);
- a stale downstream artifact (a plan edited after the source map was written) fails
  the freshness gate CLOSED;
- a missing required upstream artifact fails closed (the command maps it to exit 2).

No Gemini/Vertex/API/network; no real Phase 1/2/3/4 command run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.evidence.evidenced_coverage import (  # noqa: E402
    evaluate_evidenced_coverage,
)
from wiki_generator.libs.evidence.options import EvidenceOptions  # noqa: E402

_PROFILE = "subsystem-deep-dive"


def _section(sid, *, catalog_id="doc.parsers", topic="parser flow"):
    return {
        "section_id": sid, "section_role": "source", "title": sid,
        "page_profile": _PROFILE, "parent_section_id": None,
        "catalog_topic_ids": [catalog_id],
        "required_content_blocks": [{"block_id": b}
                                    for b in cov.required_block_ids(_PROFILE)],
        "required_topics": [topic],
        "topic_evidence_requirements": [
            {"topic": topic, "required": True,
             "source_fields": ["retrieval_needs.files[0]"], "min_items": 1,
             "acceptable_lanes": ["file_anchor"],
             "catalog_topic_id": catalog_id, "content_block_id": "flow"}],
        "known_gaps": [],
        # three file handles so the subsystem-deep-dive profile floor (>=3 exact
        # citeable items) is satisfied by the retrieved evidence.
        "retrieval_needs": {"query_packs": [], "symbols": [],
                            "files": [{"path": f"{sid}_{i}.py"} for i in range(3)],
                            "contracts": [], "tests": [], "graph_nodes": [],
                            "search_hints": [], "context_artifacts": []},
    }


def _packet(sid):
    reqs = [{"lane": "file_anchor",
             "source_field": f"retrieval_needs.files[{i}]", "status": "covered",
             "candidate_count": 1, "kept_count": 1,
             "evidence_ids": [f"ev:{sid}:000{i + 1}"]} for i in range(3)]
    return {"section_id": sid, "lane_summary": {},
            "coverage": {"exact_requests": reqs}}


def _evidenced_matrix(sections):
    bundle = SimpleNamespace(
        section_order=[s["section_id"] for s in sections],
        section_by_id={s["section_id"]: s for s in sections})
    packets = [_packet(s["section_id"]) for s in sections]
    options = EvidenceOptions(bundle_root="/b", out_dir="/o", coverage_mode="expanded")
    return evaluate_evidenced_coverage(bundle, packets, options).matrix


def _generated_from_evidenced(evidenced):
    """Synthesize a consistent expanded generated-coverage matrix: every sufficient
    evidenced topic/block is covered with its mapped evidence (no live provider)."""
    sections = []
    for sec in evidenced["sections"]:
        sid = sec["section_id"]
        topics = []
        for t in sec.get("topics") or []:
            if t["status"] == "sufficient":
                topics.append({
                    "topic": t["topic"], "generated_status": "covered",
                    "evidence_ids": list(t.get("mapped_evidence_ids") or []),
                    "markdown_anchor": t["topic"].replace(" ", "-"), "cited": True})
        blocks = []
        for b in sec.get("content_blocks") or []:
            if b["status"] == "sufficient":
                blocks.append({
                    "content_block_id": b["content_block_id"],
                    "generated_status": "covered",
                    "evidence_ids": [f"ev:{sid}:0001"], "markdown_anchor": "flow"})
        sections.append({"section_id": sid, "topics": topics,
                         "content_blocks": blocks})
    return {"schema_version": "phase4-generated-coverage-v1",
            "coverage_mode": "expanded", "status": "pass", "sections": sections}


def _manifest(sections):
    return {"citations": [{"evidence_id": f"ev:{s['section_id']}:0001"}
                          for s in sections]}


def _write_bundle(tmp, sections):
    """Write a full set of consistent expanded artifacts to ``tmp``."""
    catalog = {"schema_version": "deepwiki-topic-catalog-v1",
               "source_fingerprint": "sha256:catfp",
               "topics": [{"topic_id": "doc.parsers", "parent_topic_id": None,
                           "family": "doc", "label": "Parsers",
                           "topic_kind": "subsystem", "priority": "must",
                           "signal_strength": "high", "status": "present"}]}
    document_plan = {"schema_version": "phase2-plan-v1",
                     "section_order": [s["section_id"] for s in sections]}
    source_map = cov.build_relevant_source_map(catalog, document_plan, sections)
    evidenced = _evidenced_matrix(sections)
    generated = _generated_from_evidenced(evidenced)

    util.write_json(os.path.join(tmp, "derived", "topic-catalog.json"), catalog)
    util.write_json(os.path.join(tmp, "plans", "document-plan.json"), document_plan)
    util.write_jsonl(os.path.join(tmp, "plans", "section-plans.jsonl"), sections)
    util.write_json(os.path.join(tmp, "plans", "relevant-source-map.json"),
                    source_map.to_dict())
    util.write_json(os.path.join(tmp, "evidence", "evidenced-coverage.json"),
                    evidenced)
    util.write_json(os.path.join(tmp, "wiki", "metadata", "generated-coverage.json"),
                    generated)
    util.write_json(os.path.join(tmp, "wiki", "metadata", "citation-manifest.json"),
                    _manifest(sections))
    util.write_json(os.path.join(tmp, "wiki", "metadata", "document.json"),
                    {"section_paths": [f"sections/00{i + 1}-{s['section_id']}.md"
                                       for i, s in enumerate(sections)]})
    return catalog, document_plan, source_map


class ExpandedArtifactE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="artifact_consistency_")
        self.sections = [_section("parsers"), _section("chunker",
                                                        catalog_id="doc.parsers",
                                                        topic="chunking strategy")]
        _write_bundle(self.tmp, self.sections)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_chain_passes(self):
        report, gate = cov.build_and_gate_from_bundle(self.tmp)
        self.assertTrue(gate.passed, report.diagnostics + [c.detail
                        for c in report.freshness if not c.ok])
        self.assertTrue(report.fresh)
        # the lineage reaches generated output for the planned topics.
        covered = [r for r in report.rows if r.generated_status == "covered"]
        self.assertTrue(covered)
        self.assertTrue(all(r.evidence_ids for r in covered if r.topic))

    def test_relevant_source_map_is_byte_deterministic(self):
        catalog = util.read_json(
            os.path.join(self.tmp, "derived", "topic-catalog.json"))
        document_plan = util.read_json(
            os.path.join(self.tmp, "plans", "document-plan.json"))
        a = cov.build_relevant_source_map(catalog, document_plan, self.sections)
        b = cov.build_relevant_source_map(catalog, document_plan, self.sections)
        self.assertEqual(json.dumps(a.to_dict(), sort_keys=True),
                         json.dumps(b.to_dict(), sort_keys=True))

    def test_traceability_is_byte_deterministic(self):
        r1, _ = cov.build_and_gate_from_bundle(self.tmp)
        r2, _ = cov.build_and_gate_from_bundle(self.tmp)
        self.assertEqual(json.dumps(r1.to_dict(), sort_keys=True),
                         json.dumps(r2.to_dict(), sort_keys=True))

    def test_stale_plan_fails_closed(self):
        # edit the normalized plan AFTER the source map was fingerprinted.
        path = os.path.join(self.tmp, "plans", "section-plans.jsonl")
        rows = list(util.read_jsonl(path))
        rows[0]["required_topics"] = rows[0]["required_topics"] + ["a new topic"]
        util.write_jsonl(path, rows)
        report, gate = cov.build_and_gate_from_bundle(self.tmp)
        self.assertFalse(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_FAIL_EXIT)
        self.assertFalse(report.fresh)

    def test_missing_required_artifact_fails_closed(self):
        os.remove(os.path.join(self.tmp, "evidence", "evidenced-coverage.json"))
        with self.assertRaises(FileNotFoundError):
            cov.build_and_gate_from_bundle(self.tmp)


if __name__ == "__main__":
    unittest.main()
