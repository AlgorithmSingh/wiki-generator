"""The ``build-retrieval`` command contract: a frozen options value object.

Every knob the Step 5 substrate builder reads is an explicit field here. Nothing
is pulled from globals or the environment, so a run is fully determined by the
``BuildOptions`` passed in — which is also what makes the builder easy to drive
from a test without touching ``argv``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import config as C

#: Vector-metadata is written as one JSON document up to this many vectors, and
#: as line-delimited ``vector-metadata.jsonl`` beyond it (so the file stays
#: streamable for large corpora). Recorded in retrieval-capabilities.json.
METADATA_JSONL_THRESHOLD = 20_000

_MODES = ("auto", "on", "off")


@dataclass(frozen=True)
class BuildOptions:
    """Resolved configuration for one ``build-retrieval`` run."""

    bundle_root: str
    bm25_mode: str = "on"          # auto | on | off
    vectors_mode: str = "auto"     # auto | on | off
    embedding_model: str = C.EMBED_MODEL
    batch_size: int = 2048
    max_seq_length: int = 512
    rebuild: bool = False
    smoke_query: str | None = None
    metadata_jsonl_threshold: int = METADATA_JSONL_THRESHOLD

    def __post_init__(self) -> None:
        if self.bm25_mode not in _MODES:
            raise ValueError(f"bm25_mode must be one of {_MODES}: {self.bm25_mode!r}")
        if self.vectors_mode not in _MODES:
            raise ValueError(
                f"vectors_mode must be one of {_MODES}: {self.vectors_mode!r}")
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1: {self.batch_size}")
