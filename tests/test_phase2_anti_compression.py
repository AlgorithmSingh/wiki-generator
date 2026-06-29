"""Next phase — DeepWiki scale-parity anti-compression gate (deepwiki-scale mode).

Deterministic, LLM-free, network-free tests for the new Phase 2 anti-compression
contract that closes the loophole proven by the real RAGFlow run (a 94-``must`` /
13-family catalog collapsed into 21 flat pages / 42 TERs because "catalog id listed on
a page" counted as planning coverage):

- the source-derived promotion contract assigns each catalog topic a tier
  (page / overview / optional / known_gap);
- ``deepwiki-scale`` fails closed when a promoted leaf topic has no own non-overview
  leaf page, has no own TER, when a leaf page is overloaded, when a large family is not
  split into child pages, when the plan is wholly flat, or when the leaf-page count is
  below the catalog-derived breadth floor;
- an overview/index page may list promoted ids only as navigation — it never satisfies
  a leaf obligation (a topic only on the overview page fails);
- a fanned-out plan (each promoted leaf topic on its own <=cap leaf page with a TER)
  passes;
- ``baseline``/``enhancement``/``expanded`` are report-only here (opt-in isolation);
- the integrated ``normalize-plan --coverage-mode deepwiki-scale`` runs the gate, writes
  its artifacts, passes a non-compressed plan, and fails a compressed one (exit 3),
  while ``expanded``/``enhancement`` never run it.

No Gemini/Vertex/API/network; no real Phase 1/3/4 pipeline run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
sys.path.insert(0, TESTS)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.coverage import anti_compression as ac  # noqa: E402
from wiki_generator.libs.commands import normalize_plan as normalize_plan_cmd  # noqa: E402
from wiki_generator.libs.evidence.options import EvidenceOptions  # noqa: E402
from wiki_generator.libs.writing.options import WritingOptions  # noqa: E402

# Reuse the existing expanded integration fixtures (a complete plan that passes every
# expanded gate over a real bundle) for the wiring tests.
import test_phase2_topic_catalog_planning as base  # noqa: E402


# --- inline builders (unit tests) --------------------------------------------
def _topic(tid, *, kind="subsystem", priority="must", strength="high",
           family=None, status="present"):
    fam = family or (tid.split(".")[0] if "." in tid else tid)
    return {"topic_id": tid,
            "parent_topic_id": fam if (kind != "family" and fam != tid) else None,
            "family": fam, "label": tid, "topic_kind": kind,
            "suggested_page_profile": "subsystem-deep-dive", "status": status,
            "signal_strength": strength, "priority": priority}


def _catalog(*topics, fingerprint="sha256:acfp"):
    return {"schema_version": "deepwiki-topic-catalog-v1", "role": "planner_context",
            "citeable_as_evidence": False, "source_fingerprint": fingerprint,
            "topics": list(topics)}


def _ter(tid):
    return {"topic": tid, "required": True, "catalog_topic_id": tid,
            "source_fields": ["retrieval_needs.files[0]"], "min_items": 1,
            "acceptable_lanes": ["file_anchor"]}


def _sec(sid, *, profile="subsystem-deep-dive", catalog_ids=(), parent=None,
         ters=(), role="source", known_gaps=()):
    """A normalized section dict in the exact shape the anti-compression gate reads."""
    return {"section_id": sid, "section_role": role, "title": sid,
            "page_profile": profile, "parent_section_id": parent,
            "catalog_topic_ids": list(catalog_ids), "required_content_blocks": [],
            "required_topics": [], "topic_evidence_requirements": list(ters),
            "known_gaps": list(known_gaps), "retrieval_needs": {}}


def _family_catalog(family, n, *, priority="must", strength="high"):
    """A family topic plus ``n`` high-signal subsystem (leaf) topics under it."""
    subs = [f"{family}.s{i}" for i in range(1, n + 1)]
    topics = [_topic(family, kind="family", priority=priority, strength=strength)]
    topics += [_topic(s, kind="subsystem", priority=priority, strength=strength,
                      family=family) for s in subs]
    return _catalog(*topics), subs


def _fanned_sections(family, subs, *, per_page=4):
    """Each promoted leaf topic on its own <=cap leaf page (with a TER), linked to an
    overview parent page. The non-compressed shape the gate must accept."""
    sections = [_sec("overview", profile="overview")]
    for start in range(0, len(subs), per_page):
        chunk = subs[start:start + per_page]
        sid = f"{family}-{start // per_page}"
        sections.append(_sec(sid, catalog_ids=chunk, parent="overview",
                             ters=[_ter(t) for t in chunk]))
    return sections


# ===========================================================================
class PromotionContractTests(unittest.TestCase):
    """The source-derived promotion contract assigns the correct tier per topic."""

    def test_family_must_is_overview_tier(self):
        self.assertEqual(ac.classify_promotion(_topic("f", kind="family"), False),
                         ac.TIER_OVERVIEW)

    def test_subsystem_must_is_page_tier(self):
        self.assertEqual(ac.classify_promotion(_topic("f.s1", kind="subsystem"), False),
                         ac.TIER_PAGE)

    def test_should_is_optional_tier(self):
        self.assertEqual(
            ac.classify_promotion(_topic("f.s1", kind="subsystem", priority="should"),
                                  False),
            ac.TIER_OPTIONAL)

    def test_deferred_is_known_gap_tier(self):
        self.assertEqual(ac.classify_promotion(_topic("f.s1", kind="subsystem"), True),
                         ac.TIER_KNOWN_GAP)

    def test_promoted_topics_contract_emitted(self):
        catalog, subs = _family_catalog("frontend", 5)
        secs = _fanned_sections("frontend", subs, per_page=4)
        rep = ac.evaluate_anti_compression(catalog, None, secs,
                                           mode=cov.MODE_DEEPWIKI_SCALE)
        tiers = {r.topic_id: r.tier for r in rep.promoted_topics}
        self.assertEqual(tiers["frontend"], ac.TIER_OVERVIEW)
        self.assertEqual(tiers["frontend.s1"], ac.TIER_PAGE)
        # the contract row carries the downstream fields.
        row = next(r for r in rep.promoted_topics if r.topic_id == "frontend.s1")
        self.assertTrue(row.has_ter)
        self.assertTrue(row.leaf_pages)


class AntiCompressionGateUnitTests(unittest.TestCase):
    """The deterministic deepwiki-scale anti-compression / breadth gate."""

    def test_fanned_plan_passes(self):
        catalog, subs = _family_catalog("frontend", 8)
        secs = _fanned_sections("frontend", subs, per_page=4)
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])
        self.assertEqual(g.exit_code, cov.COVERAGE_GATE_PASS_EXIT)
        self.assertFalse(g.report.diagnostics)

    def test_collapse_fails_with_multiple_codes(self):
        # the exact real-run shape: a 13-topic family on one leaf page, too few TERs.
        catalog, subs = _family_catalog("frontend", 12)
        collapse = [
            _sec("overview", profile="overview"),
            _sec("frontend", catalog_ids=["frontend"] + subs,
                 ters=[_ter(subs[0]), _ter(subs[1])]),   # only 2 of 12 TERs
        ]
        g = cov.gate_anti_compression(catalog, None, collapse,
                                      mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        self.assertEqual(g.exit_code, cov.COVERAGE_GATE_FAIL_EXIT)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_LEAF_PAGE_OVERLOADED, codes)
        self.assertIn(ac.CODE_TOPIC_NO_TER, codes)
        self.assertIn(ac.CODE_FAMILY_NOT_SPLIT, codes)
        self.assertEqual(g.report.failure_category, ac.FAILURE_CATEGORY)

    def test_overloaded_leaf_fails(self):
        catalog, subs = _family_catalog("frontend", 5)   # 5 > cap 4, <= split 6
        secs = [_sec("overview", profile="overview"),
                _sec("frontend", catalog_ids=subs, ters=[_ter(t) for t in subs])]
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_LEAF_PAGE_OVERLOADED, codes)

    def test_missing_ter_fails(self):
        # each promoted topic on its own leaf page (so no overload / floor defect), but
        # without a TER -> distributive TER obligation fails.
        catalog, subs = _family_catalog("frontend", 3)
        secs = [_sec("overview", profile="overview")]
        for i, t in enumerate(subs):
            secs.append(_sec(f"frontend-{i}", catalog_ids=[t], parent="overview"))
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_TOPIC_NO_TER, codes)

    def test_topic_only_on_overview_fails(self):
        # the overview page lists the topic id, but no leaf page does -> no leaf page.
        catalog, subs = _family_catalog("frontend", 2)
        secs = [
            _sec("overview", profile="overview", catalog_ids=subs,
                 ters=[_ter(t) for t in subs]),     # overview carries id + TER...
            _sec("frontend-0", catalog_ids=[subs[0]], parent="overview",
                 ters=[_ter(subs[0])]),             # ...but only s1 has a leaf page
        ]
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes_for = {(d["id"], d["code"]) for d in g.report.diagnostics}
        self.assertIn((subs[1], ac.CODE_TOPIC_NO_LEAF_PAGE), codes_for)
        # s1 is on its own leaf page, so it is NOT flagged for a missing leaf page.
        self.assertNotIn((subs[0], ac.CODE_TOPIC_NO_LEAF_PAGE), codes_for)

    def test_large_family_not_split_fails(self):
        catalog, subs = _family_catalog("frontend", 8)   # 8 > split 6
        # all 8 on a single leaf page -> family not split (and overloaded), but give
        # every topic a TER and enough breadth so the *split* code is exercised.
        secs = [_sec("overview", profile="overview"),
                _sec("frontend", catalog_ids=subs, ters=[_ter(t) for t in subs])]
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_FAMILY_NOT_SPLIT, codes)
        fam = next(f for f in g.report.families if f.family == "frontend")
        self.assertEqual(fam.promoted_leaf_count, 8)
        self.assertEqual(fam.required_leaf_pages, 2)
        self.assertEqual(fam.actual_leaf_pages, 1)

    def test_flat_hierarchy_fails(self):
        # three families, each fanned within density, every topic with a TER and its own
        # leaf page, but NO resolving parent_section_id anywhere -> flat plan.
        topics = []
        sections = [_sec("overview", profile="overview")]
        for fam in ("frontend", "memory", "queue"):
            topics.append(_topic(fam, kind="family"))
            for i in range(1, 4):
                tid = f"{fam}.s{i}"
                topics.append(_topic(tid, kind="subsystem", family=fam))
                sections.append(_sec(f"{fam}-{i}", catalog_ids=[tid], ters=[_ter(tid)]))
        catalog = _catalog(*topics)
        g = cov.gate_anti_compression(catalog, None, sections,
                                      mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_FLAT_HIERARCHY, codes)
        self.assertTrue(g.report.flat_hierarchy)

    def test_breadth_floor_fails(self):
        # 6 promoted leaf topics (<= split 6, so no family-not-split), but crammed so
        # there are fewer leaf pages than the catalog floor ceil(6/4)=2... use 2 pages
        # each holding 3 (<= cap 4) but only spread across pages below the floor would
        # need >2; instead put all on ONE page is overloaded. To isolate the floor:
        # 5 topics across 2 leaf pages is >= floor ceil(5/4)=2 (passes); 5 on 1 page is
        # overloaded. So exercise the floor with 8 topics on 2 pages of 4 (floor 2, ok)
        # vs the failing shape: 8 topics where only 1 leaf page exists is overloaded.
        # The cleanest pure-floor failure: many single-topic leaf pages removed. Build
        # 5 topics, each on its own leaf page (5 pages >= floor 2) -> passes; then
        # collapse to 1 page (overloaded). The floor code is therefore exercised via the
        # collapse case; here we assert the floor number is computed and reported.
        catalog, subs = _family_catalog("frontend", 5)
        collapse = [_sec("overview", profile="overview"),
                    _sec("frontend", catalog_ids=subs, ters=[_ter(t) for t in subs])]
        g = cov.gate_anti_compression(catalog, None, collapse,
                                      mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(ac.CODE_INSUFFICIENT_BREADTH, codes)
        self.assertEqual(g.report.required_leaf_pages, 2)   # ceil(5/4)
        self.assertEqual(g.report.actual_leaf_pages, 1)

    def test_deferred_topics_not_blocking(self):
        catalog, subs = _family_catalog("frontend", 8)
        # defer every subsystem topic via a source-derived known_gaps[] entry naming it.
        secs = [_sec("overview", profile="overview",
                     known_gaps=[f"{t}: no source in this repo snapshot" for t in subs])]
        g = cov.gate_anti_compression(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])
        tiers = {r.topic_id: r.tier for r in g.report.promoted_topics}
        self.assertEqual(tiers[subs[0]], ac.TIER_KNOWN_GAP)

    def test_overview_index_with_leaf_pages_passes(self):
        # an overview/index page that lists many promoted ids passes WHEN each topic
        # also has its own non-overview leaf page + TER (the allowed exception).
        catalog, subs = _family_catalog("frontend", 6)
        sections = [_sec("overview", profile="overview", catalog_ids=subs)]
        for i, t in enumerate(subs):
            sections.append(_sec(f"frontend-{i}", catalog_ids=[t], parent="overview",
                                 ters=[_ter(t)]))
        g = cov.gate_anti_compression(catalog, None, sections,
                                      mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])

    def test_baseline_reports_but_never_gates(self):
        catalog, subs = _family_catalog("frontend", 12)
        collapse = [_sec("overview", profile="overview"),
                    _sec("frontend", catalog_ids=["frontend"] + subs)]
        g = cov.gate_anti_compression(catalog, None, collapse, mode=cov.MODE_BASELINE)
        self.assertTrue(g.passed)              # report-only
        self.assertFalse(g.report.enforced)
        self.assertTrue(g.report.diagnostics)  # still computed/reported

    def test_expanded_is_report_only(self):
        catalog, subs = _family_catalog("frontend", 12)
        collapse = [_sec("overview", profile="overview"),
                    _sec("frontend", catalog_ids=["frontend"] + subs)]
        g = cov.gate_anti_compression(catalog, None, collapse, mode=cov.MODE_EXPANDED)
        self.assertTrue(g.passed)
        self.assertFalse(g.report.enforced)

    def test_no_catalog_is_graceful(self):
        g = cov.gate_anti_compression(None, None, [_sec("a")],
                                      mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertTrue(g.passed)
        self.assertFalse(g.report.catalog_present)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            ac.evaluate_anti_compression(_catalog(), None, [], mode="nope")

    def test_determinism(self):
        catalog, subs = _family_catalog("frontend", 9)
        secs = _fanned_sections("frontend", subs, per_page=4)
        a = ac.evaluate_anti_compression(catalog, None, secs,
                                         mode=cov.MODE_DEEPWIKI_SCALE).to_dict()
        b = ac.evaluate_anti_compression(catalog, None, secs,
                                         mode=cov.MODE_DEEPWIKI_SCALE).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_policy_is_injectable(self):
        # a stricter cap turns a 3-on-one-page plan (default-passing) into a failure.
        catalog, subs = _family_catalog("frontend", 3)
        secs = [_sec("overview", profile="overview"),
                _sec("frontend", catalog_ids=subs, ters=[_ter(t) for t in subs])]
        ok = cov.gate_anti_compression(catalog, None, secs,
                                       mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertTrue(ok.passed, [d for d in ok.report.diagnostics])
        strict = ac.BreadthPolicy(max_promoted_topics_per_leaf_page=2,
                                  family_split_threshold=2)
        bad = cov.gate_anti_compression(catalog, None, secs,
                                        mode=cov.MODE_DEEPWIKI_SCALE, policy=strict)
        self.assertFalse(bad.passed)


class ModeWiringTests(unittest.TestCase):
    """deepwiki-scale is a strict superset of expanded and is accepted everywhere."""

    def test_deepwiki_scale_enforces_expanded_page_planning(self):
        # a defective page (missing profile) must still fail page-planning in
        # deepwiki-scale (proving the superset enforces the expanded gates too).
        catalog = base._catalog(base._topic("doc-processing", priority="must"))
        secs = [base._norm_section("a", profile=None)]
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_DEEPWIKI_SCALE)
        self.assertFalse(g.passed)
        self.assertTrue(cov.is_enforcing(cov.MODE_DEEPWIKI_SCALE))
        self.assertTrue(cov.is_expanded_family(cov.MODE_DEEPWIKI_SCALE))
        self.assertFalse(cov.enforces_breadth(cov.MODE_EXPANDED))
        self.assertTrue(cov.enforces_breadth(cov.MODE_DEEPWIKI_SCALE))

    def test_evidence_and_writing_options_accept_mode(self):
        eo = EvidenceOptions(bundle_root="/tmp/b", out_dir="/tmp/o",
                             coverage_mode="deepwiki-scale")
        self.assertEqual(eo.coverage_mode, "deepwiki-scale")
        wo = WritingOptions(bundle_root="/tmp/b", out_dir="/tmp/o",
                            coverage_mode="deepwiki-scale")
        self.assertTrue(wo.is_expanded)            # superset of expanded
        self.assertTrue(wo.enforces_coverage)


# ===========================================================================
class IntegratedDeepwikiScaleTests(unittest.TestCase):
    """``normalize-plan --coverage-mode deepwiki-scale`` end to end over a real bundle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="deepwiki_scale_cmd_")
        self.bundle = os.path.join(self.tmp, "bundle")
        self.plans = os.path.join(self.bundle, "plans")
        inv = os.path.join(self.bundle, "inventory")
        os.makedirs(inv)
        with open(os.path.join(inv, "files.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"path": base._TOPIC_FILE, "line_count": 200}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_catalog(self, catalog):
        derived = os.path.join(self.bundle, "derived")
        os.makedirs(derived, exist_ok=True)
        util.write_json(os.path.join(derived, "topic-catalog.json"), catalog)

    def _write_raw(self, rows) -> str:
        p = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(base._raw_response(rows))
        return p

    def _args(self, raw, mode="deepwiki-scale"):
        return SimpleNamespace(bundle=self.bundle, raw_response=raw, out_dir=None,
                               strict=False, provider="test", coverage_mode=mode)

    def _scale_fail_rows(self, subs):
        """The complete expanded plan, but with the doc-pipeline leaf page compressed:
        it now lists the whole doc-processing family's subsystem topics on one page."""
        rows = []
        for meta, plan in base._EFULL:
            if meta["id"] == "doc-pipeline":
                rows.append(base._esec(
                    "doc-pipeline", "Document Processing Pipeline",
                    "subsystem-deep-dive", labels=["doc-processing"],
                    topics=["deepdoc parser factory, ocr and chunking strategy"],
                    parent="subsystems", catalog_ids=["doc-processing"] + subs))
            else:
                rows.append((meta, plan))
        return rows

    def test_passes_when_catalog_has_no_promoted_leaf(self):
        # _EFULL_CATALOG's must topics are family-level only -> no promoted leaf topics,
        # so the anti-compression gate passes; this proves the gate RAN and is wired.
        self._write_catalog(base._EFULL_CATALOG)
        rc = normalize_plan_cmd.run(self._args(self._write_raw(base._EFULL)))
        self.assertEqual(rc, 0)
        path = os.path.join(self.plans, "anti-compression-gate.json")
        self.assertTrue(os.path.isfile(path))
        gate = util.read_json(path)
        self.assertTrue(gate["passed"], gate["report"]["diagnostics"])
        self.assertEqual(gate["report"]["mode"], "deepwiki-scale")

    def test_fails_on_compressed_family(self):
        subs = [f"doc-processing.s{i}" for i in range(1, 8)]   # 7 promoted leaves
        catalog = base._catalog(
            base._topic("retrieval-internals", priority="must"),
            base._topic("doc-processing", priority="must"),
            *[base._topic(s, priority="must", kind="subsystem", parent="doc-processing")
              for s in subs],
            base._topic("memory", priority="should", strength="low", status="low"))
        self._write_catalog(catalog)
        rc = normalize_plan_cmd.run(self._args(self._write_raw(self._scale_fail_rows(subs))))
        self.assertEqual(rc, cov.COVERAGE_GATE_FAIL_EXIT)
        gate = util.read_json(os.path.join(self.plans, "anti-compression-gate.json"))
        self.assertFalse(gate["passed"])
        codes = {d["code"] for d in gate["report"]["diagnostics"]}
        self.assertIn(ac.CODE_FAMILY_NOT_SPLIT, codes)
        # the prior expanded gates still passed (the failure is anti-compression).
        pp = util.read_json(os.path.join(self.plans, "page-planning-gate.json"))
        self.assertTrue(pp["passed"], pp["report"]["diagnostics"])

    def test_expanded_does_not_run_anti_compression(self):
        self._write_catalog(base._EFULL_CATALOG)
        rc = normalize_plan_cmd.run(
            self._args(self._write_raw(base._EFULL), mode="expanded"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.isfile(
            os.path.join(self.plans, "anti-compression-gate.json")))
        # expanded still writes its own gates.
        self.assertTrue(os.path.isfile(
            os.path.join(self.plans, "page-planning-gate.json")))

    def test_enhancement_does_not_run_anti_compression(self):
        self._write_catalog(base._EFULL_CATALOG)
        rc = normalize_plan_cmd.run(
            self._args(self._write_raw(base._EFULL), mode="enhancement"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.isfile(
            os.path.join(self.plans, "anti-compression-gate.json")))


if __name__ == "__main__":
    unittest.main()
