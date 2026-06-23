"""Phase 4 failure taxonomy: typed exceptions, categories, and exit codes.

Phase 4 is a *synthesis* step. It fails closed on anything that would let an
ungrounded, stale, forced, or unsupported claim reach the final wiki. Every
failure maps to exactly one category and one exit code so the CLI wrapper stays
a thin dispatcher (mirrors the Phase 3 ``evidence/schema.py`` convention).

Exit codes:
- 0  PASS
- 1  internal writer bug (unclassified)
- 2  bad/missing input artifact (a required bundle file is missing/invalid)
- 3  upstream gate failure (readiness/retrieval/force/stale/hygiene/packets) —
     the fix lives in Phase 1/2/3, not here
- 4  provider failure (credentials, quota, safety block, network, bad config)
- 5  writing-validation failure (unresolved citation, context-artifact citation,
     unsupported/invented claim, placeholder, or provider truncation that a
     bounded rewrite could not repair)
"""
from __future__ import annotations

# --- failure categories -------------------------------------------------------
CAT_BAD_INPUT = "bad_missing_input_artifact"
CAT_GATE = "upstream_gate_not_satisfied"
CAT_PROVIDER = "provider_failure"
CAT_WRITING = "writing_validation_failure"
CAT_BUG = "writer_implementation_bug"

# --- exit codes ---------------------------------------------------------------
EXIT_OK = 0
EXIT_BUG = 1
EXIT_BAD_INPUT = 2
EXIT_GATE = 3
EXIT_PROVIDER = 4
EXIT_WRITING = 5

EXIT_FOR_CATEGORY = {
    None: EXIT_OK,
    CAT_BAD_INPUT: EXIT_BAD_INPUT,
    CAT_GATE: EXIT_GATE,
    CAT_PROVIDER: EXIT_PROVIDER,
    CAT_WRITING: EXIT_WRITING,
    CAT_BUG: EXIT_BUG,
}


class Phase4Error(RuntimeError):
    """Base class for all classified Phase 4 failures."""

    category = CAT_BUG

    @property
    def exit_code(self) -> int:
        return EXIT_FOR_CATEGORY.get(self.category, EXIT_BUG)


class BadInputArtifact(Phase4Error):
    """A required bundle artifact is missing, unreadable, or schema-invalid."""

    category = CAT_BAD_INPUT


class GateFailure(Phase4Error):
    """A precondition gate failed: readiness, retrieval validation, force/stale
    provenance, source hygiene, or section-packet presence. Fix upstream."""

    category = CAT_GATE


class ProviderFailure(Phase4Error):
    """The model provider could not be configured or returned a hard error."""

    category = CAT_PROVIDER


class WritingValidationFailure(Phase4Error):
    """A generated section failed citation/claim/placeholder/truncation checks and
    no permitted bounded rewrite could repair it."""

    category = CAT_WRITING
