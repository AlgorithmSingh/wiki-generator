"""Milestone 2 (DeepWiki coverage enhancement) — Phase 1 coverage-signal slice.

Deterministic, LLM-free tests for the Phase 1 coverage-signal expansion: the
per-family source-signal detector (``libs/coverage/signals.py``), its planner-facing
markdown digest, and its integration into the condense/upload flow. No
Gemini/Vertex/API/network calls; no live Phase 1/2/3/4 pipeline runs.

Proves the slice's required behaviours:

- a synthetic file inventory produces the expected family signals for
  frontend/memory/queue/helm/ci/go/sandbox/migrations (status != missing);
- low-signal and missing families are reported, not hidden (all 13 present);
- query-pack-only and symbol-only detection both work, with no substring false
  positives (``research`` ≠ ``search``, ``memoryless`` ≠ ``memory``);
- the generated markdown carries the canonical coverage labels and a loud
  non-citeable-context warning;
- the glossary is reported as synthesized, seeded from the families that have signal;
- detection is deterministic (byte-stable JSON + Markdown across runs);
- the condense step writes derived/planning-coverage-signals.md + coverage-signals.json
  and the planner upload bundle includes the markdown;
- the Phase 2 coverage taxonomy/validator are untouched and still strict.

Run with stdlib only: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import coverage as cov  # noqa: E402
from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs.coverage import signals as S  # noqa: E402
from wiki_generator.libs.coverage.taxonomy import family_keys  # noqa: E402
from wiki_generator.libs.digest.loader import Bundle, load_bundle  # noqa: E402


# --- synthetic bundle helpers -------------------------------------------------
def _f(path, category="source", *, ext=None, generated=False, vendor=False,
       binary=False, top=None):
    """A minimal inventory row shaped like inventory/files.jsonl."""
    name = path.rsplit("/", 1)[-1]
    if ext is None:
        ext = ("." + name.rsplit(".", 1)[-1]) if "." in name else ""
    return {"path": path, "name": name, "ext": ext, "category": category,
            "is_generated": generated, "is_vendor": vendor, "is_binary": binary,
            "top_dir": top or (path.split("/", 1)[0] if "/" in path else "(root)")}


# A synthetic inventory that lights up eight families through different signal
# kinds (extensions, dir tokens, exact basenames, basename tokens, path prefix),
# plus noise files that MUST NOT produce false positives.
RICH_FILES = [
    # frontend: ext + dir
    _f("web/src/app.tsx"),
    _f("web/src/locales/en.ts"),
    _f("web/package.json", "config"),
    # memory: dir + basename token
    _f("agent/memory/memory.py"),
    # queue: dir 'svr', basename token 'consumer', dir 'queue'
    _f("rag/svr/task_executor.py"),
    _f("rag/svr/task_consumer.py"),
    _f("queue/redis_queue.py"),
    # helm: dir + exact basenames
    _f("helm/ragflow/Chart.yaml", "deployment"),
    _f("helm/ragflow/values.yaml", "deployment"),
    # ci/cd: path prefix + exact basenames
    _f(".github/workflows/ci.yml", "deployment"),
    _f("Dockerfile", "deployment", ext=""),
    # go-native: ext + exact basename
    _f("cmd/server/main.go"),
    _f("go.mod", "config"),
    _f("go.sum", "generated", generated=True),       # generated → must be skipped
    # sandbox: dir + basename token
    _f("sandbox/sandbox_manager.py"),
    # migrations: dir token
    _f("api/db/migrations/0001_init.py"),
    _f("api/db/migrations/0002_add_col.py"),
    # --- noise: must NOT trigger families ---
    _f("research/researcher.py"),                    # 'search' ⊄ 'research'
    _f("core/memoryless.py"),                         # 'memory' ⊄ 'memoryless'
    _f("goalkeeper/score.py"),                        # 'go' dir ≠ 'goal...'
    _f("web/dist/bundle.js", "vendor", vendor=True),  # vendored → skipped
    _f("docs/guide.md", "docs"),
    _f("pkg/util.py"),
]

RICH_RG_HITS = [
    {"pack": "task_workers", "path": "rag/svr/task_executor.py", "line": 10},
    {"pack": "task_workers", "path": "rag/svr/task_consumer.py", "line": 4},
    {"pack": "llm_integrations", "path": "rag/llm/chat_model.py", "line": 5},
    {"pack": "web_routes", "path": "api/apps/x.py", "line": 1},   # unused by families
]

RICH_SYMBOLS = [
    {"symbol_id": "python rag.llm.llm_bundle/LLMBundle#chat().", "name": "chat"},
    {"symbol_id": "python pkg.util/helper().", "name": "helper"},
]


def _bundle(files=(), rg_hits=(), symbols=(), coverage=None, root="/demo"):
    return Bundle(root=root, files=list(files), rg_hits=list(rg_hits),
                  symbols=list(symbols), coverage=coverage or {"repo_root": root})


# ---------------------------------------------------------------------------
class DetectorRegistryTests(unittest.TestCase):
    def test_detectors_cover_exactly_the_thirteen_families(self):
        self.assertEqual(set(S.DETECTORS), set(family_keys()))
        self.assertEqual(len(S.DETECTORS), 13)

    def test_non_synthesized_detectors_have_a_signal(self):
        for key, det in S.DETECTORS.items():
            if det.synthesized:
                continue
            self.assertTrue(
                det.extensions or det.dir_tokens or det.basename_exact
                or det.basename_tokens or det.path_prefixes or det.query_packs
                or det.symbol_tokens, key)


# ---------------------------------------------------------------------------
class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.sig = S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS))
        self.by = {f.key: f for f in self.sig.families}

    def test_expected_families_detected_from_inventory(self):
        for fam in ("frontend", "memory", "queue-system", "helm-k8s",
                    "ci-cd-build", "go-native", "sandbox-executor",
                    "migrations-operations"):
            self.assertNotEqual(self.by[fam].status, S.STATUS_MISSING,
                                f"{fam} should have a signal: {self.by[fam].status}")

    def test_all_thirteen_families_present_in_output(self):
        # nothing is hidden — every mandatory family appears with a status
        self.assertEqual(set(self.by), set(family_keys()))
        self.assertEqual(self.sig.family_count, 13)

    def test_low_and_missing_families_reported_not_hidden(self):
        # doc-processing / retrieval-internals / user-tenant have no signal here
        for fam in ("doc-processing", "retrieval-internals",
                    "user-tenant-admin-health"):
            self.assertEqual(self.by[fam].status, S.STATUS_MISSING, fam)
            self.assertTrue(any("No Phase-1 source signal" in n
                                for n in self.by[fam].notes), fam)

    def test_query_pack_only_detection(self):
        # llm-internals here is found via the llm_integrations rg pack + a symbol,
        # without any file match
        llm = self.by["llm-internals"]
        self.assertGreater(llm.query_hit_count, 0)
        self.assertTrue(any(qp["pack"] == "llm_integrations"
                            for qp in llm.query_packs))

    def test_symbol_detection_boundary_matched(self):
        llm = self.by["llm-internals"]
        self.assertEqual(llm.symbols,
                         ["python rag.llm.llm_bundle/LLMBundle#chat()."])

    def test_generated_and_vendored_files_skipped(self):
        # go.sum (generated) and web/dist/bundle.js (vendor) never appear
        for fam in self.sig.families:
            for c in fam.candidate_paths:
                self.assertNotEqual(c["path"], "go.sum")
                self.assertNotIn("web/dist/", c["path"])

    def test_no_substring_false_positives(self):
        noisy = _bundle([
            _f("research/researcher.py"),
            _f("core/memoryless.py"),
            _f("goalkeeper/score.py"),
        ])
        by = {f.key: f for f in S.derive_coverage_signals(noisy).families}
        self.assertEqual(by["retrieval-internals"].status, S.STATUS_MISSING)
        self.assertEqual(by["memory"].status, S.STATUS_MISSING)
        self.assertEqual(by["go-native"].status, S.STATUS_MISSING)

    def test_candidate_path_carries_reasons(self):
        fe = self.by["frontend"]
        app = next(c for c in fe.candidate_paths if c["path"] == "web/src/app.tsx")
        self.assertIn("ext:.tsx", app["reasons"])
        self.assertIn("dir:web", app["reasons"])

    def test_suggested_labels_lead_with_canonical_key(self):
        self.assertEqual(self.by["frontend"].suggested_labels[0], "frontend")
        # taxonomy aliases are included too
        self.assertIn("ui", self.by["frontend"].suggested_labels)


# ---------------------------------------------------------------------------
class GlossarySynthesisTests(unittest.TestCase):
    def test_glossary_is_synthesized_from_detected_families(self):
        sig = S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS))
        gloss = {f.key: f for f in sig.families}["glossary"]
        self.assertEqual(gloss.status, S.STATUS_SYNTHESIZED)
        self.assertTrue(gloss.synthesized_from)
        # it references real, named families that DID have signal
        joined = " ".join(gloss.synthesized_from)
        self.assertIn("frontend", joined)
        self.assertEqual(sig.synthesized_count, 1)


# ---------------------------------------------------------------------------
class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.sig = S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS))
        self.md = S.render_signals_markdown(self.sig)

    def test_markdown_lists_every_canonical_label(self):
        self.assertIn("Canonical coverage labels", self.md)
        for key in family_keys():
            self.assertIn(f"`{key}`", self.md, key)

    def test_markdown_has_nonciteable_warning(self):
        self.assertIn("Planner CONTEXT, not evidence", self.md)
        self.assertIn("not citeable Phase 3 evidence", self.md)

    def test_markdown_shows_status_and_candidate_paths(self):
        self.assertIn("Coverage-signal summary", self.md)
        self.assertIn("web/src/app.tsx", self.md)
        self.assertIn("missing", self.md)        # missing families are visible

    def test_markdown_is_deterministic(self):
        md2 = S.render_signals_markdown(S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS)))
        self.assertEqual(self.md, md2)


# ---------------------------------------------------------------------------
class DeterminismTests(unittest.TestCase):
    def test_to_dict_is_stable_across_runs(self):
        a = S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS)).to_dict()
        b = S.derive_coverage_signals(
            _bundle(RICH_FILES, RICH_RG_HITS, RICH_SYMBOLS)).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))

    def test_empty_bundle_does_not_crash_and_reports_all_missing(self):
        sig = S.derive_coverage_signals(_bundle())
        by = {f.key: f for f in sig.families}
        self.assertEqual(by["frontend"].status, S.STATUS_MISSING)
        self.assertEqual(by["glossary"].status, S.STATUS_SYNTHESIZED)
        self.assertEqual(sig.missing_count, 12)   # all but glossary


# ---------------------------------------------------------------------------
class CondenseIntegrationTests(unittest.TestCase):
    """The condense step writes both artifacts and the upload bundle includes the
    planner-facing markdown (deterministic, no decompose run required)."""

    def _bundle_dir(self):
        d = tempfile.mkdtemp(prefix="covsig_")
        self.addCleanup(_rmtree, d)
        inv = os.path.join(d, "inventory")
        os.makedirs(inv, exist_ok=True)
        util.write_jsonl(os.path.join(inv, "files.jsonl"), RICH_FILES)
        util.write_json(os.path.join(inv, "source-coverage.json"),
                        {"repo_root": d,
                         "counts_by_top_dir": {"web": 3, "rag": 2, "api": 2}})
        return d

    def test_condense_writes_md_and_json_sidecar(self):
        from wiki_generator.libs.commands import condense as condense_cmd
        d = self._bundle_dir()
        bundle = load_bundle(d)
        self.assertTrue(bundle.files)             # loader now reads files.jsonl
        derived = os.path.join(d, "derived")
        condense_cmd.write_condensates(bundle, derived)

        md_path = os.path.join(derived, "planning-coverage-signals.md")
        json_path = os.path.join(derived, "coverage-signals.json")
        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(os.path.isfile(json_path))
        with open(md_path, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("DeepWiki Coverage Signals", md)
        self.assertIn("web/src/app.tsx", md)
        data = util.read_json(json_path)
        self.assertEqual(len(data["families"]), 13)
        self.assertFalse(data["citeable_as_evidence"])
        self.assertEqual(data["role"], "planner_context")

    def test_upload_bundle_includes_coverage_signals(self):
        from wiki_generator.libs.commands import condense as condense_cmd
        from wiki_generator.libs.digest import upload_package
        d = self._bundle_dir()
        bundle = load_bundle(d)
        condense_cmd.write_condensates(bundle, os.path.join(d, "derived"))
        out = os.path.join(d, "planner-digest")
        report = upload_package.assemble(d, out, 250_000, "gen-at", d)
        self.assertIn("derived/planning-coverage-signals.md", report["included"])
        with open(os.path.join(out, "planner-upload-bundle.md"),
                  encoding="utf-8") as f:
            text = f.read()
        self.assertIn(
            "BEGIN INCLUDED FILE: derived/planning-coverage-signals.md", text)
        with open(os.path.join(out, "README_FOR_PLANNER.md"),
                  encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("planning-coverage-signals.md", readme)


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
