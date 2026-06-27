"""Phase 4 (write-wiki) tests — fake-provider only, no live Gemini/Vertex.

A tiny *synthetic* but schema-faithful Phase 1-3 bundle is hand-written (matching
the accepted-run shapes: document-plan, section-plans, readiness report,
retrieval-validation with all required contract checks, evidence manifest, and
per-section EvidencePackets with resolvable SHAs). Tests then exercise
``wiki_generator.libs.writing`` with an injected fake provider, plus the CLI via
the ``gemini-gem`` import path (which makes no API call).

Run with stdlib only: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs import util  # noqa: E402
from wiki_generator.libs import writing  # noqa: E402
from wiki_generator.libs.writing import bundle as wbundle  # noqa: E402
from wiki_generator.libs.writing.options import (  # noqa: E402
    PROVIDER_GEMINI_GEM,
    PROVIDER_VERTEX,
    WritingOptions,
)
from wiki_generator.libs.writing.provider import SectionResponse  # noqa: E402

REQUIRED_CONTRACT_CHECKS = (
    "all_sections_have_packets", "document_plan_valid", "section_plans_valid_jsonl",
    "section_plans_cover_order", "capabilities_consistent", "packets_schema_valid",
    "evidence_anchors_resolve", "no_plan_only_evidence", "no_context_artifact_evidence",
)


# --- synthetic-bundle builder -------------------------------------------------
def _section_plan(sid, title, order, *, files=(), contracts=(),
                  search_hints=("orient",), context_artifacts=("derived/planning-digest.md",),
                  expected=()):
    return {
        "schema_version": "phase2-section-plan-v1", "section_id": sid,
        "section_role": "source", "title": title, "order": order, "parent": None,
        "priority": "high", "purpose": f"Document {title}.",
        "goal": f"Understand {title}.", "rationale": "test",
        "required_topics": [f"Explain {title}."], "key_questions": ["What is it?"],
        "retrieval_needs": {
            "query_packs": [], "symbols": [],
            "files": [{"input": f, "path": f, "anchor": None,
                       "anchor_confidence": None, "resolution": "file_exists",
                       "candidates": []} for f in files],
            "contracts": [{"input": c} for c in contracts],
            "tests": [], "graph_nodes": [],
            "search_hints": [{"text": h, "scope": [], "reason": "planner search hint"}
                             for h in search_hints],
            "context_artifacts": [{"path": p, "role": "planner_context",
                                   "citeable_as_evidence": False}
                                  for p in context_artifacts]},
        "expected_evidence_types": list(expected), "depends_on": [],
        "verification_needs": [], "estimated_size": "S", "known_gaps": [],
        "normalization_warnings": []}


def _ev_span(eid, path, sl, el, symbol_id, excerpt, conf="exact"):
    return {"evidence_id": eid, "lane": "file_anchor", "type": "source_span",
            "source": {"artifact": "rag/spans.jsonl", "path": path,
                       "range": {"start_line": sl, "end_line": el},
                       "span_id": f"span:{path}:{sl}-{el}:function",
                       "symbol_id": symbol_id},
            "excerpt": excerpt, "provenance": {"matched_by": "file_range"},
            "scores": {"lane_rank": 1, "lane_score": None, "bm25": None,
                       "vector": None}, "confidence": conf,
            "dedupe_key": f"{path}:{sl}-{el}"}


def _ev_route(eid, route, method, excerpt):
    return {"evidence_id": eid, "lane": "contract", "type": "route_operation",
            "source": {"artifact": "contracts/openapi.json",
                       "json_pointer": f"/paths/~1{route.strip('/')}/{method.lower()}",
                       "route": route, "method": method},
            "excerpt": excerpt, "provenance": {"matched_by": "openapi_operation"},
            "scores": {"lane_rank": 1, "lane_score": None, "bm25": None,
                       "vector": None}, "confidence": "exact",
            "dedupe_key": f"openapi|{route}|{method}"}


def _ev_chunk(eid, path, sl, el, excerpt, conf="medium"):
    return {"evidence_id": eid, "lane": "bm25", "type": "source_chunk",
            "source": {"artifact": "rag/chunks.jsonl", "path": path,
                       "range": {"start_line": sl, "end_line": el},
                       "chunk_id": f"chunk:{path}:{sl}-{el}"},
            "excerpt": excerpt, "provenance": {"matched_by": "bm25"},
            "scores": {"lane_rank": 1, "lane_score": None, "bm25": 2.0,
                       "vector": None}, "confidence": conf,
            "dedupe_key": f"{path}:{sl}-{el}|bm25"}


def _packet(sid, title, order, evidence, sha):
    return {
        "schema_version": "phase3-evidence-packet-v1", "section_id": sid,
        "title": title, "order": order, "retrieval_mode": "lexical-symbolic",
        "source_plan": {"document_plan_path": "plans/document-plan.json",
                        "section_plans_path": "plans/section-plans.jsonl",
                        "section_plan_sha256": sha},
        "work_order": {"purpose": f"Document {title}.", "required_topics": [],
                       "expected_evidence_types": [],
                       "retrieval_needs": {"query_packs": [], "symbols": [],
                                           "files": [], "contracts": [], "tests": [],
                                           "graph_nodes": []},
                       "context_artifacts": ["derived/planning-digest.md"]},
        "evidence": evidence,
        "lane_summary": {"file_anchor": {"requested": 1, "returned": len(evidence),
                                         "status": "pass"}},
        "coverage": {"satisfied": [], "missing": [], "warnings": []},
        "validation": {"status": "pass", "errors": [], "warnings": []}}


# A faithful, minimal regression of the live ev:deployment:0005 excerpt
# (docker/entrypoint.sh shell-variable assignments) that triggered the Iteration 2
# failure. The expanded literal `/ragflow/conf/service_conf.yaml` is NOT a verbatim
# token here; only CONF_FILE / ${CONF_FILE} / ${CONF_DIR}/service_conf.yaml are.
DEPLOYMENT_SHELL_EXCERPT = (
    "# Replace env variables in the service_conf.yaml file\n"
    'CONF_DIR="/ragflow/conf"\n'
    'TEMPLATE_FILE="${CONF_DIR}/service_conf.yaml.template"\n'
    'CONF_FILE="${CONF_DIR}/service_conf.yaml"\n'
    "\n"
    'rm -f "${CONF_FILE}"\n'
    'done < "${TEMPLATE_FILE}"\n'
)


def make_bundle(root, *, with_manifest=True, with_deployment=False):
    """Write a small, schema-faithful, gate-passing Phase 1-3 bundle.

    Two sections: 'overview' (one bm25 chunk citing README) and 'service' (a
    file_anchor span over pkg/svc.py + a GET /items route). With
    ``with_deployment`` a third 'deployment' section is added whose evidence
    carries the docker/entrypoint.sh shell-variable snippet (Iteration 2
    regression). Returns the root."""
    plans = os.path.join(root, "plans")
    evid = os.path.join(root, "evidence")
    packets_dir = os.path.join(evid, "packets")
    os.makedirs(packets_dir, exist_ok=True)

    sections = [
        _section_plan("overview", "Overview", 1, search_hints=("repo overview",)),
        _section_plan("service", "Service Layer", 2, files=("pkg/svc.py",),
                      contracts=("GET /items",), expected=()),
    ]
    if with_deployment:
        sections.append(_section_plan(
            "deployment", "Deployment", 3, files=("docker/entrypoint.sh",)))
    doc = {"schema_version": "phase2-plan-v1",
           "repo": {"name": "demo", "root": root},
           "title": "Demo Documentation Plan",
           "purpose": "A demo service for testing Phase 4.",
           "summary": "", "audience": "developers",
           "section_order": [s["section_id"] for s in sections],
           "coverage_goals": [], "known_gaps": [],
           "source_raw_response": "plans/raw.md", "provider": "test",
           "normalization": {"generated_by": "test", "unresolved_count": 0,
                             "warnings": []}}
    util.write_json(os.path.join(plans, "document-plan.json"), doc)

    # section-plans.jsonl: serialize with the SAME json.dumps used for the SHA.
    raw_lines = {s["section_id"]: json.dumps(s) for s in sections}
    with open(os.path.join(plans, "section-plans.jsonl"), "w", encoding="utf-8") as f:
        for s in sections:
            f.write(raw_lines[s["section_id"]] + "\n")
    sha = {sid: f"sha256:{util.sha256_text(line)}" for sid, line in raw_lines.items()}

    util.write_text(os.path.join(plans, "phase3-readiness-report.md"),
                    "# Phase 3 Readiness Report\n\nStatus: PASS\nFailures: 0\n"
                    f"Warnings: 0\nSections: {len(sections)}\n")
    util.write_text(os.path.join(plans, "normalization-report.md"),
                    "# normalization report\n")

    packets = {
        "overview": _packet("overview", "Overview", 1, [
            _ev_chunk("ev:overview:0001", "README.md", 1, 8,
                      "Demo is a Retrieval service. See README.md for the overview.")],
            sha["overview"]),
        "service": _packet("service", "Service Layer", 2, [
            _ev_span("ev:service:0001", "pkg/svc.py", 5, 12,
                     "python pkg.svc/work().",
                     "def work(n):\n    return [Item(name=str(i)) for i in range(n)]"),
            _ev_route("ev:service:0002", "/items", "GET",
                      '{"operationId": "list_items", "x-source": "pkg/api/routes.py"}')],
            sha["service"]),
    }
    if with_deployment:
        packets["deployment"] = _packet("deployment", "Deployment", 3, [
            _ev_chunk("ev:deployment:0001", "docker/entrypoint.sh", 146, 305,
                      DEPLOYMENT_SHELL_EXCERPT, conf="high")],
            sha["deployment"])
    packet_paths = []
    for sid, pkt in packets.items():
        util.write_json(os.path.join(packets_dir, f"{sid}.json"), pkt)
        packet_paths.append(f"evidence/packets/{sid}.json")
    util.write_jsonl(os.path.join(evid, "evidence-packets.jsonl"),
                     [packets[s["section_id"]] for s in sections])

    n_sections = len(sections)
    ev_total = sum(len(packets[s["section_id"]]["evidence"]) for s in sections)
    validation = {
        "schema_version": "phase3-retrieval-validation-v1", "status": "pass",
        "failure_category": None, "retrieval_mode": "lexical-symbolic",
        "counts": {"sections_expected": n_sections, "sections_processed": n_sections,
                   "packets_written": n_sections, "evidence_items": ev_total},
        "contract_checks": [{"name": n, "status": "pass", "details": "ok"}
                            for n in REQUIRED_CONTRACT_CHECKS],
        "section_results": [{"section_id": s["section_id"], "status": "pass",
                             "evidence_count": len(packets[s["section_id"]]["evidence"]),
                             "missing_expected_evidence_types": [], "warnings": []}
                            for s in sections],
        "errors": [], "warnings": []}
    util.write_json(os.path.join(evid, "retrieval-validation.json"), validation)
    util.write_json(os.path.join(evid, "evidence-manifest.json"), {
        "schema_version": "phase3-evidence-manifest-v1", "bundle_root": root,
        "document_plan": "plans/document-plan.json",
        "section_plans": "plans/section-plans.jsonl",
        "retrieval_mode": "lexical-symbolic", "section_count": n_sections,
        "packet_count": n_sections,
        "combined_packets": "evidence/evidence-packets.jsonl",
        "packet_paths": packet_paths, "validation": "evidence/retrieval-validation.json",
        "report": "evidence/retrieval-report.md", "status": "pass"})

    util.write_json(os.path.join(root, "run-metadata.json"),
                    {"generator": "test", "git": {"head_commit": "abc"}})
    if with_manifest:
        # a clean command manifest with a Phase 3 invocation and NO --force
        util.write_text(os.path.join(root, "command-manifest.tsv"),
                        "git_status\tgit status\t0\n"
                        "phase3_retrieve_evidence\tscripts/phase3_retrieve_evidence.sh "
                        "--out " + root + " --with-vectors\t0\n")
    return root


# --- fake provider ------------------------------------------------------------
def valid_markdown(sid, title, evidence_ids, *, body=None):
    cites = "".join(f"[{i}]" for i in evidence_ids)
    text = body or (f"The {title} subsystem is implemented as described by the "
                    f"source evidence. {cites}")
    return f"## {title}\n\n{text}\n"


def draft_json(sid, title, markdown, used=None):
    return json.dumps({
        "schema_version": "phase4-section-draft-v1", "section_id": sid,
        "title": title, "markdown": markdown,
        "used_evidence_ids": used or [],
        "self_check": {"no_uncited_repo_claims": True,
                       "no_context_artifact_citations": True,
                       "no_placeholders": True}})


class FakeProvider:
    """Returns canned SectionResponses. ``by_section`` maps section_id -> either a
    SectionResponse, a raw string, or a list (one per successive call, for rewrites)."""

    def __init__(self, by_section, mode=PROVIDER_VERTEX, model="fake-model"):
        self.mode = mode
        self.model = model
        self.by_section = by_section
        self.calls = []

    def generate(self, section_id, prompt):
        self.calls.append(section_id)
        val = self.by_section.get(section_id)
        if isinstance(val, list):
            n = sum(1 for c in self.calls if c == section_id) - 1
            val = val[min(n, len(val) - 1)]
        if isinstance(val, SectionResponse):
            return val
        if val is None:
            val = draft_json(section_id, section_id, f"## {section_id}\n\nText.\n")
        return SectionResponse(val, "STOP")


def default_provider(b):
    by = {}
    for sid in b.section_order:
        title = b.section_plans[sid]["title"]
        ids = sorted(b.section_evidence_ids[sid])
        by[sid] = draft_json(sid, title, valid_markdown(sid, title, ids), used=ids)
    return FakeProvider(by)


def opts_for(root, **kw):
    base = dict(bundle_root=root, out_dir=os.path.join(root, "wiki"),
                provider=PROVIDER_VERTEX)
    base.update(kw)
    return WritingOptions(**base)


def gated(root, **kw):
    return wbundle.load_and_gate(opts_for(root, **kw))


def _assert_phase4_prompt_contract(testcase, prompt: str, *,
                                   expect_coverage: bool = False) -> None:
    """Focused guardrails for the Phase 4 prompt failure classes."""
    for needle in (
        # strict JSON / escaping failures observed in generated drafts
        "one raw strict JSON object",
        "standard `json.loads` parser can parse",
        "JSON-safe Markdown string escaping",
        "the `markdown` value and every other string value",
        "encode Markdown newlines as `\\n`",
        "raw unescaped newlines",
        "raw unescaped double quotes",
        "Return only the raw JSON object, with JSON-safe Markdown string escaping.",
        # instruction-example leakage failures
        "Instruction examples are NOT evidence",
        "FORBIDDEN INSTRUCTION EXAMPLE",
        "unless the exact token appears in the EvidencePacket and is cited",
        "must never be copied into the generated `markdown`",
        # reserved validation-token hardening
        "validation-reserved filler words or tokens",
        "the literal word `placeholder`",
        "including plural or compound forms that contain that substring",
        "`TODO`, `TBD`, `FIXME`",
        "the phrase `needs citation`",
        "terminal validation failures in headings, prose, lists",
        "code fences, and inline code",
        "If evidence uses the literal validation-reserved word `placeholder`",
        "code/comment concept",
        "do NOT copy that word into `markdown`",
        "Paraphrase with precise safe wording such as no-op, stub, default",
        "temporary body, route variable marker, or template marker",
        "and cite the evidence",
        # route normalization/synthesis failures
        "Never synthesize or normalize a route pattern",
        "do not add or remove route prefixes, version markers, base paths",
        "query parameters, or trailing slashes",
        "do not convert route-template marker syntax",
        "do not combine separate route fragments",
        "unless that exact complete route string appears verbatim",
        "High-salience route-template rule",
        "Do not rewrite f-strings, code templates",
        "variables, or template markers into simplified route patterns",
        "do not drop qualifiers such as `self.`",
        "rename variables into brace variables",
        "If only a template or f-string is evidenced",
        "quote the exact evidenced template/token",
        "describe it in prose using separate exact tokens",
        "do not invent a normalized route pattern",
        "Never put ellipses (three dots or the single",
        "ellipsis glyph) inside route, path, identifier",
        "or inline-code tokens to",
        "summarize multiple endpoints or names",
        "Do not write a prefix followed by an",
        "ellipsis as an abbreviated route/path/identifier",
        "unless that exact complete token appears verbatim in one cited evidence item",
        "To discuss a family of endpoints",
        "routes under the API prefix",
        "list exact cited routes individually",
        "do not invent a pseudo-route",
        "intentionally avoid literal forbidden route examples",
        "copy only `source.route` or `source.public_route` values verbatim",
        "do not compose a public route from a base path, prefix, version marker",
        # fully-qualified identifier / import synthesis failures
        "Class/object ownership does not create dotted identifiers",
        "method/function name inside or near a class/object",
        "the `method` method in/inside/on `Class`",
        "do NOT write `Class.method`, `Class._private`, `object.member`",
        "Nested JSON/YAML/dict/object keys do NOT create dotted identifiers",
        "field paths",
        "object with key `data` containing key `graph`",
        "the `graph` field under the `data` object",
        "quote exact JSON/YAML/object snippets",
        "do NOT write `object.field`, `parent.child`, or any dotted key path",
        "This applies to API response examples, config maps, request bodies",
        "dict literals, and JSON/YAML snippets",
        "Instruction examples in this object-key rule are not evidence",
        "Import statements must be described in import syntax or as separate tokens",
        "file path, directory, package context, or section context must never be used",
        "qualify an imported symbol/name",
        "If evidence shows a file under a directory or",
        "package/section context and separately shows `from X import Y` or `import Y`",
        "do NOT write `directory.Y`, `package.Y`, `section.Y`, or any dotted context-symbol",
        "say the file imports `Y` from `X`",
        "quote the exact import line",
        "imports `Name` from `module`",
        "quote `from module import Name`",
        "do NOT write `module.Name`, `package.Name`, or any dotted package-symbol form",
        "Instruction examples in this import rule are not evidence",
        "Never synthesize fully-qualified names by joining",
        "file paths, file-path directories, package names, package context",
        "section context, file stems, classes",
        "A cited file path/source directory",
        "surrounding context is not a namespace for an",
        "imported symbol/name and must not qualify it",
        "Dotted class/member, object/member, module/member, and package/member notation",
        "Separate tokens in the same cited item are not enough",
        "a class token plus a method token does NOT evidence `ClassName.method_name`",
        "refer to an evidenced method and evidenced class as separate cited tokens",
        "never join them into a class-method dotted token unless",
        "Do not transform import statements into dotted fully-qualified identifiers",
        "`from package.module import Name` evidences only exact tokens present",
        "it does NOT evidence `package.module.Name`",
        "Instruction examples in this rule are not evidence",
        "Forbidden instruction identifier examples (not evidence; never copy unless "
        "the full exact token appears in cited EvidencePacket)",
        "`common.metadata_es_filter` plus `MetaFilterTranslator`",
        "`common.metadata_es_filter.MetaFilterTranslator`",
        "unless that full exact token appears verbatim",
        # response-contract self checks; downstream validation remains authoritative
        '"valid_json": true',
        '"json_strings_escaped": true',
        '"no_empty_headings": true',
        '"no_synthesized_identifiers": true',
        '"no_synthesized_routes": true',
        "declarations only",
        "validation independently parses JSON and checks citations",
        # empty-heading hardening for the live top-section failure mode
        "No empty headings: every heading you emit MUST be followed by substantive",
        "non-heading content before the next heading",
        "Do not put one heading directly after another heading",
        "even with blank lines between them",
        "If the `markdown` starts with the section title heading",
        "the next nonblank line MUST be a substantive introductory paragraph",
        "list item, or table row with an inline citation",
        "it MUST NOT be another heading",
        "Do NOT emit a decorative duplicate title heading with no body",
        "A title heading is allowed only when it is immediately followed",
        "This introductory paragraph states an evidence-backed summary",
        "subheading. [ev:",
        "This subsection opens with cited body content before any later heading",
    ):
        testcase.assertIn(needle, prompt)
    for leaked_route in ("/api/{api_version}", "/{api_version}", "/api/v1/..."):
        testcase.assertNotIn(leaked_route, prompt)
    testcase.assertNotIn("quart_auth.AuthUser", prompt)
    testcase.assertNotIn("Parser._pdf", prompt)
    testcase.assertNotIn("agent.settings", prompt)
    testcase.assertNotIn("data.graph", prompt)
    if expect_coverage:
        for needle in (
            "DeepWiki coverage enhancement — REQUIRED",
            "drawn ONLY from that topic's supporting evidence_ids",
            "Evidence scope distinction for required-topic coverage",
            "`allowed_evidence_ids` is the section-wide citation allowlist",
            "listed `supporting_evidence_ids` are the ONLY ids you may cite",
            "paragraph/subsection/block whose purpose is to satisfy that topic",
            "ONLY ids you may put in that topic's `covered_topics[].evidence_ids` row",
            "Do NOT cite broader section evidence inside a required-topic coverage block",
            "If broader allowed evidence is useful, discuss it elsewhere outside",
            "do not include it in that topic's `covered_topics[].evidence_ids`",
            "Using an id from `allowed_evidence_ids` is not enough for required-topic coverage",
            "the id counts only if it is also listed in that topic's `supporting_evidence_ids`",
            "inside that topic's coverage block",
            "citing broader section evidence inside the topic block",
            "declaring an id outside its supporting set fails validation",
        ):
            testcase.assertIn(needle, prompt)


# ---------------------------------------------------------------------------
class TmpBundleMixin:
    def fresh(self, **kw):
        d = tempfile.mkdtemp(prefix="p4_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        root = os.path.join(d, "bundle")
        os.makedirs(root)
        make_bundle(root, **kw)
        return root


# ---------------------------------------------------------------------------
class GateTests(TmpBundleMixin, unittest.TestCase):
    """Every precondition gate fails closed before any model call."""

    def test_clean_bundle_gates_pass(self):
        b = gated(self.fresh())
        self.assertEqual(b.section_order, ["overview", "service"])
        self.assertEqual(len(b.evidence_index), 3)
        self.assertTrue(all(c["status"] == "pass" for c in b.gate_report),
                        [c for c in b.gate_report if c["status"] != "pass"])

    def test_readiness_fail_blocks(self):
        root = self.fresh()
        util.write_text(os.path.join(root, "plans", "phase3-readiness-report.md"),
                        "# R\n\nStatus: FAIL\nFailures: 2\n")
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_readiness_failures_nonzero_blocks(self):
        root = self.fresh()
        util.write_text(os.path.join(root, "plans", "phase3-readiness-report.md"),
                        "# R\n\nStatus: PASS\nFailures: 1\n")
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_missing_readiness_is_bad_input(self):
        root = self.fresh()
        os.remove(os.path.join(root, "plans", "phase3-readiness-report.md"))
        with self.assertRaises(writing.BadInputArtifact):
            gated(root)

    def test_retrieval_not_pass_blocks(self):
        root = self.fresh()
        v = json.load(open(os.path.join(root, "evidence", "retrieval-validation.json")))
        v["status"] = "fail"
        v["failure_category"] = "bad_underspecified_normalized_plan"
        util.write_json(os.path.join(root, "evidence", "retrieval-validation.json"), v)
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_retrieval_missing_contract_check_blocks(self):
        root = self.fresh()
        v = json.load(open(os.path.join(root, "evidence", "retrieval-validation.json")))
        v["contract_checks"] = [c for c in v["contract_checks"]
                                if c["name"] != "no_context_artifact_evidence"]
        util.write_json(os.path.join(root, "evidence", "retrieval-validation.json"), v)
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_retrieval_count_mismatch_blocks(self):
        root = self.fresh()
        v = json.load(open(os.path.join(root, "evidence", "retrieval-validation.json")))
        v["counts"]["packets_written"] = 1
        util.write_json(os.path.join(root, "evidence", "retrieval-validation.json"), v)
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_missing_document_plan_is_bad_input(self):
        root = self.fresh()
        os.remove(os.path.join(root, "plans", "document-plan.json"))
        with self.assertRaises(writing.BadInputArtifact):
            gated(root)

    def test_missing_packet_is_bad_input(self):
        root = self.fresh()
        os.remove(os.path.join(root, "evidence", "packets", "service.json"))
        with self.assertRaises(writing.BadInputArtifact):
            gated(root)

    def test_stale_section_plan_sha_blocks(self):
        root = self.fresh()
        # mutate a section plan line so its sha no longer matches the packet
        p = os.path.join(root, "plans", "section-plans.jsonl")
        rows = [json.loads(l) for l in open(p) if l.strip()]
        for r in rows:
            if r["section_id"] == "service":
                r["purpose"] = "MUTATED after packets were written"
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_force_in_command_manifest_blocks(self):
        root = self.fresh()
        util.write_text(os.path.join(root, "command-manifest.tsv"),
                        "phase3\tscripts/phase3_retrieve_evidence.sh --out " + root
                        + " --force\t0\n")
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_no_manifest_without_accept_blocks(self):
        root = self.fresh(with_manifest=False)
        with self.assertRaises(writing.GateFailure):
            gated(root)  # accept_no_force defaults to False

    def test_no_manifest_with_accept_passes(self):
        root = self.fresh(with_manifest=False)
        b = gated(root, accept_no_force=True)
        self.assertTrue(all(c["status"] == "pass" for c in b.gate_report))

    def test_help_text_force_mention_not_treated_as_force(self):
        # a manifest row that merely mentions --force inside a help string for a
        # non-phase3 command must not trip the force gate
        root = self.fresh()
        util.write_text(os.path.join(root, "command-manifest.tsv"),
                        "help\tscripts/phase3_retrieve_evidence.sh --help\t0\n"
                        "phase3\tscripts/phase3_retrieve_evidence.sh --out " + root
                        + "\t0\n")
        b = gated(root)  # no real --force token in a phase3 invocation
        self.assertTrue(all(c["status"] == "pass" for c in b.gate_report))

    def test_source_hygiene_rejects_derived_evidence(self):
        root = self.fresh()
        pkt = json.load(open(os.path.join(root, "evidence", "packets", "service.json")))
        pkt["evidence"][0]["source"]["path"] = "derived/planning-digest.md"
        util.write_json(os.path.join(root, "evidence", "packets", "service.json"), pkt)
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_packet_validation_fail_blocks(self):
        root = self.fresh()
        pkt = json.load(open(os.path.join(root, "evidence", "packets", "overview.json")))
        pkt["validation"]["status"] = "fail"
        util.write_json(os.path.join(root, "evidence", "packets", "overview.json"), pkt)
        with self.assertRaises(writing.GateFailure):
            gated(root)


# ---------------------------------------------------------------------------
class HappyPathTests(TmpBundleMixin, unittest.TestCase):
    def _run(self, root, **kw):
        b = gated(root, **kw)
        return writing.run(opts_for(root, **kw), provider=default_provider(b)), b

    def test_full_pass_writes_all_outputs(self):
        root = self.fresh()
        res, _ = self._run(root)
        self.assertEqual(res.status, "pass")
        self.assertEqual(res.exit_code, 0)
        wiki = os.path.join(root, "wiki")
        for rel in ("index.md", "metadata/generated-sections.jsonl",
                    "metadata/generated-document.json",
                    "metadata/citation-manifest.json",
                    "validation/writing-validation.json",
                    "validation/writing-validation-report.md",
                    "PHASE4_RUN_REPORT.md",
                    "sections/001-overview.md", "sections/002-service.md",
                    "audit/prompts/overview.md", "audit/responses/overview.raw.txt",
                    "audit/responses/overview.parsed.json"):
            self.assertTrue(os.path.isfile(os.path.join(wiki, rel)), rel)

    def test_citation_manifest_resolves_every_used_citation(self):
        root = self.fresh()
        self._run(root)
        man = json.load(open(os.path.join(root, "wiki", "metadata",
                                          "citation-manifest.json")))
        ids = {c["evidence_id"] for c in man["citations"]}
        self.assertEqual(ids, {"ev:overview:0001", "ev:service:0001", "ev:service:0002"})
        for c in man["citations"]:
            self.assertTrue(c["source"].get("artifact"))
            self.assertIn(c["owner_section_id"], ("overview", "service"))
            self.assertTrue(c["used_in_sections"])

    def test_generated_section_metadata_shape(self):
        root = self.fresh()
        self._run(root)
        rows = [json.loads(l) for l in open(os.path.join(
            root, "wiki", "metadata", "generated-sections.jsonl")) if l.strip()]
        self.assertEqual([r["section_id"] for r in rows], ["overview", "service"])
        svc = rows[1]
        self.assertEqual(svc["markdown_path"], "wiki/sections/002-service.md")
        self.assertEqual(svc["source_packet_path"], "evidence/packets/service.json")
        self.assertTrue(svc["source_packet_sha256"].startswith("sha256:"))
        self.assertEqual(set(svc["evidence_ids_used"]),
                         {"ev:service:0001", "ev:service:0002"})
        self.assertIn("derived/planning-digest.md",
                      [c["path"] for c in svc["context_artifacts_consulted"]])
        self.assertEqual(svc["generation"]["provider_mode"], PROVIDER_VERTEX)
        self.assertEqual(svc["validation"]["status"], "pass")

    def test_context_artifacts_consulted_never_cited(self):
        root = self.fresh()
        self._run(root)
        man = json.load(open(os.path.join(root, "wiki", "metadata",
                                          "citation-manifest.json")))
        for c in man["citations"]:
            self.assertFalse(str(c["source"].get("path", "")).startswith("derived/"))
            self.assertFalse(str(c["source"].get("artifact", "")).startswith("derived/"))

    def test_rerun_is_byte_identical(self):
        root = self.fresh()
        self._run(root)
        first = _snapshot(os.path.join(root, "wiki"))
        # rerun with a fresh gated bundle + identical fake provider
        b = gated(root)
        writing.run(opts_for(root), provider=default_provider(b))
        self.assertEqual(first, _snapshot(os.path.join(root, "wiki")))

    def test_no_timestamps_in_outputs(self):
        root = self.fresh()
        self._run(root)
        blob = json.dumps(_snapshot(os.path.join(root, "wiki")))
        for needle in ("generated_at", "timestamp", "created_at"):
            self.assertNotIn(needle, blob)

    def test_cross_section_citation_allowed_and_recorded(self):
        root = self.fresh()
        b = gated(root)
        by = {
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            # service cites overview's evidence (cross-section) plus its own
            "service": draft_json("service", "Service Layer",
                                  valid_markdown("service", "Service Layer",
                                                 ["ev:overview:0001", "ev:service:0001"])),
        }
        res = writing.run(opts_for(root), provider=FakeProvider(by))
        self.assertEqual(res.status, "pass")
        rows = [json.loads(l) for l in open(os.path.join(
            root, "wiki", "metadata", "generated-sections.jsonl")) if l.strip()]
        svc = next(r for r in rows if r["section_id"] == "service")
        self.assertIn("ev:overview:0001", svc["cross_section_citations"])
        man = json.load(open(os.path.join(root, "wiki", "metadata",
                                          "citation-manifest.json")))
        ov = next(c for c in man["citations"] if c["evidence_id"] == "ev:overview:0001")
        self.assertEqual(ov["owner_section_id"], "overview")
        self.assertIn("service", ov["used_in_sections"])

    def test_supported_identifier_in_backticks_passes(self):
        root = self.fresh()
        b = gated(root)
        by = {
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": draft_json(
                "service", "Service Layer",
                "## Service Layer\n\nThe service layer lives in `pkg/svc.py` and "
                "exposes the `GET /items` route. [ev:service:0001][ev:service:0002]\n"),
        }
        res = writing.run(opts_for(root), provider=FakeProvider(by))
        self.assertEqual(res.status, "pass", res.message)


# ---------------------------------------------------------------------------
class WritingValidationTests(TmpBundleMixin, unittest.TestCase):
    def _provider(self, root, service_md):
        return FakeProvider({
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": service_md,
        })

    def test_invented_path_is_rejected(self):
        root = self.fresh()
        md = ("## Service Layer\n\nThe handler is defined in `app/ghost_module.py`. "
              "[ev:service:0001]\n")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root),
                        provider=self._provider(root, draft_json("service",
                                                                 "Service Layer", md)))

    def test_class_method_synthesis_is_rejected_when_tokens_are_separate(self):
        root = self.fresh()
        pkt_path = os.path.join(root, "evidence", "packets", "service.json")
        pkt = json.load(open(pkt_path))
        pkt["evidence"][0]["excerpt"] = (
            "class RAGFlowClient:\n"
            "    def login_user(self):\n"
            "        return None\n")
        util.write_json(pkt_path, pkt)
        md = ("## Service Layer\n\nThe service calls `RAGFlowClient.login_user`. "
              "[ev:service:0001]\n")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root),
                        provider=self._provider(root, draft_json("service",
                                                                 "Service Layer", md)))

    def test_context_artifact_citation_is_rejected_not_rewritten(self):
        root = self.fresh()
        md = ("## Service Layer\n\nSee `derived/planning-digest.md` for details. "
              "[ev:service:0001]\n")
        prov = self._provider(root, draft_json("service", "Service Layer", md))
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=2), provider=prov)
        # terminal: no rewrite attempted (service called exactly once)
        self.assertEqual(prov.calls.count("service"), 1)

    def test_placeholder_is_rejected(self):
        root = self.fresh()
        md = "## Service Layer\n\nTODO: document this. [ev:service:0001]\n"
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root),
                        provider=self._provider(root, draft_json("service",
                                                                 "Service Layer", md)))

    def test_placeholder_handling_phrase_is_rejected(self):
        root = self.fresh()
        md = ("## Service Layer\n\nThe implementation covers placeholder handling. "
              "[ev:service:0001]\n")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root),
                        provider=self._provider(root, draft_json("service",
                                                                 "Service Layer", md)))

    def test_parent_heading_with_child_subsections_is_allowed(self):
        root = self.fresh()
        md = ("## Service Layer\n\n### Utility Commands\n\n#### Password Reset\n\n"
              "The service layer lives in `pkg/svc.py`. [ev:service:0001]\n")
        res = writing.run(opts_for(root),
                          provider=self._provider(root, draft_json("service",
                                                                   "Service Layer", md)))
        self.assertEqual(res.status, "pass")

    def test_empty_heading_is_rejected(self):
        root = self.fresh()
        md = ("## Service Layer\n\n### Empty Group\n\n### Real Details\n\n"
              "The service layer lives in `pkg/svc.py`. [ev:service:0001]\n")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root),
                        provider=self._provider(root, draft_json("service",
                                                                 "Service Layer", md)))

    def test_empty_top_title_heading_is_rejected(self):
        root = self.fresh()
        bad_overview = ("## Overview\n\n## What RAGFlow Is\n\n"
                        "Demo is a Retrieval service. [ev:overview:0001]\n")
        service = valid_markdown("service", "Service Layer",
                                 ["ev:service:0001", "ev:service:0002"])
        provider = FakeProvider({
            "overview": draft_json("overview", "Overview", bad_overview),
            "service": draft_json("service", "Service Layer", service),
        })
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root), provider=provider)

    def test_truncation_finish_reason_fails(self):
        root = self.fresh()
        resp = SectionResponse(draft_json("service", "Service Layer",
                                          valid_markdown("service", "Service Layer",
                                                         ["ev:service:0001"])),
                               "MAX_TOKENS")
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root), provider=self._provider(root, resp))

    def test_unresolved_citation_rewrite_then_success(self):
        root = self.fresh()
        bad = draft_json("service", "Service Layer",
                         valid_markdown("service", "Service Layer", ["ev:service:9999"]))
        good = draft_json("service", "Service Layer",
                          valid_markdown("service", "Service Layer", ["ev:service:0001"]))
        prov = FakeProvider({
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": [bad, good]})
        res = writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(res.status, "pass")
        self.assertEqual(prov.calls.count("service"), 2)  # one rewrite happened

    def test_unresolved_citation_rewrite_exhausted_fails(self):
        root = self.fresh()
        bad = draft_json("service", "Service Layer",
                         valid_markdown("service", "Service Layer", ["ev:service:9999"]))
        prov = FakeProvider({
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": [bad, bad]})
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(prov.calls.count("service"), 2)  # capped at 1 rewrite

    def test_malformed_json_rewrite_then_success(self):
        root = self.fresh()
        good = draft_json("service", "Service Layer",
                          valid_markdown("service", "Service Layer", ["ev:service:0001"]))
        prov = FakeProvider({
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": ["this is not json at all", good]})
        res = writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(res.status, "pass")

    def test_provider_no_text_is_provider_failure(self):
        root = self.fresh()
        prov = self._provider(root, SectionResponse(None, "SAFETY",
                                                    error="safety block"))
        with self.assertRaises(writing.ProviderFailure):
            writing.run(opts_for(root), provider=prov)

    def test_rewrite_audit_written(self):
        root = self.fresh()
        bad = draft_json("service", "Service Layer",
                         valid_markdown("service", "Service Layer", ["ev:service:9999"]))
        good = draft_json("service", "Service Layer",
                          valid_markdown("service", "Service Layer", ["ev:service:0001"]))
        prov = FakeProvider({
            "overview": draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])),
            "service": [bad, good]})
        writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        adir = os.path.join(root, "wiki", "audit", "rewrites", "service-attempt-1")
        for name in ("prompt.md", "response.raw.txt", "problems.json"):
            self.assertTrue(os.path.isfile(os.path.join(adir, name)), name)


# ---------------------------------------------------------------------------
class GemAndProviderConfigTests(TmpBundleMixin, unittest.TestCase):
    def test_prepare_prompts_only_no_generation(self):
        root = self.fresh()
        res = writing.run(opts_for(root, provider=PROVIDER_GEMINI_GEM,
                                   prepare_only=True))
        self.assertEqual(res.status, "prepared")
        pdir = os.path.join(root, "wiki", "audit", "prompts")
        self.assertTrue(os.path.isfile(os.path.join(pdir, "overview.md")))
        service_prompt = os.path.join(pdir, "service.md")
        self.assertTrue(os.path.isfile(service_prompt))
        self.assertTrue(os.path.isfile(os.path.join(pdir, "README_GEM_HANDOFF.md")))
        with open(service_prompt, encoding="utf-8") as f:
            _assert_phase4_prompt_contract(self, f.read())
        # no generation happened
        self.assertFalse(os.path.exists(os.path.join(root, "wiki", "index.md")))

    def test_gem_import_validate_and_assemble(self):
        root = self.fresh()
        b = gated(root, provider=PROVIDER_GEMINI_GEM)
        rdir = os.path.join(root, "wiki", "audit", "responses")
        os.makedirs(rdir, exist_ok=True)
        for sid in b.section_order:
            title = b.section_plans[sid]["title"]
            ids = sorted(b.section_evidence_ids[sid])
            util.write_text(os.path.join(rdir, f"{sid}.raw.txt"),
                            draft_json(sid, title, valid_markdown(sid, title, ids)))
        res = writing.run(opts_for(root, provider=PROVIDER_GEMINI_GEM,
                                   responses_in=rdir))
        self.assertEqual(res.status, "pass")
        rows = [json.loads(l) for l in open(os.path.join(
            root, "wiki", "metadata", "generated-sections.jsonl")) if l.strip()]
        self.assertEqual(rows[0]["generation"]["provider_mode"], PROVIDER_GEMINI_GEM)
        self.assertIsNone(rows[0]["generation"]["model"])

    def test_gem_missing_response_is_provider_failure(self):
        root = self.fresh()
        rdir = os.path.join(root, "wiki", "audit", "responses")
        os.makedirs(rdir, exist_ok=True)
        util.write_text(os.path.join(rdir, "overview.raw.txt"),
                        draft_json("overview", "Overview",
                                   valid_markdown("overview", "Overview",
                                                  ["ev:overview:0001"])))
        # service response missing
        with self.assertRaises(writing.ProviderFailure):
            writing.run(opts_for(root, provider=PROVIDER_GEMINI_GEM,
                                 responses_in=rdir))

    def test_vertex_provider_requires_project(self):
        from wiki_generator.libs.writing.provider import build_provider
        from wiki_generator.libs.writing.errors import ProviderFailure
        o = opts_for("/x", provider=PROVIDER_VERTEX, project=None, location="us")
        try:
            with self.assertRaises(ProviderFailure):
                build_provider(o)
        except ProviderFailure:
            self.skipTest("google-genai not installed; SDK import path covered")

    def test_gemini_api_requires_key(self):
        from wiki_generator.libs.writing.provider import build_provider
        from wiki_generator.libs.writing.options import PROVIDER_GEMINI_API
        from wiki_generator.libs.writing.errors import ProviderFailure
        o = opts_for("/x", provider=PROVIDER_GEMINI_API, api_key=None)
        try:
            with self.assertRaises(ProviderFailure):
                build_provider(o)
        except ProviderFailure:
            self.skipTest("google-genai not installed; SDK import path covered")

    def test_options_reject_bad_values(self):
        with self.assertRaises(ValueError):
            opts_for("/x", provider="not-a-mode")
        with self.assertRaises(ValueError):
            opts_for("/x", max_output_tokens=0)
        with self.assertRaises(ValueError):
            opts_for("/x", max_rewrite_attempts=3)

    def test_8192_warns_for_gemini_pro(self):
        o = opts_for("/x", provider=PROVIDER_VERTEX, model="gemini-2.5-pro",
                     max_output_tokens=8192)
        self.assertIsNotNone(o.truncation_risk())
        o2 = opts_for("/x", provider=PROVIDER_VERTEX, model="gemini-2.5-pro",
                      max_output_tokens=32768)
        self.assertIsNone(o2.truncation_risk())


# ---------------------------------------------------------------------------
class UnitTests(unittest.TestCase):
    def test_citation_regex(self):
        from wiki_generator.libs.writing import citations as c
        md = "a [ev:overview:0001] b [ev:api-agents:0042][ev:api-agents:0001] c"
        self.assertEqual(c.extract_citations(md),
                         ["ev:overview:0001", "ev:api-agents:0042", "ev:api-agents:0001"])

    def test_placeholder_detector(self):
        from wiki_generator.libs.writing import citations as c
        self.assertTrue(c.find_placeholders("TODO: fix"))
        self.assertTrue(c.find_placeholders("TBD: fill in later"))
        self.assertIn(
            "placeholder",
            c.find_placeholders("This sentence mentions placeholder handling."))
        self.assertTrue(c.find_placeholders("I cannot determine this."))
        empty = c.find_placeholders("## Empty\n\n## Next\n\nBody.")
        self.assertIn("empty heading: ## Empty", empty)
        self.assertNotIn("empty heading: ## Next", empty)
        empty_top = c.find_placeholders(
            "## Overview\n\n## What RAGFlow Is\n\nBody. [ev:overview:0001]")
        self.assertIn("empty heading: ## Overview", empty_top)
        self.assertNotIn("empty heading: ## What RAGFlow Is", empty_top)
        nested = ("### Utility Commands\n\n#### Password Reset\n\nReset passwords.\n\n"
                  "#### MCP Server Launcher\n\nLaunches the server.\n")
        self.assertFalse(c.find_placeholders(nested))
        self.assertFalse(c.find_placeholders("Real prose with no markers."))

    def test_parse_fenced_and_balanced(self):
        from wiki_generator.libs.writing.parse import parse_section_response
        obj, _ = parse_section_response('prefix\n```json\n{"a": 1}\n```\nsuffix')
        self.assertEqual(obj, {"a": 1})
        obj2, _ = parse_section_response('garbage {"b": {"c": 2}} trailing')
        self.assertEqual(obj2, {"b": {"c": 2}})
        obj3, note = parse_section_response("not json")
        self.assertIsNone(obj3)

    def test_readiness_parser(self):
        from wiki_generator.libs.writing.bundle import parse_readiness
        r = parse_readiness("# R\n\nStatus: PASS\nFailures: 0\nWarnings: 3\n")
        self.assertEqual((r["status"], r["failures"], r["warnings"]), ("PASS", 0, 3))
        from wiki_generator.libs.writing.errors import BadInputArtifact
        with self.assertRaises(BadInputArtifact):
            parse_readiness("no status here")

    def test_invented_vs_supported_identifier(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "def work(n): in pkg/svc.py route /items GET"
        r = analyze_claims("Uses `pkg/svc.py` here. [ev:x:0001]", available)
        self.assertEqual(r["invented_identifiers"], [])
        r2 = analyze_claims("Uses `app/ghost.py` here. [ev:x:0001]", available)
        self.assertIn("app/ghost.py", r2["invented_identifiers"])

    def test_public_route_source_metadata_supports_exact_route(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        route = "/api/v1/datasets/{dataset_id}/documents/{document_id}/chunks"
        available = json.dumps({"source": {"route": "/datasets/<dataset_id>/documents/<document_id>/chunks",
                                             "public_route": route}})
        r = analyze_claims(f"Lists chunks with `GET {route}`. [ev:x:0001]",
                           available)
        self.assertEqual(r["invented_identifiers"], [])
        r2 = analyze_claims(f"Lists chunks with `GET {route}`. [ev:x:0001]",
                            '{"route": "/datasets/<dataset_id>/documents/<document_id>/chunks"}')
        self.assertIn(route, r2["invented_identifiers"])

    def test_route_family_ellipsis_is_not_supported_by_exact_routes(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "\n".join([
            json.dumps({"source": {"public_route": "/api/v1/agents",
                                     "route": "/agents"}}),
            json.dumps({"source": {"public_route": "/api/v1/datasets",
                                     "route": "/datasets"}}),
        ])
        exact = analyze_claims("Lists `GET /api/v1/agents`. [ev:x:0001]",
                               available)
        self.assertEqual(exact["invented_identifiers"], [])
        r = analyze_claims("Summarizes `GET /api/v1/...`. [ev:x:0001]",
                           available)
        self.assertIn("/api/v1/...", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_uncited_paragraph_detection(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "pkg/svc.py is here"
        r = analyze_claims("The file `pkg/svc.py` does work.", available)  # no citation
        self.assertTrue(r["uncited_paragraphs"])
        r2 = analyze_claims("The file `pkg/svc.py` does work. [ev:x:0001]", available)
        self.assertFalse(r2["uncited_paragraphs"])

    def test_context_artifact_reference_detector(self):
        from wiki_generator.libs.writing.citations import find_context_artifact_references
        self.assertTrue(find_context_artifact_references("see `derived/planning-gaps.md`"))
        self.assertTrue(find_context_artifact_references("see `plans/document-plan.json`"))
        self.assertFalse(find_context_artifact_references("see `pkg/svc.py`"))

    def test_structural_draft_errors(self):
        from wiki_generator.libs.writing.schema import structural_draft_errors
        self.assertEqual(structural_draft_errors(
            {"schema_version": "phase4-section-draft-v1", "section_id": "s",
             "title": "S", "markdown": "x"}, expected_section_id="s"), [])
        errs = structural_draft_errors({"section_id": "other", "markdown": ""},
                                       expected_section_id="s")
        self.assertTrue(any("section_id" in e for e in errs))
        self.assertTrue(any("markdown" in e for e in errs))

    def test_prompt_contract_rejects_json_and_synthesis_failures(self):
        from types import SimpleNamespace
        from wiki_generator.libs.writing.prompt import build_section_prompt
        wp = SimpleNamespace(
            section_id="service", title="Service", required_topics_coverage=None,
            allowed_evidence_ids=["ev:service:0001"],
            data={"section_id": "service", "evidence": []})
        _assert_phase4_prompt_contract(self, build_section_prompt(wp))

    def test_prompt_contract_distinguishes_section_allowed_from_topic_support(self):
        from types import SimpleNamespace
        from wiki_generator.libs.writing.prompt import build_section_prompt
        topic = ("Describe the supported retrieval methods (e.g., vector search, "
                 "keyword search, hybrid).")
        supporting = [f"ev:retrieval-search:{i:04d}" for i in range(1, 9)]
        wp = SimpleNamespace(
            section_id="retrieval-search", title="Retrieval Search",
            required_topics_coverage=[{"topic": topic, "is_obligation": True,
                                       "supporting_evidence_ids": supporting}],
            allowed_evidence_ids=supporting + ["ev:retrieval-search:0033",
                                               "ev:retrieval-search:0037"],
            data={"section_id": "retrieval-search", "evidence": [],
                  "hierarchy": {"parent_section_id": None,
                                "coverage_labels": ["retrieval"],
                                "child_section_ids": []}})
        prompt = build_section_prompt(wp)
        _assert_phase4_prompt_contract(self, prompt, expect_coverage=True)
        self.assertIn("- `ev:retrieval-search:0033`", prompt)
        self.assertIn("- `ev:retrieval-search:0037`", prompt)
        topic_line = next(line for line in prompt.splitlines()
                          if line.startswith("- **Describe the supported retrieval"))
        self.assertIn("`ev:retrieval-search:0008`", topic_line)
        self.assertNotIn("`ev:retrieval-search:0033`", topic_line)
        self.assertNotIn("`ev:retrieval-search:0037`", topic_line)


# ---------------------------------------------------------------------------
class CliTests(TmpBundleMixin, unittest.TestCase):
    def _cmd(self, *args, **kw):
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run([sys.executable, "-m", "wiki_generator", *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=120,
                              env=env, **kw)

    def test_help_lists_phase4_writing_only(self):
        res = self._cmd("write-wiki", "--help")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Phase 4", res.stdout)
        self.assertIn("writing/synthesis", res.stdout)
        # never offers a phase-3 retrieval / repair knob
        self.assertNotIn("--section", res.stdout)
        self.assertNotIn("--force", res.stdout)

    def test_prepare_only_smoke(self):
        root = self.fresh()
        res = self._cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                        "--prepare-prompts-only")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(os.path.isfile(os.path.join(
            root, "wiki", "audit", "prompts", "overview.md")))

    def test_gem_full_run_via_cli(self):
        root = self.fresh()
        # prepare, then write gem responses, then validate+assemble — all no-API
        self._cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                  "--prepare-prompts-only")
        rdir = os.path.join(root, "wiki", "audit", "responses")
        os.makedirs(rdir, exist_ok=True)
        b = gated(root, provider=PROVIDER_GEMINI_GEM)
        for sid in b.section_order:
            title = b.section_plans[sid]["title"]
            ids = sorted(b.section_evidence_ids[sid])
            util.write_text(os.path.join(rdir, f"{sid}.raw.txt"),
                            draft_json(sid, title, valid_markdown(sid, title, ids)))
        res = self._cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                        "--responses-in", rdir, "--validate-and-assemble")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(os.path.isfile(os.path.join(root, "wiki", "index.md")))

    def test_fails_before_provider_when_readiness_fail(self):
        root = self.fresh()
        util.write_text(os.path.join(root, "plans", "phase3-readiness-report.md"),
                        "# R\n\nStatus: FAIL\nFailures: 3\n")
        res = self._cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                        "--validate-and-assemble")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertFalse(os.path.exists(os.path.join(root, "wiki", "index.md")))

    def test_fails_before_provider_when_retrieval_not_pass(self):
        root = self.fresh()
        v = json.load(open(os.path.join(root, "evidence", "retrieval-validation.json")))
        v["status"] = "fail"
        v["failure_category"] = "retriever_implementation_bug"
        util.write_json(os.path.join(root, "evidence", "retrieval-validation.json"), v)
        res = self._cmd("write-wiki", "--bundle", root, "--provider", "gemini-gem",
                        "--validate-and-assemble")
        self.assertEqual(res.returncode, 3, res.stderr)


# ---------------------------------------------------------------------------
class GateCoverageTests(TmpBundleMixin, unittest.TestCase):
    """Spec "Unit tests for validators" — packet presence/coherence + hygiene."""

    def _mutate_packet(self, root, sid, fn):
        p = os.path.join(root, "evidence", "packets", f"{sid}.json")
        pkt = json.load(open(p))
        fn(pkt)
        util.write_json(p, pkt)

    def test_duplicate_evidence_ids_in_packet_blocks(self):
        root = self.fresh()
        def dup(pkt):
            pkt["evidence"].append(dict(pkt["evidence"][0]))  # repeat id 0001
        self._mutate_packet(root, "service", dup)
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_packet_order_mismatch_blocks(self):
        root = self.fresh()
        self._mutate_packet(root, "service", lambda p: p.__setitem__("order", 99))
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_packet_title_mismatch_blocks(self):
        root = self.fresh()
        self._mutate_packet(root, "service",
                            lambda p: p.__setitem__("title", "Wrong Title"))
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_packet_wrong_section_id_blocks(self):
        root = self.fresh()
        self._mutate_packet(root, "service",
                            lambda p: p.__setitem__("section_id", "elsewhere"))
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_source_hygiene_rejects_plans_evidence(self):
        root = self.fresh()
        self._mutate_packet(root, "service",
                            lambda p: p["evidence"][0]["source"].__setitem__(
                                "path", "plans/document-plan.json"))
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_source_hygiene_rejects_wiki_evidence(self):
        root = self.fresh()
        self._mutate_packet(root, "service",
                            lambda p: p["evidence"][0]["source"].__setitem__(
                                "artifact", "wiki/sections/001-overview.md"))
        with self.assertRaises(writing.GateFailure):
            gated(root)

    def test_normal_section_with_no_evidence_is_rejected(self):
        # A normal section "backed only by diagnostics" has no citeable evidence;
        # Phase 3 marks it validation:fail and Gate 5 rejects it (no wiki).
        root = self.fresh()
        def empty(pkt):
            pkt["evidence"] = []
            pkt["validation"]["status"] = "fail"
        self._mutate_packet(root, "overview", empty)
        with self.assertRaises(writing.GateFailure):
            gated(root)


# ---------------------------------------------------------------------------
class ValidatorUnitTests(TmpBundleMixin, unittest.TestCase):
    """Direct unit coverage of the citation/claim validators (spec test list)."""

    def test_resolve_citations_resolves_rejects_and_marks_cross_section(self):
        from wiki_generator.libs.writing.citations import resolve_citations
        index = {"ev:overview:0001": object(), "ev:service:0001": object()}
        sec_ids = {"overview": {"ev:overview:0001"}, "service": {"ev:service:0001"}}
        md = ("ok [ev:overview:0001] cross [ev:service:0001] unknown "
              "[ev:overview:9999] malformed [ev:overview:1]")
        r = resolve_citations(md, section_id="overview", evidence_index=index,
                              section_evidence_ids=sec_ids)
        self.assertEqual(set(r["resolved"]), {"ev:overview:0001", "ev:service:0001"})
        self.assertIn("ev:overview:9999", r["unresolved"])      # unknown id
        # ev:overview:1 has the wrong digit width -> not a well-formed citation
        self.assertNotIn("ev:overview:1", r["resolved"])
        self.assertEqual(r["cross_section"], ["ev:service:0001"])

    def test_invented_path_basename_collision_is_flagged(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = 'evidence path {"path": "test/ghost.py"} only'
        r = analyze_claims("The handler is in `app/ghost.py`. [ev:x:0001]", available)
        self.assertIn("app/ghost.py", r["invented_identifiers"])

    def test_context_artifact_basename_is_not_false_positive(self):
        from wiki_generator.libs.writing.citations import (
            find_context_artifact_references)
        # a target repo's OWN doc that merely shares a basename is NOT flagged ...
        self.assertEqual(
            find_context_artifact_references("see `docs/repo-summary.md` here"), [])
        # ... but a real bundle context/plan artifact still is.
        self.assertTrue(
            find_context_artifact_references("see `derived/planning-gaps.md`"))
        self.assertTrue(
            find_context_artifact_references("see `plans/section-plans.jsonl`"))

    def test_unused_manifest_citation_is_rejected(self):
        # validate_document must fail if the manifest carries a citation that no
        # section file actually uses (spec citation-resolution tests).
        root = self.fresh()
        b = gated(root)
        writing.run(opts_for(root), provider=default_provider(b))
        from wiki_generator.libs.writing.validate import validate_document
        out_dir = os.path.join(root, "wiki")
        generated = [json.loads(l) for l in open(os.path.join(
            out_dir, "metadata", "generated-sections.jsonl")) if l.strip()]
        manifest = json.load(open(os.path.join(out_dir, "metadata",
                                               "citation-manifest.json")))
        # ev:overview:0002 does not exist in any section file (overview has only
        # 0001), so it is an unused manifest entry the validator must reject.
        manifest["citations"].append({"evidence_id": "ev:overview:0002",
                                      "source": {"artifact": "x"}})
        b2 = gated(root)
        vd = validate_document(b2, generated, manifest, out_dir)
        self.assertEqual(vd["status"], "fail")
        self.assertTrue(any("no_unused_manifest_citations" in f
                            for f in vd["failures"]))


# ---------------------------------------------------------------------------
class ImportQualifiedNameSynthesisTests(unittest.TestCase):
    """Separate tokens do not evidence synthesized dotted names."""

    def test_from_import_does_not_support_synthesized_fqn(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "from package.module import Name\n"
        r = analyze_claims("Uses `package.module.Name`. [ev:x:0001]", available)
        self.assertIn("package.module.Name", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_quart_auth_import_does_not_support_synthesized_package_symbol(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "from quart_auth import AuthUser\n"
        r = analyze_claims("Uses `quart_auth.AuthUser`. [ev:x:0001]", available)
        self.assertIn("quart_auth.AuthUser", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_file_path_context_does_not_support_imported_symbol_fqn(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "path: agent/component/base.py\nfrom common import settings\n"
        r = analyze_claims("Uses `agent.settings`. [ev:x:0001]", available)
        self.assertIn("agent.settings", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_exact_full_dotted_token_in_evidence_supports_fqn(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "from package.module import Name\n# explicit token: package.module.Name\n"
        r = analyze_claims("Uses `package.module.Name`. [ev:x:0001]", available)
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_class_method_tokens_do_not_support_synthesized_member(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "class RAGFlowClient:\n    def login_user(self):\n        return None\n"
        r = analyze_claims("Uses `RAGFlowClient.login_user`. [ev:x:0001]", available)
        self.assertIn("RAGFlowClient.login_user", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_parser_private_method_tokens_do_not_support_known_dotted_failure(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "class Parser(object):\n    def _pdf(self, fnm):\n        return None\n"
        r = analyze_claims("Uses `Parser._pdf`. [ev:x:0001]", available)
        self.assertIn("Parser._pdf", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_exact_class_method_token_in_evidence_supports_member(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = ("class RAGFlowClient:\n    def login_user(self):\n        return None\n"
                     "# explicit token: RAGFlowClient.login_user\n")
        r = analyze_claims("Uses `RAGFlowClient.login_user`. [ev:x:0001]", available)
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_separate_evidenced_tokens_written_separately_are_allowed(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = "class RAGFlowClient:\n    def login_user(self):\n        return None\n"
        r = analyze_claims("Uses the `login_user` method on `RAGFlowClient`. "
                           "[ev:x:0001]", available)
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual(r["synthesized_identifiers"], [])


# ---------------------------------------------------------------------------
class NestedObjectKeyIdentifierTests(unittest.TestCase):
    """Nested object keys do not evidence synthesized dotted field paths."""

    def test_nested_json_keys_do_not_support_dotted_field_path(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = json.dumps({
            "evidence_id": "ev:http-api:0001",
            "excerpt": {
                "response": {
                    "data": {"graph": {"nodes": [], "edges": []}}
                }
            },
        }, indent=2)
        self.assertIn('"data"', available)
        self.assertIn('"graph"', available)
        self.assertNotIn("data.graph", available)

        r = analyze_claims("The response returns `data.graph`. [ev:http-api:0001]",
                           available)
        self.assertIn("data.graph", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

        safe = analyze_claims(
            "The response returns the `graph` field under the `data` object. "
            "[ev:http-api:0001]",
            available)
        self.assertEqual(safe["invented_identifiers"], [])
        self.assertEqual(safe["synthesized_identifiers"], [])


# ---------------------------------------------------------------------------
class SynthesizedIdentifierTests(unittest.TestCase):
    """Iteration 2: deterministic shell-variable path expansions are rewriteable
    `synthesized_identifier`s (never grounded); true inventions stay terminal.

    Regression for the live `deployment` failure where the model expanded
    CONF_DIR/CONF_FILE into the literal `/ragflow/conf/service_conf.yaml`."""

    SNIPPET = DEPLOYMENT_SHELL_EXCERPT

    def _claims(self, md):
        from wiki_generator.libs.writing.citations import analyze_claims
        return analyze_claims(md, self.SNIPPET)

    def test_conf_file_token_passes(self):
        r = self._claims("It writes to `CONF_FILE`. [ev:deployment:0001]")
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_brace_var_path_token_passes(self):
        r = self._claims("It writes `${CONF_DIR}/service_conf.yaml`. "
                         "[ev:deployment:0001]")
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_expanded_literal_is_synthesized_not_invented(self):
        r = self._claims("The script generates `/ragflow/conf/service_conf.yaml`. "
                         "[ev:deployment:0001]")
        self.assertEqual(r["invented_identifiers"], [])      # not terminal
        self.assertEqual(len(r["synthesized_identifiers"]), 1)
        syn = r["synthesized_identifiers"][0]
        self.assertEqual(syn["identifier"], "/ragflow/conf/service_conf.yaml")
        # exact evidence alternatives are suggested for the rewrite
        self.assertIn("CONF_FILE", syn["alternatives"])
        self.assertIn("${CONF_FILE}", syn["alternatives"])
        self.assertIn("${CONF_DIR}/service_conf.yaml", syn["alternatives"])

    def test_expanded_literal_in_fenced_block_is_synthesized(self):
        md = ("Generated config:\n\n```\n/ragflow/conf/service_conf.yaml\n```\n"
              "[ev:deployment:0001]")
        r = self._claims(md)
        self.assertEqual(r["invented_identifiers"], [])
        self.assertEqual([s["identifier"] for s in r["synthesized_identifiers"]],
                         ["/ragflow/conf/service_conf.yaml"])

    def test_sibling_expanded_literal_is_terminal_invented(self):
        # `/ragflow/conf/other.yaml` is not produced by any assignment -> terminal
        r = self._claims("It writes `/ragflow/conf/other.yaml`. [ev:deployment:0001]")
        self.assertIn("/ragflow/conf/other.yaml", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_ghost_path_is_terminal_invented(self):
        r = self._claims("The handler is in `app/ghost.py`. [ev:deployment:0001]")
        self.assertIn("app/ghost.py", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_directory_filename_synthesis_is_terminal_invented(self):
        # joining a dir + filename (not a shell-variable expansion) stays terminal
        r = self._claims("See `docker/service_conf.yaml`. [ev:deployment:0001]")
        self.assertIn("docker/service_conf.yaml", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_public_route_synthesis_is_terminal_invented(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        route = "/api/v1/datasets/{dataset_id}/documents"
        available = json.dumps({"source": {"route": "/datasets/<dataset_id>/documents"}})
        r = analyze_claims(f"Lists via `GET {route}`. [ev:x:0001]", available)
        self.assertIn(route, r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_api_version_route_prefix_synthesis_is_terminal_invented(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = json.dumps({"source": {"route": "/{api_version}"}})
        r = analyze_claims("Uses `/api/{api_version}`. [ev:x:0001]", available)
        self.assertIn("/api/{api_version}", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_fstring_api_version_template_does_not_support_normalized_route(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        available = 'return f"{self.host}:{self.port}/api/{self.api_version}"\n'
        r = analyze_claims("Uses `/api/{api_version}`. [ev:x:0001]", available)
        self.assertIn("/api/{api_version}", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_ambiguous_multi_target_expansion_is_terminal(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        # two distinct vars expand to the SAME literal -> >1 semantic target
        snippet = 'A="/x"\nB="/x"\nP="${A}/conf.yaml"\nQ="${B}/conf.yaml"\n'
        r = analyze_claims("Path `/x/conf.yaml`. [ev:x:0001]", snippet)
        self.assertIn("/x/conf.yaml", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_multi_step_expansion_is_terminal(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        # P -> ${M} -> ${D}: only ONE deterministic step is allowed, so the full
        # 2-step literal is not derivable and stays terminal invented
        snippet = 'D="/ragflow"\nM="${D}/conf"\nP="${M}/service_conf.yaml"\n'
        r = analyze_claims("Path `/ragflow/conf/service_conf.yaml`. [ev:x:0001]",
                           snippet)
        self.assertIn("/ragflow/conf/service_conf.yaml", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])

    def test_command_substitution_rhs_is_ignored(self):
        from wiki_generator.libs.writing.citations import analyze_claims
        # command substitution is not a deterministic literal -> no expansion map
        snippet = 'CONF_DIR="$(pwd)/conf"\nCONF_FILE="${CONF_DIR}/service_conf.yaml"\n'
        r = analyze_claims("Path `/home/app/conf/service_conf.yaml`. [ev:x:0001]",
                           snippet)
        self.assertIn("/home/app/conf/service_conf.yaml", r["invented_identifiers"])
        self.assertEqual(r["synthesized_identifiers"], [])


# ---------------------------------------------------------------------------
class SynthesizedIdentifierRewriteTests(TmpBundleMixin, unittest.TestCase):
    """Fake-provider integration: an expanded shell path is rejected as a
    rewriteable `synthesized_identifier`, the bounded rewrite swaps it for an
    exact evidence token, and the run passes — with no new evidence added."""

    def _base_responses(self, b):
        return {sid: draft_json(
            sid, b.section_plans[sid]["title"],
            valid_markdown(sid, b.section_plans[sid]["title"],
                           sorted(b.section_evidence_ids[sid])),
            used=sorted(b.section_evidence_ids[sid]))
            for sid in ("overview", "service")}

    def test_expanded_path_rewrites_to_exact_token_and_passes(self):
        root = self.fresh(with_deployment=True)
        bad = draft_json("deployment", "Deployment",
                         "## Deployment\n\nThe entrypoint script generates "
                         "`/ragflow/conf/service_conf.yaml` from the template. "
                         "[ev:deployment:0001]\n")
        good = draft_json("deployment", "Deployment",
                          "## Deployment\n\nThe entrypoint script renders the config "
                          "file referenced by `CONF_FILE`. [ev:deployment:0001]\n")
        b = gated(root)
        by = self._base_responses(b)
        by["deployment"] = [bad, good]
        prov = FakeProvider(by)
        res = writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(res.status, "pass", res.message)
        self.assertEqual(prov.calls.count("deployment"), 2)  # exactly one rewrite

        # rewrite audit records the unsupported id + exact suggested alternatives
        adir = os.path.join(root, "wiki", "audit", "rewrites", "deployment-attempt-1")
        for name in ("prompt.md", "response.raw.txt", "problems.json"):
            self.assertTrue(os.path.isfile(os.path.join(adir, name)), name)
        blob = json.dumps(json.load(open(os.path.join(adir, "problems.json"))))
        self.assertIn("synthesized_identifier", blob)
        self.assertIn("/ragflow/conf/service_conf.yaml", blob)
        self.assertIn("CONF_FILE", blob)

        # no new evidence was introduced for the section by the rewrite
        rows = [json.loads(l) for l in open(os.path.join(
            root, "wiki", "metadata", "generated-sections.jsonl")) if l.strip()]
        dep = next(r for r in rows if r["section_id"] == "deployment")
        self.assertEqual(dep["evidence_ids_available"], ["ev:deployment:0001"])
        # final assembled section uses the exact token, not the expanded literal
        with open(os.path.join(root, "wiki", "sections",
                               "003-deployment.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("CONF_FILE", text)
        self.assertNotIn("/ragflow/conf/service_conf.yaml", text)

    def test_rewrite_to_brace_var_token_also_passes(self):
        root = self.fresh(with_deployment=True)
        bad = draft_json("deployment", "Deployment",
                         "## Deployment\n\nGenerates `/ragflow/conf/service_conf.yaml`. "
                         "[ev:deployment:0001]\n")
        good = draft_json("deployment", "Deployment",
                          "## Deployment\n\nGenerates `${CONF_DIR}/service_conf.yaml` "
                          "from the template. [ev:deployment:0001]\n")
        b = gated(root)
        by = self._base_responses(b)
        by["deployment"] = [bad, good]
        res = writing.run(opts_for(root, max_rewrite_attempts=1),
                          provider=FakeProvider(by))
        self.assertEqual(res.status, "pass", res.message)

    def test_synthesized_not_passable_repeated_after_rewrite_fails(self):
        # a synthesized identifier is rewriteable but never silently passed: if the
        # rewrite repeats the expanded literal, the run still fails closed
        root = self.fresh(with_deployment=True)
        bad = draft_json("deployment", "Deployment",
                         "## Deployment\n\nGenerates `/ragflow/conf/service_conf.yaml`. "
                         "[ev:deployment:0001]\n")
        b = gated(root)
        by = self._base_responses(b)
        by["deployment"] = [bad, bad]
        prov = FakeProvider(by)
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(prov.calls.count("deployment"), 2)  # capped at one rewrite

    def test_synthesized_with_zero_rewrites_fails_closed(self):
        # with rewrites disabled the expanded literal is still rejected (no pass)
        root = self.fresh(with_deployment=True)
        bad = draft_json("deployment", "Deployment",
                         "## Deployment\n\nGenerates `/ragflow/conf/service_conf.yaml`. "
                         "[ev:deployment:0001]\n")
        b = gated(root)
        by = self._base_responses(b)
        by["deployment"] = bad
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=0),
                        provider=FakeProvider(by))


# ---------------------------------------------------------------------------
class MalformedEvidenceTokenUnitTests(unittest.TestCase):
    """Milestone 1: only `[ev:<section_id>:<NNNN>]` is valid; every other
    evidence-like token (the live `[ev:data-models:010]` shape, dangling openers,
    extra fields, bad section ids, bare `ev:` tokens) must fail loudly."""

    # the exact malformed examples the spec enumerates
    SPEC_MALFORMED = (
        ("[ev:data-models:010]", "wrong_ordinal_width"),       # three-digit ordinal
        ("[ev:data-models:00010]", "wrong_ordinal_width"),     # five-digit ordinal
        ("[ev:data-models:]", "missing_ordinal"),              # missing ordinal
        ("[ev:data-models]", "missing_ordinal_separator"),     # missing separator
        ("[ev:data models:0010]", "invalid_section_id"),       # space in section id
        ("[ev:data-models:0010", "dangling_opener"),           # dangling opener
        ("[ev:data-models:0010 extra]", "malformed_ordinal"),  # extra text
        ("[ev:data-models:0010:extra]", "extra_field"),        # extra field
    )

    def _find(self, md, **kw):
        from wiki_generator.libs.writing.citations import find_malformed_evidence_tokens
        return find_malformed_evidence_tokens(md, **kw)

    def test_every_spec_malformed_example_fails_with_category(self):
        for token, category in self.SPEC_MALFORMED:
            md = f"Prose before {token} prose after."
            diags = self._find(md)
            self.assertEqual(len(diags), 1, (token, diags))
            self.assertEqual(diags[0]["token"], token, token)
            self.assertEqual(diags[0]["category"], category, token)
            self.assertTrue(diags[0]["remediation"], token)
            self.assertGreaterEqual(diags[0]["line"], 1)
            self.assertGreaterEqual(diags[0]["column"], 1)

    def test_canonical_citation_is_not_flagged(self):
        md = ("ok [ev:data-models:0010] adjacent [ev:a:0001][ev:b:0002] "
              "and a known-but-unknown [ev:x:9999] is well-formed too")
        self.assertEqual(self._find(md), [])

    def test_dangling_opener_does_not_swallow_next_token(self):
        # two [ev: openers on one line: the first is dangling, the second canonical
        md = "first [ev:a:0001 second [ev:b:0002]"
        diags = self._find(md)
        self.assertEqual([d["token"] for d in diags], ["[ev:a:0001"])
        self.assertEqual(diags[0]["category"], "dangling_opener")

    def test_bare_unbracketed_token_is_flagged(self):
        diags = self._find("see ev:service:01 written without brackets")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["category"], "unbracketed_token")
        self.assertEqual(diags[0]["candidate"], "ev:service:0001")

    def test_malformed_inside_a_valid_run_is_isolated(self):
        diags = self._find("[ev:a:0001][ev:b:01][ev:c:0003]")
        self.assertEqual([d["token"] for d in diags], ["[ev:b:01]"])

    def test_line_and_column_are_reported(self):
        md = "line one\nline two [ev:x:1] tail"
        d = self._find(md)[0]
        self.assertEqual(d["line"], 2)
        self.assertEqual(d["column"], md.split("\n")[1].index("[ev") + 1)

    def test_section_context_is_attached(self):
        d = self._find("[ev:x:1]", section_id="overview",
                       section_file="wiki/sections/001-overview.md")[0]
        self.assertEqual(d["section_id"], "overview")
        self.assertEqual(d["section_file"], "wiki/sections/001-overview.md")


# ---------------------------------------------------------------------------
class MalformedCitationResolutionTests(unittest.TestCase):
    """`resolve_citations` reports malformed tokens and only suggests a padded id
    when that exact id resolves in the bundle (deterministic + safe — spec rule 8)."""

    def _resolve(self, md, index, sec):
        from wiki_generator.libs.writing.citations import resolve_citations
        return resolve_citations(md, section_id="data-models", evidence_index=index,
                                 section_evidence_ids=sec)

    def test_padded_known_resolves_unknown_fails_malformed_flagged(self):
        index = {"ev:data-models:0010": object()}
        sec = {"data-models": {"ev:data-models:0010"}}
        r = self._resolve(
            "bad [ev:data-models:010] ok [ev:data-models:0010] gone "
            "[ev:data-models:9999]", index, sec)
        # the exact four-digit known id resolves ...
        self.assertEqual(r["resolved"], ["ev:data-models:0010"])
        # ... a well-formed but unknown id fails resolution (not silently dropped) ...
        self.assertEqual(r["unresolved"], ["ev:data-models:9999"])
        # ... and the three-digit token is malformed, not resolved/unresolved.
        mt = {d["token"]: d for d in r["malformed_tokens"]}
        self.assertEqual(set(mt), {"[ev:data-models:010]"})
        self.assertEqual(mt["[ev:data-models:010]"]["suggestion"],
                         "[ev:data-models:0010]")
        self.assertEqual(r["malformed_like"], ["[ev:data-models:010]"])

    def test_no_suggestion_when_padded_id_absent_from_manifest(self):
        # zero-padding `010` -> `0010` is only suggested when `ev:...:0010` exists
        r = self._resolve("bad [ev:data-models:010]", {}, {})
        self.assertEqual(len(r["malformed_tokens"]), 1)
        self.assertIsNone(r["malformed_tokens"][0].get("suggestion"))


# ---------------------------------------------------------------------------
class MalformedCitationRewriteTests(TmpBundleMixin, unittest.TestCase):
    """Fake-provider integration: a first draft carries the malformed
    `[ev:service:001]` token, the bounded rewrite is fed clear feedback, the
    corrected draft uses an exact manifest citation, and final validation passes —
    plus the fail-closed path when the rewrite leaves the malformed token."""

    def _overview(self):
        return draft_json("overview", "Overview",
                          valid_markdown("overview", "Overview", ["ev:overview:0001"]))

    BAD = ("## Service Layer\n\nThe service subsystem handles requests. "
           "[ev:service:001]\n")

    def test_malformed_citation_rewritten_then_passes(self):
        root = self.fresh()
        good = draft_json("service", "Service Layer",
                          valid_markdown("service", "Service Layer", ["ev:service:0001"]))
        prov = FakeProvider({"overview": self._overview(),
                             "service": [draft_json("service", "Service Layer",
                                                    self.BAD), good]})
        res = writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(res.status, "pass", res.message)
        self.assertEqual(prov.calls.count("service"), 2)         # exactly one rewrite

        # the rewrite prompt + audit carried the malformed-token feedback ...
        adir = os.path.join(root, "wiki", "audit", "rewrites", "service-attempt-1")
        for name in ("prompt.md", "response.raw.txt", "problems.json"):
            self.assertTrue(os.path.isfile(os.path.join(adir, name)), name)
        probs = json.dumps(json.load(open(os.path.join(adir, "problems.json"))))
        self.assertIn("malformed_citation_syntax", probs)
        self.assertIn("[ev:service:001]", probs)
        self.assertIn("[ev:service:0001]", probs)               # safe suggestion

        # ... and the final section file uses the exact token, never the malformed one
        with open(os.path.join(root, "wiki", "sections", "002-service.md"),
                  encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[ev:service:0001]", text)
        self.assertNotIn("[ev:service:001]", text)

    def test_malformed_citation_rewrite_exhausted_fails_closed(self):
        root = self.fresh()
        prov = FakeProvider({"overview": self._overview(),
                             "service": [draft_json("service", "Service Layer", self.BAD),
                                         draft_json("service", "Service Layer", self.BAD)]})
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=1), provider=prov)
        self.assertEqual(prov.calls.count("service"), 2)         # capped at one rewrite

    def test_malformed_citation_with_zero_rewrites_fails_closed(self):
        root = self.fresh()
        prov = FakeProvider({"overview": self._overview(),
                             "service": draft_json("service", "Service Layer", self.BAD)})
        with self.assertRaises(writing.WritingValidationFailure):
            writing.run(opts_for(root, max_rewrite_attempts=0), provider=prov)

    def test_final_validation_rejects_malformed_token_in_section_file(self):
        # a malformed token that reaches an assembled section file is terminal in
        # final whole-document validation — never silently edited/auto-corrected.
        root = self.fresh()
        b = gated(root)
        writing.run(opts_for(root), provider=default_provider(b))
        from wiki_generator.libs.writing.validate import validate_document
        out_dir = os.path.join(root, "wiki")
        svc = os.path.join(out_dir, "sections", "002-service.md")
        with open(svc, "a", encoding="utf-8") as f:
            f.write("\nStray token [ev:service:001].\n")
        generated = [json.loads(l) for l in open(os.path.join(
            out_dir, "metadata", "generated-sections.jsonl")) if l.strip()]
        manifest = json.load(open(os.path.join(out_dir, "metadata",
                                               "citation-manifest.json")))
        vd = validate_document(gated(root), generated, manifest, out_dir)
        self.assertEqual(vd["status"], "fail")
        self.assertTrue(any("no_malformed_citations" in f for f in vd["failures"]))
        # the safe suggestion (the padded id resolves via the manifest) is surfaced
        self.assertTrue(any("suggestion" in f for f in vd["failures"]))


# ---------------------------------------------------------------------------
class IsolationTests(unittest.TestCase):
    """Phase 4 must never invoke Phase 3 retrieval, Phase 2 repair, or a planner.

    Checks the *invocation mechanisms*, not string literals: Phase 4 legitimately
    reads the string ``retrieve-evidence`` out of a command manifest (provenance)
    and reuses ``evidence.schema.validate_packet`` (a pure validator), neither of
    which runs another phase."""

    def test_writing_package_spawns_no_process_and_calls_no_phase_command(self):
        import glob
        files = (glob.glob(os.path.join(SRC, "wiki_generator", "libs", "writing",
                                        "*.py"))
                 + [os.path.join(SRC, "wiki_generator", "libs", "commands",
                                 "write_wiki.py")])
        # process spawning + calling another phase's command/orchestrator entrypoint
        banned = ("subprocess", "os.system", "os.popen", "os.exec",
                  "evidence.run(", "import retrieve_evidence", "import plan_repair",
                  "import normalize_plan", "import decompose", "commands.plan")
        for f in files:
            text = open(f, encoding="utf-8").read()
            for token in banned:
                self.assertNotIn(token, text, f"{os.path.basename(f)} -> {token}")


def _snapshot(d: str) -> dict:
    out = {}
    for base, _, files in os.walk(d):
        for name in files:
            p = os.path.join(base, name)
            with open(p, encoding="utf-8") as f:
                out[os.path.relpath(p, d)] = f.read()
    return out


if __name__ == "__main__":
    unittest.main()
