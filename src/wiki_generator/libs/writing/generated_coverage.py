"""Phase 4 DeepWiki coverage enhancement: upstream gates + generated coverage.

This module owns the opt-in ``--coverage-mode enhancement`` machinery for Phase 4.
It does three deterministic, read-only things:

1. **Upstream enhancement gates (pre-provider).** ``read_enhancement_gates`` reads
   the Phase 2 planned-coverage gate (``plans/coverage-gate.json``) and the Phase 3
   evidenced-coverage gate (``evidence/evidenced-coverage.json`` plus the
   ``required_topic_evidence_sufficient`` retrieval-validation contract check). If
   either is absent, baseline/report-only, or failed, enhancement-mode Phase 4 must
   fail BEFORE any provider call (a :class:`GateFailure`, exit 3). Phase 4 never
   re-runs Phase 2/3, repairs plans, retrieves evidence, or synthesizes evidence —
   it only consumes the upstream artifacts.

2. **Topic obligations.** ``build_topic_obligations`` turns the evidenced-coverage
   matrix into, per section, the exact required topics Phase 4 must generate and the
   precise supporting ``evidence_id`` values (the Phase 3 mapped IDs) for each. These
   ride in the WritingPacket so the writer is told which evidence backs each topic.

3. **Generated coverage validation (post-provider).** ``evaluate_generated_coverage``
   checks the writer's structured ``covered_topics[]`` declaration against the
   generated markdown deterministically: every evidenced *sufficient* required topic
   must have a ``covered`` row whose ``evidence_ids`` are within the topic's mapped
   IDs, resolve through the citation manifest, and actually appear as inline
   citations in non-empty markdown containing the topic text or declared anchor. A
   missing/placeholder/out-of-scope/uncited topic is a writing-validation failure
   (exit 5). This never mutates ``covered_topics[]``, never adds filler, and never
   downgrades a required topic.
"""
from __future__ import annotations

import os
import re

from .. import markdown as md
from .. import util
from . import citations as cit
from .schema import GENERATED_COVERAGE_SCHEMA_VERSION

# Upstream enhancement artifacts Phase 4 consumes (never produces).
PLANNED_GATE_REL = "plans/coverage-gate.json"
EVIDENCED_COVERAGE_REL = "evidence/evidenced-coverage.json"
# The named Phase 3 retrieval-validation contract check that proves evidenced
# coverage was enforced and passed (owned by the evidence phase).
EVIDENCED_CONTRACT_CHECK = "required_topic_evidence_sufficient"

# The named Phase 4 writing-validation check this module contributes.
GENERATED_COVERAGE_CHECK = "generated_required_topics_covered"

# Per-topic generated status.
GEN_COVERED = "covered"          # generated with valid mapped citations
GEN_OMITTED = "omitted"          # no covered_topics row / not declared covered
GEN_INVALID = "invalid"          # declared covered but citations/anchor invalid

# Evidenced status that obliges Phase 4 to generate the topic. Only ``sufficient``
# required topics are obligations; ``weak``/``missing`` would have blocked Phase 3
# in enhancement mode, and ``not_applicable`` (provenance) carries no obligation.
_OBLIGATION_STATUS = "sufficient"


# --- upstream enhancement gates -----------------------------------------------
def _maybe_json(path: str):
    """Read a JSON file, or ``None`` if missing/unreadable (a deterministic miss
    that the gate reports as an absent upstream artifact, never a crash)."""
    if not os.path.isfile(path):
        return None
    try:
        return util.read_json(path)
    except (OSError, ValueError):
        return None


def _planned_gate_failures(bundle_root: str) -> list[str]:
    """Verify the Phase 2 planned-coverage gate artifact is present, enhancement-
    enforced, and passing. Returns a list of failure strings (empty == satisfied)."""
    path = os.path.join(bundle_root, PLANNED_GATE_REL)
    gate = _maybe_json(path)
    if gate is None:
        return [f"missing Phase 2 planned-coverage gate `{PLANNED_GATE_REL}`; run "
                "`normalize-plan --coverage-mode enhancement` and fix any missing "
                "mandatory topic families before Phase 4"]
    report = gate.get("report") or {}
    # baseline/report-only or non-enhancement gate is not an enforced pass.
    if report.get("mode") != "enhancement" or not report.get("enforced"):
        return [f"`{PLANNED_GATE_REL}` is not an enforced enhancement gate "
                f"(mode={report.get('mode')!r}, enforced={report.get('enforced')!r}); "
                "re-run `normalize-plan --coverage-mode enhancement`"]
    if not gate.get("passed") or report.get("status") != "pass":
        return [f"Phase 2 planned-coverage gate failed (status="
                f"{report.get('status')!r}, missing="
                f"{report.get('missing_mandatory')}); fix the Phase 2 plan upstream "
                "— Phase 4 does not repair plans"]
    return []


