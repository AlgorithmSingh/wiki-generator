"""Phase C — deterministic relevant-source map and source-selection gate.

Deterministic, LLM-free, network-free tests for ``coverage.source_selection``:

- the source map selects one citeable exact handle per resolved exact lane item
  (files/symbols/contracts/tests/query_packs) and never promotes broad recall
  (``search_hints`` / ``graph_nodes``) to a citeable handle;
- each handle is mapped to the catalog topics / content blocks its TERs declare,
  with a deterministic, documented score and a tri-state citeability;
- the map fingerprints the catalog (``source_fingerprint``) and the normalized plan
  it consumed; identical inputs produce a byte-identical map;
- the source-selection gate fails closed (expanded mode) when a page-profile floor,
  a blocking required topic, or an evidence-bearing content block has no citeable
  selected handle, and reports-only in baseline mode;
- benchmark / generated-wiki artifacts are never source-map inputs.

No Gemini/Vertex/API/network.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs.coverage import source_selection as ss  # noqa: E402


def _needs(**lanes):
    base = {"query_packs": [], "symbols": [], "files": [], "contracts": [],
            "tests": [], "graph_nodes": [], "search_hints": [], "context_artifacts": []}
    base.update(lanes)
    return base


def _file(path):
    return {"input": path, "path": path, "resolution": "file_exists"}


def _sym(sid):
    return {"input": sid, "symbol_id": sid, "resolution": "exact"}


def _ter(topic, source_fields, *, required=True, catalog_topic_id=None,
         content_block_id=None, acceptable_lanes=None):
    return {"topic": topic, "required": required, "source_fields": list(source_fields),
            "min_items": 1,
            "acceptable_lanes": list(acceptable_lanes) if acceptable_lanes is not None
            else ["file_anchor", "symbol_anchor", "contract", "test", "query_pack"],
            "catalog_topic_id": catalog_topic_id, "content_block_id": content_block_id}


def _section(sid, *, profile=None, catalog_ids=(), needs=None, required_topics=(),
             ters=(), blocks=(), role="source"):
    return {
        "section_id": sid, "section_role": role, "title": sid,
        "page_profile": profile, "parent_section_id": None,
        "catalog_topic_ids": list(catalog_ids),
        "required_content_blocks": [
            {"block_id": b, "block_type": b, "required": True,
             "required_topics": [], "min_exact_items": 0,
             "expected_evidence_lanes": []} for b in blocks],
        "required_topics": list(required_topics),
        "topic_evidence_requirements": list(ters),
        "known_gaps": [], "retrieval_needs": needs or _needs(),
    }


def _catalog(fp="sha256:catfp"):
    return {"schema_version": "deepwiki-topic-catalog-v1",
            "source_fingerprint": fp, "topics": []}


def _substrate(chunk_paths=(), span_paths=()):
    return cov.CiteableSubstrate(chunk_paths=frozenset(chunk_paths),
                                 span_paths=frozenset(span_paths), available=True)


# ===========================================================================
class SourceSelectionTests(unittest.TestCase):
    def test_selects_exact_handles_only(self):
        sec = _section(
            "s", profile="subsystem-deep-dive",
            needs=_needs(files=[_file("rag/app.py")], symbols=[_sym("rag.app.run")],
                         search_hints=[{"text": "broad recall"}],
                         graph_nodes=["n1"]))
        sm = cov.build_relevant_source_map(_catalog(), None, [sec])
        page = sm.pages[0]
        lanes = sorted(h.lane for h in page.selected_handles)
        self.assertEqual(lanes, ["file_anchor", "symbol_anchor"])
        # broad recall lanes never become selected handles
        self.assertNotIn("bm25", lanes)
        self.assertNotIn("graph_neighbors", lanes)

    def test_handle_mapped_to_topic_and_block(self):
        sec = _section(
            "s", profile="subsystem-deep-dive",
            needs=_needs(files=[_file("rag/app.py")]),
            required_topics=["flow"],
            ters=[_ter("flow", ["retrieval_needs.files[0]"],
                       catalog_topic_id="doc.flow", content_block_id="flow")])
        sm = cov.build_relevant_source_map(_catalog(), None, [sec])
        h = sm.pages[0].selected_handles[0]
        self.assertEqual(list(h.topics), ["flow"])
        self.assertEqual(list(h.catalog_topic_ids), ["doc.flow"])
        self.assertEqual(list(h.content_block_ids), ["flow"])
        # named by a required obligation -> higher score than a bare handle
        self.assertGreater(h.score, ss._LANE_WEIGHT["file_anchor"])

    def test_citeability_tristate(self):
        sec = _section("s", profile="subsystem-deep-dive",
                       needs=_needs(files=[_file("rag/app.py")],
                                    symbols=[_sym("rag.app.run")]))
        # with a substrate that cites the file path
        sm = cov.build_relevant_source_map(_catalog(), None, [sec],
                                           substrate=_substrate(chunk_paths=["rag/app.py"]))
        by_lane = {h.lane: h for h in sm.pages[0].selected_handles}
        self.assertIs(by_lane["file_anchor"].citeable, True)
        # symbol lane is undecidable by the substrate view
        self.assertIsNone(by_lane["symbol_anchor"].citeable)
        # without a substrate, file citeability is undecidable (never a false fail)
        sm2 = cov.build_relevant_source_map(_catalog(), None, [sec])
        self.assertIsNone({h.lane: h for h in sm2.pages[0].selected_handles}["file_anchor"].citeable)

    def test_deterministic_and_fingerprinted(self):
        sec = _section("s", profile="subsystem-deep-dive",
                       needs=_needs(files=[_file("a.py"), _file("b.py")]))
        a = cov.build_relevant_source_map(_catalog("sha256:X"), None, [sec]).to_dict()
        b = cov.build_relevant_source_map(_catalog("sha256:X"), None, [sec]).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["catalog_fingerprint"], "sha256:X")
        self.assertTrue(a["plan_fingerprint"].startswith("sha256:"))
        # a changed plan changes the plan fingerprint
        sec2 = _section("s", profile="subsystem-deep-dive",
                        needs=_needs(files=[_file("a.py")]))
        c = cov.build_relevant_source_map(_catalog("sha256:X"), None, [sec2]).to_dict()
        self.assertNotEqual(a["plan_fingerprint"], c["plan_fingerprint"])

    def test_map_marks_non_citeable_role(self):
        sm = cov.build_relevant_source_map(_catalog(), None, []).to_dict()
        self.assertFalse(sm["citeable_as_evidence"])
        self.assertEqual(sm["role"], "source_selection")


class SourceMapGateTests(unittest.TestCase):
    def _gate(self, sections, *, substrate=None, mode=cov.MODE_EXPANDED):
        sm = cov.build_relevant_source_map(_catalog(), None, sections,
                                           substrate=substrate)
        return cov.gate_source_map(sm, sections, mode=mode)

    def test_page_floor_satisfied_passes(self):
        sec = _section("s", profile="subsystem-deep-dive",
                       blocks=cov.required_block_ids("subsystem-deep-dive"),
                       needs=_needs(files=[_file("rag/app.py")]))
        g = self._gate([sec], substrate=_substrate(chunk_paths=["rag/app.py"]))
        self.assertTrue(g.passed, [d.to_dict() for d in g.report.diagnostics])

    def test_page_floor_unsatisfied_fails(self):
        # api-reference floor is (contract, file_anchor, symbol_anchor); the page
        # only carries a `test` handle -> no floor lane -> fail.
        sec = _section("s", profile="api-reference",
                       needs=_needs(tests=[_file("tests/test_app.py")]))
        g = self._gate([sec], substrate=_substrate(chunk_paths=["tests/test_app.py"]))
        self.assertFalse(g.passed)
        codes = {d.code for d in g.report.diagnostics}
        self.assertIn(ss.CODE_PAGE_NO_FLOOR_HANDLE, codes)

    def test_non_citeable_floor_handle_fails(self):
        # the only floor-lane handle resolves to a path the substrate cannot cite.
        sec = _section("s", profile="subsystem-deep-dive",
                       needs=_needs(files=[_file("go.mod")]))
        g = self._gate([sec], substrate=_substrate(chunk_paths=["other.py"]))
        self.assertFalse(g.passed)
        codes = {d.code for d in g.report.diagnostics}
        self.assertIn(ss.CODE_PAGE_NO_FLOOR_HANDLE, codes)

    def test_content_block_without_citeable_handle_fails(self):
        # the flow block is TER-linked but its handle is non-citeable.
        sec = _section(
            "s", profile="subsystem-deep-dive",
            blocks=cov.required_block_ids("subsystem-deep-dive"),
            needs=_needs(files=[_file("rag/app.py"), _file("go.mod")]),
            required_topics=["flow"],
            ters=[_ter("flow", ["retrieval_needs.files[1]"],   # -> go.mod
                       content_block_id="flow")])
        # rag/app.py is citeable (satisfies the page floor) but go.mod is not, and
        # go.mod is the only handle linked to the flow block.
        g = self._gate([sec], substrate=_substrate(chunk_paths=["rag/app.py"]))
        self.assertFalse(g.passed)
        codes = {d.code for d in g.report.diagnostics}
        self.assertIn(ss.CODE_BLOCK_NO_HANDLE, codes)

    def test_blocking_topic_without_handle_fails(self):
        # a required topic whose TER points at a broad lane -> no exact selected
        # handle maps to it.
        sec = _section(
            "s", profile="subsystem-deep-dive",
            blocks=cov.required_block_ids("subsystem-deep-dive"),
            needs=_needs(files=[_file("rag/app.py")], search_hints=[{"text": "x"}]),
            required_topics=["loose"],
            ters=[_ter("loose", ["retrieval_needs.search_hints[0]"])])
        g = self._gate([sec], substrate=_substrate(chunk_paths=["rag/app.py"]))
        self.assertFalse(g.passed)
        codes = {d.code for d in g.report.diagnostics}
        self.assertIn(ss.CODE_TOPIC_NO_HANDLE, codes)

    def test_glossary_profile_skips_floor(self):
        sec = _section("g", profile="glossary",
                       blocks=cov.required_block_ids("glossary"))
        g = self._gate([sec])
        self.assertTrue(g.passed)

    def test_provenance_section_skipped(self):
        sec = _section("prov", profile=None, role="provenance")
        g = self._gate([sec])
        self.assertTrue(g.passed)

    def test_baseline_reports_but_never_gates(self):
        sec = _section("s", profile="api-reference",
                       needs=_needs(tests=[_file("t.py")]))
        g = self._gate([sec], substrate=_substrate(chunk_paths=["t.py"]),
                       mode=cov.MODE_BASELINE)
        self.assertTrue(g.passed)              # report-only
        self.assertFalse(g.report.enforced)
        self.assertTrue(g.report.diagnostics)  # still reported


if __name__ == "__main__":
    unittest.main()
