"""Load a Step 1 artifact bundle into memory for condensation.

The loader is the single seam between the raw bundle on disk and every
``planning_*`` summarizer. It reads the JSONL/JSON/markdown artifacts that the
decomposition pipeline produced, tolerates missing or empty files, and exposes
them as plain Python lists/dicts. Nothing here interprets the data — that is the
job of the summarizers — so the loader stays a thin, deep IO module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _read_json(path: str):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


@dataclass
class Bundle:
    """An in-memory view of a decomposition bundle."""

    root: str
    files: list[dict] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)
    imports: list[dict] = field(default_factory=list)
    occurrences: list[dict] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    rg_hits: list[dict] = field(default_factory=list)
    test_files: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    run_metadata: dict = field(default_factory=dict)
    openapi: dict = field(default_factory=dict)
    contract_sources: str | None = None
    pytest_collect: str | None = None
    repo_summary: str | None = None
    grep_ast: dict[str, str] = field(default_factory=dict)

    # --- convenience accessors -------------------------------------------------
    @property
    def warnings(self) -> list[str]:
        w = self.run_metadata.get("warnings")
        return list(w) if isinstance(w, list) else []

    @property
    def counts(self) -> dict:
        c = self.run_metadata.get("counts")
        return dict(c) if isinstance(c, dict) else {}

    @property
    def tools(self) -> dict:
        t = self.run_metadata.get("tools")
        if isinstance(t, dict):
            return t
        return self.coverage.get("tools", {}) if isinstance(self.coverage, dict) else {}

    def rel(self, abspath: str) -> str:
        try:
            return os.path.relpath(abspath, self.root)
        except ValueError:
            return abspath


def load_bundle(in_dir: str) -> Bundle:
    """Read every artifact a condensate may need. Missing files load as empty."""
    root = os.path.abspath(os.path.expanduser(in_dir))
    if not os.path.isdir(root):
        raise NotADirectoryError(f"not a bundle directory: {root}")

    def p(*parts: str) -> str:
        return os.path.join(root, *parts)

    grep_ast: dict[str, str] = {}
    ga_dir = p("queries", "results", "grep-ast")
    if os.path.isdir(ga_dir):
        for name in sorted(os.listdir(ga_dir)):
            if name.endswith(".md"):
                text = _read_text(os.path.join(ga_dir, name))
                if text is not None:
                    grep_ast[name[:-3]] = text

    return Bundle(
        root=root,
        files=_read_jsonl(p("inventory", "files.jsonl")),
        symbols=_read_jsonl(p("symbols", "symbols.jsonl")),
        imports=_read_jsonl(p("symbols", "imports.jsonl")),
        occurrences=_read_jsonl(p("symbols", "occurrences.jsonl")),
        nodes=_read_jsonl(p("static", "nodes.jsonl")),
        edges=_read_jsonl(p("static", "edges.jsonl")),
        rg_hits=_read_jsonl(p("queries", "results", "rg.jsonl")),
        test_files=_read_jsonl(p("tests", "test-files.jsonl")),
        coverage=_read_json(p("inventory", "source-coverage.json")) or {},
        run_metadata=_read_json(p("run-metadata.json")) or {},
        openapi=_read_json(p("contracts", "openapi.json")) or {},
        contract_sources=_read_text(p("contracts", "contract-sources.md")),
        pytest_collect=_read_text(p("tests", "pytest-collect.txt")),
        repo_summary=_read_text(p("derived", "repo-summary.md")),
        grep_ast=grep_ast,
    )
