"""Phase 2 readiness iteration 2 — Patch 1/2/3 deterministic behaviour.

Patch 1: directory-like file anchors are routed to search_hints[] as visible,
         non-blocking readiness *warnings* (not failures).
Patch 2: malformed required SectionPlan JSONL rows are never silently skipped —
         they are deterministically repaired when structurally obvious, else
         surfaced as a blocking parse-error diagnostic.
Patch 3: a normal section backed only by internal planning diagnostics
         (derived/planning-gaps.md) is a blocking diagnostic_only_user_section;
         an explicitly-marked controlled provenance/meta section is non-source.

These are pure unit tests over the deterministic normalizer/parser/readiness —
no subprocess, no LLM. The bounded Phase 2 Gemini repair is exercised separately.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from wiki_generator.libs import context_docs
from wiki_generator.libs.plan_normalization import normalize, parse, repair, writer
from wiki_generator.libs.plan_normalization.lookups import Lookups

RAGFLOW_FILES = {
    "agent/component/base.py", "agent/plugin/llm_tool_plugin.py",
    "agent/plugin/README.md", "agent/sandbox/sandbox_spec.md",
    "rag/graphrag/graph_extractor.py", "rag/flow/parser/parser.py",
    "test/unit_test/test_x.py", "test/testcases/test_y.py",
    "conf/mapping.json", "api/db/db_models.py",
}


def _lookups(files=RAGFLOW_FILES, symbols=()):
    lk = Lookups("/tmp/wiki-readiness-test")
    lk.files = set(files)
    for sid in symbols:
        lk._by_id[sid] = {"symbol_id": sid}
    return lk


def _normalize(section_plan, *, files=RAGFLOW_FILES, symbols=(),
               doc_sections=None, doc_extra=None):
    sid = section_plan.get("section_id")
    meta = doc_sections or [{"id": sid, "title": section_plan.get("title") or sid}]
    doc = {"sections": meta}
    if doc_extra:
        doc.update(doc_extra)
    raw = parse.RawPlan(document_plan=doc, section_plans=[section_plan])
    return normalize.normalize(raw, _lookups(files, symbols), "plans/raw.md", "test")


def _section(result, sid):
    return next(s for s in result.sections if s["section_id"] == sid)


# ---------------------------------------------------------------------------
class DirectoryLikeClassificationTests(unittest.TestCase):
    """Patch 1: deterministic directory-like classification (inventory only)."""

    def setUp(self):
        self.lk = _lookups()

    def test_trailing_slash_is_directory_like(self):
        for ref in ("agent/component/", "agent/plugin/", "agent/sandbox/",
                    "rag/graphrag/", "test/unit_test/", "test/testcases/"):
            self.assertTrue(self.lk.is_directory_like(ref), ref)

    def test_path_prefix_without_slash_is_directory_like(self):
        # A directory proven by the inventory (files live under it) — no slash.
        self.assertTrue(self.lk.is_directory_like("agent/component"))
        self.assertTrue(self.lk.is_directory_like("agent/plugin"))

    def test_exact_file_is_not_directory_like(self):
        for ref in ("agent/component/base.py", "agent/plugin/llm_tool_plugin.py",
                    "agent/sandbox/sandbox_spec.md"):
            self.assertFalse(self.lk.is_directory_like(ref), ref)

    def test_nonexistent_exact_looking_file_is_not_directory_like(self):
        # conf/config.yaml looks like a file and does not exist -> NOT directory-like
        # (it stays a genuine readiness failure, like not/a/real/file.py).
        self.assertFalse(self.lk.is_directory_like("conf/config.yaml"))
        self.assertFalse(self.lk.is_directory_like("not/a/real/file.py"))

    def test_anchor_is_ignored(self):
        self.assertTrue(self.lk.is_directory_like("agent/component/:1-10"))


# ---------------------------------------------------------------------------
class Patch1RoutingTests(unittest.TestCase):
    """Patch 1: routing directory anchors to search_hints[] as warnings."""

    def _agent_subsystem(self):
        return _normalize({
            "section_id": "agent-subsystem", "title": "Agent Subsystem",
            "evidence_needs": {"file_anchors": ["agent/component/", "agent/plugin/",
                                                "agent/sandbox/"]}})

    def test_routed_dirs_leave_exact_files_lane(self):
        r = self._agent_subsystem()
        files = _section(r, "agent-subsystem")["retrieval_needs"]["files"]
        self.assertEqual(files, [])  # no directory path left in the exact lane

    def test_routed_dirs_preserved_in_search_hints_with_trace(self):
        r = self._agent_subsystem()
        hints = _section(r, "agent-subsystem")["retrieval_needs"]["search_hints"]
        inputs = {h.get("source_input") for h in hints}
        self.assertEqual(inputs, {"agent/component/", "agent/plugin/", "agent/sandbox/"})
        for h in hints:
            self.assertEqual(h.get("source_field"), "file_anchors[]")

    def test_routed_dirs_are_warnings_not_failures(self):
        r = self._agent_subsystem()
        self.assertTrue(writer.readiness_pass(r))
        fails = writer._readiness_failures(r)
        self.assertEqual(fails["agent-subsystem"], [])
        routed = [u for u in r.unresolved if u["reason"] == "directory_like_routed"]
        self.assertEqual(len(routed), 3)
        self.assertTrue(all(u["blocking"] is False for u in routed))
        self.assertTrue(all(
            u["code"] == "broad_directory_ref_routed_to_search_hints" for u in routed))

    def test_report_lists_routed_warnings_and_counts(self):
        r = self._agent_subsystem()
        md = writer._readiness_report_md(r)
        self.assertIn("Status: PASS", md)
        self.assertIn("Broad directory refs routed to search_hints[]: 3", md)
        self.assertIn("`agent/component/`", md)

    def test_expected_evidence_excludes_files_for_routed_dir(self):
        r = _normalize({"section_id": "s", "title": "S",
                        "evidence_needs": {"file_anchors": ["agent/component/"]}})
        self.assertNotIn("files", _section(r, "s")["expected_evidence_types"])

    def test_exact_file_passes_through(self):
        r = _normalize({"section_id": "s", "title": "S",
                        "evidence_needs": {"file_anchors": ["agent/component/base.py"]}})
        files = _section(r, "s")["retrieval_needs"]["files"]
        self.assertEqual([f["path"] for f in files], ["agent/component/base.py"])
        self.assertFalse([u for u in r.unresolved
                          if u["reason"] == "directory_like_routed"])
        self.assertIn("files", _section(r, "s")["expected_evidence_types"])

    def test_real_exact_lane_failure_not_masked(self):
        # Regression: a routed directory ref warns, but a genuine nonexistent file
        # still fails — overall readiness FAIL.
        r = _normalize({"section_id": "s", "title": "S", "evidence_needs": {
            "file_anchors": ["agent/component/", "not/a/real/file.py"]}})
        self.assertFalse(writer.readiness_pass(r))
        reasons = {f["reason"] for f in writer._readiness_failures(r)["s"]}
        self.assertEqual(reasons, {"no_match"})

    def test_no_active_files_lane_ever_holds_a_directory(self):
        r = self._agent_subsystem()
        for s in r.sections:
            for f in s["retrieval_needs"]["files"]:
                self.assertFalse(f["path"].endswith("/"))

    def test_routed_dir_intent_never_dropped_without_trace(self):
        # Every routed directory ref must be traceable to a search_hint (the broad
        # intent is preserved, never dropped) — else readiness would FAIL.
        r = self._agent_subsystem()
        hints = _section(r, "agent-subsystem")["retrieval_needs"]["search_hints"]
        traced = {h.get("source_input") for h in hints}
        routed = [u for u in r.unresolved if u["reason"] == "directory_like_routed"]
        self.assertTrue(routed)
        for u in routed:
            self.assertIn(u["input"], traced)

    def test_directory_left_in_active_files_lane_fails_readiness(self):
        # Defense-in-depth: the readiness gate itself FAILs a directory-like path in
        # the active exact files lane, independent of normalizer routing.
        r = normalize.Result(
            document_plan={"section_order": ["s"]},
            sections=[{"section_id": "s", "section_role": "source",
                       "retrieval_needs": {"symbols": [], "contracts": [], "tests": [],
                                           "graph_nodes": [], "query_packs": [],
                                           "search_hints": [],
                                           "files": [{"path": "agent/component/",
                                                      "input": "agent/component/"}]}}],
            unresolved=[], warnings=[], raw_document_plan={}, raw_section_plans=[])
        self.assertFalse(writer.readiness_pass(r))
        reasons = {f["reason"] for f in writer._readiness_failures(r)["s"]}
        self.assertIn("directory_like_in_exact_lane", reasons)


# ---------------------------------------------------------------------------
# The exact malformed row observed from the RAGFlow run (bare string after an
# empty verification_needs array).
_BAD = ('{"section_id":"llm-integration","title":"LLM Integration",'
        '"verification_needs":[],'
        '"Lexical query hits for LLM integrations need to be verified to confirm '
        'the exact nature of the integration.","estimated_size":"M"}')
_GOOD = ('{"section_id":"llm-integration","title":"LLM Integration",'
         '"verification_needs":["Lexical query hits for LLM integrations need to '
         'be verified."],"known_gaps":[],"estimated_size":"M"}')


class Patch2ParseTests(unittest.TestCase):
    """Patch 2: malformed SectionPlan JSONL never disappears silently."""

    def _jsonl(self, *lines):
        warnings: list = []
        diags: list = []
        rows = parse._loads_jsonl("\n".join(lines), warnings, "section-plans.jsonl",
                                  diags)
        return rows, warnings, diags

    def test_bad_row_deterministically_repaired_not_skipped(self):
        rows, warnings, diags = self._jsonl(_BAD)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["verification_needs"],
            ["Lexical query hits for LLM integrations need to be verified to "
             "confirm the exact nature of the integration."])
        self.assertEqual(rows[0]["estimated_size"], "M")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["code"],
                         "section_plan_jsonl_deterministically_repaired")
        self.assertEqual(diags[0]["severity"], "warning")
        self.assertEqual(diags[0]["section_id"], "llm-integration")
        self.assertFalse(any("skipped unparseable" in w for w in warnings))

    def test_good_row_parses_with_no_diagnostic(self):
        rows, warnings, diags = self._jsonl(_GOOD)
        self.assertEqual(len(rows), 1)
        self.assertIn("Lexical query hits", rows[0]["verification_needs"][0])
        self.assertEqual(diags, [])
        self.assertEqual(warnings, [])

    def test_unrepairable_row_is_a_blocking_parse_error(self):
        bad = '{"section_id":"x","title":"X" "estimated_size":"M"}'  # missing comma
        rows, warnings, diags = self._jsonl(bad)
        self.assertEqual(rows, [])
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["code"], "section_plan_jsonl_parse_error")
        self.assertEqual(diags[0]["severity"], "failure")
        self.assertEqual(diags[0]["section_id"], "x")  # recovered for routing
        self.assertIn("parse_error", diags[0])

    def test_ambiguous_unkeyed_string_fails_closed(self):
        # An unkeyed string NOT immediately after an empty prose array is not
        # safely repairable -> parse error, not a guess.
        bad = ('{"section_id":"x","title":"X","coverage_requirements":["a"],'
               '"a stray sentence with no key","estimated_size":"M"}')
        rows, _, diags = self._jsonl(bad)
        self.assertEqual(rows, [])
        self.assertEqual(diags[0]["code"], "section_plan_jsonl_parse_error")

    def test_parse_threads_diagnostics_into_rawplan(self):
        text = ("```text\nplans/document-plan.json\n```\n"
                '```json\n{"repo":"x","sections":[{"id":"llm-integration",'
                '"title":"LLM Integration"}]}\n```\n'
                "```text\nplans/section-plans.jsonl\n```\n"
                f"```jsonl\n{_BAD}\n```\n")
        rp = parse.parse(text)
        self.assertEqual(len(rp.section_plans), 1)
        self.assertEqual(len(rp.parse_diagnostics), 1)
        self.assertEqual(rp.parse_diagnostics[0]["code"],
                         "section_plan_jsonl_deterministically_repaired")

    def test_parse_error_surfaces_as_readiness_failure(self):
        raw = parse.RawPlan(
            document_plan={"sections": [{"id": "llm-integration",
                                         "title": "LLM Integration"}]},
            section_plans=[],
            parse_diagnostics=[{"artifact": "section-plans.jsonl", "line": 13,
                                "section_id": "llm-integration", "severity": "failure",
                                "code": "section_plan_jsonl_parse_error",
                                "message": "...", "raw_excerpt": "...",
                                "parse_error": "Expecting ',' : line 1 column 80"}])
        result = normalize.normalize(raw, _lookups(), "plans/raw.md", "test")
        self.assertFalse(writer.readiness_pass(result))
        fails = writer._readiness_failures(result)
        reasons = {f["reason"] for f in fails["llm-integration"]}
        self.assertIn("section_plan_jsonl_parse_error", reasons)
        md = writer._readiness_report_md(result)
        self.assertIn("Malformed planner artifacts", md)
        self.assertIn("line 13", md)
        self.assertIn("llm-integration", md)

    def test_repaired_row_shows_as_warning_in_report(self):
        raw = parse.RawPlan(
            document_plan={"sections": [{"id": "llm-integration",
                                         "title": "LLM Integration"}]},
            section_plans=[{"section_id": "llm-integration",
                            "evidence_needs": {"query_packs": ["llm_integrations"]},
                            "verification_needs": ["x"]}],
            parse_diagnostics=[{"artifact": "section-plans.jsonl", "line": 13,
                                "section_id": "llm-integration", "severity": "warning",
                                "code": "section_plan_jsonl_deterministically_repaired",
                                "repair": "moved unkeyed string token into "
                                          "verification_needs[]", "raw_excerpt": "..."}])
        # query_packs resolution depends on the bundle; readiness still records the
        # repair as a visible, non-blocking warning regardless.
        md = writer._readiness_report_md(
            normalize.normalize(raw, _lookups(), "plans/raw.md", "test"))
        self.assertIn("Deterministic repairs (warning): 1", md)


# ---------------------------------------------------------------------------
class Patch3DiagnosticTests(unittest.TestCase):
    """Patch 3: diagnostics are not source evidence; provenance is non-source."""

    def test_diagnostic_artifact_classifier(self):
        self.assertEqual(context_docs.is_diagnostic_artifact("derived/planning-gaps.md"),
                         "derived/planning-gaps.md")
        self.assertEqual(
            context_docs.is_diagnostic_artifact("planner-digest/planning-gaps.md"),
            "planner-digest/planning-gaps.md")
        # ordinary planner context is NOT a diagnostic
        self.assertIsNone(context_docs.is_diagnostic_artifact("derived/planning-digest.md"))
        self.assertIsNone(context_docs.is_diagnostic_artifact("api/db/db_models.py"))

    def test_diagnostic_only_section_fails_readiness(self):
        r = _normalize({"section_id": "known-gaps", "title": "Known Gaps",
                        "evidence_needs": {
                            "file_anchors": ["derived/planning-gaps.md"],
                            "context_artifacts": ["derived/planning-gaps.md"]}})
        self.assertFalse(writer.readiness_pass(r))
        fails = writer._readiness_failures(r)["known-gaps"]
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0]["reason"], "diagnostic_only_user_section")
        self.assertEqual(fails[0]["secondary"], "no_retrieval_signal")
        # the diagnostic was routed out of the exact files lane to context_artifacts
        sec = _section(r, "known-gaps")
        self.assertEqual(sec["retrieval_needs"]["files"], [])
        self.assertTrue(sec["retrieval_needs"]["context_artifacts"])

    def test_controlled_provenance_section_is_non_source(self):
        r = _normalize({"section_id": "provenance", "title": "Provenance",
                        "role": "provenance", "evidence_needs": {
                            "context_artifacts": ["derived/planning-gaps.md"]}})
        sec = _section(r, "provenance")
        self.assertEqual(sec["section_role"], "provenance")
        self.assertTrue(context_docs.is_provenance_section(sec))
        self.assertTrue(writer.readiness_pass(r))         # not a source failure
        self.assertEqual(writer._readiness_failures(r)["provenance"], [])
        md = writer._readiness_report_md(r)
        self.assertIn("Controlled provenance / meta sections", md)
        self.assertIn("`provenance` (role: provenance, non-source)", md)

    def test_normal_role_default_is_source(self):
        r = _normalize({"section_id": "s", "title": "S",
                        "evidence_needs": {"file_anchors": ["agent/component/base.py"]}})
        self.assertEqual(_section(r, "s")["section_role"], "source")

    def test_section_with_real_signals_plus_diagnostic_passes(self):
        # A genuine section that also references planning-gaps.md as context but has
        # real retrieval signal is a normal section, not diagnostic-only.
        r = _normalize({"section_id": "s", "title": "S", "evidence_needs": {
            "file_anchors": ["agent/component/base.py"],
            "context_artifacts": ["derived/planning-gaps.md"]}})
        self.assertTrue(writer.readiness_pass(r))
        self.assertEqual(writer._readiness_failures(r)["s"], [])

    def test_plain_no_signal_section_is_no_retrieval_signal_not_diagnostic(self):
        r = _normalize({"section_id": "s", "title": "S", "evidence_needs": {}})
        fails = writer._readiness_failures(r)["s"]
        self.assertEqual([f["reason"] for f in fails], ["no_retrieval_signal"])


_GEM_DIR = os.path.join(os.path.dirname(__file__), "..", "gemini-gem")


class PlannerPromptSnapshotTests(unittest.TestCase):
    """Every planner prompt surface carries the Patch 1/2/3 guidance (so the
    stricter rules cannot disappear in a fallback environment)."""

    def _read(self, name):
        with open(os.path.join(_GEM_DIR, name), encoding="utf-8") as f:
            return f.read()

    def _assert_patch_guidance(self, text, *, name):
        # Patch 1: file_anchors exact files only, directories invalid.
        self.assertIn("agent/component/", text, name)
        self.assertTrue("INVALID" in text or "invalid" in text, name)
        # Patch 2: strict JSONL + BAD/GOOD one-shot + prose destinations.
        self.assertIn("verification_needs", text, name)
        self.assertIn("known_gaps", text, name)
        self.assertIn("BAD", text, name)
        self.assertIn("GOOD", text, name)
        # Patch 3: planning-gaps is context, not a section.
        self.assertIn("planning-gaps.md", text, name)

    def test_gem_instructions(self):
        text = self._read("GEM_INSTRUCTIONS.md")
        self._assert_patch_guidance(text, name="GEM_INSTRUCTIONS.md")
        self.assertIn("valid JSONL", text)
        self.assertIn('"role":"provenance"', text)

    def test_kickoff_prompt(self):
        self._assert_patch_guidance(self._read("KICKOFF_PROMPT.md"),
                                    name="KICKOFF_PROMPT.md")

    def test_plan_py_fallback_prompts(self):
        from wiki_generator.libs.commands import plan
        sys_text = plan._DEFAULT_SYSTEM
        self.assertIn("agent/component/", sys_text)
        self.assertIn("valid JSONL", sys_text)
        self.assertIn("verification_needs", sys_text)
        self.assertIn("known_gaps", sys_text)
        self.assertIn("planning-gaps.md", sys_text)
        self.assertIn("Known gaps", sys_text)  # forbids the diagnostics-only section

    def test_upload_bundle_readme_guidance(self):
        from wiki_generator.libs.digest.upload_package import _readme
        text = _readme("/repo", "bundle", "2026-01-01", ["planning-digest.md"])
        self.assertIn("agent/component/", text)
        self.assertIn("INVALID", text)
        self.assertIn("verification_needs", text)
        self.assertIn("known_gaps", text)
        self.assertIn("planning-gaps.md", text)
        self.assertIn("Valid JSONL", text)


def _raw_response(doc_sections, section_lines) -> str:
    return ("```text\nplans/document-plan.json\n```\n"
            "```json\n" + json.dumps({"repo": "x", "sections": doc_sections})
            + "\n```\n"
            "```text\nplans/section-plans.jsonl\n```\n"
            "```jsonl\n" + "\n".join(section_lines) + "\n```\n")


class BoundedRepairTests(unittest.TestCase):
    """Patch 2/3: bounded planner-artifact repair (Gemini client injected)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="repair_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bundle = os.path.join(self.tmp, "bundle")
        inv = os.path.join(self.bundle, "inventory")
        os.makedirs(inv)
        with open(os.path.join(inv, "files.jsonl"), "w") as f:
            for p in ("api/db/db_models.py", "agent/component/base.py"):
                f.write(json.dumps({"path": p, "line_count": 80}) + "\n")
        self.out = os.path.join(self.tmp, "out")

    def _write_raw(self, text) -> str:
        p = os.path.join(self.bundle, "phase2-gemini-response.md")
        with open(p, "w") as f:
            f.write(text)
        return p

    def _readiness(self) -> str:
        with open(os.path.join(self.out, "phase3-readiness-report.md")) as f:
            return f.read()

    def test_no_repair_needed_when_already_ready(self):
        raw = self._write_raw(_raw_response(
            [{"id": "data-models", "title": "Data Models"}],
            [json.dumps({"section_id": "data-models", "title": "Data Models",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}})]))

        def boom(system, user):
            raise AssertionError("client must not be called when already ready")

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=boom)
        self.assertFalse(report["repaired"])
        self.assertEqual(report["attempts"], 0)
        self.assertIn("Status: PASS", self._readiness())

    def test_repair_fixes_unready_plan(self):
        raw = self._write_raw(_raw_response(
            [{"id": "data-models", "title": "Data Models"}],
            [json.dumps({"section_id": "data-models", "title": "Data Models",
                         "evidence_needs": {}})]))  # no signal -> FAIL
        fixed = _raw_response(
            [{"id": "data-models", "title": "Data Models"}],
            [json.dumps({"section_id": "data-models", "title": "Data Models",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}})])
        calls = []

        def fake(system, user):
            calls.append(user)
            return fixed

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=fake)
        self.assertTrue(report["repaired"])
        self.assertEqual(report["attempts"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("Status: PASS", self._readiness())
        # audit artifacts exist
        adir = os.path.join(self.out, "repair", "attempt-1")
        for name in ("repair-request.txt", "errors.json", "repair-response.md",
                     "validation.json", "accepted-response.md"):
            self.assertTrue(os.path.exists(os.path.join(adir, name)), name)

    def test_repair_handles_initial_ambiguous_jsonl_parse_error(self):
        doc_sections = [{"id": "data-models", "title": "Data Models"}]
        live_style_bad = (
            "```json\n" + json.dumps({"repo": "x", "sections": doc_sections}) + "\n```\n"
            "```jsonl\n```\n"
            "```jsonl\n"
            + json.dumps({"section_id": "data-models", "title": "Data Models",
                          "evidence_needs": {}}) + "\n```\n")
        raw = self._write_raw(live_style_bad)
        fixed = _raw_response(
            doc_sections,
            [json.dumps({"section_id": "data-models", "title": "Data Models",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}})])
        calls = []

        def fake(system, user):
            calls.append(user)
            return fixed

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=fake)
        self.assertTrue(report["repaired"])
        self.assertEqual(len(calls), 1)
        self.assertIn("multiple JSONL blocks", calls[0])
        self.assertIn("raw_planning_response_parse_error", open(
            os.path.join(self.out, "repair", "attempt-1", "errors.json")).read())
        self.assertIn("Status: PASS", self._readiness())

    def test_repair_preserves_section_ids_after_initial_parse_error(self):
        doc_sections = [{"id": "s", "title": "S"}]
        live_style_bad = (
            "```json\n" + json.dumps({"repo": "x", "sections": doc_sections}) + "\n```\n"
            "```jsonl\n```\n"
            "```jsonl\n" + json.dumps({"section_id": "s", "title": "S",
                                            "evidence_needs": {}}) + "\n```\n")
        raw = self._write_raw(live_style_bad)
        added = _raw_response(
            [{"id": "s", "title": "S"}, {"id": "invented", "title": "Invented"}],
            [json.dumps({"section_id": "s", "title": "S",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}}),
             json.dumps({"section_id": "invented", "title": "Invented",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}})])

        def fake(system, user):
            return added

        with self.assertRaises(repair.RepairFailed):
            repair.repair_plan(self.bundle, raw, self.out, client_call=fake,
                               max_attempts=1)
        self.assertIn("added sections", open(
            os.path.join(self.out, "repair", "repair-report.md")).read())

    def test_repair_rejects_initial_parse_error_without_document_plan(self):
        raw = self._write_raw("```jsonl\n{}\n```\n")

        def fake(system, user):
            raise AssertionError("client must not be called without a DocumentPlan")

        with self.assertRaises(repair.RepairFailed):
            repair.repair_plan(self.bundle, raw, self.out, client_call=fake)
        report = open(os.path.join(self.out, "repair", "repair-report.md")).read()
        self.assertIn("unambiguous DocumentPlan", report)

    def test_repair_unavailable_fails_loudly(self):
        raw = self._write_raw(_raw_response(
            [{"id": "s", "title": "S"}],
            [json.dumps({"section_id": "s", "title": "S", "evidence_needs": {}})]))
        # No client injected, no project, no api key -> RepairUnavailable.
        with self.assertRaises(repair.RepairUnavailable):
            repair.repair_plan(self.bundle, raw, self.out, project=None, api_key=None)

    def test_repair_failure_after_cap_raises(self):
        raw = self._write_raw(_raw_response(
            [{"id": "s", "title": "S"}],
            [json.dumps({"section_id": "s", "title": "S", "evidence_needs": {}})]))
        still_bad = _raw_response(
            [{"id": "s", "title": "S"}],
            [json.dumps({"section_id": "s", "title": "S", "evidence_needs": {}})])

        def fake(system, user):
            return still_bad

        with self.assertRaises(repair.RepairFailed):
            repair.repair_plan(self.bundle, raw, self.out, client_call=fake,
                               max_attempts=2)
        self.assertIn("FAILED", open(
            os.path.join(self.out, "repair", "repair-report.md")).read())

    def test_repair_rejects_added_section(self):
        raw = self._write_raw(_raw_response(
            [{"id": "s", "title": "S"}],
            [json.dumps({"section_id": "s", "title": "S", "evidence_needs": {}})]))
        added = _raw_response(
            [{"id": "s", "title": "S"}, {"id": "invented", "title": "Invented"}],
            [json.dumps({"section_id": "s", "title": "S",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}}),
             json.dumps({"section_id": "invented", "title": "Invented",
                         "evidence_needs": {"file_anchors": ["api/db/db_models.py"]}})])

        def fake(system, user):
            return added

        with self.assertRaises(repair.RepairFailed):
            repair.repair_plan(self.bundle, raw, self.out, client_call=fake,
                               max_attempts=1)
        report = open(os.path.join(self.out, "repair", "repair-report.md")).read()
        self.assertIn("added sections", report)

    def test_repair_allows_removing_diagnostic_only_section(self):
        raw = self._write_raw(_raw_response(
            [{"id": "overview", "title": "Overview"},
             {"id": "known-gaps", "title": "Known Gaps"}],
            [json.dumps({"section_id": "overview", "title": "Overview",
                         "evidence_needs": {"search_hints": ["repo overview"]}}),
             json.dumps({"section_id": "known-gaps", "title": "Known Gaps",
                         "evidence_needs": {
                             "file_anchors": ["derived/planning-gaps.md"],
                             "context_artifacts": ["derived/planning-gaps.md"]}})]))
        # repaired: known-gaps removed (a sanctioned diagnostic-only removal)
        fixed = _raw_response(
            [{"id": "overview", "title": "Overview"}],
            [json.dumps({"section_id": "overview", "title": "Overview",
                         "evidence_needs": {"search_hints": ["repo overview"]}})])

        def fake(system, user):
            return fixed

        report = repair.repair_plan(self.bundle, raw, self.out, client_call=fake)
        self.assertTrue(report["repaired"])
        self.assertIn("Status: PASS", self._readiness())


if __name__ == "__main__":
    unittest.main()
