"""Milestone 2 — Phase 2 topic-obligation completeness gate.

Deterministic, LLM-free, network-free tests for the new Phase 2 → Phase 3
obligation-alignment boundary: ``coverage.gate_topic_obligations`` and its wiring
inside ``normalize-plan --coverage-mode enhancement``.

Reproduces the live RAGFlow enhancement-run failure pattern WITHOUT copying bulky
live artifacts: the planner authored ``coverage_requirements[]`` that normalization
merges into ``required_topics[]``, but only authored ``topic_evidence_requirements[]``
for the originally-authored ``required_topics[]`` — so merged required topics reached
Phase 3 with no exact citeable evidence obligation and failed closed after retrieval.

Proves the next-slice acceptance:

- a normalized source section whose required_topics[] entry lacks a matching
  topic_evidence_requirements[] row FAILS before Phase 3 (exit 3,
  ``bad_underspecified_normalized_plan``) — including a topic merged from
  coverage_requirements[];
- a required topic supported only by broad recall (search_hints/graph_nodes) or by
  source_fields referencing a nonexistent retrieval_needs entry FAILS before Phase 3;
- an acceptable_lanes[] with no exact citeable lane FAILS before Phase 3;
- an expanded hierarchical plan where every normalized required topic has exact
  citeable source-field obligations PASSES both the family-coverage gate and the
  obligation gate (family gate stays green while only the obligation gate flips);
- baseline/default mode stays non-breaking / report-only;
- the gate never synthesizes/repairs the plan;
- the obligation enumeration is shared with the Phase 3 evidenced-coverage consumer,
  so producer and checker cannot drift.

No Gemini/Vertex/API/network; no real Phase 1/3/4 pipeline run.
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
from wiki_generator.libs.commands import normalize_plan as normalize_plan_cmd  # noqa: E402
from wiki_generator.libs.evidence import evidenced_coverage as ec  # noqa: E402
from wiki_generator.libs.plan_normalization import normalize, parse, repair  # noqa: E402
from wiki_generator.libs.plan_normalization.lookups import Lookups  # noqa: E402

_TOPIC_FILE = "src/app.py"


# ---------------------------------------------------------------------------
# Hand-written *normalized* sections for the pure evaluator (full control over
# retrieval_needs shape + topic_evidence_requirements).
def _section(sid, *, required_topics=(), ters=(), needs=None, role="source"):
    return {
        "section_id": sid, "section_role": role,
        "required_topics": list(required_topics),
        "topic_evidence_requirements": list(ters),
        "retrieval_needs": needs or {},
    }


def _ter(topic, source_fields, *, required=True, min_items=1, acceptable_lanes=None):
    return {
        "topic": topic, "required": required, "source_fields": list(source_fields),
        "min_items": min_items,
        "acceptable_lanes": list(acceptable_lanes) if acceptable_lanes is not None
        else ["file_anchor", "symbol_anchor", "contract", "test", "query_pack"],
    }


def _needs(**lanes):
    base = {"query_packs": [], "symbols": [], "files": [], "contracts": [],
            "tests": [], "graph_nodes": [], "search_hints": [], "context_artifacts": []}
    base.update(lanes)
    return base


def _topic_row(report, sid, topic):
    sec = next(s for s in report.sections if s.section_id == sid)
    return next(t for t in sec.topics if t.topic == topic)


class ObligationEvaluatorUnitTests(unittest.TestCase):
    """Pure ``evaluate_topic_obligations`` over hand-written normalized sections."""

    def _gate(self, sections, mode=cov.MODE_ENHANCEMENT):
        return cov.gate_topic_obligations(None, sections, mode=mode)

    def test_complete_obligation_passes(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.files[0]"],
                                  acceptable_lanes=["file_anchor"])],
                       needs=_needs(files=[{"path": "a.py"}]))
        gate = self._gate([sec])
        self.assertTrue(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_PASS_EXIT)
        row = _topic_row(gate.report, "s", "t")
        self.assertEqual(row.status, cov.obligations.STATUS_OK)
        self.assertEqual(row.defects, [])
        self.assertEqual(gate.report.complete_count, 1)

    def test_missing_ter_is_blocking(self):
        sec = _section("s", required_topics=["t"])  # no TER for required topic 't'
        gate = self._gate([sec])
        self.assertFalse(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_FAIL_EXIT)
        self.assertEqual(gate.report.failure_category,
                         "bad_underspecified_normalized_plan")
        self.assertEqual(gate.report.blocking_sections, ["s"])
        row = _topic_row(gate.report, "s", "t")
        self.assertEqual(row.status, cov.obligations.STATUS_INCOMPLETE)
        self.assertIn(cov.obligations.CODE_MISSING_TER, row.defects)
        self.assertTrue(row.remediation)

    def test_empty_source_fields_is_blocking(self):
        sec = _section("s", required_topics=["t"], ters=[_ter("t", [])])
        row = _topic_row(self._gate([sec]).report, "s", "t")
        self.assertIn(cov.obligations.CODE_EMPTY_SOURCE_FIELDS, row.defects)

    def test_broad_only_source_fields_is_blocking(self):
        # source field references a real broad-recall lane -> valid but never exact.
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.search_hints[0]"])],
                       needs=_needs(search_hints=[{"text": "x"}]))
        gate = self._gate([sec])
        self.assertFalse(gate.passed)
        row = _topic_row(gate.report, "s", "t")
        self.assertIn(cov.obligations.CODE_BROAD_ONLY_SOURCE_FIELDS, row.defects)
        self.assertNotIn(cov.obligations.CODE_INVALID_SOURCE_FIELD, row.defects)

    def test_graph_nodes_only_source_field_is_blocking(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.graph_nodes[0]"])],
                       needs=_needs(graph_nodes=["n1"]))
        row = _topic_row(self._gate([sec]).report, "s", "t")
        self.assertIn(cov.obligations.CODE_BROAD_ONLY_SOURCE_FIELDS, row.defects)

    def test_invalid_source_field_reference_is_blocking(self):
        # symbols[3] does not exist (no symbols normalized) -> invalid reference.
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.symbols[3]"])],
                       needs=_needs(symbols=[]))
        gate = self._gate([sec])
        self.assertFalse(gate.passed)
        row = _topic_row(gate.report, "s", "t")
        self.assertIn(cov.obligations.CODE_INVALID_SOURCE_FIELD, row.defects)

    def test_unknown_source_field_lane_is_blocking(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.bogus[0]"])])
        row = _topic_row(self._gate([sec]).report, "s", "t")
        self.assertIn(cov.obligations.CODE_INVALID_SOURCE_FIELD, row.defects)

    def test_broad_only_acceptable_lanes_is_blocking(self):
        # valid exact source field, but acceptable_lanes restricts to broad-only.
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.files[0]"],
                                  acceptable_lanes=["bm25", "vector"])],
                       needs=_needs(files=[{"path": "a.py"}]))
        gate = self._gate([sec])
        self.assertFalse(gate.passed)
        row = _topic_row(gate.report, "s", "t")
        self.assertIn(cov.obligations.CODE_BROAD_ONLY_ACCEPTABLE_LANES, row.defects)

    def test_required_topic_with_required_false_ter_is_blocking(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.files[0]"], required=False,
                                  acceptable_lanes=["file_anchor"])],
                       needs=_needs(files=[{"path": "a.py"}]))
        row = _topic_row(self._gate([sec]).report, "s", "t")
        self.assertIn(cov.obligations.CODE_NOT_REQUIRED, row.defects)

    def test_provenance_section_is_not_applicable_and_never_blocks(self):
        sec = _section("s", required_topics=["t"], role="provenance")
        gate = self._gate([sec])
        self.assertTrue(gate.passed)
        row = _topic_row(gate.report, "s", "t")
        self.assertEqual(row.status, cov.obligations.STATUS_NOT_APPLICABLE)
        secrow = gate.report.sections[0]
        self.assertEqual(secrow.status, cov.obligations.STATUS_NOT_APPLICABLE)

    def test_extra_optional_ter_does_not_block(self):
        # a TER topic that is NOT a required_topics[] entry and is required:false is
        # reported (optional) and, even if underspecified, never blocks.
        sec = _section("s", ters=[_ter("opt", [], required=False)])
        gate = self._gate([sec])
        self.assertTrue(gate.passed)
        self.assertEqual(_topic_row(gate.report, "s", "opt").status,
                         cov.obligations.STATUS_OPTIONAL)

    def test_baseline_mode_reports_but_never_gates(self):
        sec = _section("s", required_topics=["t"])  # would be missing in enhancement
        gate = self._gate([sec], mode=cov.MODE_BASELINE)
        self.assertTrue(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_PASS_EXIT)
        self.assertFalse(gate.report.enforced)
        self.assertIsNone(gate.report.failure_category)
        # the per-topic truth is still reported, only not enforced
        self.assertEqual(_topic_row(gate.report, "s", "t").status,
                         cov.obligations.STATUS_INCOMPLETE)

    def test_summary_lines_name_topic_and_disclaim_autoheal(self):
        sec = _section("svc", required_topics=["redis streams lifecycle"])
        text = "\n".join(self._gate([sec]).summary_lines())
        self.assertIn("redis streams lifecycle", text)
        self.assertIn("does NOT", text)
        self.assertIn("FAIL", text)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            cov.evaluate_topic_obligations(None, [], mode="bogus")

    def test_non_list_sections_raises(self):
        with self.assertRaises(ValueError):
            cov.evaluate_topic_obligations(None, {"not": "a list"})

    def test_enumeration_is_shared_with_phase3(self):
        # The Phase-3-blocking topic set this gate validates is exactly the set Phase 3
        # evidences: the enumerator is the same object (no drift possible).
        self.assertIs(cov.obligations.enumerate_section_topics, ec._section_topics)


# ---------------------------------------------------------------------------
# Live-failure-pattern: coverage_requirements[] merged into required_topics[] with
# no matching topic_evidence_requirements[] row, proven through real normalization.
class MergedCoverageRequirementNormalizeTests(unittest.TestCase):
    """``normalize`` merges coverage_requirements[] into required_topics[]; the gate
    must then demand a matching obligation for the merged topic too."""

    def _lookups(self) -> Lookups:
        lk = Lookups("/tmp/wiki-obl-gate-test")
        lk.files = {_TOPIC_FILE}
        return lk

    def _normalize(self, section_plan):
        doc = {"repo": "demo", "sections": [{"id": section_plan["section_id"],
                                             "title": section_plan.get("title", "S"),
                                             "parent": None}]}
        raw = parse.RawPlan(document_plan=doc, section_plans=[section_plan])
        return normalize.normalize(raw, self._lookups(), "plans/raw.md", "test")

    def test_merged_coverage_requirement_without_ter_fails(self):
        # The exact live pattern: a coverage_requirements[] entry that the planner did
        # NOT give a topic_evidence_requirements[] row. It merges into required_topics[]
        # and must block before Phase 3.
        res = self._normalize({
            "section_id": "task-queues", "title": "Task Queues",
            "coverage_requirements": ["redis streams lifecycle"],
            "required_topics": ["task workers"],
            "evidence_needs": {"file_anchors": [_TOPIC_FILE]},
            "topic_evidence_requirements": [
                {"topic": "task workers", "required": True,
                 "source_fields": ["retrieval_needs.files[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        })
        sec = res.sections[0]
        # normalization merged both into the canonical required_topics[]
        self.assertIn("redis streams lifecycle", sec["required_topics"])
        self.assertIn("task workers", sec["required_topics"])
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertFalse(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_FAIL_EXIT)
        # the authored required topic is complete; the merged one is missing its TER
        self.assertEqual(_topic_row(gate.report, "task-queues", "task workers").status,
                         cov.obligations.STATUS_OK)
        bad = _topic_row(gate.report, "task-queues", "redis streams lifecycle")
        self.assertEqual(bad.status, cov.obligations.STATUS_INCOMPLETE)
        self.assertIn(cov.obligations.CODE_MISSING_TER, bad.defects)

    def test_all_merged_topics_with_obligations_pass(self):
        res = self._normalize({
            "section_id": "task-queues", "title": "Task Queues",
            "coverage_requirements": ["redis streams lifecycle"],
            "required_topics": ["task workers"],
            "evidence_needs": {"file_anchors": [_TOPIC_FILE]},
            "topic_evidence_requirements": [
                {"topic": "task workers", "required": True,
                 "source_fields": ["retrieval_needs.files[0]"],
                 "acceptable_lanes": ["file_anchor"]},
                {"topic": "redis streams lifecycle", "required": True,
                 "source_fields": ["retrieval_needs.files[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        })
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)


# ---------------------------------------------------------------------------
# Integrated: real ``normalize-plan --coverage-mode enhancement`` over a bundle.
# A full 13-family obligation-complete plan passes BOTH gates; corrupting one
# section's obligation flips ONLY the obligation gate while the family gate stays
# green, proving the obligation gate is an independent Phase 2 → Phase 3 boundary.
_FAMILY_ROWS = [
    ("overview", "Overview", (), ()),
    ("subsystems", "Subsystems", (), ()),
    ("frontend-app", "Frontend Application", ("frontend",),
     ("routing and ui component architecture",)),
    ("memory-system", "Memory System", ("memory",),
     ("episodic and procedural memory apis",)),
    ("task-queues", "Task Queues and Redis Streams", (),
     ("task lifecycle and workers", "redis streams cancellation")),
    ("k8s-helm", "Kubernetes and Helm Deployment", (),
     ("helm chart values and manifests",)),
    ("build-cicd", "Build System and CI/CD", (),
     ("github actions and docker build flow",)),
    ("go-native", "Go Server and Native Components", (),
     ("go server build modes and native component services",)),
    ("retrieval-internals", "Retrieval and Search Internals", ("retrieval-internals",),
     ("document store abstraction and hybrid search",)),
    ("doc-pipeline", "Document Processing Pipeline", ("doc-processing",),
     ("deepdoc parser factory, ocr and chunking strategy",)),
    ("llm-internals", "LLM Provider Internals", ("llm-provider",),
     ("llmbundle, tool calling, retry logic and backoff",)),
    ("admin-health", "User, Tenant, Admin and System Health", (),
     ("tenant management and admin service", "health endpoint")),
    ("sandbox", "Sandbox Code Executor", ("sandbox",),
     ("code executor and provider registry",)),
    ("ops-migrations", "Migrations and Operations", (),
     ("database migration and schema sync",)),
    ("glossary", "Glossary", ("glossary",),
     ("repo-specific terminology and acronyms",)),
]


def _full_plans():
    """The 13-family obligation-complete section plans (each topic-bearing section has
    an exact files[] lane + one TER per topic). Returns (doc_sections, section_plans)."""
    doc, plans = [], []
    for sid, title, labels, topics in _FAMILY_ROWS:
        doc.append({"id": sid, "title": title, "parent": None})
        ev = {"search_hints": [f"retrieve: {sid}"]}
        plan = {"section_id": sid, "title": title, "evidence_needs": ev}
        if labels:
            plan["coverage_labels"] = list(labels)
        if topics:
            plan["required_topics"] = list(topics)
            ev["file_anchors"] = [_TOPIC_FILE]
            plan["topic_evidence_requirements"] = [
                {"topic": t, "required": True,
                 "source_fields": ["retrieval_needs.files[0]"],
                 "acceptable_lanes": ["file_anchor"]} for t in topics]
        plans.append(plan)
    return doc, plans


def _raw_response(doc, plans) -> str:
    lines = "\n".join(json.dumps(p) for p in plans)
    return ("```text\nplans/document-plan.json\n```\n"
            "```json\n" + json.dumps({"repo": "demo", "sections": doc}) + "\n```\n"
            "```text\nplans/section-plans.jsonl\n```\n"
            "```jsonl\n" + lines + "\n```\n")


class IntegratedObligationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obl_gate_cmd_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bundle = os.path.join(self.tmp, "bundle")
        self.plans = os.path.join(self.bundle, "plans")
        inv = os.path.join(self.bundle, "inventory")
        os.makedirs(inv)
        with open(os.path.join(inv, "files.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"path": _TOPIC_FILE, "line_count": 200}) + "\n")

    def _run(self, doc, plans, mode="enhancement"):
        raw = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(raw, "w", encoding="utf-8") as f:
            f.write(_raw_response(doc, plans))
        args = SimpleNamespace(bundle=self.bundle, raw_response=raw, out_dir=None,
                               strict=False, provider="test", coverage_mode=mode)
        return normalize_plan_cmd.run(args)

    def _coverage_gate(self):
        return util.read_json(os.path.join(self.plans, "coverage-gate.json"))

    def _obligations_gate(self):
        return util.read_json(os.path.join(self.plans, "topic-obligations-gate.json"))

    def test_full_obligation_complete_plan_passes_both_gates(self):
        doc, plans = _full_plans()
        rc = self._run(doc, plans)
        self.assertEqual(rc, 0)
        self.assertTrue(self._coverage_gate()["passed"])      # family gate green
        ob = self._obligations_gate()
        self.assertTrue(ob["passed"])                          # obligation gate green
        self.assertEqual(ob["report"]["blocking_sections"], [])

    def test_obligation_gate_blocks_while_family_gate_passes(self):
        # Corrupt ONE section: keep its required_topics[] but DROP its
        # topic_evidence_requirements[] (the live failure pattern). The family gate
        # still passes (label/keywords intact); only the obligation gate flips.
        doc, plans = _full_plans()
        tq = next(p for p in plans if p["section_id"] == "task-queues")
        del tq["topic_evidence_requirements"]
        rc = self._run(doc, plans)
        self.assertEqual(rc, cov.COVERAGE_GATE_FAIL_EXIT)
        self.assertTrue(self._coverage_gate()["passed"])      # family gate STILL green
        ob = self._obligations_gate()
        self.assertFalse(ob["passed"])
        self.assertEqual(ob["report"]["failure_category"],
                         "bad_underspecified_normalized_plan")
        self.assertIn("task-queues", ob["report"]["blocking_sections"])
        report = self._read_report()
        self.assertIn("**FAIL**", report)
        self.assertIn("task-queues", report)

    def test_broad_only_required_topic_blocks(self):
        # A required topic grounded only on search_hints (broad recall) blocks.
        doc, plans = _full_plans()
        tq = next(p for p in plans if p["section_id"] == "task-queues")
        tq["topic_evidence_requirements"] = [
            {"topic": t, "required": True,
             "source_fields": ["retrieval_needs.search_hints[0]"],
             "acceptable_lanes": ["file_anchor"]}
            for t in tq["required_topics"]]
        rc = self._run(doc, plans)
        self.assertEqual(rc, cov.COVERAGE_GATE_FAIL_EXIT)
        ob = self._obligations_gate()
        self.assertFalse(ob["passed"])
        self.assertIn("task-queues", ob["report"]["blocking_sections"])

    def test_baseline_mode_writes_no_obligation_gate(self):
        doc, plans = _full_plans()
        tq = next(p for p in plans if p["section_id"] == "task-queues")
        del tq["topic_evidence_requirements"]          # would block in enhancement
        rc = self._run(doc, plans, mode="baseline")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(
            os.path.join(self.plans, "topic-obligations-gate.json")))

    def test_gate_does_not_repair_the_plan(self):
        # upstream prevention by loud failure: the written plan is exactly what the
        # planner authored — no synthesized topic_evidence_requirements[] rows.
        doc, plans = _full_plans()
        tq = next(p for p in plans if p["section_id"] == "task-queues")
        del tq["topic_evidence_requirements"]
        self._run(doc, plans)
        rows = list(util.read_jsonl(
            os.path.join(self.plans, "section-plans.jsonl")))
        written = next(r for r in rows if r["section_id"] == "task-queues")
        self.assertEqual(written["topic_evidence_requirements"], [])

    def test_rerun_obligation_gate_byte_identical(self):
        doc, plans = _full_plans()
        self._run(doc, plans)
        first = open(os.path.join(self.plans, "topic-obligations-gate.json")).read()
        self._run(doc, plans)
        second = open(os.path.join(self.plans, "topic-obligations-gate.json")).read()
        self.assertEqual(first, second)
        self.assertNotIn("generated_at", first)
        self.assertNotIn("timestamp", first)

    def _read_report(self):
        with open(os.path.join(self.plans, "topic-obligations-report.md")) as f:
            return f.read()


# ---------------------------------------------------------------------------
# Phase 2 TER source-field canonicalization: a documented raw evidence_needs.*
# alias is rewritten to canonical retrieval_needs.* form ONLY when the raw lane
# item resolved to a concrete normalized lane item — using the raw-index →
# normalized-index map built during need resolution, never a naïve same-index
# rewrite and never a guess. This reproduces the live RAGFlow failure where the
# planner/repair output used raw aliases the obligation gate could not read.
class RawAliasCanonicalizationTests(unittest.TestCase):
    def _lookups(self, files=(), symbols=()) -> Lookups:
        lk = Lookups("/tmp/wiki-ter-canon-test")
        lk.files = set(files)
        # an exact symbol_id resolves via _by_id (resolution == "exact").
        lk._by_id = {s: {"symbol_id": s, "name": s} for s in symbols}
        return lk

    def _normalize(self, section_plan, lk):
        doc = {"repo": "demo", "sections": [{"id": section_plan["section_id"],
                                             "title": section_plan.get("title", "S"),
                                             "parent": None}]}
        raw = parse.RawPlan(document_plan=doc, section_plans=[section_plan])
        return normalize.normalize(raw, lk, "plans/raw.md", "test")

    def _fields(self, section, topic):
        ter = next(t for t in section["topic_evidence_requirements"]
                   if t["topic"] == topic)
        return ter["source_fields"]

    def test_file_anchor_alias_canonicalizes_to_files(self):
        lk = self._lookups(files=["api/svc.py"])
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["service lifecycle"],
            "evidence_needs": {"file_anchors": ["api/svc.py"]},
            "topic_evidence_requirements": [
                {"topic": "service lifecycle", "required": True,
                 "source_fields": ["evidence_needs.file_anchors[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual(self._fields(sec, "service lifecycle"),
                         ["retrieval_needs.files[0]"])
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)

    def test_symbol_ids_alias_canonicalizes_to_symbols(self):
        lk = self._lookups(symbols=["mod.Worker"])
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["class behavior"],
            "evidence_needs": {"symbol_ids": ["mod.Worker"]},
            "topic_evidence_requirements": [
                {"topic": "class behavior", "required": True,
                 "source_fields": ["evidence_needs.symbol_ids[0]"],
                 "acceptable_lanes": ["symbol_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual(self._fields(sec, "class behavior"),
                         ["retrieval_needs.symbols[0]"])
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)

    def test_pruned_raw_item_shifts_index_and_unresolved_left_invalid(self):
        # file_anchors = [missing (unresolved), good (resolves)] -> normalized files[]
        # holds ONLY good, at index 0. So raw file_anchors[1] must canonicalize to
        # retrieval_needs.files[0] (NOT files[1]: the non-naïve remap follows the
        # pruning), and raw file_anchors[0] (the pruned item) must be LEFT invalid.
        lk = self._lookups(files=["good.py"])
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["good topic", "bad topic"],
            "evidence_needs": {"file_anchors": ["missing.py", "good.py"]},
            "topic_evidence_requirements": [
                {"topic": "good topic", "required": True,
                 "source_fields": ["evidence_needs.file_anchors[1]"],
                 "acceptable_lanes": ["file_anchor"]},
                {"topic": "bad topic", "required": True,
                 "source_fields": ["evidence_needs.file_anchors[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual([f["path"] for f in sec["retrieval_needs"]["files"]],
                         ["good.py"])
        self.assertEqual(self._fields(sec, "good topic"),
                         ["retrieval_needs.files[0]"])           # raw[1] -> norm[0]
        self.assertEqual(self._fields(sec, "bad topic"),
                         ["evidence_needs.file_anchors[0]"])     # left invalid, not guessed
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertFalse(gate.passed)
        self.assertEqual(_topic_row(gate.report, "svc", "good topic").status,
                         cov.obligations.STATUS_OK)
        bad = _topic_row(gate.report, "svc", "bad topic")
        self.assertEqual(bad.status, cov.obligations.STATUS_INCOMPLETE)
        self.assertIn(cov.obligations.CODE_RAW_ALIAS_SOURCE_FIELD, bad.defects)
        self.assertIn("raw planner alias", bad.remediation)

    def test_broad_search_hint_alias_canonicalizes_but_stays_blocking(self):
        lk = self._lookups()
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["broad topic"],
            "evidence_needs": {"search_hints": ["retrieve: svc internals"]},
            "topic_evidence_requirements": [
                {"topic": "broad topic", "required": True,
                 "source_fields": ["evidence_needs.search_hints[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        # canonicalized to the BROAD canonical field — but a broad lane is never
        # sufficient for a required topic, so it must still block.
        self.assertEqual(self._fields(sec, "broad topic"),
                         ["retrieval_needs.search_hints[0]"])
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertFalse(gate.passed)
        row = _topic_row(gate.report, "svc", "broad topic")
        self.assertIn(cov.obligations.CODE_BROAD_ONLY_SOURCE_FIELDS, row.defects)
        self.assertNotIn(cov.obligations.CODE_INVALID_SOURCE_FIELD, row.defects)
        self.assertNotIn(cov.obligations.CODE_RAW_ALIAS_SOURCE_FIELD, row.defects)

    def test_live_style_raw_alias_plan_passes_after_canonicalization(self):
        # The live failure shape: TERs authored entirely with raw evidence_needs.*
        # aliases across lanes. Once each raw handle resolves exactly, Phase 2
        # canonicalizes them (recorded as a traceable warning) and the gate passes.
        lk = self._lookups(files=["api/svc.py"], symbols=["mod.Worker"])
        res = self._normalize({
            "section_id": "queues", "title": "Task Queues",
            "required_topics": ["task workers", "queue lifecycle"],
            "evidence_needs": {"file_anchors": ["api/svc.py"],
                               "symbol_ids": ["mod.Worker"]},
            "topic_evidence_requirements": [
                {"topic": "task workers", "required": True,
                 "source_fields": ["evidence_needs.symbol_ids[0]"],
                 "acceptable_lanes": ["symbol_anchor"]},
                {"topic": "queue lifecycle", "required": True,
                 "source_fields": ["evidence_needs.file_anchors[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual(self._fields(sec, "task workers"),
                         ["retrieval_needs.symbols[0]"])
        self.assertEqual(self._fields(sec, "queue lifecycle"),
                         ["retrieval_needs.files[0]"])
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)
        self.assertTrue(any("canonicalized topic_evidence_requirements" in w
                            for w in res.warnings))

    def test_dual_key_authoring_is_ambiguous_and_left_invalid(self):
        # evidence_needs authored BOTH file_anchors[] and files[] -> a raw file alias
        # is ambiguous about which raw list it indexes. Phase 2 must NOT guess: it
        # leaves the alias invalid so the gate fails loudly (rather than canonicalize
        # against the wrong list and mask the defect).
        lk = self._lookups(files=["a.py", "b.py"])
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["topic"],
            "evidence_needs": {"file_anchors": ["a.py"], "files": ["b.py"]},
            "topic_evidence_requirements": [
                {"topic": "topic", "required": True,
                 "source_fields": ["evidence_needs.file_anchors[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual(self._fields(sec, "topic"),
                         ["evidence_needs.file_anchors[0]"])     # left invalid, not guessed
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertFalse(gate.passed)
        row = _topic_row(gate.report, "svc", "topic")
        self.assertIn(cov.obligations.CODE_RAW_ALIAS_SOURCE_FIELD, row.defects)
        self.assertTrue(any("ambiguous" in w for w in res.warnings))

    def test_already_canonical_and_bare_fields_are_unchanged(self):
        # retrieval_needs.* keeps normalized-index semantics; a bare lane name is left
        # verbatim (the gate reads it as a normalized index, as before). No spurious
        # canonicalization warning is emitted for either.
        lk = self._lookups(files=["api/svc.py"])
        res = self._normalize({
            "section_id": "svc", "title": "Service",
            "required_topics": ["a", "b"],
            "evidence_needs": {"file_anchors": ["api/svc.py"]},
            "topic_evidence_requirements": [
                {"topic": "a", "source_fields": ["retrieval_needs.files[0]"],
                 "acceptable_lanes": ["file_anchor"]},
                {"topic": "b", "source_fields": ["files[0]"],
                 "acceptable_lanes": ["file_anchor"]}],
        }, lk)
        sec = res.sections[0]
        self.assertEqual(self._fields(sec, "a"), ["retrieval_needs.files[0]"])
        self.assertEqual(self._fields(sec, "b"), ["files[0]"])
        self.assertFalse(any("canonicalized topic_evidence_requirements" in w
                             for w in res.warnings))
        gate = cov.gate_topic_obligations(res.document_plan, res.sections,
                                          mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)


# ---------------------------------------------------------------------------
# Bounded plan-repair in ENHANCEMENT mode: success means readiness AND the strict
# planned-coverage + topic-obligation gates pass. A repair that passes only the old
# Phase-3 readiness but fails topic obligations is rejected, its diagnostics fed into
# the next attempt, and after the cap it fails loudly. Gemini is injected (fake) — no
# Vertex/Gemini/API/network. Reuses the 13-family obligation-complete fixture so the
# planned-coverage gate is green and only the obligation gate is exercised.
def _broken_plan_missing_one_ter():
    """The 13-family plan with one topic-bearing section (task-queues) stripped of its
    topic_evidence_requirements[] — passes readiness, fails the obligation gate."""
    doc, plans = _full_plans()
    tq = next(p for p in plans if p["section_id"] == "task-queues")
    del tq["topic_evidence_requirements"]
    return doc, plans


class EnhancementRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obl_repair_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bundle = os.path.join(self.tmp, "bundle")
        self.out = os.path.join(self.bundle, "plans")
        inv = os.path.join(self.bundle, "inventory")
        os.makedirs(inv)
        with open(os.path.join(inv, "files.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"path": _TOPIC_FILE, "line_count": 200}) + "\n")

    def _write_raw(self, text) -> str:
        p = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_rejects_old_readiness_only_repair_then_accepts(self):
        broken_doc, broken_plans = _broken_plan_missing_one_ter()
        full_doc, full_plans = _full_plans()
        raw = self._write_raw(_raw_response(broken_doc, broken_plans))
        bad_raw = _raw_response(broken_doc, broken_plans)   # passes readiness, fails obligations
        good_raw = _raw_response(full_doc, full_plans)      # passes both gates
        calls: list = []

        def fake(system, user):
            calls.append(user)
            return bad_raw if len(calls) == 1 else good_raw

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=fake,
                                    max_attempts=2, coverage_mode="enhancement")
        self.assertTrue(report["repaired"])
        self.assertEqual(report["attempts"], 2)            # attempt-1 rejected, attempt-2 accepted
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["coverage_mode"], "enhancement")

        # attempt-1 was rejected on the topic-obligation gate (NOT readiness).
        a1 = os.path.join(self.out, "repair", "attempt-1")
        v1 = util.read_json(os.path.join(a1, "validation.json"))
        self.assertFalse(v1["ok"])
        self.assertTrue(any("topic-obligation gate FAIL" in p for p in v1["problems"]))
        self.assertFalse(any("readiness still FAIL" in p for p in v1["problems"]))
        # the exact topic-obligation diagnostics were fed to the model.
        fed1 = util.read_json(os.path.join(a1, "obligation-diagnostics-fed.json"))
        self.assertTrue(any(d["section_id"] == "task-queues" for d in fed1))
        # attempt-2 was re-prompted WITH those diagnostics.
        req2 = open(os.path.join(self.out, "repair", "attempt-2",
                                 "repair-request.txt")).read()
        self.assertIn("Topic-obligation gate failures to fix", req2)
        self.assertIn("task-queues", req2)
        # the accepted attempt records the final post-repair gate verdict (both pass).
        gates = util.read_json(os.path.join(self.out, "repair", "attempt-2",
                                            "enhancement-gates.json"))
        self.assertTrue(gates["planned_coverage"]["passed"])
        self.assertTrue(gates["topic_obligations"]["passed"])
        # and the written plan really carries task-queues' restored obligation.
        rows = list(util.read_jsonl(os.path.join(self.out, "section-plans.jsonl")))
        tq = next(r for r in rows if r["section_id"] == "task-queues")
        self.assertTrue(tq["topic_evidence_requirements"])

    def test_accepts_in_one_attempt_when_gates_pass(self):
        broken_doc, broken_plans = _broken_plan_missing_one_ter()
        full_doc, full_plans = _full_plans()
        raw = self._write_raw(_raw_response(broken_doc, broken_plans))
        good_raw = _raw_response(full_doc, full_plans)

        report = repair.repair_plan(self.bundle, raw, self.out,
                                    client_call=lambda s, u: good_raw,
                                    max_attempts=1, coverage_mode="enhancement")
        self.assertTrue(report["repaired"])
        self.assertEqual(report["attempts"], 1)

    def test_fails_loudly_after_cap_when_obligations_never_pass(self):
        broken_doc, broken_plans = _broken_plan_missing_one_ter()
        raw = self._write_raw(_raw_response(broken_doc, broken_plans))
        bad_raw = _raw_response(broken_doc, broken_plans)
        with self.assertRaises(repair.RepairFailed):
            repair.repair_plan(self.bundle, raw, self.out,
                               client_call=lambda s, u: bad_raw,
                               max_attempts=2, coverage_mode="enhancement")
        rep = open(os.path.join(self.out, "repair", "repair-report.md")).read()
        self.assertIn("FAILED", rep)

    def test_baseline_mode_does_not_run_enhancement_gates(self):
        # Non-breaking: a plan that passes readiness but fails obligations is accepted
        # in baseline mode with NO repair (the client is never invoked).
        broken_doc, broken_plans = _broken_plan_missing_one_ter()
        raw = self._write_raw(_raw_response(broken_doc, broken_plans))

        def boom(system, user):
            raise AssertionError("baseline repair must not run for a readiness-pass plan")

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=boom,
                                    coverage_mode="baseline")
        self.assertFalse(report["repaired"])
        self.assertEqual(report["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
