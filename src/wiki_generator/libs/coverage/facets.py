"""Phase A: deterministic facet (subsystem) clustering inside a topic family.

A *facet* is a source-derived subsystem within one mandatory DeepWiki topic
family: the group of that family's candidate files that share a leaf directory.
For example, a ``doc-processing`` family whose candidate files live under both
``deepdoc/parser/`` and ``deepdoc/vision/`` yields two facets — the seed for two
child pages under a single parent ``doc-processing`` page.

This is the smallest deterministic decomposition the Phase-A topic catalog needs:
it turns the flat per-family file signal that :mod:`.signals` already produces
into a shallow parent/child hierarchy without any model call, embedding, or
network I/O. It does not decide *which* facets become pages or what evidence they
require — that is the catalog's job; this module only clusters.

Hard discipline (mirrors the rest of the pipeline):

- **Deterministic, LLM-free, network-free.** Pure grouping of the
  ``{path, category, reasons}`` candidate dicts that :func:`signals.family_candidates`
  returns. Identical input → identical output, with stable ordering and no
  timestamps, so the catalog built on top is byte-stable.
- **Planner CONTEXT, not evidence.** A facet tells the planner a subsystem
  *exists and where it lives*; it is never citeable Phase 3 evidence.
- **Repository-derived only.** Facets come exclusively from repository inventory
  rows; no benchmark material is read or referenced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..util import slug

# Bounds so the catalog stays compact regardless of repository size.
MAX_FACETS_PER_FAMILY = 12
MAX_PATHS_PER_FACET = 15

ROOT_DIRECTORY = "(root)"


@dataclass(frozen=True)
class Facet:
    """One source-derived subsystem inside a topic family.

    ``family_key``  the parent family's stable key (e.g. ``doc-processing``).
    ``facet_key``   stable, family-unique kebab-case slug (e.g. ``deepdoc-parser``).
    ``directory``   the leaf directory the facet's files share (``(root)`` allowed).
    ``label``       human-readable subsystem label for reports/diagnostics.
    ``file_count``  number of candidate files in the facet (uncapped count).
    ``paths``       the candidate file paths (sorted, capped to MAX_PATHS_PER_FACET).
    ``categories``  distinct inventory categories among the facet's files (sorted).
    ``reasons``     distinct detector reasons across the facet's files (sorted).
    """

    family_key: str
    facet_key: str
    directory: str
    label: str
    file_count: int
    paths: tuple = field(default_factory=tuple)
    categories: tuple = field(default_factory=tuple)
    reasons: tuple = field(default_factory=tuple)


def _leaf_dir(path: str) -> str:
    """The directory immediately containing ``path`` (``(root)`` for a top-level
    file). Path separators are normalised so detection is OS-independent."""
    norm = path.replace("\\", "/").strip("/")
    if "/" not in norm:
        return ROOT_DIRECTORY
    return norm.rsplit("/", 1)[0]


def _facet_key(directory: str, used: set) -> str:
    """A stable, family-unique slug for a facet's directory. Collisions (two
    distinct directories slugging to the same token) are broken deterministically
    by a numeric suffix so topic IDs built from facet keys never collide."""
    base = "root" if directory == ROOT_DIRECTORY else slug(directory)
    key = base
    n = 2
    while key in used:
        key = f"{base}-{n}"
        n += 1
    used.add(key)
    return key


def derive_family_facets(family_key: str, candidates: list) -> list:
    """Cluster a family's candidate files into deterministic subsystem facets.

    ``candidates`` is the uncapped ``{path, category, reasons}`` list from
    :func:`signals.family_candidates`. Files are grouped by leaf directory; the
    resulting facets are returned in directory order (stable), after capping the
    count to the largest MAX_FACETS_PER_FAMILY by file count. Each facet's paths
    are capped to MAX_PATHS_PER_FACET. Returns ``[]`` when the family has no
    candidate files (query-pack-only or symbol-only families have no facets)."""
    # Sort by path up front so grouping, paths, and facet keys are deterministic
    # regardless of the caller's candidate ordering.
    ordered = sorted(candidates, key=lambda c: str(c.get("path") or ""))
    groups: dict[str, list] = {}
    for c in ordered:
        path = str(c.get("path") or "")
        if not path:
            continue
        groups.setdefault(_leaf_dir(path), []).append(c)

    # Build one facet per leaf directory; iterate directories in sorted order so
    # facet_key assignment (and thus topic IDs) is fully deterministic.
    used_keys: set = set()
    facets: list = []
    for directory in sorted(groups):
        rows = groups[directory]
        paths = tuple(str(r.get("path") or "") for r in rows)
        categories = tuple(sorted({str(r.get("category") or "?") for r in rows}))
        reasons = tuple(sorted({rs for r in rows
                                for rs in (r.get("reasons") or [])}))
        facets.append(Facet(
            family_key=family_key,
            facet_key=_facet_key(directory, used_keys),
            directory=directory,
            label=directory,
            file_count=len(rows),
            paths=paths[:MAX_PATHS_PER_FACET],
            categories=categories,
            reasons=reasons))

    # Keep the most-populated subsystems when a family sprawls, then restore
    # directory order for stable output. Ties break on directory name.
    facets.sort(key=lambda f: (-f.file_count, f.directory))
    facets = facets[:MAX_FACETS_PER_FAMILY]
    facets.sort(key=lambda f: f.directory)
    return facets
