"""Step 3: derived/planning-digest.md — the one compact repo overview.

The first content file the Phase 2 planning LLM reads after the README. Pulls
counts from inventory/run-metadata and recomputes the planning-critical rankings
(top modules, graph hubs, import clusters, runtime-surface counts, tests,
unresolved areas) in a single compact brief.
"""
from __future__ import annotations

from collections import Counter

from . import ranking as R
from .loader import Bundle

TOP = 12


def _surface_counts(bundle: Bundle) -> Counter:
    c: Counter = Counter()
    for hit in bundle.rg_hits:
        c[hit.get("pack", "?")] += 1
    return c


# rg pack -> short product-signal phrase, in priority order.
_PURPOSE_SIGNALS = [
    ("web_routes", "an HTTP/web service"),
    ("cli_commands", "a command-line tool"),
    ("task_workers", "background task/worker processing"),
    ("llm_integrations", "LLM/AI integration"),
    ("datastore", "data storage/retrieval"),
    ("models_schemas", "structured data models"),
]


def _purpose_line(bundle: Bundle, cov: dict) -> str:
    """A deterministic one-line purpose guess from language + surface signals.
    Explicitly heuristic; the planner must verify against docs/source."""
    sc = _surface_counts(bundle)
    signals = [phrase for pack, phrase in _PURPOSE_SIGNALS if sc.get(pack, 0) > 0]
    lang = cov.get("primary_language", "Python")
    if not signals:
        return (f"A {lang} codebase; no strong runtime-surface signals were found — "
                "inspect `derived/repo-summary.md` and top docs to confirm purpose.")
    head = "; ".join(signals[:3])
    return (f"A {lang} codebase exhibiting {head} "
            "(heuristic from query-surface hits — verify against docs/README).")


