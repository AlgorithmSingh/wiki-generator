"""Contracts lane — framework-native interface contracts where available.

Strategy (safe by default):
  1. Statically discover existing OpenAPI/Swagger/AsyncAPI specs in the repo.
  2. Otherwise, derive a conservative OpenAPI skeleton from AST-detected routes.
  3. Only with --contracts-import (off by default) do we import app code to ask a
     live framework for its schema.

Artifacts:
  contracts/openapi.json        discovered, derived, or imported spec
  contracts/contract-sources.md  what was found and exactly how it was produced
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

from .. import config as C
from ..context import RunContext
from ..tools import run as run_cmd
from ..util import read_text, write_json, write_text, log

_SPEC_NAMES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json",
               "swagger.yaml", "swagger.yml", "asyncapi.yaml", "asyncapi.json")


def _looks_like_spec(rec) -> bool:
    nl = rec["name"].lower()
    if nl in _SPEC_NAMES or nl.endswith(".openapi.json") or nl.endswith(".openapi.yaml"):
        return True
    if "openapi" in rec["path"].lower() or "swagger" in rec["path"].lower():
        return rec["ext"] in {".json", ".yaml", ".yml"}
    return False


def _load_spec(path: str) -> dict | None:
    txt = read_text(path, C.MAX_FILE_BYTES_FOR_TEXT)
    if not txt:
        return None
    if path.endswith(".json"):
        try:
            return json.loads(txt)
        except ValueError:
            return None
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(txt)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _discover(ctx: RunContext, inv: dict) -> list[dict]:
    found = []
    for rec in inv["files"]:
        if rec["category"] in {"vendor", "generated"} or rec["is_binary"]:
            continue
        candidate = _looks_like_spec(rec)
        if not candidate and rec["ext"] in {".json", ".yaml", ".yml"} \
                and rec["size_bytes"] <= 400_000:
            head = read_text(os.path.join(ctx.repo, rec["path"])) or ""
            head = head[:4000].lower()
            candidate = ('"openapi"' in head or "openapi:" in head
                         or '"swagger"' in head or "swagger:" in head)
        if not candidate:
            continue
        data = _load_spec(os.path.join(ctx.repo, rec["path"]))
        if not isinstance(data, dict):
            continue
        version = data.get("openapi") or data.get("swagger") or data.get("asyncapi")
        if not version:
            continue
        found.append({"path": rec["path"], "version": str(version),
                      "kind": "openapi" if data.get("openapi") else
                              ("swagger" if data.get("swagger") else "asyncapi"),
                      "path_count": len(data.get("paths", {}) or {}), "data": data})
    found.sort(key=lambda f: (-f["path_count"], f["path"]))
    return found


def _derive_from_routes(ctx: RunContext, routes: list[dict], repo_name: str) -> dict:
    paths: dict[str, dict] = defaultdict(dict)
    frameworks = set()
    for r in routes:
        frameworks.add(r.get("framework", "unknown"))
        for method in r.get("methods", ["GET"]):
            m = method.lower()
            if m in ("websocket", "*"):
                # method unknown (Django path()/re_path()) or non-HTTP (websocket):
                # record at the path-item level so the path still appears.
                paths[r["path"]].setdefault("x-source", f"{r.get('path_file')}:{r.get('lineno')}")
                paths[r["path"]]["x-handler"] = r.get("handler")
                paths[r["path"]]["x-methods"] = "unknown" if m == "*" else "websocket"
                continue
            op = {
                "operationId": r.get("handler"),
                "summary": f"{r.get('handler')} ({r.get('framework')})",
                "x-handler-symbol-id": r.get("handler_symbol_id"),
                "x-source": f"{r.get('path_file')}:{r.get('lineno')}",
                "responses": {"default": {
                    "description": "(undocumented; derived from route decorator)"}},
            }
            if r.get("router_prefix"):
                op["x-router-prefix"] = r["router_prefix"]
            paths[r["path"]][m] = op
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{repo_name} (derived)",
            "version": "0.0.0",
            "description": "Derived statically from route decorators by "
                           "phase1_decomposition. NOT authoritative — no app code "
                           "was executed; request/response schemas are unknown.",
        },
        "x-derived-by": "phase1_decomposition static route analysis",
        "x-frameworks": sorted(frameworks),
        "paths": dict(sorted(paths.items())),
    }


def _import_openapi(ctx: RunContext, routes: list[dict]) -> dict | None:
    """UNSAFE opt-in: import the app in a subprocess and ask for .openapi()."""
    candidates = sorted({r["path_file"] for r in routes if r.get("path_file")})
    script = r'''
import importlib.util, json, sys, os
repo = sys.argv[1]
sys.path.insert(0, repo)
for rel in sys.argv[2:]:
    mod_path = os.path.join(repo, rel)
    name = "p1_contract_probe"
    try:
        spec = importlib.util.spec_from_file_location(name, mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        continue
    for attr in dir(mod):
        obj = getattr(mod, attr, None)
        fn = getattr(obj, "openapi", None)
        if callable(fn):
            try:
                doc = fn()
                if isinstance(doc, dict) and doc.get("openapi"):
                    print(json.dumps(doc)); sys.exit(0)
            except Exception:
                pass
sys.exit(3)
'''
    proc = run_cmd([sys.executable, "-c", script, ctx.repo, *candidates[:25]], timeout=120)
    if proc is None or proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def build(ctx: RunContext, inv: dict, sym: dict) -> dict:
    routes = sym.get("routes", [])
    repo_name = os.path.basename(ctx.repo.rstrip("/")) or "repo"
    discovered = _discover(ctx, inv)
    method = None
    spec = None
    imported = False

    if ctx.opts.contracts_import and routes:
        spec = _import_openapi(ctx, routes)
        if spec is not None:
            method = "imported"
            imported = True
        else:
            ctx.warn("--contracts-import: could not import app to extract OpenAPI; "
                     "falling back to discovery/derivation.")

    if spec is None and discovered:
        spec = discovered[0]["data"]
        method = "discovered"
    if spec is None:
        spec = _derive_from_routes(ctx, routes, repo_name)
        method = "derived"

    write_json(ctx.paths.openapi_json, spec)
    path_count = len(spec.get("paths", {}) or {})
    ctx.count("contracts/openapi.json", path_count)
    ctx.record(ctx.paths.openapi_json, produced_by=f"contracts ({method})",
               description=f"OpenAPI spec ({method}); {path_count} paths",
               rows=path_count,
               note=None if method == "discovered" else f"{method} (not authoritative)")

    # contract-sources.md
    L = ["# Contract sources", ""]
    L.append(f"OpenAPI spec written to `contracts/openapi.json` via **{method}**.")
    L.append("")
    L.append("## Method")
    L.append("")
    if method == "discovered":
        L.append("An existing API specification was found in the repository and "
                 "copied verbatim (converted to JSON if it was YAML). No code ran.")
    elif method == "derived":
        L.append("No existing spec was found. A conservative OpenAPI 3.1 skeleton was "
                 "**derived statically** from route decorators detected by the Python "
                 "AST. No application code was imported or executed. Request/response "
                 "schemas are unknown; only paths, methods, and handler anchors are "
                 "recorded (`x-source`, `x-handler-symbol-id`).")
    else:
        L.append("The application was imported in a subprocess (`--contracts-import`) "
                 "and its live `.openapi()` schema captured. This executes repository "
                 "code and is off by default.")
    L.append("")
    L.append("## Discovered specification files")
    L.append("")
    if discovered:
        L.append("| File | Kind | Version | Paths |")
        L.append("|---|---|---|---|")
        for d in discovered:
            L.append(f"| `{d['path']}` | {d['kind']} | {d['version']} | {d['path_count']} |")
    else:
        L.append("- None found by static discovery.")
    L.append("")
    L.append("## Routes detected by AST")
    L.append("")
    if routes:
        frameworks = sorted({r.get("framework", "unknown") for r in routes})
        L.append(f"- {len(routes)} route(s) across frameworks: {', '.join(frameworks)}")
        L.append("")
        L.append("| Methods | Path | Handler | Source |")
        L.append("|---|---|---|---|")
        for r in sorted(routes, key=lambda x: (x.get("path_file", ""), x.get("lineno", 0)))[:200]:
            methods = ",".join(r.get("methods", []))
            L.append(f"| {methods} | `{r['path']}` | `{r.get('handler')}` | "
                     f"`{r.get('path_file')}:{r.get('lineno')}` |")
    else:
        L.append("- No route decorators detected (the repo may not be a web service, "
                 "or it uses an unrecognized routing style).")
    L.append("")
    L.append("## Safety")
    L.append("")
    L.append(f"- App code imported: **{'yes' if imported else 'no'}**.")
    L.append("- No servers were started.")
    write_text(ctx.paths.contract_sources, "\n".join(L) + "\n")
    ctx.record(ctx.paths.contract_sources, produced_by="contracts",
               description="how the contract was produced + discovered specs + routes")

    log(f"contracts: method={method}, {path_count} paths, {len(routes)} routes, "
        f"{len(discovered)} discovered specs")
    return {"method": method, "paths": path_count, "routes": len(routes),
            "discovered": len(discovered)}
