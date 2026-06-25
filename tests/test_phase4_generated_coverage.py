"""Phase 4 generated-coverage + hierarchical-writing tests (Milestone 2 next slice).

Fake-provider / deterministic only — no live Gemini/Vertex. Proves the Phase 4
DeepWiki coverage enhancement contract:

- ``write-wiki --coverage-mode enhancement`` refuses to call any provider unless the
  Phase 2 planned-coverage gate (``plans/coverage-gate.json``) and the Phase 3
  evidenced-coverage gate (``evidence/evidenced-coverage.json`` + the
  ``required_topic_evidence_sufficient`` contract check) are present, enforced, and
  passing — a missing/baseline/failed upstream gate is a pre-provider GateFailure
  (exit 3), and no provider call happens.
- The hierarchical happy path consumes the plan hierarchy + page-level evidence,
  renders a nested ``index.md``, carries evidenced topic rows into WritingPackets,
  and emits the deterministic ``generated-coverage.json`` / report artifacts.
- Generated coverage passes only when every evidenced *sufficient* required topic is
  declared ``covered`` with mapped evidence IDs that resolve through the manifest and
  are cited near the topic; it fails (exit 5, post-provider) when a topic is omitted,
  declared without local citation, cited with out-of-scope IDs, or placeholder-only.
- Baseline/default Phase 4 remains non-breaking (no gate, no covered_topics needed).

The E2E class builds one real decomposed + retrieval-built bundle, runs the real
``retrieve-evidence --coverage-mode enhancement`` to produce genuine evidenced
coverage with real mapped IDs, hand-writes a passing Phase 2 planned-coverage gate
(Phase 2's 13-family gate is tested separately; Phase 4 only consumes the artifact),
and drives Phase 4 with an injected fake provider.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import util, writing  # noqa: E402
from wiki_generator.libs.writing import bundle as wbundle  # noqa: E402
from wiki_generator.libs.writing import generated_coverage as gencov  # noqa: E402
from wiki_generator.libs.writing.options import (  # noqa: E402
    PROVIDER_VERTEX,
    WritingOptions,
)
from wiki_generator.libs.writing.provider import SectionResponse  # noqa: E402


def _subenv(**extra) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra)
    return env


def _run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wiki_generator", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=_subenv())


def _passing_planned_gate() -> dict:
    return {"passed": True, "exit_code": 0,
            "report": {"schema_version": "phase2-coverage-validation-v1",
                       "mode": "enhancement", "status": "pass", "enforced": True,
                       "missing_mandatory": []}}


# --- repo + hierarchical plan -------------------------------------------------
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
            "from pkg.svc import work\n\n\ndef test_work():\n    assert work(0) == []\n"
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


def _hierarchical_sections(syms):
    """Two pages with a parent/child hierarchy and explicit topic evidence."""
    routes = _base_section(
        "routes-and-handlers", "Routes and Handlers",
        order=1, coverage_labels=["retrieval-internals"],
        required_topics=["http routes"],
        topic_evidence_requirements=[
            {"topic": "http routes", "required": True,
             "source_fields": ["retrieval_needs.symbols[0]",
                               "retrieval_needs.contracts[0]"],
             "min_items": 1, "acceptable_lanes": ["symbol_anchor", "contract"]}],
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
        order=2, parent_section_id="routes-and-handlers",
        coverage_labels=["retrieval-internals"],
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
    with open(os.path.join(plans, "phase3-readiness-report.md"), "w") as f:
        f.write("# Phase 3 Readiness Report\n\nStatus: PASS\nFailures: 0\n"
                "Warnings: 0\nSections: %d\n" % len(sections))
    with open(os.path.join(out, "command-manifest.tsv"), "w") as f:
        f.write("phase3\tscripts/phase3_retrieve_evidence.sh --out %s\t0\n" % out)


# --- fake provider that honors the obligations --------------------------------
class CoverageProvider:
    """Fake provider that emits one ``### topic`` subsection per obligation, citing
    the topic's mapped evidence IDs, and a matching ``covered_topics[]`` row. Knobs
    let a test omit / under-cite / out-of-scope one topic to exercise failures."""

    mode = PROVIDER_VERTEX
    model = "fake-model"

    def __init__(self, bundle, *, omit=None, uncite=None, out_of_scope=None,
                 placeholder=None):
        self.b = bundle
        self.omit = omit
        self.uncite = uncite
        self.out_of_scope = out_of_scope
        self.placeholder = placeholder
        self.calls = []

    def generate(self, sid, prompt):
        self.calls.append(sid)
        b = self.b
        obligations = [o for o in b.topic_obligations.get(sid, [])
                       if o["is_obligation"]]
        parts = [f"## {b.section_plans[sid]['title']}", ""]
        covered = []
        for ob in obligations:
            topic = ob["topic"]
            if self.omit == topic:
                continue
            ids = list(ob["mapped_evidence_ids"])
            decl_ids = ["ev:not-a-section:9999"] + ids if self.out_of_scope == topic \
                else ids
            cite_ids = [] if self.uncite == topic else ids
            cites = "".join(f"[{i}]" for i in cite_ids)
            anchor = topic.replace(" ", "-")
            status = "covered" if self.placeholder != topic else "covered"
            parts.append(f"### {topic.title()}")
            parts.append("")
            if self.placeholder == topic:
                # declared covered but the heading body is empty (placeholder-only)
                parts.append("")
            else:
                parts.append(f"The {topic} is implemented as the evidence shows. "
                             f"{cites}")
                parts.append("")
            covered.append({"topic": topic, "status": status,
                            "evidence_ids": decl_ids, "markdown_anchor": anchor})
        markdown = "\n".join(parts) + "\n"
        draft = {"schema_version": "phase4-section-draft-v1", "section_id": sid,
                 "title": b.section_plans[sid]["title"], "markdown": markdown,
                 "used_evidence_ids": sorted(b.section_evidence_ids[sid]),
                 "covered_topics": covered,
                 "self_check": {"no_uncited_repo_claims": True,
                                "no_context_artifact_citations": True,
                                "no_placeholders": True}}
        return SectionResponse(json.dumps(draft), "STOP")


# ---------------------------------------------------------------------------
class EnhancementE2ETests(unittest.TestCase):
    """Full enhancement-mode Phase 4 over a real bundle + fake provider."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p4gc_")
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

    def _fresh(self, *, gate=True, run_phase3=True) -> str:
        dst = tempfile.mkdtemp(prefix="p4gc_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        _write_doc(out, _hierarchical_sections(self.syms))
        if run_phase3:
            res = _run_cmd("retrieve-evidence", "--bundle", out,
                           "--coverage-mode", "enhancement")
            self.assertEqual(res.returncode, 0, res.stderr)
        if gate:
            util.write_json(os.path.join(out, "plans", "coverage-gate.json"),
                            _passing_planned_gate())
        return out

    def _opts(self, root, **kw):
        base = dict(bundle_root=root, out_dir=os.path.join(root, "wiki"),
                    provider=PROVIDER_VERTEX, coverage_mode="enhancement")
        base.update(kw)
        return WritingOptions(**base)

    def _gated(self, root, **kw):
        return wbundle.load_and_gate(self._opts(root, **kw))

    # --- happy path -----------------------------------------------------------
    def test_enhancement_happy_path_writes_hierarchy_and_coverage(self):
        out = self._fresh()
        b = self._gated(out)
        # WritingPackets carry the evidenced topic obligations with mapped IDs.
        self.assertEqual(
            sorted(o["topic"] for o in b.topic_obligations["service-layer"]),
            ["item model", "service layer"])
        res = writing.run(self._opts(out), provider=CoverageProvider(b))
        self.assertEqual(res.status, "pass", res.message)

        wiki = os.path.join(out, "wiki")
        for rel in ("metadata/generated-coverage.json",
                    "validation/generated-coverage-report.md",
                    "metadata/generated-sections.jsonl", "index.md"):
            self.assertTrue(os.path.isfile(os.path.join(wiki, rel)), rel)

        gc = json.load(open(os.path.join(wiki, "metadata", "generated-coverage.json")))
        self.assertEqual(gc["status"], "pass")
        self.assertEqual(gc["counts"]["required_topics"], 3)
        self.assertEqual(gc["counts"]["covered"], 3)
        self.assertEqual(gc["counts"]["invalid"], 0)

        # the writing-validation report carries the named generated-coverage check.
        vd = json.load(open(os.path.join(wiki, "validation",
                                         "writing-validation.json")))
        check = next(c for c in vd["checks"]
                     if c["name"] == "generated_required_topics_covered")
        self.assertEqual(check["status"], "pass")

        # index.md renders nested hierarchy (child indented under its parent).
        index = open(os.path.join(wiki, "index.md")).read()
        self.assertIn("1. [Routes and Handlers]", index)
        self.assertIn("  - [Service Layer]", index)

        # generated-section rows preserve hierarchy + the generated declaration.
        rows = [json.loads(l) for l in open(os.path.join(
            wiki, "metadata", "generated-sections.jsonl")) if l.strip()]
        svc = next(r for r in rows if r["section_id"] == "service-layer")
        self.assertEqual(svc["parent_section_id"], "routes-and-handlers")
        self.assertEqual(sorted(t["topic"] for t in svc["covered_topics"]),
                         ["item model", "service layer"])

        # generated-document.json references the coverage artifacts + hierarchy.
        doc = json.load(open(os.path.join(wiki, "metadata",
                                          "generated-document.json")))
        self.assertEqual(doc["coverage_mode"], "enhancement")
        self.assertEqual(doc["generated_coverage_status"], "pass")
        self.assertEqual(doc["generated_coverage_path"],
                         "wiki/metadata/generated-coverage.json")

    def test_packet_carries_exact_mapped_evidence_ids(self):
        out = self._fresh()
        b = self._gated(out)
        from wiki_generator.libs.writing.packet import build_writing_packet
        wp = build_writing_packet(b, "service-layer")
        item = next(o for o in wp.required_topics_coverage
                    if o["topic"] == "item model")
        # the exact Phase 3 mapped evidence_id rides in the packet for the writer.
        self.assertEqual(item["supporting_evidence_ids"], ["ev:service-layer:0001"])
        self.assertIn("hierarchy", wp.data)
        self.assertEqual(wp.data["hierarchy"]["parent_section_id"],
                         "routes-and-handlers")

    def test_rerun_generated_coverage_byte_identical(self):
        out = self._fresh()
        b = self._gated(out)
        writing.run(self._opts(out), provider=CoverageProvider(b))
        first = open(os.path.join(out, "wiki", "metadata",
                                  "generated-coverage.json")).read()
        b2 = self._gated(out)
        writing.run(self._opts(out), provider=CoverageProvider(b2))
        self.assertEqual(first, open(os.path.join(
            out, "wiki", "metadata", "generated-coverage.json")).read())
        self.assertNotIn("generated_at", first)
        self.assertNotIn("timestamp", first)

    # --- upstream gate failures: pre-provider, exit 3, NO provider call -------
    def test_missing_planned_gate_fails_before_provider(self):
        out = self._fresh(gate=False)
        spy = CoverageProvider(self._gated(out, coverage_mode="baseline"))
        with self.assertRaises(writing.GateFailure):
            writing.run(self._opts(out), provider=spy)
        self.assertEqual(spy.calls, [])  # no provider call happened
        self.assertFalse(os.path.exists(os.path.join(out, "wiki", "index.md")))

    def test_baseline_planned_gate_fails_before_provider(self):
        out = self._fresh()
        gate = _passing_planned_gate()
        gate["report"]["mode"] = "baseline"
        gate["report"]["enforced"] = False
        util.write_json(os.path.join(out, "plans", "coverage-gate.json"), gate)
        with self.assertRaises(writing.GateFailure):
            self._gated(out)

    def test_failed_planned_gate_fails_before_provider(self):
        out = self._fresh()
        gate = _passing_planned_gate()
        gate["passed"] = False
        gate["report"]["status"] = "fail"
        gate["report"]["missing_mandatory"] = ["frontend", "memory"]
        util.write_json(os.path.join(out, "plans", "coverage-gate.json"), gate)
        with self.assertRaises(writing.GateFailure):
            self._gated(out)

    def test_missing_evidenced_coverage_fails_before_provider(self):
        out = self._fresh()
        os.remove(os.path.join(out, "evidence", "evidenced-coverage.json"))
        with self.assertRaises(writing.GateFailure):
            self._gated(out)

    def test_baseline_evidenced_coverage_fails_before_provider(self):
        out = self._fresh()
        m = json.load(open(os.path.join(out, "evidence", "evidenced-coverage.json")))
        m["coverage_mode"] = "baseline"
        m["enforced"] = False
        util.write_json(os.path.join(out, "evidence", "evidenced-coverage.json"), m)
        with self.assertRaises(writing.GateFailure):
            self._gated(out)

    def test_missing_retrieval_contract_check_fails_before_provider(self):
        out = self._fresh()
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        v["contract_checks"] = [c for c in v["contract_checks"]
                                if c["name"] != "required_topic_evidence_sufficient"]
        util.write_json(os.path.join(out, "evidence", "retrieval-validation.json"), v)
        with self.assertRaises(writing.GateFailure):
            self._gated(out)

    # --- generated coverage failures: post-provider, exit 5 -------------------
    def test_omitted_required_topic_fails(self):
        out = self._fresh()
        b = self._gated(out)
        prov = CoverageProvider(b, omit="service layer")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(self._opts(out), provider=prov)
        # the deterministic coverage matrix is still written for audit (omitted).
        gc = json.load(open(os.path.join(out, "wiki", "metadata",
                                         "generated-coverage.json")))
        self.assertEqual(gc["status"], "fail")
        self.assertTrue(any("service layer" in f and "omitted" in f.lower()
                            or "service layer" in f for f in gc["failures"]))

    def test_topic_declared_without_local_citation_fails(self):
        out = self._fresh()
        b = self._gated(out)
        prov = CoverageProvider(b, uncite="item model")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(self._opts(out), provider=prov)

    def test_topic_cited_with_out_of_scope_id_fails(self):
        out = self._fresh()
        b = self._gated(out)
        prov = CoverageProvider(b, out_of_scope="item model")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(self._opts(out), provider=prov)

    def test_placeholder_only_topic_fails(self):
        out = self._fresh()
        b = self._gated(out)
        # an empty heading body is caught by the existing placeholder validator
        # (terminal) before final coverage validation — still a writing failure.
        prov = CoverageProvider(b, placeholder="item model")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(self._opts(out), provider=prov)

    # --- baseline / default remains non-breaking ------------------------------
    def test_baseline_mode_ignores_coverage_and_passes(self):
        # the same hierarchical bundle, written in baseline mode, needs no upstream
        # gate and no covered_topics: it is the historical Phase 4 behavior.
        out = self._fresh(gate=False, run_phase3=True)
        b = wbundle.load_and_gate(self._opts(out, coverage_mode="baseline"))

        def by(sid):
            ids = sorted(b.section_evidence_ids[sid])
            cites = "".join(f"[{i}]" for i in ids)
            md = (f"## {b.section_plans[sid]['title']}\n\nThe subsystem is described "
                  f"by the evidence. {cites}\n")
            return SectionResponse(json.dumps(
                {"schema_version": "phase4-section-draft-v1", "section_id": sid,
                 "title": b.section_plans[sid]["title"], "markdown": md,
                 "used_evidence_ids": ids}), "STOP")

        class Prov:
            mode = PROVIDER_VERTEX
            model = "fake"

            def generate(self, sid, prompt):
                return by(sid)

        res = writing.run(self._opts(out, coverage_mode="baseline"), provider=Prov())
        self.assertEqual(res.status, "pass", res.message)
        # baseline writes no generated-coverage artifact.
        self.assertFalse(os.path.isfile(os.path.join(
            out, "wiki", "metadata", "generated-coverage.json")))
        vd = json.load(open(os.path.join(out, "wiki", "validation",
                                         "writing-validation.json")))
        names = {c["name"] for c in vd["checks"]}
        self.assertNotIn("generated_required_topics_covered", names)


# ---------------------------------------------------------------------------
class GeneratedCoverageUnitTests(unittest.TestCase):
    """Pure unit coverage of the deterministic per-section coverage evaluator."""

    INDEX = {"ev:s:0001": object(), "ev:s:0002": object()}
    MANIFEST_IDS = {"ev:s:0001", "ev:s:0002"}

    def _ob(self, topic, ids):
        return {"topic": topic, "evidenced_status": "sufficient",
                "mapped_evidence_ids": list(ids), "min_items": 1,
                "is_obligation": True}

    def _eval(self, obligations, covered_topics, markdown):
        return gencov.evaluate_section_coverage(
            obligations=obligations, covered_topics=covered_topics,
            markdown=markdown, evidence_index=self.INDEX,
            manifest_ids=self.MANIFEST_IDS)

    def test_covered_topic_passes(self):
        md = "## S\n\n### Redis\n\nThe redis topic is here. [ev:s:0001]\n"
        r = self._eval(
            [self._ob("redis", ["ev:s:0001"])],
            [{"topic": "redis", "status": "covered", "evidence_ids": ["ev:s:0001"],
              "markdown_anchor": "redis"}], md)
        self.assertEqual(r["failures"], [])
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_COVERED)

    def test_omitted_topic_is_flagged(self):
        r = self._eval([self._ob("redis", ["ev:s:0001"])], [], "## S\n\nNothing.\n")
        self.assertTrue(r["failures"])
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_OMITTED)

    def test_out_of_scope_evidence_id_is_flagged(self):
        md = "## S\n\n### Redis\n\nText. [ev:s:0002]\n"
        r = self._eval(
            [self._ob("redis", ["ev:s:0001"])],
            [{"topic": "redis", "status": "covered", "evidence_ids": ["ev:s:0002"],
              "markdown_anchor": "redis"}], md)
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_INVALID)
        self.assertTrue(any("outside its Phase 3 mapped" in f for f in r["failures"]))

    def test_unresolved_evidence_id_is_flagged(self):
        md = "## S\n\n### Redis\n\nText. [ev:s:0003]\n"
        r = self._eval(
            [self._ob("redis", ["ev:s:0003"])],   # mapped but not in manifest/index
            [{"topic": "redis", "status": "covered", "evidence_ids": ["ev:s:0003"],
              "markdown_anchor": "redis"}], md)
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_INVALID)
        self.assertTrue(any("does not resolve through the citation manifest" in f
                            for f in r["failures"]))

    def test_declared_but_not_cited_in_block_is_flagged(self):
        md = "## S\n\n### Redis\n\nThe redis topic has no citation here.\n"
        r = self._eval(
            [self._ob("redis", ["ev:s:0001"])],
            [{"topic": "redis", "status": "covered", "evidence_ids": ["ev:s:0001"],
              "markdown_anchor": "redis"}], md)
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_INVALID)

    def test_status_not_covered_is_flagged(self):
        md = "## S\n\n### Redis\n\nText. [ev:s:0001]\n"
        r = self._eval(
            [self._ob("redis", ["ev:s:0001"])],
            [{"topic": "redis", "status": "partial", "evidence_ids": ["ev:s:0001"],
              "markdown_anchor": "redis"}], md)
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_INVALID)

    def test_non_obligation_topic_is_not_required(self):
        ob = self._ob("weak topic", [])
        ob["is_obligation"] = False
        ob["evidenced_status"] = "weak"
        r = self._eval([ob], [], "## S\n\nNothing.\n")
        self.assertEqual(r["failures"], [])
        self.assertEqual(r["rows"][0]["generated_status"], gencov.GEN_OMITTED)

    def test_heading_slug_matches_anchor(self):
        self.assertEqual(gencov.heading_slug("### Redis Streams Lifecycle"),
                         "redis-streams-lifecycle")
        self.assertIsNone(gencov.heading_slug("not a heading"))


# ---------------------------------------------------------------------------
class CliSurfaceTests(unittest.TestCase):
    def test_write_wiki_has_coverage_mode_no_section_or_force(self):
        from wiki_generator.cli import build_parser
        parser = build_parser()
        sub = parser._subparsers._group_actions[0].choices["write-wiki"]
        opts = {a for action in sub._actions for a in action.option_strings}
        self.assertIn("--coverage-mode", opts)
        self.assertNotIn("--section", opts)
        self.assertNotIn("--force", opts)

    def test_help_mentions_enhancement_coverage(self):
        env = _subenv()
        res = subprocess.run([sys.executable, "-m", "wiki_generator", "write-wiki",
                              "--help"], cwd=ROOT, capture_output=True, text=True,
                             timeout=120, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("coverage-mode", res.stdout)
        self.assertIn("enhancement", res.stdout)


if __name__ == "__main__":
    unittest.main()
