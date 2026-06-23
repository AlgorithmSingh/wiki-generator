"""Phase 3 (retrieve-evidence) tests.

Runnable with stdlib only: ``python -m unittest discover -s tests -v``.

The end-to-end classes build a *real* bundle once with ``decompose`` +
``build-retrieval``, hand-write deterministic ``plans/`` artifacts against the
bundle's actual symbol IDs/paths (no LLM), then exercise ``retrieve-evidence``.
Pure-logic units (options, query text, schema, aggregate) run without a bundle.
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


def _write_plans(out: str) -> None:
    """Write deterministic plans/ artifacts referencing the bundle's real anchors."""
    syms = {}
    for line in open(os.path.join(out, "symbols", "symbols.jsonl")):
        r = json.loads(line)
        syms[r["name"]] = r["symbol_id"]
    plans = os.path.join(out, "plans")
    os.makedirs(plans, exist_ok=True)

    def sym(name):
        return {"input": name, "symbol_id": syms[name], "resolution": "exact",
                "candidates": []}

    sections = [
        {"schema_version": "phase2-section-plan-v1", "section_id": "overview",
         "title": "Overview", "order": 1, "parent": None, "priority": None,
         "purpose": "Explain what the demo service does.",
         "goal": "Give a high-level overview of the demo FastAPI service and items.",
         "rationale": None, "required_topics": ["demo service overview", "items"],
         "key_questions": ["What does the service do?"],
         "retrieval_needs": {
             "query_packs": [], "symbols": [], "files": [], "contracts": [],
             "tests": [], "graph_nodes": [],
             "search_hints": [{"text": "demo service entrypoint and item model",
                               "scope": ["source"], "reason": "planner search hint"}],
             "context_artifacts": [{"path": "derived/planning-digest.md",
                                    "role": "planner_context",
                                    "citeable_as_evidence": False}]},
         "expected_evidence_types": [], "depends_on": [], "verification_needs": [],
         "estimated_size": None, "known_gaps": [], "normalization_warnings": []},
        {"schema_version": "phase2-section-plan-v1",
         "section_id": "routes-and-handlers", "title": "Routes and Handlers",
         "order": 2, "parent": None, "priority": None,
         "purpose": "Document the HTTP routes and their handlers.",
         "goal": "Describe the /items route and the list_items handler.",
         "rationale": None, "required_topics": ["http routes", "list_items handler"],
         "key_questions": ["What routes are exposed?"],
         "retrieval_needs": {
             "query_packs": ["web_routes"],
             "symbols": [sym("list_items")],
             "files": [{"input": "pkg/api/routes.py:9-11", "path": "pkg/api/routes.py",
                        "anchor": "9-11", "anchor_confidence": "exact_range",
                        "resolution": "file_exists", "candidates": []}],
             "contracts": [{"input": "GET /items", "method": "GET", "path": "/items",
                            "resolution": "exact"}],
             "tests": [],
             "graph_nodes": ["sym:" + syms["list_items"]]},
         "expected_evidence_types": ["symbols", "files", "queries", "contracts", "graph"],
         "depends_on": [], "verification_needs": ["confirm the route path"],
         "estimated_size": None, "known_gaps": [], "normalization_warnings": []},
        {"schema_version": "phase2-section-plan-v1", "section_id": "service-layer",
         "title": "Service Layer", "order": 3, "parent": None, "priority": None,
         "purpose": "Document the service layer and item model.",
         "goal": "Describe the work() function and the Item model.",
         "rationale": None, "required_topics": ["service layer", "item model"],
         "key_questions": ["How are items produced?"],
         "retrieval_needs": {
             "query_packs": ["models_schemas"],
             "symbols": [sym("Item"), sym("work")],
             "files": [{"input": "pkg/svc.py", "path": "pkg/svc.py", "anchor": None,
                        "anchor_confidence": None, "resolution": "file_exists",
                        "candidates": []}],
             "contracts": [],
             "tests": [{"input": "tests/test_svc.py", "path": "tests/test_svc.py",
                        "resolution": "test_file"}],
             "graph_nodes": []},
         "expected_evidence_types": ["symbols", "files", "queries", "tests"],
         "depends_on": [], "verification_needs": [], "estimated_size": None,
         "known_gaps": [], "normalization_warnings": []},
    ]
    doc = {"schema_version": "phase2-plan-v1", "repo": {"name": "demo", "root": out},
           "title": "Demo Documentation Plan", "purpose": "Document the demo service.",
           "summary": "", "audience": "developers",
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


# ---------------------------------------------------------------------------
class Phase3E2ETests(unittest.TestCase):
    """End-to-end over a real decomposed + retrieval-built bundle."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p3_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.master = os.path.join(cls.tmp, "bundle")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        dec = _run_cmd("decompose", "--repo", cls.repo, "--out", cls.master,
                       "--embeddings", "off")
        assert dec.returncode == 0, dec.stderr
        br = _run_cmd("build-retrieval", "--in", cls.master, "--vectors", "off")
        assert br.returncode == 0, br.stderr
        _write_plans(cls.master)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fresh(self) -> str:
        dst = tempfile.mkdtemp(prefix="p3_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        return out

    def _ev(self, out):
        return os.path.join(out, "evidence")

    def test_cli_exposes_command_without_section_flag(self):
        from wiki_generator.cli import build_parser
        parser = build_parser()
        # subcommand exists
        sub = parser._subparsers._group_actions[0].choices
        self.assertIn("retrieve-evidence", sub)
        # no product --section option
        opts = {a for action in sub["retrieve-evidence"]._actions
                for a in action.option_strings}
        self.assertNotIn("--section", opts)
        self.assertNotIn("--section-id", opts)

    def test_end_to_end_pass_and_outputs(self):
        out = self._fresh()
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 0, res.stderr)
        ev = self._ev(out)
        for name in ("evidence-manifest.json", "evidence-packets.jsonl",
                     "retrieval-validation.json", "unresolved-evidence.jsonl",
                     "retrieval-report.md"):
            self.assertTrue(os.path.isfile(os.path.join(ev, name)), name)
        for sid in ("overview", "routes-and-handlers", "service-layer"):
            self.assertTrue(os.path.isfile(os.path.join(ev, "packets", f"{sid}.json")))
        manifest = json.load(open(os.path.join(ev, "evidence-manifest.json")))
        self.assertEqual(manifest["section_count"], 3)
        self.assertEqual(manifest["packet_count"], 3)
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["retrieval_mode"], "lexical-symbolic")

    def test_validation_pass_all_contract_checks(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        v = json.load(open(os.path.join(self._ev(out), "retrieval-validation.json")))
        self.assertEqual(v["status"], "pass")
        self.assertIsNone(v["failure_category"])
        self.assertTrue(all(c["status"] == "pass" for c in v["contract_checks"]),
                        v["contract_checks"])
        self.assertEqual(v["counts"]["sections_processed"], 3)
        # the spec's required contract checks are surfaced as named, auditable entries
        names = {c["name"] for c in v["contract_checks"]}
        for required in ("all_sections_have_packets", "document_plan_valid",
                         "section_plans_cover_order", "capabilities_consistent",
                         "bm25_readable", "vectors_readable_count_consistent",
                         "packets_schema_valid", "evidence_ids_unique",
                         "evidence_anchors_resolve", "no_plan_only_evidence",
                         "no_context_artifact_evidence"):
            self.assertIn(required, names)

    def test_context_artifacts_preserved_but_never_cited(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "overview")
        # preserved in work_order for traceability ...
        self.assertIn("derived/planning-digest.md",
                      p["work_order"]["context_artifacts"])
        # ... but never cited as evidence, and never counted as a 'files' anchor.
        for e in p["evidence"]:
            src = e["source"]
            self.assertFalse(str(src.get("artifact", "")).startswith("derived/planning-"))
            self.assertNotIn("derived/planning-digest.md", str(src.get("path", "")))
            self.assertNotIn("derived/planning-digest.md", str(src.get("artifact", "")))

    def test_combined_jsonl_one_packet_per_section_in_order(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        rows = _read_jsonl(os.path.join(self._ev(out), "evidence-packets.jsonl"))
        self.assertEqual([r["section_id"] for r in rows],
                         ["overview", "routes-and-handlers", "service-layer"])

    def test_rerun_is_byte_identical(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        ev = self._ev(out)
        first = _snapshot(ev)
        _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(first, _snapshot(ev))

    def test_no_timestamps_in_outputs(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        blob = json.dumps(_snapshot(self._ev(out)))
        for needle in ("generated_at", "timestamp", "\"time\":", "created_at"):
            self.assertNotIn(needle, blob)

    def test_exact_file_range_maps_to_source_span(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "routes-and-handlers")
        file_items = [e for e in p["evidence"] if e["lane"] == "file_anchor"]
        self.assertTrue(file_items)
        e = file_items[0]
        self.assertEqual(e["confidence"], "exact")
        self.assertEqual(e["source"]["path"], "pkg/api/routes.py")
        self.assertEqual(e["source"]["range"], {"start_line": 9, "end_line": 11})

    def test_symbol_resolves_to_span_evidence(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "service-layer")
        # 'symbols' coverage satisfied (possibly via a span shared with file_anchor).
        self.assertIn("symbols", p["coverage"]["satisfied"])
        lanes = {e["lane"] for e in p["evidence"]} | {
            l for e in p["evidence"] for l in e["provenance"].get("lanes", [])}
        self.assertIn("symbol_anchor", lanes)

    def test_query_pack_maps_to_source_with_provenance(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "routes-and-handlers")
        qp = [e for e in p["evidence"] if e["lane"] == "query_pack"]
        self.assertTrue(qp)
        prov = qp[0]["provenance"]
        self.assertEqual(prov.get("pack"), "web_routes")
        self.assertEqual(prov.get("rule_path"), "queries/rules/rg/web_routes.json")

    def test_contract_exact_operation_and_handler_link(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "routes-and-handlers")
        ops = [e for e in p["evidence"] if e["type"] == "route_operation"]
        self.assertTrue(ops)
        self.assertEqual(ops[0]["source"]["json_pointer"], "/paths/~1items/get")
        self.assertEqual(ops[0]["confidence"], "exact")
        # handler recovered via x-handler-symbol-id (folds into the symbol span).
        matched = {e["provenance"].get("matched_by") for e in p["evidence"]}
        matched |= {a.get("matched_by") for e in p["evidence"]
                    for a in e["provenance"].get("additional", [])}
        self.assertIn("contract_handler", matched)

    def test_graph_neighbors_one_hop(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        p = _packet(self._ev(out), "routes-and-handlers")
        gn = [e for e in p["evidence"] if e["lane"] == "graph_neighbors"]
        self.assertTrue(gn)
        for e in gn:
            self.assertIn(e["confidence"], ("medium", "low"))
            self.assertEqual(e["provenance"]["matched_by"], "graph_edge")

    def test_vector_lane_capability_disabled_in_lexical_mode(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        for sid in ("overview", "routes-and-handlers", "service-layer"):
            p = _packet(self._ev(out), sid)
            self.assertEqual(p["lane_summary"]["vector"]["status"], "capability_disabled")

    def test_evidence_ids_unique_sorted_and_anchored(self):
        out = self._fresh()
        _run_cmd("retrieve-evidence", "--bundle", out)
        for sid in ("overview", "routes-and-handlers", "service-layer"):
            p = _packet(self._ev(out), sid)
            ids = [e["evidence_id"] for e in p["evidence"]]
            self.assertEqual(ids, sorted(ids))
            self.assertEqual(len(ids), len(set(ids)))
            for n, e in enumerate(p["evidence"], 1):
                self.assertEqual(e["evidence_id"], f"ev:{sid}:{n:04d}")
                src = e["source"]
                self.assertTrue(src.get("artifact"))
                self.assertFalse(str(src["artifact"]).startswith("plans/"))


# ---------------------------------------------------------------------------
class Phase3FailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p3f_")
        repo = os.path.join(cls.tmp, "repo")
        cls.master = os.path.join(cls.tmp, "bundle")
        os.makedirs(repo)
        _make_repo(repo)
        assert _run_cmd("decompose", "--repo", repo, "--out", cls.master,
                        "--embeddings", "off").returncode == 0
        assert _run_cmd("build-retrieval", "--in", cls.master,
                        "--vectors", "off").returncode == 0
        _write_plans(cls.master)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fresh(self) -> str:
        dst = tempfile.mkdtemp(prefix="p3f_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        return out

    def test_missing_document_plan_is_bad_input(self):
        out = self._fresh()
        os.remove(os.path.join(out, "plans", "document-plan.json"))
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 2, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_missing_input_artifact")
        self.assertTrue(os.path.isfile(os.path.join(out, "evidence",
                                                    "retrieval-report.md")))

    def test_missing_section_plan_is_bad_plan(self):
        out = self._fresh()
        rows = _read_jsonl(os.path.join(out, "plans", "section-plans.jsonl"))
        rows = [r for r in rows if r["section_id"] != "service-layer"]
        with open(os.path.join(out, "plans", "section-plans.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 3, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_underspecified_normalized_plan")

    def test_corrupt_bm25_with_capability_enabled_is_bad_input(self):
        out = self._fresh()
        with open(os.path.join(out, "rag", "bm25.sqlite"), "wb") as f:
            f.write(b"not a real sqlite database")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 2, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_missing_input_artifact")

    def test_vectors_enabled_but_missing_files_is_bad_input(self):
        out = self._fresh()
        caps_path = os.path.join(out, "rag", "retrieval-capabilities.json")
        caps = json.load(open(caps_path))
        caps["retrieval_mode"] = "hybrid"
        caps["capabilities"]["vectors"] = True
        caps.setdefault("indexes", {})["vectors"] = {
            "path": "rag/vectors.faiss", "metadata_path": "rag/vector-metadata.json",
            "metadata_format": "json", "row_count": 5, "model": "x",
            "distance": "cosine", "status": "built", "reason": None}
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2)
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 2, res.stderr)

    def test_duplicate_span_id_is_bad_input(self):
        out = self._fresh()
        sp = os.path.join(out, "rag", "spans.jsonl")
        rows = _read_jsonl(sp)
        with open(sp, "a") as f:           # re-append the first span row (dup id)
            f.write(json.dumps(rows[0]) + "\n")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 2, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_missing_input_artifact")

    def test_underspecified_section_unresolved_symbol_is_bad_plan(self):
        out = self._fresh()
        rows = _read_jsonl(os.path.join(out, "plans", "section-plans.jsonl"))
        for r in rows:
            if r["section_id"] == "service-layer":
                r["retrieval_needs"] = {"query_packs": [], "files": [], "contracts": [],
                                        "tests": [], "graph_nodes": [],
                                        "symbols": [{"input": "Nope.does_not_exist",
                                                     "symbol_id": None,
                                                     "resolution": "no_match",
                                                     "candidates": []}]}
                r["expected_evidence_types"] = ["symbols"]
                r["required_topics"] = []
                r["key_questions"] = []
                r["verification_needs"] = []
                r["purpose"] = ""
                r["goal"] = ""
                r["title"] = ""
        with open(os.path.join(out, "plans", "section-plans.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 3, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["failure_category"], "bad_underspecified_normalized_plan")
        sl = next(s for s in v["section_results"] if s["section_id"] == "service-layer")
        self.assertEqual(sl["status"], "fail")

    def test_no_signal_section_gets_no_generic_fallback(self):
        # Patch 3: a normal section with NO retrieval signal (no exact lanes, no
        # query packs, no search hints — only title/purpose prose) must NOT be
        # rescued by generic BM25/vector fallback. The recall lanes are not run
        # and the section fails as an underspecified plan.
        out = self._fresh()
        rows = _read_jsonl(os.path.join(out, "plans", "section-plans.jsonl"))
        for r in rows:
            if r["section_id"] == "service-layer":
                r["retrieval_needs"] = {"query_packs": [], "symbols": [], "files": [],
                                        "contracts": [], "tests": [], "graph_nodes": [],
                                        "search_hints": []}
                r["expected_evidence_types"] = []
        with open(os.path.join(out, "plans", "section-plans.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 3, res.stderr)
        p = json.load(open(os.path.join(out, "evidence", "packets",
                                        "service-layer.json")))
        self.assertEqual(p["evidence"], [])
        # the generic recall lanes were never requested for a no-signal section
        self.assertEqual(p["lane_summary"]["bm25"]["status"], "not_requested")
        self.assertEqual(p["lane_summary"]["vector"]["status"], "not_requested")

    def test_provenance_section_handled_outside_evidence_lanes(self):
        # Patch 3: an explicitly-marked controlled provenance/meta section is
        # non-source — Phase 3 performs no source retrieval, emits no evidence,
        # and the run still PASSES (absence of evidence is correct here).
        out = self._fresh()
        rows = _read_jsonl(os.path.join(out, "plans", "section-plans.jsonl"))
        for r in rows:
            if r["section_id"] == "service-layer":
                r["section_role"] = "provenance"
                r["retrieval_needs"] = {
                    "query_packs": [], "symbols": [], "files": [], "contracts": [],
                    "tests": [], "graph_nodes": [], "search_hints": [],
                    "context_artifacts": [{"path": "derived/planning-gaps.md",
                                           "role": "planner_context",
                                           "citeable_as_evidence": False}]}
                r["expected_evidence_types"] = []
        with open(os.path.join(out, "plans", "section-plans.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 0, res.stderr)
        p = json.load(open(os.path.join(out, "evidence", "packets",
                                        "service-layer.json")))
        self.assertEqual(p.get("section_role"), "provenance")
        self.assertEqual(p["evidence"], [])
        self.assertEqual(p["validation"]["status"], "pass")
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["status"], "pass")

    def test_ragflow_section_passes_after_readiness_normalization(self):
        # Regression for the RAGFlow failure: a section whose ORIGINAL plan put a
        # vague symbol / openapi.json-only contract / digest file in exact lanes.
        # After the Phase 2 readiness fix it carries only resolvable handles, with
        # the broad request in search_hints[] and the digest in context_artifacts[],
        # and expected_evidence_types reduced to what resolves. Phase 3 must PASS —
        # this is exactly the bad_underspecified_normalized_plan that is now closed.
        out = self._fresh()
        syms = {json.loads(l)["name"]: json.loads(l)["symbol_id"]
                for l in open(os.path.join(out, "symbols", "symbols.jsonl"))}
        sec = {
            "schema_version": "phase2-section-plan-v1", "section_id": "api-routes",
            "title": "API Routes", "order": 1, "parent": None, "priority": None,
            "purpose": "Document the HTTP API routes.", "goal": "Describe the routes.",
            "rationale": None, "required_topics": ["api routes"],
            "key_questions": ["what routes?"],
            "retrieval_needs": {
                "query_packs": ["web_routes"],
                "symbols": [{"input": "list_items", "symbol_id": syms["list_items"],
                             "resolution": "exact", "candidates": []}],
                "files": [], "contracts": [], "tests": [], "graph_nodes": [],
                "search_hints": [{"text": "retrieve: api.apps.* route handlers",
                                  "scope": ["query_pack:web_routes"],
                                  "reason": "non-exact contract (hint)"}],
                "context_artifacts": [{"path": "derived/planning-digest.md",
                                       "role": "planner_context",
                                       "citeable_as_evidence": False}]},
            "expected_evidence_types": ["symbols", "queries"],
            "depends_on": [], "verification_needs": [], "estimated_size": None,
            "known_gaps": [], "normalization_warnings": []}
        doc = json.load(open(os.path.join(out, "plans", "document-plan.json")))
        doc["section_order"] = ["api-routes"]
        with open(os.path.join(out, "plans", "document-plan.json"), "w") as f:
            json.dump(doc, f, indent=2)
        with open(os.path.join(out, "plans", "section-plans.jsonl"), "w") as f:
            f.write(json.dumps(sec) + "\n")

        res = _run_cmd("retrieve-evidence", "--bundle", out)
        self.assertEqual(res.returncode, 0, res.stderr)
        v = json.load(open(os.path.join(out, "evidence", "retrieval-validation.json")))
        self.assertEqual(v["status"], "pass")
        self.assertIsNone(v["failure_category"])
        checks = {c["name"]: c["status"] for c in v["contract_checks"]}
        self.assertEqual(checks.get("no_context_artifact_evidence"), "pass")
        p = json.load(open(os.path.join(out, "evidence", "packets", "api-routes.json")))
        self.assertIn("derived/planning-digest.md", p["work_order"]["context_artifacts"])
        for e in p["evidence"]:
            self.assertFalse(str(e["source"].get("artifact", "")).startswith("derived/"))
            self.assertNotIn("derived/planning-", str(e["source"].get("path", "")))


# ---------------------------------------------------------------------------
class Phase3HybridVectorTests(unittest.TestCase):
    """Vector lane runs (via an injected backend) when capabilities are hybrid."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p3v_")
        repo = os.path.join(cls.tmp, "repo")
        cls.master = os.path.join(cls.tmp, "bundle")
        os.makedirs(repo)
        _make_repo(repo)
        assert _run_cmd("decompose", "--repo", repo, "--out", cls.master,
                        "--embeddings", "off").returncode == 0
        assert _run_cmd("build-retrieval", "--in", cls.master,
                        "--vectors", "off").returncode == 0
        _write_plans(cls.master)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fresh(self) -> str:
        dst = tempfile.mkdtemp(prefix="p3v_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        return out

    def test_hybrid_fixture_recovers_chunks_via_vector_metadata(self):
        out = self._fresh()
        chunks = _read_jsonl(os.path.join(out, "rag", "chunks.jsonl"))
        picked = chunks[:3]
        meta = {"schema_version": "vector-metadata-v1", "model": "fake", "distance":
                "cosine", "count": len(picked),
                "vectors": [{"ordinal": i, "chunk_id": c["chunk_id"],
                             "span_ids": c.get("span_ids", []), "path": c["path"],
                             "range": c["range"], "language": c.get("language"),
                             "category": c.get("category"), "sha256": c.get("sha256")}
                            for i, c in enumerate(picked)]}
        with open(os.path.join(out, "rag", "vector-metadata.json"), "w") as f:
            json.dump(meta, f, indent=2)
        _make_faiss(os.path.join(out, "rag", "vectors.faiss"), len(picked))
        caps_path = os.path.join(out, "rag", "retrieval-capabilities.json")
        caps = json.load(open(caps_path))
        caps["retrieval_mode"] = "hybrid"
        caps["capabilities"]["vectors"] = True
        caps.setdefault("indexes", {})["vectors"] = {
            "path": "rag/vectors.faiss", "metadata_path": "rag/vector-metadata.json",
            "metadata_format": "json", "row_count": len(picked), "model": "fake",
            "distance": "cosine", "status": "built", "reason": None}
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2)

        from wiki_generator.libs import evidence

        class FakeBackend:
            def probe(self):
                return True, None

            def query(self, index_path, query_text, *, model, k):
                return [(0, 0.91), (1, 0.80)][:k]

        opts = evidence.EvidenceOptions(bundle_root=out,
                                        out_dir=os.path.join(out, "evidence"))
        res = evidence.run(opts, vector_backend=FakeBackend())
        self.assertEqual(res.retrieval_mode, "hybrid")
        self.assertEqual(res.exit_code, 0, res.warnings)
        p = _packet(os.path.join(out, "evidence"), "overview")
        self.assertEqual(p["lane_summary"]["vector"]["status"], "pass")
        vecs = [e for e in p["evidence"] if e["lane"] == "vector"] + [
            e for e in p["evidence"] if "vector" in e["provenance"].get("lanes", [])]
        self.assertTrue(vecs, "expected vector-lane evidence in hybrid mode")


