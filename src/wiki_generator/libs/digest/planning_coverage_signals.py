"""Step 2 condensate: derived/planning-coverage-signals.md.

A thin digest-layer wrapper over :mod:`..coverage.signals`. It exposes the
``build(bundle) -> str`` contract the condensate machinery expects, rendering the
deterministic per-family DeepWiki coverage signals into the planner-facing
markdown digest.

The signals tell the Phase 2 planner WHERE each mandatory topic family likely
lives so it can plan hierarchical pages and tag canonical ``coverage_labels[]``.
They are deterministic, LLM-free, and **planner CONTEXT only** — never citeable
Phase 3 evidence. The machine-readable companion (``derived/coverage-signals.json``)
is written alongside by the ``condense`` command.
"""
from __future__ import annotations

from ..coverage import derive_coverage_signals, render_signals_markdown
from .loader import Bundle


def build(bundle: Bundle) -> str:
    return render_signals_markdown(derive_coverage_signals(bundle))
