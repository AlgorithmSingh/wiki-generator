"""Core DeepWiki-scale behaviour: expanded is the scale path, not an opt-in product.

Deterministic, LLM-free, network-free tests for the core-scale-fanout slice:

- ``expanded`` is now the core DeepWiki-scale path: it enforces the anti-compression
  breadth gate by default, and ``deepwiki-scale`` is a behaviour-identical alias;
- the source-derived **breadth budget** (page / required-topic targets, per-family
  fan-out floor) is computed only from the catalog and rendered into the planner-facing
  ``planning-topic-catalog.md`` so the planner is told the breadth to fan out to;
- the embedded planner prompts and the Gemini-Gem prompt files instruct a fanned-out
  hierarchy (parent/index vs leaf pages, one TER per promoted catalog topic, no broad
  page claiming leaf coverage by listing ids);
- the Phase 2 anti-compression gate emits a downstream ``promoted-topic-contract.json``
  data contract, and Phase 4 carries promoted ``catalog_topic_id`` granularity into the
  generated-coverage obligations/rows so a promoted topic missing from generated output
  fails once it has evidence.

No Gemini/Vertex/API/network; no real Phase 1/3/4 pipeline run.
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs.coverage import anti_compression as ac  # noqa: E402
from wiki_generator.libs.coverage import topic_catalog as tc  # noqa: E402
from wiki_generator.libs.commands import plan as plan_cmd  # noqa: E402
from wiki_generator.libs.writing import generated_coverage as gc  # noqa: E402


# --- catalog builders (plain dicts, the shape the gate/budget read) -----------
def _topic(tid, *, kind="subsystem", priority="must", strength="high", family=None):
    fam = family or (tid.split(".")[0] if "." in tid else tid)
    return {"topic_id": tid, "parent_topic_id": fam if kind != "family" else None,
            "family": fam, "label": tid, "topic_kind": kind,
            "suggested_page_profile": "subsystem-deep-dive", "status": "present",
            "signal_strength": strength, "priority": priority}


def _catalog(*topics):
    return {"schema_version": "deepwiki-topic-catalog-v1", "role": "planner_context",
            "citeable_as_evidence": False, "source_fingerprint": "sha256:fp",
            "topics": list(topics)}


def _family_catalog(family, n, **kw):
    topics = [_topic(family, kind="family", **kw)]
    topics += [_topic(f"{family}.s{i}", kind="subsystem", family=family, **kw)
               for i in range(1, n + 1)]
    return topics


# ===========================================================================
class BreadthBudgetTests(unittest.TestCase):
    """The source-derived breadth budget mirrors the gate's promotion logic."""

    def test_budget_counts_and_targets(self):
        # frontend: 12 leaves, doc-processing: 6 leaves, plus a should family (ignored).
        catalog = _catalog(
            *_family_catalog("frontend", 12),
            *_family_catalog("doc-processing", 6),
            _topic("memory", kind="family", priority="should", strength="low"),
            _topic("memory.cache", kind="subsystem", family="memory",
                   priority="should", strength="low"))
        b = ac.derive_breadth_budget(catalog)
        self.assertEqual(b.promoted_leaf_count, 18)            # 12 + 6
        self.assertEqual(b.families_with_promoted, 2)
        # min leaf pages = ceil(12/4) + ceil(6/4) = 3 + 2 = 5.
        self.assertEqual(b.min_leaf_pages, 5)
        self.assertEqual(b.max_leaf_pages, 18)                 # one page per leaf
        # one top index + one per fanned family = 3 overview pages.
        self.assertEqual(b.min_overview_pages, 3)
        self.assertEqual(b.min_total_pages, 8)                 # 3 + 5
        self.assertEqual(b.max_total_pages, 21)                # 3 + 18
        # one required topic per promoted leaf + one per fanned family overview.
        self.assertEqual(b.min_required_topics, 20)            # 18 + 2
        fam = {f.family: f for f in b.families}
        self.assertEqual(fam["frontend"].min_leaf_pages, 3)
        self.assertEqual(fam["doc-processing"].min_leaf_pages, 2)

    def test_budget_empty_catalog(self):
        b = ac.derive_breadth_budget(None)
        self.assertFalse(b.catalog_present)
        self.assertEqual(b.promoted_leaf_count, 0)
        self.assertEqual(ac.render_breadth_budget_lines(b), [])

    def test_budget_uses_injected_policy(self):
        catalog = _catalog(*_family_catalog("frontend", 8))
        strict = ac.BreadthPolicy(max_promoted_topics_per_leaf_page=2)
        b = ac.derive_breadth_budget(catalog, policy=strict)
        self.assertEqual(b.min_leaf_pages, 4)                  # ceil(8/2)

    def test_budget_lines_state_targets(self):
        catalog = _catalog(*_family_catalog("frontend", 12))
        lines = "\n".join(ac.render_breadth_budget_lines(ac.derive_breadth_budget(catalog)))
        self.assertIn("Source-derived breadth budget", lines)
        self.assertIn("never from any benchmark", lines)
        self.assertIn("promoted leaf", lines)
        self.assertIn("one required topic", lines.lower())


