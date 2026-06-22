"""vector lane: semantic recall over rag/vectors.faiss (hybrid bundles only).

``vectors.py`` (Step 5) builds the index but exposes no query API, so we embed
the query with the *same* model2vec recipe, L2-normalize, and search the FAISS
inner-product index. The embedding backend is injectable so tests can exercise
the lane without faiss/model2vec installed.
"""
from __future__ import annotations

from ...util import clip
from ..loader import load_vector_metadata
from ..model import LaneResult, build_scores, chunk_hit
from ..query_text import build_query_text

LANE = "vector"
_MAX_SEQ_LENGTH = 512  # matches Step 5 BuildOptions.max_seq_length


class FaissModel2VecQueryBackend:
    """Default backend: embed with model2vec, search a FAISS IndexFlatIP."""

    def probe(self):
        try:
            import faiss  # noqa: F401
            import numpy  # noqa: F401
            from model2vec import StaticModel  # noqa: F401
            return True, None
        except Exception as e:  # pragma: no cover - env-dependent
            return False, f"vector backend unavailable: {e}"

    def query(self, index_path, query_text, *, model, k):
        import faiss
        import numpy as np
        from model2vec import StaticModel

        static = StaticModel.from_pretrained(model)
        v = np.asarray(static.encode([query_text], max_length=_MAX_SEQ_LENGTH),
                       dtype="float32")
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        q = (v / norms).astype("float32")
        index = faiss.read_index(index_path)
        distances, ordinals = index.search(q, k)
        return [(int(ordinals[0][j]), float(distances[0][j]))
                for j in range(len(ordinals[0])) if ordinals[0][j] != -1]


def run(bundle, section, options, backend=None) -> LaneResult:
    vmeta = (bundle.capabilities.get("indexes") or {}).get("vectors") or {}
    if not bundle.caps.get("vectors"):
        return LaneResult(lane=LANE, requested=0, resolved=0,
                          status="capability_disabled")

    backend = backend or FaissModel2VecQueryBackend()
    available, _reason = backend.probe()
    res = LaneResult(lane=LANE, requested=1, resolved=0)
    if not available:
        # Recall lane: degrade deterministically. The lane_summary 'unavailable'
        # status is the visible signal; we deliberately do NOT write the
        # environment-dependent backend error into unresolved-evidence.jsonl so
        # the sidecar stays byte-stable. The orchestrator records a fixed warning.
        res.status = "unavailable"
        return res

    query = build_query_text(section)
    if not query.strip():
        res.status = "empty"
        return res

    metadata = {r.get("ordinal"): r for r in
                load_vector_metadata(bundle.paths, vmeta.get("metadata_format"))}
    model = vmeta.get("model")
    results = backend.query(bundle.paths.vectors_faiss, query, model=model,
                            k=options.max_per_lane)
    query_label = clip(query, 200)
    for rank, (ordinal, score) in enumerate(results, 1):
        meta = metadata.get(ordinal)
        if meta is None:
            continue
        chunk = bundle.chunk(meta.get("chunk_id"))
        if chunk is None:
            continue
        rounded = round(float(score), 6)
        res.hits.append(chunk_hit(
            chunk, lane=LANE, confidence="medium", lane_rank=rank,
            provenance={"section_plan_field": "query_text", "input": query_label,
                        "matched_by": "vector", "ordinal": ordinal},
            scores=build_scores(lane_rank=rank, lane_score=rounded, vector=rounded)))

    res.resolved = 1 if res.hits else 0
    res.status = "pass" if res.hits else "empty"
    return res
