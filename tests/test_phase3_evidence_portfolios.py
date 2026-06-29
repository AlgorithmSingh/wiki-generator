"""Phase D — profile-aware evidence portfolios (expanded coverage).

Deterministic, LLM-free, network-free tests for the additive ``expanded`` evidenced
coverage: ``coverage.evaluate_evidenced_coverage`` with
``options.coverage_mode == "expanded"``.

- expanded mode carries page/profile/content-block linkage onto the matrix
  (``page_profile``, per-topic ``catalog_topic_id`` / ``content_block_id``,
  ``portfolio_status`` / ``portfolio_requirements`` / ``content_blocks``);
- a page is portfolio-sufficient only when its retrieved exact evidence covers a
  page-profile floor lane and meets the profile minimum exact item count;
- a page whose required topic is sufficient but whose exact evidence covers NO
  profile floor lane still fails the portfolio (broad/off-floor recall is not a
  sufficient page portfolio) — a distinct block beyond per-topic sufficiency;
- a TER-linked evidence-bearing content block with no sufficient topic blocks;
- the glossary profile (no exact floor) is portfolio not-applicable and never blocks;
- portfolio failures route into ``blocking_section_ids`` so Phase 3 fails closed
  (exit 3) exactly like a weak/missing required topic;
- ``enhancement`` and ``baseline`` matrices are UNCHANGED (no portfolio fields),
  so Phase 3 stays backward-compatible.

No Gemini/Vertex/API/network.
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs.evidence.evidenced_coverage import (  # noqa: E402
    CODE_BLOCK_WEAK,
    CODE_PORTFOLIO_WEAK,
    evaluate_evidenced_coverage,
)
from wiki_generator.libs.evidence.options import EvidenceOptions  # noqa: E402


def _needs(**lanes):
    base = {"query_packs": [], "symbols": [], "files": [], "contracts": [],
            "tests": [], "graph_nodes": [], "search_hints": [], "context_artifacts": []}
    base.update(lanes)
    return base


def _ter(topic, source_fields, *, required=True, min_items=1, acceptable_lanes=None,
         catalog_topic_id=None, content_block_id=None):
    return {"topic": topic, "required": required, "source_fields": list(source_fields),
            "min_items": min_items,
            "acceptable_lanes": list(acceptable_lanes) if acceptable_lanes is not None
            else ["file_anchor", "symbol_anchor", "contract", "test", "query_pack"],
            "catalog_topic_id": catalog_topic_id, "content_block_id": content_block_id}


def _section(sid, *, profile=None, blocks=(), required_topics=(), ters=(),
             needs=None, role="source"):
    return {
        "section_id": sid, "section_role": role, "title": sid,
        "page_profile": profile,
        "required_content_blocks": [{"block_id": b} for b in blocks],
        "required_topics": list(required_topics),
        "topic_evidence_requirements": list(ters),
        "retrieval_needs": needs or _needs(),
    }


def _exact(source_field, lane, status, *, evidence_ids=()):
    ev = list(evidence_ids)
    return {"lane": lane, "source_field": source_field, "status": status,
            "candidate_count": len(ev), "kept_count": len(ev), "evidence_ids": ev}


def _packet(sid, *, exact_requests=()):
    return {"section_id": sid, "coverage": {"exact_requests": list(exact_requests)},
            "lane_summary": {}}


def _bundle(sections):
    return SimpleNamespace(section_order=[s["section_id"] for s in sections],
                           section_by_id={s["section_id"]: s for s in sections})


def _opts(mode="expanded"):
    return EvidenceOptions(bundle_root="/b", out_dir="/o", coverage_mode=mode)


def _evaluate(sections, packets, mode="expanded"):
    return evaluate_evidenced_coverage(_bundle(sections), packets, _opts(mode))


def _section_row(matrix, sid):
    return next(r for r in matrix["sections"] if r["section_id"] == sid)


# ===========================================================================
class PortfolioTests(unittest.TestCase):
    def test_portfolio_sufficient_with_floor_handle(self):
        sec = _section(
            "ops", profile="operations-page", blocks=["operations"],
            required_topics=["x"], needs=_needs(files=[{"path": "ops/run.py"}]),
            ters=[_ter("x", ["retrieval_needs.files[0]"],
                       content_block_id="operations")])
        pkt = _packet("ops", exact_requests=[
            _exact("retrieval_needs.files[0]", "file_anchor", "covered",
                   evidence_ids=["ev:ops:0001"])])
        ec = _evaluate([sec], [pkt])
        self.assertFalse(ec.has_blocking, ec.blocking_diagnostics)
        row = _section_row(ec.matrix, "ops")
        self.assertEqual(row["page_profile"], "operations-page")
        self.assertEqual(row["portfolio_status"], "sufficient")
        self.assertEqual(row["status"], "pass")

    def test_topic_sufficient_but_portfolio_off_floor_blocks(self):
        # api-reference floor is (contract, file_anchor, symbol_anchor); the only
        # covered lane is query_pack -> the required topic is sufficient but the page
        # portfolio is weak -> a distinct block beyond per-topic sufficiency.
        sec = _section(
            "api", profile="api-reference", blocks=["route_matrix"],
            required_topics=["r"], needs=_needs(query_packs=["web_routes"]),
            ters=[_ter("r", ["retrieval_needs.query_packs[0]"],
                       acceptable_lanes=["query_pack"], content_block_id="route_matrix")])
        pkt = _packet("api", exact_requests=[
            _exact("retrieval_needs.query_packs[0]", "query_pack", "covered",
                   evidence_ids=["ev:api:0001"])])
        ec = _evaluate([sec], [pkt])
        # the topic itself is sufficient...
        row = _section_row(ec.matrix, "api")
        topic = row["topics"][0]
        self.assertEqual(topic["status"], "sufficient")
        # ...but the page portfolio is weak and blocks.
        self.assertTrue(ec.has_blocking)
        self.assertEqual(row["portfolio_status"], "weak")
        self.assertEqual(row["status"], "fail")
        self.assertTrue(any(CODE_PORTFOLIO_WEAK in d for d in ec.blocking_diagnostics))
        self.assertIn("api", ec.blocking_section_ids)

    def test_min_exact_items_floor(self):
        # data-model-reference requires min_exact_items=2; only 1 floor handle -> weak.
        sec = _section(
            "dm", profile="data-model-reference", blocks=["data_models"],
            required_topics=["m"], needs=_needs(symbols=[{"symbol_id": "S"}]),
            ters=[_ter("m", ["retrieval_needs.symbols[0]"],
                       content_block_id="data_models")])
        pkt = _packet("dm", exact_requests=[
            _exact("retrieval_needs.symbols[0]", "symbol_anchor", "covered",
                   evidence_ids=["ev:dm:0001"])])
        ec = _evaluate([sec], [pkt])
        row = _section_row(ec.matrix, "dm")
        self.assertEqual(row["portfolio_status"], "weak")
        self.assertTrue(ec.has_blocking)

    def test_content_block_insufficient_blocks(self):
        # the flow block is TER-linked but its topic produced no exact evidence.
        sec = _section(
            "sub", profile="subsystem-deep-dive",
            blocks=["purpose", "entrypoints", "flow", "key_files", "tests"],
            required_topics=["flow topic"],
            needs=_needs(files=[{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}],
                         query_packs=["q"]),
            ters=[_ter("flow topic", ["retrieval_needs.query_packs[0]"],
                       acceptable_lanes=["query_pack"], content_block_id="flow")])
        # file lanes cover the floor (3 ids) so the page floor is satisfied, but the
        # flow block's only topic maps to a query_pack that returned no hits.
        pkt = _packet("sub", exact_requests=[
            _exact("retrieval_needs.files[0]", "file_anchor", "covered",
                   evidence_ids=["ev:sub:0001"]),
            _exact("retrieval_needs.files[1]", "file_anchor", "covered",
                   evidence_ids=["ev:sub:0002"]),
            _exact("retrieval_needs.files[2]", "file_anchor", "covered",
                   evidence_ids=["ev:sub:0003"]),
            _exact("retrieval_needs.query_packs[0]", "query_pack", "no_hits")])
        ec = _evaluate([sec], [pkt])
        row = _section_row(ec.matrix, "sub")
        self.assertEqual(row["portfolio_status"], "sufficient")   # floor met by files
        self.assertTrue(ec.has_blocking)                          # but a block is weak
        self.assertTrue(any(CODE_BLOCK_WEAK in d for d in ec.blocking_diagnostics))
        block = next(b for b in row["content_blocks"]
                     if b["content_block_id"] == "flow")
        self.assertNotEqual(block["status"], "sufficient")

    def test_glossary_profile_not_applicable(self):
        sec = _section("g", profile="glossary", blocks=["term"],
                       required_topics=[], needs=_needs())
        ec = _evaluate([sec], [_packet("g")])
        row = _section_row(ec.matrix, "g")
        self.assertEqual(row["portfolio_status"], "not_applicable")
        self.assertFalse(ec.has_blocking)

    def test_expanded_adds_linkage_fields(self):
        sec = _section(
            "ops", profile="operations-page", blocks=["operations"],
            required_topics=["x"], needs=_needs(files=[{"path": "ops/run.py"}]),
            ters=[_ter("x", ["retrieval_needs.files[0]"],
                       catalog_topic_id="ops.run", content_block_id="operations")])
        pkt = _packet("ops", exact_requests=[
            _exact("retrieval_needs.files[0]", "file_anchor", "covered",
                   evidence_ids=["ev:ops:0001"])])
        row = _section_row(_evaluate([sec], [pkt]).matrix, "ops")
        topic = row["topics"][0]
        self.assertEqual(topic["catalog_topic_id"], "ops.run")
        self.assertEqual(topic["content_block_id"], "operations")
        self.assertIn("portfolio_requirements", row)


class BackwardCompatTests(unittest.TestCase):
    def _sec_pkt(self):
        sec = _section(
            "ops", profile="operations-page", blocks=["operations"],
            required_topics=["x"], needs=_needs(files=[{"path": "ops/run.py"}]),
            ters=[_ter("x", ["retrieval_needs.files[0]"],
                       content_block_id="operations")])
        pkt = _packet("ops", exact_requests=[
            _exact("retrieval_needs.files[0]", "file_anchor", "covered",
                   evidence_ids=["ev:ops:0001"])])
        return sec, pkt

    def test_enhancement_has_no_portfolio_fields(self):
        sec, pkt = self._sec_pkt()
        row = _section_row(_evaluate([sec], [pkt], mode="enhancement").matrix, "ops")
        self.assertNotIn("page_profile", row)
        self.assertNotIn("portfolio_status", row)
        self.assertNotIn("catalog_topic_id", row["topics"][0])

    def test_baseline_never_gates_and_no_portfolio(self):
        # a page that would fail the portfolio floor in expanded mode...
        sec = _section(
            "api", profile="api-reference", required_topics=["r"],
            needs=_needs(query_packs=["q"]),
            ters=[_ter("r", ["retrieval_needs.query_packs[0]"],
                       acceptable_lanes=["query_pack"])])
        pkt = _packet("api", exact_requests=[
            _exact("retrieval_needs.query_packs[0]", "query_pack", "covered",
                   evidence_ids=["ev:api:0001"])])
        ec = _evaluate([sec], [pkt], mode="baseline")
        self.assertFalse(ec.enforced)
        self.assertFalse(ec.has_blocking)
        self.assertNotIn("portfolio_status", _section_row(ec.matrix, "api"))


if __name__ == "__main__":
    unittest.main()