# ---------------------------------------------------------------------------
class Phase3UnitTests(unittest.TestCase):
    def test_options_reject_nonpositive_caps(self):
        from wiki_generator.libs.evidence import EvidenceOptions
        with self.assertRaises(ValueError):
            EvidenceOptions(bundle_root="/b", out_dir="/o", max_per_lane=0)
        with self.assertRaises(ValueError):
            EvidenceOptions(bundle_root="/b", out_dir="/o", max_total_per_section=0)

    def test_query_text_orders_and_dedupes(self):
        from wiki_generator.libs.evidence.query_text import build_query_text
        section = {"title": "Routes", "purpose": "routes", "goal": "",
                   "required_topics": ["routes", "Handlers"],
                   "key_questions": ["what routes"], "verification_needs": [],
                   "retrieval_needs": {}}
        q = build_query_text(section)
        # 'Routes' (title) case-insensitively dedupes purpose 'routes' and the
        # required_topic 'routes'; first occurrence's casing is preserved.
        self.assertEqual(q, "Routes Handlers what routes")

    def test_query_text_folds_search_hints(self):
        from wiki_generator.libs.evidence.query_text import build_query_text
        section = {"title": "Routes", "purpose": "", "goal": "",
                   "required_topics": [], "key_questions": [],
                   "verification_needs": [],
                   "retrieval_needs": {"search_hints": [
                       {"text": "api.apps route handlers"},
                       {"text": "Routes"},        # case-insensitively deduped vs title
                       "module layout"]}}          # tolerate a bare string too
        q = build_query_text(section)
        self.assertEqual(q, "Routes api.apps route handlers module layout")

    def test_validate_packet_flags_missing_anchor_and_dup_id(self):
        from wiki_generator.libs.evidence.schema import validate_packet
        packet = {
            "schema_version": "phase3-evidence-packet-v1", "section_id": "s",
            "title": "S", "order": 1, "retrieval_mode": "lexical-symbolic",
            "source_plan": {}, "work_order": {}, "lane_summary": {}, "coverage": {},
            "validation": {},
            "evidence": [
                {"evidence_id": "ev:s:0001", "lane": "bm25", "type": "source_chunk",
                 "source": {"artifact": "rag/chunks.jsonl"}, "excerpt": "x",
                 "provenance": {}, "scores": {}, "confidence": "medium",
                 "dedupe_key": "k1"},
                {"evidence_id": "ev:s:0001", "lane": "bogus", "type": "x",
                 "source": {"artifact": "rag/chunks.jsonl", "chunk_id": "c"},
                 "excerpt": "y", "provenance": {}, "scores": {},
                 "confidence": "nope", "dedupe_key": "k2"}],
        }
        errors = validate_packet(packet)
        joined = " ".join(errors)
        self.assertIn("no stable source anchor", joined)   # item 0
        self.assertIn("duplicate evidence_id", joined)     # item 1
        self.assertIn("illegal lane", joined)
        self.assertIn("illegal confidence", joined)

    def test_aggregate_prefers_span_over_chunk_and_merges_provenance(self):
        from wiki_generator.libs.evidence.aggregate import aggregate
        from wiki_generator.libs.evidence.model import (
            LaneResult, build_scores, chunk_hit, span_hit)
        from wiki_generator.libs.evidence.options import EvidenceOptions
        span = {"span_id": "span:f.py:1-5:function", "path": "f.py",
                "range": {"start_line": 1, "end_line": 5}, "text": "code"}
        chunk = {"chunk_id": "chunk:f.py:1-5", "path": "f.py",
                 "range": {"start_line": 1, "end_line": 5}, "text": "code",
                 "span_ids": []}
        sym_lr = LaneResult(lane="symbol_anchor", requested=1, resolved=1, status="pass",
                            hits=[span_hit(span, lane="symbol_anchor", confidence="exact",
                                           lane_rank=1, provenance={"matched_by": "symbol_id"})])
        bm_lr = LaneResult(lane="bm25", requested=1, resolved=1, status="pass",
                           hits=[chunk_hit(chunk, lane="bm25", confidence="medium",
                                           lane_rank=1, provenance={"matched_by": "bm25"},
                                           scores=build_scores(lane_rank=1, bm25=2.0))])
        opts = EvidenceOptions(bundle_root="/b", out_dir="/o")
        evidence, summary, lanes, _cov = aggregate("s", [sym_lr, bm_lr], opts)
        self.assertEqual(len(evidence), 1)              # chunk folded into the span
        item = evidence[0]
        self.assertEqual(item["lane"], "symbol_anchor")
        self.assertEqual(item["type"], "source_span")
        self.assertIn("bm25", item["provenance"].get("lanes", []))
        self.assertEqual(item["scores"]["bm25"], 2.0)   # merged score preserved
        self.assertEqual(lanes, {"symbol_anchor", "bm25"})

    def test_aggregate_does_not_demote_strong_chunk_into_weak_span(self):
        # A low-confidence graph span and a high-confidence file_anchor chunk at the
        # SAME range must collapse to one item that keeps the strongest authority.
        from wiki_generator.libs.evidence.aggregate import aggregate
        from wiki_generator.libs.evidence.model import LaneResult, chunk_hit, span_hit
        from wiki_generator.libs.evidence.options import EvidenceOptions
        span = {"span_id": "span:f.py:1-5:doc", "path": "f.py",
                "range": {"start_line": 1, "end_line": 5}, "text": "x"}
        chunk = {"chunk_id": "chunk:f.py:1-5", "path": "f.py",
                 "range": {"start_line": 1, "end_line": 5}, "text": "x", "span_ids": []}
        graph_lr = LaneResult(lane="graph_neighbors", requested=1, resolved=1,
                              status="pass",
                              hits=[span_hit(span, lane="graph_neighbors",
                                             confidence="low", lane_rank=1,
                                             provenance={"matched_by": "graph_edge"})])
        file_lr = LaneResult(lane="file_anchor", requested=1, resolved=1, status="pass",
                             hits=[chunk_hit(chunk, lane="file_anchor",
                                             confidence="high", lane_rank=1,
                                             provenance={"matched_by": "file_range"})])
        opts = EvidenceOptions(bundle_root="/b", out_dir="/o")
        evidence, _, lanes, _cov = aggregate("s", [graph_lr, file_lr], opts)
        self.assertEqual(len(evidence), 1)
        item = evidence[0]
        self.assertEqual(item["confidence"], "high")     # not demoted to low
        self.assertEqual(item["lane"], "file_anchor")    # strongest lane wins primary
        self.assertEqual(item["type"], "source_span")    # span anchor preserved
        self.assertEqual(lanes, {"file_anchor", "graph_neighbors"})

    def test_symbols_lane_emits_class_member_spans_within_cap(self):
        from wiki_generator.libs.evidence.lanes import symbols as symbols_lane
        from wiki_generator.libs.evidence.options import EvidenceOptions

        class FakeBundle:
            def __init__(self):
                self.syms = {
                    "C": {"symbol_id": "C", "kind": "class", "path": "m.py",
                          "range": {"start_line": 1, "end_line": 40}, "span_id": "sC"},
                    "C.m0": {"symbol_id": "C.m0", "kind": "method", "path": "m.py",
                             "range": {"start_line": 5, "end_line": 9}, "span_id": "sm0"},
                    "C.m1": {"symbol_id": "C.m1", "kind": "method", "path": "m.py",
                             "range": {"start_line": 11, "end_line": 15}, "span_id": "sm1"}}
                self.spans = {
                    "sC": {"span_id": "sC", "path": "m.py",
                           "range": {"start_line": 1, "end_line": 3}, "text": "class C"},
                    "sm0": {"span_id": "sm0", "path": "m.py",
                            "range": {"start_line": 5, "end_line": 9}, "text": "def m0"},
                    "sm1": {"span_id": "sm1", "path": "m.py",
                            "range": {"start_line": 11, "end_line": 15}, "text": "def m1"}}
                self.chunks = [{"chunk_id": f"ch{i}", "path": "m.py",
                                "range": {"start_line": i, "end_line": i + 1},
                                "text": "c", "span_ids": []} for i in range(1, 40)]

            def symbol(self, sid):
                return self.syms.get(sid)

            def span(self, sid):
                return self.spans.get(sid)

            def children_of(self, sid):
                return [self.syms["C.m0"], self.syms["C.m1"]] if sid == "C" else []

            def overlapping_chunks(self, path, s, e, cap):
                return self.chunks[:cap]

        section = {"section_id": "s", "retrieval_needs": {
            "symbols": [{"input": "C", "symbol_id": "C", "resolution": "exact"}]}}
        opts = EvidenceOptions(bundle_root="/b", out_dir="/o", max_per_lane=8)
        res = symbols_lane.run(FakeBundle(), section, opts)
        matched = [h.provenance.get("matched_by") for h in res.hits]
        self.assertIn("class_member", matched)   # children are not starved by chunks

    def test_resolve_pointer_traverses_arrays(self):
        from wiki_generator.libs.evidence.validate import _resolve_pointer
        doc = {"paths": {"/x": {"get": {"parameters": [{"name": "q"}]}}}}
        found, val = _resolve_pointer(doc, "/paths/~1x/get/parameters/0/name")
        self.assertTrue(found)
        self.assertEqual(val, "q")
        found2, _ = _resolve_pointer(doc, "/paths/~1x/get/parameters/5/name")
        self.assertFalse(found2)


