"""Milestone 2 — Phase 2 enhancement-mode upstream-prevention gate.

Deterministic, LLM-free, network-free tests for the new Phase 2 → Phase 3 coverage
boundary: ``normalize-plan --coverage-mode enhancement`` and the shared
``coverage.gate_plan_coverage`` it runs.

Proves the next-slice acceptance:

- a deterministic enhancement gate evaluates the NORMALIZED plan against all
  thirteen mandatory DeepWiki topic families before Phase 3 retrieval;
- an expanded hierarchical plan with every family PASSES (exit 0);
- a plan missing frontend/memory/queue FAILS loudly (exit 3) with actionable
  diagnostics naming exactly those families and remediation;
- a broad parent page alone does NOT satisfy a deep child family;
- baseline mode (the default) stays non-breaking / report-only — a missing family
  never gates the command, and an older arg namespace without ``coverage_mode``
  defaults to baseline;
- the deterministic gate never synthesizes, silently adds, or auto-heals missing
  pages / labels / source obligations — upstream prevention is by loud failure;
- ``coverage_labels[]``, ``parent_section_id``, merged ``required_topics[]``, and
  ``expected_sources[]`` continue to survive normalization through the command;
- every planner prompt surface cites ``planning-coverage-signals.md`` as planner
  CONTEXT, not citeable evidence;
- Milestone 1 malformed-evidence-token validation remains intact.

No Gemini/Vertex/API/network; no real Phase 1/2/3/4 pipeline run.
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
from wiki_generator.libs.plan_normalization import normalize, parse, writer  # noqa: E402
from wiki_generator.libs.plan_normalization.lookups import Lookups  # noqa: E402

DROP_THREE = {"frontend-app", "memory-system", "task-queues"}


def _lookups() -> Lookups:
    lk = Lookups("/tmp/wiki-enh-gate-test")
    lk.files = set()
    return lk


def _sec(sid, title, *, labels=(), topics=(), parent=None, sources=()):
    """Build one ``(document-meta, section-plan)`` pair. Retrieval signal is a
    benign ``search_hints`` so every section is independently Phase-3 ready and the
    coverage verdict is judged purely from the plan's stated intent."""
    meta = {"id": sid, "title": title, "parent": None}
    plan = {"section_id": sid, "title": title,
            "evidence_needs": {"search_hints": [f"retrieve: {sid}"]}}
    if labels:
        plan["coverage_labels"] = list(labels)
    if topics:
        plan["required_topics"] = list(topics)
    if parent:
        plan["parent_id"] = parent
    if sources:
        plan["expected_sources"] = list(sources)
    return meta, plan


# A full expanded plan: one section per mandatory family, signalled by a deliberate
# mix of explicit coverage labels and distinctive keyword topics (mirrors the
# proven fixture in test_phase2_coverage_planning).
_FULL = [
    _sec("overview", "Overview"),
    _sec("subsystems", "Subsystems"),
    _sec("frontend-app", "Frontend Application", labels=["frontend"],
         topics=["routing and ui component architecture"], parent="subsystems"),
    _sec("memory-system", "Memory System", labels=["memory"],
         topics=["episodic and procedural memory apis"]),
    _sec("task-queues", "Task Queues and Redis Streams",
         topics=["task lifecycle and workers", "redis streams cancellation"]),
    _sec("k8s-helm", "Kubernetes and Helm Deployment",
         topics=["helm chart values and manifests", "ingress and secrets"]),
    _sec("build-cicd", "Build System and CI/CD",
         topics=["github actions and docker build flow"]),
    _sec("go-native", "Go Server and Native Components",
         topics=["go server build modes and native component services"]),
    _sec("retrieval-internals", "Retrieval and Search Internals",
         labels=["retrieval-internals"],
         topics=["document store abstraction and hybrid search"],
         parent="subsystems", sources=["rag/nlp/search.py"]),
    _sec("doc-pipeline", "Document Processing Pipeline", labels=["doc-processing"],
         topics=["deepdoc parser factory, ocr and chunking strategy"],
         parent="subsystems"),
    _sec("llm-internals", "LLM Provider Internals", labels=["llm-provider"],
         topics=["llmbundle, tool calling, retry logic and backoff"]),
    _sec("admin-health", "User, Tenant, Admin and System Health",
         topics=["tenant management and admin service", "health endpoint"]),
    _sec("sandbox", "Sandbox Code Executor", labels=["sandbox"],
         topics=["code executor and provider registry"]),
    _sec("ops-migrations", "Migrations and Operations",
         topics=["database migration and schema sync", "oceanbase upgrade path"]),
    _sec("glossary", "Glossary", labels=["glossary"],
         topics=["repo-specific terminology and acronyms"]),
]


