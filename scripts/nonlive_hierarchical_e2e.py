#!/usr/bin/env python3
"""Non-live hierarchical end-to-end validation harness (NO model calls, ever).

Proves the three DeepWiki coverage-enhancement gates work *together* over an
expanded, multi-family, hierarchical plan, using the real production CLI surfaces:

    expanded hierarchical plan
      -> normalize-plan   --coverage-mode enhancement   (Phase 2 planned gate)
      -> retrieve-evidence --coverage-mode enhancement   (Phase 3 evidenced gate)
      -> write-wiki --provider gemini-gem --coverage-mode enhancement
                                                         (Phase 4 generated gate)
      -> benchmark-only coverage/structure comparison

Everything is deterministic and offline:

* A synthetic mini-repo (``ragdemo``) is built with one real Python module + class
  per mandatory topic family, so decompose/retrieval produce genuine, citeable
  exact-lane evidence (a real ``symbol_anchor`` per required topic).
* A raw Phase 2 planner response is authored as a fenced markdown fixture and fed
  to the **real** ``normalize-plan`` (no Gemini/Vertex); the deterministic 13-family
  planned-coverage gate runs and writes ``plans/coverage-gate.json``.
* ``retrieve-evidence --coverage-mode enhancement`` produces real evidenced coverage.
* Phase 4 uses the **real** ``gemini-gem`` import path: per-section response files
  are synthesized *deterministically from the real Phase 3 evidenced-coverage matrix*
  (the exact mapped ``evidence_id`` values) — this is fixture data, not a model call.
  The production CLI re-gates, re-validates, and assembles independently.

The harness never weakens a validator, never synthesizes evidence (it cites only
the exact IDs Phase 3 already mapped), and never calls a billed/live model. If any
gate, wrapper, or validator fails, it fails loudly and writes a FAIL result doc.

Usage:
    uv run python scripts/nonlive_hierarchical_e2e.py --run-dir <dir> \
        [--benchmark /path/to/ragflow-deepwiki.md]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)

from wiki_generator.libs.coverage.taxonomy import (  # noqa: E402
    MANDATORY_TOPIC_FAMILIES,
)

# --- the expanded multi-family hierarchical plan ------------------------------
# One section per mandatory topic family. Each declares its family's canonical
# coverage label (so the planned-coverage gate matches by exact label), one
# concrete required topic backed by a real class symbol, and (for children) a
# parent so the index renders a real two-level hierarchy. Topics are punctuation-
# free so the writer's heading slug equals the declared anchor.
FAMILIES = [
    # sid, title, label, package dir, class symbol, required topic, parent
    ("retrieval-internals", "Retrieval and Search Internals", "retrieval-internals",
     "ragdemo/retrieval", "HybridSearcher",
     "hybrid search and document store internals", None),
    ("doc-processing", "Document Processing Pipeline", "doc-processing",
     "ragdemo/docproc", "DeepDocParser",
     "deepdoc parser factory and chunking strategy", "retrieval-internals"),
    ("llm-internals", "LLM Provider Internals", "llm-internals",
     "ragdemo/llm", "LlmBundleRegistry",
     "llmbundle tool calling and retry backoff", "retrieval-internals"),
    ("queue-system", "Task Queues and Redis Streams", "queue-system",
     "ragdemo/queue", "RedisStreamQueue",
     "redis streams task lifecycle and workers", None),
    ("memory", "Memory System", "memory",
     "ragdemo/memory", "EpisodicMemoryStore",
     "episodic and procedural memory apis", "queue-system"),
    ("helm-k8s", "Kubernetes and Helm Deployment", "helm-k8s",
     "ragdemo/deploy", "HelmChartRenderer",
     "helm chart values and ingress manifests", None),
    # NB: avoid a package dir named ``build`` — decompose excludes build-artifact
    # directories (build/dist/node_modules/...), so the symbol would never index.
    ("ci-cd-build", "Build System and CI CD", "ci-cd-build",
     "ragdemo/cicd", "BuildPipeline",
     "github actions docker build flow", "helm-k8s"),
    ("migrations-operations", "Migrations and Operations", "migrations-operations",
     "ragdemo/ops", "SchemaMigrator",
     "database migration and schema sync", "helm-k8s"),
    ("user-tenant-admin-health", "User Tenant Admin and System Health",
     "user-tenant-admin-health", "ragdemo/admin", "TenantAdminService",
     "tenant management and health endpoint", None),
    ("sandbox-executor", "Sandbox Code Executor", "sandbox-executor",
     "ragdemo/sandbox", "SandboxExecutorManager",
     "code executor and provider registry", "user-tenant-admin-health"),
    ("frontend", "Frontend and UI Architecture", "frontend",
     "ragdemo/frontend", "FrontendRouter",
     "frontend routing and ui components", None),
    ("go-native", "Go Server and Native Components", "go-native",
     "ragdemo/native", "GoNativeBridge",
     "go server build modes and native services", None),
    ("glossary", "Glossary", "glossary",
     "ragdemo", "GlossaryIndex",
     "repo terminology and acronyms", None),
]


def _module_source(cls: str, title: str, topic: str, vocab: str) -> str:
    """Deterministic real Python module exposing one uniquely-named class symbol.

    The class is the citeable ``symbol_anchor`` for the family's required topic.
    The module/class docstrings carry the family's distinctive vocabulary so the
    decomposition surfaces it; the prose written later cites only the exact
    evidence id, never the symbol name."""
    return (
        f'"""{title} module.\n\n'
        f'{vocab}\n'
        f'"""\n'
        f'from __future__ import annotations\n\n\n'
        f'class {cls}:\n'
        f'    """{cls}: {topic}.\n\n'
        f'    {vocab}\n'
        f'    """\n\n'
        f'    def __init__(self, config: dict | None = None) -> None:\n'
        f'        self.config = config or {{}}\n\n'
        f'    def handle(self, payload):\n'
        f'        """Handle work for {topic}."""\n'
        f'        return payload\n'
    )


