"""Deterministic shell-wrapper surface tests (no install, no model, no network).

The three phase wrappers wrap the production ``python -m wiki_generator`` CLI. The
underlying commands already support ``--coverage-mode {baseline,enhancement}``; these
tests prove the wrappers EXPOSE the flag (it appears in ``--help``, which exits before
any venv install) and PASS it through to the CLI (the script source constructs
``--coverage-mode "$COVERAGE_MODE"`` only when the operator set it, keeping the CLI
default — baseline — the single source of truth).

``--help`` short-circuits in the argument loop before ``install_base``/``install_vertex``
runs, so these tests never touch pip/uv/the network and stay fast and deterministic.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

# wrapper -> the CLI subcommand it wraps.
WRAPPERS = {
    "phase2_step2_normalize_plan.sh": "normalize-plan",
    "phase3_retrieve_evidence.sh": "retrieve-evidence",
    "phase4_write_wiki.sh": "write-wiki",
}


def _help(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", os.path.join(SCRIPTS, name), "--help"],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)


def _source(name: str) -> str:
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as f:
        return f.read()


class WrapperCoverageModeSurfaceTests(unittest.TestCase):
    def test_help_exposes_coverage_mode_enhancement(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                res = _help(name)
                self.assertEqual(res.returncode, 0, res.stderr)
                out = res.stdout
                self.assertIn("--coverage-mode", out)
                self.assertIn("enhancement", out)
                self.assertIn("baseline", out)

    def test_source_passes_flag_through_when_set(self):
        # The wrapper must forward the implemented CLI flag (gap was: it did not),
        # and must omit it when unset so the dataclass default stays authoritative.
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                src = _source(name)
                self.assertIn('--coverage-mode "$COVERAGE_MODE"', src)
                # omitted-when-empty guard (non-breaking default)
                self.assertIn('-n "$COVERAGE_MODE"', src)

    def test_help_does_not_install_anything(self):
        # A cheap proxy that --help short-circuits before install: no pip/uv chatter
        # and a clean exit. (install_* would emit "installing wiki-generator".)
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                res = _help(name)
                self.assertNotIn("installing wiki-generator", res.stderr)
                self.assertNotIn("installing wiki-generator", res.stdout)


if __name__ == "__main__":
    sys.exit(unittest.main())
