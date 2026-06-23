"""Phase 2 Step 1 (`plan`) — truncated-response guard.

gemini-2.5-pro is a thinking model and shares ``--max-output-tokens`` between its
reasoning and its visible output, so a cap that is too small returns a partial
body with ``finish_reason=MAX_TOKENS``. ``plan`` must fail loudly on that instead
of silently writing a truncated plan that ``normalize-plan`` would then consume.
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import unittest
from unittest import mock

from wiki_generator.libs.commands import plan as plan_cmd

try:
    from google import genai  # noqa: F401
    HAVE_GENAI = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_GENAI = False


class _Reason:
    def __init__(self, name):
        self.name = name


class _Candidate:
    def __init__(self, reason):
        self.finish_reason = reason


class _Usage:
    prompt_token_count = 100
    candidates_token_count = 50
    total_token_count = 150


class _Resp:
    def __init__(self, text, reason=None, *, reason_has_name=True):
        self.text = text
        if reason is None:
            self.candidates = []
        else:
            self.candidates = [_Candidate(_Reason(reason) if reason_has_name else reason)]
        self.usage_metadata = _Usage()


class _FakeModels:
    def __init__(self, resp):
        self._resp = resp

    def generate_content(self, **_kw):
        return self._resp


class _FakeClient:
    def __init__(self, resp):
        self.models = _FakeModels(resp)


class FinishReasonNameTests(unittest.TestCase):
    def test_enum_like_uses_name(self):
        self.assertEqual(plan_cmd._finish_reason_name(_Resp("x", "MAX_TOKENS")), "MAX_TOKENS")

    def test_plain_value_is_stringified(self):
        self.assertEqual(
            plan_cmd._finish_reason_name(_Resp("x", "STOP", reason_has_name=False)), "STOP")

    def test_no_candidates_is_empty(self):
        self.assertEqual(plan_cmd._finish_reason_name(_Resp("x", None)), "")

    def test_missing_finish_reason_is_empty(self):
        class _C:
            pass

        class _R:
            text = "x"
            candidates = [_C()]

        self.assertEqual(plan_cmd._finish_reason_name(_R()), "")


@unittest.skipUnless(HAVE_GENAI, "google-genai SDK not installed")
class PlanTruncationGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wiki-plan-trunc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        bundle_dir = os.path.join(self.tmp, "planner-digest")
        os.makedirs(bundle_dir)
        with open(os.path.join(bundle_dir, "planner-upload-bundle.md"), "w") as f:
            f.write("# bundle\n\nsome planner content for the upload\n")
        self.out_path = os.path.join(self.tmp, "plans", "phase2-gemini-response.md")

    def _args(self, max_output_tokens=8192):
        return argparse.Namespace(
            bundle=self.tmp, project="test-project", provider="gemini",
            max_output_tokens=max_output_tokens, temperature=0.1,
        )

    def _run_with(self, resp):
        with mock.patch.object(genai, "Client", lambda **_kw: _FakeClient(resp)):
            return plan_cmd.run(self._args())

    def test_max_tokens_truncation_fails_and_writes_nothing(self):
        rc = self._run_with(_Resp('{"section_id":"configuration","title":"Conf', "MAX_TOKENS"))
        self.assertEqual(rc, 1)
        self.assertFalse(
            os.path.exists(self.out_path),
            "a truncated plan must not be written as the canonical response")

    def test_complete_stop_response_succeeds_and_writes(self):
        rc = self._run_with(_Resp("```json\n{}\n```\nfull plan body\n", "STOP"))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self.out_path))
        self.assertIn("full plan body", open(self.out_path).read())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