def synth_repo(repo: str) -> None:
    """Write the deterministic synthetic repo with one module per family."""
    if os.path.exists(repo):
        shutil.rmtree(repo)
    os.makedirs(repo)
    pkg_dirs: set[str] = set()
    for sid, title, _label, pkgdir, cls, topic, _parent in FAMILIES:
        vocab = (f"This subsystem covers {topic} for the ragdemo reference service. "
                 f"It is a deterministic fixture used to exercise the {sid} topic "
                 "family in the coverage-enhancement pipeline.")
        mod_path = os.path.join(repo, pkgdir, f"{sid.replace('-', '_')}.py")
        os.makedirs(os.path.dirname(mod_path), exist_ok=True)
        with open(mod_path, "w", encoding="utf-8") as f:
            f.write(_module_source(cls, title, topic, vocab))
        # remember every package directory between repo root and the module
        rel = pkgdir
        while rel and rel != ".":
            pkg_dirs.add(rel)
            rel = os.path.dirname(rel)
    for d in sorted(pkg_dirs):
        init_path = os.path.join(repo, d, "__init__.py")
        if not os.path.isfile(init_path):
            with open(init_path, "w", encoding="utf-8") as f:
                f.write('"""ragdemo package."""\n')
    with open(os.path.join(repo, "ragdemo", "__init__.py"), "w") as f:
        f.write('"""ragdemo: deterministic multi-family reference service."""\n')
    with open(os.path.join(repo, "pyproject.toml"), "w", encoding="utf-8") as f:
        f.write('[project]\nname = "ragdemo"\nversion = "0.1.0"\n'
                'description = "Deterministic multi-family reference service."\n')
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("# ragdemo\n\nA deterministic, multi-subsystem reference service "
                "used as a non-live coverage-enhancement E2E fixture.\n")


