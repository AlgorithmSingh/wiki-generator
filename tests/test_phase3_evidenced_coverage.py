"""Phase 3 evidenced-coverage tests (Milestone 2 next slice).

Deterministic, LLM-free, network-free. Proves the Phase 3 Evidence Sufficiency
Contract:

- Phase 2 normalization preserves the additive ``topic_evidence_requirements[]``
  field without making it mandatory in baseline mode.
- Phase 3 maps each planned required topic through explicit ``source_fields[]`` to
  the packet's exact-request coverage records and final ``evidence_id`` values
  (no fuzzy prose matching).
- Each required topic receives ``sufficient`` / ``weak`` / ``missing`` /
  ``not_applicable`` with counts, evidence IDs, source categories, and remediation.
- In enhancement mode a ``weak`` or ``missing`` required topic is a blocking
  pipeline failure BEFORE Phase 4: exit 3, ``bad_underspecified_normalized_plan``.
- Broad recall alone is ``weak`` (and blocking), never ``sufficient``.
- Baseline mode is non-breaking: it reports the matrix but never gates.
- Context/derived/plans/generated/reference artifacts are never citeable: the only
  evidence a topic can claim is a real ``evidence_id`` from a covered exact request.

The unit class exercises the pure ``evaluate_evidenced_coverage`` over synthetic
packets; the E2E class builds a real decomposed + retrieval-built bundle once and
hand-writes deterministic plans against the bundle's actual symbols/paths.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs.evidence import evidenced_coverage as ec  # noqa: E402
from wiki_generator.libs.evidence.options import EvidenceOptions  # noqa: E402


def _subenv(**extra) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra)
    return env


def _run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wiki_generator", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=_subenv())


def _read_jsonl(path):
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


# ---------------------------------------------------------------------------
# Unit tests over the pure evaluator with synthetic packets + a fake bundle.
def _opts(mode="enhancement"):
    return EvidenceOptions(bundle_root="/b", out_dir="/o", coverage_mode=mode)


def _bundle(sections):
    return SimpleNamespace(
        section_order=[s["section_id"] for s in sections],
        section_by_id={s["section_id"]: s for s in sections})


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


def _exact(source_field, status, *, evidence_ids=(), candidate_count=None,
           kept_count=None, lane="symbol_anchor"):
    ev = list(evidence_ids)
    return {
        "lane": lane, "source_field": source_field, "status": status,
        "candidate_count": candidate_count if candidate_count is not None else len(ev),
        "kept_count": kept_count if kept_count is not None else len(ev),
        "evidence_ids": ev,
    }


def _packet(sid, *, exact_requests=(), lane_summary=None):
    return {
        "section_id": sid,
        "coverage": {"exact_requests": list(exact_requests)},
        "lane_summary": lane_summary or {},
    }


def _topic_row(cov, sid, topic):
    sec = next(s for s in cov.matrix["sections"] if s["section_id"] == sid)
    return next(t for t in sec["topics"] if t["topic"] == topic)


class EvidencedCoverageUnitTests(unittest.TestCase):
    def test_sufficient_required_topic(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.symbols[0]"])],
                       needs={"symbols": [{"symbol_id": "S"}]})
        pkt = _packet("s", exact_requests=[
            _exact("retrieval_needs.symbols[0]", "covered",
                   evidence_ids=["ev:s:0001"])])
        cov = ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts())
        row = _topic_row(cov, "s", "t")
        self.assertEqual(row["status"], ec.STATUS_SUFFICIENT)
        self.assertEqual(row["mapped_evidence_ids"], ["ev:s:0001"])
        self.assertEqual(row["evidence_count"], 1)
        self.assertIn("symbol_anchor", row["source_categories"])
        self.assertFalse(cov.has_blocking)
        self.assertEqual(cov.matrix["status"], "pass")

    def test_required_topic_without_requirements_is_missing(self):
        sec = _section("s", required_topics=["t"])  # no TER for 't'
        cov = ec.evaluate_evidenced_coverage(
            _bundle([sec]), [_packet("s")], _opts())
        row = _topic_row(cov, "s", "t")
        self.assertEqual(row["status"], ec.STATUS_MISSING)
        self.assertEqual(row["diagnostic_code"], ec.CODE_MISSING)
        self.assertTrue(row["remediation"])
        self.assertEqual(cov.blocking_section_ids, ["s"])

    def test_no_mapped_exact_evidence_is_missing(self):
        # exact source field resolved but produced no candidate at all (no_hits)
        # and no broad recall -> missing (no related evidence).
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.files[0]"])],
                       needs={"files": [{"path": "a.py"}]})
        pkt = _packet("s", exact_requests=[
            _exact("retrieval_needs.files[0]", "no_hits", lane="file_anchor",
                   candidate_count=0, kept_count=0)])
        cov = ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts())
        self.assertEqual(_topic_row(cov, "s", "t")["status"], ec.STATUS_MISSING)
        self.assertTrue(cov.has_blocking)

    def test_invalid_source_field_index_is_missing(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.contracts[0]"])],
                       needs={"contracts": []})  # index out of range -> invalid
        cov = ec.evaluate_evidenced_coverage(
            _bundle([sec]), [_packet("s")], _opts())
        self.assertEqual(_topic_row(cov, "s", "t")["status"], ec.STATUS_MISSING)

    def test_broad_recall_only_is_weak_and_blocking(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.graph_nodes[0]"])],
                       needs={"graph_nodes": ["n1"]})
        pkt = _packet("s", lane_summary={"graph_neighbors": {"returned": 3}})
        cov = ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts())
        row = _topic_row(cov, "s", "t")
        self.assertEqual(row["status"], ec.STATUS_WEAK)
        self.assertEqual(row["diagnostic_code"], ec.CODE_WEAK)
        self.assertEqual(row["mapped_evidence_ids"], [])  # broad recall is not citeable
        self.assertEqual(cov.blocking_section_ids, ["s"])

    def test_below_threshold_is_weak(self):
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.symbols[0]"], min_items=2)],
                       needs={"symbols": [{"symbol_id": "S"}]})
        pkt = _packet("s", exact_requests=[
            _exact("retrieval_needs.symbols[0]", "covered",
                   evidence_ids=["ev:s:0001"])])  # 1 < min_items 2
        self.assertEqual(
            _topic_row(ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts()),
                       "s", "t")["status"], ec.STATUS_WEAK)

    def test_covered_but_lane_excluded_is_weak(self):
        # exact request is covered, but the topic restricts acceptable_lanes so the
        # evidence is unmapped -> related-but-insufficient -> weak.
        sec = _section("s", required_topics=["t"],
                       ters=[_ter("t", ["retrieval_needs.files[0]"],
                                  acceptable_lanes=["symbol_anchor"])],
                       needs={"files": [{"path": "a.py"}]})
        pkt = _packet("s", exact_requests=[
            _exact("retrieval_needs.files[0]", "covered", lane="file_anchor",
                   evidence_ids=["ev:s:0001"])])
        self.assertEqual(
            _topic_row(ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts()),
                       "s", "t")["status"], ec.STATUS_WEAK)

    def test_provenance_section_is_not_applicable_and_never_blocks(self):
        sec = _section("s", required_topics=["t"], role="provenance")
        cov = ec.evaluate_evidenced_coverage(
            _bundle([sec]), [_packet("s")], _opts())
        secrow = cov.matrix["sections"][0]
        self.assertEqual(secrow["status"], ec.STATUS_NOT_APPLICABLE)
        self.assertEqual(_topic_row(cov, "s", "t")["status"],
                         ec.STATUS_NOT_APPLICABLE)
        self.assertFalse(cov.has_blocking)

    def test_baseline_mode_reports_but_never_gates(self):
        sec = _section("s", required_topics=["t"])  # would be missing
        cov = ec.evaluate_evidenced_coverage(
            _bundle([sec]), [_packet("s")], _opts(mode="baseline"))
        self.assertFalse(cov.enforced)
        self.assertFalse(cov.has_blocking)
        self.assertEqual(cov.matrix["status"], "pass")
        # the per-topic truth is still reported (missing), only not enforced
        self.assertEqual(_topic_row(cov, "s", "t")["status"], ec.STATUS_MISSING)

    def test_union_across_source_fields_and_min_items(self):
        sec = _section(
            "s", required_topics=["t"],
            ters=[_ter("t", ["retrieval_needs.symbols[0]", "retrieval_needs.files[0]"],
                       min_items=2)],
            needs={"symbols": [{"symbol_id": "S"}], "files": [{"path": "a.py"}]})
        pkt = _packet("s", exact_requests=[
            _exact("retrieval_needs.symbols[0]", "covered",
                   evidence_ids=["ev:s:0001"]),
            _exact("retrieval_needs.files[0]", "covered", lane="file_anchor",
                   evidence_ids=["ev:s:0002"])])
        row = _topic_row(
            ec.evaluate_evidenced_coverage(_bundle([sec]), [pkt], _opts()), "s", "t")
        self.assertEqual(row["status"], ec.STATUS_SUFFICIENT)
        self.assertEqual(row["mapped_evidence_ids"], ["ev:s:0001", "ev:s:0002"])


# ---------------------------------------------------------------------------
# End-to-end over a real decomposed + retrieval-built bundle.
def _make_repo(d: str) -> None:
    files = {
        "pkg/__init__.py": '"""Pkg."""\n',
        "pkg/api/__init__.py": "",
        "pkg/api/routes.py": (
            '"""HTTP routes for the demo service."""\n'
            "from fastapi import APIRouter\n"
            "from pkg.svc import work\n\n"
            "router = APIRouter()\n\n\n"
            '@router.get("/items")\n'
            "async def list_items(limit: int = 10) -> list:\n"
            '    """List items from the service layer."""\n'
            "    return work(limit)\n"
        ),
        "pkg/svc.py": (
            '"""Service layer with the core work function and item model."""\n'
            "from pydantic import BaseModel\n\n\n"
            "class Item(BaseModel):\n"
            '    """An item produced by the service."""\n'
            "    name: str\n\n\n"
            "def work(n):\n"
            '    """Return n items."""\n'
            "    return [Item(name=str(i)) for i in range(n)]\n"
        ),
        "tests/test_svc.py": (
            "from pkg.svc import work\n\n\n"
            "def test_work():\n"
            "    assert work(0) == []\n"
        ),
        "README.md": "# Demo\n\n## Overview\nA demo service.\n",
        "pyproject.toml": (
            '[project]\nname = "demo"\nversion = "0.1.0"\n'
            'dependencies = ["fastapi", "pydantic"]\n'
        ),
    }
    for rel, content in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)


def _symbols(out):
    syms = {}
    for line in open(os.path.join(out, "symbols", "symbols.jsonl")):
        r = json.loads(line)
        syms[r["name"]] = r["symbol_id"]
    return syms


def _sym(syms, name):
    return {"input": name, "symbol_id": syms[name], "resolution": "exact",
            "candidates": []}


def _write_doc(out, sections):
    plans = os.path.join(out, "plans")
    os.makedirs(plans, exist_ok=True)
    doc = {"schema_version": "phase2-plan-v1", "repo": {"name": "demo", "root": out},
           "title": "Demo", "purpose": "Document the demo service.", "summary": "",
           "audience": "developers",
           "section_order": [s["section_id"] for s in sections],
           "coverage_goals": [], "known_gaps": [],
           "source_raw_response": "plans/raw.md", "provider": "test",
           "normalization": {"generated_by": "test", "unresolved_count": 0,
                             "warnings": []}}
    with open(os.path.join(plans, "document-plan.json"), "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    with open(os.path.join(plans, "section-plans.jsonl"), "w") as f:
        for s in sections:
            f.write(json.dumps(s) + "\n")
    with open(os.path.join(plans, "normalization-report.md"), "w") as f:
        f.write("# normalization report\n")


def _base_section(sid, title, **over):
    sec = {"schema_version": "phase2-section-plan-v1", "section_id": sid,
           "section_role": "source", "title": title, "order": 1, "parent": None,
           "parent_section_id": None, "coverage_labels": [], "priority": None,
           "purpose": title, "goal": title, "rationale": None,
           "required_topics": [], "topic_evidence_requirements": [],
           "key_questions": [], "expected_sources": [],
           "retrieval_needs": {"query_packs": [], "symbols": [], "files": [],
                               "contracts": [], "tests": [], "graph_nodes": [],
                               "search_hints": [], "context_artifacts": []},
           "expected_evidence_types": [], "depends_on": [], "verification_needs": [],
           "estimated_size": None, "known_gaps": [], "normalization_warnings": []}
    sec.update(over)
    return sec


def _pass_sections(syms):
    routes = _base_section(
        "routes-and-handlers", "Routes and Handlers",
        required_topics=["http routes"],
        topic_evidence_requirements=[
            {"topic": "http routes", "required": True,
             "source_fields": ["retrieval_needs.symbols[0]",
                               "retrieval_needs.contracts[0]"],
             "min_items": 1,
             "acceptable_lanes": ["symbol_anchor", "contract"]}],
        retrieval_needs={
            "query_packs": ["web_routes"], "symbols": [_sym(syms, "list_items")],
            "files": [{"input": "pkg/api/routes.py:9-11", "path": "pkg/api/routes.py",
                       "anchor": "9-11", "anchor_confidence": "exact_range",
                       "resolution": "file_exists", "candidates": []}],
            "contracts": [{"input": "GET /items", "method": "GET", "path": "/items",
                           "resolution": "exact"}],
            "tests": [], "graph_nodes": ["sym:" + syms["list_items"]],
            "search_hints": [], "context_artifacts": []},
        expected_evidence_types=["symbols", "files", "queries", "contracts", "graph"])
    service = _base_section(
        "service-layer", "Service Layer",
        required_topics=["item model", "service layer"],
        topic_evidence_requirements=[
            {"topic": "item model", "required": True,
             "source_fields": ["retrieval_needs.symbols[0]"], "min_items": 1,
             "acceptable_lanes": ["symbol_anchor"]},
            {"topic": "service layer", "required": True,
             "source_fields": ["retrieval_needs.symbols[1]",
                               "retrieval_needs.files[0]"], "min_items": 1,
             "acceptable_lanes": ["symbol_anchor", "file_anchor"]}],
        retrieval_needs={
            "query_packs": ["models_schemas"],
            "symbols": [_sym(syms, "Item"), _sym(syms, "work")],
            "files": [{"input": "pkg/svc.py", "path": "pkg/svc.py", "anchor": None,
                       "anchor_confidence": None, "resolution": "file_exists",
                       "candidates": []}],
            "contracts": [],
            "tests": [{"input": "tests/test_svc.py", "path": "tests/test_svc.py",
                       "resolution": "test_file"}],
            "graph_nodes": [], "search_hints": [], "context_artifacts": []},
        expected_evidence_types=["symbols", "files", "queries", "tests"])
    return [routes, service]


class EvidencedCoverageE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p3ec_")
        repo = os.path.join(cls.tmp, "repo")
        cls.master = os.path.join(cls.tmp, "bundle")
        os.makedirs(repo)
        _make_repo(repo)
        assert _run_cmd("decompose", "--repo", repo, "--out", cls.master,
                        "--embeddings", "off").returncode == 0
        assert _run_cmd("build-retrieval", "--in", cls.master,
                        "--vectors", "off").returncode == 0
        cls.syms = _symbols(cls.master)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fresh(self) -> str:
        dst = tempfile.mkdtemp(prefix="p3ec_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        return out

    def _ev(self, out):
        return os.path.join(out, "evidence")

    def _evidenced(self, out):
        return json.load(open(os.path.join(self._ev(out), "evidenced-coverage.json")))

    def _topic(self, matrix, sid, topic):
        sec = next(s for s in matrix["sections"] if s["section_id"] == sid)
        return next(t for t in sec["topics"] if t["topic"] == topic)

    def test_enhancement_passes_with_sufficient_evidence(self):
        out = self._fresh()
        _write_doc(out, _pass_sections(self.syms))
        res = _run_cmd("retrieve-evidence", "--bundle", out,
                       "--coverage-mode", "enhancement")
        self.assertEqual(res.returncode, 0, res.stderr)
        m = self._evidenced(out)
        self.assertEqual(m["coverage_mode"], "enhancement")
        self.assertTrue(m["enforced"])
        self.assertEqual(m["status"], "pass")
        for sid, topic in (("routes-and-handlers", "http routes"),
                           ("service-layer", "item model"),
                           ("service-layer", "service layer")):
            row = self._topic(m, sid, topic)
            self.assertEqual(row["status"], "sufficient", (sid, topic))
            self.assertTrue(row["mapped_evidence_ids"], (sid, topic))
        # manifest references the evidenced-coverage artifacts
        man = json.load(open(os.path.join(self._ev(out), "evidence-manifest.json")))
        self.assertEqual(man["coverage_mode"], "enhancement")
        self.assertEqual(man["evidenced_coverage"], "evidence/evidenced-coverage.json")
        self.assertEqual(man["evidenced_coverage_status"], "pass")
        # validation carries the named contract check, passing
        v = json.load(open(os.path.join(self._ev(out), "retrieval-validation.json")))
        check = next(c for c in v["contract_checks"]
                     if c["name"] == "required_topic_evidence_sufficient")
        self.assertEqual(check["status"], "pass")
        self.assertTrue(os.path.isfile(os.path.join(
            self._ev(out), "evidenced-coverage-report.md")))

    def test_mapped_evidence_ids_are_real_citeable_packet_ids(self):
        # The only evidence a topic can claim is a real evidence_id present in the
        # packet — never a context/derived/plan/generated/reference artifact.
        out = self._fresh()
        _write_doc(out, _pass_sections(self.syms))
        _run_cmd("retrieve-evidence", "--bundle", out, "--coverage-mode", "enhancement")
        m = self._evidenced(out)
        for sid in ("routes-and-handlers", "service-layer"):
            packet = json.load(open(os.path.join(
                self._ev(out), "packets", f"{sid}.json")))
            real_ids = {e["evidence_id"] for e in packet["evidence"]}
            sec = next(s for s in m["sections"] if s["section_id"] == sid)
            for t in sec["topics"]:
                for eid in t["mapped_evidence_ids"]:
                    self.assertIn(eid, real_ids)

    def test_missing_required_topic_fails_before_phase4(self):
        out = self._fresh()
        sections = _pass_sections(self.syms)
        # add a required topic whose source field points at an empty lane (no
        # mapped exact evidence) -> missing -> blocking.
        svc = next(s for s in sections if s["section_id"] == "service-layer")
        svc["required_topics"].append("deployment topology")
        svc["topic_evidence_requirements"].append(
            {"topic": "deployment topology", "required": True,
             "source_fields": ["retrieval_needs.contracts[0]"], "min_items": 1,
             "acceptable_lanes": ["contract"]})  # service-layer has no contracts
        _write_doc(out, sections)
        res = _run_cmd("retrieve-evidence", "--bundle", out,
                       "--coverage-mode", "enhancement")
        self.assertEqual(res.returncode, 3, res.stderr)
        v = json.load(open(os.path.join(self._ev(out), "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_underspecified_normalized_plan")
        check = next(c for c in v["contract_checks"]
                     if c["name"] == "required_topic_evidence_sufficient")
        self.assertEqual(check["status"], "fail")
        m = self._evidenced(out)
        self.assertEqual(m["status"], "fail")
        self.assertEqual(m["failure_category"], "bad_underspecified_normalized_plan")
        row = self._topic(m, "service-layer", "deployment topology")
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["diagnostic_code"], "required_topic_evidence_missing")

    def test_broad_recall_only_required_topic_is_weak_and_blocking(self):
        out = self._fresh()
        section = _base_section(
            "graph-area", "Graph Relationships",
            required_topics=["call graph relationships"],
            topic_evidence_requirements=[
                {"topic": "call graph relationships", "required": True,
                 "source_fields": ["retrieval_needs.graph_nodes[0]"], "min_items": 1,
                 "acceptable_lanes": ["symbol_anchor", "file_anchor", "contract",
                                      "test", "query_pack"]}],
            retrieval_needs={
                "query_packs": [], "symbols": [_sym(self.syms, "list_items")],
                "files": [], "contracts": [], "tests": [],
                "graph_nodes": ["sym:" + self.syms["list_items"]],
                "search_hints": [], "context_artifacts": []},
            expected_evidence_types=["symbols", "graph"])
        _write_doc(out, [section])
        res = _run_cmd("retrieve-evidence", "--bundle", out,
                       "--coverage-mode", "enhancement")
        self.assertEqual(res.returncode, 3, res.stderr)
        m = self._evidenced(out)
        row = self._topic(m, "graph-area", "call graph relationships")
        self.assertEqual(row["status"], "weak")
        self.assertEqual(row["diagnostic_code"], "required_topic_evidence_weak")
        self.assertEqual(row["mapped_evidence_ids"], [])

    def test_baseline_mode_is_non_breaking(self):
        # the same plan that fails enhancement passes baseline (report-only).
        out = self._fresh()
        sections = _pass_sections(self.syms)
        svc = next(s for s in sections if s["section_id"] == "service-layer")
        svc["required_topics"].append("deployment topology")  # no TER -> missing
        _write_doc(out, sections)
        res = _run_cmd("retrieve-evidence", "--bundle", out,
                       "--coverage-mode", "baseline")
        self.assertEqual(res.returncode, 0, res.stderr)
        m = self._evidenced(out)
        self.assertEqual(m["coverage_mode"], "baseline")
        self.assertFalse(m["enforced"])
        self.assertEqual(m["status"], "pass")        # never gates
        # but the truth is still reported
        self.assertEqual(self._topic(m, "service-layer", "deployment topology")["status"],
                         "missing")
        # baseline omits the enhancement contract check (legacy runs unchanged)
        v = json.load(open(os.path.join(self._ev(out), "retrieval-validation.json")))
        names = {c["name"] for c in v["contract_checks"]}
        self.assertNotIn("required_topic_evidence_sufficient", names)

    def test_default_mode_is_baseline_non_breaking(self):
        # no --coverage-mode flag -> baseline default, exit 0 even with a missing topic
        out = self._fresh()
        sections = _pass_sections(self.syms)
        next(s for s in sections if s["section_id"] == "service-layer")[
            "required_topics"].append("deployment topology")
        _write_doc(out, sections)
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._evidenced(out)["coverage_mode"], "baseline")

    def test_rerun_byte_identical(self):
        out = self._fresh()
        _write_doc(out, _pass_sections(self.syms))
        _run_cmd("retrieve-evidence", "--bundle", out, "--coverage-mode", "enhancement")
        first = open(os.path.join(self._ev(out), "evidenced-coverage.json")).read()
        _run_cmd("retrieve-evidence", "--bundle", out, "--coverage-mode", "enhancement")
        self.assertEqual(
            first, open(os.path.join(self._ev(out), "evidenced-coverage.json")).read())
        self.assertNotIn("generated_at", first)
        self.assertNotIn("timestamp", first)


# ---------------------------------------------------------------------------
class NormalizePreservesTopicEvidenceRequirementsTests(unittest.TestCase):
    """Phase 2 normalization preserves the additive ``topic_evidence_requirements[]``
    field (baseline-compatible: a plan that omits it normalizes to ``[]``)."""

    def _normalize(self, section_plans, doc_sections=None):
        from wiki_generator.libs.plan_normalization import normalize, parse
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/tmp/wiki-ter-test")
        lk.files = set()
        doc = {"repo": "demo",
               "sections": doc_sections or [{"id": p["section_id"],
                                             "title": p.get("title", p["section_id"]),
                                             "parent": None}
                                            for p in section_plans]}
        raw = parse.RawPlan(document_plan=doc, section_plans=section_plans)
        return normalize.normalize(raw, lk, "plans/raw.md", "test")

    def _by_id(self, res):
        return {s["section_id"]: s for s in res.sections}

    def test_topic_evidence_requirements_preserved_and_normalized(self):
        res = self._normalize([{
            "section_id": "svc", "title": "Service",
            "required_topics": ["item model"],
            "evidence_needs": {"search_hints": ["service"]},
            "topic_evidence_requirements": [
                {"topic": "item model",
                 "source_fields": ["retrieval_needs.symbols[0]"]},
                {"topic": "  ", "source_fields": []},        # empty topic dropped
                "not-a-dict",                                  # non-dict dropped
                {"topic": "ops", "required": False,
                 "source_fields": ["retrieval_needs.files[1]"], "min_items": 3,
                 "acceptable_lanes": ["file_anchor"]}],
        }])
        ter = self._by_id(res)["svc"]["topic_evidence_requirements"]
        self.assertEqual(len(ter), 2)
        self.assertEqual(ter[0]["topic"], "item model")
        self.assertTrue(ter[0]["required"])          # defaults to True
        self.assertEqual(ter[0]["min_items"], 1)     # defaults to 1
        # acceptable_lanes defaults to the exact lanes
        self.assertEqual(ter[0]["acceptable_lanes"],
                         ["file_anchor", "symbol_anchor", "contract", "test",
                          "query_pack"])
        self.assertEqual(ter[0]["source_fields"], ["retrieval_needs.symbols[0]"])
        self.assertFalse(ter[1]["required"])
        self.assertEqual(ter[1]["min_items"], 3)
        self.assertEqual(ter[1]["acceptable_lanes"], ["file_anchor"])

    def test_absent_field_normalizes_to_empty_list(self):
        res = self._normalize([{
            "section_id": "svc", "title": "Service",
            "evidence_needs": {"search_hints": ["service"]}}])
        self.assertEqual(self._by_id(res)["svc"]["topic_evidence_requirements"], [])


# ---------------------------------------------------------------------------
class CliSurfaceTests(unittest.TestCase):
    def test_coverage_mode_option_present_no_section_flag(self):
        from wiki_generator.cli import build_parser
        parser = build_parser()
        sub = parser._subparsers._group_actions[0].choices["retrieve-evidence"]
        opts = {a for action in sub._actions for a in action.option_strings}
        self.assertIn("--coverage-mode", opts)
        self.assertNotIn("--section", opts)
        self.assertNotIn("--section-id", opts)
        self.assertNotIn("--force", opts)


if __name__ == "__main__":
    unittest.main()