# ---------------------------------------------------------------------------
# Iteration 3: balanced per-request exact-evidence coverage after capping.
# These are pure-logic unit tests over synthetic lane results — no bundle build,
# no LLM, deterministic.
def _agg():
    from wiki_generator.libs.evidence.aggregate import aggregate
    return aggregate


def _opts(**kw):
    from wiki_generator.libs.evidence.options import EvidenceOptions
    return EvidenceOptions(bundle_root="/b", out_dir="/o", **kw)


def _file_chunk(path, s, e):
    return {"chunk_id": f"chunk:{path}:{s}-{e}", "path": path,
            "range": {"start_line": s, "end_line": e},
            "text": f"{path}:{s}-{e}", "span_ids": []}


def _file_lane(files_with_counts, *, start_rank=0):
    """A file_anchor LaneResult with ``n`` representative chunks per requested file.

    ``files_with_counts`` is a list of ``(path, n_candidates)``; later files get
    higher lane_rank (as the real lane assigns them) so global sorting alone would
    starve them — the allocator must rebalance."""
    from wiki_generator.libs.evidence.model import (
        LaneResult, chunk_hit, exact_request)
    res = LaneResult(lane="file_anchor", requested=len(files_with_counts),
                     resolved=0, status="pass")
    rank = start_rank
    for i, (path, n) in enumerate(files_with_counts):
        res.resolved += 1
        field = f"retrieval_needs.files[{i}]"
        req = exact_request(lane="file_anchor", source_field=field,
                            requested_input=path, handle_field="resolved_path",
                            resolved_handle=path, resolution="file_exists")
        for j in range(n):
            rank += 1
            s = 1 + j * 10
            res.hits.append(chunk_hit(
                _file_chunk(path, s, s + 5), lane="file_anchor", confidence="high",
                lane_rank=rank, request=req,
                provenance={"section_plan_field": field, "input": path,
                            "matched_by": "file_repr"}))
    return res