# --- raw Phase 2 planner response (fed to the REAL normalize-plan) -------------
def build_raw_plan() -> str:
    """Author the fenced raw planner response that ``normalize-plan`` parses.

    A ``document-plan.json`` fence (section order + titles) plus a
    ``section-plans.jsonl`` fence (one planner section per family). Symbols are
    bare class names resolved by normalization to exact ``symbol_anchor`` lanes;
    each required topic carries a ``topic_evidence_requirements[]`` bridge pointing
    at ``retrieval_needs.symbols[0]`` so Phase 3 can map it to citeable evidence."""
    doc_sections = [{"id": sid, "title": title} for sid, title, *_ in FAMILIES]
    document_plan = {
        "repo": "ragdemo",
        "title": "RAGdemo Repository Guide",
        "purpose": "A DeepWiki-informed, citation-grounded guide to the ragdemo "
                   "reference service.",
        "audience": "developers and operators",
        "sections": doc_sections,
    }
    plans = []
    for sid, title, label, _pkg, cls, topic, parent in FAMILIES:
        plan = {
            "section_id": sid,
            "title": title,
            "section_role": "source",
            "coverage_labels": [label],
            "required_topics": [topic],
            "topic_evidence_requirements": [
                {"topic": topic, "required": True,
                 "source_fields": ["retrieval_needs.symbols[0]"],
                 "min_items": 1, "acceptable_lanes": ["symbol_anchor"]},
            ],
            "evidence_needs": {"symbols": [cls]},
        }
        if parent:
            plan["parent_id"] = parent
        plans.append(plan)
    jsonl = "\n".join(json.dumps(p) for p in plans)
    return ("```text\nplans/document-plan.json\n```\n"
            "```json\n" + json.dumps(document_plan, indent=2) + "\n```\n"
            "```text\nplans/section-plans.jsonl\n```\n"
            "```jsonl\n" + jsonl + "\n```\n")


# --- deterministic gemini-gem response fixtures -------------------------------
def _heading_anchor(topic: str) -> str:
    return topic.replace(" ", "-")


def build_gem_response(sid: str, title: str, obligations: list) -> str:
    """Build one deterministic section-draft JSON (the verbatim 'Gem response').

    Mirrors the proven fake-provider shape from tests: one ``### <topic>`` block per
    obligation that cites exactly the Phase 3 mapped evidence ids, and a matching
    ``covered_topics[]`` declaration. No model call — the ids come straight from the
    real evidenced-coverage matrix."""
    parts = [f"## {title}", ""]
    covered = []
    used: list[str] = []
    for ob in obligations:
        topic = ob["topic"]
        ids = list(ob["mapped_evidence_ids"])
        used += ids
        cites = "".join(f"[{i}]" for i in ids)
        parts.append(f"### {topic.title()}")
        parts.append("")
        parts.append(f"The {topic} is implemented as the cited evidence shows. "
                     f"{cites}")
        parts.append("")
        covered.append({"topic": topic, "status": "covered",
                        "evidence_ids": ids,
                        "markdown_anchor": _heading_anchor(topic)})
    markdown = "\n".join(parts) + "\n"
    draft = {
        "schema_version": "phase4-section-draft-v1",
        "section_id": sid,
        "title": title,
        "markdown": markdown,
        "used_evidence_ids": sorted(set(used)),
        "covered_topics": covered,
        "self_check": {"no_uncited_repo_claims": True,
                       "no_context_artifact_citations": True,
                       "no_placeholders": True},
    }
    return json.dumps(draft, indent=2) + "\n"


