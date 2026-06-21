"""Static analysis graph lane — code relationships as a portable property graph.

Artifacts:
  static/nodes.jsonl   Repository/File/Module/Class/Function/Method/Dependency/
                       Test/ConfigFile/DocSection
  static/edges.jsonl   CONTAINS / IMPORTS / CALLS_APPROX / INHERITS /
                       DECORATED_BY / MENTIONS / TESTS_APPROX

Edges carry ``confidence`` (high/medium/low) and ``basis`` (observed/inferred);
approximate edges (calls, mentions, tests) are explicitly low/medium confidence.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

from .. import config as C
from .. import ids
from ..context import RunContext
from ..util import read_text, write_jsonl, log

_STDLIB = set(getattr(sys, "stdlib_module_names", set()))
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _decorator_root(expr: str) -> str:
    """`app.route` / `pytest.fixture(...)` -> root identifier (`app`,`pytest`)."""
    expr = expr.strip().lstrip("@")
    expr = expr.split("(")[0]
    return expr.split(".")[0].split("[")[0]


def _base_last(expr: str) -> str:
    return expr.split("(")[0].split("[")[0].strip().split(".")[-1]


def build(ctx: RunContext, inv: dict, sym: dict, rg_data) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    edge_keys: set[str] = set()

    def add_node(nid, ntype, **attrs):
        if nid not in nodes:
            nodes[nid] = {"node_id": nid, "type": ntype, **attrs}

    def add_edge(src, etype, dst, *, confidence, basis, provenance=None, extra=""):
        eid = ids.edge_id(src, etype, dst, extra=extra)
        if eid in edge_keys:
            return
        edge_keys.add(eid)
        e = {"edge_id": eid, "type": etype, "src": src, "dst": dst,
             "confidence": confidence, "basis": basis}
        if provenance:
            e["provenance"] = provenance
        edges.append(e)

    repo_name = (ctx.git_meta.get("remote", "").rstrip("/").split("/")[-1]
                 or os.path.basename(ctx.repo.rstrip("/")) or "repo")
    repo_name = repo_name.removesuffix(".git")
    repo_id = ids.repo_node_id(repo_name)
    add_node(repo_id, "Repository", name=repo_name, path=ctx.repo)

    # --- File / ConfigFile / Test nodes + Repo CONTAINS File -------------------
    file_node_type = {}
    for r in inv["files"]:
        if not (r["indexable"] or r["category"] in {"deployment", "config", "docs"}):
            continue
        cat = r["category"]
        if cat == "test":
            ntype = "Test"
        elif cat in {"config", "deployment"}:
            ntype = "ConfigFile"
        else:
            ntype = "File"
        file_node_type[r["path"]] = ntype
        fid = ids.file_node_id(r["path"])
        add_node(fid, ntype, name=r["name"], path=r["path"],
                 language=r["language"], category=cat)
        add_edge(repo_id, "CONTAINS", fid, confidence="high", basis="observed")

    # --- Module nodes + File CONTAINS Module -----------------------------------
    # Only modules that symbols.jsonl actually materialized as a kind=module row
    # get a node, so the two artifacts agree (empty/whitespace .py files have no
    # module symbol row — see symbols.build — and therefore no Module node).
    modules = sym.get("modules", {})
    materialized_modules = {s["symbol_id"] for s in sym.get("symbols", [])
                            if s["kind"] == "module"}
    module_of_path = {}
    for path, parser in modules.items():
        if getattr(parser, "error", None):
            continue
        if ids.module_symbol_id(parser.module) not in materialized_modules:
            continue
        mid = ids.module_node_id(parser.module)
        module_of_path[path] = mid
        add_node(mid, "Module", name=parser.module, path=path, language="python")
        fid = ids.file_node_id(path)
        if fid in nodes:
            add_edge(fid, "CONTAINS", mid, confidence="high", basis="observed")

    # --- Symbol nodes (Class/Function/Method) + CONTAINS hierarchy -------------
    symbols = sym.get("symbols", [])
    sym_by_id = {s["symbol_id"]: s for s in symbols}
    class_name_to_ids: dict[str, list[str]] = {}
    name_to_ids: dict[str, list[str]] = {}
    for s in symbols:
        if s["kind"] == "module":
            continue  # the module's node is created in the modules loop above
        ntype = {"class": "Class", "function": "Function", "method": "Method"}[s["kind"]]
        nid = ids.symbol_node_id(s["symbol_id"])
        add_node(nid, ntype, name=s["name"], path=s["path"], symbol_id=s["symbol_id"],
                 module=s["module"], range=s["range"], signature=s.get("signature"))
        name_to_ids.setdefault(s["name"], []).append(s["symbol_id"])
        if s["kind"] == "class":
            class_name_to_ids.setdefault(s["name"], []).append(s["symbol_id"])
        # CONTAINS from parent (module or class)
        parent = s["parent_symbol_id"]
        if parent and parent.endswith("/"):       # module-level
            mid = ids.module_node_id(s["module"])
            if mid in nodes:
                add_edge(mid, "CONTAINS", nid, confidence="high", basis="observed")
        elif parent in sym_by_id:
            add_edge(ids.symbol_node_id(parent), "CONTAINS", nid,
                     confidence="high", basis="observed")

    # --- Dependency nodes + Module IMPORTS Dependency --------------------------
    deps: Counter = Counter()
    # (file path, imported alias) -> external root package, for resolving the
    # origin of external base classes / decorators below.
    ext_name_by_path: dict[str, dict[str, str]] = {}
    for imp in sym.get("imports", []):
        if imp["is_internal"]:
            continue
        roots = []
        amap = ext_name_by_path.setdefault(imp["path"], {})
        if imp["kind"] == "import":
            for n in imp["names"]:
                root = n["name"].split(".")[0]
                roots.append(root)
                amap[(n["asname"] or n["name"]).split(".")[0]] = root
        elif imp["kind"] == "from" and imp.get("level", 0) == 0 and imp.get("module"):
            root = imp["module"].split(".")[0]
            roots.append(root)
            for n in imp["names"]:
                amap[n["asname"] or n["name"]] = root
        mid = module_of_path.get(imp["path"])
        for root in roots:
            if not root:
                continue
            deps[root] += 1
            did = ids.dependency_node_id(root)
            add_node(did, "Dependency", name=root, stdlib=root in _STDLIB)
            if mid:
                add_edge(mid, "IMPORTS", did, confidence="medium", basis="observed",
                         provenance={"lineno": imp["lineno"]}, extra=str(imp["lineno"]))

    # --- File IMPORTS File (internal) ------------------------------------------
    for imp in sym.get("imports", []):
        if not imp["is_internal"] or not imp.get("resolved_path"):
            continue
        src = ids.file_node_id(imp["path"])
        dst = ids.file_node_id(imp["resolved_path"])
        if src in nodes and dst in nodes and src != dst:
            add_edge(src, "IMPORTS", dst, confidence="high", basis="observed",
                     provenance={"lineno": imp["lineno"]})

    # --- CALLS_APPROX ----------------------------------------------------------
    for ce in sym.get("calls_edges", []):
        s_id = sym_by_id.get(ce["from_symbol_id"])
        t_id = sym_by_id.get(ce["to_symbol_id"])
        if not s_id or not t_id:
            continue
        add_edge(ids.symbol_node_id(ce["from_symbol_id"]), "CALLS_APPROX",
                 ids.symbol_node_id(ce["to_symbol_id"]),
                 confidence=ce["confidence"], basis="inferred",
                 provenance={"path": ce["path"], "lineno": ce["line"]},
                 extra=str(ce["line"]))

    # --- INHERITS --------------------------------------------------------------
    for s in symbols:
        if s["kind"] != "class":
            continue
        src = ids.symbol_node_id(s["symbol_id"])
        fmap = ext_name_by_path.get(s["path"], {})
        for base in s.get("bases", []):
            last = _base_last(base)
            cands = class_name_to_ids.get(last, [])
            if len(cands) == 1:
                add_edge(src, "INHERITS", ids.symbol_node_id(cands[0]),
                         confidence="medium", basis="inferred",
                         provenance={"base": base})
                continue
            # external base: resolve via this file's imported names, else by root.
            root = fmap.get(last) or fmap.get(_decorator_root(base)) or _decorator_root(base)
            did = ids.dependency_node_id(root)
            if did in nodes:
                add_edge(src, "INHERITS", did, confidence="low", basis="inferred",
                         provenance={"base": base})

    # --- DECORATED_BY ----------------------------------------------------------
    for s in symbols:
        src = ids.symbol_node_id(s["symbol_id"])
        fmap = ext_name_by_path.get(s["path"], {})
        for dec in s.get("decorators", []):
            root = _decorator_root(dec)
            internal = name_to_ids.get(root, [])
            if len(internal) == 1:
                add_edge(src, "DECORATED_BY", ids.symbol_node_id(internal[0]),
                         confidence="low", basis="inferred", provenance={"decorator": dec})
            else:
                did = ids.dependency_node_id(fmap.get(root, root))
                if did in nodes:
                    add_edge(src, "DECORATED_BY", did, confidence="low",
                             basis="inferred", provenance={"decorator": dec})

    # --- DocSection nodes + MENTIONS -------------------------------------------
    meaningful = {n for n, lst in name_to_ids.items() if len(n) > 3}
    doc_sections = 0
    for r in inv["files"]:
        if r["category"] != "docs" or r["language"] not in {"markdown", "rst"}:
            continue
        if r["line_count"] == 0:
            continue
        text = read_text(os.path.join(ctx.repo, r["path"]), C.MAX_FILE_BYTES_FOR_TEXT)
        if not text:
            continue
        fid = ids.file_node_id(r["path"])
        for i, ln in enumerate(text.split("\n")):
            m = _HEADING.match(ln)
            if not m:
                continue
            title = m.group(2).strip()
            sec_id = f"doc:{r['path']}#{i + 1}"
            add_node(sec_id, "DocSection", name=title, path=r["path"],
                     range={"start_line": i + 1, "end_line": i + 1})
            doc_sections += 1
            if fid in nodes:
                add_edge(fid, "CONTAINS", sec_id, confidence="high", basis="observed")
            for w in sorted(set(_WORD.findall(title))):
                if w in meaningful and len(name_to_ids[w]) == 1:
                    add_edge(sec_id, "MENTIONS", ids.symbol_node_id(name_to_ids[w][0]),
                             confidence="low", basis="inferred")

    # --- TESTS_APPROX ----------------------------------------------------------
    for s in symbols:
        if s["kind"] not in {"function", "method"} or not s["name"].startswith("test_"):
            continue
        target = s["name"][len("test_"):]
        cands = name_to_ids.get(target, [])
        if len(cands) == 1 and cands[0] != s["symbol_id"]:
            add_edge(ids.symbol_node_id(s["symbol_id"]), "TESTS_APPROX",
                     ids.symbol_node_id(cands[0]), confidence="low", basis="inferred")

    # --- write -----------------------------------------------------------------
    node_rows = list(nodes.values())
    n_nodes = write_jsonl(ctx.paths.nodes_jsonl, node_rows)
    n_edges = write_jsonl(ctx.paths.edges_jsonl, edges)
    ctx.count("static/nodes.jsonl", n_nodes)
    ctx.count("static/edges.jsonl", n_edges)
    node_types = dict(Counter(n["type"] for n in node_rows).most_common())
    edge_types = dict(Counter(e["type"] for e in edges).most_common())
    ctx.record(ctx.paths.nodes_jsonl, produced_by="python ast",
               description=f"graph nodes ({', '.join(f'{k}:{v}' for k, v in node_types.items())})",
               rows=n_nodes)
    ctx.record(ctx.paths.edges_jsonl, produced_by="python ast",
               description=f"graph edges ({', '.join(f'{k}:{v}' for k, v in edge_types.items())})",
               rows=n_edges, note="CALLS_APPROX/MENTIONS/TESTS_APPROX are approximate")
    log(f"static: {n_nodes} nodes {node_types}, {n_edges} edges {edge_types}")
    return {"nodes": n_nodes, "edges": n_edges, "node_types": node_types,
            "edge_types": edge_types, "deps": dict(deps.most_common())}
