"""Milestone 2 — Phase 2 hierarchical planning & PagePlan coverage obligations.

Deterministic, LLM-free tests for the coverage-enhanced planning fields the
normalizer now preserves so the existing ``validate-coverage`` scaffold can
evaluate planned-topic obligations off the canonical normalized plan.

Proves this slice's required behaviour:

- normalization preserves ``coverage_labels`` (kebab-normalized) from a raw
  SectionPlan (and from DocumentPlan section meta);
- normalization preserves/resolves the hierarchy field ``parent_section_id`` from
  both DocumentPlan ``parent`` and a SectionPlan ``parent_id``;
- ``required_topics`` merges ``coverage_requirements`` + ``required_topics`` and
  ``expected_sources`` is preserved;
- a deterministic expanded/hierarchical plan, once normalized, PASSES enhancement
  -mode coverage validation (all thirteen mandatory families);
- a plan missing frontend/memory/queue labels & topics FAILS enhancement-mode
  coverage with exactly those diagnostics, even though citation discipline is fine;
- the new fields survive the ``write_all`` round-trip into
  ``plans/section-plans.jsonl`` and the human-readable plan;
- the normalization report carries a NON-enforcing (baseline) coverage matrix and
  coverage never gates readiness;
- planner prompt surfaces ask for coverage labels / parent-child obligations;
- Milestone 1 malformed-evidence-token validation remains intact.

No Gemini/Vertex/API/network; no Phase 1/2/3/4 pipeline runs.
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.plan_normalization import normalize, parse, writer  # noqa: E402
from wiki_generator.libs.plan_normalization.lookups import Lookups  # noqa: E402


def _lookups() -> Lookups:
    lk = Lookups("/tmp/wiki-coverage-planning-test")
    lk.files = set()
    return lk


def _normalize(doc_sections, section_plans, *, doc_extra=None):
    doc = {"repo": "demo", "sections": doc_sections}
    if doc_extra:
        doc.update(doc_extra)
    raw = parse.RawPlan(document_plan=doc, section_plans=section_plans)
    return normalize.normalize(raw, _lookups(), "plans/raw.md", "test")


def _by_id(result):
    return {s["section_id"]: s for s in result.sections}


# A small hierarchical plan: one parent ("subsystems") with two deep children that
# carry explicit coverage labels + a SectionPlan-level parent reference.
def _hierarchical_raw():
    doc_sections = [
        {"id": "overview", "title": "Overview", "parent": None},
        {"id": "subsystems", "title": "Subsystems", "parent": None},
        # child via DocumentPlan meta parent
        {"id": "retrieval-internals", "title": "Retrieval and Search Internals",
         "parent": "subsystems"},
        # child via SectionPlan parent_id (meta parent left null)
        {"id": "doc-pipeline", "title": "Document Processing Pipeline",
         "parent": None},
    ]
    section_plans = [
        {"section_id": "overview", "title": "Overview",
         "evidence_needs": {"search_hints": ["repo overview"]}},
        {"section_id": "subsystems", "title": "Subsystems",
         "evidence_needs": {"search_hints": ["module layout"]}},
        {"section_id": "retrieval-internals",
         "title": "Retrieval and Search Internals",
         "coverage_labels": ["Retrieval Internals"],  # → kebab "retrieval-internals"
         "coverage_requirements": ["document store abstraction"],
         "required_topics": ["hybrid search and reranking"],
         "expected_sources": ["rag/nlp/search.py"],
         "evidence_needs": {"search_hints": ["retrieve: rag.nlp.search"]}},
        {"section_id": "doc-pipeline", "title": "Document Processing Pipeline",
         "parent_id": "subsystems",
         "coverage_labels": ["doc-processing"],
         "required_topics": ["deepdoc parser factory", "chunking strategy"],
         "evidence_needs": {"search_hints": ["retrieve: deepdoc"]}},
    ]
    return doc_sections, section_plans


# A full expanded plan: one section per mandatory family, all signalled. Detection
# is a deliberate mix of explicit coverage labels and distinctive keyword topics.
def _full_expanded_raw():
    def sec(sid, title, *, labels=(), topics=(), parent=None):
        plan = {"section_id": sid, "title": title,
                "evidence_needs": {"search_hints": [f"retrieve: {sid}"]}}
        if labels:
            plan["coverage_labels"] = list(labels)
        if topics:
            plan["required_topics"] = list(topics)
        if parent:
            plan["parent_id"] = parent
        meta = {"id": sid, "title": title, "parent": None}
        return meta, plan

    rows = [
        sec("overview", "Overview"),
        sec("subsystems", "Subsystems"),
        sec("frontend-app", "Frontend Application", labels=["frontend"],
            topics=["routing and ui component architecture"], parent="subsystems"),
        sec("memory-system", "Memory System", labels=["memory"],
            topics=["episodic and procedural memory apis"]),
        sec("task-queues", "Task Queues and Redis Streams",
            topics=["task lifecycle and workers", "redis streams cancellation"]),
        sec("k8s-helm", "Kubernetes and Helm Deployment",
            topics=["helm chart values and manifests", "ingress and secrets"]),
        sec("build-cicd", "Build System and CI/CD",
            topics=["github actions and docker build flow"]),
        sec("go-native", "Go Server and Native Components",
            topics=["go server build modes and native component services"]),
        sec("retrieval-internals", "Retrieval and Search Internals",
            labels=["retrieval-internals"],
            topics=["document store abstraction and hybrid search"],
            parent="subsystems"),
        sec("doc-pipeline", "Document Processing Pipeline",
            labels=["doc-processing"],
            topics=["deepdoc parser factory, ocr and chunking strategy"],
            parent="subsystems"),
        sec("llm-internals", "LLM Provider Internals", labels=["llm-provider"],
            topics=["llmbundle, tool calling, retry logic and backoff"]),
        sec("admin-health", "User, Tenant, Admin and System Health",
            topics=["tenant management and admin service", "health endpoint"]),
        sec("sandbox", "Sandbox Code Executor", labels=["sandbox"],
            topics=["code executor and provider registry"]),
        sec("ops-migrations", "Migrations and Operations",
            topics=["database migration and schema sync", "oceanbase upgrade path"]),
        sec("glossary", "Glossary", labels=["glossary"],
            topics=["repo-specific terminology and acronyms"]),
    ]
    return [m for m, _ in rows], [p for _, p in rows]


# ---------------------------------------------------------------------------
class FieldPreservationTests(unittest.TestCase):
    """Normalization preserves the coverage-enhanced planning fields."""

    def setUp(self):
        doc, plans = _hierarchical_raw()
        self.result = _normalize(doc, plans)
        self.secs = _by_id(self.result)

    def test_coverage_labels_kebab_normalized(self):
        # "Retrieval Internals" → canonical "retrieval-internals"
        self.assertEqual(self.secs["retrieval-internals"]["coverage_labels"],
                         ["retrieval-internals"])
        self.assertEqual(self.secs["doc-pipeline"]["coverage_labels"],
                         ["doc-processing"])
        # a section with no labels carries an empty list, not a missing key
        self.assertEqual(self.secs["overview"]["coverage_labels"], [])

    def test_coverage_labels_from_document_meta(self):
        doc = [{"id": "fe", "title": "Frontend", "parent": None,
                "coverage_labels": ["frontend"]}]
        plans = [{"section_id": "fe", "title": "Frontend",
                  "evidence_needs": {"search_hints": ["frontend"]}}]
        r = _normalize(doc, plans)
        self.assertEqual(_by_id(r)["fe"]["coverage_labels"], ["frontend"])

    def test_parent_resolved_from_document_meta(self):
        self.assertEqual(self.secs["retrieval-internals"]["parent_section_id"],
                         "subsystems")

    def test_parent_resolved_from_section_plan_parent_id(self):
        # doc meta parent was null; the SectionPlan parent_id drives the hierarchy
        self.assertEqual(self.secs["doc-pipeline"]["parent_section_id"],
                         "subsystems")

    def test_top_level_parent_is_none(self):
        self.assertIsNone(self.secs["overview"]["parent_section_id"])
        self.assertIsNone(self.secs["subsystems"]["parent_section_id"])

    def test_required_topics_merges_both_sources(self):
        self.assertEqual(self.secs["retrieval-internals"]["required_topics"],
                         ["document store abstraction", "hybrid search and reranking"])

    def test_expected_sources_preserved(self):
        self.assertEqual(self.secs["retrieval-internals"]["expected_sources"],
                         ["rag/nlp/search.py"])

    def test_unresolved_parent_kept_with_nonblocking_warning(self):
        doc = [{"id": "child", "title": "Child", "parent": "ghost-parent"}]
        plans = [{"section_id": "child", "title": "Child",
                  "evidence_needs": {"search_hints": ["x"]}}]
        r = _normalize(doc, plans)
        # the hint is preserved verbatim (never silently dropped)...
        self.assertEqual(_by_id(r)["child"]["parent_section_id"], "ghost-parent")
        # ...and it is a warning, not a readiness failure
        self.assertTrue(any("ghost-parent" in w for w in r.warnings))
        self.assertTrue(writer.readiness_pass(r))


# ---------------------------------------------------------------------------
class NormalizedCoverageValidationTests(unittest.TestCase):
    """Coverage validation evaluated off the NORMALIZED plan (the real path)."""

    def test_full_expanded_plan_passes_enhancement(self):
        doc, plans = _full_expanded_raw()
        r = _normalize(doc, plans)
        report = cov.evaluate_plan_coverage(r.document_plan, r.sections,
                                            mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(report.status, "pass", report.missing_mandatory)
        self.assertEqual(report.missing_mandatory, [])
        self.assertEqual(report.covered_count, report.family_count)
        # the normalized plan is also Phase-3 ready (coverage is orthogonal)
        self.assertTrue(writer.readiness_pass(r))

    def test_dropping_frontend_memory_queue_fails_enhancement(self):
        doc, plans = _full_expanded_raw()
        drop = {"frontend-app", "memory-system", "task-queues"}
        doc = [d for d in doc if d["id"] not in drop]
        plans = [p for p in plans if p["section_id"] not in drop]
        r = _normalize(doc, plans)
        report = cov.evaluate_plan_coverage(r.document_plan, r.sections,
                                            mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(report.status, "fail")
        self.assertEqual(set(report.missing_mandatory),
                         {"frontend", "memory", "queue-system"})
        self.assertEqual({d["family"] for d in report.diagnostics},
                         {"frontend", "memory", "queue-system"})
        # citation discipline is irrelevant to this gate: it still fails on coverage
        self.assertTrue(report.diagnostics[0]["remediation"])

    def test_baseline_mode_never_gates_the_partial_plan(self):
        doc, plans = _hierarchical_raw()
        r = _normalize(doc, plans)
        report = cov.evaluate_plan_coverage(r.document_plan, r.sections,
                                            mode=cov.MODE_BASELINE)
        self.assertEqual(report.status, "pass")        # report-only
        self.assertTrue(report.missing_mandatory)      # but gaps are still listed


# ---------------------------------------------------------------------------
class WriterRoundTripTests(unittest.TestCase):
    """The new fields survive write_all into the canonical artifacts, and the
    report carries a non-enforcing coverage matrix."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cov_plan_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # mirror the real bundle layout: plan artifacts live under <bundle>/plans
        self.plans = os.path.join(self.tmp, "plans")
        doc, plans = _full_expanded_raw()
        self.result = _normalize(doc, plans)
        writer.write_all(self.plans, self.result, strict=False, strict_pass=True)

    def _sections(self):
        rows = list(util.read_jsonl(os.path.join(self.plans, "section-plans.jsonl")))
        return {r["section_id"]: r for r in rows}

    def test_coverage_labels_survive_into_section_plans_jsonl(self):
        secs = self._sections()
        self.assertEqual(secs["frontend-app"]["coverage_labels"], ["frontend"])
        self.assertEqual(secs["sandbox"]["coverage_labels"], ["sandbox"])
        self.assertEqual(secs["retrieval-internals"]["parent_section_id"],
                         "subsystems")

    def test_validate_coverage_loads_written_plan_and_passes(self):
        # the standalone validate-coverage loader reads exactly these artifacts
        document_plan, sections = cov.load_plan_for_coverage(self.tmp)
        report = cov.evaluate_plan_coverage(document_plan, sections,
                                            mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(report.status, "pass", report.missing_mandatory)

    def test_document_plan_md_shows_labels_and_hierarchy(self):
        with open(os.path.join(self.plans, "document-plan.md")) as f:
            md = f.read()
        self.assertIn("Coverage labels:", md)
        self.assertIn("`frontend`", md)
        self.assertIn("_(under `subsystems`)_", md)

    def test_report_has_non_enforcing_coverage_block(self):
        with open(os.path.join(self.plans, "normalization-report.md")) as f:
            md = f.read()
        self.assertIn("DeepWiki coverage (benchmark, non-enforcing)", md)
        self.assertIn("report-only", md)
        self.assertIn("13/13", md)             # full expanded plan covers all

    def test_coverage_does_not_gate_readiness(self):
        # the readiness report (the real Phase 3 gate) is independent of coverage
        with open(os.path.join(self.plans, "phase3-readiness-report.md")) as f:
            self.assertIn("Status: PASS", f.read())


# ---------------------------------------------------------------------------
class PlannerPromptCoverageGuidanceTests(unittest.TestCase):
    """Every planner prompt surface asks for coverage labels / hierarchy so the
    coverage-enhancement obligations cannot vanish in a fallback environment."""

    GEM_DIR = os.path.join(ROOT, "gemini-gem")
    SAMPLE_FAMILIES = ("queue-system", "retrieval-internals", "doc-processing",
                       "sandbox-executor")

    def _read(self, name):
        with open(os.path.join(self.GEM_DIR, name), encoding="utf-8") as f:
            return f.read()

    def _assert_coverage_guidance(self, text, name, *, expect_labels=True):
        self.assertIn("coverage_labels", text, name)
        if expect_labels:
            self.assertIn("parent_section_id", text, name)
        for fam in self.SAMPLE_FAMILIES:
            self.assertIn(fam, text, f"{name}:{fam}")

    def test_gem_instructions(self):
        self._assert_coverage_guidance(self._read("GEM_INSTRUCTIONS.md"),
                                       "GEM_INSTRUCTIONS.md")

    def test_kickoff_prompt(self):
        self._assert_coverage_guidance(self._read("KICKOFF_PROMPT.md"),
                                       "KICKOFF_PROMPT.md")

    def test_plan_py_fallback_prompt(self):
        from wiki_generator.libs.commands import plan
        self._assert_coverage_guidance(plan._DEFAULT_SYSTEM, "plan._DEFAULT_SYSTEM")

    def test_upload_bundle_readme(self):
        from wiki_generator.libs.digest.upload_package import _readme
        text = _readme("/repo", "bundle", "2026-01-01", ["planning-digest.md"])
        self._assert_coverage_guidance(text, "_readme", expect_labels=False)


# ---------------------------------------------------------------------------
class Milestone1IntactTests(unittest.TestCase):
    """Coverage-enhanced planning must not weaken Milestone 1 citation discipline."""

    def test_malformed_evidence_token_still_flagged(self):
        from wiki_generator.libs.writing.citations import (
            find_malformed_evidence_tokens,
        )
        self.assertEqual(
            len(find_malformed_evidence_tokens("x [ev:data-models:010] y")), 1)
        self.assertEqual(
            find_malformed_evidence_tokens("x [ev:data-models:0010] y"), [])


if __name__ == "__main__":
    unittest.main()