def write_gem_fixtures(bundle: str, gem_dir: str) -> dict:
    """Read the REAL Phase 3 evidenced-coverage matrix + plan, write one
    deterministic ``<sid>.raw.txt`` per section. Fail loudly if any required topic
    is not ``sufficient`` (that would mean Phase 3 should have blocked already)."""
    os.makedirs(gem_dir, exist_ok=True)
    with open(os.path.join(bundle, "evidence", "evidenced-coverage.json")) as f:
        ec = json.load(f)
    titles = {}
    with open(os.path.join(bundle, "plans", "section-plans.jsonl")) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                titles[r["section_id"]] = r.get("title") or r["section_id"]
    summary = {"sections": 0, "obligations": 0}
    for sec in ec.get("sections", []):
        sid = sec["section_id"]
        obligations = []
        for t in sec.get("topics", []):
            if not t.get("required"):
                continue
            if t.get("status") != "sufficient":
                raise SystemExit(
                    f"FATAL: required topic {t.get('topic')!r} in section {sid!r} is "
                    f"{t.get('status')!r}, not sufficient — Phase 3 enhancement "
                    "should have blocked before Phase 4. Fix upstream.")
            obligations.append({"topic": t["topic"],
                                "mapped_evidence_ids": list(t.get("mapped_evidence_ids") or [])})
            if not obligations[-1]["mapped_evidence_ids"]:
                raise SystemExit(
                    f"FATAL: sufficient topic {t['topic']!r} in {sid!r} has no mapped "
                    "evidence ids; refusing to synthesize evidence.")
        if not obligations:
            raise SystemExit(
                f"FATAL: section {sid!r} has no sufficient required topic; the E2E "
                "must exercise evidenced+generated coverage for every section.")
        text = build_gem_response(sid, titles.get(sid, sid), obligations)
        with open(os.path.join(gem_dir, f"{sid}.raw.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        summary["sections"] += 1
        summary["obligations"] += len(obligations)
    return summary


# --- command running + recording ----------------------------------------------
class Runner:
    def __init__(self, run_dir: str):
        self.run_dir = run_dir
        self.manifest = os.path.join(run_dir, "command-manifest.tsv")
        self.transcript = os.path.join(run_dir, "command-transcript.log")
        with open(self.manifest, "w") as f:
            f.write("step\tcommand\texit_code\n")
        with open(self.transcript, "w") as f:
            f.write("# Non-live hierarchical E2E command transcript\n\n")
        self.env = dict(os.environ)
        self.env["PYTHONPATH"] = SRC + os.pathsep + self.env.get("PYTHONPATH", "")

    def cli(self, step: str, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "wiki_generator", *args]
        return self._run(step, cmd, expect=expect)

    def _run(self, step, cmd, expect):
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                             timeout=600, env=self.env)
        printable = " ".join(
            a if a == sys.executable else (os.path.relpath(a, REPO)
                                           if a.startswith(REPO) else a)
            for a in cmd)
        printable = printable.replace(sys.executable, "python")
        with open(self.manifest, "a") as f:
            f.write(f"{step}\t{printable}\t{res.returncode}\n")
        with open(self.transcript, "a") as f:
            f.write(f"\n===== {step} (exit {res.returncode}) =====\n$ {printable}\n")
            tail_out = "\n".join(res.stdout.strip().splitlines()[-25:])
            tail_err = "\n".join(res.stderr.strip().splitlines()[-40:])
            if tail_out:
                f.write("--- stdout (tail) ---\n" + tail_out + "\n")
            if tail_err:
                f.write("--- stderr (tail) ---\n" + tail_err + "\n")
        if res.returncode != expect:
            sys.stderr.write(
                f"\nSTEP {step} expected exit {expect} got {res.returncode}\n"
                f"STDERR:\n{res.stderr[-3000:]}\n")
            raise SystemExit(f"E2E step {step!r} failed (see {self.transcript})")
        return res

    def help_capture(self, step: str, script: str) -> None:
        """Capture a wrapper --help into the transcript to prove the operator
        surface exposes --coverage-mode (no install runs on --help)."""
        cmd = ["bash", os.path.join(REPO, "scripts", script), "--help"]
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                             timeout=60)
        with open(self.manifest, "a") as f:
            f.write(f"{step}\tscripts/{script} --help\t{res.returncode}\n")
        cov = [ln for ln in res.stdout.splitlines() if "coverage-mode" in ln]
        with open(self.transcript, "a") as f:
            f.write(f"\n===== {step} (exit {res.returncode}) =====\n"
                    f"$ scripts/{script} --help\n")
            f.write("--- coverage-mode help line ---\n" + "\n".join(cov) + "\n")


