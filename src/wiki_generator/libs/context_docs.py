"""Shared notion of a *planner-context* document.

Digest/condensate docs (``derived/planning-*.md``, ``repo-summary.md`` …) help a
planner understand the repo but are NOT citeable repo evidence. Both the Phase 2
normalizer (which routes them to ``context_artifacts[]``) and the Phase 3
validator (which must never let one be cited as evidence) need the *same*
predicate, so it lives here and both import it — producer and checker cannot
drift.
"""
from __future__ import annotations

import os

# Basenames of digest/condensate docs that are planner context, not evidence.
CONTEXT_BASENAMES = frozenset({
    "planning-digest.md", "planning-symbols.md", "planning-graph.md",
    "planning-runtime-surfaces.md", "planning-tests.md", "planning-gaps.md",
    "planning-handles.md", "repo-summary.md", "artifact-index.md",
    "ARTIFACT_GUIDE.md", "README_FOR_PLANNER.md", "upload-list.md",
    "planner-upload-bundle.md",
})

# Bundle subtrees that only ever hold planner-context docs (never repo source).
CONTEXT_PREFIXES = ("derived/", "planner-digest/")


def _clean(ref) -> str:
    """Repo-relative path portion of ``ref`` (drops any ``:anchor``), POSIX."""
    text = ref if isinstance(ref, str) else str(ref)
    path = text.strip().split(":", 1)[0].strip()
    return path.replace("\\", "/")


def looks_like_context_artifact(ref) -> str | None:
    """Repo-relative path of the planner-context doc named by ``ref``, else None."""
    norm = _clean(ref)
    if not norm:
        return None
    if norm.startswith(CONTEXT_PREFIXES):
        return norm
    if os.path.basename(norm) in CONTEXT_BASENAMES:
        return norm
    return None


# The bundle's OWN generated context namespaces. Unlike CONTEXT_BASENAMES, these
# are safe to match against an evidence source path: a real repo source file is
# never emitted under ``derived/planning-`` or ``planner-digest/``, so matching
# them cannot false-positive a legitimate citation (a target repo could, however,
# legitimately contain a file merely *named* e.g. ``repo-summary.md``).
_GENERATED_CONTEXT_PREFIXES = ("derived/planning-", "planner-digest/")


def is_generated_context_path(ref) -> bool:
    """True if ``ref`` is one of the bundle's own generated planner-context docs.

    Used by the Phase 3 validator as a safe backstop against citing a context
    artifact as evidence — narrower than :func:`looks_like_context_artifact` so it
    never flags a real repo source file."""
    return _clean(ref).startswith(_GENERATED_CONTEXT_PREFIXES)


# --- Patch 3: internal planning *diagnostics* vs ordinary planner context ------
# A *diagnostic* artifact records what the pipeline skipped, approximated, or could
# not verify (``derived/planning-gaps.md``). Unlike the other condensates it is not
# even a useful neighbourhood description of repository behaviour — it is an
# inspector's punch list. A normal user-facing wiki section must never be backed
# *only* by such an artifact (Patch 3). This is a narrow, deterministic subset of
# the planner-context docs above; everything here is also a context artifact.
DIAGNOSTIC_BASENAMES = frozenset({"planning-gaps.md"})


def is_diagnostic_artifact(ref) -> str | None:
    """Repo-relative path of the planning *diagnostic* doc named by ``ref``, else
    None. A diagnostic doc is internal planning/provenance context (it summarises
    skipped/approximate/unverified analysis), never source evidence for a normal
    section. Deterministic; matches a known diagnostic basename (optionally under
    the bundle's generated ``derived/`` / ``planner-digest/`` namespaces)."""
    norm = _clean(ref)
    if not norm:
        return None
    if os.path.basename(norm) in DIAGNOSTIC_BASENAMES:
        return norm
    return None


# --- Patch 3: a section's role (normal source-evidence vs controlled provenance)-
# A normal wiki section ("source") must be backed by real retrieval signals. A
# section explicitly marked "provenance"/"meta" is a controlled provenance/meta
# note handled OUTSIDE the normal evidence lanes: it does not require source
# retrieval signals and Phase 3 must not retrieve generic source evidence for it.
SECTION_ROLE_SOURCE = "source"
SECTION_ROLE_PROVENANCE = "provenance"
_PROVENANCE_ROLES = frozenset({"provenance", "meta", "provenance_meta"})


def normalize_section_role(value) -> str:
    """Canonical section role from a raw planner ``role``/``kind`` value.

    Anything matching a known provenance/meta label becomes
    :data:`SECTION_ROLE_PROVENANCE`; everything else (including ``None``) is a
    normal source-evidence section."""
    if value is None:
        return SECTION_ROLE_SOURCE
    return (SECTION_ROLE_PROVENANCE
            if str(value).strip().casefold().replace("-", "_") in _PROVENANCE_ROLES
            else SECTION_ROLE_SOURCE)


def is_provenance_section(section: dict) -> bool:
    """True if ``section`` is a controlled provenance/meta section (handled outside
    the normal source-evidence lanes by readiness and Phase 3)."""
    return (section or {}).get("section_role") == SECTION_ROLE_PROVENANCE


def section_has_retrieval_signal(section: dict) -> bool:
    """True if a normalized ``section`` carries at least one deterministic
    retrieval directive.

    A retrieval signal is an exact handle (``symbols``/``files``/``contracts``/
    ``tests``/``graph_nodes``), a canonical ``query_pack``, or a ``search_hint``
    (BM25/vector recall text). Bare title/topic prose is NOT a signal: it only
    feeds generic recall that may match nothing. Shared by the Phase 2 readiness
    gate (producer) and the Phase 3 retriever (consumer) so the "does this section
    have a legitimate retrieval driver?" question is answered identically — a
    no-signal section must fail readiness and must never be rescued by generic
    BM25/vector fallback (Patch 3)."""
    needs = (section or {}).get("retrieval_needs") or {}
    if any(needs.get(k) for k in
           ("symbols", "files", "contracts", "tests", "graph_nodes")):
        return True
    return bool(needs.get("query_packs")) or bool(needs.get("search_hints"))
