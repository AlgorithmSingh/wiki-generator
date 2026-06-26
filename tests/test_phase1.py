"""End-to-end + unit tests for wiki_generator. Runnable with stdlib only:

    python -m unittest discover -s tests -v
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
# src layout: import the package from src/. After `pip install -e .` the editable
# install also satisfies this; adding src lets the suite run without a global
# install too (the package never sits at the repo root).
sys.path.insert(0, SRC)

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


def _subenv(**extra) -> dict:
    """Child-process env with src/ on PYTHONPATH so `-m wiki_generator` resolves
    (works with or without an editable install)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra)
    return env


def _run(repo: str, out: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "wiki_generator", "decompose",
         "--repo", repo, "--out", out],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=_subenv(),
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
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=_subenv(),
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

    CONDENSATES = ["planning-handles.md", "planning-symbols.md",
                   "planning-graph.md", "planning-runtime-surfaces.md",
                   "planning-tests.md", "planning-gaps.md"]

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
                  "derived/planning-handles.md", "derived/planning-digest.md",
                  "derived/planning-symbols.md", "derived/planning-graph.md",
                  "derived/planning-runtime-surfaces.md",
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


class PlanningHandlesTests(unittest.TestCase):
    """Phase 1 readiness: derived/planning-handles.md exact-handle catalog."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p1handles_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.out = os.path.join(cls.tmp, "out")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        cls.dec = _run(cls.repo, cls.out)
        cls.con = _run_cmd("condense", "--in", cls.out)
        cls.dig = _run_cmd("digest", "--in", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _handles(self, where: str) -> str:
        with open(os.path.join(self.out, where, "planning-handles.md"),
                  encoding="utf-8") as f:
            return f.read()

    def test_generated_in_derived_and_packaged(self):
        self.assertEqual(self.con.returncode, 0, self.con.stderr)
        self.assertEqual(self.dig.returncode, 0, self.dig.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(self.out, "derived", "planning-handles.md")))
        self.assertTrue(os.path.exists(
            os.path.join(self.out, "planner-digest", "planning-handles.md")))

    def test_exact_handles_present(self):
        text = self._handles("derived")
        self.assertIn("web_routes", text)                              # query pack
        self.assertIn("python pkg.api.routes/list_items().", text)      # route symbol
        self.assertIn("python pkg.svc/Item#", text)                     # model symbol
        self.assertIn("GET /items", text)                               # contract op
        self.assertIn("repo:repo", text)                                # repo node
        self.assertIn("dep:fastapi", text)                              # dep node
        self.assertIn("tests/test_svc.py", text)                        # test file
        self.assertIn("search_hints[]", text)
        self.assertIn("context_artifacts[]", text)

    def test_no_raw_artifact_bodies(self):
        # The catalog holds copyable handles, never raw JSONL rows from the indexes.
        text = self._handles("derived")
        for forbidden in ('"span_id"', '"sha256"', '"chunk_id"', '"start_line"'):
            self.assertNotIn(forbidden, text)

    def test_included_in_bundle_after_readme_before_summaries(self):
        with open(os.path.join(self.out, "planner-digest",
                               "planner-upload-bundle.md"), encoding="utf-8") as f:
            text = f.read()
        readme = text.index("BEGIN INCLUDED FILE: planner-digest/README_FOR_PLANNER.md")
        handles = text.index("BEGIN INCLUDED FILE: derived/planning-handles.md")
        digest = text.index("BEGIN INCLUDED FILE: derived/planning-digest.md")
        self.assertLess(readme, handles)   # right after the README
        self.assertLess(handles, digest)   # before the broad summaries

    def test_readme_documents_lane_discipline(self):
        with open(os.path.join(self.out, "planner-digest",
                               "README_FOR_PLANNER.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("search_hints[]", readme)
        self.assertIn("context_artifacts[]", readme)
        self.assertIn("not** a contract", readme)


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

    def test_graph_node_resolution_logic(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._node_ids = {"repo:demo", "dep:pytest", "file:a/b.py", "sym:python m/F#"}
        lk._node_alias = {"pytest|dependency": {"dep:pytest"}, "pytest": {"dep:pytest"},
                          "demo|repository": {"repo:demo"}, "demo": {"repo:demo"}}
        self.assertEqual(lk.resolve_graph_node("dep:pytest").resolution, "exact")
        self.assertEqual(lk.resolve_graph_node("repo:demo").node_id, "repo:demo")
        # bare handle gains its known prefix
        self.assertEqual(lk.resolve_graph_node("python m/F#").node_id, "sym:python m/F#")
        # a display label resolves to the exact node_id, never stays a label
        r = lk.resolve_graph_node("pytest [Dependency]")
        self.assertEqual((r.resolution, r.node_id), ("display_label", "dep:pytest"))
        # a label with no matching node does not guess
        self.assertEqual(lk.resolve_graph_node("ghost [Dependency]").resolution, "no_match")

    def test_context_artifact_detection(self):
        from wiki_generator.libs.plan_normalization.normalize import (
            _looks_like_context_artifact as L)
        self.assertEqual(L("derived/planning-digest.md"), "derived/planning-digest.md")
        self.assertEqual(L("planning-handles.md"), "planning-handles.md")
        self.assertEqual(L("planner-digest/README_FOR_PLANNER.md"),
                         "planner-digest/README_FOR_PLANNER.md")
        self.assertIsNone(L("pkg/svc.py"))
        self.assertIsNone(L("api/apps/base_app.py"))

    def test_resolve_needs_routes_unresolved_out_of_exact_lanes(self):
        from wiki_generator.libs.plan_normalization import normalize as N
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._by_id = {"python m/F#": {}}
        lk.files = {"pkg/svc.py"}
        lk.qpack_canonical = {"web_routes"}
        lk._openapi_paths = {"/items": {"GET"}}
        lk._node_ids = {"dep:fastapi"}
        lk._node_alias = {"fastapi|dependency": {"dep:fastapi"}}
        ev = {"symbols": ["bogus.sym", "python m/F#"],
              "files": ["derived/planning-graph.md", "pkg/svc.py"],
              "contracts": ["contracts/openapi.json", "GET /items"],
              "graph_nodes": ["fastapi [Dependency]", "ghost [Dependency]"],
              "query_packs": ["web_routes", "bogus pack"]}
        unresolved, warnings = [], []
        needs, _ = N._resolve_needs("s", ev, lk, unresolved, warnings)
        # exact lanes keep only resolvable handles
        self.assertEqual([s["symbol_id"] for s in needs["symbols"]], ["python m/F#"])
        self.assertEqual([f["path"] for f in needs["files"]], ["pkg/svc.py"])
        self.assertEqual([c["resolution"] for c in needs["contracts"]], ["exact"])
        self.assertEqual(needs["graph_nodes"], ["dep:fastapi"])
        self.assertEqual(needs["query_packs"], ["web_routes"])
        # digests -> context_artifacts; everything unresolvable -> search_hints
        self.assertEqual([c["path"] for c in needs["context_artifacts"]],
                         ["derived/planning-graph.md"])
        hint_texts = {h["text"] for h in needs["search_hints"]}
        self.assertIn("bogus.sym", hint_texts)
        self.assertIn("contracts/openapi.json", hint_texts)
        self.assertIn("ghost [Dependency]", hint_texts)
        self.assertIn("bogus pack", hint_texts)
        # expected_evidence_types derives only from what resolved
        self.assertEqual(N._expected_types(needs),
                         ["symbols", "files", "queries", "contracts", "graph"])
        # never a citeable digest in files[], never a label in graph_nodes[]
        self.assertNotIn("derived/planning-graph.md",
                         [f["input"] for f in needs["files"]])
        self.assertNotIn("fastapi [Dependency]", needs["graph_nodes"])

    def test_openapi_json_never_becomes_a_context_artifact(self):
        # Regression: contracts/openapi.json is the contract-evidence source; a
        # planner that mislabels it as context (or lists it in files[]) must NOT
        # turn it into a context_artifact, or Phase 3 would flag the contract
        # lane's legitimate citation of it (retriever_implementation_bug).
        from wiki_generator.libs.plan_normalization import normalize as N
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        ev = {"context_artifacts": ["contracts/openapi.json",
                                    "derived/planning-digest.md"],
              "files": ["contracts/openapi.json"]}
        needs, _ = N._resolve_needs("s", ev, lk, [], [])
        ca = [c["path"] for c in needs["context_artifacts"]]
        self.assertIn("derived/planning-digest.md", ca)        # genuine digest kept
        self.assertNotIn("contracts/openapi.json", ca)         # evidence artifact dropped
        self.assertEqual([f["input"] for f in needs["files"]], [])  # not a source file

    def test_resolve_test_splits_pytest_node_id(self):
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._test_files = {"test/playwright/conftest.py"}
        r = lk.resolve_test("test/playwright/conftest.py::pytest_sessionstart")
        self.assertEqual(r["resolution"], "test_file")
        self.assertEqual(r["path"], "test/playwright/conftest.py")
        self.assertEqual(r["function"], "pytest_sessionstart")

    def test_object_shaped_contract_and_test_resolve(self):
        from wiki_generator.libs.plan_normalization import normalize as N
        from wiki_generator.libs.plan_normalization.lookups import Lookups
        lk = Lookups("/nonexistent")
        lk._openapi_paths = {"/items": {"GET"}}
        lk._test_files = {"tests/test_svc.py"}
        # the spec's SectionPlan example uses object-shaped contracts/tests
        ev = {"contracts": [{"method": "GET", "path": "/items"}],
              "tests": [{"path": "tests/test_svc.py", "function": "test_work"}]}
        needs, _ = N._resolve_needs("s", ev, lk, [], [])
        self.assertEqual([c["resolution"] for c in needs["contracts"]], ["exact"])
        self.assertEqual([t["resolution"] for t in needs["tests"]], ["test_file"])
        self.assertEqual(needs["tests"][0].get("function"), "test_work")

    def test_expected_types_graph_from_symbol_or_file_seed(self):
        from wiki_generator.libs.plan_normalization.normalize import _expected_types
        # a resolvable symbol/file can seed the graph lane (spec rule 5)
        self.assertIn("graph", _expected_types(
            {"symbols": [{"symbol_id": "x"}], "files": [], "query_packs": [],
             "contracts": [], "tests": [], "graph_nodes": []}))
        # ... but a query-pack-only section does not claim graph
        self.assertNotIn("graph", _expected_types(
            {"symbols": [], "files": [], "query_packs": ["web_routes"],
             "contracts": [], "tests": [], "graph_nodes": []}))

    def _result(self, section, unresolved):
        from wiki_generator.libs.plan_normalization.normalize import Result
        return Result(document_plan={"repo": {"root": "/r"},
                                     "section_order": [section["section_id"]]},
                      sections=[section], unresolved=unresolved, warnings=[],
                      raw_document_plan={}, raw_section_plans=[])

    def test_readiness_passes_when_only_a_digest_was_relocated(self):
        from wiki_generator.libs.plan_normalization import writer
        sec = {"section_id": "s", "title": "S", "purpose": "p",
               "required_topics": [], "key_questions": [],
               "retrieval_needs": {
                   "query_packs": ["web_routes"], "symbols": [], "files": [],
                   "contracts": [], "tests": [], "graph_nodes": [],
                   "search_hints": [],
                   "context_artifacts": [{"path": "derived/planning-digest.md",
                                          "role": "planner_context",
                                          "citeable_as_evidence": False}]},
               "expected_evidence_types": ["queries"]}
        # the normalizer relocated the digest and logged a context_only entry
        res = self._result(sec, [{"section_id": "s", "type": "file",
                                  "input": "derived/planning-digest.md",
                                  "reason": "context_only", "candidates": []}])
        self.assertTrue(writer.readiness_pass(res))

    def test_readiness_fails_for_section_with_no_retrieval_signal(self):
        from wiki_generator.libs.plan_normalization import writer
        sec = {"section_id": "s", "title": "Only a title",
               "purpose": "a purpose", "required_topics": ["topic"],
               "key_questions": ["q"],
               "retrieval_needs": {"query_packs": [], "symbols": [], "files": [],
                                   "contracts": [], "tests": [], "graph_nodes": [],
                                   "search_hints": [], "context_artifacts": []},
               "expected_evidence_types": []}
        self.assertFalse(writer.readiness_pass(self._result(sec, [])))

    def test_context_docs_broad_vs_narrow_predicates(self):
        from wiki_generator.libs import context_docs as C
        # broad (normalizer, on planner file refs): basename + subtree
        self.assertTrue(C.looks_like_context_artifact("derived/planning-digest.md"))
        self.assertTrue(C.looks_like_context_artifact("repo-summary.md"))
        self.assertTrue(C.looks_like_context_artifact(
            "planner-digest/README_FOR_PLANNER.md"))
        self.assertIsNone(C.looks_like_context_artifact("pkg/svc.py"))
        # narrow (validator, on evidence source paths): only the bundle's own
        # generated namespaces, so a real repo file merely NAMED repo-summary.md
        # is not falsely flagged as a context citation
        self.assertTrue(C.is_generated_context_path("derived/planning-digest.md"))
        self.assertTrue(C.is_generated_context_path("planner-digest/upload-list.md"))
        self.assertFalse(C.is_generated_context_path("docs/repo-summary.md"))
        self.assertFalse(C.is_generated_context_path("pkg/svc.py"))


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
        # overview: a clean section (every handle resolves).
        sp1 = {"section_id": "overview", "title": "Overview", "goal": "Intro",
               "coverage_requirements": ["What"], "key_questions": ["What?"],
               "evidence_needs": {
                   "symbol_ids": ["pkg.svc.work", "python pkg.svc/Item#"],
                   "file_anchors": ["pkg/svc.py", "README.md:Overview"],
                   "query_packs": ["Web routes"],
                   "graph_nodes": ["repo [Repository]"], "contracts": []},
               "depends_on": [], "verification_needs": [], "estimated_size": "S"}
        # api-routes: the RAGFlow-style bad section — vague symbol, digest in
        # files[], display-label graph node, openapi.json-only contract, bogus
        # query pack. The normalizer must route every one of these out of its
        # exact lane (readiness FAIL), keeping only the resolvable handles.
        sp2 = {"section_id": "api routes", "title": "API Routes", "goal": "Routes",
               "coverage_requirements": ["Endpoints"], "key_questions": ["?"],
               "evidence_needs": {
                   "symbol_ids": ["pkg.api.routes.list_items", "retrieve: api.apps.*"],
                   "file_anchors": ["routes.py", "derived/planning-digest.md"],
                   "query_packs": ["Auth / security", "totally bogus pack"],
                   "graph_nodes": ["fastapi [Dependency]", "pytest [Dependency]"],
                   "contracts": ["GET /items", "contracts/openapi.json"]},
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
                     "normalization-report.md", "phase3-readiness-report.md",
                     "unresolved-references.jsonl"):
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

    def test_overview_graph_node_resolves(self):
        ov = self._sections()["overview"]
        self.assertEqual(ov["retrieval_needs"]["graph_nodes"], ["repo:repo"])

    def test_bad_inputs_routed_out_of_exact_lanes(self):
        api = self._sections()["api-routes"]
        nh = api["retrieval_needs"]
        # query packs: only the canonical key survives
        self.assertEqual(nh["query_packs"], ["auth_security"])
        # symbols: vague "retrieve: ..." is gone; the exact one stays
        sym_inputs = [s["input"] for s in nh["symbols"]]
        self.assertEqual(sym_inputs, ["pkg.api.routes.list_items"])
        # contracts: only the exact METHOD /path; openapi.json-only removed
        contracts = {c["input"]: c for c in nh["contracts"]}
        self.assertEqual(list(contracts), ["GET /items"])
        self.assertEqual(contracts["GET /items"]["resolution"], "exact")
        # graph_nodes: the resolvable display label became an exact node_id; the
        # unresolvable one was dropped
        self.assertEqual(nh["graph_nodes"], ["dep:fastapi"])
        # files: the digest doc is NOT an active file work item
        file_inputs = [f["input"] for f in nh["files"]]
        self.assertNotIn("derived/planning-digest.md", file_inputs)
        # context_artifacts: the digest doc, marked non-citeable
        ca_paths = [c["path"] for c in nh["context_artifacts"]]
        self.assertIn("derived/planning-digest.md", ca_paths)
        self.assertTrue(all(c["citeable_as_evidence"] is False
                            for c in nh["context_artifacts"]))
        # search_hints: every rerouted item is recall text now
        hints = {h["text"] for h in nh["search_hints"]}
        for moved in ("retrieve: api.apps.*", "totally bogus pack",
                      "pytest [Dependency]", "contracts/openapi.json"):
            self.assertIn(moved, hints)

    def test_expected_evidence_types_from_resolvable_only(self):
        api = self._sections()["api-routes"]
        # symbols(list_items), files(routes.py), queries(auth_security),
        # contracts(GET /items), graph(dep:fastapi) — NOT tests (none resolved).
        self.assertEqual(api["expected_evidence_types"],
                         ["symbols", "files", "queries", "contracts", "graph"])

    def test_unresolved_log_covers_all_lanes(self):
        with open(os.path.join(self.plans, "unresolved-references.jsonl")) as f:
            unresolved = [json.loads(ln) for ln in f if ln.strip()]
        types = {u["type"] for u in unresolved}
        self.assertEqual(types, {"symbol", "query_pack", "contract", "graph", "file"})

    def test_negative_acceptance_no_bad_items_in_exact_lanes(self):
        # The RAGFlow negative-acceptance checks (spec): none of these may appear
        # in any exact lane of any section.
        for sec in self._sections().values():
            nh = sec["retrieval_needs"]
            for s in nh["symbols"]:
                self.assertNotIn("retrieve:", str(s["input"]))
            self.assertNotIn("contracts/openapi.json",
                             [c["input"] for c in nh["contracts"]])
            self.assertNotIn("pytest [Dependency]", nh["graph_nodes"])
            for f in nh["files"]:
                self.assertFalse(str(f.get("path") or "").startswith("derived/planning-"))
                self.assertNotIn("derived/planning-digest.md", str(f["input"]))

    def test_readiness_report_written_and_fails_for_bad_plan(self):
        path = os.path.join(self.plans, "phase3-readiness-report.md")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            report = f.read()
        self.assertIn("Status: FAIL", report)
        self.assertIn("# Phase 3 Readiness Report", report)
        # the failing section is named with a suggested fix
        self.assertIn("api-routes", report)

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
                     "phase3-readiness-report.md", "unresolved-references.jsonl"):
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
        env = _subenv()
        env.pop("GOOGLE_CLOUD_PROJECT", None)
        proc = subprocess.run(
            [sys.executable, "-m", "wiki_generator", "plan", "--bundle", tmp],
            cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("project", proc.stderr.lower())


class _FakeVectorBackend:
    """In-test vector backend so the hybrid/skip/fail paths run without faiss.

    ``build`` writes the vector count to ``index_path`` and ``count`` reads it
    back, so the count-verification logic is exercised end to end. ``count_delta``
    simulates a FAISS/metadata divergence.
    """

    def __init__(self, available=True, reason=None, count_delta=0):
        self._available = available
        self._reason = reason
        self._count_delta = count_delta

    def probe(self):
        from wiki_generator.libs.retrieval.vectors import ProbeResult
        return ProbeResult(self._available, self._reason)

    def build(self, texts, index_path, *, model, batch_size, max_seq_length):
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(str(len(texts)))
        return len(texts)

    def count(self, index_path):
        with open(index_path, encoding="utf-8") as f:
            return int(f.read()) + self._count_delta


class BuildRetrievalUnitTests(unittest.TestCase):
    def test_build_options_fail_without_vectors_implies_on(self):
        from wiki_generator.libs.commands import build_retrieval as brcmd
        import argparse
        ns = argparse.Namespace(
            in_dir="/x", bm25="on", vectors="auto", embedding_model=None,
            batch_size=None, rebuild=False, smoke_query=None,
            fail_without_vectors=True)
        opts = brcmd.build_options(ns)
        self.assertEqual(opts.vectors_mode, "on")
        self.assertEqual(opts.batch_size, 2048)
        self.assertTrue(opts.embedding_model)  # falls back to default

    def test_build_options_passthrough(self):
        from wiki_generator.libs.commands import build_retrieval as brcmd
        import argparse
        ns = argparse.Namespace(
            in_dir="/x", bm25="off", vectors="auto", embedding_model="m/x",
            batch_size=8, rebuild=True, smoke_query="q", fail_without_vectors=False)
        opts = brcmd.build_options(ns)
        self.assertEqual(opts.vectors_mode, "auto")
        self.assertEqual(opts.bm25_mode, "off")
        self.assertEqual(opts.embedding_model, "m/x")
        self.assertEqual(opts.batch_size, 8)
        self.assertTrue(opts.rebuild)
        self.assertEqual(opts.smoke_query, "q")

    def test_build_options_rejects_bad_mode(self):
        from wiki_generator.libs.retrieval import BuildOptions
        with self.assertRaises(ValueError):
            BuildOptions(bundle_root="/x", vectors_mode="bogus")

    def test_corpus_fingerprint_order_independent(self):
        from wiki_generator.libs.retrieval import fingerprints as fp
        a = [{"chunk_id": "c1", "sha256": "aa"}, {"chunk_id": "c2", "sha256": "bb"}]
        b = list(reversed(a))
        self.assertEqual(fp.corpus_fingerprint(a), fp.corpus_fingerprint(b))
        c = [{"chunk_id": "c1", "sha256": "aa"}, {"chunk_id": "c2", "sha256": "CHANGED"}]
        self.assertNotEqual(fp.corpus_fingerprint(a), fp.corpus_fingerprint(c))
        self.assertTrue(fp.is_stale(None, "x"))
        self.assertFalse(fp.is_stale("x", "x"))

    def test_fts_match_query(self):
        from wiki_generator.libs.retrieval import bm25
        self.assertEqual(bm25.fts_match_query("foo bar"), '"foo" OR "bar"')
        self.assertIsNone(bm25.fts_match_query("   "))
        # punctuation can't become an FTS operator
        self.assertEqual(bm25.fts_match_query("a-b"), '"a" OR "b"')

    def test_fingerprint_corpus_vs_index_agree_with_null_sha(self):
        # corpus-side (str-normalized) and index-side (SQLite COALESCE) must
        # produce the SAME fingerprint even when a chunk has a null sha256.
        from wiki_generator.libs.retrieval import bm25, fingerprints
        db = os.path.join(tempfile.mkdtemp(prefix="p1fp_"), "bm25.sqlite")
        chunks = [
            {"chunk_id": "c1", "path": "a.py",
             "range": {"start_line": 1, "end_line": 2}, "sha256": None, "text": "x"},
            {"chunk_id": "c2", "path": "b.py",
             "range": {"start_line": 1, "end_line": 2}, "sha256": "abc", "text": "y"},
        ]
        bm25.build_index(db, [], chunks, [])
        state = bm25.read_index_state(db)
        self.assertEqual(state.fingerprint, fingerprints.corpus_fingerprint(chunks))

    def test_missing_corpus_raises(self):
        from wiki_generator.libs import retrieval
        empty = tempfile.mkdtemp(prefix="p1br_empty_")
        with self.assertRaises(retrieval.MissingCorpusError):
            retrieval.run(retrieval.BuildOptions(bundle_root=empty))

    def test_missing_corpus_exit_2(self):
        empty = tempfile.mkdtemp(prefix="p1br_empty2_")
        p = _run_cmd("build-retrieval", "--in", empty)
        self.assertEqual(p.returncode, 2, p.stderr)


class BuildRetrievalE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="p1br_")
        cls.repo = os.path.join(cls.tmp, "repo")
        cls.master = os.path.join(cls.tmp, "out")
        os.makedirs(cls.repo)
        _make_repo(cls.repo)
        cls.dec = _run(cls.repo, cls.master)

    def _fresh(self) -> str:
        """An isolated copy of the decomposed bundle (so a test that mutates the
        corpus or writes vector files never affects another test)."""
        dst = tempfile.mkdtemp(prefix="p1br_run_")
        out = os.path.join(dst, "bundle")
        shutil.copytree(self.master, out)
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        return out

    def _opts(self, out, **kw):
        from wiki_generator.libs.retrieval import BuildOptions
        return BuildOptions(bundle_root=out, **kw)

    def _caps(self, out):
        with open(os.path.join(out, "rag", "retrieval-capabilities.json")) as f:
            return json.load(f)

    def test_decompose_ok(self):
        self.assertEqual(self.dec.returncode, 0, self.dec.stderr)

    def test_bm25_verifies_after_decompose(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="off"))
        self.assertTrue(res.ok)
        # decompose already built the index with the shared builder -> verify
        self.assertEqual(res.bm25.status, "verified")
        self.assertTrue(res.bm25.ok)
        self.assertEqual(res.bm25.row_count, res.bm25.chunk_count)
        self.assertEqual(res.retrieval_mode, "lexical-symbolic")
        caps = self._caps(out)
        self.assertTrue(caps["capabilities"]["bm25"])
        self.assertTrue(caps["capabilities"]["file_lookup"])
        self.assertTrue(caps["capabilities"]["symbol_lookup"])
        self.assertFalse(caps["capabilities"]["vectors"])
        for name in ("retrieval-capabilities.json", "retrieval-substrate-report.md"):
            self.assertTrue(os.path.exists(os.path.join(out, "rag", name)), name)

    def test_vectors_auto_skips_gracefully(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="auto"),
                            backend=_FakeVectorBackend(available=False,
                                                       reason="no faiss here"))
        self.assertTrue(res.ok)  # auto-skip still passes
        self.assertEqual(res.vectors.status, "skipped")
        self.assertIn("no faiss here", res.vectors.reason)
        self.assertEqual(res.retrieval_mode, "lexical-symbolic")
        self.assertFalse(self._caps(out)["capabilities"]["vectors"])

    def test_vectors_on_fails_when_unavailable(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="on"),
                            backend=_FakeVectorBackend(available=False,
                                                       reason="missing libs"))
        self.assertFalse(res.ok)
        self.assertEqual(res.vectors.status, "failed")

    def test_vectors_on_fails_via_cli_without_faiss(self):
        try:
            import faiss  # noqa: F401
            from model2vec import StaticModel  # noqa: F401
        except Exception:
            pass
        else:
            self.skipTest(
                "faiss/model2vec installed; missing-backend behavior is covered "
                "by the injected-backend unit test")
        out = self._fresh()
        p = _run_cmd("build-retrieval", "--in", out, "--vectors", "on")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("FAIL", p.stderr)

    def test_vectors_auto_passes_via_cli_without_faiss(self):
        out = self._fresh()
        p = _run_cmd("build-retrieval", "--in", out, "--vectors", "auto")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_hybrid_build_with_backend(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="on"),
                            backend=_FakeVectorBackend(available=True))
        self.assertTrue(res.ok)
        self.assertEqual(res.vectors.status, "built")
        self.assertEqual(res.retrieval_mode, "hybrid")
        self.assertEqual(res.vectors.count, res.bm25.chunk_count)
        caps = self._caps(out)
        self.assertTrue(caps["capabilities"]["vectors"])
        self.assertEqual(caps["retrieval_mode"], "hybrid")
        with open(os.path.join(out, "rag", "vector-metadata.json")) as f:
            md = json.load(f)
        self.assertEqual(md["schema_version"], "vector-metadata-v1")
        self.assertEqual(len(md["vectors"]), res.vectors.count)
        row = md["vectors"][0]
        for k in ("ordinal", "chunk_id", "span_ids", "path", "range", "sha256"):
            self.assertIn(k, row)
        self.assertTrue(os.path.exists(os.path.join(out, "rag", "vector-build-report.md")))

    def test_vector_count_divergence_fails(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="on"),
                            backend=_FakeVectorBackend(available=True, count_delta=1))
        self.assertFalse(res.ok)
        self.assertEqual(res.vectors.status, "failed")
        self.assertIn("diverge", res.vectors.reason)

    def test_stale_index_triggers_rebuild(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        retrieval.run(self._opts(out, vectors_mode="off"))  # verify baseline
        chunks_path = os.path.join(out, "rag", "chunks.jsonl")
        rows = _read_jsonl(chunks_path)
        rows[0]["sha256"] = "0" * 64  # same row count, changed content hash
        with open(chunks_path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        res = retrieval.run(self._opts(out, vectors_mode="off"))
        self.assertEqual(res.bm25.status, "rebuilt")
        self.assertIn("stale", res.bm25.reason)
        self.assertTrue(res.bm25.ok)

    def test_rebuild_flag_forces_rebuild(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, vectors_mode="off", rebuild=True))
        self.assertEqual(res.bm25.status, "rebuilt")
        self.assertTrue(res.bm25.ok)

    def test_bm25_off_records_disabled(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        res = retrieval.run(self._opts(out, bm25_mode="off", vectors_mode="off"))
        self.assertTrue(res.ok)  # lexical-symbolic still viable via symbols/rg
        self.assertEqual(res.bm25.status, "disabled")
        self.assertFalse(self._caps(out)["capabilities"]["bm25"])

    def test_smoke_query_deterministic(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        opts = self._opts(out, vectors_mode="off", smoke_query="item service work")
        smoke_path = os.path.join(out, "rag", "retrieval-smoke-tests.jsonl")
        retrieval.run(opts)
        with open(smoke_path) as f:
            first = f.read()
        retrieval.run(opts)
        with open(smoke_path) as f:
            second = f.read()
        self.assertEqual(first, second)
        rows = [json.loads(ln) for ln in first.splitlines() if ln.strip()]
        self.assertEqual(rows[0]["mode"], "bm25")
        self.assertEqual(rows[0]["query"], "item service work")

    def test_capabilities_deterministic_across_verify_runs(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        opts = self._opts(out, vectors_mode="off")
        caps_path = os.path.join(out, "rag", "retrieval-capabilities.json")
        retrieval.run(opts)  # first run may build/verify
        with open(caps_path) as f:
            a = f.read()
        retrieval.run(opts)
        with open(caps_path) as f:
            b = f.read()
        self.assertEqual(a, b)

    # --- review-driven regression tests --------------------------------------
    def test_decompose_writes_v1_vector_metadata(self):
        # decompose now delegates vectors to the shared Step 5 builder, so its
        # vector-metadata.json is the same vector-metadata-v1 contract.
        with open(os.path.join(self.master, "rag", "vector-metadata.json")) as f:
            md = json.load(f)
        self.assertEqual(md["schema_version"], "vector-metadata-v1")

    def test_failed_vector_build_leaves_no_orphan_faiss(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        faiss_path = os.path.join(out, "rag", "vectors.faiss")
        res = retrieval.run(self._opts(out, vectors_mode="on"),
                            backend=_FakeVectorBackend(available=True, count_delta=1))
        self.assertEqual(res.vectors.status, "failed")
        # the index the backend wrote before the count check must be cleaned up
        self.assertFalse(os.path.exists(faiss_path), "orphan vectors.faiss left behind")

    def test_empty_corpus_skips_vectors_and_passes(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        with open(os.path.join(out, "rag", "chunks.jsonl"), "w"):
            pass  # empty corpus
        res = retrieval.run(self._opts(out, vectors_mode="auto"),
                            backend=_FakeVectorBackend(available=True))
        self.assertTrue(res.ok)
        self.assertEqual(res.vectors.status, "skipped")
        self.assertEqual(res.retrieval_mode, "lexical-symbolic")
        self.assertFalse(self._caps(out)["capabilities"]["vectors"])

    def test_stale_jsonl_metadata_cleaned_on_skip(self):
        from wiki_generator.libs.retrieval import BuildOptions
        from wiki_generator.libs import retrieval
        out = self._fresh()
        jsonl = os.path.join(out, "rag", "vector-metadata.jsonl")
        # force JSONL metadata by lowering the threshold, then build with vectors
        built = retrieval.run(
            BuildOptions(bundle_root=out, vectors_mode="on",
                         metadata_jsonl_threshold=1),
            backend=_FakeVectorBackend(available=True))
        self.assertTrue(built.ok)
        self.assertTrue(os.path.exists(jsonl), "expected jsonl metadata")
        # a later skip/disable run must not leave the orphan jsonl behind
        retrieval.run(self._opts(out, vectors_mode="off"))
        self.assertFalse(os.path.exists(jsonl), "stale vector-metadata.jsonl left behind")

    def test_malformed_chunk_exits_2(self):
        out = self._fresh()
        with open(os.path.join(out, "rag", "chunks.jsonl"), "w") as f:
            f.write(json.dumps({"chunk_id": "c1", "path": "x.py"}) + "\n")  # no range
        p = _run_cmd("build-retrieval", "--in", out)
        self.assertEqual(p.returncode, 2, p.stderr)

    def test_duplicate_chunk_id_exits_2(self):
        from wiki_generator.libs import retrieval
        out = self._fresh()
        row = {"chunk_id": "dup", "path": "x.py",
               "range": {"start_line": 1, "end_line": 2}, "sha256": "a"}
        with open(os.path.join(out, "rag", "chunks.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        with self.assertRaises(retrieval.MissingCorpusError):
            retrieval.run(self._opts(out, vectors_mode="off"))

    def test_batch_size_zero_exits_2(self):
        out = self._fresh()
        p = _run_cmd("build-retrieval", "--in", out, "--batch-size", "0")
        self.assertEqual(p.returncode, 2, p.stderr)


if __name__ == "__main__":
    unittest.main()
