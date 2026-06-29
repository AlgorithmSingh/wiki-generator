"""Phase E — grounded page-profile rendering and content-block coverage (expanded).

Deterministic, LLM-free, network-free tests for the additive ``expanded`` Phase 4
content-block coverage:

- ``build_content_block_obligations`` turns the Phase D evidenced matrix's
  ``content_blocks[]`` into per-section obligations carrying their supporting Phase 3
  evidence ids;
- ``normalize_covered_content_blocks`` parses the writer's declaration defensively;
- ``evaluate_section_block_coverage`` accepts a block covered with valid mapped,
  manifest-resolved, locally-cited evidence and rejects omitted / out-of-scope /
  uncited / absent blocks;
- ``evaluate_generated_coverage`` validates content blocks end to end (expanded), and
  is byte-unchanged in enhancement/baseline;
- the grounded ``render_section`` deterministically derives ``covered_content_blocks[]``
  from the topic subsections of the claims linked to each block;
- ``build_writing_packet`` carries the page profile, catalog topics, required content
  blocks, content-block obligations, and relevant-source-map rows in expanded mode.

No Gemini/Vertex/API/network; no real provider call.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.writing import claim_plan as cp  # noqa: E402
from wiki_generator.libs.writing import generated_coverage as gencov  # noqa: E402
from wiki_generator.libs.writing.packet import build_writing_packet  # noqa: E402
from wiki_generator.libs.writing.token_bank import TokenBank  # noqa: E402


# --- evidenced-matrix -> obligations -----------------------------------------
def _evidenced_matrix(content_blocks, topics):
    return {"sections": [{"section_id": "sub", "content_blocks": content_blocks,
                          "topics": topics}]}


class ContentBlockObligationTests(unittest.TestCase):
    def test_build_from_matrix(self):
        matrix = _evidenced_matrix(
            content_blocks=[{"content_block_id": "flow", "status": "sufficient",
                             "topics": ["flow topic"]},
                            {"content_block_id": "key_files", "status": "weak",
                             "topics": ["kf topic"]}],
            topics=[{"content_block_id": "flow",
                     "mapped_evidence_ids": ["ev:sub:0001", "ev:sub:0002"]},
                    {"content_block_id": "key_files",
                     "mapped_evidence_ids": ["ev:sub:0003"]}])
        out = gencov.build_content_block_obligations(matrix)
        rows = {r["content_block_id"]: r for r in out["sub"]}
        self.assertTrue(rows["flow"]["is_obligation"])
        self.assertEqual(rows["flow"]["supporting_evidence_ids"],
                         ["ev:sub:0001", "ev:sub:0002"])
        self.assertFalse(rows["key_files"]["is_obligation"])  # weak, not sufficient

    def test_enhancement_matrix_yields_no_block_obligations(self):
        # an enhancement matrix has no content_blocks[] -> nothing to oblige.
        matrix = {"sections": [{"section_id": "sub",
                                "topics": [{"mapped_evidence_ids": ["ev:sub:0001"]}]}]}
        self.assertEqual(gencov.build_content_block_obligations(matrix), {})


class NormalizeCoveredBlocksTests(unittest.TestCase):
    def test_parses_rows(self):
        rows = gencov.normalize_covered_content_blocks([
            {"content_block_id": "flow", "status": "covered",
             "evidence_ids": ["ev:sub:0001"], "markdown_anchor": "flow"},
            {"block_id": "key_files", "evidence_ids": ["ev:sub:0002", 7]},
            "garbage", {"status": "covered"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["content_block_id"], "flow")
        self.assertEqual(rows[1]["content_block_id"], "key_files")
        self.assertEqual(rows[1]["evidence_ids"], ["ev:sub:0002"])  # non-str dropped


class SectionBlockCoverageTests(unittest.TestCase):
    MD = ("## Subsystem\n\n### Flow\nThe parser flow runs end to end [ev:sub:0001].\n\n"
          "### Key files\nThe core module is described [ev:sub:0002].\n")
    EVIDENCE_INDEX = {"ev:sub:0001": object(), "ev:sub:0002": object()}
    MANIFEST_IDS = {"ev:sub:0001", "ev:sub:0002"}

    def _ob(self, bid, *, is_obligation=True, supporting=("ev:sub:0001",)):
        return {"content_block_id": bid, "evidenced_status": "sufficient",
                "is_obligation": is_obligation, "supporting_evidence_ids": list(supporting)}

    def _eval(self, obligations, covered_blocks):
        return gencov.evaluate_section_block_coverage(
            obligations=obligations, covered_blocks=covered_blocks, markdown=self.MD,
            evidence_index=self.EVIDENCE_INDEX, manifest_ids=self.MANIFEST_IDS)

    def test_covered(self):
        res = self._eval(
            [self._ob("flow")],
            [{"content_block_id": "flow", "status": "covered",
              "evidence_ids": ["ev:sub:0001"], "markdown_anchor": "flow"}])
        self.assertEqual(res["failures"], [])
        self.assertEqual(res["rows"][0]["generated_status"], gencov.GEN_COVERED)

    def test_omitted_block_fails(self):
        res = self._eval([self._ob("flow")], [])   # no declaration
        self.assertTrue(res["failures"])
        self.assertEqual(res["rows"][0]["generated_status"], gencov.GEN_OMITTED)

    def test_out_of_scope_evidence_fails(self):
        res = self._eval(
            [self._ob("flow", supporting=("ev:sub:0001",))],
            [{"content_block_id": "flow", "status": "covered",
              "evidence_ids": ["ev:sub:0002"], "markdown_anchor": "flow"}])
        self.assertTrue(res["failures"])
        self.assertEqual(res["rows"][0]["generated_status"], gencov.GEN_INVALID)

    def test_block_not_in_markdown_fails(self):
        res = self._eval(
            [self._ob("entrypoints")],
            [{"content_block_id": "entrypoints", "status": "covered",
              "evidence_ids": ["ev:sub:0001"], "markdown_anchor": "entrypoints"}])
        self.assertTrue(res["failures"])
        self.assertEqual(res["rows"][0]["generated_status"], gencov.GEN_INVALID)

    def test_non_obligation_block_is_omitted_not_failing(self):
        res = self._eval([self._ob("flow", is_obligation=False)], [])
        self.assertEqual(res["failures"], [])
        self.assertEqual(res["rows"][0]["generated_status"], gencov.GEN_OMITTED)


class EvaluateGeneratedCoverageExpandedTests(unittest.TestCase):
    def _bundle(self, root, *, block_obs):
        return SimpleNamespace(
            root=root, section_order=["sub"],
            section_plans={"sub": {"page_profile": "subsystem-deep-dive",
                                   "parent_section_id": None, "required_topics": []}},
            evidence_index={"ev:sub:0001": object()},
            topic_obligations={"sub": []},
            content_block_obligations={"sub": block_obs},
            coverage_mode="expanded")

    def _run(self, *, covered_blocks, block_obs):
        tmp = tempfile.mkdtemp(prefix="gencov_blocks_")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        sec_dir = os.path.join(tmp, "sections")
        os.makedirs(sec_dir)
        util.write_text(os.path.join(sec_dir, "sub.md"),
                        "## Subsystem\n\n### Flow\nThe flow [ev:sub:0001].\n")
        bundle = self._bundle(tmp, block_obs=block_obs)
        generated = [{"section_id": "sub", "markdown_path": "sections/sub.md",
                      "covered_topics": [], "covered_content_blocks": covered_blocks}]
        manifest = {"citations": [{"evidence_id": "ev:sub:0001"}]}
        return gencov.evaluate_generated_coverage(bundle, generated, manifest)

    def test_covered_block_passes(self):
        matrix = self._run(
            covered_blocks=[{"content_block_id": "flow", "status": "covered",
                             "evidence_ids": ["ev:sub:0001"], "markdown_anchor": "flow"}],
            block_obs=[{"content_block_id": "flow", "is_obligation": True,
                        "supporting_evidence_ids": ["ev:sub:0001"]}])
        self.assertEqual(matrix["status"], "pass", matrix["failures"])
        self.assertEqual(matrix["counts"]["required_content_blocks"], 1)
        self.assertEqual(matrix["counts"]["content_blocks_covered"], 1)

    def test_omitted_block_fails_the_matrix(self):
        matrix = self._run(
            covered_blocks=[],
            block_obs=[{"content_block_id": "flow", "is_obligation": True,
                        "supporting_evidence_ids": ["ev:sub:0001"]}])
        self.assertEqual(matrix["status"], "fail")
        self.assertTrue(any("flow" in f for f in matrix["failures"]))


class RenderContentBlocksTests(unittest.TestCase):
    def test_render_derives_covered_content_blocks(self):
        claims = [{
            "claim_id": "c1", "claim_kind": "runtime_flow",
            "evidence_ids": ["ev:sub:0001"], "token_ids": [],
            "token_evidence_ids": [], "render_evidence_ids": ["ev:sub:0001"],
            "required_topic": "Parser flow", "content_block_id": "flow",
            "intent": "", "skeleton": "The parser flow runs end to end."}]
        pv = cp.PlanValidation("sub", True, [], [], claims)
        bank = TokenBank(section_id="sub", tokens=[])
        obligations = [{"topic": "Parser flow", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:sub:0001"]}]
        block_obs = [{"content_block_id": "flow", "is_obligation": True,
                      "supporting_evidence_ids": ["ev:sub:0001"]}]
        rendered = cp.render_section(
            pv, token_bank=bank, title="Subsystem", section_id="sub",
            obligations=obligations, content_block_obligations=block_obs)
        self.assertIsNotNone(rendered.covered_content_blocks)
        row = rendered.covered_content_blocks[0]
        self.assertEqual(row["content_block_id"], "flow")
        self.assertEqual(row["evidence_ids"], ["ev:sub:0001"])
        # the block reuses the topic subsection anchor (locatable + locally cited).
        self.assertEqual(row["markdown_anchor"], "parser-flow")
        draft = cp.rendered_draft(rendered)
        self.assertIn("covered_content_blocks", draft)

    def test_baseline_render_has_no_content_blocks(self):
        claims = [{"claim_id": "c1", "claim_kind": "prose", "evidence_ids": ["e"],
                   "token_ids": [], "token_evidence_ids": [],
                   "render_evidence_ids": ["e"], "required_topic": None,
                   "content_block_id": None, "intent": "", "skeleton": "Hello."}]
        pv = cp.PlanValidation("sub", True, [], [], claims)
        bank = TokenBank(section_id="sub", tokens=[])
        rendered = cp.render_section(pv, token_bank=bank, title="S", section_id="sub")
        self.assertIsNone(rendered.covered_content_blocks)


class PacketEnrichmentTests(unittest.TestCase):
    def test_expanded_packet_carries_page_context(self):
        tmp = tempfile.mkdtemp(prefix="packet_expanded_")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        os.makedirs(os.path.join(tmp, "plans"))
        util.write_json(os.path.join(tmp, "plans", "relevant-source-map.json"),
                        {"pages": [{"section_id": "sub", "selected_handles": [
                            {"handle_id": "sub:files:0", "lane": "file_anchor",
                             "path": "a.py"}]}]})
        bundle = SimpleNamespace(
            root=tmp,
            document_plan={"title": "T", "purpose": "", "audience": ""},
            section_order=["sub"],
            section_plans={"sub": {
                "title": "Subsystem", "purpose": "", "goal": "",
                "required_topics": ["Parser flow"], "key_questions": [],
                "expected_evidence_types": [], "retrieval_needs": {},
                "page_profile": "subsystem-deep-dive",
                "catalog_topic_ids": ["doc.parsers"],
                "required_content_blocks": [{"block_id": "flow"}],
                "parent_section_id": None, "coverage_labels": []}},
            packets={"sub": {"order": 1, "evidence": []}},
            coverage_mode="expanded",
            topic_obligations={"sub": [{"topic": "Parser flow",
                                        "evidenced_status": "sufficient",
                                        "is_obligation": True,
                                        "mapped_evidence_ids": ["ev:sub:0001"],
                                        "min_items": 1}]},
            content_block_obligations={"sub": [{
                "content_block_id": "flow", "evidenced_status": "sufficient",
                "is_obligation": True, "supporting_evidence_ids": ["ev:sub:0001"]}]})
        pkt = build_writing_packet(bundle, "sub")
        self.assertEqual(pkt.data["page_profile"], "subsystem-deep-dive")
        self.assertEqual(pkt.data["catalog_topic_ids"], ["doc.parsers"])
        self.assertEqual(pkt.data["required_content_blocks"], [{"block_id": "flow"}])
        self.assertEqual(pkt.data["content_block_coverage"][0]["content_block_id"],
                         "flow")
        self.assertEqual(pkt.data["relevant_source_handles"][0]["path"], "a.py")
        self.assertIsNotNone(pkt.content_block_coverage)


if __name__ == "__main__":
    unittest.main()