# --- benchmark-only comparison ------------------------------------------------
def benchmark_compare(run_dir: str, bundle: str, benchmark: str | None) -> dict:
    """Benchmark-ONLY structure/coverage comparison. Reads ``ragflow-deepwiki.md``
    purely as a structural benchmark: counts its headings and, per mandatory family,
    a boolean of whether the benchmark's text contains the family's distinctive
    signals. It NEVER copies benchmark prose/headings and NEVER treats the benchmark
    as citeable evidence."""
    gen_families = {sid for sid, *_ in FAMILIES}
    out = {
        "benchmark_path": benchmark,
        "benchmark_available": bool(benchmark and os.path.isfile(benchmark)),
        "benchmark_heading_count": 0,
        "generated_section_count": len(FAMILIES),
        "generated_families_covered": sorted(gen_families),
        "family_rows": [],
    }
    text = ""
    if out["benchmark_available"]:
        with open(benchmark, encoding="utf-8", errors="replace") as f:
            text = f.read()
        out["benchmark_heading_count"] = sum(
            1 for ln in text.splitlines() if ln.lstrip().startswith("#"))
        out["benchmark_line_count"] = len(text.splitlines())
    low = text.casefold()
    for fam in MANDATORY_TOPIC_FAMILIES:
        signals = list(fam.all_labels) + list(fam.keywords)
        present = any(s.casefold() in low for s in signals) if text else None
        out["family_rows"].append({
            "family": fam.key,
            "benchmark_signal_present": present,
            "generated_covered": fam.key in gen_families,
        })
    with open(os.path.join(run_dir, "COMPARISON_WITH_RAGFLOW_DEEPWIKI.md"), "w",
              encoding="utf-8") as f:
        f.write(_render_comparison(out))
    return out


def _render_comparison(out: dict) -> str:
    lines = [
        "# Benchmark-only coverage/structure comparison",
        "",
        "> **Benchmark only — never citeable evidence.** `ragflow-deepwiki.md` is a "
        "coverage/structure warning signal. No benchmark prose, headings, or claims "
        "are copied into the generated wiki, and line count is NOT a target. This "
        "note compares *structure and topic-family coverage* only.",
        "",
        "## Structure",
        "",
        f"- Benchmark available: {out['benchmark_available']}",
        f"- Benchmark headings (structural count): {out['benchmark_heading_count']}",
    ]
    if out.get("benchmark_line_count"):
        lines.append(f"- Benchmark lines (structural count): {out['benchmark_line_count']}")
    lines += [
        f"- Generated sections (this non-live run): {out['generated_section_count']} "
        "across a two-level parent/child hierarchy",
        "",
        "## Topic-family coverage (planned + evidenced + generated)",
        "",
        "Every mandatory family is planned, evidenced, and generated in this run. The "
        "`benchmark_signal_present` column only reflects whether the benchmark text "
        "mentions a family's distinctive signals (a structural gap indicator), not "
        "any benchmark content.",
        "",
        "| family | generated_covered | benchmark_signal_present |",
        "|---|---|---|",
    ]
    for r in out["family_rows"]:
        bench = ("—" if r["benchmark_signal_present"] is None
                 else ("yes" if r["benchmark_signal_present"] else "no"))
        lines.append(f"| `{r['family']}` | "
                     f"{'yes' if r['generated_covered'] else 'no'} | {bench} |")
    lines += [
        "",
        "## Reading",
        "",
        "- The benchmark is far larger and flatter; this non-live run deliberately "
        "does not chase its line count. The objective is hierarchical, grounded "
        "topic-family coverage with citation discipline.",
        "- This synthetic fixture covers all 13 mandatory families with one grounded "
        "required topic each. A real RAGFlow run would expand depth per family where "
        "repository evidence supports it; remaining depth gaps are an evidence/"
        "planning scope question, never a benchmark-copy exercise.",
        "",
    ]
    return "\n".join(lines)


# --- result doc ---------------------------------------------------------------
def _read_json(path: str):
    with open(path) as f:
        return json.load(f)


