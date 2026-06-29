"""Phase A: the deterministic repository-derived hierarchical topic catalog.

This is the first authorized coverage-expansion slice (TDD Milestone A, shadow
mode). It turns the flat per-family coverage signal that :mod:`.signals` produces
into a shallow parent/child *topic catalog* — one parent topic per mandatory
DeepWiki family plus child *subsystem* topics derived from :mod:`.facets` — and
serialises it as:

- ``derived/topic-catalog.json``  (schema ``deepwiki-topic-catalog-v1``)
- ``derived/planning-topic-catalog.md`` (the planner-facing summary)

It is **shadow mode**: it only adds artifacts. It enforces no new gate, requires
no live model, and does not change generated wiki output. Every downstream
milestone (hierarchical planning, source selection, evidence portfolios) can read
this catalog, but Phase A wires none of that enforcement.

Hard discipline (binding, mirrors the rest of the pipeline):

- **Deterministic and timestamp-free.** Identical Phase 1 input → byte-identical
  JSON and Markdown. There is intentionally **no** ``generated_at`` wall-clock
  field; a ``source_fingerprint`` over the topics is the stable identity the TDD's
  freshness/traceability milestones consume.
- **Planner CONTEXT, never citeable evidence.** The catalog is marked
  ``citeable_as_evidence: false`` / ``role: planner_context``; the Markdown carries
  a loud non-citeable warning. Repo claims must still cite exact handles that
  resolve through the Phase 3 citation manifest.
- **Repository-derived only; benchmark-isolated.** Every signal's ``source`` is
  ``repo``. No benchmark export (e.g. ``ragflow-deepwiki.md``) is read, copied, or
  referenced as evidence — the breadth comparator stays comparator-only.
- **Gaps are explicit.** A family with no Phase 1 signal becomes a *deferred*
  known-gap topic with a source-derived reason, never an invented page.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from ..util import read_json, sha256_text
from .facets import derive_family_facets
from .signals import (
    DETECTORS,
    STATUS_LOW,
    STATUS_MISSING,
    STATUS_PRESENT,
    STATUS_SYNTHESIZED,
    CoverageSignals,
    FamilySignal,
    derive_coverage_signals,
    family_candidates,
    status_for,
)
from .taxonomy import family_by_key

TOPIC_CATALOG_SCHEMA_VERSION = "deepwiki-topic-catalog-v1"

# Where Phase 1 condense writes the machine-readable catalog within a bundle.
TOPIC_CATALOG_REL_PATH = os.path.join("derived", "topic-catalog.json")

# A topic is a family-level parent or a subsystem-level child.
TOPIC_KIND_FAMILY = "family"
TOPIC_KIND_SUBSYSTEM = "subsystem"

# --- Phase-A profile / block / lane mappings ---------------------------------
# These are catalog *suggestions* for the later hierarchical planner, never gates
# in Phase A. They keep the catalog informative for Milestone B without enforcing
# any page-profile contract here.
DEFAULT_CHILD_PROFILE = "subsystem-deep-dive"

SUGGESTED_PROFILE_BY_FAMILY: dict = {
    "frontend": "subsystem-deep-dive",
    "memory": "subsystem-deep-dive",
    "queue-system": "subsystem-deep-dive",
    "helm-k8s": "deployment-runbook",
    "ci-cd-build": "deployment-runbook",
    "go-native": "subsystem-deep-dive",
    "retrieval-internals": "subsystem-deep-dive",
    "doc-processing": "subsystem-deep-dive",
    "llm-internals": "subsystem-deep-dive",
    "user-tenant-admin-health": "operations-page",
    "sandbox-executor": "subsystem-deep-dive",
    "migrations-operations": "operations-page",
    "glossary": "glossary",
}

CONTENT_BLOCKS_BY_PROFILE: dict = {
    "subsystem-deep-dive": ("purpose", "entrypoints", "flow", "key_files", "tests"),
    "deployment-runbook": ("entrypoints", "config", "health_ops", "rollback"),
    "operations-page": ("purpose", "operations", "key_files", "known_gaps"),
    "glossary": ("term", "source_occurrence", "meaning_context"),
}
DEFAULT_CONTENT_BLOCKS = ("purpose", "key_files")

PROFILE_DEFAULT_LANES: dict = {
    "subsystem-deep-dive": ("file_anchor", "symbol_anchor"),
    "deployment-runbook": ("config", "file_anchor"),
    "operations-page": ("file_anchor",),
    "glossary": (),
}
LANE_BY_SIGNAL_KIND: dict = {
    "path": "file_anchor",
    "symbol": "symbol_anchor",
    "query_pack": "query_pack",
}

# signal status -> catalog signal-strength / planning priority / evidence floor.
STRENGTH_BY_STATUS: dict = {
    STATUS_PRESENT: "high",
    STATUS_LOW: "low",
    STATUS_MISSING: "none",
    STATUS_SYNTHESIZED: "medium",
}
PRIORITY_BY_STATUS: dict = {
    STATUS_PRESENT: "must",
    STATUS_LOW: "should",
    STATUS_MISSING: "could",
    STATUS_SYNTHESIZED: "should",
}
MIN_EXACT_BY_STATUS: dict = {
    STATUS_PRESENT: 3,
    STATUS_LOW: 2,
    STATUS_MISSING: 0,
    STATUS_SYNTHESIZED: 0,
}

# Bounds on the parent topic's signal/handle lists (the per-family detector
# already caps its candidate_paths/symbols; this caps query-pack signals).
_MAX_QUERY_PACK_SIGNALS = 8

_DEFER_REASON = ("No Phase-1 source signal detected for this family. Recorded as "
                 "a deferred known gap; a later page must be backed by repository "
                 "evidence or this gap kept explicit — never an invented page.")


# --- catalog data model -------------------------------------------------------
@dataclass(frozen=True)
class TopicSignal:
    """One source-derived signal supporting a topic. ``source`` is always
    ``repo`` — benchmark material can never seed a catalog signal."""

    kind: str          # path | symbol | query_pack | glossary_seed
    value: str
    weight: float
    source: str = "repo"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value,
                "weight": self.weight, "source": self.source}


@dataclass(frozen=True)
class SourceHandle:
    """A citeable-source *candidate* for later Phase 2/3 selection. It is a
    candidate handle only — Phase A does not retrieve or cite it."""

    kind: str          # file | symbol | query_pack
    path: str | None = None
    symbol: str | None = None
    line_start: int | None = None
    line_end: int | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "symbol": self.symbol,
                "line_start": self.line_start, "line_end": self.line_end}


@dataclass(frozen=True)
class CatalogTopic:
    """One catalog topic: a family-level parent or a subsystem-level child."""

    topic_id: str
    parent_topic_id: str | None
    family: str
    label: str
    topic_kind: str
    suggested_page_profile: str
    status: str
    signal_strength: str
    priority: str
    source_signals: tuple = field(default_factory=tuple)
    candidate_source_handles: tuple = field(default_factory=tuple)
    required_content_blocks: tuple = field(default_factory=tuple)
    expected_evidence_lanes: tuple = field(default_factory=tuple)
    min_exact_items: int = 0
    known_gap_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "parent_topic_id": self.parent_topic_id,
            "family": self.family,
            "label": self.label,
            "topic_kind": self.topic_kind,
            "suggested_page_profile": self.suggested_page_profile,
            "status": self.status,
            "signal_strength": self.signal_strength,
            "priority": self.priority,
            "source_signals": [s.to_dict() for s in self.source_signals],
            "candidate_source_handles": [h.to_dict()
                                         for h in self.candidate_source_handles],
            "required_content_blocks": list(self.required_content_blocks),
            "expected_evidence_lanes": list(self.expected_evidence_lanes),
            "min_exact_items": self.min_exact_items,
            "known_gap_reason": self.known_gap_reason,
        }


@dataclass(frozen=True)
class TopicCatalog:
    """The whole repository-derived topic catalog (planner context, non-citeable)."""

    schema_version: str
    source_fingerprint: str
    repo_root: str
    topic_count: int
    family_count: int
    subsystem_count: int
    deferred_count: int
    topics: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "role": "planner_context",
            "citeable_as_evidence": False,
            "source_fingerprint": self.source_fingerprint,
            "repo_root": self.repo_root,
            "topic_count": self.topic_count,
            "family_count": self.family_count,
            "subsystem_count": self.subsystem_count,
            "deferred_count": self.deferred_count,
            "topics": [t.to_dict() for t in self.topics],
        }


# --- builders -----------------------------------------------------------------
def _content_blocks(profile: str) -> tuple:
    return CONTENT_BLOCKS_BY_PROFILE.get(profile, DEFAULT_CONTENT_BLOCKS)


def _evidence_lanes(profile: str, signal_kinds: set) -> tuple:
    lanes = set(PROFILE_DEFAULT_LANES.get(profile, ()))
    for kind in signal_kinds:
        lane = LANE_BY_SIGNAL_KIND.get(kind)
        if lane:
            lanes.add(lane)
    return tuple(sorted(lanes))


def _family_signals_and_handles(fs: FamilySignal) -> tuple:
    """Build the parent topic's ``source_signals`` and ``candidate_source_handles``
    from a :class:`FamilySignal`, plus the set of signal kinds present."""
    signals: list = []
    handles: list = []
    kinds: set = set()

    for c in fs.candidate_paths:
        path = str(c.get("path") or "")
        if not path:
            continue
        signals.append(TopicSignal("path", path, 1.0))
        handles.append(SourceHandle("file", path=path))
        kinds.add("path")
    for qp in fs.query_packs[:_MAX_QUERY_PACK_SIGNALS]:
        pack = str(qp.get("pack") or "")
        if not pack:
            continue
        signals.append(TopicSignal("query_pack", pack,
                                   float(qp.get("hits") or 1)))
        handles.append(SourceHandle("query_pack", path=None, symbol=None))
        kinds.add("query_pack")
    for sid in fs.symbols:
        signals.append(TopicSignal("symbol", str(sid), 1.0))
        handles.append(SourceHandle("symbol", symbol=str(sid)))
        kinds.add("symbol")

    # The glossary is synthesized from other families' names, not located in a
    # file; record those seeds as repo-derived signals so the topic is honest.
    if fs.status == STATUS_SYNTHESIZED:
        for seed in fs.synthesized_from:
            signals.append(TopicSignal("glossary_seed", str(seed), 0.5))
        kinds.discard("path")
    return signals, handles, kinds


def _parent_topic(fs: FamilySignal) -> CatalogTopic:
    fam = family_by_key(fs.key)
    label = fam.label if fam else fs.key
    profile = SUGGESTED_PROFILE_BY_FAMILY.get(fs.key, DEFAULT_CHILD_PROFILE)
    signals, handles, kinds = _family_signals_and_handles(fs)
    deferred = fs.status == STATUS_MISSING
    return CatalogTopic(
        topic_id=fs.key,
        parent_topic_id=None,
        family=fs.key,
        label=label,
        topic_kind=TOPIC_KIND_FAMILY,
        suggested_page_profile=profile,
        status=fs.status,
        signal_strength=STRENGTH_BY_STATUS.get(fs.status, "none"),
        priority=PRIORITY_BY_STATUS.get(fs.status, "could"),
        source_signals=tuple(signals),
        candidate_source_handles=tuple(handles),
        required_content_blocks=_content_blocks(profile),
        expected_evidence_lanes=_evidence_lanes(profile, kinds),
        min_exact_items=MIN_EXACT_BY_STATUS.get(fs.status, 0),
        known_gap_reason=_DEFER_REASON if deferred else None,
    )


def _child_topic(fs: FamilySignal, facet) -> CatalogTopic:
    fam = family_by_key(fs.key)
    fam_label = fam.label if fam else fs.key
    status = status_for(facet.file_count)
    signals = [TopicSignal("path", p, 1.0) for p in facet.paths]
    handles = [SourceHandle("file", path=p) for p in facet.paths]
    profile = DEFAULT_CHILD_PROFILE
    return CatalogTopic(
        topic_id=f"{fs.key}.{facet.facet_key}",
        parent_topic_id=fs.key,
        family=fs.key,
        label=f"{fam_label} — {facet.directory}",
        topic_kind=TOPIC_KIND_SUBSYSTEM,
        suggested_page_profile=profile,
        status=status,
        signal_strength=STRENGTH_BY_STATUS.get(status, "none"),
        priority=PRIORITY_BY_STATUS.get(status, "could"),
        source_signals=tuple(signals),
        candidate_source_handles=tuple(handles),
        required_content_blocks=_content_blocks(profile),
        expected_evidence_lanes=_evidence_lanes(profile, {"path"}),
        min_exact_items=MIN_EXACT_BY_STATUS.get(status, 0),
        known_gap_reason=None,
    )


def _topics_for_family(fs: FamilySignal, files: list) -> list:
    """The parent topic for a family, followed by its subsystem child topics.

    Children are emitted only for a *present* (high-signal) family that has at
    least two distinct leaf-directory subsystems — a single-subsystem or
    low/missing family is fully represented by its parent topic, avoiding 1:1
    parent/child noise."""
    topics: list = [_parent_topic(fs)]
    if fs.status != STATUS_PRESENT:
        return topics
    candidates = family_candidates(files, DETECTORS[fs.key])
    facets = derive_family_facets(fs.key, candidates)
    if len(facets) < 2:
        return topics
    for facet in facets:
        topics.append(_child_topic(fs, facet))
    return topics


def _fingerprint(topic_dicts: list) -> str:
    payload = json.dumps(topic_dicts, sort_keys=True, ensure_ascii=False)
    return "sha256:" + sha256_text(payload)


def build_topic_catalog(bundle,
                        signals: CoverageSignals | None = None) -> TopicCatalog:
    """Build the deterministic repository-derived topic catalog from a Phase 1
    bundle. ``signals`` may be passed to avoid recomputing the per-family signal;
    otherwise it is derived here. Pure and deterministic — no timestamps, no
    network, no model, no benchmark input."""
    cov = signals if signals is not None else derive_coverage_signals(bundle)
    files = list(getattr(bundle, "files", []) or [])

    topics: list = []
    for fs in cov.families:
        topics.extend(_topics_for_family(fs, files))

    topic_dicts = [t.to_dict() for t in topics]
    subsystem_count = sum(1 for t in topics
                          if t.topic_kind == TOPIC_KIND_SUBSYSTEM)
    deferred_count = sum(1 for t in topics if t.status == STATUS_MISSING)
    return TopicCatalog(
        schema_version=TOPIC_CATALOG_SCHEMA_VERSION,
        source_fingerprint=_fingerprint(topic_dicts),
        repo_root=cov.repo_root,
        topic_count=len(topics),
        family_count=cov.family_count,
        subsystem_count=subsystem_count,
        deferred_count=deferred_count,
        topics=tuple(topics),
    )


# --- catalog loading ----------------------------------------------------------
def load_topic_catalog(bundle_dir: str) -> dict | None:
    """Load the deterministic ``derived/topic-catalog.json`` from a bundle.

    Returns the parsed dict (with its ``topics[]``), or ``None`` when the catalog
    is absent — the Phase B/C expanded gates treat an absent catalog as a hard
    missing-input failure, while baseline/enhancement runs never read it. Read-only;
    no network, no model."""
    path = os.path.join(bundle_dir, TOPIC_CATALOG_REL_PATH)
    if not os.path.isfile(path):
        return None
    catalog = read_json(path)
    return catalog if isinstance(catalog, dict) else None


# --- planner-facing markdown --------------------------------------------------
_NONCITEABLE_WARNING = (
    "> ⚠️ **Planner CONTEXT, not evidence.** This catalog is a deterministic, "
    "source-derived map of candidate topics and subsystems built only from this "
    "repository's Phase 1 decomposition. It is **non-citeable** — a topic, label, "
    "or candidate source handle here is a hint to plan and retrieve, **not "
    "citeable Phase 3 evidence**. Repo-specific claims must still cite exact "
    "handles from `planning-handles.md` that resolve through the citation "
    "manifest. It is derived **only** from this repository; no benchmark export "
    "seeds any topic, label, or claim.")


def _handle_summary(topic: CatalogTopic, limit: int = 6) -> str:
    """A compact one-line listing of a topic's candidate source handles."""
    parts: list = []
    for h in topic.candidate_source_handles[:limit]:
        if h.kind == "file" and h.path:
            parts.append(f"`{h.path}`")
        elif h.kind == "symbol" and h.symbol:
            parts.append(f"`{h.symbol}`")
        elif h.kind == "query_pack":
            parts.append("query-pack")
    more = len(topic.candidate_source_handles) - len(parts)
    line = ", ".join(parts) if parts else "_(no exact handles; see signals)_"
    if more > 0:
        line += f" (+{more} more)"
    return line


