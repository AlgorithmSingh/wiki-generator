"""Phase 2 Step 2: deterministic normalization of a planning LLM response.

Turns a raw Gemini/Kimi planning response into machine-resolvable plan artifacts
for Phase 3 retrieval, resolving references against the Phase 1 indexes. No LLM,
no network — only deterministic local reads/writes.

Facade:

    report = run(bundle_dir, raw_path, out_dir, strict=False, provider="gemini")
"""
from __future__ import annotations

import os

from ..util import read_text
from . import normalize as _normalize
from . import parse as _parse
from . import writer as _writer
from .lookups import Lookups
from .parse import ParseError

__all__ = ["run", "ParseError"]


def _source_rel(raw_path: str, bundle_dir: str) -> str:
    try:
        rel = os.path.relpath(raw_path, bundle_dir)
    except ValueError:
        return os.path.basename(raw_path)
    return rel if not rel.startswith("..") else os.path.basename(raw_path)


def run(bundle_dir: str, raw_path: str, out_dir: str, *, strict: bool = False,
        allow_unresolved: bool = True, provider: str | None = "gemini") -> dict:
    """Normalize ``raw_path`` against the Phase 1 bundle at ``bundle_dir`` and
    write the plan artifacts into ``out_dir``. Returns a report dict with the
    counts, strict verdict, and written file paths. Raises :class:`ParseError`
    if the raw response cannot be parsed unambiguously."""
    bundle_dir = os.path.abspath(os.path.expanduser(bundle_dir))
    raw_path = os.path.abspath(os.path.expanduser(raw_path))

    text = read_text(raw_path)
    if text is None:
        raise FileNotFoundError(f"raw response not readable: {raw_path}")

    raw = _parse.parse(text)
    lookups = Lookups.load(bundle_dir)
    result = _normalize.normalize(raw, lookups, _source_rel(raw_path, bundle_dir),
                                  provider)

    counts = result.counts
    strict_pass = (not strict) or counts["unresolved_total"] == 0
    written = _writer.write_all(out_dir, result, strict=strict,
                                strict_pass=strict_pass)

    return {
        "out_dir": written["out_dir"],
        "files": written["files"],
        "sections": counts["sections"],
        "unresolved_total": counts["unresolved_total"],
        "unresolved_by_type": counts["unresolved_by_type"],
        "strict": strict,
        "strict_pass": strict_pass,
        "warnings": len(result.warnings),
    }
