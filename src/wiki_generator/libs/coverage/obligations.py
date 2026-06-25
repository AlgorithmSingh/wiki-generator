"""Deterministic Phase 2 topic-obligation completeness gate.

The planned-coverage gate in :mod:`.validate` answers *"does the plan name every
mandatory topic family?"*. This module answers the next, finer question, also
purely from the **normalized plan** and **before Phase 3 retrieval runs**:

    For every normalized required topic in a normal source-evidence section, does
    the plan already carry a complete, exact, citeable evidence obligation that
    Phase 3 could actually satisfy?

It exists because the live RAGFlow enhancement run reached Phase 3 with 67 of 112
required topics having **no matching** ``topic_evidence_requirements[]`` row (the
planner authored ``coverage_requirements[]`` that normalization merges into
``required_topics[]``, but only authored topic-evidence rows for the originally
authored ``required_topics[]``), plus other topics mapped only to broad recall.
Those defects are deterministic plan-shape defects: they are visible in the plan
itself, with no evidence retrieved. Catching them here fails the pipeline at the
Phase 2 → Phase 3 boundary with an actionable diagnostic instead of letting it run
23 packets / 707 evidence items and fail closed downstream.

This is **upstream prevention by loud failure**, not a healing loop. The evaluator
is LLM-free, network-free, read-only: it never edits the plan, never synthesizes a
topic-evidence row, never downgrades a required topic to optional, and never
guesses a source field. A defect is reported with remediation pointing back at the
LLM-authored Phase 2 plan / prompt / schema.

The lane taxonomy and source-field grammar below are the *single source of truth*
shared with the Phase 3 evidenced-coverage consumer
(:mod:`wiki_generator.libs.evidence.evidenced_coverage`), so the producer-side
obligation checker and the consumer-side evidence gate cannot drift on what counts
as an exact citeable lane or how ``retrieval_needs.files[0]`` is parsed.

``enhancement`` mode is a fail-closed gate (a defect blocks before Phase 3,
``status == "fail"``, exit ``3``, ``bad_underspecified_normalized_plan``).
``baseline`` mode reports the same matrix but never gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_docs import is_provenance_section
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    MODE_BASELINE,
    MODE_ENHANCEMENT,
    _MODES,
)

TOPIC_OBLIGATIONS_SCHEMA_VERSION = "phase2-topic-obligations-v1"

# Same blocking failure category Phase 3 evidenced coverage uses: this gate catches
# the same class of underspecified-plan defect earlier, at the Phase 2 boundary.
FAILURE_CATEGORY = "bad_underspecified_normalized_plan"

# ``retrieval_needs.<field>`` name -> the exact (citeable) evidence lane it feeds.
# These are the ONLY lanes whose source fields can ground a required topic. Mirrors
# ``normalize._TER_ACCEPTABLE_LANES`` and the Phase 3 exact-lane mapping.
EXACT_FIELD_LANES = {
    "files": "file_anchor", "symbols": "symbol_anchor", "contracts": "contract",
    "tests": "test", "query_packs": "query_pack",
}
# Broad-recall ``retrieval_needs.<field>`` names -> the broad lane(s) they feed.
# Valid retrieval directives, but supporting context only: they can never make a
# required topic sufficient, so a topic grounded ONLY on them is a plan defect.
BROAD_FIELD_LANES = {
    "graph_nodes": ("graph_neighbors",), "search_hints": ("bm25", "vector"),
}
# The exact lane names a topic's ``acceptable_lanes[]`` must include at least one of.
EXACT_LANES = frozenset(EXACT_FIELD_LANES.values())

# Per-topic obligation statuses.
STATUS_OK = "ok"                       # complete exact citeable obligation
STATUS_INCOMPLETE = "incomplete"       # ≥1 blocking defect (enhancement: blocking)
STATUS_OPTIONAL = "optional"           # a non-required TER row (reported, never blocks)
STATUS_NOT_APPLICABLE = "not_applicable"  # controlled provenance/meta section

# Defect codes (one per distinct, actionable plan-shape defect).
CODE_MISSING_TER = "required_topic_missing_evidence_requirement"
CODE_NOT_REQUIRED = "topic_evidence_requirement_not_required"
CODE_EMPTY_SOURCE_FIELDS = "topic_evidence_requirement_empty_source_fields"
CODE_INVALID_SOURCE_FIELD = "topic_evidence_requirement_invalid_source_field"
CODE_BROAD_ONLY_SOURCE_FIELDS = "topic_evidence_requirement_broad_only_source_fields"
CODE_BROAD_ONLY_ACCEPTABLE_LANES = "topic_evidence_requirement_broad_only_acceptable_lanes"


# --- shared source-field grammar / topic enumeration --------------------------
def parse_source_field(source_field: str):
    """``'retrieval_needs.files[2]'`` -> ``('files', 2)``; index ``-1`` when absent.

    The single parser both this gate and Phase 3 evidenced coverage use, so the
    producer obligation check and the consumer evidence map read source fields
    identically."""
    name = source_field or ""
    idx = -1
    if name.endswith("]") and "[" in name:
        head, _, tail = name.partition("[")
        name = head
        num = tail[:-1]
        idx = int(num) if num.isdigit() else -1
    if name.startswith("retrieval_needs."):
        name = name[len("retrieval_needs."):]
    return name, idx


def field_index_valid(section: dict, field_name: str, idx: int) -> bool:
    """True when ``retrieval_needs.<field_name>[idx]`` references a real normalized
    entry on ``section`` (the deterministic 'does this source field point at
    something that exists?' check)."""
    if idx < 0:
        return False
    items = (section.get("retrieval_needs") or {}).get(field_name)
    return isinstance(items, list) and 0 <= idx < len(items)


def enumerate_section_topics(section: dict):
    """The ``(topic, ter, required)`` triples to evaluate for one section.

    Driven by the canonical ``required_topics[]`` (the merged
    ``coverage_requirements[]`` + ``required_topics[]`` the planned-coverage gate
    and Phase 3 both read), unioned with any extra ``topic_evidence_requirements[]``
    entry. A ``required_topics[]`` entry is always ``required`` (it is a
    Phase-3-blocking obligation); an extra TER carries its own ``required`` flag.

    Shared verbatim with Phase 3 so the set of Phase-3-blocking topics this gate
    validates is exactly the set Phase 3 will later try to evidence."""
    ters = section.get("topic_evidence_requirements") or []
    ter_by_topic: dict = {}
    ter_by_topic_cf: dict = {}
    for t in ters:
        topic = t.get("topic")
        if isinstance(topic, str):
            ter_by_topic.setdefault(topic, t)
            ter_by_topic_cf.setdefault(topic.casefold(), t)

    def match(topic: str):
        return ter_by_topic.get(topic) or ter_by_topic_cf.get(topic.casefold())

    triples: list = []
    seen: set = set()
    for topic in section.get("required_topics") or []:
        if not isinstance(topic, str) or topic in seen:
            continue
        seen.add(topic)
        triples.append((topic, match(topic), True))
    for t in ters:
        topic = t.get("topic")
        if isinstance(topic, str) and topic not in seen:
            seen.add(topic)
            triples.append((topic, t, bool(t.get("required", True))))
    return triples


# --- result model -------------------------------------------------------------
@dataclass
class TopicObligation:
    """One required topic's evidence-obligation completeness verdict."""

    topic: str
    required: bool
    status: str
    defects: list = field(default_factory=list)        # defect-code strings
    source_fields: list = field(default_factory=list)
    source_field_results: list = field(default_factory=list)
    acceptable_lanes: list = field(default_factory=list)
    remediation: str = ""

    @property
    def blocking(self) -> bool:
        return self.required and self.status == STATUS_INCOMPLETE

    def to_dict(self) -> dict:
        return {
            "topic": self.topic, "required": self.required, "status": self.status,
            "defects": list(self.defects), "source_fields": list(self.source_fields),
            "source_field_results": list(self.source_field_results),
            "acceptable_lanes": list(self.acceptable_lanes),
            "remediation": self.remediation,
        }


@dataclass
class SectionObligations:
    section_id: str
    section_role: str
    status: str                                          # pass | fail | not_applicable
    required_topic_count: int
    topics: list = field(default_factory=list)           # TopicObligation

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id, "section_role": self.section_role,
            "status": self.status, "required_topic_count": self.required_topic_count,
            "topics": [t.to_dict() for t in self.topics],
        }