def _evidenced_gate_failures(bundle_root: str, retrieval_validation: dict) -> list[str]:
    """Verify the Phase 3 evidenced-coverage gate is present, enhancement-enforced,
    and passing, and that the retrieval-validation contract check confirms it."""
    failures: list[str] = []
    path = os.path.join(bundle_root, EVIDENCED_COVERAGE_REL)
    matrix = _maybe_json(path)
    if matrix is None:
        failures.append(
            f"missing Phase 3 evidenced-coverage gate `{EVIDENCED_COVERAGE_REL}`; run "
            "`retrieve-evidence --coverage-mode enhancement` before Phase 4")
    else:
        if matrix.get("coverage_mode") != "enhancement" or not matrix.get("enforced"):
            failures.append(
                f"`{EVIDENCED_COVERAGE_REL}` is report-only (coverage_mode="
                f"{matrix.get('coverage_mode')!r}, enforced={matrix.get('enforced')!r}); "
                "re-run `retrieve-evidence --coverage-mode enhancement`")
        elif matrix.get("status") != "pass":
            failures.append(
                f"Phase 3 evidenced-coverage gate failed (status="
                f"{matrix.get('status')!r}, failure_category="
                f"{matrix.get('failure_category')!r}); fix Phase 2/3 upstream — Phase "
                "4 does not retrieve or synthesize evidence")

    # The retrieval-validation contract check must independently confirm it.
    by_name = {c.get("name"): c
               for c in (retrieval_validation.get("contract_checks") or [])}
    check = by_name.get(EVIDENCED_CONTRACT_CHECK)
    if check is None:
        failures.append(
            f"retrieval-validation is missing the `{EVIDENCED_CONTRACT_CHECK}` "
            "contract check; Phase 3 was not run in enhancement mode")
    elif check.get("status") != "pass":
        failures.append(
            f"retrieval-validation contract check `{EVIDENCED_CONTRACT_CHECK}` is "
            f"{check.get('status')!r}; fix the Phase 3 evidenced-coverage failure "
            "upstream")
    return failures


def read_enhancement_gates(bundle_root: str, retrieval_validation: dict):
    """Read the Phase 2 + Phase 3 enhancement gates from the bundle.

    Returns ``(failures, evidenced_matrix)``. ``failures`` is the (possibly empty)
    list of pre-provider gate-failure strings; ``evidenced_matrix`` is the parsed
    ``evidenced-coverage.json`` (or ``None`` when absent) for downstream obligation
    building. Pure file reads — no provider call, no phase re-run."""
    failures = _planned_gate_failures(bundle_root)
    failures += _evidenced_gate_failures(bundle_root, retrieval_validation)
    evidenced = _maybe_json(os.path.join(bundle_root, EVIDENCED_COVERAGE_REL))
    return failures, evidenced


# --- topic obligations --------------------------------------------------------
def build_topic_obligations(evidenced_matrix: dict | None) -> dict:
    """``section_id -> [obligation]`` from the evidenced-coverage matrix.

    An obligation is one *required* topic Phase 4 must generate, carrying the exact
    Phase 3 mapped ``evidence_id`` values that support it. Only ``sufficient``
    required topics are obligations (the writer must cover them); weak/missing would
    have blocked Phase 3, and ``not_applicable`` provenance topics carry none."""
    out: dict = {}
    if not isinstance(evidenced_matrix, dict):
        return out
    for sec in evidenced_matrix.get("sections") or []:
        sid = sec.get("section_id")
        rows: list = []
        for t in sec.get("topics") or []:
            if not t.get("required"):
                continue
            rows.append({
                "topic": t.get("topic"),
                "evidenced_status": t.get("status"),
                "mapped_evidence_ids": list(t.get("mapped_evidence_ids") or []),
                "min_items": t.get("min_items") or 1,
                "source_categories": list(t.get("source_categories") or []),
                "is_obligation": t.get("status") == _OBLIGATION_STATUS,
            })
        if sid is not None:
            out[sid] = rows
    return out