class CatalogMarkdownBudgetTests(unittest.TestCase):
    """planning-topic-catalog.md carries the breadth budget for the planner."""

    def _catalog_obj(self):
        topics = [tc.CatalogTopic(
            topic_id="frontend", parent_topic_id=None, family="frontend",
            label="Frontend", topic_kind=tc.TOPIC_KIND_FAMILY,
            suggested_page_profile="subsystem-deep-dive", status=tc.STATUS_PRESENT,
            signal_strength="high", priority="must")]
        for i in range(1, 9):
            topics.append(tc.CatalogTopic(
                topic_id=f"frontend.s{i}", parent_topic_id="frontend",
                family="frontend", label=f"Frontend s{i}",
                topic_kind=tc.TOPIC_KIND_SUBSYSTEM,
                suggested_page_profile="subsystem-deep-dive",
                status=tc.STATUS_PRESENT, signal_strength="high", priority="must"))
        return tc.TopicCatalog(
            schema_version=tc.TOPIC_CATALOG_SCHEMA_VERSION,
            source_fingerprint="sha256:fp", repo_root="/x", topic_count=len(topics),
            family_count=1, subsystem_count=8, deferred_count=0,
            topics=tuple(topics))

    def test_render_includes_breadth_budget(self):
        md = tc.render_catalog_markdown(self._catalog_obj())
        self.assertIn("Source-derived breadth budget", md)
        self.assertIn("promoted leaf", md)
        # per-family fan-out floor table row for frontend (ceil(8/4) = 2).
        self.assertIn("`frontend`", md)


class PlannerPromptFanOutTests(unittest.TestCase):
    """The planner prompts instruct a fanned-out hierarchy (not just reject one)."""

    def test_embedded_system_prompt_has_fan_out_rules(self):
        s = plan_cmd._DEFAULT_SYSTEM.lower()
        self.assertIn("fan out", s)
        self.assertIn("breadth budget", s)
        self.assertIn("catalog_topic_id", s)
        self.assertIn("anti-compression", s)
        self.assertIn("parent_section_id", s)
        # the no-broad-page rule and the per-promoted-topic TER rule.
        self.assertIn("does not count", s)
        self.assertIn("topic_evidence_requirements", s)

    def test_embedded_kickoff_has_fan_out(self):
        k = plan_cmd._DEFAULT_KICKOFF.lower()
        self.assertIn("fan out", k)
        self.assertIn("breadth budget", k)
        self.assertIn("catalog_topic_id", k)

    def test_gemini_gem_files_have_fan_out_rule(self):
        gem = os.path.join(ROOT, "gemini-gem")
        for name in ("GEM_INSTRUCTIONS.md", "KICKOFF_PROMPT.md"):
            with open(os.path.join(gem, name), encoding="utf-8") as f:
                # collapse whitespace so line-wrapped phrases still match.
                text = " ".join(f.read().lower().split())
            self.assertIn("fan out", text, name)
            self.assertIn("breadth budget", text, name)
            self.assertIn("anti-compression", text, name)
            # the no-broad-page rule (markdown-bolds "not", so match the stable phrase).
            self.assertIn("a family's subsystem", text, name)


