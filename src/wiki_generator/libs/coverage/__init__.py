"""DeepWiki-informed coverage taxonomy and coverage validation (Milestone 2).

Deterministic, LLM-free, read-only scaffolding that checks a Phase 2 plan against
the mandatory topic families a coverage-enhanced repository guide must plan for.
See ``taxonomy.py`` for the family model and ``validate.py`` for the validator.
"""
from __future__ import annotations

from .taxonomy import (
    MANDATORY_TOPIC_FAMILIES,
    TopicFamily,
    family_by_key,
    family_keys,
)
from .validate import (
    COVERAGE_GATE_FAIL_EXIT,
    COVERAGE_GATE_INPUT_EXIT,
    COVERAGE_GATE_PASS_EXIT,
    COVERAGE_VALIDATION_SCHEMA_VERSION,
    MODE_BASELINE,
    MODE_ENHANCEMENT,
    CoverageGate,
    CoverageReport,
    FamilyCoverage,
    evaluate_plan_coverage,
    gate_plan_coverage,
    load_plan_for_coverage,
    load_plan_from_dir,
    render_markdown,
)
from .obligations import (
    FAILURE_CATEGORY as OBLIGATION_FAILURE_CATEGORY,
    TOPIC_OBLIGATIONS_SCHEMA_VERSION,
    ObligationGate,
    ObligationReport,
    SectionObligations,
    TopicObligation,
    evaluate_topic_obligations,
    gate_topic_obligations,
    render_obligations_markdown,
)
from .substrate import (
    CITEABLE_SUBSTRATE_SCHEMA_VERSION,
    CiteableSubstrate,
    load_citeable_substrate,
)
from .signals import (
    COVERAGE_SIGNALS_SCHEMA_VERSION,
    DETECTORS,
    CoverageSignals,
    FamilyDetector,
    FamilySignal,
    canonical_label_line,
    derive_coverage_signals,
    render_signals_markdown,
)

__all__ = [
    "MANDATORY_TOPIC_FAMILIES",
    "TopicFamily",
    "family_by_key",
    "family_keys",
    "COVERAGE_GATE_FAIL_EXIT",
    "COVERAGE_GATE_INPUT_EXIT",
    "COVERAGE_GATE_PASS_EXIT",
    "COVERAGE_VALIDATION_SCHEMA_VERSION",
    "MODE_BASELINE",
    "MODE_ENHANCEMENT",
    "CoverageGate",
    "CoverageReport",
    "FamilyCoverage",
    "evaluate_plan_coverage",
    "gate_plan_coverage",
    "load_plan_for_coverage",
    "load_plan_from_dir",
    "render_markdown",
    "OBLIGATION_FAILURE_CATEGORY",
    "TOPIC_OBLIGATIONS_SCHEMA_VERSION",
    "ObligationGate",
    "ObligationReport",
    "SectionObligations",
    "TopicObligation",
    "evaluate_topic_obligations",
    "gate_topic_obligations",
    "render_obligations_markdown",
    "CITEABLE_SUBSTRATE_SCHEMA_VERSION",
    "CiteableSubstrate",
    "load_citeable_substrate",
    "COVERAGE_SIGNALS_SCHEMA_VERSION",
    "DETECTORS",
    "CoverageSignals",
    "FamilyDetector",
    "FamilySignal",
    "canonical_label_line",
    "derive_coverage_signals",
    "render_signals_markdown",
]
