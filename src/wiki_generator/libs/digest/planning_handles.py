"""Step 2: derived/planning-handles.md — the exact-handle catalog for planners.

A compact, ranked, budget-aware list of the EXACT retrieval handles a planning
LLM should copy verbatim into a SectionPlan's exact lanes:

* canonical query-pack keys (``web_routes`` …);
* representative ``symbol_id`` values with their source anchors;
* OpenAPI ``METHOD /path`` operations;
* exact graph ``node_id`` values (``repo:`` / ``file:`` / ``sym:`` / ``dep:``);
* test files (and pytest node ids when collection ran);
* search-hint examples for broad topics that must NOT go in exact lanes.

It reuses the same classifiers/anchor helpers as the other condensates so the
handles always agree with what they show, and it never embeds a raw index — only
copyable handles. Digest/condensate docs are planner CONTEXT, not evidence.
"""
from __future__ import annotations

from collections import Counter

from ..rgpacks import PACKS
from . import ranking as R
from .loader import Bundle

MAX_PER_GROUP = 20
_HTTP_VERBS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")

# Broad topics that belong in search_hints[], never in an exact lane.
_SEARCH_HINT_EXAMPLES = [
    "module layout and primary imports",
    "general application code entrypoints",
    "route handler family for a subsystem",
    "background task / worker registration",
    "configuration and settings surface",
    "test function markers for a subsystem",
]


def _by_pos(items: list[dict]) -> list[dict]:
    # symbol_id is the final, unique tie-breaker so ordering is total and never
    # depends on the input order of symbols.jsonl.
    return sorted(items, key=lambda s: (s.get("path", ""),
                                        (s.get("range") or {}).get("start_line", 0),
                                        s.get("symbol_id", "")))


def _symbol_handles(syms: list[dict]) -> list[tuple[str, str]]:
    """Representative ``(symbol_id, anchor)`` handles, ranked then ordered by
    position. Routes/workers/CLI/models/config first, then largest classes,
    module symbols, and remaining callables — deduped, capped, deterministic."""
    seen: set[str] = set()
    picks: list[dict] = []

    def add(s: dict) -> None:
        sid = s.get("symbol_id")
        if sid and sid not in seen:
            seen.add(sid)
            picks.append(s)

    for pred in (R.is_route, R.is_worker, R.is_cli, R.is_model, R.is_config_symbol):
        for s in _by_pos([x for x in syms if pred(x)])[:6]:
            add(s)
    for s in sorted([s for s in syms if s.get("kind") == "class"],
                    key=lambda s: (-R.span_lines(s), s.get("path", ""),
                                   s.get("symbol_id", "")))[:8]:
        add(s)
    for s in _by_pos([s for s in syms if s.get("kind") == "module"])[:6]:
        add(s)
    for s in _by_pos([s for s in syms if s.get("kind") in ("function", "method")]):
        if len(picks) >= MAX_PER_GROUP:
            break
        add(s)
    return [(s["symbol_id"], R.anchor(s)) for s in _by_pos(picks[:MAX_PER_GROUP])]


def _contract_handles(openapi: dict) -> list[str]:
    paths = (openapi or {}).get("paths") or {}
    if not isinstance(paths, dict):       # tolerate a malformed/external spec
        return []
    ops: list[str] = []
    for path in sorted(paths):
        methods = paths[path]
        if not isinstance(methods, dict):
            continue
        for m in sorted(methods):
            if m.lower() in _HTTP_VERBS:
                ops.append(f"{m.upper()} {path}")
    return ops[:MAX_PER_GROUP]


def _graph_handles(nodes: list[dict], edges: list[dict]) -> list[tuple[str, str, str]]:
    nodes_by_id = {n.get("node_id"): n for n in nodes}
    deg: Counter = Counter()
    for e in edges:
        if e.get("src"):
            deg[e["src"]] += 1
        if e.get("dst"):
            deg[e["dst"]] += 1
    seen: set[str] = set()
    picks: list[str] = []
    for n in sorted((n for n in nodes if n.get("type") == "Repository"),
                    key=lambda n: n.get("node_id") or ""):
        nid = n.get("node_id")
        if nid and nid not in seen:
            seen.add(nid)
            picks.append(nid)
    for nid, _ in R.top(deg, MAX_PER_GROUP * 3):
        if len(picks) >= MAX_PER_GROUP:
            break
        if nid not in seen:
            seen.add(nid)
            picks.append(nid)
    rows = []
    for nid in picks[:MAX_PER_GROUP]:
        n = nodes_by_id.get(nid) or {}
        rows.append((nid, n.get("type") or "?", str(n.get("name") or "")))
    return rows


