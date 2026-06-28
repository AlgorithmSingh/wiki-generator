"""Phase 4 grounded claim/token planning tests — deterministic, no live model.

Proves the upstream terminal-token-prevention foundation:

- ``token_bank`` extracts only verbatim-grounded terminal tokens (the grounding
  invariant), assigns stable ids, and never fabricates a dotted/route/JSON-path
  composite that is not present verbatim in evidence.
- ``claim_plan.validate_claim_plan`` deterministically rejects plans that cite
  unknown/disallowed evidence or tokens, break token-evidence linkage, free-type a
  terminal technical token instead of using a placeholder, write inline citations,
  or (enhancement) leave a required topic unplanned.
- Composite synthesis (``quart_auth.AuthUser``, ``Parser._pdf``,
  ``HttpClient.request``, ``/api/{api_version}``, ``data.graph``, ``/api/v1/...``)
  is rejected unless the exact composite exists in the token bank, and accepted
  when it does.
- ``claim_plan.render_section`` renders Markdown deterministically from an accepted
  plan and that Markdown passes the EXISTING strict section validator unchanged;
  enhancement-mode rendering derives ``covered_topics[]`` that passes the generated
  coverage evaluator.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs.writing import claim_plan as cp  # noqa: E402
from wiki_generator.libs.writing import generated_coverage as gencov  # noqa: E402
from wiki_generator.libs.writing import token_bank as tb  # noqa: E402
from wiki_generator.libs.writing.bundle import EvidenceItem  # noqa: E402
from wiki_generator.libs.writing.packet import WritingPacket  # noqa: E402
from wiki_generator.libs.writing.schema import CLAIM_PLAN_SCHEMA_VERSION  # noqa: E402
from wiki_generator.libs.writing.validate import validate_section_draft  # noqa: E402


# --- tiny in-memory bundle ----------------------------------------------------
def ev(eid, sid, source, excerpt, prov=None, conf="exact", lane="file_anchor"):
    return EvidenceItem(evidence_id=eid, section_id=sid, lane=lane,
                        type="source_span", confidence=conf, source=source,
                        excerpt=excerpt, provenance=prov or {}, scores={},
                        packet_path=f"evidence/packets/{sid}.json")


class FakeBundle:
    """Minimal bundle exposing only what token_bank / claim_plan / the section
    validator read: an evidence index, per-section ids, and coverage_mode."""

    def __init__(self, items, coverage_mode="baseline"):
        self.evidence_index = {i.evidence_id: i for i in items}
        self.section_evidence_ids = {}
        for i in items:
            self.section_evidence_ids.setdefault(i.section_id, set()).add(i.evidence_id)
        self.coverage_mode = coverage_mode


def allowed(b, sid):
    return sorted(b.section_evidence_ids[sid])


def validate(plan, bank, b, sid, obligations=None):
    return cp.validate_claim_plan(
        plan, section_id=sid, token_bank=bank, allowed_evidence_ids=allowed(b, sid),
        evidence_index=b.evidence_index, obligations=obligations)


def tok_id(bank, token):
    for t in bank.tokens:
        if t.token == token:
            return t.token_id
    raise AssertionError(f"token {token!r} not in bank: "
                         f"{[t.token for t in bank.tokens]}")


def plan_obj(sid, claims):
    return {"schema_version": CLAIM_PLAN_SCHEMA_VERSION, "section_id": sid,
            "claims": claims}


# --- token bank ---------------------------------------------------------------
class TokenBankTests(unittest.TestCase):
    def _bundle(self):
        return FakeBundle([
            ev("ev:svc:0001", "svc",
               {"path": "pkg/svc.py", "route": "/items", "method": "GET",
                "symbol_name": "work"},
               "from quart_auth import AuthUser\n"
               "class Parser:\n    def _pdf(self):\n        return None\n"
               'CONF_DIR="/ragflow/conf"\n'),
        ])

    def test_extracts_structured_and_excerpt_kinds(self):
        bank = tb.build_token_bank(self._bundle(), "svc")
        kinds = {t.token: t.kind for t in bank.tokens}
        self.assertEqual(kinds.get("/items"), tb.K_ROUTE)
        self.assertEqual(kinds.get("GET"), tb.K_HTTP_METHOD)
        self.assertEqual(kinds.get("pkg/svc.py"), tb.K_FILE_PATH)
        self.assertEqual(kinds.get("work"), tb.K_SYMBOL)
        self.assertEqual(kinds.get("CONF_DIR"), tb.K_ENV_VAR)
        self.assertEqual(kinds.get("quart_auth"), tb.K_MODULE)
        self.assertEqual(kinds.get("from quart_auth import AuthUser"), tb.K_IMPORT)
        for name in ("AuthUser", "Parser", "_pdf"):
            self.assertIn(name, kinds, f"{name} should be a separate symbol token")

    def test_verbatim_invariant_holds(self):
        b = self._bundle()
        bank = tb.build_token_bank(b, "svc")
        self.assertEqual(tb.verify_bank_grounding(b, bank), [])

    def test_import_does_not_create_dotted_composite(self):
        bank = tb.build_token_bank(self._bundle(), "svc")
        toks = {t.token for t in bank.tokens}
        self.assertNotIn("quart_auth.AuthUser", toks)
        self.assertNotIn("Parser._pdf", toks)

    def test_directory_map_tokens_include_trailing_slash(self):
        b = FakeBundle([
            ev("ev:svc:0001", "svc", {"path": "AGENTS.md"},
               "- `api/`: Backend API server.\n- `rag/`: Core RAG logic.\n")])
        bank = tb.build_token_bank(b, "svc")
        kinds = {t.token: t.kind for t in bank.tokens}
        self.assertEqual(kinds.get("api/"), tb.K_FILE_PATH)
        self.assertEqual(kinds.get("rag/"), tb.K_FILE_PATH)
        self.assertEqual(tb.verify_bank_grounding(b, bank), [])

    def test_stable_ids_byte_identical_on_rerun(self):
        b = self._bundle()
        a1 = json.dumps(tb.build_token_bank(b, "svc").to_dict(), sort_keys=True)
        a2 = json.dumps(tb.build_token_bank(b, "svc").to_dict(), sort_keys=True)
        self.assertEqual(a1, a2)

    def test_composite_present_only_when_verbatim(self):
        b = FakeBundle([
            ev("ev:svc:0001", "svc", {"path": "pkg/p.py"},
               "user: quart_auth.AuthUser = current_user\n")])
        bank = tb.build_token_bank(b, "svc")
        self.assertIn("quart_auth.AuthUser", {t.token for t in bank.tokens})
        self.assertEqual(tb.verify_bank_grounding(b, bank), [])


# --- claim-plan validation ----------------------------------------------------
class ClaimPlanValidationTests(unittest.TestCase):
    def setUp(self):
        self.b = FakeBundle([
            ev("ev:svc:0001", "svc", {"path": "pkg/svc.py", "symbol_name": "work"},
               "def work(n):\n    return n\n"),
            ev("ev:svc:0002", "svc", {"route": "/items", "method": "GET"},
               '{"operationId": "list_items"}'),
        ])
        self.bank = tb.build_token_bank(self.b, "svc")
        self.t_path = tok_id(self.bank, "pkg/svc.py")

    def _good_claim(self, **over):
        c = {"claim_id": "c1", "claim_kind": "file_role",
             "evidence_ids": ["ev:svc:0001"], "token_ids": [self.t_path],
             "required_topic": None, "intent": "x",
             "skeleton": f"The module {{{{{self.t_path}}}}} defines the worker."}
        c.update(over)
        return c

    def test_valid_plan_passes(self):
        r = validate(plan_obj("svc", [self._good_claim()]), self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())

    def test_summary_claim_kind_is_valid(self):
        r = validate(plan_obj("svc", [self._good_claim(claim_kind="summary")]),
                     self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())

    def test_no_claims_rejected(self):
        r = validate(plan_obj("svc", []), self.bank, self.b, "svc")
        self.assertFalse(r.ok)
        self.assertIn("no_claims", {v["code"] for v in r.violations})

    def test_unknown_token_id_rejected(self):
        c = self._good_claim(token_ids=["tok:svc:9999"],
                             skeleton="See {{tok:svc:9999}}.")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("unknown_token_id", {v["code"] for v in r.violations})

    def test_token_provenance_is_auto_cited_when_not_listed(self):
        # selects the path token (from ev:svc:0001) but cites only ev:svc:0002.
        # The plan remains valid because token ids carry provenance; rendering adds
        # the token's evidence citation deterministically.
        c = self._good_claim(evidence_ids=["ev:svc:0002"])
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())
        self.assertTrue(any("token provenance" in w for w in r.warnings))
        rendered = cp.render_section(r, token_bank=self.bank, title="Service",
                                     section_id="svc")
        self.assertIn("[ev:svc:0002][ev:svc:0001]", rendered.markdown)
        self.assertEqual(rendered.used_evidence_ids, ["ev:svc:0001", "ev:svc:0002"])

    def test_evidence_not_allowed_rejected(self):
        c = self._good_claim(evidence_ids=["ev:other:0001"])
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("evidence_not_allowed", {v["code"] for v in r.violations})

    def test_claim_uncited_rejected(self):
        c = self._good_claim(evidence_ids=[], token_ids=[], skeleton="Just prose.")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("claim_uncited", {v["code"] for v in r.violations})

    def test_placeholder_not_declared_is_derived_with_warning(self):
        other = tok_id(self.bank, "work")
        c = self._good_claim(token_ids=[self.t_path],
                             skeleton=f"Uses {{{{{other}}}}} undeclared.")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())
        self.assertTrue(any("derived token use" in w for w in r.warnings))
        self.assertIn(other, r.claims[0]["token_ids"])

    def test_inline_citation_in_skeleton_rejected(self):
        c = self._good_claim(skeleton="The worker is here [ev:svc:0001].")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("inline_citation_in_skeleton", {v["code"] for v in r.violations})

    def test_placeholder_text_in_skeleton_rejected_before_render(self):
        c = self._good_claim(
            skeleton="The worker uses placeholder document IDs for queued jobs.")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("placeholder_in_skeleton", {v["code"] for v in r.violations})

    def test_plain_prose_terminal_token_rejected(self):
        c = self._good_claim(
            skeleton="This plain sentence still free-types HttpClient.request.")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("free_typed_terminal_token", {v["code"] for v in r.violations})

    def test_invalid_claim_kind_rejected(self):
        c = self._good_claim(claim_kind="totally-made-up")
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc")
        self.assertIn("invalid_claim_kind", {v["code"] for v in r.violations})

    def test_duplicate_claim_id_rejected(self):
        r = validate(plan_obj("svc", [self._good_claim(), self._good_claim()]),
                     self.bank, self.b, "svc")
        self.assertIn("duplicate_claim_id", {v["code"] for v in r.violations})

    def test_required_topic_derived_from_mapped_evidence(self):
        obligations = [{"topic": "Explain the worker.", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:svc:0001"]}]
        r = validate(plan_obj("svc", [self._good_claim(required_topic=None)]),
                     self.bank, self.b, "svc", obligations=obligations)
        self.assertTrue(r.ok, r.problem_lines())
        self.assertEqual(r.claims[0]["required_topic"], "Explain the worker.")
        self.assertTrue(any("derived" in w and "required_topic" in w
                            for w in r.warnings))

    def test_required_topic_not_planned_rejected(self):
        obligations = [{"topic": "Explain the worker.", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:svc:0002"]}]
        # plan covers only ev:svc:0001, so it cannot be derived for the mapped topic
        r = validate(plan_obj("svc", [self._good_claim(required_topic=None)]),
                     self.bank, self.b, "svc", obligations=obligations)
        self.assertIn("required_topic_not_planned", {v["code"] for v in r.violations})

    def test_required_topic_evidence_not_mapped_rejected(self):
        obligations = [{"topic": "Explain the worker.", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:svc:0002"]}]
        c = self._good_claim(required_topic="Explain the worker.")  # cites ev:svc:0001
        r = validate(plan_obj("svc", [c]), self.bank, self.b, "svc",
                     obligations=obligations)
        self.assertIn("required_topic_evidence_not_mapped",
                      {v["code"] for v in r.violations})


# --- the six required composite-synthesis regressions -------------------------
class CompositeSynthesisRejectionTests(unittest.TestCase):
    """For each composite: with split evidence it is absent from the bank and a
    plan that free-types it is rejected; with the verbatim composite it is banked
    and a plan referencing its placeholder passes."""

    # (label, composite, split-evidence excerpt that does NOT contain the composite)
    CASES = [
        ("import_dotted", "quart_auth.AuthUser",
         "from quart_auth import AuthUser\n"),
        ("class_method", "Parser._pdf",
         "class Parser:\n    def _pdf(self):\n        return None\n"),
        ("client_method", "HttpClient.request",
         "class HttpClient:\n    def request(self, url):\n        return url\n"),
        ("route_template", "/api/{api_version}",
         'self.api_version = "v1"\nbase = f"/api/{self.api_version}/agents"\n'),
        ("json_path", "data.graph",
         '{"data": {"graph": {"nodes": []}}}\n'),
        ("route_family", "/api/v1/...",
         "/api/v1/agents and /api/v1/items are exposed\n"),
    ]

    def test_split_evidence_excludes_composite_and_rejects_freetype(self):
        for label, composite, excerpt in self.CASES:
            with self.subTest(label):
                b = FakeBundle([ev("ev:s:0001", "s", {"path": "pkg/p.py"}, excerpt)])
                bank = tb.build_token_bank(b, "s")
                toks = {t.token for t in bank.tokens}
                self.assertNotIn(composite, toks,
                                 f"{composite!r} must NOT be banked from split evidence")
                self.assertEqual(tb.verify_bank_grounding(b, bank), [])
                # a plan that free-types the composite inline-code is rejected
                anchor = tok_id(bank, "pkg/p.py")
                claim = {"claim_id": "c1", "claim_kind": "file_role",
                         "evidence_ids": ["ev:s:0001"], "token_ids": [anchor],
                         "required_topic": None, "intent": "x",
                         "skeleton": f"The file {{{{{anchor}}}}} uses `{composite}`."}
                r = validate(plan_obj("s", [claim]), bank, b, "s")
                self.assertIn("free_typed_terminal_token",
                              {v["code"] for v in r.violations},
                              f"free-typed {composite!r} should be rejected")

    def test_verbatim_composite_is_banked_and_accepted(self):
        for label, composite, _ in self.CASES:
            with self.subTest(label):
                excerpt = f"Exact reference: {composite}\n"
                b = FakeBundle([ev("ev:s:0001", "s", {"path": "pkg/p.py"}, excerpt)])
                bank = tb.build_token_bank(b, "s")
                toks = {t.token for t in bank.tokens}
                self.assertIn(composite, toks,
                              f"verbatim {composite!r} must be banked")
                self.assertEqual(tb.verify_bank_grounding(b, bank), [])
                tid = tok_id(bank, composite)
                claim = {"claim_id": "c1", "claim_kind": "file_role",
                         "evidence_ids": ["ev:s:0001"], "token_ids": [tid],
                         "required_topic": None, "intent": "x",
                         "skeleton": f"It references {{{{{tid}}}}} exactly."}
                r = validate(plan_obj("s", [claim]), bank, b, "s")
                self.assertTrue(r.ok, (label, r.problem_lines()))


# --- deterministic rendering --------------------------------------------------
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.b = FakeBundle([
            ev("ev:svc:0001", "svc", {"path": "pkg/svc.py", "symbol_name": "work"},
               "def work(n):\n    return n\n"),
            ev("ev:svc:0002", "svc", {"route": "/items", "method": "GET"},
               '{"operationId": "list_items"}'),
        ])
        self.bank = tb.build_token_bank(self.b, "svc")
        self.t_path = tok_id(self.bank, "pkg/svc.py")
        self.t_route = tok_id(self.bank, "/items")

    def test_renders_substituted_tokens_and_appended_citations(self):
        claim = {"claim_id": "c1", "claim_kind": "file_role",
                 "evidence_ids": ["ev:svc:0001"], "token_ids": [self.t_path],
                 "required_topic": None, "intent": "x",
                 "skeleton": f"The {{{{{self.t_path}}}}} module defines the worker."}
        r = validate(plan_obj("svc", [claim]), self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())
        rendered = cp.render_section(r, token_bank=self.bank, title="Service",
                                     section_id="svc")
        self.assertIn("`pkg/svc.py`", rendered.markdown)
        self.assertIn("[ev:svc:0001]", rendered.markdown)
        self.assertNotIn("{{", rendered.markdown)
        self.assertEqual(rendered.used_evidence_ids, ["ev:svc:0001"])

    def test_rendered_markdown_passes_existing_section_validator(self):
        claims = [
            {"claim_id": "c1", "claim_kind": "file_role",
             "evidence_ids": ["ev:svc:0001"], "token_ids": [self.t_path],
             "required_topic": None, "intent": "x",
             "skeleton": f"The {{{{{self.t_path}}}}} module defines the worker."},
            {"claim_id": "c2", "claim_kind": "api_route",
             "evidence_ids": ["ev:svc:0002"], "token_ids": [self.t_route],
             "required_topic": None, "intent": "y",
             "skeleton": f"The {{{{{self.t_route}}}}} endpoint lists items."},
        ]
        r = validate(plan_obj("svc", claims), self.bank, self.b, "svc")
        self.assertTrue(r.ok, r.problem_lines())
        rendered = cp.render_section(r, token_bank=self.bank, title="Service",
                                     section_id="svc")
        draft = cp.rendered_draft(rendered)
        v = validate_section_draft(section_id="svc", draft=draft, parse_note="ok",
                                   finish_reason="STOP", bundle=self.b)
        self.assertEqual(v.status, "pass", [vi for vi in v.violations])

    def test_enhancement_covered_topics_render_and_pass_evaluator(self):
        obligations = [{"topic": "Explain the worker.", "is_obligation": True,
                        "mapped_evidence_ids": ["ev:svc:0001"], "min_items": 1,
                        "evidenced_status": "sufficient"}]
        claim = {"claim_id": "c1", "claim_kind": "file_role",
                 "evidence_ids": ["ev:svc:0001"], "token_ids": [self.t_path],
                 "required_topic": "Explain the worker.", "intent": "x",
                 "skeleton": f"The {{{{{self.t_path}}}}} module defines the worker."}
        r = validate(plan_obj("svc", [claim]), self.bank, self.b, "svc",
                     obligations=obligations)
        self.assertTrue(r.ok, r.problem_lines())
        rendered = cp.render_section(r, token_bank=self.bank, title="Service",
                                     section_id="svc", obligations=obligations)
        self.assertIsNotNone(rendered.covered_topics)
        row = rendered.covered_topics[0]
        self.assertEqual(row["status"], gencov.GEN_COVERED)
        self.assertEqual(row["evidence_ids"], ["ev:svc:0001"])
        self.assertIn("### Explain the worker.", rendered.markdown)
        # the deterministic generated-coverage evaluator accepts the rendered output
        result = gencov.evaluate_section_coverage(
            obligations=[{"topic": "Explain the worker.", "is_obligation": True,
                          "mapped_evidence_ids": ["ev:svc:0001"],
                          "evidenced_status": "sufficient"}],
            covered_topics=rendered.covered_topics, markdown=rendered.markdown,
            evidence_index=self.b.evidence_index, manifest_ids={"ev:svc:0001"})
        self.assertEqual(result["failures"], [])


# --- end-to-end grounded write-wiki (fake provider, no live model) ------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shutil  # noqa: E402
import tempfile  # noqa: E402

from test_phase4 import make_bundle, opts_for  # noqa: E402
from wiki_generator.libs import util, writing  # noqa: E402
from wiki_generator.libs.writing import bundle as wbundle  # noqa: E402
from wiki_generator.libs.writing.errors import WritingValidationFailure  # noqa: E402
from wiki_generator.libs.writing.provider import SectionResponse  # noqa: E402


class _PlanProvider:
    """Returns canned claim-plan responses. ``by_section`` maps section_id -> a JSON
    string or a list of strings (one per successive call, to exercise re-prompts)."""

    def __init__(self, by_section, mode="vertex-ai", model="fake-model"):
        self.mode = mode
        self.model = model
        self.by_section = by_section
        self.calls: list = []

    def generate(self, section_id, prompt):
        self.calls.append(section_id)
        val = self.by_section.get(section_id)
        if isinstance(val, list):
            n = sum(1 for c in self.calls if c == section_id) - 1
            val = val[min(n, len(val) - 1)]
        return SectionResponse(val, "STOP")


def _grounded_plans(root, **opt_kw):
    """Load the gated bundle, build each section's token bank, and author one valid
    claim plan per section from real token ids. Returns (options, plans_by_section)."""
    options = opts_for(root, grounded_claim_plan=True, **opt_kw)
    b = wbundle.load_and_gate(options)
    plans: dict = {}
    for sid in b.section_order:
        bank = tb.build_token_bank(b, sid)
        eids = sorted(b.section_evidence_ids[sid])
        claims = []
        # one claim per evidence id, selecting that evidence's tokens.
        for n, eid in enumerate(eids, 1):
            sel = [t.token_id for t in bank.tokens if eid in t.evidence_ids][:2]
            ph = " ".join("{{%s}}" % t for t in sel)
            claims.append({
                "claim_id": f"c{n}", "claim_kind": "file_role",
                "evidence_ids": [eid], "token_ids": sel, "required_topic": None,
                "intent": "explain", "skeleton": f"This component is described {ph}."})
        plans[sid] = json.dumps(plan_obj(sid, claims))
    return options, plans


class GroundedE2ETests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="phase4-grounded-")
        make_bundle(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_grounded_run_passes_and_writes_all_outputs(self):
        options, plans = _grounded_plans(self.root)
        result = writing.run(options, provider=_PlanProvider(plans))
        self.assertEqual(result.status, "pass", result.message)
        wiki = os.path.join(self.root, "wiki")
        self.assertTrue(os.path.isfile(os.path.join(wiki, "index.md")))
        # token banks + plan-validation audit written per section
        for sid in ("overview", "service"):
            self.assertTrue(os.path.isfile(
                os.path.join(wiki, "audit", "token-banks", f"{sid}.json")))
            self.assertTrue(os.path.isfile(
                os.path.join(wiki, "audit", "plans", f"{sid}.plan-validation.json")))
        doc = util.read_json(os.path.join(wiki, "metadata", "generated-document.json"))
        self.assertTrue(doc["grounded_claim_plan"])
        val = util.read_json(os.path.join(wiki, "validation", "writing-validation.json"))
        self.assertEqual(val["status"], "pass")

    def test_grounded_section_metadata_records_grounded_block(self):
        options, plans = _grounded_plans(self.root)
        writing.run(options, provider=_PlanProvider(plans))
        rows = util.read_jsonl(os.path.join(
            self.root, "wiki", "metadata", "generated-sections.jsonl"))
        for r in rows:
            self.assertIn("grounded", r)
            self.assertGreaterEqual(r["grounded"]["claim_count"], 1)

    def test_grounded_rerun_is_byte_identical(self):
        options, plans = _grounded_plans(self.root)
        writing.run(options, provider=_PlanProvider(plans))
        with open(os.path.join(self.root, "wiki", "index.md"), encoding="utf-8") as f:
            first = f.read()
        writing.run(options, provider=_PlanProvider(plans))
        with open(os.path.join(self.root, "wiki", "index.md"), encoding="utf-8") as f:
            second = f.read()
        self.assertEqual(first, second)

    def test_invalid_plan_freetypes_composite_fails_closed(self):
        # provider free-types `quart_auth.AuthUser` in the skeleton; no re-prompt.
        options = opts_for(self.root, grounded_claim_plan=True, max_rewrite_attempts=0)
        b = wbundle.load_and_gate(options)
        plans: dict = {}
        for sid in b.section_order:
            bank = tb.build_token_bank(b, sid)
            eid = sorted(b.section_evidence_ids[sid])[0]
            sel = [t.token_id for t in bank.tokens if eid in t.evidence_ids][:1]
            ph = "{{%s}}" % sel[0] if sel else ""
            claims = [{"claim_id": "c1", "claim_kind": "file_role",
                       "evidence_ids": [eid], "token_ids": sel,
                       "required_topic": None, "intent": "x",
                       "skeleton": f"It uses `quart_auth.AuthUser` here {ph}."}]
            plans[sid] = json.dumps(plan_obj(sid, claims))
        with self.assertRaises(WritingValidationFailure):
            writing.run(options, provider=_PlanProvider(plans))

    def test_invalid_then_valid_plan_reprompt_succeeds(self):
        options, good = _grounded_plans(self.root, max_rewrite_attempts=1)
        b = wbundle.load_and_gate(options)
        by_section: dict = {}
        for sid in b.section_order:
            bank = tb.build_token_bank(b, sid)
            eid = sorted(b.section_evidence_ids[sid])[0]
            sel = [t.token_id for t in bank.tokens if eid in t.evidence_ids][:1]
            bad = json.dumps(plan_obj(sid, [{
                "claim_id": "c1", "claim_kind": "file_role", "evidence_ids": [eid],
                "token_ids": sel, "required_topic": None, "intent": "x",
                "skeleton": "Free-typed `data.graph` token here."}]))
            by_section[sid] = [bad, good[sid]]   # first invalid, then valid
        result = writing.run(options, provider=_PlanProvider(by_section))
        self.assertEqual(result.status, "pass")
        # a rewrite-attempt audit was written for at least one section
        rw = os.path.join(self.root, "wiki", "audit", "rewrites")
        self.assertTrue(os.path.isdir(rw) and os.listdir(rw))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