def _split(rows):
    return [m for m, _ in rows], [p for _, p in rows]


def _drop(rows, drop):
    return [(m, p) for m, p in rows if m["id"] not in drop]


def _normalize(rows):
    doc, plans = _split(rows)
    raw = parse.RawPlan(document_plan={"repo": "demo", "sections": doc},
                        section_plans=plans)
    return normalize.normalize(raw, _lookups(), "plans/raw.md", "test")


def _raw_response(rows) -> str:
    """Serialize ``rows`` as a fenced raw planning response that ``parse`` reads."""
    doc, plans = _split(rows)
    lines = "\n".join(json.dumps(p) for p in plans)
    return ("```text\nplans/document-plan.json\n```\n"
            "```json\n" + json.dumps({"repo": "demo", "sections": doc}) + "\n```\n"
            "```text\nplans/section-plans.jsonl\n```\n"
            "```jsonl\n" + lines + "\n```\n")


# ---------------------------------------------------------------------------
class CoverageGateUnitTests(unittest.TestCase):
    """The shared deterministic gate over a normalized plan."""

    def _gate(self, rows, mode=cov.MODE_ENHANCEMENT):
        r = _normalize(rows)
        return cov.gate_plan_coverage(r.document_plan, r.sections, mode=mode), r

    def test_full_plan_passes(self):
        gate, r = self._gate(_FULL)
        self.assertTrue(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_PASS_EXIT)
        self.assertEqual(gate.report.missing_mandatory, [])
        self.assertEqual(gate.report.covered_count, gate.report.family_count)
        # coverage is orthogonal to Phase 3 readiness — the plan is also ready
        self.assertTrue(writer.readiness_pass(r))

    def test_missing_families_fail_with_diagnostics(self):
        gate, _ = self._gate(_drop(_FULL, DROP_THREE))
        self.assertFalse(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_FAIL_EXIT)
        self.assertEqual(set(gate.report.missing_mandatory),
                         {"frontend", "memory", "queue-system"})
        diags = {d["family"]: d for d in gate.report.diagnostics}
        self.assertEqual(set(diags), {"frontend", "memory", "queue-system"})
        for d in diags.values():
            self.assertTrue(d["remediation"])
            self.assertTrue(d["message"])

    def test_summary_lines_name_families_and_disclaim_autoheal(self):
        gate, _ = self._gate(_drop(_FULL, DROP_THREE))
        text = "\n".join(gate.summary_lines())
        for fam in ("frontend", "memory", "queue-system"):
            self.assertIn(fam, text)
        # the gate must advertise that it does NOT synthesize/heal the plan
        self.assertIn("does NOT", text)
        self.assertIn("FAIL", text)

    def test_baseline_mode_never_gates_but_still_reports(self):
        gate, _ = self._gate(_drop(_FULL, {"frontend-app"}), mode=cov.MODE_BASELINE)
        self.assertTrue(gate.passed)
        self.assertEqual(gate.exit_code, cov.COVERAGE_GATE_PASS_EXIT)
        self.assertIn("frontend", gate.report.missing_mandatory)  # gap still listed

    def test_broad_parent_does_not_satisfy_deep_child(self):
        rows = [
            _sec("overview", "Overview"),
            _sec("core-rag", "Core RAG Pipeline",
                 topics=["the core retrieval pipeline overview"]),
        ]
        gate, _ = self._gate(rows)
        # a broad page mentioning only "retrieval" is not retrieval-internals
        self.assertIn("retrieval-internals", gate.report.missing_mandatory)
        self.assertFalse(gate.passed)

    def test_unknown_mode_raises(self):
        r = _normalize(_FULL)
        with self.assertRaises(ValueError):
            cov.gate_plan_coverage(r.document_plan, r.sections, mode="bogus")