@dataclass
class ObligationReport:
    """A whole-plan topic-obligation completeness verdict."""

    schema_version: str
    mode: str
    status: str                                          # pass | fail
    enforced: bool
    failure_category: str | None
    section_count: int
    required_topic_count: int
    complete_count: int
    incomplete_count: int
    not_applicable_count: int
    blocking_sections: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)      # actionable dicts
    sections: list = field(default_factory=list)         # SectionObligations

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version, "mode": self.mode,
            "status": self.status, "enforced": self.enforced,
            "failure_category": self.failure_category,
            "counts": {
                "sections": self.section_count,
                "required_topics": self.required_topic_count,
                "complete": self.complete_count,
                "incomplete": self.incomplete_count,
                "not_applicable": self.not_applicable_count,
            },
            "blocking_sections": list(self.blocking_sections),
            "diagnostics": list(self.diagnostics),
            "sections": [s.to_dict() for s in self.sections],
        }


# --- per-source-field + per-topic evaluation ----------------------------------
def _classify_source_field(section: dict, source_field: str) -> dict:
    """Classify one ``source_fields[]`` entry against the normalized plan shape.

    ``valid`` means it references a real ``retrieval_needs.*`` entry; ``exact`` means
    that entry is a citeable exact lane. The two booleans drive every obligation
    defect: a topic needs at least one ``valid and exact`` source field."""
    field_name, idx = parse_source_field(source_field)
    if field_name in EXACT_FIELD_LANES:
        lane, kind = EXACT_FIELD_LANES[field_name], "exact"
        valid = field_index_valid(section, field_name, idx)
        exact = True
    elif field_name in BROAD_FIELD_LANES:
        lane, kind = BROAD_FIELD_LANES[field_name][0], "broad"
        valid = field_index_valid(section, field_name, idx)
        exact = False
    else:
        lane, kind = None, "unknown"
        valid = False
        exact = False
    return {
        "source_field": source_field, "field": field_name, "index": idx,
        "lane": lane, "kind": kind, "valid": valid, "exact": exact,
    }