# --- covered_topics declaration parsing ---------------------------------------
def normalize_covered_topics(value) -> list:
    """Defensively normalize a draft's ``covered_topics`` value into a list of
    ``{topic, status, evidence_ids, markdown_anchor}`` rows (non-dict/garbage
    entries are dropped). The writer authors this; deterministic code never edits
    its semantic content, only reads it."""
    rows: list = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if not isinstance(item, dict):
            continue
        topic = item.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            continue
        eids = item.get("evidence_ids")
        eids = [e for e in eids if isinstance(e, str)] if isinstance(eids, list) else []
        anchor = item.get("markdown_anchor")
        rows.append({
            "topic": topic.strip(),
            "status": item.get("status") if isinstance(item.get("status"), str)
            else None,
            "evidence_ids": eids,
            "markdown_anchor": anchor.strip() if isinstance(anchor, str) else None,
        })
    return rows


# --- markdown presence helpers ------------------------------------------------
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
_HEADING_LEVEL_RE = re.compile(r"^\s{0,3}(#{1,6})\s")


def heading_slug(line: str) -> str | None:
    """GitHub-style slug of a markdown heading line, or ``None`` if not a heading.

    Lower-cased, punctuation (except hyphens) stripped, whitespace runs collapsed to
    single hyphens — the same anchor a ``covered_topics`` row declares."""
    m = _HEADING_RE.match(line)
    if not m:
        return None
    text = m.group(1).strip().casefold()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text or None


def _heading_level(line: str) -> int | None:
    m = _HEADING_LEVEL_RE.match(line)
    return len(m.group(1)) if m else None


def _heading_block(lines: list, i: int, level: int) -> str:
    """Lines from heading at index ``i`` until the next same-or-higher heading."""
    block = [lines[i]]
    for nxt in lines[i + 1:]:
        nl = _heading_level(nxt)
        if nl is not None and nl <= level:
            break
        block.append(nxt)
    return "\n".join(block)


def topic_block(markdown: str, topic: str, anchor: str | None) -> str | None:
    """The local markdown block that covers ``topic``, or ``None`` when the topic is
    absent. Located by (1) a heading whose slug equals the declared ``anchor``, then
    (2) a heading whose text contains the topic, then (3) the paragraph containing the
    topic text. The block is the unit citations must appear in, so a topic cannot be
    "covered" by a sibling topic's citations elsewhere in the same section."""
    lines = (markdown or "").splitlines()
    if anchor:
        for i, line in enumerate(lines):
            if heading_slug(line) == anchor:
                return _heading_block(lines, i, _heading_level(line))
    tl = (topic or "").casefold()
    if not tl:
        return None
    for i, line in enumerate(lines):
        lvl = _heading_level(line)
        if lvl is not None and tl in line.casefold():
            return _heading_block(lines, i, lvl)
    for i, line in enumerate(lines):
        if _heading_level(line) is None and tl in line.casefold():
            start = i
            while start > 0 and lines[start - 1].strip():
                start -= 1
            end = i
            while end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
            return "\n".join(lines[start:end + 1])
    return None


