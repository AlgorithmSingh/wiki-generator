"""Deterministic page-profile taxonomy for expanded (DeepWiki-style) coverage.

This is the single source of truth for *what each page type must contain* and
*which exact evidence lanes can satisfy it*. It is consumed by three later gates,
so they cannot drift:

- **Phase B** (:mod:`.page_planning`) uses :func:`required_block_ids` to check that
  a profile-bearing page declares every required content block of its profile, and
  :func:`is_valid_profile` to reject an unknown profile.
- **Phase D** (:mod:`wiki_generator.libs.evidence.evidenced_coverage`) uses
  :func:`profile_evidence_floor` to require that a page carry at least one sufficient
  exact citeable handle from a profile-appropriate lane — broad recall alone is
  never enough for a precise technical page (PRD BR-04/QA-06).
- **Phase E** (:mod:`wiki_generator.libs.writing.generated_coverage`) uses
  :func:`required_block_ids` to validate generated ``covered_content_blocks[]``.

It is deterministic, import-light, LLM-free, and timestamp-free. The profiles and
their required blocks are derived from the TDD §7.2 page-profile table; they are
catalog *suggestions* a planner adopts, and an explicit expanded-mode contract a
plan is validated against — never benchmark-copied structure.

Hard discipline:

- The ten profiles below are the closed valid set; an unknown profile is a plan
  defect, not silently accepted.
- ``evidence_required`` marks a content block that needs exact citeable source
  evidence (``flow``, ``key_files``, ``handlers`` …) versus a narrative/gap block
  that does not (``purpose``, ``known_gaps``, glossary ``meaning_context`` …). The
  evidence-bearing blocks are what Phase D/E hold to exact-evidence floors.
- The exact lanes a floor may name are exactly the citeable lanes shared with the
  obligation gate (``file_anchor`` / ``symbol_anchor`` / ``contract`` / ``test`` /
  ``query_pack``); broad recall lanes are never a floor.
"""
from __future__ import annotations

from dataclasses import dataclass

PAGE_PROFILES_SCHEMA_VERSION = "deepwiki-page-profiles-v1"

# The exact (citeable) evidence lanes a profile floor may require. Mirrors
# ``obligations.EXACT_FIELD_LANES`` values and the Phase 3 exact-lane mapping, so
# the page-profile floor and the per-topic obligation gate share one lane taxonomy.
EXACT_LANES = ("file_anchor", "symbol_anchor", "contract", "test", "query_pack")


@dataclass(frozen=True)
class ContentBlockSpec:
    """One required content block of a page profile.

    ``block_id``         stable id a plan's ``required_content_blocks[]`` references.
    ``block_type``       coarse block category (often equal to ``block_id``).
    ``evidence_required``True when the block must be grounded in exact citeable
                         source evidence (Phase D/E hold these to the profile floor);
                         False for narrative/gap blocks (purpose, known_gaps, …).
    """

    block_id: str
    block_type: str
    evidence_required: bool = True


def _b(block_id: str, *, evidence: bool = True,
       block_type: str | None = None) -> ContentBlockSpec:
    return ContentBlockSpec(block_id=block_id,
                            block_type=block_type or block_id,
                            evidence_required=evidence)


@dataclass(frozen=True)
class PageProfile:
    """A page profile: its required content blocks and its exact-evidence floor.

    ``required_blocks``     the blocks a plan MUST declare for a page of this profile.
    ``evidence_floor_lanes``the exact lanes that can satisfy a page of this profile;
                            Phase D requires ≥1 sufficient exact handle from one of
                            them. An empty floor (the glossary) is synthesized and
                            holds no exact floor.
    ``min_exact_items``     the minimum count of exact citeable handles a normal page
                            of this profile should carry (Phase D portfolio floor).
    """

    key: str
    label: str
    required_blocks: tuple
    evidence_floor_lanes: tuple = EXACT_LANES
    min_exact_items: int = 1

    def required_block_ids(self) -> tuple:
        return tuple(b.block_id for b in self.required_blocks)

    def evidence_block_ids(self) -> tuple:
        return tuple(b.block_id for b in self.required_blocks if b.evidence_required)


