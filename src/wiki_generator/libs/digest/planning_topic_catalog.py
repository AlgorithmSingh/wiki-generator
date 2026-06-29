"""Step 2 condensate: derived/planning-topic-catalog.md (Phase A, shadow mode).

A thin digest-layer wrapper over :mod:`..coverage.topic_catalog`. It exposes the
``build(bundle) -> str`` contract the condensate machinery expects, rendering the
deterministic repository-derived hierarchical topic catalog into the
planner-facing markdown.

The catalog tells the Phase 2 planner WHICH source-derived topics and subsystems
exist so it can plan a broader hierarchical wiki. It is deterministic, LLM-free,
benchmark-isolated, and **planner CONTEXT only** — never citeable Phase 3
evidence. The machine-readable companion (``derived/topic-catalog.json``) is
written alongside by the ``condense`` command.
"""
from __future__ import annotations

from ..coverage import build_topic_catalog, render_catalog_markdown
from .loader import Bundle


def build(bundle: Bundle) -> str:
    return render_catalog_markdown(build_topic_catalog(bundle))