def write_result(run_dir: str, bundle: str, *, determinism_ok: bool,
                 rerun_note: str, bench: dict, gem_summary: dict,
                 negative_ok: bool) -> str:
    planned = _read_json(os.path.join(bundle, "plans", "coverage-gate.json"))
    evid = _read_json(os.path.join(bundle, "evidence", "evidenced-coverage.json"))
    gen = _read_json(os.path.join(bundle, "wiki", "metadata", "generated-coverage.json"))
    wv = _read_json(os.path.join(bundle, "wiki", "validation", "writing-validation.json"))
    doc = _read_json(os.path.join(bundle, "wiki", "metadata", "generated-document.json"))
    rv = _read_json(os.path.join(bundle, "evidence", "retrieval-validation.json"))
    cite_manifest = _read_json(
        os.path.join(bundle, "wiki", "metadata", "citation-manifest.json"))

    planned_ok = planned.get("passed") and planned["report"]["status"] == "pass"
    evid_ok = evid.get("status") == "pass" and evid.get("enforced")
    gen_ok = gen.get("status") == "pass"
    wv_ok = wv.get("status") == "pass"
    verdict = all([planned_ok, evid_ok, gen_ok, wv_ok, determinism_ok, negative_ok])

    ev_counts = (rv.get("counts") if isinstance(rv, dict) else {}) or {}
    lines = [
        "# Non-live Hierarchical E2E — Result",
        "",
        f"## Verdict: {'PASS' if verdict else 'FAIL'}",
        "",
        "All three DeepWiki coverage-enhancement gates were exercised together over "
        "one fresh, expanded, multi-family, hierarchical plan using the real "
        "production CLI. No Vertex / Gemini API / Gemini Gem live call / network "
        "model call was made; Phase 4 used the deterministic `gemini-gem` import path "
        "with fixtures synthesized from the real Phase 3 evidenced-coverage matrix.",
        "",
        "## Layout",
        "",
        "- `bundle/` — the working Phase 1-3 bundle + generated `wiki/`",
        "- `bundle/repo/` is the synthetic 13-family `ragdemo` fixture repo",
        "- `command-manifest.tsv` / `command-transcript.log` — exact commands + exits",
        "- `gem-responses/` — deterministic per-section Gem response fixtures (no model)",
        "- `COMPARISON_WITH_RAGFLOW_DEEPWIKI.md` — benchmark-only structure comparison",
        "",
        "## Gate statuses",
        "",
        "| gate | command | status |",
        "|---|---|---|",
        f"| Phase 2 planned coverage | `normalize-plan --coverage-mode enhancement` | "
        f"{'PASS' if planned_ok else 'FAIL'} "
        f"({planned['report']['covered_count']}/{planned['report']['family_count']} "
        "families) |",
        f"| Phase 3 evidenced coverage | `retrieve-evidence --coverage-mode enhancement` "
        f"| {'PASS' if evid_ok else 'FAIL'} |",
        f"| Phase 4 generated coverage | `write-wiki --provider gemini-gem "
        f"--coverage-mode enhancement` | {'PASS' if gen_ok else 'FAIL'} |",
        f"| Phase 4 writing validation | (whole-document) | "
        f"{'PASS' if wv_ok else 'FAIL'} |",
        "",
        "## Coverage + evidence counts",
        "",
        f"- Planned mandatory families covered: "
        f"{planned['report']['covered_count']}/{planned['report']['family_count']}",
        f"- Evidenced required topics: {evid['counts']['required_topics']} "
        f"(sufficient={evid['counts']['sufficient']}, weak={evid['counts']['weak']}, "
        f"missing={evid['counts']['missing']})",
        f"- Generated required topics: {gen['counts']['required_topics']} "
        f"(covered={gen['counts']['covered']}, omitted={gen['counts']['omitted']}, "
        f"invalid={gen['counts']['invalid']})",
        f"- Evidence packets/items: {ev_counts.get('packets_written', '?')} "
        f"section packets, {ev_counts.get('evidence_items', '?')} evidence items",
        f"- Distinct citations in wiki: "
        f"{(cite_manifest or {}).get('counts', {}).get('distinct_citations', '?')}",
        f"- Sections + obligations generated: {gem_summary['sections']} sections, "
        f"{gem_summary['obligations']} obligations",
        "",
        "## Hierarchy",
        "",
        f"- `generated-document.json` coverage_mode = `{doc.get('coverage_mode')}`, "
        f"generated_coverage_status = `{doc.get('generated_coverage_status')}`",
        "- Two-level parent/child hierarchy preserved in `wiki/index.md`, "
        "`generated-sections.jsonl`, and `generated-document.json` `hierarchy[]`.",
        "",
        "## Determinism / rerun",
        "",
        f"- {rerun_note}",
        "",
        "## Strictness probe (negative, self-evidencing)",
        "",
        f"- Phase 4 enhancement mode refuses pre-provider when the upstream planned-"
        f"coverage gate is absent: {'PASS (exit 3, no provider call)' if negative_ok else 'FAIL'}.",
        "- Additional negatives (missing/baseline/failed planned gate, baseline/missing "
        "evidenced gate, missing retrieval contract check; omitted/uncited/out-of-scope/"
        "placeholder generated topic; compact/broad-parent plan missing families) are "
        "proven by `tests/test_phase4_generated_coverage.py`, "
        "`tests/test_phase3_evidenced_coverage.py`, and "
        "`tests/test_phase2_enhancement_gate.py`.",
        "",
        "## Writing-validation checks (all must pass)",
        "",
    ]
    for c in wv.get("checks", []):
        lines.append(f"- `{c['name']}`: {c['status']}")
    lines += [
        "",
        "## Benchmark-only comparison",
        "",
        f"- Benchmark available: {bench['benchmark_available']}; headings "
        f"(structural): {bench['benchmark_heading_count']}. See "
        "`COMPARISON_WITH_RAGFLOW_DEEPWIKI.md`. Benchmark is never citeable evidence "
        "and no prose was copied.",
        "",
        "## Risks / notes",
        "",
        "- This is a **synthetic** fixture repo: it proves the gates interoperate and "
        "stay strict, not that RAGFlow itself has sufficient evidence for every "
        "family. A real run still depends on real repository evidence.",
        "- Enhancement mode remains opt-in and is NOT wired into the default Phase 4 "
        "path (compact fixtures intentionally fail the 13-family gate).",
        "- Phase 4 fixtures cite ONLY the exact Phase 3 mapped evidence ids; the "
        "production CLI re-gates and re-validates independently (no validator was "
        "weakened, no evidence synthesized).",
        "",
        "## Next recommendation",
        "",
        ("- Gates interoperate cleanly on a non-live hierarchical run. A live/billed "
         "retry over real RAGFlow MAY now be proposed to the user, but the default "
         "remains **no live retry** until the user explicitly approves it."
         if verdict else
         "- DO NOT request a live retry: a gate/validator failed above. Fix upstream "
         "and rerun this non-live E2E first."),
        "",
    ]
    path = os.path.join(run_dir, "NON_LIVE_HIERARCHICAL_E2E_RESULT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path, verdict


# --- orchestration ------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--benchmark",
                    default="/Users/ankitsingh/Documents/deep-wiki/ragflow-deepwiki.md")
    args = ap.parse_args()

    run_dir = os.path.abspath(os.path.expanduser(args.run_dir))
    os.makedirs(run_dir, exist_ok=True)
    bundle = os.path.join(run_dir, "bundle")
    repo = os.path.join(bundle, "repo")
    gem_dir = os.path.join(run_dir, "gem-responses")
    os.makedirs(bundle, exist_ok=True)

    r = Runner(run_dir)
    print(f"[e2e] run dir: {run_dir}")

    # 0. prove the operator wrapper surface exposes the enhancement flag (no install)
    for step, script in (("wrapper-help-phase2", "phase2_step2_normalize_plan.sh"),
                         ("wrapper-help-phase3", "phase3_retrieve_evidence.sh"),
                         ("wrapper-help-phase4", "phase4_write_wiki.sh")):
        r.help_capture(step, script)

    # 1. synthetic repo + Phase 1 substrate (non-live)
    synth_repo(repo)
    r.cli("phase1-decompose", "decompose", "--repo", repo, "--out", bundle,
          "--embeddings", "off")
    r.cli("phase1-build-retrieval", "build-retrieval", "--in", bundle,
          "--vectors", "off")

    # 2. author raw plan + REAL Phase 2 normalize with the enhancement gate
    raw_path = os.path.join(bundle, "plans", "phase2-fixture-response.md")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(build_raw_plan())
    r.cli("phase2-normalize-enhancement", "normalize-plan", "--bundle", bundle,
          "--raw-response", raw_path, "--provider", "fixture",
          "--coverage-mode", "enhancement")

    # 3. REAL Phase 3 evidenced-coverage gate
    r.cli("phase3-retrieve-enhancement", "retrieve-evidence", "--bundle", bundle,
          "--coverage-mode", "enhancement")

    # record the run's provenance so Phase 4's force/provenance gate is satisfied
    # (a non-forced Phase 3 invocation). Append so any decompose-written lines stay.
    bundle_manifest = os.path.join(bundle, "command-manifest.tsv")
    existing = ""
    if os.path.isfile(bundle_manifest):
        with open(bundle_manifest) as f:
            existing = f.read()
    if "retrieve-evidence" not in existing:
        with open(bundle_manifest, "a") as f:
            f.write("phase3\tpython -m wiki_generator retrieve-evidence --bundle "
                    f"{bundle} --coverage-mode enhancement\t0\n")

    # 4. Phase 4 — REAL gemini-gem path. First prepare prompts (runs ALL pre-provider
    #    gates with NO provider call), then synthesize deterministic responses, then
    #    validate+assemble.
    r.cli("phase4-prepare-prompts", "write-wiki", "--bundle", bundle,
          "--provider", "gemini-gem", "--coverage-mode", "enhancement",
          "--prepare-prompts-only")
    gem_summary = write_gem_fixtures(bundle, gem_dir)
    r.cli("phase4-validate-assemble", "write-wiki", "--bundle", bundle,
          "--provider", "gemini-gem", "--coverage-mode", "enhancement",
          "--responses-in", gem_dir, "--validate-and-assemble")

    # 5. determinism — rerun Phase 4 to the SAME wiki dir over identical inputs and
    #    byte-compare the deterministic artifacts (coverage matrix, section metadata,
    #    nested index). Same out dir keeps the embedded relative paths comparable.
    wiki = os.path.join(bundle, "wiki")
    det_files = ("metadata/generated-coverage.json",
                 "metadata/generated-sections.jsonl", "index.md")
    before = {rel: open(os.path.join(wiki, rel)).read() for rel in det_files}
    r.cli("phase4-rerun-determinism", "write-wiki", "--bundle", bundle,
          "--provider", "gemini-gem", "--coverage-mode", "enhancement",
          "--responses-in", gem_dir, "--validate-and-assemble")
    after = {rel: open(os.path.join(wiki, rel)).read() for rel in det_files}
    diffs = [rel for rel in det_files if before[rel] != after[rel]]
    determinism_ok = not diffs
    rerun_note = (f"byte-identical on rerun over identical inputs ({', '.join(det_files)})"
                  if determinism_ok else
                  f"NON-DETERMINISTIC: {diffs} differed across reruns")

    # 5b. negative probe (non-destructive): enhancement-mode Phase 4 must REFUSE
    #     pre-provider when the upstream planned-coverage gate is absent. Move the
    #     gate aside, expect exit 3 (GateFailure) into a throwaway out dir, restore.
    neg_out = os.path.join(bundle, "_neg_probe_wiki")
    gate_path = os.path.join(bundle, "plans", "coverage-gate.json")
    gate_bak = gate_path + ".bak"
    os.rename(gate_path, gate_bak)
    try:
        r.cli("phase4-negative-missing-planned-gate", "write-wiki", "--bundle",
              bundle, "--provider", "gemini-gem", "--coverage-mode", "enhancement",
              "--out", neg_out, "--prepare-prompts-only", expect=3)
        negative_ok = True
    finally:
        os.rename(gate_bak, gate_path)
        shutil.rmtree(neg_out, ignore_errors=True)

    # 6. benchmark-only comparison + result doc
    bench = benchmark_compare(run_dir, bundle, args.benchmark)
    result_path, verdict = write_result(
        run_dir, bundle, determinism_ok=determinism_ok, rerun_note=rerun_note,
        bench=bench, gem_summary=gem_summary, negative_ok=negative_ok)

    print(f"[e2e] result: {result_path}")
    print(f"[e2e] VERDICT: {'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
