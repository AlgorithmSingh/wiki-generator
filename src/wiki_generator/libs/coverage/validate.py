"""Deterministic coverage validation against the planned-topic taxonomy.

Given a Phase 2 plan (the normalized ``document-plan.json`` + the list of
normalized section plans), :func:`evaluate_plan_coverage` decides, for every
mandatory :class:`~.taxonomy.TopicFamily`, whether any planned section covers it.

This is **LLM-free, network-free, and read-only**: it never calls a model, never
edits artifacts, and never changes Phase 3 retrieval semantics. It is the
non-live coverage-validation scaffolding for Milestone 2 — a compact 16-section
baseline fails it in ``enhancement`` mode, while an expanded/hierarchical plan
that plans for all mandatory families passes.

Modes:

- ``enhancement`` (default): a missing mandatory family is a **gate failure**
  (``status == "fail"``), with actionable diagnostics.
- ``baseline``: coverage is **reported but not enforced** (``status == "pass"``);
  gaps are still listed so the report stays informative. This mirrors how the old
  successful run is described as a grounded baseline rather than strict final
  sign-off.

The "planned" coverage dimension is implemented in full here. The "evidenced" and
"generated" dimensions (per-page EvidencePacket sufficiency and per-required-topic
generated-heading checks) are explicit next-integration steps and are intentionally
NOT asserted by this slice.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .taxonomy import MANDATORY_TOPIC_FAMILIES, TopicFamily

COVERAGE_VALIDATION_SCHEMA_VERSION = "phase2-coverage-validation-v1"

MODE_ENHANCEMENT = "enhancement"
MODE_BASELINE = "baseline"
# ``expanded`` is the opt-in DeepWiki-style hierarchical coverage mode. It is a
# strict superset of ``enhancement``: it enforces the same planned-coverage and
# topic-obligation gates AND the additional Phase B/C hierarchical catalog / page
# profile / content-block / relevant-source-map gates. ``enhancement`` keeps its
# exact historical behaviour (the existing enhancement gates only); ``baseline``
# reports without enforcing. Staging the expanded gates behind their own mode keeps
# every existing baseline AND enhancement run non-breaking (TDD OD-02 / OD-03).
MODE_EXPANDED = "expanded"
_MODES = (MODE_ENHANCEMENT, MODE_BASELINE, MODE_EXPANDED)
# The modes whose gates fail closed (vs. report-only). ``expanded`` enforces like
# ``enhancement``; both the planned-coverage and topic-obligation gates consult this.
_ENFORCING_MODES = frozenset({MODE_ENHANCEMENT, MODE_EXPANDED})


def is_enforcing(mode: str) -> bool:
    """True when ``mode`` fails closed (``enhancement`` or ``expanded``)."""
    return mode in _ENFORCING_MODES

# Exit codes for the deterministic planned coverage gate (shared by the standalone
# ``validate-coverage`` command and the integrated ``normalize-plan
# --coverage-mode enhancement`` boundary so both speak the same language).
COVERAGE_GATE_PASS_EXIT = 0     # all mandatory families planned (or report-only)
COVERAGE_GATE_INPUT_EXIT = 2    # no normalized plan to gate
COVERAGE_GATE_FAIL_EXIT = 3     # enhancement gate: a mandatory family is missing


# --- coverage result model ----------------------------------------------------
@dataclass
class FamilyCoverage:
    """Whether one topic family is covered by the plan, and the evidence trail."""

    key: str
    label: str
    mandatory: bool
    covered: bool
    covering_sections: list = field(default_factory=list)   # section_ids
    signals: list = field(default_factory=list)             # human-readable matches

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "mandatory": self.mandatory,
            "covered": self.covered,
            "covering_sections": list(self.covering_sections),
            "signals": list(self.signals),
        }


@dataclass
class CoverageReport:
    """A whole-plan coverage verdict against the mandatory topic taxonomy."""

    schema_version: str
    mode: str
    status: str                                   # "pass" | "fail"
    enforced: bool                                # True in enhancement mode
    section_count: int
    family_count: int
    covered_count: int
    missing_mandatory: list = field(default_factory=list)   # family keys
    families: list = field(default_factory=list)            # FamilyCoverage
    diagnostics: list = field(default_factory=list)         # actionable dicts

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "status": self.status,
            "enforced": self.enforced,
            "section_count": self.section_count,
            "family_count": self.family_count,
            "covered_count": self.covered_count,
            "missing_mandatory": list(self.missing_mandatory),
            "families": [f.to_dict() for f in self.families],
            "diagnostics": list(self.diagnostics),
        }


# --- signal matching ----------------------------------------------------------
def _norm(text) -> str:
    return text.casefold() if isinstance(text, str) else ""


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _section_search_text(section: dict) -> str:
    """The lower-cased planner text a keyword may match: title, required topics,
    key questions, goal, and purpose. (Retrieval handles/paths are intentionally
    excluded — coverage is judged from the *plan's stated intent*, not from which
    files happened to resolve.)"""
    parts: list[str] = [
        _norm(section.get("title")),
        _norm(section.get("goal")),
        _norm(section.get("purpose")),
        _norm(section.get("rationale")),
    ]
    for field_name in ("required_topics", "key_questions"):
        for item in _as_list(section.get(field_name)):
            parts.append(_norm(item))
    return "  ".join(p for p in parts if p)


def _section_labels(section: dict) -> set:
    """Explicit coverage labels declared on a section (forward-compatible plan
    field). Normalized to lower case; non-string entries are ignored."""
    return {_norm(x) for x in _as_list(section.get("coverage_labels")) if _norm(x)}


def _contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word / whole-phrase boundary match on already-lower-cased ``text``.

    A signal must not match inside a larger alphanumeric run: ``go`` must not
    match ``goal``, ``memory`` must not match ``memoryless`` mid-token. Internal
    spaces/punctuation in a phrase are matched literally."""
    if not phrase:
        return False
    pat = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pat, text) is not None


