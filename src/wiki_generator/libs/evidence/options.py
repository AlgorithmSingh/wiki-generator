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


@dataclass(frozen=True)
class EvidenceOptions:
    """Resolved, validated options for one all-sections Phase 3 run."""

    bundle_root: str                 # absolute Phase 1/2 bundle root
    out_dir: str                     # absolute evidence output dir
    max_per_lane: int = DEFAULT_MAX_PER_LANE
    max_total_per_section: int = DEFAULT_MAX_TOTAL_PER_SECTION

    def __post_init__(self) -> None:
        if self.max_per_lane < 1:
            raise ValueError(f"--max-per-lane must be >= 1, got {self.max_per_lane}")
        if self.max_total_per_section < 1:
            raise ValueError(
                f"--max-total-per-section must be >= 1, got {self.max_total_per_section}")