def _test_handles(bundle: Bundle) -> list[str]:
    pc = bundle.pytest_collect or ""
    node_ids = [ln.strip() for ln in pc.splitlines()
                if "::" in ln and not ln.strip().startswith("#")]
    if node_ids:
        return sorted(set(node_ids))[:MAX_PER_GROUP]
    files = sorted(bundle.test_files,
                   key=lambda t: (-int(t.get("test_functions") or 0), t.get("path", "")))
    return [t.get("path", "") for t in files if t.get("path")][:MAX_PER_GROUP]


def build(bundle: Bundle) -> str:
    L: list[str] = []
    L += R.heading(1, "Planning — Exact Retrieval Handles")
    L.append("Copy these **exact** handles into a SectionPlan's exact lanes. They "
             "are the only values Phase 3 can retrieve without guessing.")
    L.append("")
    L.append("> ⚠️ Digest/condensate docs (`planning-*.md`, `repo-summary.md`) are "
             "planner **context**, not evidence. Put them in `context_artifacts[]`, "
             "never in `files[]`. `contracts/openapi.json` by itself is **not** a "
             "contract — use a `METHOD /path` operation. A graph display label like "
             "`pytest [Dependency]` is **not** a node_id — use `dep:pytest`.")
    L.append("")

    L += R.heading(2, "Lane discipline")
    L += ["- `symbols[]`: exact `symbol_id` only (below).",
          "- `files[]`: real repo source paths only (not `derived/planning-*.md`).",
          "- `contracts[]`: exact `METHOD /path` only.",
          "- `tests[]`: exact test file (and function/node id when known).",
          "- `graph_nodes[]`: exact `node_id` only (not display labels).",
          "- `query_packs[]`: canonical keys only (below).",
          "- `search_hints[]`: broad/fuzzy recall text that has no exact handle.",
          "- `context_artifacts[]`: digest/condensate docs used to understand the "
          "repo; never citeable evidence.", ""]

    # Query packs --------------------------------------------------------------
    pack_hits = Counter(h.get("pack") for h in bundle.rg_hits if h.get("pack"))
    L += R.heading(2, "Query packs (canonical keys)")
    for key in PACKS:
        why = PACKS[key].get("why", "")
        L.append(f"- `{key}` — {why} ({pack_hits.get(key, 0):,} hits)")
    L.append("")

    # Symbols ------------------------------------------------------------------
    L += R.heading(2, "Symbols (exact symbol_id → source anchor)")
    sym_rows = _symbol_handles(bundle.symbols)
    if sym_rows:
        for sid, anc in sym_rows:
            L.append(f"- `{sid}`  →  `{anc}`")
    else:
        L.append("_none_")
    L.append("")

    # Contracts ----------------------------------------------------------------
    L += R.heading(2, "Contracts (exact METHOD /path operations)")
    ops = _contract_handles(bundle.openapi)
    if ops:
        for op in ops:
            L.append(f"- `{op}`")
    else:
        L.append("_no routes detected in `contracts/openapi.json` — use "
                 "`search_hints[]` for route topics_")
    L.append("")

    # Graph nodes --------------------------------------------------------------
    L += R.heading(2, "Graph nodes (exact node_id)")
    grows = _graph_handles(bundle.nodes, bundle.edges)
    if grows:
        for nid, ntype, name in grows:
            suffix = f" — {ntype} `{name}`" if name else f" — {ntype}"
            L.append(f"- `{nid}`{suffix}")
    else:
        L.append("_none_")
    L.append("")

    # Tests --------------------------------------------------------------------
    L += R.heading(2, "Tests (exact files / node ids)")
    thandles = _test_handles(bundle)
    if thandles:
        for t in thandles:
            L.append(f"- `{t}`")
    else:
        L.append("_none_")
    L.append("")

    # Search-hint examples -----------------------------------------------------
    L += R.heading(2, "Search-hint examples (for `search_hints[]`, NOT exact lanes)")
    for ex in _SEARCH_HINT_EXAMPLES:
        L.append(f"- {ex}")
    L.append("")
    return "\n".join(L) + "\n"