def _match_family(family: TopicFamily, sections: list):
    """Return ``(covering_section_ids, signals)`` for one family across all
    sections. A section covers the family if it declares one of the family's
    exact labels, or if any distinctive family keyword appears in its planner
    text."""
    covering: list[str] = []
    signals: list[str] = []
    labels = family.all_labels
    for section in sections:
        sid = section.get("section_id") or section.get("id") or "?"
        matched_here = False
        # 1) explicit coverage-label declaration (exact set match)
        for lbl in sorted(_section_labels(section) & labels):
            signals.append(f"label:{lbl}@{sid}")
            matched_here = True
        # 2) distinctive keyword / phrase in the section's planner text
        text = _section_search_text(section)
        for kw in family.keywords:
            if _contains_phrase(text, kw):
                signals.append(f"keyword:{kw}@{sid}")
                matched_here = True
        if matched_here:
            covering.append(sid)
    return covering, signals


def _diagnostic(family: TopicFamily) -> dict:
    """Actionable remediation for a missing mandatory family."""
    keyword_preview = ", ".join(family.keywords[:6]) or "(declare a coverage label)"
    return {
        "category": "missing_mandatory_topic_family",
        "family": family.key,
        "label": family.label,
        "message": (f"no planned section covers mandatory topic family "
                    f"'{family.key}' ({family.label})"),
        "remediation": (
            f"add a planned page or child section for {family.label}. "
            f"Declare coverage label '{family.key}' on that section, or include "
            f"distinctive topics such as: {keyword_preview}."),
        "expected_labels": sorted(family.all_labels),
        "expected_keywords": list(family.keywords),
    }


