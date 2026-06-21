"""RunContext: the single object threaded through every lane.

It carries the resolved paths, detected tools, CLI options, and mutable
collectors (warnings, per-artifact counts, lane timings) that the pipeline reads
back when it writes ARTIFACT_GUIDE.md / run-metadata.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .paths import Paths
from .tools import Tools


@dataclass
class Options:
    embeddings: str = "auto"      # auto | on | off
    grep_ast: str = "auto"        # auto | on | off
    semgrep: str = "auto"         # auto | on | off
    ast_grep: str = "auto"        # auto | on | off
    pytest_collect: str = "auto"  # auto | on | off
    contracts_import: bool = False  # opt-in unsafe FastAPI app import (default off)
    rg_cap: int = 80              # max digested hits captured per query pack
    max_grep_ast_matches: int = 40  # max preview blocks per grep-ast pack


@dataclass
class RunContext:
    paths: Paths
    tools: Tools
    opts: Options
    git_meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=dict)        # artifact -> row count
    artifacts: list[dict] = field(default_factory=list)  # for artifact-index.md
    timings: dict = field(default_factory=dict)       # lane -> seconds

    @property
    def repo(self) -> str:
        return self.paths.repo

    @property
    def out(self) -> str:
        return self.paths.out

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def count(self, key: str, n: int) -> None:
        self.counts[key] = n

    def record(self, abspath: str, *, produced_by: str, description: str,
               rows: int | None = None, skipped: bool = False,
               note: str | None = None) -> None:
        """Register an artifact for derived/artifact-index.md and the guide."""
        self.artifacts.append({
            "path": self.paths.rel(abspath),
            "produced_by": produced_by,
            "description": description,
            "rows": rows,
            "skipped": skipped,
            "note": note,
        })


def artifact_table(artifacts: list[dict]) -> list[str]:
    """Render artifact records (the shape produced by :meth:`RunContext.record`)
    as a markdown table. Shared by the pipeline guide and the derived index so
    the two never drift. Returns header/separator/row lines (no trailing blank —
    callers add their own)."""
    out = ["| Artifact | Produced by | Rows | Notes |", "|---|---|---|---|"]
    for a in artifacts:
        rows = "—" if a.get("rows") is None else f"{a['rows']:,}"
        note = (a.get("note") or ("skipped" if a.get("skipped") else "")).replace("|", "\\|")
        out.append(f"| `{a['path']}` | {a['produced_by']} | {rows} | {note} |")
    return out
