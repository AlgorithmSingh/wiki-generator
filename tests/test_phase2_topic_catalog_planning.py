"""Phase B — hierarchical page-planning contract and gates (expanded coverage).

Deterministic, LLM-free, network-free tests for the new Phase 2 expanded-coverage
contract:

- normalization preserves the additive hierarchical page fields (``page_profile``,
  ``catalog_topic_ids[]``, ``required_content_blocks[]``) and the extended
  ``topic_evidence_requirements[].catalog_topic_id`` / ``.content_block_id`` links,
  while a baseline plan that omits them is unaffected;
- the page-profile registry is a closed, well-formed valid set;
- the deterministic ``page-planning`` gate validates acyclic resolved hierarchy,
  valid page profiles, required content blocks per profile, and high-signal
  catalog-topic coverage (planned or explicitly deferred), failing closed in
  ``expanded`` mode and reporting-only in ``baseline``;
- a broad parent page does NOT satisfy a child subsystem catalog topic;
- the integrated ``normalize-plan --coverage-mode expanded`` command runs the
  family + obligation + page-planning + source-map gates over a real bundle, writes
  the gate artifacts, passes a complete expanded plan, fails a defective one (exit
  3), and fails closed (exit 2) when the Phase A topic catalog is absent;
- ``enhancement`` mode keeps its exact historical behaviour (no new gates).

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
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.commands import normalize_plan as normalize_plan_cmd  # noqa: E402
from wiki_generator.libs.coverage import page_profiles  # noqa: E402
from wiki_generator.libs.plan_normalization import normalize, parse  # noqa: E402
from wiki_generator.libs.plan_normalization.lookups import Lookups  # noqa: E402

_TOPIC_FILE = "src/app.py"


def _lookups() -> Lookups:
    lk = Lookups("/tmp/wiki-topic-catalog-planning-test")
    lk.files = {_TOPIC_FILE}
    return lk


# --- catalog / section builders ----------------------------------------------
def _topic(tid, *, priority="must", strength="high", status="present",
           parent=None, kind="family", label=None):
    return {"topic_id": tid, "parent_topic_id": parent,
            "family": tid.split(".")[0], "label": label or tid,
            "topic_kind": kind, "suggested_page_profile": "subsystem-deep-dive",
            "status": status, "signal_strength": strength, "priority": priority}


def _catalog(*topics, fingerprint="sha256:catalogfp"):
    return {"schema_version": "deepwiki-topic-catalog-v1",
            "role": "planner_context", "citeable_as_evidence": False,
            "source_fingerprint": fingerprint, "topics": list(topics)}


def _norm_section(sid, *, profile=None, catalog_ids=(), blocks=(), parent=None,
                  required_topics=(), ters=(), known_gaps=(), needs=None,
                  role="source"):
    """A normalized section dict in the exact shape the gates read."""
    return {
        "section_id": sid, "section_role": role, "title": sid,
        "page_profile": profile, "parent_section_id": parent,
        "catalog_topic_ids": list(catalog_ids),
        "required_content_blocks": [
            b if isinstance(b, dict) else {"block_id": b, "block_type": b,
                                           "required": True, "required_topics": [],
                                           "min_exact_items": 0,
                                           "expected_evidence_lanes": []}
            for b in blocks],
        "required_topics": list(required_topics),
        "topic_evidence_requirements": list(ters),
        "known_gaps": list(known_gaps),
        "retrieval_needs": needs or {},
    }


def _blocks_for(profile):
    return [{"block_id": b, "block_type": b, "required": True,
             "required_topics": [], "min_exact_items": 0,
             "expected_evidence_lanes": []}
            for b in page_profiles.required_block_ids(profile)]


# --- raw-plan / bundle integration helpers -----------------------------------
def _esec(sid, title, profile, *, labels=(), topics=(), parent=None,
          catalog_ids=(), sources=()):
    """An expanded ``(meta, section-plan)`` pair: a page profile, its required
    content blocks, a file anchor, a required topic with a TER linking the topic to
    the file handle and an evidence content block, and optional catalog topic ids."""
    meta = {"id": sid, "title": title, "parent": None}
    ev = {"search_hints": [f"retrieve: {sid}"], "file_anchors": [_TOPIC_FILE]}
    ev_blocks = page_profiles.evidence_block_ids(profile)
    block_id = ev_blocks[0] if ev_blocks else None
    cat_id = list(catalog_ids)[0] if catalog_ids else None
    tlist = list(topics) or [f"{title.lower()} purpose and key files"]
    plan = {
        "section_id": sid, "title": title, "evidence_needs": ev,
        "page_profile": profile, "catalog_topic_ids": list(catalog_ids),
        "required_content_blocks": [{"block_id": b}
                                    for b in page_profiles.required_block_ids(profile)],
        "required_topics": tlist,
        "topic_evidence_requirements": [
            {"topic": t, "required": True,
             "source_fields": ["retrieval_needs.files[0]"],
             "min_items": 1, "acceptable_lanes": ["file_anchor"],
             "content_block_id": block_id, "catalog_topic_id": cat_id}
            for t in tlist],
    }
    if labels:
        plan["coverage_labels"] = list(labels)
    if parent:
        plan["parent_id"] = parent
    if sources:
        plan["expected_sources"] = list(sources)
    return meta, plan


# A complete expanded plan: one page per mandatory family (so the planned-coverage
# gate passes), each with a valid profile, content blocks, and an exact obligation.
_EFULL = [
    _esec("overview", "Overview", "overview"),
    _esec("subsystems", "Subsystems", "architecture-flow"),
    _esec("frontend-app", "Frontend Application", "subsystem-deep-dive",
          labels=["frontend"], topics=["routing and ui component architecture"],
          parent="subsystems"),
    _esec("memory-system", "Memory System", "subsystem-deep-dive",
          labels=["memory"], topics=["episodic and procedural memory apis"]),
    _esec("task-queues", "Task Queues and Redis Streams", "subsystem-deep-dive",
          topics=["task lifecycle and workers", "redis streams cancellation"]),
    _esec("k8s-helm", "Kubernetes and Helm Deployment", "deployment-runbook",
          topics=["helm chart values and manifests", "ingress and secrets"]),
    _esec("build-cicd", "Build System and CI/CD", "deployment-runbook",
          topics=["github actions and docker build flow"]),
    _esec("go-native", "Go Server and Native Components", "subsystem-deep-dive",
          topics=["go server build modes and native component services"]),
    _esec("retrieval-internals", "Retrieval and Search Internals",
          "subsystem-deep-dive", labels=["retrieval-internals"],
          topics=["document store abstraction and hybrid search"],
          parent="subsystems", catalog_ids=["retrieval-internals"]),
    _esec("doc-pipeline", "Document Processing Pipeline", "subsystem-deep-dive",
          labels=["doc-processing"],
          topics=["deepdoc parser factory, ocr and chunking strategy"],
          parent="subsystems", catalog_ids=["doc-processing"]),
    _esec("llm-internals", "LLM Provider Internals", "subsystem-deep-dive",
          labels=["llm-provider"],
          topics=["llmbundle, tool calling, retry logic and backoff"]),
    _esec("admin-health", "User, Tenant, Admin and System Health",
          "operations-page",
          topics=["tenant management and admin service", "health endpoint"]),
    _esec("sandbox", "Sandbox Code Executor", "subsystem-deep-dive",
          labels=["sandbox"], topics=["code executor and provider registry"]),
    _esec("ops-migrations", "Migrations and Operations", "operations-page",
          topics=["database migration and schema sync", "oceanbase upgrade path"]),
    _esec("glossary", "Glossary", "glossary", labels=["glossary"],
          topics=["repo-specific terminology and acronyms"]),
]

# The catalog the integrated expanded run gates against: two high-signal (must)
# topics that ARE planned, plus a should-topic that need not be planned.
_EFULL_CATALOG = _catalog(
    _topic("retrieval-internals", priority="must"),
    _topic("doc-processing", priority="must"),
    _topic("memory", priority="should", strength="low", status="low"),
)


def _split(rows):
    return [m for m, _ in rows], [p for _, p in rows]


def _normalize(rows):
    doc, plans = _split(rows)
    raw = parse.RawPlan(document_plan={"repo": "demo", "sections": doc},
                        section_plans=plans)
    return normalize.normalize(raw, _lookups(), "plans/raw.md", "test")


def _raw_response(rows) -> str:
    doc, plans = _split(rows)
    lines = "\n".join(json.dumps(p) for p in plans)
    return ("```text\nplans/document-plan.json\n```\n"
            "```json\n" + json.dumps({"repo": "demo", "sections": doc}) + "\n```\n"
            "```text\nplans/section-plans.jsonl\n```\n"
            "```jsonl\n" + lines + "\n```\n")


# ===========================================================================
class NormalizationFieldTests(unittest.TestCase):
    """The additive hierarchical fields survive normalization, additively."""

    def test_expanded_fields_preserved(self):
        meta = {"id": "doc-parsers", "title": "Parsers", "parent": None}
        plan = {
            "section_id": "doc-parsers", "title": "Parsers",
            "page_profile": "API Reference",                  # mixed-case -> kebab
            "catalog_topic_ids": ["doc-processing.parsers"],
            "required_content_blocks": [
                "purpose", {"block_id": "flow", "min_exact_items": 3,
                            "expected_evidence_lanes": ["file_anchor"]}],
            "required_topics": ["Parser selection flow"],
            "topic_evidence_requirements": [
                {"topic": "Parser selection flow",
                 "source_fields": ["retrieval_needs.files[0]"],
                 "catalog_topic_id": "doc-processing.parsers",
                 "content_block_id": "flow"}],
            "evidence_needs": {"file_anchors": [_TOPIC_FILE]},
        }
        r = _normalize([(meta, plan)])
        s = r.sections[0]
        self.assertEqual(s["page_profile"], "api-reference")  # kebab-normalized
        self.assertEqual(s["catalog_topic_ids"], ["doc-processing.parsers"])
        block_ids = [b["block_id"] for b in s["required_content_blocks"]]
        self.assertEqual(block_ids, ["purpose", "flow"])
        flow = s["required_content_blocks"][1]
        self.assertEqual(flow["min_exact_items"], 3)
        self.assertEqual(flow["expected_evidence_lanes"], ["file_anchor"])
        ter = s["topic_evidence_requirements"][0]
        self.assertEqual(ter["catalog_topic_id"], "doc-processing.parsers")
        self.assertEqual(ter["content_block_id"], "flow")

    def test_baseline_plan_unaffected(self):
        meta = {"id": "s", "title": "S", "parent": None}
        plan = {"section_id": "s", "title": "S",
                "evidence_needs": {"search_hints": ["x"]}}
        s = _normalize([(meta, plan)]).sections[0]
        self.assertIsNone(s["page_profile"])
        self.assertEqual(s["catalog_topic_ids"], [])
        self.assertEqual(s["required_content_blocks"], [])


class PageProfileRegistryTests(unittest.TestCase):
    def test_ten_profiles_closed_set(self):
        self.assertEqual(len(page_profiles.VALID_PROFILES), 10)
        self.assertIn("subsystem-deep-dive", page_profiles.VALID_PROFILES)
        self.assertFalse(page_profiles.is_valid_profile("not-a-profile"))

    def test_required_and_evidence_blocks(self):
        self.assertIn("flow", page_profiles.required_block_ids("subsystem-deep-dive"))
        # purpose / known_gaps are narrative blocks: not evidence-required.
        self.assertNotIn("purpose",
                         page_profiles.evidence_block_ids("subsystem-deep-dive"))
        self.assertIn("flow", page_profiles.evidence_block_ids("subsystem-deep-dive"))

    def test_glossary_has_no_exact_floor(self):
        self.assertEqual(page_profiles.profile_evidence_floor("glossary"), ())
        self.assertGreater(len(page_profiles.profile_evidence_floor("api-reference")), 0)


class PagePlanningGateUnitTests(unittest.TestCase):
    """The deterministic hierarchical page-planning gate."""

    def _pass_sections(self):
        prof = "subsystem-deep-dive"
        return [
            _norm_section("parent", profile="overview",
                          blocks=_blocks_for("overview")),
            _norm_section("child", profile=prof, parent="parent",
                          catalog_ids=["doc-processing"], blocks=_blocks_for(prof)),
        ]

    def _catalog_one_must(self):
        return _catalog(_topic("doc-processing", priority="must"))

    def test_complete_plan_passes(self):
        g = cov.gate_page_planning(self._catalog_one_must(), None,
                                   self._pass_sections(), mode=cov.MODE_EXPANDED)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])
        self.assertEqual(g.exit_code, cov.COVERAGE_GATE_PASS_EXIT)

    def test_missing_profile_fails(self):
        secs = [_norm_section("a", profile=None)]
        g = cov.gate_page_planning(self._catalog_one_must(), None, secs,
                                   mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_MISSING_PROFILE, codes)

    def test_invalid_profile_fails(self):
        secs = [_norm_section("a", profile="encyclopedia",
                              catalog_ids=["doc-processing"])]
        g = cov.gate_page_planning(self._catalog_one_must(), None, secs,
                                   mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_INVALID_PROFILE, codes)

    def test_missing_required_content_block_fails(self):
        # subsystem-deep-dive requires a `flow` block; omit it.
        prof = "subsystem-deep-dive"
        blocks = [b for b in _blocks_for(prof) if b["block_id"] != "flow"]
        secs = [_norm_section("a", profile=prof, blocks=blocks,
                              catalog_ids=["doc-processing"])]
        g = cov.gate_page_planning(self._catalog_one_must(), None, secs,
                                   mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_MISSING_CONTENT_BLOCK, codes)

    def test_unresolved_parent_fails(self):
        secs = [_norm_section("child", profile="subsystem-deep-dive",
                              parent="ghost", blocks=_blocks_for("subsystem-deep-dive"),
                              catalog_ids=["doc-processing"])]
        g = cov.gate_page_planning(self._catalog_one_must(), None, secs,
                                   mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_UNRESOLVED_PARENT, codes)

    def test_hierarchy_cycle_fails(self):
        prof = "subsystem-deep-dive"
        secs = [
            _norm_section("a", profile=prof, parent="b", blocks=_blocks_for(prof),
                          catalog_ids=["doc-processing"]),
            _norm_section("b", profile=prof, parent="a", blocks=_blocks_for(prof)),
        ]
        g = cov.gate_page_planning(self._catalog_one_must(), None, secs,
                                   mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_HIERARCHY_CYCLE, codes)

    def test_uncovered_high_signal_catalog_topic_fails(self):
        # a `must` topic that no page plans and no known_gap defers.
        catalog = _catalog(_topic("frontend", priority="must"),
                           _topic("doc-processing", priority="must"))
        secs = [_norm_section("a", profile="subsystem-deep-dive",
                              blocks=_blocks_for("subsystem-deep-dive"),
                              catalog_ids=["doc-processing"])]
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        codes = {d["code"] for d in g.report.diagnostics}
        self.assertIn(cov.page_planning.CODE_UNCOVERED_CATALOG_TOPIC, codes)
        # the uncovered topic is reported with its id.
        self.assertTrue(any("frontend" in d["detail"]
                            for d in g.report.diagnostics
                            if d["code"] == cov.page_planning.CODE_UNCOVERED_CATALOG_TOPIC))

    def test_known_gap_defers_high_signal_topic(self):
        catalog = _catalog(_topic("frontend", priority="must"))
        secs = [_norm_section(
            "a", profile="subsystem-deep-dive",
            blocks=_blocks_for("subsystem-deep-dive"),
            known_gaps=["frontend has no source in this repo snapshot"])]
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_EXPANDED)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])
        topic = next(t for t in g.report.catalog_topics if t.topic_id == "frontend")
        self.assertEqual(topic.coverage_status, cov.page_planning.TOPIC_DEFERRED)

    def test_broad_parent_does_not_cover_child(self):
        # planning the parent family id does NOT cover its child subsystem topic.
        catalog = _catalog(
            _topic("doc-processing", priority="must"),
            _topic("doc-processing.parsers", priority="must", kind="subsystem",
                   parent="doc-processing"))
        secs = [_norm_section("docs", profile="subsystem-deep-dive",
                              blocks=_blocks_for("subsystem-deep-dive"),
                              catalog_ids=["doc-processing"])]   # parent only
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_EXPANDED)
        self.assertFalse(g.passed)
        uncovered = [d for d in g.report.diagnostics
                     if d["code"] == cov.page_planning.CODE_UNCOVERED_CATALOG_TOPIC]
        self.assertTrue(any("doc-processing.parsers" in d["detail"]
                            for d in uncovered))

    def test_should_topic_not_blocking(self):
        catalog = _catalog(_topic("memory", priority="should", strength="low"))
        secs = [_norm_section("a", profile="subsystem-deep-dive",
                              blocks=_blocks_for("subsystem-deep-dive"))]
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_EXPANDED)
        self.assertTrue(g.passed, [d for d in g.report.diagnostics])

    def test_baseline_reports_but_never_gates(self):
        catalog = _catalog(_topic("frontend", priority="must"))
        secs = [_norm_section("a", profile="not-real")]    # invalid profile
        g = cov.gate_page_planning(catalog, None, secs, mode=cov.MODE_BASELINE)
        self.assertTrue(g.passed)                          # report-only
        self.assertFalse(g.report.enforced)
        self.assertTrue(g.report.diagnostics)              # still reported


# ===========================================================================
class IntegratedExpandedGateTests(unittest.TestCase):
    """``normalize-plan --coverage-mode expanded`` end to end over a real bundle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="expanded_gate_cmd_")
        self.bundle = os.path.join(self.tmp, "bundle")
        self.plans = os.path.join(self.bundle, "plans")
        inv = os.path.join(self.bundle, "inventory")
        os.makedirs(inv)
        with open(os.path.join(inv, "files.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"path": _TOPIC_FILE, "line_count": 200}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_catalog(self, catalog):
        derived = os.path.join(self.bundle, "derived")
        os.makedirs(derived, exist_ok=True)
        util.write_json(os.path.join(derived, "topic-catalog.json"), catalog)

    def _write_raw(self, rows) -> str:
        p = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_raw_response(rows))
        return p

    def _args(self, raw, **over):
        base = dict(bundle=self.bundle, raw_response=raw, out_dir=None,
                    strict=False, provider="test", coverage_mode="expanded")
        base.update(over)
        return SimpleNamespace(**base)

    def test_expanded_passes_on_complete_plan(self):
        self._write_catalog(_EFULL_CATALOG)
        rc = normalize_plan_cmd.run(self._args(self._write_raw(_EFULL)))
        self.assertEqual(rc, 0)
        pp = util.read_json(os.path.join(self.plans, "page-planning-gate.json"))
        self.assertTrue(pp["passed"], pp["report"]["diagnostics"])
        sm = util.read_json(os.path.join(self.plans, "relevant-source-map.json"))
        self.assertEqual(sm["schema_version"], "deepwiki-relevant-source-map-v1")
        self.assertEqual(sm["catalog_fingerprint"], _EFULL_CATALOG["source_fingerprint"])
        self.assertGreater(sm["handle_count"], 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.plans, "source-selection-gate.json")))

    def test_expanded_fails_on_uncovered_must_topic(self):
        # add a must topic no page plans -> page-planning gate fails (exit 3).
        catalog = _catalog(
            _topic("retrieval-internals", priority="must"),
            _topic("doc-processing", priority="must"),
            _topic("sandbox-internals", priority="must"))   # never planned
        self._write_catalog(catalog)
        rc = normalize_plan_cmd.run(self._args(self._write_raw(_EFULL)))
        self.assertEqual(rc, cov.COVERAGE_GATE_FAIL_EXIT)
        pp = util.read_json(os.path.join(self.plans, "page-planning-gate.json"))
        self.assertFalse(pp["passed"])

    def test_expanded_missing_catalog_is_input_failure(self):
        # no derived/topic-catalog.json -> exit 2 (hard missing input).
        rc = normalize_plan_cmd.run(self._args(self._write_raw(_EFULL)))
        self.assertEqual(rc, cov.COVERAGE_GATE_INPUT_EXIT)

    def test_enhancement_mode_skips_new_gates(self):
        # enhancement keeps historical behaviour: no page-planning / source-map gate.
        self._write_catalog(_EFULL_CATALOG)
        rc = normalize_plan_cmd.run(
            self._args(self._write_raw(_EFULL), coverage_mode="enhancement"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.isfile(
            os.path.join(self.plans, "page-planning-gate.json")))
        self.assertFalse(os.path.isfile(
            os.path.join(self.plans, "relevant-source-map.json")))


if __name__ == "__main__":
    unittest.main()
