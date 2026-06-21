"""Deterministic reference resolution against the Phase 1 indexes.

``Lookups`` loads the raw decomposition artifacts (``inventory/files.jsonl``,
``symbols/symbols.jsonl``, ``queries/rules/rg/*.json``, ``contracts/openapi.json``,
``tests/test-files.jsonl``) once and answers the questions Phase 2 normalization
asks of them:

* ``resolve_query_pack`` — human title -> canonical query-pack key;
* ``resolve_symbol``     -> exact ``symbol_id`` / unique alias / unresolved+candidates;
* ``resolve_file``       -> verified path + anchor confidence / unresolved+candidates;
* ``resolve_contract``   -> ``METHOD /path`` against the derived OpenAPI;
* ``resolve_test``       -> test-file path.

It never guesses among multiple candidates: ambiguous references resolve to an
unresolved verdict carrying the sorted candidate list. No LLM, no network.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field


def _read_json(path: str):
    """Tolerant JSON read: returns None for missing/empty/malformed/unreadable
    files (an upstream artifact may be truncated; degrade rather than crash)."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: str):
    """Tolerant JSONL read: skips blank/malformed lines, never raises."""
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return rows
    return rows

# Canonical query-pack aliases (display form -> canonical key). Normalised with
# ``_norm`` at load, and only kept when the target pack actually exists.
_STATIC_QPACK_ALIASES = {
    "web routes": "web_routes", "routes": "web_routes", "api routes": "web_routes",
    "http routes": "web_routes", "rest api": "web_routes", "endpoints": "web_routes",
    "task workers": "task_workers", "tasks / workers": "task_workers",
    "tasks workers": "task_workers", "workers": "task_workers", "tasks": "task_workers",
    "background tasks": "task_workers", "job queues": "task_workers",
    "cli": "cli_commands", "cli commands": "cli_commands",
    "models": "models_schemas", "schemas": "models_schemas",
    "model/schema": "models_schemas", "models schemas": "models_schemas",
    "data models": "models_schemas",
    "config": "config_keys", "config keys": "config_keys",
    "config keys (code)": "config_keys", "configuration": "config_keys",
    "settings": "config_keys",
    "config file keys": "config_file_keys",
    "env": "env_vars", "env vars": "env_vars", "environment variables": "env_vars",
    "auth": "auth_security", "security": "auth_security",
    "auth / security": "auth_security", "auth security": "auth_security",
    "datastore": "datastore", "datastore / storage / cache": "datastore",
    "datastores": "datastore", "storage": "datastore", "cache": "datastore",
    "databases": "datastore",
    "llm integrations": "llm_integrations", "llm": "llm_integrations",
    "llm / ai provider integrations": "llm_integrations",
    "entry points": "entrypoints", "entrypoints": "entrypoints",
    "process entrypoints": "entrypoints",
    "plugins": "plugin_registries", "registries": "plugin_registries",
    "plugins / registries / factories": "plugin_registries",
    "factories": "plugin_registries",
}

_RANGE_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")
_METHOD_PATH_RE = re.compile(r"^([A-Za-z]+)\s+(/\S*)$")


def _norm(s: str) -> str:
    """Casefold; collapse runs of non-alphanumerics to a single ``_``; trim."""
    out = re.sub(r"[^0-9a-z]+", "_", s.casefold())
    return out.strip("_")


def _split_anchor(ref: str) -> tuple[str, str | None]:
    """Split ``path:anchor`` into ``(path, anchor)``. Anchor may be a line range
    (``120-145``), a single line (``120``) or free text (a heading hint)."""
    ref = ref.strip()
    if ":" not in ref:
        return ref, None
    head, _, tail = ref.partition(":")
    tail = tail.strip()
    return head.strip(), (tail or None)


@dataclass
class SymRes:
    input: str
    symbol_id: str | None
    resolution: str            # exact | unique_alias | ambiguous | no_match
    candidates: list[str] = field(default_factory=list)


@dataclass
class FileRes:
    input: str
    path: str | None
    anchor: str | None
    anchor_confidence: str | None   # exact_range | line_only | file_only | unresolved
    resolution: str                 # file_exists | unique_suffix | digest_artifact | ambiguous | no_match
    candidates: list[str] = field(default_factory=list)