def _remediation(topic: str, defects: list) -> str:
    """One actionable remediation line for the worst defect on a topic."""
    if CODE_MISSING_TER in defects:
        return (f"add a topic_evidence_requirements[] row for required topic "
                f"'{topic}' (required:true) whose source_fields[] point at the exact "
                f"retrieval_needs.* lanes that ground it. This required topic was "
                f"merged from coverage_requirements[]/required_topics[]; every merged "
                f"required topic needs its own exact evidence obligation. Fix the "
                f"Phase 2 plan/prompt upstream — do not defer to Phase 3.")
    if CODE_NOT_REQUIRED in defects:
        return (f"'{topic}' is a required topic but its topic_evidence_requirements[] "
                f"row is required:false; set required:true or drop the topic from "
                f"required_topics[] (do not silently downgrade a required obligation).")
    if CODE_EMPTY_SOURCE_FIELDS in defects:
        return (f"give '{topic}' non-empty source_fields[] pointing at exact "
                f"retrieval_needs.* lanes (files/symbols/contracts/tests/query_packs).")
    if CODE_INVALID_SOURCE_FIELD in defects:
        return (f"a source_field for '{topic}' references a retrieval_needs.* entry "
                f"that does not exist in the normalized plan; point it at a real "
                f"normalized lane index, or add that exact handle to evidence_needs.")
    if CODE_BROAD_ONLY_SOURCE_FIELDS in defects:
        return (f"'{topic}' is grounded only on broad recall "
                f"(search_hints/graph_nodes); add at least one exact source_field "
                f"(files/symbols/contracts/tests/query_packs) that resolves to "
                f"citeable evidence. Broad recall is never sufficient.")
    if CODE_BROAD_ONLY_ACCEPTABLE_LANES in defects:
        return (f"'{topic}' acceptable_lanes[] contains no exact citeable lane "
                f"(file_anchor/symbol_anchor/contract/test/query_pack); broad-only "
                f"lanes (bm25/vector/graph_neighbors) can never be sufficient.")
    return ""