# --- per-section generated coverage evaluation --------------------------------
def evaluate_section_coverage(*, obligations, covered_topics, markdown,
                              evidence_index, manifest_ids):
    """Deterministically validate one section's generated coverage.

    ``obligations``     this section's required-topic obligations (mapped IDs).
    ``covered_topics``  normalized ``covered_topics[]`` rows from the draft.
    ``markdown``        the generated section markdown.
    ``evidence_index``  ``evidence_id -> EvidenceItem`` (bundle citeable evidence).
    ``manifest_ids``    the set of ``evidence_id``s present in the citation manifest.

    Returns ``{rows, failures}``. ``rows`` is one record per obligation (for the
    coverage matrix); ``failures`` is the list of human-readable violations. The
    only evidence a topic may claim is a real mapped ``evidence_id`` that resolves
    through the manifest and is cited in the markdown."""
    cited = set(cit.distinct_citations(markdown))
    by_topic = {r["topic"].casefold(): r for r in covered_topics}
    rows: list = []
    failures: list = []

    for ob in obligations:
        topic = ob.get("topic")
        # Only sufficient required topics are generation obligations.
        if not ob.get("is_obligation"):
            rows.append({
                "topic": topic, "evidenced_status": ob.get("evidenced_status"),
                "generated_status": GEN_OMITTED,
                "mapped_evidence_ids": list(ob.get("mapped_evidence_ids") or []),
                "evidence_ids": [], "markdown_anchor": None, "cited": False,
                "problems": [],
            })
            continue

        mapped = list(ob.get("mapped_evidence_ids") or [])
        mapped_set = set(mapped)
        decl = by_topic.get((topic or "").casefold())
        problems: list = []
        status = GEN_COVERED
        decl_ids: list = []
        anchor = None

        if decl is None:
            status = GEN_OMITTED
            problems.append(
                f"required topic {topic!r} has no covered_topics declaration "
                "(omitted from generated output)")
        else:
            anchor = decl.get("markdown_anchor")
            decl_ids = list(decl.get("evidence_ids") or [])
            if decl.get("status") != GEN_COVERED:
                status = GEN_INVALID
                problems.append(
                    f"required topic {topic!r} declared status "
                    f"{decl.get('status')!r}, not {GEN_COVERED!r}")
            if not decl_ids:
                status = GEN_INVALID
                problems.append(
                    f"required topic {topic!r} declares no evidence_ids")
            for eid in decl_ids:
                if eid not in mapped_set:
                    status = GEN_INVALID
                    problems.append(
                        f"topic {topic!r} cites {eid!r} outside its Phase 3 mapped "
                        f"evidence IDs {sorted(mapped_set)}")
                    continue
                if eid not in evidence_index or eid not in manifest_ids:
                    status = GEN_INVALID
                    problems.append(
                        f"topic {topic!r} cites {eid!r} that does not resolve through "
                        "the citation manifest")
                    continue
                if eid not in cited:
                    status = GEN_INVALID
                    problems.append(
                        f"topic {topic!r} declares {eid!r} but it is not cited in the "
                        "generated markdown")
            # the topic must be present in non-empty generated content AND that local
            # block must itself carry a citation to one of the topic's declared
            # evidence IDs (a sibling topic's citation elsewhere does not count).
            if status == GEN_COVERED:
                block = topic_block(markdown, topic, anchor)
                if block is None:
                    status = GEN_INVALID
                    problems.append(
                        f"topic {topic!r} not found in generated markdown (no matching "
                        f"text or heading anchor {anchor!r})")
                else:
                    block_cited = set(cit.distinct_citations(block))
                    if not any(e in block_cited for e in decl_ids):
                        status = GEN_INVALID
                        problems.append(
                            f"topic {topic!r} content has no inline citation to its "
                            "declared evidence IDs (covered without local grounding)")

        cited_ok = bool(decl_ids) and all(e in cited for e in decl_ids)
        rows.append({
            "topic": topic, "evidenced_status": ob.get("evidenced_status"),
            "generated_status": status, "mapped_evidence_ids": mapped,
            "evidence_ids": decl_ids, "markdown_anchor": anchor,
            "cited": cited_ok, "problems": problems,
        })
        failures += problems

    return {"rows": rows, "failures": failures}


