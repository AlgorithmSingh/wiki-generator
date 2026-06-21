"""End-to-end + unit tests for wiki_generator. Runnable with stdlib only:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wiki_generator.libs import config, ids  # noqa: E402
from wiki_generator.libs import chunker  # noqa: E402
from wiki_generator.libs.lanes import symbols as symmod  # noqa: E402


def _read_jsonl(path):
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _make_repo(d: str) -> None:
    os.makedirs(os.path.join(d, "pkg", "api"), exist_ok=True)
    os.makedirs(os.path.join(d, "tests"), exist_ok=True)
    files = {
        "pkg/__init__.py": '"""Pkg."""\n',
        "pkg/api/__init__.py": "",
        "pkg/api/routes.py": (
            '"""Routes."""\n'
            "from fastapi import APIRouter\n"
            "from pkg.svc import work\n\n"
            "router = APIRouter()\n\n\n"
            '@router.get("/items")\n'
            "async def list_items(limit: int = 10) -> list:\n"
            '    """List items."""\n'
            "    return work(limit)\n"
        ),
        "pkg/svc.py": (
            '"""Service layer."""\n'
            "from pydantic import BaseModel\n\n\n"
            "class Item(BaseModel):\n"
            '    """An item."""\n'
            "    name: str\n\n\n"
            "def work(n):\n"
            "    return [Item(name=str(i)) for i in range(n)]\n"
        ),
        "tests/test_svc.py": (
            "from pkg.svc import work\n\n\n"
            "def test_work():\n"
            "    assert work(0) == []\n"
        ),
        "README.md": "# Demo\n\n## Overview\nA demo.\n",
        "pyproject.toml": (
            "[project]\nname = \"demo\"\nversion = \"0.1.0\"\n"
            "dependencies = [\"fastapi\", \"pydantic\"]\n"
        ),
    }
    for rel, content in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)


def _run(repo: str, out: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wiki_generator", "decompose",
         "--repo", repo, "--out", out],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


class UnitTests(unittest.TestCase):
    def test_module_dotted(self):
        self.assertEqual(ids.module_dotted("app/api/users.py"), "app.api.users")
        self.assertEqual(ids.module_dotted("app/api/__init__.py"), "app.api")
        self.assertEqual(ids.module_dotted("src/app/main.py"), "app.main")

    def test_symbol_id(self):
        self.assertEqual(
            ids.symbol_id("app.api.users", [("list_users", "function")]),
            "python app.api.users/list_users().")
        self.assertEqual(
            ids.symbol_id("app.db", [("User", "class"), ("save", "method")]),
            "python app.db/User#save().")

    def test_classify(self):
        self.assertEqual(config.classify("app/main.py", ".py", 10)["category"], "source")
        self.assertEqual(config.classify("tests/test_x.py", ".py", 10)["category"], "test")
        self.assertEqual(config.classify("docs/guide.md", ".md", 10)["category"], "docs")
        self.assertEqual(config.classify("Dockerfile", "", 10)["category"], "deployment")
        self.assertTrue(config.classify("uv.lock", ".lock", 10)["is_generated"])

    def test_chunker_window_no_gap(self):
        rec = {"path": "x.py", "language": "python", "category": "source",
               "name": "x.py", "ext": ".py"}
        text = "\n".join(f"line{i}" for i in range(1, 501))
        chunks = chunker.chunk_window(rec, text)
        self.assertGreater(len(chunks), 1)
        # windows must cover every line with no gap
        covered = set()
        for c in chunks:
            for ln in range(c["range"]["start_line"], c["range"]["end_line"] + 1):
                covered.add(ln)
        self.assertEqual(covered, set(range(1, 501)))


class RegressionTests(unittest.TestCase):
    """Covers the specific defects found by the adversarial review."""

    def test_src_layout_import_resolution(self):
        m = symmod._module_to_path({"src/app/db.py", "src/app/main.py"})
        self.assertEqual(m.get("app.db"), "src/app/db.py")
        tgt = symmod._resolve_import_target(
            {"kind": "from", "module": "app.db", "level": 0,
             "names": [{"name": "User", "asname": None}]},
            "src/app/main.py", m)
        self.assertEqual(tgt, "src/app/db.py")

    def test_relative_import_in_package_init(self):
        m = symmod._module_to_path({"app/api/__init__.py", "app/api/users.py"})
        # `from . import users` inside app/api/__init__.py -> app/api/users.py
        tgt = symmod._resolve_import_target(
            {"kind": "from", "module": None, "level": 1,
             "names": [{"name": "users", "asname": None}]},
            "app/api/__init__.py", m)
        self.assertEqual(tgt, "app/api/users.py")

    def test_django_routes_detected(self):
        src = (
            "from django.urls import path, re_path\n"
            "from . import views\n"
            "urlpatterns = [\n"
            '    path("users/", views.user_list),\n'
            '    re_path(r"^articles/$", views.articles),\n'
            "]\n"
        )
        p = symmod._ModuleParser(src, "app/urls.py").parse()
        routes = {r["path"] for r in p.routes}
        self.assertIn("/users/", routes)
        self.assertTrue(any(r["framework"] == "django" for r in p.routes))

    def test_router_prefix_applied(self):
        src = (
            "from fastapi import APIRouter\n"
            'router = APIRouter(prefix="/api/v1")\n\n'
            '@router.get("/users")\n'
            "def list_users():\n"
            "    return []\n"
        )
        p = symmod._ModuleParser(src, "app/r.py").parse()
        self.assertTrue(any(r["path"] == "/api/v1/users" for r in p.routes),
                        [r["path"] for r in p.routes])

    def test_nested_call_not_attributed_to_encloser(self):
        src = (
            "def outer():\n"
            "    def inner():\n"
            "        helper()\n"
            "    inner()\n"
            "def helper():\n"
            "    pass\n"
        )
        p = symmod._ModuleParser(src, "m.py").parse()
        outer_id = "python m/outer()."
        inner_id = "python m/outer().inner()."
        # outer calls inner; inner calls helper; outer must NOT call helper.
        outer_calls = {(c["name"]) for c in p.calls if c["caller_symbol_id"] == outer_id}
        inner_calls = {(c["name"]) for c in p.calls if c["caller_symbol_id"] == inner_id}
        self.assertIn("inner", outer_calls)
        self.assertNotIn("helper", outer_calls)
        self.assertIn("helper", inner_calls)


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p1test_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.out = os.path.join(cls.tmp, "out")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        cls.proc = _run(cls.repo, cls.out)

    def test_exit_ok(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_required_artifacts_exist(self):
        required = [
            "ARTIFACT_GUIDE.md", "run-metadata.json",
            "inventory/files.jsonl", "inventory/git-tracked-files.txt",
            "inventory/source-coverage.json",
            "symbols/symbols.jsonl", "symbols/imports.jsonl",
            "symbols/occurrences.jsonl", "symbols/tags", "symbols/tags.jsonl",
            "rag/spans.jsonl", "rag/chunks.jsonl", "rag/bm25.sqlite",
            "rag/rg-results.jsonl", "rag/vector-metadata.json",
            "static/nodes.jsonl", "static/edges.jsonl",
            "queries/results/rg.jsonl", "queries/results/semgrep.json",
            "queries/results/semgrep.sarif", "queries/results/ast-grep.json",
            "contracts/openapi.json", "contracts/contract-sources.md",
            "tests/pytest-collect.txt", "tests/test-files.jsonl",
            "derived/repo-summary.md", "derived/artifact-index.md",
        ]
        for rel in required:
            self.assertTrue(os.path.exists(os.path.join(self.out, rel)),
                            f"missing artifact: {rel}")

    def test_all_json_valid(self):
        import glob
        for p in glob.glob(self.out + "/**/*.json", recursive=True):
            with open(p) as f:
                json.load(f)
        for p in glob.glob(self.out + "/**/*.jsonl", recursive=True):
            with open(p) as f:
                for ln in f:
                    if ln.strip():
                        json.loads(ln)

    def test_symbol_ids_and_routes(self):
        syms = _read_jsonl(os.path.join(self.out, "symbols", "symbols.jsonl"))
        ids_set = {s["symbol_id"] for s in syms}
        self.assertIn("python pkg.api.routes/list_items().", ids_set)
        self.assertIn("python pkg.svc/Item#", ids_set)
        self.assertIn("python pkg.svc/work().", ids_set)

    def test_chunk_span_links(self):
        spans = _read_jsonl(os.path.join(self.out, "rag", "spans.jsonl"))
        chunks = _read_jsonl(os.path.join(self.out, "rag", "chunks.jsonl"))
        span_ids = {s["span_id"] for s in spans}
        for c in chunks:
            for sid in c["span_ids"]:
                self.assertIn(sid, span_ids, f"chunk {c['chunk_id']} -> missing span {sid}")
        # every Python symbol's span_id should exist among spans
        syms = _read_jsonl(os.path.join(self.out, "symbols", "symbols.jsonl"))
        for s in syms:
            self.assertIn(s["span_id"], span_ids,
                          f"symbol {s['symbol_id']} span {s['span_id']} not in spans")

    def test_symbol_nodes_present(self):
        syms = _read_jsonl(os.path.join(self.out, "symbols", "symbols.jsonl"))
        nodes = _read_jsonl(os.path.join(self.out, "static", "nodes.jsonl"))
        node_ids = {n["node_id"] for n in nodes}
        for s in syms:
            self.assertIn("sym:" + s["symbol_id"], node_ids)

    def test_internal_import_resolved(self):
        imps = _read_jsonl(os.path.join(self.out, "symbols", "imports.jsonl"))
        internal = [i for i in imps if i["is_internal"]]
        self.assertTrue(any(i["resolved_path"] == "pkg/svc.py" for i in internal))

    def test_openapi_has_route(self):
        with open(os.path.join(self.out, "contracts", "openapi.json")) as f:
            spec = json.load(f)
        self.assertIn("/items", spec.get("paths", {}))

    def test_module_symbol_and_parent_links_resolve(self):
        syms = _read_jsonl(os.path.join(self.out, "symbols", "symbols.jsonl"))
        sym_ids = {s["symbol_id"] for s in syms}
        # module symbols are materialized
        self.assertTrue(any(s["kind"] == "module" for s in syms))
        # every non-null parent_symbol_id resolves within symbols.jsonl
        for s in syms:
            if s["parent_symbol_id"] is not None:
                self.assertIn(s["parent_symbol_id"], sym_ids,
                              f"dangling parent: {s['symbol_id']} -> {s['parent_symbol_id']}")
        # every span.symbol_id (incl module_header) resolves to a symbol
        spans = _read_jsonl(os.path.join(self.out, "rag", "spans.jsonl"))
        for sp in spans:
            if sp.get("symbol_id") is not None:
                self.assertIn(sp["symbol_id"], sym_ids,
                              f"span {sp['span_id']} -> missing symbol {sp['symbol_id']}")

    def test_module_nodes_match_module_symbols(self):
        # Every static Module node must be backed by a kind=module symbol row,
        # and vice-versa (no asymmetry for empty/whitespace .py files).
        syms = _read_jsonl(os.path.join(self.out, "symbols", "symbols.jsonl"))
        nodes = _read_jsonl(os.path.join(self.out, "static", "nodes.jsonl"))
        module_sym_nodes = {"sym:" + s["symbol_id"] for s in syms if s["kind"] == "module"}
        module_nodes = {n["node_id"] for n in nodes if n["type"] == "Module"}
        self.assertEqual(module_nodes, module_sym_nodes)

    def test_empty_python_file_consistency(self):
        # An empty __init__.py must not produce a Module node or module symbol.
        tmp = tempfile.mkdtemp(prefix="p1empty_")
        repo = os.path.join(tmp, "r")
        out = os.path.join(tmp, "o")
        os.makedirs(os.path.join(repo, "pkg"))
        open(os.path.join(repo, "pkg", "__init__.py"), "w").close()  # empty
        with open(os.path.join(repo, "pkg", "m.py"), "w") as f:
            f.write("def go():\n    return 1\n")
        p = _run(repo, out)
        self.assertEqual(p.returncode, 0, p.stderr)
        syms = _read_jsonl(os.path.join(out, "symbols", "symbols.jsonl"))
        mod_paths = {s["path"] for s in syms if s["kind"] == "module"}
        self.assertIn("pkg/m.py", mod_paths)
        self.assertNotIn("pkg/__init__.py", mod_paths)
        nodes = _read_jsonl(os.path.join(out, "static", "nodes.jsonl"))
        mod_node_paths = {n.get("path") for n in nodes if n["type"] == "Module"}
        self.assertNotIn("pkg/__init__.py", mod_node_paths)

    def test_determinism_data_artifacts(self):
        out2 = os.path.join(self.tmp, "out2")
        p2 = _run(self.repo, out2)
        self.assertEqual(p2.returncode, 0, p2.stderr)
        for rel in ["inventory/files.jsonl", "symbols/symbols.jsonl",
                    "rag/spans.jsonl", "rag/chunks.jsonl",
                    "static/nodes.jsonl", "static/edges.jsonl",
                    "queries/results/rg.jsonl", "symbols/occurrences.jsonl"]:
            with open(os.path.join(self.out, rel)) as f1, \
                    open(os.path.join(out2, rel)) as f2:
                self.assertEqual(f1.read(), f2.read(), f"nondeterministic: {rel}")


def _run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wiki_generator", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


class RankingUnitTests(unittest.TestCase):
    def test_top_is_deterministic_and_tie_broken(self):
        from collections import Counter
        from wiki_generator.libs.digest import ranking as R
        c = Counter({"b": 2, "a": 2, "c": 5})
        self.assertEqual(R.top(c, 3), [("c", 5), ("a", 2), ("b", 2)])

    def test_md_table_escapes_pipes(self):
        from wiki_generator.libs.digest import ranking as R
        out = R.md_table(["h"], [["a|b"]])
        self.assertIn("a\\|b", "\n".join(out))

    def test_symbol_classifiers(self):
        from wiki_generator.libs.digest import ranking as R
        self.assertTrue(R.is_route({"decorators": ["router.get"]}))
        self.assertTrue(R.is_worker({"decorators": ["shared_task"]}))
        self.assertTrue(R.is_cli({"decorators": ["click.command"]}))
        self.assertTrue(R.is_model({"kind": "class", "bases": ["BaseModel"]}))
        self.assertFalse(R.is_model({"kind": "function", "bases": ["BaseModel"]}))


class DigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p1digest_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.out = os.path.join(cls.tmp, "out")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        cls.dec = _run(cls.repo, cls.out)
        cls.con = _run_cmd("condense", "--in", cls.out)
        cls.dig = _run_cmd("digest", "--in", cls.out)

    CONDENSATES = ["planning-symbols.md", "planning-graph.md",
                   "planning-runtime-surfaces.md", "planning-tests.md",
                   "planning-gaps.md"]

    def test_commands_exit_ok(self):
        self.assertEqual(self.dec.returncode, 0, self.dec.stderr)
        self.assertEqual(self.con.returncode, 0, self.con.stderr)
        self.assertEqual(self.dig.returncode, 0, self.dig.stderr)

    def test_condensates_written_and_nonempty(self):
        for name in self.CONDENSATES + ["planning-digest.md"]:
            p = os.path.join(self.out, "derived", name)
            self.assertTrue(os.path.exists(p), f"missing {name}")
            self.assertGreater(os.path.getsize(p), 0, f"empty {name}")

    def test_upload_package_assembled(self):
        pkg = os.path.join(self.out, "planner-digest")
        for name in (["README_FOR_PLANNER.md", "upload-list.md",
                      "planning-digest.md"] + self.CONDENSATES):
            self.assertTrue(os.path.exists(os.path.join(pkg, name)),
                            f"missing package file {name}")

    def test_single_file_bundle_present_and_complete(self):
        # The one-file upload bundle must exist and wrap each included file in the
        # spec's BEGIN/END boundary markers, in deterministic order.
        pkg = os.path.join(self.out, "planner-digest")
        bundle = os.path.join(pkg, "planner-upload-bundle.md")
        self.assertTrue(os.path.exists(bundle), "missing planner-upload-bundle.md")
        with open(bundle, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("<!-- BEGIN INCLUDED FILE: planner-digest/README_FOR_PLANNER.md -->",
                      text)
        labels = ["planner-digest/README_FOR_PLANNER.md",
                  "derived/planning-digest.md", "derived/planning-symbols.md",
                  "derived/planning-graph.md", "derived/planning-runtime-surfaces.md",
                  "derived/planning-tests.md", "derived/planning-gaps.md"]
        positions = []
        for label in labels:
            begin = f"<!-- BEGIN INCLUDED FILE: {label} -->"
            end = f"<!-- END INCLUDED FILE: {label} -->"
            self.assertIn(begin, text, f"bundle missing BEGIN for {label}")
            self.assertIn(end, text, f"bundle missing END for {label}")
            positions.append(text.index(begin))
        self.assertEqual(positions, sorted(positions), "included files out of order")

    def test_no_raw_artifacts_in_package(self):
        # The giant backend artifacts must never be copied into the upload set.
        pkg = os.path.join(self.out, "planner-digest")
        present = set(os.listdir(pkg))
        for forbidden in ("symbols.jsonl", "nodes.jsonl", "edges.jsonl",
                          "chunks.jsonl", "spans.jsonl", "bm25.sqlite"):
            self.assertNotIn(forbidden, present)

    def _read(self, *parts: str) -> str:
        with open(os.path.join(self.out, *parts), encoding="utf-8") as f:
            return f.read()

    def test_digest_brief_is_deterministic(self):
        # The data-derived brief must be byte-identical across runs (no dates).
        first = self._read("derived", "planning-digest.md")
        _run_cmd("digest", "--in", self.out)
        second = self._read("derived", "planning-digest.md")
        self.assertEqual(first, second)
        for name in self.CONDENSATES:
            self.assertTrue(self._read("derived", name).strip(), name)

    def test_upload_within_budget(self):
        self.assertIn("within budget", self.dig.stderr)

    def test_graph_labels_disambiguate_same_file(self):
        # Two symbols in one file must not collapse to one ambiguous label.
        from wiki_generator.libs.digest import planning_graph as G
        nodes = {
            "sym:a": {"node_id": "sym:a", "type": "Function", "name": "f",
                      "path": "x.py"},
            "sym:b": {"node_id": "sym:b", "type": "Function", "name": "g",
                      "path": "x.py"},
        }
        self.assertNotEqual(G._node_label(nodes, "sym:a"),
                            G._node_label(nodes, "sym:b"))

    # --- Step 4 bundle -------------------------------------------------------
    def test_bundle_command_standalone(self):
        out2 = os.path.join(self.tmp, "bundle_pkg")
        p = _run_cmd("bundle", "--in", self.out, "--out", out2)
        self.assertEqual(p.returncode, 0, p.stderr)
        for name in ("README_FOR_PLANNER.md", "upload-list.md",
                     "planner-upload-bundle.md"):
            self.assertTrue(os.path.exists(os.path.join(out2, name)), name)

    def test_bundle_budget_trim_keeps_required(self):
        from wiki_generator.libs.commands import bundle as bcmd
        full = bcmd.assemble_package(self.out, os.path.join(self.tmp, "b_full"), 250_000)
        req, total = full["required_tokens"], full["total_tokens"]
        self.assertFalse(full["failed"])
        self.assertTrue(full["within_budget"])
        if total > req:  # only meaningful when there are trimmable extras
            budget = req + (total - req) // 2
            trimmed = bcmd.assemble_package(self.out, os.path.join(self.tmp, "b_trim"), budget)
            self.assertTrue(trimmed["trimmed"], "expected some files trimmed")
            self.assertTrue(trimmed["within_budget"])
            self.assertFalse(trimmed["failed"])
            # the six condensates + README are never trimmed
            self.assertIn("derived/planning-digest.md", trimmed["included"])
            self.assertIn("planner-digest/README_FOR_PLANNER.md", trimmed["included"])

    def test_bundle_fail_loud_when_required_over_budget(self):
        from wiki_generator.libs.commands import bundle as bcmd
        rep = bcmd.assemble_package(self.out, os.path.join(self.tmp, "b_fail"), 1)
        self.assertTrue(rep["failed"])
        self.assertFalse(rep["within_budget"])
        with open(os.path.join(rep["out_dir"], "upload-list.md"), encoding="utf-8") as f:
            self.assertIn("FAIL", f.read())
        # the command surfaces the failure as a non-zero exit
        p = _run_cmd("bundle", "--in", self.out,
                     "--out", os.path.join(self.tmp, "b_fail2"), "--budget-tokens", "1")
        self.assertEqual(p.returncode, 1, p.stderr)

    def test_bundle_excludes_raw_indexes(self):
        out2 = os.path.join(self.tmp, "b_raw")
        _run_cmd("bundle", "--in", self.out, "--out", out2)
        with open(os.path.join(out2, "planner-upload-bundle.md"), encoding="utf-8") as f:
            text = f.read()
        for raw in ("symbols/symbols.jsonl", "static/edges.jsonl", "rag/chunks.jsonl"):
            self.assertNotIn(f"BEGIN INCLUDED FILE: {raw}", text)


class NormalizePlanUnitTests(unittest.TestCase):
    def test_parse_minimal(self):
        from wiki_generator.libs.plan_normalization import parse
        text = (
            "prose\n\n"
            "```text\nplans/document-plan.json\n```\n\n"
            '```json\n{"repo":"x","sections":[{"id":"a","title":"A"}]}\n```\n\n'
            "```text\nplans/section-plans.jsonl\n```\n\n"
            '```jsonl\n{"section_id":"a","title":"A"}\n```\n'
        )
        rp = parse.parse(text)
        self.assertEqual(rp.document_plan["repo"], "x")
        self.assertEqual(len(rp.section_plans), 1)
        self.assertEqual(rp.section_plans[0]["section_id"], "a")

    def test_parse_ambiguous_document_plan_raises(self):
        from wiki_generator.libs.plan_normalization import parse
        text = ('```json\n{"sections":[]}\n```\n\n```json\n{"sections":[]}\n```\n')
        with self.assertRaises(parse.ParseError):
            parse.parse(text)

    def test_parse_missing_section_plans_raises(self):
        from wiki_generator.libs.plan_normalization import parse
        text = ('```text\nplans/document-plan.json\n```\n'
                '```json\n{"sections":[{"id":"a","title":"A"}]}\n```\n')
        with self.assertRaises(parse.ParseError):
            parse.parse(text)

    def test_parse_format4_markdown_headings(self):
        # Accepted raw format #4: DocumentPlan/SectionPlans markdown headings with
        # raw (unfenced) JSON beneath them.
        from wiki_generator.libs.plan_normalization import parse
        text = (
            "# Plan\n\n"
            "## DocumentPlan\n\n"
            '{"repo":"x","sections":[{"id":"a","title":"A"}]}\n\n'
            "## SectionPlans\n\n"
            '{"section_id":"a","title":"A","goal":"g"}\n'
        )
        rp = parse.parse(text)
        self.assertEqual(rp.document_plan["repo"], "x")
        self.assertEqual(len(rp.section_plans), 1)
        self.assertEqual(rp.section_plans[0]["section_id"], "a")

    def test_parse_filename_in_fence_info_string(self):
        # Gemini sometimes writes the filename on the SAME fence line as the
        # language, e.g. "```text plans/document-plan.json" with the content in
        # that one fence. The label must be read from the info string.
        from wiki_generator.libs.plan_normalization import parse
        text = (
            "intro\n\n"
            "```text plans/document-plan.json\n"
            '{"repo":"x","sections":[{"id":"a","title":"A"}]}\n'
            "```\n\n"
            "```text plans/section-plans.jsonl\n"
            '{"section_id":"a","title":"A","goal":"g"}\n'
            "```\n"
        )
        rp = parse.parse(text)
        self.assertEqual(rp.document_plan["repo"], "x")
        self.assertEqual(len(rp.section_plans), 1)
        self.assertEqual(rp.section_plans[0]["section_id"], "a")

    def test_digest_artifact_requires_on_disk(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._artifact_basenames = {"openapi.json"}
        # basename matches the allowlist but no such file exists -> unresolved
        self.assertEqual(lk.resolve_file("some/random/openapi.json").resolution,
                         "no_match")

    def test_title_fallback_no_double_consume(self):
        from wiki_generator.libs.plan_normalization import normalize as N
        from wiki_generator.libs.plan_normalization.parse import RawPlan
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        doc = {"repo": "x", "sections": [{"id": "a", "title": "Alpha"},
                                         {"title": "Shared Title"}]}
        sp = {"section_id": "a", "title": "Shared Title", "goal": "PLAN-1 goal",
              "evidence_needs": {}}
        res = N.normalize(RawPlan(document_plan=doc, section_plans=[sp]),
                          lk, "raw.md", "gemini")
        by = {s["section_id"]: s for s in res.sections}
        self.assertEqual(by["a"]["goal"], "PLAN-1 goal")
        self.assertEqual(by["shared-title"]["goal"], "")
        self.assertTrue(any("no SectionPlan" in w
                            for w in by["shared-title"]["normalization_warnings"]))

    def test_slugify_and_unique_ids(self):
        from wiki_generator.libs.plan_normalization import normalize as N
        self.assertEqual(N._slugify("RAG Pipeline & Tasks"), "rag-pipeline-tasks")
        used = set()
        self.assertEqual(N._section_id("overview", "Overview", used), "overview")
        self.assertEqual(N._section_id(None, "Overview", used), "overview-2")
        self.assertEqual(N._section_id("API Routes", "API Routes", used), "api-routes")

    def test_symbol_resolution_logic(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._by_id = {"sid1": {}, "sid2": {}}
        lk._sym_alias = {"dup": {"sid1", "sid2"}, "uniq": {"sid1"}}
        self.assertEqual(lk.resolve_symbol("sid1").resolution, "exact")
        r = lk.resolve_symbol("uniq")
        self.assertEqual((r.resolution, r.symbol_id), ("unique_alias", "sid1"))
        amb = lk.resolve_symbol("dup")
        self.assertEqual(amb.resolution, "ambiguous")
        self.assertEqual(amb.candidates, ["sid1", "sid2"])
        self.assertEqual(lk.resolve_symbol("missing").resolution, "no_match")

    def test_file_resolution_and_anchor_confidence(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk.files = {"a/b/c.py", "d/c.py", "x/y.py"}
        lk.line_counts = {"x/y.py": 10}
        self.assertEqual(lk.resolve_file("x/y.py").resolution, "file_exists")
        self.assertEqual(lk.resolve_file("y.py").resolution, "unique_suffix")
        self.assertEqual(lk.resolve_file("c.py").resolution, "ambiguous")
        self.assertEqual(lk.resolve_file("nope.py").resolution, "no_match")
        self.assertEqual(lk.resolve_file("x/y.py:3-7").anchor_confidence, "exact_range")
        self.assertEqual(lk.resolve_file("x/y.py:5").anchor_confidence, "line_only")
        self.assertEqual(lk.resolve_file("x/y.py:50").anchor_confidence, "file_only")
        self.assertEqual(lk.resolve_file("x/y.py:Heading").anchor_confidence, "file_only")

    def test_norm(self):
        from wiki_generator.libs.plan_normalization.lookups import _norm
        self.assertEqual(_norm("Auth / security"), "auth_security")
        self.assertEqual(_norm("Tasks / workers"), "tasks_workers")
        self.assertEqual(_norm("Config keys (code)"), "config_keys_code")


class NormalizePlanE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p1norm_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.out = os.path.join(cls.tmp, "out")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        cls.dec = _run(cls.repo, cls.out)
        # Synthetic planning response referencing the demo repo's real symbols.
        doc = {"repo": "demo", "one_line_purpose": "Demo app.",
               "audience": ["Devs"],
               "sections": [
                   {"id": "overview", "title": "Overview", "order": 1,
                    "parent": None, "purpose": "Intro.", "priority": "high"},
                   {"id": "api routes", "title": "API Routes", "order": 2,
                    "parent": None, "purpose": "Routes.", "priority": "high"}]}
        sp1 = {"section_id": "overview", "title": "Overview", "goal": "Intro",
               "coverage_requirements": ["What"], "key_questions": ["What?"],
               "evidence_needs": {
                   "symbol_ids": ["pkg.svc.work", "python pkg.svc/Item#"],
                   "file_anchors": ["pkg/svc.py", "README.md:Overview"],
                   "query_packs": ["Web routes"],
                   "graph_nodes": ["demo [Repository]"], "contracts": []},
               "depends_on": [], "verification_needs": [], "estimated_size": "S"}
        sp2 = {"section_id": "api routes", "title": "API Routes", "goal": "Routes",
               "coverage_requirements": ["Endpoints"], "key_questions": ["?"],
               "evidence_needs": {
                   "symbol_ids": ["pkg.api.routes.list_items", "does.not.exist"],
                   "file_anchors": ["routes.py"],
                   "query_packs": ["Auth / security", "totally bogus pack"],
                   "graph_nodes": [], "contracts": ["GET /items", "POST /nope"]},
               "depends_on": ["overview"], "estimated_size": "M"}
        raw = ("Here are the artifacts:\n\n"
               "```text\nplans/document-plan.json\n```\n\n"
               "```json\n" + json.dumps(doc, indent=2) + "\n```\n\n"
               "```text\nplans/section-plans.jsonl\n```\n\n"
               "```jsonl\n" + json.dumps(sp1) + "\n" + json.dumps(sp2) + "\n```\n")
        cls.raw_path = os.path.join(cls.out, "plans", "phase2-gemini-response.md")
        os.makedirs(os.path.dirname(cls.raw_path), exist_ok=True)
        with open(cls.raw_path, "w", encoding="utf-8") as f:
            f.write(raw)
        cls.plans = os.path.join(cls.tmp, "plans_out")
        cls.norm = _run_cmd("normalize-plan", "--bundle", cls.out,
                            "--raw-response", cls.raw_path, "--out", cls.plans)

    def _sections(self):
        with open(os.path.join(self.plans, "section-plans.jsonl")) as f:
            return {json.loads(ln)["section_id"]: json.loads(ln) for ln in f if ln.strip()}

    def test_exit_ok_and_outputs(self):
        self.assertEqual(self.dec.returncode, 0, self.dec.stderr)
        self.assertEqual(self.norm.returncode, 0, self.norm.stderr)
        for name in ("document-plan.json", "document-plan.md", "section-plans.jsonl",
                     "normalization-report.md", "unresolved-references.jsonl"):
            self.assertTrue(os.path.exists(os.path.join(self.plans, name)), name)

    def test_document_plan_valid(self):
        with open(os.path.join(self.plans, "document-plan.json")) as f:
            dp = json.load(f)
        self.assertEqual(dp["schema_version"], "phase2-plan-v1")
        self.assertEqual(dp["section_order"], ["overview", "api-routes"])
        self.assertEqual(dp["audience"], "Devs")

    def test_section_plans_jsonl_valid(self):
        secs = self._sections()
        self.assertEqual(set(secs), {"overview", "api-routes"})

    def test_query_pack_and_symbol_resolution(self):
        secs = self._sections()
        ov = secs["overview"]
        self.assertEqual(ov["retrieval_needs"]["query_packs"], ["web_routes"])
        syms = {s["input"]: s for s in ov["retrieval_needs"]["symbols"]}
        self.assertEqual(syms["pkg.svc.work"]["resolution"], "unique_alias")
        self.assertEqual(syms["pkg.svc.work"]["symbol_id"], "python pkg.svc/work().")
        self.assertEqual(syms["python pkg.svc/Item#"]["resolution"], "exact")
        files = {f["input"]: f for f in ov["retrieval_needs"]["files"]}
        self.assertEqual(files["pkg/svc.py"]["resolution"], "file_exists")
        self.assertEqual(files["README.md:Overview"]["anchor_confidence"], "file_only")

    def test_unresolved_and_contracts(self):
        secs = self._sections()
        api = secs["api-routes"]
        self.assertEqual(api["retrieval_needs"]["query_packs"], ["auth_security"])
        syms = {s["input"]: s for s in api["retrieval_needs"]["symbols"]}
        self.assertEqual(syms["does.not.exist"]["resolution"], "no_match")
        contracts = {c["input"]: c for c in api["retrieval_needs"]["contracts"]}
        self.assertEqual(contracts["GET /items"]["resolution"], "exact")
        with open(os.path.join(self.plans, "unresolved-references.jsonl")) as f:
            unresolved = [json.loads(ln) for ln in f if ln.strip()]
        types = {u["type"] for u in unresolved}
        self.assertEqual(types, {"symbol", "query_pack", "contract"})

    def test_query_pack_aliases_map_to_canonical(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups.load(self.out)
        cases = {
            "Web routes": "web_routes", "Auth / security": "auth_security",
            "Tasks / workers": "task_workers", "CLI commands": "cli_commands",
            "LLM integrations": "llm_integrations",
            "Plugins / registries / factories": "plugin_registries",
            "Datastore / storage / cache": "datastore",
            "Config keys (code)": "config_keys",
            "Environment variables": "env_vars",
        }
        for disp, key in cases.items():
            self.assertEqual(lk.resolve_query_pack(disp), key, disp)
        self.assertIsNone(lk.resolve_query_pack("totally bogus pack"))

    def test_strict_mode_fails_on_unresolved(self):
        p = _run_cmd("normalize-plan", "--bundle", self.out,
                     "--raw-response", self.raw_path,
                     "--out", os.path.join(self.tmp, "plans_strict"), "--strict")
        self.assertEqual(p.returncode, 1, p.stderr)

    def test_determinism(self):
        a = os.path.join(self.tmp, "det_a")
        b = os.path.join(self.tmp, "det_b")
        _run_cmd("normalize-plan", "--bundle", self.out,
                 "--raw-response", self.raw_path, "--out", a)
        _run_cmd("normalize-plan", "--bundle", self.out,
                 "--raw-response", self.raw_path, "--out", b)
        for name in ("document-plan.json", "section-plans.jsonl",
                     "unresolved-references.jsonl"):
            with open(os.path.join(a, name)) as f1, open(os.path.join(b, name)) as f2:
                self.assertEqual(f1.read(), f2.read(), name)


class PlanCommandTests(unittest.TestCase):
    """Phase 2 Step 1 `plan` command — the config-check paths run without the
    google-genai SDK or any GCP credentials."""

    def test_build_user_content_orders_kickoff_then_bundle(self):
        from wiki_generator.libs.commands.plan import build_user_content
        out = build_user_content("KICK", "BUNDLE-TEXT")
        self.assertIn("KICK", out)
        self.assertIn("BUNDLE-TEXT", out)
        self.assertLess(out.index("KICK"), out.index("BUNDLE-TEXT"))

    def test_plan_missing_bundle_file_exits_2(self):
        tmp = tempfile.mkdtemp(prefix="p1plan_")
        p = _run_cmd("plan", "--bundle", tmp, "--project", "dummy")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("planner-upload-bundle.md", p.stderr)

    def test_plan_missing_project_exits_2(self):
        tmp = tempfile.mkdtemp(prefix="p1plan2_")
        pkg = os.path.join(tmp, "planner-digest")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "planner-upload-bundle.md"), "w") as f:
            f.write("# bundle\n")
        env = dict(os.environ)
        env.pop("GOOGLE_CLOUD_PROJECT", None)
        proc = subprocess.run(
            [sys.executable, "-m", "wiki_generator", "plan", "--bundle", tmp],
            cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("project", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