# ---------------------------------------------------------------------------
class LoadPlanFromDirTests(unittest.TestCase):
    """``load_plan_from_dir`` reads the exact on-disk artifacts Phase 3 reads."""

    def test_reads_written_plan_and_gates(self):
        tmp = tempfile.mkdtemp(prefix="enh_load_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        plans = os.path.join(tmp, "plans")
        writer.write_all(plans, _normalize(_FULL), strict=False, strict_pass=True)
        dp, sections = cov.load_plan_from_dir(plans)
        gate = cov.gate_plan_coverage(dp, sections, mode=cov.MODE_ENHANCEMENT)
        self.assertTrue(gate.passed)

    def test_missing_plan_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            cov.load_plan_from_dir("/no/such/plans/dir")


# ---------------------------------------------------------------------------
class IntegratedNormalizePlanGateTests(unittest.TestCase):
    """The gate as it actually runs inside ``normalize-plan`` at the Phase 2
    boundary (real parse → normalize → write → gate, over a minimal bundle)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="enh_gate_cmd_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bundle = os.path.join(self.tmp, "bundle")
        os.makedirs(self.bundle)
        self.plans = os.path.join(self.bundle, "plans")

    def _write_raw(self, rows) -> str:
        p = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_raw_response(rows))
        return p

    def _args(self, raw, **over):
        base = dict(bundle=self.bundle, raw_response=raw, out_dir=None,
                    strict=False, provider="test", coverage_mode="enhancement")
        base.update(over)
        return SimpleNamespace(**base)

    def _gate_json(self):
        return util.read_json(os.path.join(self.plans, "coverage-gate.json"))

    def _sections(self):
        rows = list(util.read_jsonl(os.path.join(self.plans, "section-plans.jsonl")))
        return {r["section_id"]: r for r in rows}

    def test_enhancement_passes_on_full_plan(self):
        rc = normalize_plan_cmd.run(self._args(self._write_raw(_FULL)))
        self.assertEqual(rc, 0)
        gate = self._gate_json()
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["report"]["missing_mandatory"], [])
        with open(os.path.join(self.plans, "coverage-gate-report.md")) as f:
            self.assertIn("**PASS**", f.read())

    def test_enhancement_fails_loudly_on_missing_families(self):
        rc = normalize_plan_cmd.run(
            self._args(self._write_raw(_drop(_FULL, DROP_THREE))))
        self.assertEqual(rc, cov.COVERAGE_GATE_FAIL_EXIT)
        gate = self._gate_json()
        self.assertFalse(gate["passed"])
        self.assertEqual(set(gate["report"]["missing_mandatory"]),
                         {"frontend", "memory", "queue-system"})
        with open(os.path.join(self.plans, "coverage-gate-report.md")) as f:
            md = f.read()
        self.assertIn("**FAIL**", md)
        for fam in ("frontend", "memory", "queue-system"):
            self.assertIn(fam, md)

    def test_baseline_default_is_non_breaking(self):
        # a missing-family plan under baseline mode must NOT gate the command,
        # and must not write the enhancement gate artifacts...
        rc = normalize_plan_cmd.run(
            self._args(self._write_raw(_drop(_FULL, DROP_THREE)),
                       coverage_mode="baseline"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(
            os.path.join(self.plans, "coverage-gate.json")))
        # ...but the non-enforcing baseline matrix still rides in the report
        with open(os.path.join(self.plans, "normalization-report.md")) as f:
            self.assertIn("DeepWiki coverage (benchmark, non-enforcing)", f.read())

    def test_missing_coverage_mode_attr_defaults_to_baseline(self):
        # an older arg namespace (no coverage_mode) must behave like baseline
        args = self._args(self._write_raw(_drop(_FULL, {"frontend-app"})))
        delattr(args, "coverage_mode")
        rc = normalize_plan_cmd.run(args)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(
            os.path.join(self.plans, "coverage-gate.json")))

    def test_gate_does_not_synthesize_or_heal_the_plan(self):
        # upstream prevention is by loud failure, never by adding the missing
        # pages/labels — the written plan is exactly what the planner authored.
        normalize_plan_cmd.run(
            self._args(self._write_raw(_drop(_FULL, DROP_THREE))))
        secs = self._sections()
        for missing in DROP_THREE:
            self.assertNotIn(missing, secs)
        all_labels = {lbl for s in secs.values()
                      for lbl in s.get("coverage_labels", [])}
        self.assertNotIn("frontend", all_labels)
        self.assertNotIn("memory", all_labels)
        self.assertNotIn("queue-system", all_labels)

    def test_planning_fields_survive_through_command(self):
        normalize_plan_cmd.run(self._args(self._write_raw(_FULL)))
        secs = self._sections()
        # coverage_labels[], parent_section_id, merged required_topics[],
        # expected_sources[] all survive normalization end-to-end
        self.assertEqual(secs["frontend-app"]["coverage_labels"], ["frontend"])
        self.assertEqual(secs["retrieval-internals"]["parent_section_id"],
                         "subsystems")
        self.assertEqual(secs["retrieval-internals"]["expected_sources"],
                         ["rag/nlp/search.py"])
        self.assertIn("task lifecycle and workers",
                      secs["task-queues"]["required_topics"])


# ---------------------------------------------------------------------------
class PromptCoverageSignalReferenceTests(unittest.TestCase):
    """Every planner surface explicitly cites planning-coverage-signals.md as
    planner CONTEXT, not citeable evidence, so the obligation survives fallbacks."""

    GEM_DIR = os.path.join(ROOT, "gemini-gem")
    # a context-only disclaimer must appear near the reference
    NOT_CITEABLE = ("not citeable", "never citeable", "context only",
                    "context, not", "not source evidence")

    def _read(self, name):
        with open(os.path.join(self.GEM_DIR, name), encoding="utf-8") as f:
            return f.read()

    def _assert_context_only(self, text, name):
        self.assertIn("planning-coverage-signals.md", text, name)
        low = text.lower()
        self.assertTrue(any(p in low for p in self.NOT_CITEABLE),
                        f"{name}: no context-only disclaimer near the reference")

    def test_gem_instructions(self):
        self._assert_context_only(self._read("GEM_INSTRUCTIONS.md"),
                                  "GEM_INSTRUCTIONS.md")

    def test_kickoff_prompt(self):
        self._assert_context_only(self._read("KICKOFF_PROMPT.md"),
                                  "KICKOFF_PROMPT.md")

    def test_plan_default_system(self):
        from wiki_generator.libs.commands import plan
        self._assert_context_only(plan._DEFAULT_SYSTEM, "plan._DEFAULT_SYSTEM")

    def test_plan_default_kickoff(self):
        from wiki_generator.libs.commands import plan
        self._assert_context_only(plan._DEFAULT_KICKOFF, "plan._DEFAULT_KICKOFF")

    def test_upload_bundle_readme(self):
        from wiki_generator.libs.digest.upload_package import _readme
        text = _readme("/repo", "bundle", "2026-01-01",
                       ["planning-coverage-signals.md"])
        self._assert_context_only(text, "_readme")


# ---------------------------------------------------------------------------
class Milestone1IntactTests(unittest.TestCase):
    """The enhancement gate must not weaken Milestone 1 citation discipline."""

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