def _bm25_lane(n, *, confidence="medium"):
    from wiki_generator.libs.evidence.model import (
        LaneResult, build_scores, chunk_hit)
    res = LaneResult(lane="bm25", requested=1, resolved=1, status="pass")
    for j in range(n):
        res.hits.append(chunk_hit(
            _file_chunk("other/recall.py", 100 + j * 10, 105 + j * 10), lane="bm25",
            confidence=confidence, lane_rank=j + 1,
            provenance={"section_plan_field": "query_text", "input": "q",
                        "matched_by": "bm25"},
            scores=build_scores(lane_rank=j + 1, lane_score=9.0, bm25=9.0)))
    return res


_RAG_CORE_FILES = ["rag/flow/parser/parser.py", "rag/nlp/search.py",
                   "deepdoc/parser/pdf_parser.py", "rag/llm/embedding_model.py"]


class Phase3Iteration3Tests(unittest.TestCase):
    def test_four_files_cap_eight_balanced_includes_all(self):
        # Case 1 + 7 (regression): 4 requested files, candidates for all, an
        # effective file-anchor cap of 8 -> ~2 kept items per file, NOT 8/0/0/0.
        from collections import Counter
        lr = _file_lane([(p, 8) for p in _RAG_CORE_FILES])
        ev, _summary, _lanes, cov = _agg()(
            "subsystem-rag-core", [lr],
            _opts(max_total_per_section=8, max_per_lane=8))
        self.assertEqual(len(ev), 8)
        by_path = Counter(e["source"]["path"] for e in ev)
        for p in _RAG_CORE_FILES:
            self.assertEqual(by_path[p], 2, f"{p}: {dict(by_path)}")
        # the live-failure file is present and covered.
        self.assertIn("rag/llm/embedding_model.py", by_path)
        self.assertTrue(all(r["status"] == "covered" for r in cov), cov)
        emb = next(r for r in cov
                   if r["resolved_path"] == "rag/llm/embedding_model.py")
        self.assertEqual(emb["status"], "covered")
        self.assertEqual(emb["kept_count"], 2)
        self.assertEqual(len(emb["evidence_ids"]), 2)

    def test_exact_obligations_beat_broad_recall_for_budget(self):
        # Case 2: high-scoring broad-recall (bm25) candidates must not consume the
        # section budget before exact minima/depth are allocated.
        from collections import Counter
        lr = _file_lane([(p, 2) for p in _RAG_CORE_FILES])  # 8 exact candidates
        bm = _bm25_lane(6, confidence="high")               # 6 "high" recall hits
        ev, summary, _lanes, cov = _agg()(
            "subsystem-rag-core", [lr, bm],
            _opts(max_total_per_section=8, max_per_lane=8))
        self.assertEqual(len(ev), 8)
        lanes = Counter(e["lane"] for e in ev)
        self.assertEqual(lanes["bm25"], 0)            # broad recall got no budget
        self.assertEqual(lanes["file_anchor"], 8)
        for p in _RAG_CORE_FILES:                     # every exact file covered
            self.assertTrue(any(e["source"]["path"] == p for e in ev), p)
        self.assertTrue(all(r["status"] == "covered" for r in cov))

    def test_uneven_candidates_still_cover_every_file(self):
        # Water-fill redistribution: one dominant file + three single-candidate
        # files. Every file (incl. the last) keeps its minimum; the dominant file
        # absorbs the redistributed depth — never starving the others.
        from collections import Counter
        lr = _file_lane([("rag/flow/parser/parser.py", 10),
                         ("rag/nlp/search.py", 1),
                         ("deepdoc/parser/pdf_parser.py", 1),
                         ("rag/llm/embedding_model.py", 1)])
        ev, _summary, _lanes, cov = _agg()(
            "s", [lr], _opts(max_total_per_section=8, max_per_lane=8))
        by_path = Counter(e["source"]["path"] for e in ev)
        for p in _RAG_CORE_FILES:
            self.assertGreaterEqual(by_path[p], 1, dict(by_path))
        self.assertEqual(by_path["rag/flow/parser/parser.py"], 5)  # absorbs depth
        self.assertTrue(all(r["status"] == "covered" for r in cov))

    def test_resolved_file_with_no_chunks_reports_no_hits(self):
        # Case 4: a file_exists request whose file has no chunks reports no_hits
        # explicitly in per-request coverage rather than disappearing.
        from wiki_generator.libs.evidence.model import LaneResult
        lr = LaneResult(lane="file_anchor", requested=1, resolved=1, status="miss")
        lr.unresolved.append({
            "section_id": "s", "type": "file", "input": "pkg/empty.py",
            "reason": "no_hits", "source_field": "retrieval_needs.files[0]",
            "candidates": []})
        section = {"section_id": "s", "retrieval_needs": {"files": [
            {"input": "pkg/empty.py", "path": "pkg/empty.py",
             "resolution": "file_exists"}]}}
        ev, _summary, _lanes, cov = _agg()("s", [lr], _opts(), section)
        self.assertEqual(ev, [])
        self.assertEqual(len(cov), 1)
        rec = cov[0]
        self.assertEqual(rec["status"], "no_hits")
        self.assertEqual(rec["resolved_path"], "pkg/empty.py")
        self.assertEqual(rec["candidate_count"], 0)
        self.assertEqual(rec["kept_count"], 0)
        # no_hits with no candidates is NOT a fail-closed coverage failure.
        from wiki_generator.libs.evidence.validate import exact_coverage_failures
        errs, sids = exact_coverage_failures(
            [{"section_id": "s", "coverage": {"exact_requests": cov}}])
        self.assertEqual(errs, [])

    def test_search_hints_are_not_exact_obligations(self):
        # Case 5: a search_hints-driven bm25 lane with no result must not create a
        # starved_by_cap or any exact coverage record.
        from wiki_generator.libs.evidence.model import LaneResult
        bm = LaneResult(lane="bm25", requested=1, resolved=0, status="empty")
        ev, _summary, _lanes, cov = _agg()("s", [bm], _opts())
        self.assertEqual(ev, [])
        self.assertEqual(cov, [])               # no exact obligations from hints

    def test_total_cap_too_small_starves_and_fails_closed(self):
        # Case 6: more exact requests with candidates than max_total_per_section
        # -> keep a deterministic subset, mark the rest starved_by_cap, fail closed.
        lr = _file_lane([(p, 4) for p in _RAG_CORE_FILES[:3]])
        ev, _summary, _lanes, cov = _agg()(
            "s", [lr], _opts(max_total_per_section=2, max_per_lane=8))
        self.assertEqual(len(ev), 2)
        starved = [r for r in cov if r["status"] == "starved_by_cap"]
        covered = [r for r in cov if r["status"] == "covered"]
        self.assertEqual(len(covered), 2)
        self.assertEqual(len(starved), 1)
        self.assertIn("infeasible", starved[0]["reason"])
        from wiki_generator.libs.evidence.validate import exact_coverage_failures
        errs, sids = exact_coverage_failures(
            [{"section_id": "s", "coverage": {"exact_requests": cov}}])
        self.assertTrue(errs)                   # fail closed
        self.assertEqual(sids, ["s"])

    def test_feasible_request_absent_fails_validation(self):
        # Case 3: a resolved exact file with candidates but zero kept evidence,
        # while minima fit under hard caps, must fail validation as an
        # aggregation/allocation implementation error — never a clean pass.
        from wiki_generator.libs.evidence.validate import exact_coverage_failures
        packet = {"section_id": "subsystem-rag-core", "coverage": {"exact_requests": [
            {"lane": "file_anchor",
             "source_field": "retrieval_needs.files[3]",
             "requested_input": "rag/llm/embedding_model.py",
             "resolved_path": "rag/llm/embedding_model.py",
             "resolution": "file_exists", "candidate_count": 6, "kept_count": 0,
             "evidence_ids": [], "status": "covered"}]}}  # mislabelled "covered"
        errs, sids = exact_coverage_failures([packet])
        self.assertTrue(errs, "feasible candidate>0/kept==0 must fail closed")
        self.assertEqual(sids, ["subsystem-rag-core"])

    def test_merged_representative_preserves_both_request_identities(self):
        # Case 8: when two exact requests dedupe to one representative (a shared
        # span), the kept item covers both only because merged provenance/coverage
        # records preserve both identities.
        from wiki_generator.libs.evidence.model import (
            LaneResult, exact_request, span_hit)
        span = {"span_id": "span:a.py:1-5", "path": "a.py",
                "range": {"start_line": 1, "end_line": 5}, "text": "x"}
        freq = exact_request(lane="file_anchor",
                             source_field="retrieval_needs.files[0]",
                             requested_input="a.py", handle_field="resolved_path",
                             resolved_handle="a.py", resolution="file_exists")
        sreq = exact_request(lane="symbol_anchor",
                             source_field="retrieval_needs.symbols[0]",
                             requested_input="S", handle_field="resolved_symbol_id",
                             resolved_handle="S", resolution="exact")
        flr = LaneResult(lane="file_anchor", requested=1, resolved=1, status="pass",
                         hits=[span_hit(span, lane="file_anchor", confidence="exact",
                                        lane_rank=1, request=freq,
                                        provenance={"matched_by": "file_range"})])
        slr = LaneResult(lane="symbol_anchor", requested=1, resolved=1,
                         status="pass",
                         hits=[span_hit(span, lane="symbol_anchor", confidence="exact",
                                        lane_rank=1, request=sreq,
                                        provenance={"matched_by": "symbol_id"})])
        ev, _summary, _lanes, cov = _agg()("s", [flr, slr], _opts())
        self.assertEqual(len(ev), 1)            # deduped to one representative
        eid = ev[0]["evidence_id"]
        self.assertEqual(len(cov), 2)
        self.assertTrue(all(r["status"] == "covered" for r in cov))
        for r in cov:
            self.assertEqual(r["evidence_ids"], [eid])  # both tied to the one item

    def test_byte_stable_over_identical_inputs(self):
        # Case 9: two runs over freshly-built identical synthetic inputs produce
        # byte-identical evidence + coverage.
        def run_once():
            lr = _file_lane([(p, 3) for p in _RAG_CORE_FILES])
            bm = _bm25_lane(4)
            ev, summary, _lanes, cov = _agg()(
                "subsystem-rag-core", [lr, bm],
                _opts(max_total_per_section=10, max_per_lane=8))
            return json.dumps({"evidence": ev, "coverage": cov, "summary": summary},
                              sort_keys=True)
        self.assertEqual(run_once(), run_once())


def _snapshot(d: str) -> dict:
    out = {}
    for base, _, files in os.walk(d):
        for name in files:
            p = os.path.join(base, name)
            with open(p, encoding="utf-8") as f:
                out[os.path.relpath(p, d)] = f.read()
    return out


def _packet(ev_dir: str, sid: str) -> dict:
    return json.load(open(os.path.join(ev_dir, "packets", f"{sid}.json")))


def _make_faiss(path: str, n: int) -> None:
    """Write a real FAISS index when faiss is importable, else a placeholder file."""
    try:
        import faiss  # type: ignore
        import numpy as np
        mat = np.zeros((n, 8), dtype="float32")
        for i in range(n):
            mat[i][i % 8] = 1.0
        index = faiss.IndexFlatIP(8)
        index.add(mat)
        faiss.write_index(index, path)
    except Exception:
        with open(path, "wb") as f:
            f.write(b"FAISSPLACEHOLDER")


if __name__ == "__main__":
    unittest.main()
