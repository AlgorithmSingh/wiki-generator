"""Phase 1 decomposition.

Turns a Python repository directory into a deterministic *repo-analysis artifact
bundle* of standard / standard-adjacent artifacts (inventory, symbols, RAG/BM25,
static graph, query packs, contracts, tests, derived summaries).

No LLM calls happen here. Later phases consume the bundle described by the
top-level ``ARTIFACT_GUIDE.md``.

Run:

    python -m phase1_decomposition decompose --repo <repo> --out <out>
"""
from __future__ import annotations

__version__ = "0.1.0"

# Bumped when an artifact schema changes in a non-backward-compatible way.
SCHEMA_VERSION = "1"

# Identifies the producer in ARTIFACT_GUIDE.md / run-metadata.json.
GENERATOR = f"phase1_decomposition v{__version__} (schema {SCHEMA_VERSION})"
