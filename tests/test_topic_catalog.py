"""Phase A (DeepWiki coverage expansion) — topic-catalog slice.

Deterministic, LLM-free tests for ``libs/coverage/topic_catalog.py``: the
repository-derived hierarchical topic catalog (parent families + source-derived
child subsystems), its machine-readable JSON, its planner-facing markdown, and
its integration into the condense / upload-package flow. No Gemini/Vertex/API/
network calls; no live pipeline runs.

Proves the slice's required behaviours (Phase A acceptance criteria):

- the catalog emits one parent topic per mandatory family plus child subsystem
  topics under high-signal families (path/doc/config/test-derived);
- frontend / deployment / backend-like signals surface where fixtures permit;
- weak (low-signal) and deferred (missing) families are explicit, separated, and
  carry source-derived known-gap reasons rather than invented pages;
- topic IDs are stable and output ordering is deterministic and byte-stable;
- the catalog is non-citeable planner context and benchmark-isolated;
- the condense step writes topic-catalog.json + planning-topic-catalog.md and the
  upload bundle includes the markdown as planner context, never citeable evidence.

Run with stdlib only: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.coverage import topic_catalog as TC  # noqa: E402
from wiki_generator.libs.coverage.taxonomy import family_keys  # noqa: E402
from wiki_generator.libs.digest.loader import Bundle, load_bundle  # noqa: E402


def _f(path, category="source", *, ext=None, generated=False, vendor=False,
       binary=False):
    """A minimal inventory row shaped like inventory/files.jsonl."""
    name = path.rsplit("/", 1)[-1]
    if ext is None:
        ext = ("." + name.rsplit(".", 1)[-1]) if "." in name else ""
    return {"path": path, "name": name, "ext": ext, "category": category,
            "is_generated": generated, "is_vendor": vendor, "is_binary": binary,
            "top_dir": (path.split("/", 1)[0] if "/" in path else "(root)")}


# A synthetic inventory exercising present-with-children (frontend, doc-processing,
# helm deployment), weak/low families (memory, queue via a TEST file, go via a
# CONFIG file, migrations), and missing/deferred families (the rest). Noise must
# not create false topics.
CATALOG_FILES = [
    # frontend: present (ext + dir + i18n + config basename) across 3 leaf dirs
    _f("web/src/app.tsx"),
    _f("web/src/dashboard.tsx"),
    _f("web/src/locales/en.ts"),
    _f("web/package.json", "config"),
    # doc-processing: present (source) across 2 leaf dirs
    _f("deepdoc/parser/pdf_parser.py"),
    _f("deepdoc/parser/docx_parser.py"),
    _f("deepdoc/vision/ocr.py"),
    # helm-k8s: present (deployment) across 2 leaf dirs
    _f("helm/ragflow/Chart.yaml", "deployment"),
    _f("helm/ragflow/values.yaml", "deployment"),
    _f("helm/ragflow/templates/deployment.yaml", "deployment"),
    # weak single-signal families
    _f("agent/memory/memory.py"),                    # memory (source) -> low
    _f("api/db/migrations/0001_init.py"),            # migrations (source) -> low
    _f("tests/test_task_worker.py", "test"),         # queue-system (TEST) -> low
    _f("go.mod", "config"),                          # go-native (CONFIG) -> low
    # noise: must not light up a family
    _f("research/researcher.py"),
]


def _bundle(files=CATALOG_FILES, root="/demo"):
    return Bundle(root=root, files=list(files),
                  coverage={"repo_root": root,
                            "counts_by_top_dir": {"web": 4, "deepdoc": 3}})


class CatalogShapeTests(unittest.TestCase):
    def setUp(self):
        self.cat = TC.build_topic_catalog(_bundle())
        self.by = {t.topic_id: t for t in self.cat.topics}

    def test_schema_and_non_citeable_metadata(self):
        d = self.cat.to_dict()
        self.assertEqual(d["schema_version"], "deepwiki-topic-catalog-v1")
        self.assertEqual(d["role"], "planner_context")
        self.assertFalse(d["citeable_as_evidence"])
        self.assertTrue(d["source_fingerprint"].startswith("sha256:"))

    def test_one_parent_topic_per_mandatory_family(self):
        parents = {t.topic_id for t in self.cat.topics
                   if t.topic_kind == TC.TOPIC_KIND_FAMILY}
        self.assertEqual(parents, set(family_keys()))
        self.assertEqual(self.cat.family_count, 13)
        for t in self.cat.topics:
            if t.topic_kind == TC.TOPIC_KIND_FAMILY:
                self.assertIsNone(t.parent_topic_id)

    def test_present_family_gets_subsystem_children(self):
        # frontend is high-signal across >=2 leaf dirs -> child subsystems exist
        children = [t for t in self.cat.topics
                    if t.parent_topic_id == "frontend"]
        self.assertTrue(children)
        for c in children:
            self.assertEqual(c.topic_kind, TC.TOPIC_KIND_SUBSYSTEM)
            self.assertTrue(c.topic_id.startswith("frontend."))
            self.assertEqual(c.family, "frontend")

    def test_low_family_has_no_children(self):
        # memory is single-signal -> represented by its parent topic alone
        self.assertEqual(self.by["memory"].status, "low")
        self.assertFalse([t for t in self.cat.topics
                          if t.parent_topic_id == "memory"])

    def test_deferred_family_is_explicit_known_gap(self):
        # a missing family is a deferred known gap, never an invented page
        sandbox = self.by["sandbox-executor"]
        self.assertEqual(sandbox.status, "missing")
        self.assertEqual(sandbox.priority, "could")
        self.assertIsNotNone(sandbox.known_gap_reason)
        self.assertFalse(sandbox.candidate_source_handles)
        self.assertGreaterEqual(self.cat.deferred_count, 1)

    def test_glossary_is_synthesized_not_missing(self):
        gloss = self.by["glossary"]
        self.assertEqual(gloss.status, "synthesized")
        self.assertEqual(gloss.suggested_page_profile, "glossary")
        self.assertIsNone(gloss.known_gap_reason)

    def test_present_parents_carry_must_priority_and_handles(self):
        for key in ("frontend", "doc-processing", "helm-k8s"):
            p = self.by[key]
            self.assertEqual(p.status, "present")
            self.assertEqual(p.priority, "must")
            self.assertTrue(p.candidate_source_handles)
            self.assertGreaterEqual(p.min_exact_items, 3)


class SourceDerivationTests(unittest.TestCase):
    """Topics are derived from path/doc/config/test inventory signals."""

    def setUp(self):
        self.by = {t.topic_id: t
                   for t in TC.build_topic_catalog(_bundle()).topics}

    def test_source_file_derived_topic(self):
        handles = {h.path for h in self.by["doc-processing"].candidate_source_handles}
        self.assertIn("deepdoc/parser/pdf_parser.py", handles)

    def test_config_file_derived_topic(self):
        handles = {h.path for h in self.by["go-native"].candidate_source_handles}
        self.assertIn("go.mod", handles)

    def test_deployment_file_derived_topic(self):
        handles = {h.path for h in self.by["helm-k8s"].candidate_source_handles}
        self.assertIn("helm/ragflow/values.yaml", handles)

    def test_test_file_derived_topic(self):
        handles = {h.path for h in self.by["queue-system"].candidate_source_handles}
        self.assertIn("tests/test_task_worker.py", handles)

    def test_handles_never_reference_generated_context_docs(self):
        for t in TC.build_topic_catalog(_bundle()).topics:
            for h in t.candidate_source_handles:
                if h.path:
                    self.assertFalse(h.path.startswith("derived/"))
                    self.assertNotIn("planning-", h.path)


class DeterminismTests(unittest.TestCase):
    def test_topics_and_fingerprint_are_stable(self):
        a = TC.build_topic_catalog(_bundle())
        b = TC.build_topic_catalog(_bundle())
        self.assertEqual(json.dumps(a.to_dict(), sort_keys=True),
                         json.dumps(b.to_dict(), sort_keys=True))
        self.assertEqual(a.source_fingerprint, b.source_fingerprint)

    def test_families_emitted_in_taxonomy_order(self):
        parents = [t.topic_id for t in TC.build_topic_catalog(_bundle()).topics
                   if t.topic_kind == TC.TOPIC_KIND_FAMILY]
        self.assertEqual(parents, list(family_keys()))

    def test_child_follows_its_parent(self):
        topics = TC.build_topic_catalog(_bundle()).topics
        ids = [t.topic_id for t in topics]
        for i, t in enumerate(topics):
            if t.topic_kind == TC.TOPIC_KIND_SUBSYSTEM:
                self.assertIn(t.parent_topic_id, ids[:i],
                              f"{t.topic_id} appears before its parent")

    def test_empty_bundle_defers_all_but_glossary(self):
        cat = TC.build_topic_catalog(Bundle(root="/d", coverage={"repo_root": "/d"}))
        by = {t.topic_id: t for t in cat.topics}
        self.assertEqual(cat.subsystem_count, 0)
        self.assertEqual(cat.deferred_count, 12)
        self.assertEqual(by["glossary"].status, "synthesized")
        self.assertEqual(by["frontend"].status, "missing")


class BenchmarkIsolationTests(unittest.TestCase):
    def test_every_signal_source_is_repo(self):
        for t in TC.build_topic_catalog(_bundle()).topics:
            for s in t.source_signals:
                self.assertEqual(s.source, "repo")

    def test_no_benchmark_strings_in_serialised_catalog(self):
        cat = TC.build_topic_catalog(_bundle())
        blob = (json.dumps(cat.to_dict())
                + TC.render_catalog_markdown(cat)).lower()
        for needle in ("ragflow-deepwiki", "benchmark"):
            # the catalog renders a "benchmark-isolated" claim, so only forbid
            # benchmark material being *used*; assert no benchmark file path leaks.
            self.assertNotIn(needle + ".md", blob)
            self.assertNotIn("/" + needle, blob)


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.md = TC.render_catalog_markdown(TC.build_topic_catalog(_bundle()))

    def test_labels_itself_non_citeable_planner_context(self):
        self.assertIn("Planner CONTEXT, not evidence", self.md)
        self.assertIn("not citeable Phase 3 evidence", self.md)
        self.assertIn("non-citeable", self.md)

    def test_states_it_is_benchmark_isolated(self):
        self.assertIn("no benchmark export seeds", self.md)
        self.assertIn("benchmark-isolated", self.md)

    def test_separates_strong_from_weak_and_deferred(self):
        self.assertIn("## Strong source-derived topics", self.md)
        self.assertIn("## Weak and deferred topics", self.md)
        self.assertIn("Deferred (known gaps)", self.md)

    def test_lists_candidate_handles_for_present_family(self):
        self.assertIn("helm/ragflow/values.yaml", self.md)
        self.assertIn("`frontend`", self.md)

    def test_is_deterministic(self):
        md2 = TC.render_catalog_markdown(TC.build_topic_catalog(_bundle()))
        self.assertEqual(self.md, md2)


class CondenseIntegrationTests(unittest.TestCase):
    """The condense step writes both catalog artifacts and the upload bundle
    includes the planner-facing markdown (deterministic, no decompose run)."""

    def _bundle_dir(self):
        d = tempfile.mkdtemp(prefix="topiccat_")
        self.addCleanup(_rmtree, d)
        inv = os.path.join(d, "inventory")
        os.makedirs(inv, exist_ok=True)
        util.write_jsonl(os.path.join(inv, "files.jsonl"), CATALOG_FILES)
        util.write_json(os.path.join(inv, "source-coverage.json"),
                        {"repo_root": d,
                         "counts_by_top_dir": {"web": 4, "deepdoc": 3}})
        return d

    def test_condense_writes_catalog_json_and_markdown(self):
        from wiki_generator.libs.commands import condense as condense_cmd
        d = self._bundle_dir()
        bundle = load_bundle(d)
        derived = os.path.join(d, "derived")
        condense_cmd.write_condensates(bundle, derived)

        md_path = os.path.join(derived, "planning-topic-catalog.md")
        json_path = os.path.join(derived, "topic-catalog.json")
        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(os.path.isfile(json_path))
        data = util.read_json(json_path)
        self.assertEqual(data["schema_version"], "deepwiki-topic-catalog-v1")
        self.assertFalse(data["citeable_as_evidence"])
        self.assertEqual(data["role"], "planner_context")
        self.assertEqual(data["family_count"], 13)
        with open(md_path, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("DeepWiki Topic Catalog", md)
        self.assertIn("not citeable Phase 3 evidence", md)

    def test_catalog_json_is_not_uploaded_but_markdown_is(self):
        from wiki_generator.libs.commands import condense as condense_cmd
        from wiki_generator.libs.digest import upload_package
        d = self._bundle_dir()
        bundle = load_bundle(d)
        condense_cmd.write_condensates(bundle, os.path.join(d, "derived"))
        out = os.path.join(d, "planner-digest")
        report = upload_package.assemble(d, out, 250_000, "gen-at", d)
        # the markdown ships as planner context...
        self.assertIn("derived/planning-topic-catalog.md", report["included"])
        with open(os.path.join(out, "planner-upload-bundle.md"),
                  encoding="utf-8") as f:
            text = f.read()
        self.assertIn(
            "BEGIN INCLUDED FILE: derived/planning-topic-catalog.md", text)
        # ...but the machine-readable JSON is a derived sidecar, never uploaded.
        self.assertNotIn("topic-catalog.json", set(os.listdir(out)))
        with open(os.path.join(out, "README_FOR_PLANNER.md"),
                  encoding="utf-8") as f:
            self.assertIn("planning-topic-catalog.md", f.read())


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
