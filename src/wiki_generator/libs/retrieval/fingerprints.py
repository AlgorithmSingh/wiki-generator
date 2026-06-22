"""Deterministic content fingerprints for stale-index detection.

A retrieval index (BM25 SQLite, FAISS vectors) is *stale* when the chunk corpus
it was built from no longer matches the chunks currently on disk. We never trust
file mtimes for this; instead we fingerprint the corpus by the stable, content-
addressed pair every chunk already carries: its ``chunk_id`` and the ``sha256``
of its text.

The same fingerprint is computed two ways and compared:

* from ``rag/chunks.jsonl`` (the current corpus), and
* from a built index that recorded those ``(chunk_id, sha256)`` pairs.

Keeping the algorithm in one place guarantees the two sides agree. The function
is pure (no IO, no globals) so it is trivially testable and order-independent.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

FINGERPRINT_PREFIX = "sha256:"


def _norm(value: object) -> str:
    """Normalize a field exactly as SQLite's ``COALESCE(col, '')`` does: only
    ``None`` (SQL NULL) becomes the empty string; every other value is stringified.

    This must match :func:`bm25.read_index_state`'s index-side normalization so the
    corpus fingerprint and the recorded index fingerprint agree (chunk_id/sha256
    are expected to be strings; this only guards the NULL/missing case)."""
    return "" if value is None else str(value)


def chunk_pairs(chunks: Iterable[dict]) -> list[tuple[str, str]]:
    """Extract ``(chunk_id, sha256)`` pairs from chunk records.

    A chunk missing its ``sha256`` contributes an empty hash so that adding,
    removing, or re-hashing a chunk all change the corpus fingerprint.
    """
    pairs: list[tuple[str, str]] = []
    for c in chunks:
        pairs.append((_norm(c.get("chunk_id")), _norm(c.get("sha256"))))
    return pairs


def fingerprint_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    """Fold ``(chunk_id, sha256)`` pairs into one order-independent digest.

    Pairs are sorted so the digest depends only on the *set* of chunks and their
    content, never on iteration order — two runs over the same corpus produce the
    same fingerprint.
    """
    h = hashlib.sha256()
    for cid, sha in sorted(pairs):
        h.update(cid.encode("utf-8", "replace"))
        h.update(b"\t")
        h.update(sha.encode("utf-8", "replace"))
        h.update(b"\n")
    return FINGERPRINT_PREFIX + h.hexdigest()


def corpus_fingerprint(chunks: Iterable[dict]) -> str:
    """Fingerprint a chunk corpus (the current ``rag/chunks.jsonl``)."""
    return fingerprint_pairs(chunk_pairs(chunks))


def is_stale(built_fingerprint: str | None, current_fingerprint: str) -> bool:
    """True when a recorded index fingerprint no longer matches the corpus."""
    if not built_fingerprint:
        return True
    return built_fingerprint != current_fingerprint
