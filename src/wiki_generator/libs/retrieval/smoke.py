"""Optional post-build smoke queries.

When ``--smoke-query TEXT`` is given, run the query against the freshly built
lexical index and record the top hits to ``rag/retrieval-smoke-tests.jsonl``.
This is a sanity probe — proof the substrate answers a real query — not Phase 3
evidence retrieval. Results are deterministic (BM25 scores are content-determined
and ties break on ``chunk_id``), so reruns produce identical output.
"""
from __future__ import annotations

from ..util import write_jsonl
from . import bm25
from .loader import Corpus

DEFAULT_K = 5


def run_smoke(corpus: Corpus, query: str, *, bm25_enabled: bool,
              k: int = DEFAULT_K) -> list[dict]:
    """Run the smoke query and return the recorded result rows (also written)."""
    results: list[dict] = []
    if bm25_enabled:
        hits = bm25.search(corpus.paths.bm25_sqlite, query, k=k)
        results.append({
            "mode": "bm25",
            "query": query,
            "hit_count": len(hits),
            "hits": [{
                "chunk_id": h.chunk_id,
                "path": h.path,
                "range": {"start_line": h.start_line, "end_line": h.end_line},
                "span_ids": h.span_ids,
                "score": h.score,
            } for h in hits],
        })
    write_jsonl(corpus.paths.retrieval_smoke, results)
    return results
