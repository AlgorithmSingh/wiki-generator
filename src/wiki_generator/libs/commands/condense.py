"""Step 2 command: write planning condensates into <bundle>/derived/.

Reads an existing decomposition bundle and writes the five planner-facing
markdown condensates. Each summarizer is isolated: one failing does not abort
the others.
"""
from __future__ import annotations

import argparse
import os

from ..coverage import build_topic_catalog, derive_coverage_signals
from ..digest import loader
from ..digest import planning_coverage_signals, planning_gaps, planning_graph
from ..digest import planning_handles, planning_runtime_surfaces
from ..digest import planning_symbols, planning_tests, planning_topic_catalog
from ..util import log, token_estimate, write_json, write_text

# condensate filename -> builder module. planning-handles.md leads so the exact
# retrieval handles sit at the front of the planner bundle (right after README).
# planning-coverage-signals.md and planning-topic-catalog.md trail: they are
# coverage maps over the families/subsystems the earlier condensates surfaced.
CONDENSATES = [
    ("planning-handles.md", planning_handles),
    ("planning-symbols.md", planning_symbols),
    ("planning-graph.md", planning_graph),
    ("planning-runtime-surfaces.md", planning_runtime_surfaces),
    ("planning-tests.md", planning_tests),
    ("planning-gaps.md", planning_gaps),
    ("planning-coverage-signals.md", planning_coverage_signals),
    ("planning-topic-catalog.md", planning_topic_catalog),
]


def write_condensates(bundle, derived_dir: str) -> list[tuple[str, int]]:
    """Build and write each condensate. Returns [(filename, tokens), ...].

    Also writes the machine-readable ``coverage-signals.json`` sidecar (planner
    CONTEXT, not citeable evidence) so tooling can consume the structured signals
    that back ``planning-coverage-signals.md``."""
    os.makedirs(derived_dir, exist_ok=True)
    written: list[tuple[str, int]] = []
    for name, mod in CONDENSATES:
        try:
            text = mod.build(bundle)
        except Exception as e:  # noqa: BLE001 - isolate one summarizer's failure
            log(f"condensate '{name}' FAILED: {e.__class__.__name__}: {e}")
            text = f"# {name}\n\n_generation failed: {e.__class__.__name__}: {e}_\n"
        path = os.path.join(derived_dir, name)
        write_text(path, text)
        toks = token_estimate(text)
        written.append((name, toks))
        log(f"  wrote derived/{name}  (~{toks:,} tokens)")

    # Machine-readable coverage-signals sidecar (isolated like the condensates).
    signals = None
    try:
        signals = derive_coverage_signals(bundle)
        write_json(os.path.join(derived_dir, "coverage-signals.json"),
                   signals.to_dict())
        log(f"  wrote derived/coverage-signals.json  "
            f"({signals.present_count} present, {signals.missing_count} missing "
            f"of {signals.family_count} families)")
    except Exception as e:  # noqa: BLE001 - sidecar failure must not abort condense
        log(f"coverage-signals.json FAILED: {e.__class__.__name__}: {e}")

    # Phase A: machine-readable topic-catalog sidecar (planner CONTEXT, never
    # citeable evidence; deterministic and benchmark-isolated). Isolated like the
    # condensates so a failure here never aborts the condense step.
    try:
        catalog = build_topic_catalog(bundle, signals)
        write_json(os.path.join(derived_dir, "topic-catalog.json"),
                   catalog.to_dict())
        log(f"  wrote derived/topic-catalog.json  "
            f"({catalog.topic_count} topics: {catalog.family_count} families, "
            f"{catalog.subsystem_count} subsystems, {catalog.deferred_count} "
            f"deferred)")
    except Exception as e:  # noqa: BLE001 - sidecar failure must not abort condense
        log(f"topic-catalog.json FAILED: {e.__class__.__name__}: {e}")
    return written


def run(args: argparse.Namespace) -> int:
    in_dir = os.path.abspath(os.path.expanduser(args.in_dir))
    bundle = loader.load_bundle(in_dir)
    log(f"condensing bundle: {in_dir}")
    written = write_condensates(bundle, os.path.join(in_dir, "derived"))
    total = sum(t for _, t in written)
    budget = getattr(args, "budget_tokens", 0)
    log(f"condensates total ~{total:,} tokens "
        f"(budget {budget:,}: {'ok' if total <= budget else 'over'})")
    return 0
