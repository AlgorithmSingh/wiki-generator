"""Step 2: derived/planning-graph.md — condensed static-graph summary.

Replaces ``static/nodes.jsonl`` + ``static/edges.jsonl`` with degree rankings,
hub tables, and simple path-prefix clusters. Call edges are approximate; the
approximation warnings are preserved verbatim.
"""
from __future__ import annotations

from collections import Counter

from . import ranking as R
from .loader import Bundle

TOP_N = 25


_PATH_NODE_TYPES = ("File", "Module", "ConfigFile", "DocSection")


def _node_label(nodes_by_id: dict, node_id: str) -> str:
    """Unambiguous label: file-like nodes show their path; symbol nodes show
    name+path (so two functions with the same path stay distinct); every label
    carries its node type."""
    n = nodes_by_id.get(node_id)
    if not n:
        return node_id
    t = n.get("type") or "?"
    name = n.get("name")
    path = n.get("path")
    if t in _PATH_NODE_TYPES:
        return f"{path or name or node_id} [{t}]"
    if name and path:
        return f"{name} ({path}) [{t}]"
    return f"{name or path or node_id} [{t}]"


def _path_prefix(path: str) -> str:
    parts = str(path).split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def build(bundle: Bundle) -> str:
    nodes = bundle.nodes
    edges = bundle.edges
    nodes_by_id = {n.get("node_id"): n for n in nodes}

    L: list[str] = []
    L += R.heading(1, "Planning — Static Graph")
    L.append("Condensed from `static/nodes.jsonl` + `static/edges.jsonl`. "
             "Degree rankings and hubs; not the full graph. "
             "**Call edges (`CALLS_APPROX`) are heuristic and may be incomplete.**")
    L.append("")

    # Node / edge type counts
    L += R.heading(2, "Node counts by type")
    L += R.md_table(["type", "count"],
                    [[k, f"{v:,}"] for k, v in R.top(R.count_by(nodes, lambda n: n.get("type")), 30)])
    L += R.heading(2, "Edge counts by type")
    L += R.md_table(["type", "count"],
                    [[k, f"{v:,}"] for k, v in R.top(R.count_by(edges, lambda e: e.get("type")), 30)])

    # Degree counts
    out_deg: Counter = Counter()
    in_deg: Counter = Counter()
    for e in edges:
        src, dst = e.get("src"), e.get("dst")
        if src:
            out_deg[src] += 1
        if dst:
            in_deg[dst] += 1
    total_deg: Counter = Counter()
    for k, v in out_deg.items():
        total_deg[k] += v
    for k, v in in_deg.items():
        total_deg[k] += v

    def deg_rows(counter: Counter) -> list[list]:
        return [[_node_label(nodes_by_id, nid), f"{cnt:,}"]
                for nid, cnt in R.top(counter, TOP_N)]

    L += R.heading(2, "Top nodes by total degree")
    L += R.md_table(["node", "degree"], deg_rows(total_deg))
    L += R.heading(2, "Top nodes by incoming edges (most depended-on)")
    L += R.md_table(["node", "in-degree"], deg_rows(in_deg))
    L += R.heading(2, "Top nodes by outgoing edges (most dependent)")
    L += R.md_table(["node", "out-degree"], deg_rows(out_deg))

    # Hubs by edge type
    def hub_for(etype: str, by: str) -> Counter:
        c: Counter = Counter()
        for e in edges:
            if e.get("type") == etype:
                key = e.get(by)
                if key:
                    c[key] += 1
        return c

    L += R.heading(2, "Top import hubs (files importing the most)")
    L += R.md_table(["file", "imports"],
                    [[_node_label(nodes_by_id, k), f"{v:,}"]
                     for k, v in R.top(hub_for("IMPORTS", "src"), TOP_N)])
    L += R.heading(2, "Top approximate call hubs (callers)")
    L += R.md_table(["caller", "calls"],
                    [[_node_label(nodes_by_id, k), f"{v:,}"]
                     for k, v in R.top(hub_for("CALLS_APPROX", "src"), TOP_N)])
    L += R.heading(2, "Top inheritance roots (most subclassed)")
    L += R.md_table(["base", "subclasses"],
                    [[_node_label(nodes_by_id, k), f"{v:,}"]
                     for k, v in R.top(hub_for("INHERITS", "dst"), TOP_N)])
    L += R.heading(2, "Top decorator clusters")
    L += R.md_table(["decorator", "uses"],
                    [[_node_label(nodes_by_id, k), f"{v:,}"]
                     for k, v in R.top(hub_for("DECORATED_BY", "dst"), TOP_N)])

    # Simple path-prefix clusters
    file_nodes = [n for n in nodes if n.get("type") == "File"]
    by_prefix = R.count_by(file_nodes, lambda n: _path_prefix(n.get("path", "")))
    L += R.heading(2, "Subsystem clusters (by top-level directory)")
    L += R.count_table(by_prefix, ["directory", "files"], TOP_N, total=len(by_prefix))

    # Limitations / warnings
    L += R.heading(2, "Graph limitations & warnings")
    warn = [w for w in bundle.warnings
            if any(t in w.lower() for t in ("call", "resolve", "dynamic", "approx", "edge"))]
    if warn:
        for w in warn:
            L.append(f"- {w}")
    else:
        L.append("- No call-resolution warnings recorded.")
    L.append("- `CALLS_APPROX` edges are name-based and exclude dynamic dispatch, "
             "`getattr`, and most external calls.")
    L.append("")
    return "\n".join(L) + "\n"
