"""Step 2 command: write planning condensates into <bundle>/derived/.

Reads an existing decomposition bundle and writes the five planner-facing
markdown condensates. Each summarizer is isolated: one failing does not abort
the others.
"""
from __future__ import annotations

import argparse
import os

from ..digest import loader
from ..digest import planning_gaps, planning_graph, planning_runtime_surfaces
from ..digest import planning_symbols, planning_tests
from ..util import log, token_estimate, write_text

# condensate filename -> builder module
CONDENSATES = [
    ("planning-symbols.md", planning_symbols),
    ("planning-graph.md", planning_graph),
    ("planning-runtime-surfaces.md", planning_runtime_surfaces),
    ("planning-tests.md", planning_tests),
    ("planning-gaps.md", planning_gaps),
]


def write_condensates(bundle, derived_dir: str) -> list[tuple[str, int]]:
    """Build and write each condensate. Returns [(filename, tokens), ...]."""
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