def _render_topic(topic: CatalogTopic, indent: str = "") -> list:
    L = [f"{indent}- **{topic.label}** (`{topic.topic_id}`) — "
         f"{topic.signal_strength} signal, priority `{topic.priority}`, "
         f"profile `{topic.suggested_page_profile}`"]
    L.append(f"{indent}  - Candidate sources: {_handle_summary(topic)}")
    if topic.expected_evidence_lanes:
        lanes = ", ".join(f"`{x}`" for x in topic.expected_evidence_lanes)
        L.append(f"{indent}  - Expected evidence lanes: {lanes}")
    if topic.known_gap_reason:
        L.append(f"{indent}  - Known gap: {topic.known_gap_reason}")
    return L


def render_catalog_markdown(catalog: TopicCatalog) -> str:
    """Render ``derived/planning-topic-catalog.md`` — the planner-facing catalog.

    Groups topics by family, lists candidate handles compactly, and separates
    weak/deferred topics so gaps stay visible. Always carries the loud
    non-citeable / benchmark-isolated warning."""
    parents = [t for t in catalog.topics if t.topic_kind == TOPIC_KIND_FAMILY]
    children_by_parent: dict = {}
    for t in catalog.topics:
        if t.topic_kind == TOPIC_KIND_SUBSYSTEM:
            children_by_parent.setdefault(t.parent_topic_id, []).append(t)

    strong = [p for p in parents
              if p.status in (STATUS_PRESENT, STATUS_SYNTHESIZED)]
    weak = [p for p in parents if p.status == STATUS_LOW]
    deferred = [p for p in parents if p.status == STATUS_MISSING]

    L: list = [
        "# Planning — DeepWiki Topic Catalog (Phase A, shadow mode)",
        "",
        "A deterministic, repository-derived catalog of candidate topics and "
        "subsystems for hierarchical page planning. Each parent topic is a "
        "mandatory DeepWiki family; child topics are source-derived subsystems "
        "(by leaf directory) under a high-signal family.",
        "",
        _NONCITEABLE_WARNING,
        "",
        "## Catalog summary",
        "",
        f"- Topics: **{catalog.topic_count}** "
        f"({catalog.family_count} families, {catalog.subsystem_count} subsystems).",
        f"- Strong/synthesized families: **{len(strong)}**; weak: {len(weak)}; "
        f"deferred (known gaps): {len(deferred)}.",
        f"- Source fingerprint: `{catalog.source_fingerprint}` "
        "(deterministic; timestamp-free).",
        "",
        "## Strong source-derived topics",
        "",
    ]
    if strong:
        for p in strong:
            L += _render_topic(p)
            for child in children_by_parent.get(p.topic_id, []):
                L += _render_topic(child, indent="  ")
    else:
        L.append("_No strong-signal families detected in this repository._")
    L += ["", "## Weak and deferred topics", "",
          "Weak families have thin Phase-1 signal; deferred families have none "
          "and are recorded as explicit known gaps rather than invented pages. "
          "Neither should be planned as a deep page without confirming source "
          "evidence.", ""]
    if weak:
        L += ["### Weak signal", ""]
        for p in weak:
            L += _render_topic(p)
        L.append("")
    if deferred:
        L += ["### Deferred (known gaps)", ""]
        for p in deferred:
            L += _render_topic(p)
        L.append("")
    if not weak and not deferred:
        L += ["_Every mandatory family has at least a strong or synthesized "
              "signal._", ""]
    L.append("_Deterministic Phase 1 output. Planner context only; never "
             "citeable evidence; benchmark-isolated._")
    return "\n".join(L) + "\n"
