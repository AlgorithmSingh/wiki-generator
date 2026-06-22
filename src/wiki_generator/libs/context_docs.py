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