def _eval_topic(section: dict, topic: str, ter: dict | None, required: bool,
                provenance: bool) -> TopicObligation:
    if provenance:
        return TopicObligation(topic=topic, required=required,
                               status=STATUS_NOT_APPLICABLE)

    if ter is None:
        # A required topic (only required_topics[] entries reach here without a TER)
        # with no matching topic_evidence_requirements[] row — the live failure.
        defects = [CODE_MISSING_TER]
        return TopicObligation(
            topic=topic, required=required, status=STATUS_INCOMPLETE,
            defects=defects, remediation=_remediation(topic, defects))

    source_fields = list(ter.get("source_fields") or [])
    sf_results = [_classify_source_field(section, sf) for sf in source_fields]
    acceptable = list(ter.get("acceptable_lanes") or sorted(EXACT_LANES))

    if not required:
        # An extra topic_evidence_requirements[] row not marked required and not in
        # required_topics[]: reported for transparency, never a blocking obligation.
        return TopicObligation(
            topic=topic, required=False, status=STATUS_OPTIONAL,
            source_fields=source_fields, source_field_results=sf_results,
            acceptable_lanes=acceptable)

    has_invalid = any(not r["valid"] for r in sf_results)
    has_valid_exact = any(r["valid"] and r["exact"] for r in sf_results)

    defects: list = []
    if required and not bool(ter.get("required", True)):
        defects.append(CODE_NOT_REQUIRED)
    if not source_fields:
        defects.append(CODE_EMPTY_SOURCE_FIELDS)
    else:
        if has_invalid:
            defects.append(CODE_INVALID_SOURCE_FIELD)
        if not has_valid_exact and not has_invalid:
            # source fields present and all reference real entries, but none is an
            # exact citeable lane -> grounded only on broad recall.
            defects.append(CODE_BROAD_ONLY_SOURCE_FIELDS)
        elif not has_valid_exact:
            # all source fields were invalid references; INVALID already flagged but
            # the topic still has no exact lane to ground it -> keep it blocking with
            # the broad-only-source-fields signal so the count of "ungroundable"
            # topics is explicit.
            defects.append(CODE_BROAD_ONLY_SOURCE_FIELDS)
    if not (set(acceptable) & EXACT_LANES):
        defects.append(CODE_BROAD_ONLY_ACCEPTABLE_LANES)

    if defects:
        status = STATUS_INCOMPLETE
    elif not required:
        status = STATUS_OPTIONAL
    else:
        status = STATUS_OK
    return TopicObligation(
        topic=topic, required=required, status=status, defects=defects,
        source_fields=source_fields, source_field_results=sf_results,
        acceptable_lanes=acceptable, remediation=_remediation(topic, defects))


def evaluate_topic_obligations(document_plan: dict | None, sections: list, *,
                               mode: str = MODE_ENHANCEMENT) -> ObligationReport:
    """Evaluate every normalized required topic's evidence obligation completeness.

    Deterministic and read-only. In ``enhancement`` mode a required topic in a
    normal source-evidence section with any blocking defect makes the section (and
    the run) fail before Phase 3; ``baseline`` mode reports the same matrix without
    gating.

    Raises ``ValueError`` for an unknown mode or a non-list ``sections`` (mirrors
    :func:`.validate.evaluate_plan_coverage`)."""
    if mode not in _MODES:
        raise ValueError(f"unknown coverage mode {mode!r}; expected one of {_MODES}")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list of normalized section-plan dicts")

    enforced = mode == MODE_ENHANCEMENT
    section_rows: list = []
    diagnostics: list = []
    blocking_sids: list = []
    complete = incomplete = not_applicable = required_total = 0

    for section in sections:
        sid = section.get("section_id") or "?"
        provenance = is_provenance_section(section)
        topic_rows: list = []
        section_blocking = False
        for topic, ter, required in enumerate_section_topics(section):
            row = _eval_topic(section, topic, ter, required, provenance)
            topic_rows.append(row)
            if row.status == STATUS_NOT_APPLICABLE:
                not_applicable += 1
            if required:
                required_total += 1
                if row.status == STATUS_OK:
                    complete += 1
                elif row.status == STATUS_INCOMPLETE:
                    incomplete += 1
            if row.blocking:
                section_blocking = True
                diagnostics.append({
                    "section_id": sid, "topic": topic,
                    "codes": list(row.defects), "remediation": row.remediation,
                })

        if provenance:
            section_status = STATUS_NOT_APPLICABLE
        elif enforced and section_blocking:
            section_status = "fail"
        else:
            section_status = "pass"
        if section_blocking and sid not in blocking_sids:
            blocking_sids.append(sid)

        section_rows.append(SectionObligations(
            section_id=sid, section_role=section.get("section_role") or "source",
            status=section_status,
            required_topic_count=sum(1 for r in topic_rows if r.required),
            topics=topic_rows))

    enforced_blocking = enforced and bool(blocking_sids)
    return ObligationReport(
        schema_version=TOPIC_OBLIGATIONS_SCHEMA_VERSION, mode=mode,
        status="fail" if enforced_blocking else "pass", enforced=enforced,
        failure_category=FAILURE_CATEGORY if enforced_blocking else None,
        section_count=len(section_rows), required_topic_count=required_total,
        complete_count=complete, incomplete_count=incomplete,
        not_applicable_count=not_applicable,
        blocking_sections=sorted(blocking_sids), diagnostics=diagnostics,
        sections=section_rows)


