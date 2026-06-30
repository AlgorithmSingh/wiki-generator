"""Phase 4 source-derived depth-budget tests — deterministic, no live model.

Proves the depth/detail-density quality contract that closes the "fanned-out but shallow"
gap: the previous phase enforced breadth (every required topic is *present*); this enforces
depth (every required topic grounds enough claims for the evidence Phase 3 mapped to it).

- ``depth_budget.DepthPolicy`` validates its bounds and clamps the per-topic target.
- ``derive_section_depth_budget`` derives the per-topic target ONLY from mapped-evidence
  density (one mapped evidence id => one claim target), so a 1-evidence topic stays
  satisfiable with a single claim (no padding) and the budget is byte-identical on rerun.
- ``evaluate_plan_depth`` / ``claim_plan.validate_claim_plan(depth_budget=...)`` fail a
  shallow plan (``required_topic_underfilled_for_mapped_evidence``) and pass a detailed one,
  run AFTER the grounding checks, and never mutate the plan; ``depth_budget=None`` is
  byte-identical to the pre-depth behaviour.
- The claim-plan prompt carries the per-topic targets and no benchmark string.
- The real expanded grounded command path records the depth audit and fails closed (exit 5)
  when a topic mapped to several evidence ids is grounded by a single claim — all without any
  Vertex/Gemini/API call (the gem response-import provider).
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
sys.path.insert(0, TESTS)

from wiki_generator.libs.writing import claim_plan as cp  # noqa: E402
from wiki_generator.libs.writing import depth_budget as depth  # noqa: E402
from wiki_generator.libs.writing import token_bank as tb  # noqa: E402
from wiki_generator.libs.writing.bundle import EvidenceItem  # noqa: E402
from wiki_generator.libs.writing.packet import WritingPacket  # noqa: E402
from wiki_generator.libs.writing.schema import CLAIM_PLAN_SCHEMA_VERSION  # noqa: E402


# --- tiny in-memory bundle (mirrors test_phase4_grounded) ---------------------
def ev(eid, sid, source, excerpt, conf="exact"):
    return EvidenceItem(evidence_id=eid, section_id=sid, lane="file_anchor",
                        type="source_span", confidence=conf, source=source,
                        excerpt=excerpt, provenance={}, scores={},
                        packet_path=f"evidence/packets/{sid}.json")


class FakeBundle:
    def __init__(self, items, coverage_mode="expanded"):
        self.evidence_index = {i.evidence_id: i for i in items}
        self.section_evidence_ids = {}
        for i in items:
            self.section_evidence_ids.setdefault(i.section_id, set()).add(i.evidence_id)
        self.coverage_mode = coverage_mode


def plan_obj(sid, claims):
    return {"schema_version": CLAIM_PLAN_SCHEMA_VERSION, "section_id": sid,
            "claims": claims}


def prose_claim(cid, eid, topic=None, block=None):
    c = {"claim_id": cid, "claim_kind": "prose", "evidence_ids": [eid],
         "token_ids": [], "required_topic": topic, "intent": "x",
         "skeleton": f"This component coordinates work described in claim {cid}."}
    if block is not None:
        c["content_block_id"] = block
    return c


def three_evidence_bundle():
    return FakeBundle([
        ev("ev:svc:0001", "svc", {"path": "pkg/a.py"}, "first source span\n"),
        ev("ev:svc:0002", "svc", {"path": "pkg/b.py"}, "second source span\n"),
        ev("ev:svc:0003", "svc", {"path": "pkg/c.py"}, "third source span\n"),
    ])


def validate_with_depth(plan, bundle, sid, obligations, budget):
    return cp.validate_claim_plan(
        plan, section_id=sid, token_bank=tb.build_token_bank(bundle, sid),
        allowed_evidence_ids=sorted(bundle.section_evidence_ids[sid]),
        evidence_index=bundle.evidence_index, obligations=obligations,
        depth_budget=budget)


# --- policy -------------------------------------------------------------------
class DepthPolicyTests(unittest.TestCase):
    def test_bounds_validated(self):
        for kwargs in ({"evidence_per_claim": 0},
                       {"min_claims_per_required_topic": 0},
                       {"max_claims_per_required_topic": 0},
                       {"min_section_claims": -1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    depth.DepthPolicy(**kwargs)

    def test_topic_target_clamps(self):
        p = depth.DepthPolicy(evidence_per_claim=1, min_claims_per_required_topic=1,
                              max_claims_per_required_topic=6)
        self.assertEqual(p.topic_target(0), 1)
        self.assertEqual(p.topic_target(1), 1)
        self.assertEqual(p.topic_target(4), 4)
        self.assertEqual(p.topic_target(99), 6)
        p2 = depth.DepthPolicy(evidence_per_claim=2, max_claims_per_required_topic=10)
        self.assertEqual(p2.topic_target(5), 3)   # ceil(5/2)


# --- derivation ---------------------------------------------------------------
class DeriveBudgetTests(unittest.TestCase):
    def _budget(self, mapped, *, blocks=None, policy=None):
        obligations = [{"topic": "T", "is_obligation": True,
                        "mapped_evidence_ids": list(mapped)}]
        return depth.derive_section_depth_budget(
            section_id="svc", obligations=obligations,
            content_block_obligations=blocks, allowed_evidence_ids=list(mapped),
            token_count=10, source_handle_count=2, policy=policy)

    def test_per_topic_target_from_mapped_evidence(self):
        b = self._budget(["e1", "e2", "e3"])
        self.assertEqual(b.topic_targets[0].mapped_evidence_count, 3)
        self.assertEqual(b.topic_targets[0].min_claims, 3)
        self.assertEqual(b.counts["required_topics"], 1)

    def test_single_mapped_evidence_target_is_one(self):
        b = self._budget(["e1"])
        self.assertEqual(b.topic_targets[0].min_claims, 1)
        self.assertEqual(b.min_section_claims, 1)

    def test_section_floor_is_sum_of_targets(self):
        obligations = [
            {"topic": "A", "is_obligation": True, "mapped_evidence_ids": ["e1", "e2"]},
            {"topic": "B", "is_obligation": True, "mapped_evidence_ids": ["e3", "e4", "e5"]},
            {"topic": "C", "is_obligation": False, "mapped_evidence_ids": ["e6"]},
        ]
        b = depth.derive_section_depth_budget(
            section_id="svc", obligations=obligations, content_block_obligations=None,
            allowed_evidence_ids=["e1", "e2", "e3", "e4", "e5"], token_count=5,
            source_handle_count=0)
        self.assertEqual(b.min_section_claims, 2 + 3)
        self.assertEqual([t.topic for t in b.topic_targets], ["A", "B"])  # sorted, only obligations

    def test_empty_obligations_no_pressure(self):
        b = depth.derive_section_depth_budget(
            section_id="overview", obligations=[], content_block_obligations=[],
            allowed_evidence_ids=["e1", "e2"], token_count=3, source_handle_count=0)
        self.assertEqual(b.topic_targets, [])
        self.assertEqual(b.min_section_claims, 1)  # policy floor only
        r = depth.evaluate_plan_depth(b, [{"required_topic": None}])
        self.assertEqual(r.status, "pass")

    def test_content_blocks_counted_but_not_gated(self):
        # content-block coverage is the downstream generated-coverage gate's job; the depth
        # budget records the count for context but never blocks on it.
        b = self._budget(["e1", "e2"], blocks=[{"content_block_id": "b1",
                                                "is_obligation": True,
                                                "supporting_evidence_ids": ["e1", "e2"]}])
        self.assertEqual(b.counts["content_blocks"], 1)
        self.assertFalse(hasattr(b, "content_block_targets"))

    def test_rerun_byte_identical(self):
        a1 = json.dumps(self._budget(["e1", "e2", "e3"]).to_dict(), sort_keys=True)
        a2 = json.dumps(self._budget(["e3", "e2", "e1"]).to_dict(), sort_keys=True)
        self.assertEqual(a1, a2)


# --- the gate -----------------------------------------------------------------
class DepthGateTests(unittest.TestCase):
    def setUp(self):
        self.b = three_evidence_bundle()
        self.obligations = [{"topic": "T", "is_obligation": True,
                             "mapped_evidence_ids": ["ev:svc:0001", "ev:svc:0002",
                                                     "ev:svc:0003"]}]
        self.budget = depth.derive_section_depth_budget(
            section_id="svc", obligations=self.obligations,
            content_block_obligations=None,
            allowed_evidence_ids=["ev:svc:0001", "ev:svc:0002", "ev:svc:0003"],
            token_count=0, source_handle_count=0)

    def test_shallow_plan_fails_topic_underfilled(self):
        plan = plan_obj("svc", [prose_claim("c1", "ev:svc:0001", topic="T")])
        r = validate_with_depth(plan, self.b, "svc", self.obligations, self.budget)
        self.assertFalse(r.ok)
        codes = {v["code"] for v in r.violations}
        self.assertIn(depth.CODE_TOPIC_UNDERFILLED, codes)

    def test_detailed_plan_passes(self):
        plan = plan_obj("svc", [
            prose_claim("c1", "ev:svc:0001", topic="T"),
            prose_claim("c2", "ev:svc:0002", topic="T"),
            prose_claim("c3", "ev:svc:0003", topic="T"),
        ])
        r = validate_with_depth(plan, self.b, "svc", self.obligations, self.budget)
        self.assertTrue(r.ok, r.problem_lines())

    def test_section_underfilled_backstop(self):
        budget = depth.SectionDepthBudget(
            schema_version=depth.DEPTH_BUDGET_SCHEMA_VERSION, section_id="svc",
            policy=depth.DEFAULT_DEPTH_POLICY.to_dict(),
            counts={}, min_section_claims=4, topic_targets=[])
        r = depth.evaluate_plan_depth(budget, [{"required_topic": None},
                                               {"required_topic": None}])
        self.assertEqual(r.status, "fail")
        self.assertIn(depth.CODE_SECTION_UNDERFILLED, {s.code for s in r.shortfalls})

    def test_content_block_omission_left_to_generated_coverage(self):
        # the depth gate does NOT fire on a missing content-block link (it has three
        # topic claims and no block linkage); content-block coverage is enforced
        # downstream by the generated-coverage gate, not duplicated here.
        budget = depth.derive_section_depth_budget(
            section_id="svc", obligations=self.obligations,
            content_block_obligations=[{"content_block_id": "b1", "is_obligation": True,
                                        "supporting_evidence_ids": ["ev:svc:0001"]}],
            allowed_evidence_ids=["ev:svc:0001", "ev:svc:0002", "ev:svc:0003"],
            token_count=0, source_handle_count=0)
        claims = [prose_claim(f"c{i}", e, topic="T") for i, e in enumerate(
            ["ev:svc:0001", "ev:svc:0002", "ev:svc:0003"], 1)]
        r = depth.evaluate_plan_depth(budget, claims)
        self.assertEqual(r.status, "pass")

    def test_none_budget_is_byte_identical(self):
        plan = plan_obj("svc", [prose_claim("c1", "ev:svc:0001", topic="T")])
        bank = tb.build_token_bank(self.b, "svc")
        kwargs = dict(section_id="svc", token_bank=bank,
                      allowed_evidence_ids=sorted(self.b.section_evidence_ids["svc"]),
                      evidence_index=self.b.evidence_index, obligations=self.obligations)
        without = cp.validate_claim_plan(plan, **kwargs)
        with_none = cp.validate_claim_plan(plan, depth_budget=None, **kwargs)
        self.assertEqual(without.ok, with_none.ok)
        self.assertEqual([v["code"] for v in without.violations],
                         [v["code"] for v in with_none.violations])
        # without depth, the single-claim plan is accepted (no shallow gate)
        self.assertTrue(without.ok, without.problem_lines())

    def test_grounding_violation_still_reported_with_depth(self):
        # a plan that is BOTH ungrounded (cites disallowed evidence) AND shallow: the
        # grounding violation must still be reported, not masked by the depth gate.
        bad = {"claim_id": "c1", "claim_kind": "prose",
               "evidence_ids": ["ev:other:0001"], "token_ids": [],
               "required_topic": "T", "intent": "x", "skeleton": "Ungrounded claim."}
        r = validate_with_depth(plan_obj("svc", [bad]), self.b, "svc",
                                self.obligations, self.budget)
        self.assertFalse(r.ok)
        codes = {v["code"] for v in r.violations}
        self.assertIn("evidence_not_allowed", codes)

    def test_depth_check_does_not_mutate_claims(self):
        claims = [{"required_topic": "T"}, {"required_topic": "T"}]
        before = json.dumps(claims, sort_keys=True)
        depth.evaluate_plan_depth(self.budget, claims)
        self.assertEqual(json.dumps(claims, sort_keys=True), before)

    def test_baseline_obligations_none_compute_no_pressure(self):
        # baseline/enhancement pass obligations to validate but NO depth budget.
        plan = plan_obj("svc", [prose_claim("c1", "ev:svc:0001")])
        r = cp.validate_claim_plan(
            plan, section_id="svc", token_bank=tb.build_token_bank(self.b, "svc"),
            allowed_evidence_ids=sorted(self.b.section_evidence_ids["svc"]),
            evidence_index=self.b.evidence_index, obligations=None, depth_budget=None)
        self.assertTrue(r.ok, r.problem_lines())


# --- prompt -------------------------------------------------------------------
class DepthPromptTests(unittest.TestCase):
    def _packet(self):
        data = {"section": {"section_id": "svc", "title": "Service"},
                "allowed_evidence_ids": ["ev:svc:0001", "ev:svc:0002"]}
        return WritingPacket(section_id="svc", title="Service", order=1, data=data,
                             allowed_evidence_ids=["ev:svc:0001", "ev:svc:0002"])

    def _budget(self):
        obligations = [{"topic": "Explain the dispatcher.", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:svc:0001", "ev:svc:0002"]}]
        return depth.derive_section_depth_budget(
            section_id="svc", obligations=obligations, content_block_obligations=None,
            allowed_evidence_ids=["ev:svc:0001", "ev:svc:0002"], token_count=2,
            source_handle_count=0)

    def test_prompt_carries_per_topic_targets(self):
        b = three_evidence_bundle()
        bank = tb.build_token_bank(b, "svc")
        prompt = cp.build_claim_plan_prompt(self._packet(), bank,
                                            depth_budget=self._budget())
        self.assertIn("Source-derived depth budget", prompt)
        self.assertIn("Explain the dispatcher.", prompt)
        self.assertIn("min claims", prompt)

    def test_prompt_without_budget_omits_depth_section(self):
        b = three_evidence_bundle()
        bank = tb.build_token_bank(b, "svc")
        prompt = cp.build_claim_plan_prompt(self._packet(), bank, depth_budget=None)
        self.assertNotIn("Source-derived depth budget", prompt)

    def test_prompt_has_no_benchmark_string(self):
        b = three_evidence_bundle()
        bank = tb.build_token_bank(b, "svc")
        prompt = cp.build_claim_plan_prompt(self._packet(), bank,
                                            depth_budget=self._budget())
        lowered = prompt.lower()
        for forbidden in ("ragflow-deepwiki", "98271", "98,271", "899 headings"):
            self.assertNotIn(forbidden, lowered)


# --- end-to-end expanded grounded command path (non-live) ---------------------
from test_phase4_generated_coverage import (  # noqa: E402
    _EXPANDED_BLOCK,
    _EXPANDED_EVIDENCE_ID,
    _EXPANDED_SID,
    _run_cmd,
    _write_expanded_claim_plan,
    _write_expanded_command_bundle,
)
import shutil  # noqa: E402
import tempfile  # noqa: E402

from wiki_generator.libs import util  # noqa: E402


class DepthGroundedE2ETests(unittest.TestCase):
    """Real ``write-wiki --coverage-mode expanded --grounded-claim-plan`` via the gem
    response-import provider — no Vertex/Gemini/API client is constructed."""

    def _bundle(self):
        tmp = tempfile.mkdtemp(prefix="p4_depth_cmd_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = os.path.join(tmp, "bundle")
        os.makedirs(root)
        responses = _write_expanded_command_bundle(root)
        return root, responses

    def _write_wiki(self, root, responses):
        return _run_cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                        "--responses-in", responses, "--coverage-mode", "expanded",
                        "--grounded-claim-plan", "--validate-and-assemble")

    def test_expanded_grounded_records_depth_audit(self):
        # topic mapped to exactly one evidence id => depth target 1 => the single-claim
        # plan is satisfiable (no padding) and the depth audit is recorded.
        root, responses = self._bundle()
        _write_expanded_claim_plan(responses, include_block=True)
        res = self._write_wiki(root, responses)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        rows = [json.loads(l) for l in open(os.path.join(
            root, "wiki", "metadata", "generated-sections.jsonl")) if l.strip()]
        depth_block = rows[0]["grounded"]["depth"]
        self.assertEqual(depth_block["schema_version"], depth.DEPTH_BUDGET_SCHEMA_VERSION)
        self.assertTrue(depth_block["satisfied"])
        self.assertEqual(depth_block["topic_targets"], {"operations flow": 1})
        self.assertEqual(depth_block["total_claims"], 1)

    def test_expanded_grounded_shallow_fails_closed(self):
        # patch the upstream evidenced matrix so the topic maps to TWO evidence ids
        # (depth target 2) while the plan still grounds only one claim => fail closed.
        root, responses = self._bundle()
        ec_path = os.path.join(root, "evidence", "evidenced-coverage.json")
        ec = util.read_json(ec_path)
        topic = ec["sections"][0]["topics"][0]
        topic["mapped_evidence_ids"] = [_EXPANDED_EVIDENCE_ID, "ev:ops:0002"]
        topic["evidence_count"] = 2
        util.write_json(ec_path, ec)
        _write_expanded_claim_plan(responses, include_block=True)

        res = self._write_wiki(root, responses)
        self.assertEqual(res.returncode, 5, res.stderr + res.stdout)
        self.assertIn(depth.CODE_TOPIC_UNDERFILLED, res.stderr + res.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
