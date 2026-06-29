"""Phase A (DeepWiki coverage expansion) — facet clustering slice.

Deterministic, LLM-free tests for ``libs/coverage/facets.py``: the source-derived
subsystem clustering that turns a family's candidate files into a shallow
hierarchy of facets (by leaf directory). No Gemini/Vertex/API/network calls; no
live pipeline runs.

Proves the slice's required behaviours:

- files are grouped into facets by their leaf directory (top-level files cluster
  under ``(root)``);
- facet keys are stable, family-unique kebab-case slugs, with deterministic
  collision breaking;
- a family with no candidate files has no facets;
- paths-per-facet and facets-per-family are bounded;
- output ordering is deterministic (directory order) and byte-stable across runs.

Run with stdlib only: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs.coverage import facets as F  # noqa: E402


def _c(path, category="source", reasons=("dir:x",)):
    """A minimal candidate dict shaped like signals.family_candidates() output."""
    return {"path": path, "category": category, "reasons": list(reasons)}


class LeafDirTests(unittest.TestCase):
    def test_leaf_dir_of_nested_path(self):
        self.assertEqual(F._leaf_dir("a/b/c.py"), "a/b")

    def test_leaf_dir_of_top_level_file_is_root(self):
        self.assertEqual(F._leaf_dir("go.mod"), F.ROOT_DIRECTORY)

    def test_leaf_dir_normalises_separators(self):
        self.assertEqual(F._leaf_dir("a\\b\\c.py"), "a/b")


class FacetGroupingTests(unittest.TestCase):
    def setUp(self):
        self.cands = [
            _c("deepdoc/parser/pdf.py"),
            _c("deepdoc/parser/docx.py"),
            _c("deepdoc/vision/ocr.py"),
            _c("top.py"),
        ]
        self.facets = F.derive_family_facets("doc-processing", self.cands)
        self.by = {f.directory: f for f in self.facets}

    def test_one_facet_per_leaf_directory(self):
        self.assertEqual(set(self.by),
                         {"deepdoc/parser", "deepdoc/vision", F.ROOT_DIRECTORY})

    def test_facet_file_counts(self):
        self.assertEqual(self.by["deepdoc/parser"].file_count, 2)
        self.assertEqual(self.by["deepdoc/vision"].file_count, 1)
        self.assertEqual(self.by[F.ROOT_DIRECTORY].file_count, 1)

    def test_facet_paths_are_sorted(self):
        self.assertEqual(list(self.by["deepdoc/parser"].paths),
                         ["deepdoc/parser/docx.py", "deepdoc/parser/pdf.py"])

    def test_facets_emitted_in_directory_order(self):
        self.assertEqual([f.directory for f in self.facets],
                         sorted(f.directory for f in self.facets))

    def test_family_key_carried_through(self):
        self.assertTrue(all(f.family_key == "doc-processing" for f in self.facets))

    def test_root_facet_key_is_root(self):
        self.assertEqual(self.by[F.ROOT_DIRECTORY].facet_key, "root")

    def test_facet_keys_are_slugged_directories(self):
        self.assertEqual(self.by["deepdoc/parser"].facet_key, "deepdoc-parser")

    def test_facet_reasons_and_categories_deduped(self):
        f = self.by["deepdoc/parser"]
        self.assertEqual(list(f.categories), ["source"])
        self.assertEqual(list(f.reasons), ["dir:x"])


class FacetKeyCollisionTests(unittest.TestCase):
    def test_distinct_dirs_with_same_slug_get_unique_keys(self):
        # "a/b" and "a-b" both slug to "a-b"; keys must stay family-unique so
        # topic IDs built from them never collide.
        cands = [_c("a/b/one.py"), _c("a-b/two.py")]
        keys = sorted(f.facet_key for f in F.derive_family_facets("fam", cands))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("a-b", keys)
        self.assertIn("a-b-2", keys)


class FacetBoundsTests(unittest.TestCase):
    def test_no_candidates_means_no_facets(self):
        self.assertEqual(F.derive_family_facets("fam", []), [])

    def test_paths_per_facet_capped(self):
        many = [_c(f"d/f{i:03}.py") for i in range(F.MAX_PATHS_PER_FACET + 8)]
        facet = F.derive_family_facets("fam", many)[0]
        self.assertEqual(facet.file_count, F.MAX_PATHS_PER_FACET + 8)  # true count
        self.assertEqual(len(facet.paths), F.MAX_PATHS_PER_FACET)      # display cap

    def test_facets_per_family_capped_keeping_largest(self):
        cands = []
        # one file in each of many single-file dirs, plus one populated dir.
        for i in range(F.MAX_FACETS_PER_FAMILY + 5):
            cands.append(_c(f"dir{i:03}/only.py"))
        for j in range(4):
            cands.append(_c(f"big/file{j}.py"))
        facets = F.derive_family_facets("fam", cands)
        self.assertEqual(len(facets), F.MAX_FACETS_PER_FAMILY)
        # the most-populated subsystem is never dropped by the cap
        self.assertIn("big", [f.directory for f in facets])


class FacetDeterminismTests(unittest.TestCase):
    def test_repeated_derivation_is_byte_stable(self):
        cands = [_c("p/q/a.py"), _c("p/q/b.py"), _c("p/r/c.py"), _c("z.py")]
        a = F.derive_family_facets("fam", cands)
        b = F.derive_family_facets("fam", list(reversed(cands)))
        self.assertEqual([(f.facet_key, f.directory, f.paths) for f in a],
                         [(f.facet_key, f.directory, f.paths) for f in b])


if __name__ == "__main__":
    unittest.main()
