"""Resolved, validated options for one Phase 4 ``write-wiki`` run.

The dataclass is the single source of truth for provider config and writing
budgets; the CLI wrapper omits knobs the user did not pass so these defaults
apply. Defaults follow the spec: low temperature (0.1) and a non-tiny output
budget (>= 32768) for ``gemini-2.5-pro`` full-section synthesis — ``8192`` is
explicitly rejected for this workload because the accepted fresh run showed it
can truncate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Provider modes, as recorded in metadata.
PROVIDER_GEMINI_GEM = "gemini-gem"
PROVIDER_GEMINI_API = "direct-gemini-api"
PROVIDER_VERTEX = "vertex-ai"

# CLI provider tokens -> recorded provider mode.
CLI_PROVIDERS = {
    "gemini-gem": PROVIDER_GEMINI_GEM,
    "gemini-api": PROVIDER_GEMINI_API,
    "vertex": PROVIDER_VERTEX,
}

DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_OUTPUT_TOKENS = 32768
# Below this, gemini-2.5-pro full-section synthesis can truncate (spec).
MIN_SAFE_MAX_OUTPUT_TOKENS = 32768
UNSAFE_MAX_OUTPUT_TOKENS = 8192
DEFAULT_STYLE = "deepwiki"
MAX_REWRITE_ATTEMPTS_HARD_CAP = 2

# Phase 4 coverage-gate modes (DeepWiki coverage enhancement). ``baseline`` is the
# historical, backward-compatible behaviour: Phase 4 writes the grounded wiki with
# no planned/evidenced upstream coverage gate and no generated-coverage validation.
# ``enhancement`` (opt-in) refuses to call any provider unless the Phase 2 planned
# coverage gate and the Phase 3 evidenced coverage gate are present, enforced, and
# passing, preserves hierarchy, and deterministically validates that every
# evidenced sufficient required topic was generated with valid citations.
COVERAGE_MODE_BASELINE = "baseline"
COVERAGE_MODE_ENHANCEMENT = "enhancement"
# ``expanded`` is the DeepWiki-style hierarchical mode: a strict superset of
# ``enhancement`` that ALSO validates page-profile / content-block coverage and
# carries the hierarchical page context (profile, catalog topics, content blocks,
# relevant-source-map rows) into the writing packet. It enforces the same
# pre-provider upstream gates as ``enhancement``.
COVERAGE_MODE_EXPANDED = "expanded"
COVERAGE_MODES = (COVERAGE_MODE_BASELINE, COVERAGE_MODE_ENHANCEMENT,
                  COVERAGE_MODE_EXPANDED)
# The coverage modes that enforce the upstream gates + generated-coverage gate.
ENFORCING_COVERAGE_MODES = (COVERAGE_MODE_ENHANCEMENT, COVERAGE_MODE_EXPANDED)


@dataclass(frozen=True)
class WritingOptions:
    """One Phase 4 run's resolved configuration."""

    bundle_root: str                       # absolute Phase 1/2/3 bundle root
    out_dir: str                           # absolute wiki output dir (default <bundle>/wiki)
    provider: str = PROVIDER_VERTEX        # recorded provider mode

    # generation knobs (api/vertex)
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    # gemini-gem handoff
    prompt_out: str | None = None          # where prepared prompts are written
    responses_in: str | None = None        # verbatim raw responses to import

    # phase control
    prepare_only: bool = False             # write prompts/packets only, no generation
    validate_and_assemble: bool = True     # generate (or import) + validate + assemble

    # bounded rewrite for format/citation violations only
    max_rewrite_attempts: int = 1

    # provider config (api/vertex)
    project: str | None = None
    location: str | None = None
    api_key: str | None = None

    # DeepWiki coverage enhancement (opt-in; default non-breaking baseline)
    coverage_mode: str = COVERAGE_MODE_BASELINE

    # Grounded claim/token planning (opt-in; default off / freeform). When set,
    # Phase 4 asks the model for a structured claim plan that references terminal
    # technical strings only by token-bank id, validates it deterministically, and
    # renders the Markdown from accepted skeletons + exact token substitutions —
    # preventing invented identifiers/routes/paths upstream rather than catching
    # them after generation. Composes with either coverage mode.
    grounded_claim_plan: bool = False

    # misc
    style: str = DEFAULT_STYLE
    audit_raw: bool = True
    accept_no_force: bool = False          # operator asserts Phase 3 ran without --force

    warnings: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provider not in CLI_PROVIDERS.values():
            raise ValueError(
                f"unknown provider mode {self.provider!r}; expected one of "
                f"{sorted(CLI_PROVIDERS.values())}")
        if self.coverage_mode not in COVERAGE_MODES:
            raise ValueError(
                f"--coverage-mode must be one of {COVERAGE_MODES}, "
                f"got {self.coverage_mode!r}")
        if not 0.0 <= float(self.temperature) <= 2.0:
            raise ValueError(f"--temperature must be in [0, 2], got {self.temperature}")
        if int(self.max_output_tokens) < 1:
            raise ValueError(
                f"--max-output-tokens must be >= 1, got {self.max_output_tokens}")
        cap = int(self.max_rewrite_attempts)
        if cap < 0 or cap > MAX_REWRITE_ATTEMPTS_HARD_CAP:
            raise ValueError(
                f"--max-rewrite-attempts must be 0..{MAX_REWRITE_ATTEMPTS_HARD_CAP}, "
                f"got {self.max_rewrite_attempts}")

    @property
    def uses_live_model(self) -> bool:
        """True when generation calls a model API (not the gem import path)."""
        return self.provider in (PROVIDER_GEMINI_API, PROVIDER_VERTEX)

    @property
    def is_enhancement(self) -> bool:
        """True when the opt-in DeepWiki coverage enhancement mode is requested."""
        return self.coverage_mode == COVERAGE_MODE_ENHANCEMENT

    @property
    def is_expanded(self) -> bool:
        """True when the opt-in DeepWiki-style expanded coverage mode is requested."""
        return self.coverage_mode == COVERAGE_MODE_EXPANDED

    @property
    def enforces_coverage(self) -> bool:
        """True when the run enforces upstream + generated coverage gates
        (``enhancement`` or ``expanded``)."""
        return self.coverage_mode in ENFORCING_COVERAGE_MODES

    @property
    def is_grounded(self) -> bool:
        """True when the opt-in grounded claim/token planning path is requested."""
        return bool(self.grounded_claim_plan)

    @property
    def model_for_metadata(self) -> str | None:
        return self.model if self.uses_live_model else None

    def truncation_risk(self) -> str | None:
        """A warning string when the output budget is too small for
        ``gemini-2.5-pro`` full-section synthesis, else None."""
        if not self.uses_live_model:
            return None
        if "gemini-2.5-pro" in (self.model or "") and \
                int(self.max_output_tokens) < MIN_SAFE_MAX_OUTPUT_TOKENS:
            return (f"max_output_tokens={self.max_output_tokens} is below the "
                    f"safe minimum {MIN_SAFE_MAX_OUTPUT_TOKENS} for "
                    f"{self.model} full-section synthesis; {UNSAFE_MAX_OUTPUT_TOKENS} "
                    "is known to truncate. Increase it to avoid token truncation.")
        return None