class Lookups:
    def __init__(self, root: str):
        self.root = root
        self.repo_root = root
        self.repo_name = os.path.basename(root.rstrip("/")) or "repo"
        self.files: set[str] = set()
        self.line_counts: dict[str, int] = {}
        self._by_id: dict[str, dict] = {}
        self._sym_alias: dict[str, set[str]] = {}
        self.qpack_canonical: set[str] = set()
        self._qpack_alias: dict[str, str] = {}
        self._openapi_paths: dict[str, set[str]] = {}   # path -> {methods}
        self._test_files: set[str] = set()
        self._artifact_basenames: set[str] = set()

    # --- loading ---------------------------------------------------------------
    @classmethod
    def load(cls, root: str) -> "Lookups":
        root = os.path.abspath(os.path.expanduser(root))
        self = cls(root)

        def p(*parts: str) -> str:
            return os.path.join(root, *parts)

        cov = _read_json(p("inventory", "source-coverage.json"))
        if isinstance(cov, dict) and cov.get("repo_root"):
            self.repo_root = cov["repo_root"]
            self.repo_name = os.path.basename(str(cov["repo_root"]).rstrip("/")) or self.repo_name

        self._load_files(p("inventory", "files.jsonl"))
        self._load_symbols(p("symbols", "symbols.jsonl"))
        self._load_qpacks(p("queries", "rules", "rg"))
        self._load_openapi(p("contracts", "openapi.json"))
        self._load_tests(p("tests", "test-files.jsonl"))
        self._artifact_basenames = {
            "planning-digest.md", "planning-symbols.md", "planning-graph.md",
            "planning-runtime-surfaces.md", "planning-tests.md", "planning-gaps.md",
            "repo-summary.md", "artifact-index.md", "ARTIFACT_GUIDE.md",
            "source-coverage.json", "contract-sources.md", "openapi.json",
            "pytest-collect.txt", "README_FOR_PLANNER.md", "upload-list.md",
        }
        return self

    def _load_files(self, path: str) -> None:
        for row in _read_jsonl(path):
            fp = row.get("path")
            if not fp:
                continue
            self.files.add(fp)
            lc = row.get("line_count")
            if isinstance(lc, int) and lc > 0:
                self.line_counts[fp] = lc

    def _load_symbols(self, path: str) -> None:
        symbols = _read_jsonl(path)
        if not symbols:
            return
        id_to_name: dict[str, str] = {}
        for s in symbols:
            sid = s.get("symbol_id")
            if sid:
                self._by_id[sid] = s
                id_to_name[sid] = s.get("name") or ""
        alias: dict[str, set[str]] = defaultdict(set)
        for s in symbols:
            sid = s.get("symbol_id")
            if not sid:
                continue
            name = s.get("name") or ""
            module = s.get("module") or ""
            kind = s.get("kind") or ""
            sym_path = s.get("path") or ""
            start = (s.get("range") or {}).get("start_line")
            if name:
                alias[name].add(sid)
            if kind == "module":
                if module:
                    alias[module].add(sid)
            elif module and name:
                alias[f"{module}.{name}"].add(sid)
                parent = s.get("parent_symbol_id")
                pname = id_to_name.get(parent) if parent else None
                if pname and pname != name:
                    alias[f"{module}.{pname}.{name}"].add(sid)
            if sym_path and name:
                alias[f"{sym_path}:{name}"].add(sid)
            if sym_path and isinstance(start, int):
                alias[f"{sym_path}:{start}"].add(sid)
        self._sym_alias = dict(alias)

    def _load_qpacks(self, rules_dir: str) -> None:
        if not os.path.isdir(rules_dir):
            return
        for fn in sorted(os.listdir(rules_dir)):
            if not fn.endswith(".json"):
                continue
            d = _read_json(os.path.join(rules_dir, fn)) or {}
            stem = fn[:-5]
            name = d.get("name") or stem
            self.qpack_canonical.add(name)
            for a in (name, stem):
                self._qpack_alias.setdefault(_norm(a), name)
            why = d.get("why")
            if isinstance(why, str) and why.strip():
                self._qpack_alias.setdefault(_norm(why), name)
        for disp, key in _STATIC_QPACK_ALIASES.items():
            if key in self.qpack_canonical:
                self._qpack_alias.setdefault(_norm(disp), key)

    def _load_openapi(self, path: str) -> None:
        spec = _read_json(path)
        if not isinstance(spec, dict):
            return
        for route, ops in (spec.get("paths") or {}).items():
            if isinstance(ops, dict):
                methods = {m.upper() for m in ops.keys()
                           if m.lower() in ("get", "post", "put", "delete",
                                            "patch", "head", "options", "trace")}
                self._openapi_paths[route] = methods

    def _load_tests(self, path: str) -> None:
        for row in _read_jsonl(path):
            fp = row.get("path")
            if fp:
                self._test_files.add(fp)

    # --- resolvers -------------------------------------------------------------
    def resolve_query_pack(self, ref: str) -> str | None:
        ref = (ref or "").strip()
        if not ref:
            return None
        if ref in self.qpack_canonical:
            return ref
        return self._qpack_alias.get(_norm(ref))

    def resolve_symbol(self, ref: str) -> SymRes:
        ref = (ref or "").strip()
        if ref in self._by_id:
            return SymRes(ref, ref, "exact")
        hits = self._sym_alias.get(ref)
        if hits:
            if len(hits) == 1:
                return SymRes(ref, next(iter(hits)), "unique_alias")
            return SymRes(ref, None, "ambiguous", sorted(hits))
        return SymRes(ref, None, "no_match")

    def _resolve_digest_artifact(self, filepart: str) -> str | None:
        """Resolve a reference to a bundle artifact (digest/condensate/guide) to a
        path that actually exists on disk, or None. A bare basename (e.g.
        ``planning-digest.md``) is located under the bundle root, ``derived/`` or
        ``planner-digest/``. Never resolves on basename alone — the file must exist."""
        if filepart and os.path.isfile(os.path.join(self.root, filepart)):
            return filepart
        base = os.path.basename(filepart)
        if base in self._artifact_basenames:
            for prefix in ("derived", "planner-digest"):
                cand = f"{prefix}/{base}"
                if os.path.isfile(os.path.join(self.root, cand)):
                    return cand
        return None

    def _anchor_confidence(self, path: str | None, resolution: str,
                           anchor: str | None) -> str | None:
        if anchor is None:
            return None
        if resolution in ("no_match", "ambiguous") or path is None:
            return "unresolved"
        m = _RANGE_RE.match(anchor.strip())
        if not m:
            return "file_only"            # free-text heading hint
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        lc = self.line_counts.get(path)
        if lc is not None and not (1 <= start <= lc and 1 <= end <= lc and start <= end):
            return "file_only"            # invalid range for a known file
        return "exact_range" if end != start else "line_only"

    def resolve_file(self, ref: str) -> FileRes:
        filepart, anchor = _split_anchor(ref)
        if filepart in self.files:
            res, path, cands = "file_exists", filepart, []
        else:
            cands = sorted(p for p in self.files
                           if p.endswith("/" + filepart) or os.path.basename(p) == filepart)
            if len(cands) == 1:
                res, path = "unique_suffix", cands[0]
                cands = []
            elif len(cands) > 1:
                res, path = "ambiguous", None
                cands = cands[:25]
            else:
                artifact = self._resolve_digest_artifact(filepart)
                if artifact is not None:
                    res, path, cands = "digest_artifact", artifact, []
                else:
                    res, path, cands = "no_match", None, []
        conf = self._anchor_confidence(path, res, anchor)
        return FileRes(ref, path, anchor, conf, res, cands)

    def resolve_contract(self, ref) -> dict:
        text = ref if isinstance(ref, str) else str(ref)
        m = _METHOD_PATH_RE.match(text.strip())
        if m:
            method, route = m.group(1).upper(), m.group(2)
            if route in self._openapi_paths:
                if method in self._openapi_paths[route]:
                    return {"input": ref, "method": method, "path": route,
                            "resolution": "exact"}
                return {"input": ref, "method": None, "path": route,
                        "resolution": "path_only",
                        "methods": sorted(self._openapi_paths[route])}
            return {"input": ref, "method": method, "path": route,
                    "resolution": "no_match"}
        stripped = text.strip()
        if stripped in self._openapi_paths:
            return {"input": ref, "method": None, "path": stripped,
                    "resolution": "path_only",
                    "methods": sorted(self._openapi_paths[stripped])}
        return {"input": ref, "resolution": "hint"}

    def resolve_test(self, ref) -> dict:
        text = (ref if isinstance(ref, str) else str(ref)).strip()
        if text in self._test_files:
            return {"input": ref, "path": text, "resolution": "test_file"}
        cands = sorted(p for p in self._test_files
                       if p.endswith("/" + text) or os.path.basename(p) == text)
        if len(cands) == 1:
            return {"input": ref, "path": cands[0], "resolution": "unique_suffix"}
        if len(cands) > 1:
            return {"input": ref, "path": None, "resolution": "ambiguous",
                    "candidates": cands[:25]}
        if text in self.files:
            return {"input": ref, "path": text, "resolution": "file_exists"}
        return {"input": ref, "resolution": "hint"}