# The ten initial page profiles (TDD §7.2). Each names the blocks a page of that
# profile must declare and the exact lanes its evidence floor accepts.
PAGE_PROFILES: dict = {
    "overview": PageProfile(
        key="overview", label="Repository overview",
        required_blocks=(_b("purpose", evidence=False), _b("architecture"),
                         _b("key_files")),
        evidence_floor_lanes=("file_anchor", "symbol_anchor", "query_pack"),
        min_exact_items=1),
    "architecture-flow": PageProfile(
        key="architecture-flow", label="Architecture / data-flow page",
        required_blocks=(_b("purpose", evidence=False), _b("flow"), _b("key_files")),
        evidence_floor_lanes=("file_anchor", "symbol_anchor"),
        min_exact_items=2),
    "subsystem-deep-dive": PageProfile(
        key="subsystem-deep-dive", label="Subsystem deep dive",
        required_blocks=(_b("purpose", evidence=False), _b("entrypoints"),
                         _b("flow"), _b("key_files"), _b("tests")),
        evidence_floor_lanes=("file_anchor", "symbol_anchor", "test"),
        min_exact_items=3),
    "api-reference": PageProfile(
        key="api-reference", label="API reference",
        required_blocks=(_b("purpose", evidence=False), _b("route_matrix"),
                         _b("request_response"), _b("handlers"),
                         _b("examples_tests"), _b("known_gaps", evidence=False)),
        evidence_floor_lanes=("contract", "file_anchor", "symbol_anchor"),
        min_exact_items=2),
    "configuration-reference": PageProfile(
        key="configuration-reference", label="Configuration reference",
        required_blocks=(_b("config_matrix"), _b("defaults_source"),
                         _b("consumers"), _b("operational_notes", evidence=False)),
        evidence_floor_lanes=("file_anchor", "query_pack", "symbol_anchor"),
        min_exact_items=2),
    "deployment-runbook": PageProfile(
        key="deployment-runbook", label="Deployment runbook",
        required_blocks=(_b("entrypoints"), _b("containers"), _b("orchestration"),
                         _b("config_secrets"), _b("health_ops"),
                         _b("rollback", evidence=False)),
        evidence_floor_lanes=("file_anchor", "query_pack"),
        min_exact_items=2),
    "developer-workflow": PageProfile(
        key="developer-workflow", label="Developer workflow",
        required_blocks=(_b("purpose", evidence=False), _b("entrypoints"),
                         _b("flow"), _b("tests")),
        evidence_floor_lanes=("file_anchor", "test", "symbol_anchor"),
        min_exact_items=2),
    "data-model-reference": PageProfile(
        key="data-model-reference", label="Data-model reference",
        required_blocks=(_b("purpose", evidence=False), _b("data_models"),
                         _b("key_files")),
        evidence_floor_lanes=("symbol_anchor", "file_anchor"),
        min_exact_items=2),
    "operations-page": PageProfile(
        key="operations-page", label="Operations page",
        required_blocks=(_b("purpose", evidence=False), _b("operations"),
                         _b("key_files"), _b("known_gaps", evidence=False)),
        evidence_floor_lanes=("file_anchor", "query_pack"),
        min_exact_items=1),
    "glossary": PageProfile(
        key="glossary", label="Glossary",
        required_blocks=(_b("term", evidence=False),
                         _b("source_occurrence", evidence=False),
                         _b("meaning_context", evidence=False)),
        evidence_floor_lanes=(),
        min_exact_items=0),
}

VALID_PROFILES = frozenset(PAGE_PROFILES)


def is_valid_profile(profile: str | None) -> bool:
    """True when ``profile`` is one of the ten known page profiles."""
    return isinstance(profile, str) and profile in PAGE_PROFILES


def profile_by_key(profile: str | None) -> PageProfile | None:
    """The :class:`PageProfile` for ``profile``, or ``None`` if unknown."""
    if not isinstance(profile, str):
        return None
    return PAGE_PROFILES.get(profile)


def required_block_ids(profile: str | None) -> tuple:
    """The required content-block ids of ``profile``, or ``()`` if unknown."""
    p = profile_by_key(profile)
    return p.required_block_ids() if p else ()


def evidence_block_ids(profile: str | None) -> tuple:
    """The required content-block ids of ``profile`` that need exact evidence."""
    p = profile_by_key(profile)
    return p.evidence_block_ids() if p else ()


def profile_evidence_floor(profile: str | None) -> tuple:
    """The exact lanes that can satisfy a page of ``profile`` (Phase D floor)."""
    p = profile_by_key(profile)
    return p.evidence_floor_lanes if p else ()


def profile_min_exact_items(profile: str | None) -> int:
    """The minimum exact citeable handle count for a page of ``profile``."""
    p = profile_by_key(profile)
    return p.min_exact_items if p else 0