def build(bundle: Bundle) -> str:
    cov = bundle.coverage or {}
    syms = bundle.symbols
    L: list[str] = []
    L += R.heading(1, "Planning Digest")
    L.append("Compact, deterministic overview of the repository for Phase 2 "
             "planning. Derived with no LLM. Anchors point into the full bundle "
             "for Phase 3 retrieval.")
    L.append("")

    # Repo identity & coverage
    L += R.heading(2, "Repository & coverage")
    L.append(f"- Root: `{cov.get('repo_root', bundle.root)}`")
    L.append(f"- Files: **{cov.get('total_files', 0):,}** total, "
             f"{cov.get('indexable_files', 0):,} indexable, "
             f"{cov.get('python_files', 0):,} Python")
    if cov.get("primary_language"):
        L.append(f"- Primary language: **{cov['primary_language']}**")
    L += [""]
    L += R.heading(3, "Files by category")
    cat = cov.get("counts_by_category") or {}
    L += R.md_table(["category", "files"],
                    [[k, f"{v:,}"] for k, v in sorted(cat.items(), key=lambda kv: (-kv[1], kv[0]))])
    L += R.heading(3, "Major directories")
    td = cov.get("counts_by_top_dir") or {}
    L += R.md_table(["directory", "files"],
                    [[k, f"{v:,}"] for k, v in sorted(td.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]])

    # Likely product purpose (deterministic signal from docs/config/query mix)
    L += R.heading(2, "Likely product purpose (heuristic)")
    L.append(f"- {_purpose_line(bundle, cov)}")
    L.append("")

    # Top modules by symbol count
    by_module = R.symbols_by_module(syms)
    L += R.heading(2, "Top modules by symbol count")
    L += R.count_table(by_module, ["module", "symbols"], TOP)

    # Top files by graph degree
    deg: Counter = Counter()
    nodes_by_id = {n.get("node_id"): n for n in bundle.nodes}
    for e in bundle.edges:
        if e.get("src"):
            deg[e["src"]] += 1
        if e.get("dst"):
            deg[e["dst"]] += 1
    file_deg = Counter({nid: c for nid, c in deg.items()
                        if (nodes_by_id.get(nid) or {}).get("type") == "File"})
    L += R.heading(2, "Top files by graph degree")
    L += R.md_table(["file", "degree"],
                    [[(nodes_by_id.get(k) or {}).get("path", k), f"{v:,}"]
                     for k, v in R.top(file_deg, TOP)])

    # Top import clusters (external top-level packages)
    ext = R.external_import_clusters(bundle.imports)
    L += R.heading(2, "Top import clusters (external packages)")
    L += R.count_table(ext, ["package", "imports"], TOP)

    # Dependency / docs / deployment overview (spec "should include")
    L += R.heading(2, "Dependencies, docs & deployment")
    cat = cov.get("counts_by_category") or {}
    L.append(f"- External package imports (distinct top-level): **{len(ext):,}**; "
             f"top: {', '.join(f'`{k}`' for k, _ in R.top(ext, 8)) or '—'}.")
    L.append(f"- Docs: **{cat.get('docs', 0):,}** files. "
             f"Config: **{cat.get('config', 0):,}**. "
             f"Deployment: **{cat.get('deployment', 0):,}**. "
             f"Generated/vendored: **{cat.get('generated', 0) + cat.get('vendor', 0):,}**.")
    dep_nodes = sum(1 for n in bundle.nodes if n.get("type") == "Dependency")
    if dep_nodes:
        L.append(f"- Distinct dependency nodes in the static graph: **{dep_nodes:,}**.")
    L.append("- See `contracts/contract-sources.md` for how the API contract was produced.")
    L.append("")

    # Runtime surfaces
    sc = _surface_counts(bundle)
    L += R.heading(2, "Runtime surfaces (approx query-hit counts)")
    L += R.md_table(["surface", "hits"], [
        ["routes", f"{sc.get('web_routes', 0):,}"],
        ["workers/tasks", f"{sc.get('task_workers', 0):,}"],
        ["CLI", f"{sc.get('cli_commands', 0):,}"],
        ["models/schemas", f"{sc.get('models_schemas', 0):,}"],
        ["config (code+files)", f"{sc.get('config_keys', 0) + sc.get('config_file_keys', 0):,}"],
        ["env vars", f"{sc.get('env_vars', 0):,}"],
        ["datastore", f"{sc.get('datastore', 0):,}"],
        ["auth/security", f"{sc.get('auth_security', 0):,}"],
        ["plugins/registries", f"{sc.get('plugin_registries', 0):,}"],
        ["LLM integrations", f"{sc.get('llm_integrations', 0):,}"],
        ["entrypoints", f"{sc.get('entrypoints', 0):,}"],
    ])
    paths = (bundle.openapi or {}).get("paths") or {}
    contract_kind = "derived" if R.is_derived_contract(bundle.openapi or {}) else "discovered"
    L.append(f"- API contract paths: **{len(paths)}** ({contract_kind}).")
    L.append("")

    # Most central functions/classes (by call in-degree)
    call_in: Counter = Counter()
    for e in bundle.edges:
        if e.get("type") == "CALLS_APPROX" and e.get("dst"):
            call_in[e["dst"]] += 1
    def _sym_label(nid: str) -> str:
        n = nodes_by_id.get(nid) or {}
        name, path = n.get("name"), n.get("path")
        return f"{name} ({path})" if name and path else (name or path or nid)

    L += R.heading(2, "Most central functions/classes (approx call in-degree)")
    L += R.md_table(["symbol node", "callers"],
                    [[_sym_label(k), f"{v:,}"] for k, v in R.top(call_in, TOP)])

    # Tests
    tfs = bundle.test_files
    L += R.heading(2, "Test area")
    L.append(f"- Test files: **{len(tfs):,}**, "
             f"test functions: **{sum(int(t.get('test_functions') or 0) for t in tfs):,}**.")
    test_dirs = R.count_by(tfs, lambda t: "/".join(str(t.get('path', '')).split('/')[:-1]) or "(root)")
    if test_dirs:
        top_dirs = ", ".join(f"`{k}` ({v})" for k, v in R.top(test_dirs, 5))
        L.append(f"- Top test dirs: {top_dirs}.")
    L.append("")

    # Subsystems (file path prefixes)
    file_nodes = [n for n in bundle.nodes if n.get("type") == "File"]
    by_prefix = R.count_by(file_nodes, lambda n: str(n.get("path", "")).split("/")[0]
                           if "/" in str(n.get("path", "")) else "(root)")
    L += R.heading(2, "Likely major subsystems (by top-level directory)")
    L += R.md_table(["subsystem", "files"], [[k, f"{v:,}"] for k, v in R.top(by_prefix, TOP)])

    # Weak / uncertain areas
    L += R.heading(2, "Weak or uncertain areas")
    skipped = [name for name, info in (bundle.tools or {}).items()
               if not (info or {}).get("available")]
    if skipped:
        L.append(f"- Skipped tools: {', '.join(sorted(skipped))}.")
    for w in bundle.warnings:
        L.append(f"- {w}")
    if not bundle.warnings and not skipped:
        L.append("- No warnings recorded.")
    L.append("- See `planning-gaps.md` for the full uncertainty list.")
    L.append("")

    # Planning guidance
    L += R.heading(2, "Section-planning considerations")
    L.append("- Use the runtime-surface counts above to decide which surfaces deserve "
             "dedicated sections (routes, workers, CLI, models, config, auth, plugins).")
    L.append("- Treat call-graph centrality and import clusters as hints for "
             "architecture/overview sections, not ground truth.")
    L.append("- For each planned section, record the retrieval evidence it will need "
             "(symbol ids, file anchors, query packs) for Phase 3.")
    L.append("- Do not invent evidence: where this digest says *approximate* or "
             "*derived*, the planner must mark the section as needing verification.")
    L.append("")
    return "\n".join(L) + "\n"