# ===========================================================================
class PromotedTopicContractTests(unittest.TestCase):
    """The Phase 2 anti-compression gate emits the downstream promoted-topic contract."""

    def _report(self, n=8, *, compressed=False):
        catalog = _catalog(*_family_catalog("frontend", n))
        if compressed:
            secs = [{"section_id": "overview", "page_profile": "overview",
                     "catalog_topic_ids": [], "topic_evidence_requirements": []},
                    {"section_id": "frontend", "page_profile": "subsystem-deep-dive",
                     "catalog_topic_ids": [f"frontend.s{i}" for i in range(1, n + 1)],
                     "topic_evidence_requirements": []}]
        else:
            secs = [{"section_id": "overview", "page_profile": "overview",
                     "catalog_topic_ids": [], "topic_evidence_requirements": []}]
            for i in range(1, n + 1):
                tid = f"frontend.s{i}"
                secs.append({
                    "section_id": f"frontend-{i}", "page_profile": "subsystem-deep-dive",
                    "parent_section_id": "overview", "catalog_topic_ids": [tid],
                    "topic_evidence_requirements": [
                        {"topic": tid, "required": True, "catalog_topic_id": tid,
                         "source_fields": ["retrieval_needs.files[0]"], "min_items": 1,
                         "acceptable_lanes": ["file_anchor"]}]})
        return ac.evaluate_anti_compression(catalog, None, secs,
                                            mode=cov.MODE_EXPANDED)

    def test_contract_shape_for_fanned_plan(self):
        contract = ac.build_promoted_topic_contract(self._report(8))
        self.assertEqual(contract["schema_version"],
                         "deepwiki-promoted-topic-contract-v1")
        self.assertEqual(contract["mode"], "expanded")
        self.assertTrue(contract["enforced"])
        ids = ac.promoted_catalog_topic_ids(contract)
        self.assertEqual(ids, {f"frontend.s{i}" for i in range(1, 9)})
        row = next(r for r in contract["promoted_topics"]
                   if r["catalog_topic_id"] == "frontend.s1")
        self.assertTrue(row["has_ter"])
        self.assertEqual(row["status"], ac.STATUS_COVERED)
        self.assertTrue(row["leaf_pages"])

    def test_contract_marks_uncovered_in_compressed_plan(self):
        contract = ac.build_promoted_topic_contract(self._report(8, compressed=True))
        # every promoted leaf is still listed, but with defects/uncovered status.
        self.assertEqual(len(contract["promoted_topics"]), 8)
        self.assertGreater(contract["counts"]["uncovered"], 0)

    def test_contract_round_trips_through_disk(self):
        import json
        import tempfile
        contract = ac.build_promoted_topic_contract(self._report(5))
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "promoted-topic-contract.json"), "w",
                      encoding="utf-8") as f:
                json.dump(contract, f)
            loaded = ac.load_promoted_topic_contract(d)
        self.assertEqual(ac.promoted_catalog_topic_ids(loaded),
                         {f"frontend.s{i}" for i in range(1, 6)})

    def test_load_absent_contract_is_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ac.load_promoted_topic_contract(d))


# ===========================================================================
class Phase4PromotedGranularityTests(unittest.TestCase):
    """Phase 4 carries the promoted catalog_topic_id and enforces it once evidenced."""

    def _evidenced_matrix(self):
        # one sufficient required topic carrying its promoted catalog_topic_id (the
        # additive field Phase 3 writes in expanded mode).
        return {
            "coverage_mode": "expanded",
            "sections": [{
                "section_id": "frontend-1",
                "topics": [{
                    "topic": "router setup and route table", "required": True,
                    "status": "sufficient", "mapped_evidence_ids": ["ev1"],
                    "min_items": 1, "source_categories": ["file_anchor"],
                    "catalog_topic_id": "frontend.router"}]}]}

    def test_obligations_carry_catalog_topic_id(self):
        obs = gc.build_topic_obligations(self._evidenced_matrix())
        self.assertEqual(obs["frontend-1"][0]["catalog_topic_id"], "frontend.router")
        self.assertTrue(obs["frontend-1"][0]["is_obligation"])

    def test_generated_rows_carry_catalog_topic_id(self):
        obs = gc.build_topic_obligations(self._evidenced_matrix())["frontend-1"]
        res = gc.evaluate_section_coverage(
            obligations=obs, covered_topics=[], markdown="",
            evidence_index={}, manifest_ids=set())
        row = res["rows"][0]
        self.assertEqual(row["catalog_topic_id"], "frontend.router")

    def test_promoted_topic_missing_from_output_fails(self):
        # a promoted catalog topic that is a sufficient obligation but is omitted from
        # the generated markdown is a generated-coverage failure (exit-5 path) — so the
        # granularity cannot regress to broad-topic-only acceptance once evidence exists.
        obs = gc.build_topic_obligations(self._evidenced_matrix())["frontend-1"]
        res = gc.evaluate_section_coverage(
            obligations=obs, covered_topics=[],          # writer omitted the topic
            markdown="# Frontend\n\nNo router content here.\n",
            evidence_index={}, manifest_ids=set())
        row = res["rows"][0]
        self.assertEqual(row["generated_status"], gc.GEN_OMITTED)
        self.assertEqual(row["catalog_topic_id"], "frontend.router")
        self.assertTrue(res["failures"])


if __name__ == "__main__":
    unittest.main()