# --- the enhancement-mode gate ------------------------------------------------
@dataclass
class ObligationGate:
    """Verdict of the deterministic Phase 2 topic-obligation completeness gate.

    Like :class:`.validate.CoverageGate`, it never edits/synthesizes/heals the plan:
    it only reports the verdict and the exit code a caller should fail on
    (``0`` pass, ``3`` enhancement-mode fail)."""

    report: ObligationReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code,
                "report": self.report.to_dict()}

    def summary_lines(self) -> list:
        """Loud, actionable one-liners naming each blocking topic + remediation."""
        r = self.report
        lines = [
            f"topic-obligation gate: mode={r.mode} "
            f"({'enforced' if r.enforced else 'report-only'})",
            f"topic-obligation gate: {r.complete_count}/{r.required_topic_count} "
            f"required topic(s) carry a complete exact citeable evidence obligation "
            f"across {r.section_count} section(s)",
        ]
        if r.blocking_sections:
            lines.append("topic-obligation gate: sections with underspecified "
                         "required-topic obligations: " + ", ".join(r.blocking_sections))
            for d in r.diagnostics:
                lines.append(f"  - {d['section_id']} / {d['topic']!r} "
                             f"[{', '.join(d['codes'])}]: {d['remediation']}")
        verdict = "PASS" if self.passed else "FAIL"
        if not self.passed:
            lines.append(
                f"topic-obligation gate: {verdict} — {r.incomplete_count} required "
                "topic(s) cannot become sufficient citeable evidence. This "
                "deterministic gate does NOT add or repair topic_evidence_requirements; "
                "fix the LLM-authored Phase 2 plan (stronger prompt/schema, or a "
                "bounded audited re-prompt) and re-run before Phase 3 retrieval.")
        else:
            lines.append(f"topic-obligation gate: {verdict}")
        return lines


def gate_topic_obligations(document_plan: dict | None, sections: list, *,
                           mode: str = MODE_ENHANCEMENT) -> ObligationGate:
    """Evaluate ``sections`` and map the verdict to an :class:`ObligationGate`.

    In ``enhancement`` mode any blocking obligation defect yields
    ``passed == False`` / ``exit_code == 3``; ``baseline`` mode always passes
    (report-only). It never mutates the plan."""
    report = evaluate_topic_obligations(document_plan, sections, mode=mode)
    passed = report.status == "pass"
    return ObligationGate(
        report=report, passed=passed,
        exit_code=COVERAGE_GATE_PASS_EXIT if passed else COVERAGE_GATE_FAIL_EXIT)


def render_obligations_markdown(report: ObligationReport, *,
                                title: str = "Phase 2 Topic-Obligation Gate") -> str:
    """Render the human-readable ``topic-obligations-report.md`` artifact."""
    verdict = "PASS" if report.status == "pass" else "FAIL"
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Mode: **{report.mode}** "
        f"({'enforced' if report.enforced else 'report-only'})",
        f"- Status: **{verdict}**",
        f"- Required topics with a complete exact obligation: "
        f"{report.complete_count}/{report.required_topic_count}",
        f"- Sections: {report.section_count}",
        "",
        "> Each normalized required topic in a normal source-evidence section must",
        "> carry a topic_evidence_requirements[] row with required:true, non-empty",
        "> source_fields[] referencing real retrieval_needs.* entries, at least one",
        "> exact citeable lane (file_anchor/symbol_anchor/contract/test/query_pack),",
        "> and acceptable_lanes[] that include an exact lane. Broad recall",
        "> (bm25/vector/graph_neighbors/search_hints) is supporting context only.",
        "",
    ]
    if report.diagnostics:
        lines += ["## Underspecified required-topic obligations", ""]
        for d in report.diagnostics:
            lines.append(f"### `{d['section_id']}` — {d['topic']}")
            lines.append("")
            lines.append(f"- Defects: {', '.join(f'`{c}`' for c in d['codes'])}")
            lines.append(f"- Remediation: {d['remediation']}")
            lines.append("")
    else:
        lines += ["All required topics carry a complete exact citeable evidence "
                  "obligation.", ""]
    lines += ["## Per-section obligation matrix", "",
              "| section | role | status | required topics | complete |",
              "|---|---|---|---|---|"]
    for s in report.sections:
        complete_here = sum(1 for t in s.topics
                            if t.required and t.status == STATUS_OK)
        mark = {"pass": "✅", "fail": "❌",
                STATUS_NOT_APPLICABLE: "—"}.get(s.status, s.status)
        lines.append(f"| `{s.section_id}` | {s.section_role} | {mark} | "
                     f"{s.required_topic_count} | {complete_here} |")
    return "\n".join(lines).rstrip() + "\n"