# --- public API ---------------------------------------------------------------
def evaluate_plan_coverage(document_plan: dict | None, sections: list, *,
                           mode: str = MODE_ENHANCEMENT,
                           families: tuple[TopicFamily, ...] = MANDATORY_TOPIC_FAMILIES
                           ) -> CoverageReport:
    """Validate a plan's planned sections against the mandatory topic taxonomy.

    ``document_plan`` the normalized ``document-plan.json`` dict (used only for the
                      section count fallback; may be ``None``).
    ``sections``      list of normalized section-plan dicts (each with at least a
                      ``section_id`` and the planner text fields).
    ``mode``          ``"enhancement"`` (enforce) or ``"baseline"`` (report-only).

    Raises ``ValueError`` for an unknown mode or a non-list ``sections``.
    """
    if mode not in _MODES:
        raise ValueError(f"unknown coverage mode {mode!r}; expected one of {_MODES}")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list of normalized section-plan dicts")

    family_covs: list[FamilyCoverage] = []
    missing: list[str] = []
    diagnostics: list[dict] = []
    for family in families:
        covering, signals = _match_family(family, sections)
        covered = bool(covering)
        family_covs.append(FamilyCoverage(
            key=family.key, label=family.label, mandatory=family.mandatory,
            covered=covered, covering_sections=covering, signals=signals))
        if family.mandatory and not covered:
            missing.append(family.key)
            diagnostics.append(_diagnostic(family))

    enforced = is_enforcing(mode)
    status = "fail" if (enforced and missing) else "pass"
    section_count = len(sections)
    if not section_count and isinstance(document_plan, dict):
        section_count = len(_as_list(document_plan.get("section_order")))

    return CoverageReport(
        schema_version=COVERAGE_VALIDATION_SCHEMA_VERSION,
        mode=mode, status=status, enforced=enforced,
        section_count=section_count, family_count=len(families),
        covered_count=sum(1 for f in family_covs if f.covered),
        missing_mandatory=missing, families=family_covs, diagnostics=diagnostics)


# --- the enhancement-mode gate ------------------------------------------------
@dataclass
class CoverageGate:
    """The verdict of the deterministic Phase 2 planned coverage gate.

    This is the planned-coverage upstream-prevention boundary between Phase 2
    planning and Phase 3 retrieval: it never edits, synthesizes, or heals a plan — it only reports the
    coverage verdict and the exit code a caller should fail on. ``passed`` is the
    decision; ``exit_code`` is the process code (``0`` pass, ``3`` enhancement-mode
    fail); ``report`` is the full per-family matrix and actionable diagnostics.
    """

    report: CoverageReport
    passed: bool
    exit_code: int

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "report": self.report.to_dict(),
        }

    def summary_lines(self) -> list:
        """Loud, actionable one-liners for a CLI/log surface.

        Names every missing mandatory family and its remediation so the failure is
        diagnosable from the console without opening the report. Deterministic and
        side-effect-free."""
        r = self.report
        lines = [
            f"planned coverage gate: mode={r.mode} "
            f"({'enforced' if r.enforced else 'report-only'})",
            f"planned coverage gate: {r.covered_count}/{r.family_count} mandatory topic "
            f"families planned across {r.section_count} section(s)",
        ]
        if r.missing_mandatory:
            lines.append(
                "planned coverage gate: missing mandatory topic families: "
                + ", ".join(r.missing_mandatory))
            for d in r.diagnostics:
                lines.append(f"  - {d['family']} ({d['label']}): {d['remediation']}")
        verdict = "PASS" if self.passed else "FAIL"
        if not self.passed:
            lines.append(
                f"planned coverage gate: {verdict} — {len(r.missing_mandatory)} mandatory "
                "topic family(ies) not planned. This deterministic gate does NOT "
                "add pages, labels, or evidence; fix the LLM-authored Phase 2 plan "
                "(stronger prompt/context/schema, or a bounded audited re-prompt) "
                "and re-run before Phase 3 retrieval.")
        else:
            lines.append(f"planned coverage gate: {verdict}")
        return lines