# --- whole-document generated coverage matrix ---------------------------------
def evaluate_generated_coverage(bundle, generated: list, manifest: dict) -> dict:
    """Build the whole-document generated-coverage matrix + verdict.

    Reads each section's generated markdown from disk (the assembled section file)
    and validates it against the section's obligations. Produces the
    ``generated-coverage.json`` body plus a ``failures`` list. Deterministic and
    timestamp-free."""
    manifest_ids = {c.get("evidence_id") for c in manifest.get("citations", [])}
    obligations = bundle.topic_obligations or {}
    by_sid = {g["section_id"]: g for g in generated}

    counts = {"covered": 0, "omitted": 0, "invalid": 0}
    required_topics = 0
    section_rows: list = []
    all_failures: list = []

    for sid in bundle.section_order:
        g = by_sid.get(sid)
        plan = bundle.section_plans.get(sid) or {}
        sec_obligations = obligations.get(sid) or []
        markdown = ""
        if g is not None:
            p = os.path.join(bundle.root, g.get("markdown_path", ""))
            if os.path.isfile(p):
                markdown = util.read_text(p) or ""
        covered_topics = (g or {}).get("covered_topics") or []

        result = evaluate_section_coverage(
            obligations=sec_obligations, covered_topics=covered_topics,
            markdown=markdown, evidence_index=bundle.evidence_index,
            manifest_ids=manifest_ids)
        for row in result["rows"]:
            if not any(o.get("is_obligation") and o.get("topic") == row["topic"]
                       for o in sec_obligations):
                continue
            required_topics += 1
            counts[row["generated_status"]] = counts.get(
                row["generated_status"], 0) + 1
        all_failures += [f"{sid}: {f}" for f in result["failures"]]

        section_rows.append({
            "section_id": sid,
            "parent_section_id": plan.get("parent_section_id"),
            "coverage_labels": list(plan.get("coverage_labels") or []),
            "required_topics": list(plan.get("required_topics") or []),
            "topics": result["rows"],
        })

    status = "fail" if all_failures else "pass"
    matrix = {
        "schema_version": GENERATED_COVERAGE_SCHEMA_VERSION,
        "coverage_mode": bundle.coverage_mode,
        "status": status,
        "bundle_root": bundle.root,
        "counts": {
            "sections": len(section_rows),
            "required_topics": required_topics,
            "covered": counts["covered"],
            "omitted": counts["omitted"],
            "invalid": counts["invalid"],
        },
        "sections": section_rows,
        "failures": all_failures,
    }
    return matrix


def render_generated_coverage_report(matrix: dict) -> str:
    """Human-readable generated-coverage report (the on-disk ``*.md`` artifact)."""
    c = matrix["counts"]
    lines: list[str] = []
    lines += md.heading(1, "Phase 4 — Generated Coverage Report")
    lines.append(f"**Mode:** `{matrix['coverage_mode']}`")
    lines.append(f"**Status:** {matrix['status'].upper()}")
    lines.append("")
    lines.append("> Generated coverage proves every planned/evidenced **sufficient** "
                 "required topic was actually written, with citations to the exact "
                 "Phase 3 mapped evidence IDs that survive through the citation "
                 "manifest and appear inline in non-empty markdown. Broad parent "
                 "pages never count as coverage for a child required topic.")
    lines.append("")
    lines += md.heading(2, "Summary")
    lines.append(f"- Sections: {c['sections']}")
    lines.append(f"- Required topics (obligations): {c['required_topics']}")
    lines.append(f"- covered: {c['covered']}  omitted: {c['omitted']}  "
                 f"invalid: {c['invalid']}")
    lines.append("")
    lines += md.heading(2, "Required-topic generated coverage by section")
    rows = []
    for sec in matrix["sections"]:
        for t in sec["topics"]:
            rows.append([sec["section_id"], sec.get("parent_section_id") or "—",
                         t["topic"], t.get("evidenced_status") or "—",
                         t["generated_status"],
                         ", ".join(t.get("evidence_ids") or []) or "—",
                         t.get("markdown_anchor") or "—"])
    lines += md.md_table(
        ["section", "parent", "topic", "evidenced", "generated", "evidence_ids",
         "anchor"], rows)
    if matrix["failures"]:
        lines += md.heading(2, "Failures (remediation)")
        for f in matrix["failures"]:
            lines.append(f"- {f}")
        lines.append("")
        lines.append("Generated coverage failures are writing-validation failures "
                     "(exit 5). Fix the generated section so each required topic is "
                     "covered with valid mapped citations; do not add filler, "
                     "synthetic evidence, or downgrade required topics.")
        lines.append("")
    else:
        lines.append("All evidenced sufficient required topics were generated with "
                     "valid mapped citations.")
        lines.append("")
    return "\n".join(lines) + "\n"


# --- hierarchy helpers --------------------------------------------------------
def child_section_ids(bundle, sid: str) -> list:
    """Section ids (in document order) whose ``parent_section_id`` is ``sid``."""
    out: list = []
    for other in bundle.section_order:
        plan = bundle.section_plans.get(other) or {}
        if other != sid and plan.get("parent_section_id") == sid:
            out.append(other)
    return out


def has_hierarchy(bundle) -> bool:
    """True when any planned section declares a ``parent_section_id`` resolving to
    another planned section (so the index should render nested contents)."""
    order = set(bundle.section_order)
    for sid in bundle.section_order:
        parent = (bundle.section_plans.get(sid) or {}).get("parent_section_id")
        if parent and parent in order and parent != sid:
            return True
    return False
