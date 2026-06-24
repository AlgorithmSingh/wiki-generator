"""Milestone 2 (DeepWiki-informed coverage enhancement) — coverage-validation slice.

Deterministic, LLM-free tests for the planned-topic taxonomy and the coverage
validator. No Gemini/Vertex/API/network calls; no Phase 1/2/3/4 pipeline runs.

Proves the slice's required behaviours:

- a faithful compact 16-section baseline plan FAILS enhancement-mode coverage
  validation (and is report-only/PASS in baseline mode);
- an expanded/hierarchical plan that plans for every mandatory family PASSES;
- a plan missing exactly frontend/memory/queue fails with actionable diagnostics
  naming exactly those three families;
- a broad parent page does NOT satisfy a deep child topic family;
- keyword and explicit-coverage-label detection both work, with no false matches
  on substrings (``go`` ≠ ``goal``);
- the ``validate-coverage`` CLI command gates with exit code 3;
- Milestone 1 malformed-evidence-token validation remains intact.

Run with stdlib only: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.commands import validate_coverage as vc_cmd  # noqa: E402
from wiki_generator.libs.coverage.taxonomy import (  # noqa: E402
    MANDATORY_TOPIC_FAMILIES,
    family_keys,
)


# --- fixtures -----------------------------------------------------------------
def _sec(sid, title, *, topics=(), labels=(), purpose="", goal=""):
    """A minimal normalized-section-shaped dict the validator can read."""
    return {"schema_version": "phase2-section-plan-v1", "section_id": sid,
            "title": title, "purpose": purpose, "goal": goal, "rationale": "",
            "required_topics": list(topics), "key_questions": [],
            "coverage_labels": list(labels)}


# The actual 16 sections from the historical live run
# (13-e2e-allphases/phase4-live-vertex-runs/20260623-183730/wiki/index.md):
# faithful titles + purposes so the baseline is authentic, not strawmanned.
COMPACT_16 = [
    _sec("overview", "Overview",
         purpose="To provide a high-level introduction to RAGFlow, its purpose, "
                 "and its main features."),
    _sec("architecture", "Architecture",
         purpose="To describe the high-level software architecture, its major "
                 "components, and how they interact."),
    _sec("subsystem-rag-core", "Core RAG Pipeline",
         purpose="To detail the core components of the RAG pipeline, including "
                 "parsing, chunking, embedding, and retrieval."),
    _sec("subsystem-agent-framework", "Agent Framework",
         purpose="To explain the agent system, including the canvas, components, "
                 "tools, and plugins."),
    _sec("http-api", "HTTP API Reference",
         purpose="To provide a comprehensive reference for the RAGFlow RESTful "
                 "API, covering all major endpoints."),
    _sec("api-agents", "Agents API",
         purpose="To document API endpoints related to creating, managing, and "
                 "interacting with agents."),
    _sec("api-datasets-and-documents", "Datasets & Documents API",
         purpose="To document API endpoints for managing datasets, documents, "
                 "chunks, and the ingestion process."),
    _sec("api-chat-and-sessions", "Chat & Sessions API",
         purpose="To document endpoints for managing chat conversations, "
                 "sessions, and messages."),
    _sec("cli-tools", "Command-Line Tools",
         purpose="To document the available command-line interfaces for "
                 "administration, data migration, and other tasks."),
    _sec("data-models", "Data Models and Schemas",
         purpose="To describe the key data structures and database models used "
                 "throughout the application."),
    _sec("configuration", "Configuration",
         purpose="To explain how to configure RAGFlow using environment "
                 "variables and configuration files."),
    _sec("data-storage", "Data Storage",
         purpose="To describe the storage backends used by RAGFlow, including "
                 "databases, vector stores, and object storage."),
    _sec("llm-integration", "LLM Integration",
         purpose="To explain how RAGFlow integrates with Large Language Models "
                 "(LLMs) and how to configure different providers."),
    _sec("authentication", "Authentication and Security",
         purpose="To document the authentication mechanisms for the API and web "
                 "interface."),
    _sec("testing", "Testing",
         purpose="To guide developers on how to run the test suite and "
                 "contribute new tests."),
    _sec("deployment", "Deployment",
         purpose="To provide instructions for deploying RAGFlow, particularly "
                 "using Docker."),
]


# An expanded/hierarchical plan covering every mandatory family. Detection is a
# DELIBERATE mix of explicit coverage labels and distinctive keyword titles/topics
# so both mechanisms are exercised in one passing plan. Topic text is authored to
# avoid cross-family contamination (no stray "queue"/"memory"/"frontend").
def expanded_sections():
    return [
        _sec("overview", "Overview",
             topics=["high-level introduction to the product and features"]),
        _sec("architecture", "System Architecture",
             topics=["major components and how they interact"]),
        # --- one section per mandatory family ---
        _sec("frontend-app", "Frontend Application",
             labels=["frontend"],
             topics=["routing and page structure", "ui component architecture"]),
        _sec("memory-system", "Memory System",
             labels=["memory"],
             topics=["episodic and procedural memory apis"]),
        _sec("task-queues", "Task Queues and Redis Streams",
             topics=["task lifecycle", "workers, cancellation and retries"]),
        _sec("k8s-helm", "Kubernetes and Helm Deployment",
             topics=["charts, values and manifests", "ingress and secrets"]),
        _sec("build-cicd", "Build System and CI/CD",
             topics=["github actions", "docker build flow and release scripts"]),
        _sec("go-native", "Go Server and Native Components",
             topics=["go server build modes", "native component services"]),
        _sec("retrieval-internals", "Retrieval and Search Internals",
             labels=["retrieval-internals"],
             topics=["document store abstraction", "hybrid search and reranking"]),
        _sec("doc-pipeline", "Document Processing Pipeline",
             topics=["deepdoc parser factory", "ocr and layout recognition",
                     "chunking strategy and content enhancement"]),
        _sec("llm-internals", "LLM Provider Internals",
             labels=["llm-provider"],
             topics=["llmbundle and model registration", "tool calling",
                     "retry logic and backoff"]),
        _sec("admin-health", "User, Tenant, Admin and System Health",
             topics=["tenant management and admin service",
                     "health endpoint and status probe"]),
        _sec("sandbox", "Sandbox Code Executor",
             labels=["sandbox"],
             topics=["code executor and provider registry"]),
        _sec("ops-migrations", "Migrations and Operations",
             topics=["database migration and schema sync", "oceanbase upgrade path"]),
        _sec("glossary", "Glossary",
             labels=["glossary"],
             topics=["repo-specific terminology and acronyms"]),
    ]


def _write_plan_bundle(root, sections):
    """Write the minimal Phase 2 plan artifacts the coverage loader reads."""
    plans = os.path.join(root, "plans")
    os.makedirs(plans, exist_ok=True)
    doc = {"schema_version": "phase2-plan-v1",
           "repo": {"name": "demo", "root": root},
           "title": "Demo Documentation Plan",
           "section_order": [s["section_id"] for s in sections],
           "coverage_goals": [], "known_gaps": []}
    util.write_json(os.path.join(plans, "document-plan.json"), doc)
    util.write_jsonl(os.path.join(plans, "section-plans.jsonl"), sections)
    return root


# ---------------------------------------------------------------------------
class TaxonomyShapeTests(unittest.TestCase):
    """The mandatory taxonomy is well-formed and complete per the spec."""

    SPEC_FAMILIES = {
        "frontend", "memory", "queue-system", "helm-k8s", "ci-cd-build",
        "go-native", "retrieval-internals", "doc-processing", "llm-internals",
        "user-tenant-admin-health", "sandbox-executor", "migrations-operations",
        "glossary",
    }

    def test_all_thirteen_mandatory_families_present(self):
        self.assertEqual(set(family_keys()), self.SPEC_FAMILIES)
        self.assertEqual(len(MANDATORY_TOPIC_FAMILIES), 13)
        self.assertTrue(all(f.mandatory for f in MANDATORY_TOPIC_FAMILIES))

    def test_keys_and_labels_unique_and_signals_present(self):
        keys = [f.key for f in MANDATORY_TOPIC_FAMILIES]
        labels = [f.label for f in MANDATORY_TOPIC_FAMILIES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(labels), len(set(labels)))
        for f in MANDATORY_TOPIC_FAMILIES:
            self.assertTrue(f.coverage_labels or f.keywords, f.key)
            self.assertIn(f.key, f.all_labels)


# ---------------------------------------------------------------------------
class CompactBaselineTests(unittest.TestCase):
    """The compact 16-section baseline is under-covered for a DeepWiki guide."""

    def test_enhancement_mode_fails_the_compact_baseline(self):
        r = cov.evaluate_plan_coverage(None, COMPACT_16, mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(r.status, "fail")
        self.assertTrue(r.enforced)
        self.assertEqual(r.section_count, 16)
        # the clearly-absent deep/product families must be flagged missing
        missing = set(r.missing_mandatory)
        for fam in ("frontend", "memory", "queue-system", "helm-k8s",
                    "go-native", "sandbox-executor", "glossary",
                    "retrieval-internals", "doc-processing", "llm-internals",
                    "user-tenant-admin-health", "ci-cd-build"):
            self.assertIn(fam, missing, fam)
        self.assertGreaterEqual(len(missing), 10)

    def test_each_missing_family_has_actionable_diagnostic(self):
        r = cov.evaluate_plan_coverage(None, COMPACT_16, mode=cov.MODE_ENHANCEMENT)
        diag_by_family = {d["family"]: d for d in r.diagnostics}
        self.assertEqual(set(diag_by_family), set(r.missing_mandatory))
        d = diag_by_family["frontend"]
        self.assertEqual(d["category"], "missing_mandatory_topic_family")
        self.assertIn("frontend", d["message"])
        self.assertTrue(d["remediation"])
        self.assertIn("frontend", d["expected_labels"])
        self.assertTrue(d["expected_keywords"])

    def test_baseline_mode_reports_but_does_not_enforce(self):
        r = cov.evaluate_plan_coverage(None, COMPACT_16, mode=cov.MODE_BASELINE)
        self.assertEqual(r.status, "pass")          # report-only
        self.assertFalse(r.enforced)
        self.assertTrue(r.missing_mandatory)        # gaps still reported

    def test_render_markdown_lists_matrix_and_gaps(self):
        r = cov.evaluate_plan_coverage(None, COMPACT_16, mode=cov.MODE_ENHANCEMENT)
        md = cov.render_markdown(r)
        self.assertIn("Topic family coverage matrix", md)
        self.assertIn("Missing mandatory topic families", md)
        self.assertIn("frontend", md)
        self.assertIn("benchmark only", md)         # reference is benchmark, not evidence


# ---------------------------------------------------------------------------
class ExpandedPlanTests(unittest.TestCase):
    """An expanded/hierarchical plan with every mandatory family passes."""

    def test_expanded_plan_passes_enhancement_mode(self):
        r = cov.evaluate_plan_coverage(None, expanded_sections(),
                                       mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(r.status, "pass", r.missing_mandatory)
        self.assertEqual(r.missing_mandatory, [])
        self.assertEqual(r.covered_count, r.family_count)
        self.assertEqual(r.covered_count, 13)

    def test_both_label_and_keyword_detection_are_exercised(self):
        r = cov.evaluate_plan_coverage(None, expanded_sections(),
                                       mode=cov.MODE_ENHANCEMENT)
        sig = {f.key: f.signals for f in r.families}
        # label-driven (sandbox declared coverage_labels=["sandbox"])
        self.assertTrue(any(s.startswith("label:") for s in sig["sandbox-executor"]))
        # keyword-driven (queues covered only by distinctive title/topic text)
        self.assertTrue(any(s.startswith("keyword:") for s in sig["queue-system"]))


# ---------------------------------------------------------------------------
class MissingFamilyDiagnosticsTests(unittest.TestCase):
    """Dropping frontend/memory/queue fails with exactly those three flagged,
    even though every other family (and citation discipline) is fine."""

    def test_missing_exactly_frontend_memory_queue(self):
        drop = {"frontend-app", "memory-system", "task-queues"}
        sections = [s for s in expanded_sections()
                    if s["section_id"] not in drop]
        r = cov.evaluate_plan_coverage(None, sections, mode=cov.MODE_ENHANCEMENT)
        self.assertEqual(r.status, "fail")
        self.assertEqual(set(r.missing_mandatory),
                         {"frontend", "memory", "queue-system"})
        self.assertEqual({d["family"] for d in r.diagnostics},
                         {"frontend", "memory", "queue-system"})


# ---------------------------------------------------------------------------
class DetectionDisciplineTests(unittest.TestCase):
    """A broad parent must not satisfy a deep child; no substring false matches."""

    def test_broad_rag_parent_does_not_cover_deep_children(self):
        broad = [_sec("subsystem-rag-core", "Core RAG Pipeline",
                      topics=["parsing, chunking, embedding, and retrieval"])]
        r = cov.evaluate_plan_coverage(None, broad, mode=cov.MODE_BASELINE)
        covered = {f.key for f in r.families if f.covered}
        self.assertNotIn("retrieval-internals", covered)
        self.assertNotIn("doc-processing", covered)

    def test_broad_llm_integration_does_not_cover_deep_internals(self):
        broad = [_sec("llm-integration", "LLM Integration",
                      purpose="how RAGFlow integrates with LLMs and configures "
                              "different providers")]
        r = cov.evaluate_plan_coverage(None, broad, mode=cov.MODE_BASELINE)
        covered = {f.key for f in r.families if f.covered}
        self.assertNotIn("llm-internals", covered)

    def test_no_substring_false_positives(self):
        # "go" must not match "goal"; "memory" must not match "memoryless".
        noisy = [_sec("x", "Project goal and roadmap",
                      topics=["a memoryless stateless design"])]
        r = cov.evaluate_plan_coverage(None, noisy, mode=cov.MODE_BASELINE)
        covered = {f.key for f in r.families if f.covered}
        self.assertNotIn("go-native", covered)
        self.assertNotIn("memory", covered)

    def test_keyword_only_section_covers_family(self):
        kw = [_sec("q", "Redis Streams Task Queue and Workers",
                   topics=["task lifecycle"])]
        r = cov.evaluate_plan_coverage(None, kw, mode=cov.MODE_BASELINE)
        covered = {f.key for f in r.families if f.covered}
        self.assertIn("queue-system", covered)

    def test_unknown_mode_and_bad_sections_raise(self):
        with self.assertRaises(ValueError):
            cov.evaluate_plan_coverage(None, [], mode="nope")
        with self.assertRaises(ValueError):
            cov.evaluate_plan_coverage(None, "not-a-list", mode=cov.MODE_ENHANCEMENT)


# ---------------------------------------------------------------------------
class CliCommandTests(unittest.TestCase):
    """The validate-coverage command loads a bundle plan, writes a report, and
    gates with exit code 3 on missing mandatory families (enhancement mode)."""

    def fresh(self):
        d = tempfile.mkdtemp(prefix="cov_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return os.path.join(d, "bundle")

    def _run(self, root, mode="enhancement"):
        args = argparse.Namespace(bundle=root, out_dir=None, mode=mode)
        return vc_cmd.run(args)

    def _report(self, root):
        p = os.path.join(root, "coverage", "coverage-validation.json")
        self.assertTrue(os.path.isfile(p))
        self.assertTrue(os.path.isfile(
            os.path.join(root, "coverage", "coverage-validation-report.md")))
        return util.read_json(p)

    def test_compact_baseline_gates_fail_exit_3(self):
        root = _write_plan_bundle(self.fresh(), COMPACT_16)
        self.assertEqual(self._run(root, "enhancement"), 3)
        rep = self._report(root)
        self.assertEqual(rep["status"], "fail")
        self.assertIn("frontend", rep["missing_mandatory"])

    def test_compact_baseline_baseline_mode_exit_0(self):
        root = _write_plan_bundle(self.fresh(), COMPACT_16)
        self.assertEqual(self._run(root, "baseline"), 0)
        self.assertEqual(self._report(root)["status"], "pass")

    def test_expanded_plan_gates_pass_exit_0(self):
        root = _write_plan_bundle(self.fresh(), expanded_sections())
        self.assertEqual(self._run(root, "enhancement"), 0)
        rep = self._report(root)
        self.assertEqual(rep["status"], "pass")
        self.assertEqual(rep["missing_mandatory"], [])

    def test_missing_plan_artifacts_exit_2(self):
        root = self.fresh()
        os.makedirs(root, exist_ok=True)            # no plans/ dir
        self.assertEqual(self._run(root, "enhancement"), 2)

    def test_cli_parser_exposes_validate_coverage(self):
        from wiki_generator.cli import build_parser
        sub = build_parser()._subparsers._group_actions[0].choices
        self.assertIn("validate-coverage", sub)
        opts = {a for action in sub["validate-coverage"]._actions
                for a in action.option_strings}
        self.assertIn("--bundle", opts)
        self.assertIn("--mode", opts)


# ---------------------------------------------------------------------------
class Milestone1StillStrictTests(unittest.TestCase):
    """Coverage work must not weaken Milestone 1: the malformed-evidence-token
    validator still rejects the live `[ev:data-models:010]` shape."""

    def test_malformed_token_still_flagged(self):
        from wiki_generator.libs.writing.citations import (
            find_malformed_evidence_tokens,
        )
        diags = find_malformed_evidence_tokens(
            "Prose [ev:data-models:010] more prose.")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["category"], "wrong_ordinal_width")
        # a canonical four-digit citation is NOT flagged
        self.assertEqual(
            find_malformed_evidence_tokens("ok [ev:data-models:0010] fine"), [])


if __name__ == "__main__":
    unittest.main()