def gate_plan_coverage(document_plan: dict | None, sections: list, *,
                       mode: str = MODE_ENHANCEMENT,
                       families: tuple[TopicFamily, ...] = MANDATORY_TOPIC_FAMILIES
                       ) -> CoverageGate:
    """Evaluate ``sections`` and map the verdict to a :class:`CoverageGate`.

    The single deterministic gate both the standalone ``validate-coverage`` command
    and the integrated ``normalize-plan --coverage-mode enhancement`` planned-coverage boundary use,
    so they enforce identically. In ``enhancement`` mode a missing mandatory family
    yields ``passed == False`` and ``exit_code == COVERAGE_GATE_FAIL_EXIT``; in
    ``baseline`` mode it always passes (report-only). It never mutates the plan."""
    report = evaluate_plan_coverage(document_plan, sections, mode=mode,
                                    families=families)
    passed = report.status == "pass"
    return CoverageGate(
        report=report, passed=passed,
        exit_code=COVERAGE_GATE_PASS_EXIT if passed else COVERAGE_GATE_FAIL_EXIT)


def render_markdown(report: CoverageReport, *,
                    title: str = "Phase 2 Coverage Validation") -> str:
    """Render a human-readable coverage report (the on-disk ``*.md`` artifact)."""
    verdict = "PASS" if report.status == "pass" else "FAIL"
    lines = [
        f"# {title}",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Mode: **{report.mode}** "
        f"({'enforced' if report.enforced else 'report-only'})",
        f"- Status: **{verdict}**",
        f"- Planned sections: {report.section_count}",
        f"- Topic families covered: {report.covered_count}/{report.family_count}",
        "",
        "> Coverage enhancement benchmark only: the reference DeepWiki export is a",
        "> structure/coverage benchmark, never citeable evidence. Line count is a",
        "> warning signal, not the objective.",
        "",
        "## Topic family coverage matrix",
        "",
        "| family | label | planned | covering sections |",
        "|---|---|---|---|",
    ]
    for f in report.families:
        mark = "✅" if f.covered else "❌"
        secs = ", ".join(f"`{s}`" for s in f.covering_sections) or "—"
        lines.append(f"| `{f.key}` | {f.label} | {mark} | {secs} |")
    if report.missing_mandatory:
        lines += ["", "## Missing mandatory topic families", ""]
        for d in report.diagnostics:
            lines.append(f"### `{d['family']}` — {d['label']}")
            lines.append("")
            lines.append(f"- {d['message']}")
            lines.append(f"- Remediation: {d['remediation']}")
            lines.append("")
    else:
        lines += ["", "All mandatory topic families are planned.", ""]
    return "\n".join(lines).rstrip() + "\n"


# --- plan loading -------------------------------------------------------------
def load_plan_from_dir(plans_dir: str):
    """Load ``(document_plan, sections)`` from a normalized-plan directory.

    Reads ``document-plan.json`` and ``section-plans.jsonl`` directly from
    ``plans_dir`` — the exact artifacts ``normalize-plan`` writes and Phase 3
    consumes. Raises ``FileNotFoundError`` if either is missing so the caller can
    fail closed (never gate a plan that was never produced)."""
    from .. import util

    doc_path = os.path.join(plans_dir, "document-plan.json")
    sec_path = os.path.join(plans_dir, "section-plans.jsonl")
    if not os.path.isfile(doc_path):
        raise FileNotFoundError(f"missing normalized document plan: {doc_path}")
    if not os.path.isfile(sec_path):
        raise FileNotFoundError(f"missing normalized section plans: {sec_path}")
    document_plan = util.read_json(doc_path)
    sections = list(util.read_jsonl(sec_path))
    return document_plan, sections


def load_plan_for_coverage(bundle_root: str):
    """Load ``(document_plan, sections)`` from a bundle's ``plans/`` directory.

    Thin wrapper over :func:`load_plan_from_dir` for the standalone
    ``validate-coverage`` command, which is given a bundle root rather than the
    plans directory."""
    return load_plan_from_dir(os.path.join(bundle_root, "plans"))
