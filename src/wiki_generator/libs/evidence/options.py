"""Deterministic command options for Phase 3 evidence retrieval.

The dataclass is the single source of truth for retrieval caps; the CLI wrapper
omits knobs the user did not pass so these defaults apply. Defaults are stable
constants so reruns over identical inputs are byte-identical.
"""
from __future__ import annotations

from dataclasses import dataclass

# Implementation constants. Stable across runs (see PHASE3 spec "Command").
DEFAULT_MAX_PER_LANE = 8
DEFAULT_MAX_TOTAL_PER_SECTION = 40

# Evidenced-coverage gate modes (Phase 3 evidenced coverage). ``baseline`` is the
# historical, non-breaking behaviour: evidenced coverage is reported but never
# gates the run. ``enhancement`` fails the run before Phase 4 when a required
# topic's evidence is weak or missing (spec "CLI and mode behavior"). ``expanded``
# is the DeepWiki-style hierarchical mode: it enforces the same required-topic
# sufficiency AND a profile-aware evidence portfolio per page (a page must carry a
# sufficient exact handle in one of its page-profile floor lanes; a broad recall
# lane alone is never enough). Both enhancement and expanded fail closed; expanded
# adds the additive page_profile / catalog_topic_id / content_block_id linkage and
# the portfolio verdict to the evidenced-coverage matrix.
COVERAGE_MODE_BASELINE = "baseline"
COVERAGE_MODE_ENHANCEMENT = "enhancement"
COVERAGE_MODE_EXPANDED = "expanded"
COVERAGE_MODES = (COVERAGE_MODE_BASELINE, COVERAGE_MODE_ENHANCEMENT,
                  COVERAGE_MODE_EXPANDED)


@dataclass(frozen=True)
class EvidenceOptions:
    """Resolved, validated options for one all-sections Phase 3 run."""

    bundle_root: str                 # absolute Phase 1/2 bundle root
    out_dir: str                     # absolute evidence output dir
    max_per_lane: int = DEFAULT_MAX_PER_LANE
    max_total_per_section: int = DEFAULT_MAX_TOTAL_PER_SECTION
    coverage_mode: str = COVERAGE_MODE_BASELINE

    def __post_init__(self) -> None:
        if self.max_per_lane < 1:
            raise ValueError(f"--max-per-lane must be >= 1, got {self.max_per_lane}")
        if self.max_total_per_section < 1:
            raise ValueError(
                f"--max-total-per-section must be >= 1, got {self.max_total_per_section}")
        if self.coverage_mode not in COVERAGE_MODES:
            raise ValueError(
                f"--coverage-mode must be one of {COVERAGE_MODES}, "
                f"got {self.coverage_mode!r}")
