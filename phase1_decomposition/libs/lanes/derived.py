"""Derived lane — deterministic human-readable summaries (no LLM, no inference
beyond direct observation). Runs last so it can index every prior artifact.

Artifacts:
  derived/repo-summary.md     human-readable repo overview with file anchors
  derived/artifact-index.md   machine-ish index of every artifact + counts
"""
from __future__ import annotations

import os
import sys
from collections import Counter

from ..context import RunContext, artifact_table
from ..util import write_text, log

_STDLIB = set(getattr(sys, "stdlib_module_names", set()))


def _top_files_for_pack(rg_data, pack: str, n: int = 6) -> list[tuple[str, int]]:
    c: Counter = Counter()
    for m in rg_data.matches:
        if m["pack"] == pack:
            c[m["path"]] += 1
    return c.most_common(n)


def _external_deps(sym: dict) -> Counter:
    deps: Counter = Counter()
    for imp in sym.get("imports", []):
        if imp["is_internal"]:
            continue
        if imp["kind"] == "import":
            for nm in imp["names"]:
                root = nm["name"].split(".")[0]
                if root and root not in _STDLIB:
                    deps[root] += 1
        elif imp["kind"] == "from" and imp.get("level", 0) == 0 and imp.get("module"):
            root = imp["module"].split(".")[0]
            if root and root not in _STDLIB:
                deps[root] += 1
    return deps


def _import_hubs(sym: dict) -> list[tuple[str, int]]:
    indeg: Counter = Counter()
    for imp in sym.get("imports", []):
        if imp["is_internal"] and imp.get("resolved_path"):
            indeg[imp["resolved_path"]] += 1
    return indeg.most_common(12)


def _repo_name(ctx: RunContext) -> str:
    name = (ctx.git_meta.get("remote", "").rstrip("/").split("/")[-1]
            or os.path.basename(ctx.repo.rstrip("/")) or "repo")
    return name.removesuffix(".git")


def _summary(ctx: RunContext, inv: dict, sym: dict, rg_data) -> str:
    cov = inv.get("coverage", {})
    git = ctx.git_meta
    L: list[str] = []
    L.append(f"# {_repo_name(ctx)} — Repository Summary")
    L.append("")
    L.append("Deterministic Phase 1 overview. Every line below is a direct "
             "observation of the repository (no LLM, no inference).")
    L.append("")

    L.append("## Identity")
    L.append("")
    L.append(f"- Root: `{ctx.repo}`")
    for k in ("remote", "branch", "head_commit"):
        if git.get(k):
            L.append(f"- {k.replace('_', ' ').title()}: `{git[k]}`")
    L.append(f"- Listing method: `{cov.get('listing_method', 'unknown')}`")
    L.append("")

    L.append("## Scale & languages")
    L.append("")
    L.append(f"- Files: **{cov.get('total_files', 0)}** "
             f"({cov.get('indexable_files', 0)} indexable, "
             f"{cov.get('python_files', 0)} Python)")
    langs = cov.get("counts_by_language", {})
    if langs:
        L.append("")
        L.append("| Language | Files |")
        L.append("|---|---|")
        for lang, c in list(langs.items())[:12]:
            L.append(f"| {lang} | {c} |")
    cats = cov.get("counts_by_category", {})
    if cats:
        L.append("")
        L.append("| Category | Files |")
        L.append("|---|---|")
        for cat, c in cats.items():
            L.append(f"| {cat} | {c} |")
    L.append("")

    dirs = cov.get("counts_by_top_dir", {})
    if dirs:
        L.append("## Top-level layout")
        L.append("")
        for d, c in list(dirs.items())[:12]:
            L.append(f"- `{d}/` — {c} files")
        L.append("")

    # Entrypoints
    L.append("## Entry points")
    L.append("")
    ep = _top_files_for_pack(rg_data, "entrypoints", 8)
    if ep:
        for path, c in ep:
            L.append(f"- `{path}` ({c} signal{'s' if c != 1 else ''})")
    else:
        L.append("- None detected by the `entrypoints` query pack.")
    L.append("")

    # Routes
    routes = sym.get("routes", [])
    L.append(f"## HTTP routes ({len(routes)})")
    L.append("")
    if routes:
        frameworks = sorted({r.get("framework", "?") for r in routes})
        L.append(f"Frameworks: {', '.join(frameworks)}")
        L.append("")
        for r in sorted(routes, key=lambda x: (x.get("path_file", ""), x.get("lineno", 0)))[:25]:
            L.append(f"- `{','.join(r.get('methods', []))} {r['path']}` → "
                     f"`{r.get('handler')}` (`{r.get('path_file')}:{r.get('lineno')}`)")
        if len(routes) > 25:
            L.append(f"- …and {len(routes) - 25} more (see `symbols/symbols.jsonl` / "
                     f"`contracts/openapi.json`).")
    else:
        L.append("- No route decorators detected.")
    L.append("")

    # Surface signals
    L.append("## Surface signals (ripgrep query packs)")
    L.append("")
    L.append("| Surface | Hits | Top files |")
    L.append("|---|---|---|")
    surface_labels = {
        "cli_commands": "CLI commands", "task_workers": "Task/workers",
        "models_schemas": "Models/schemas", "datastore": "Datastores",
        "auth_security": "Auth/security", "config_keys": "Config keys",
        "env_vars": "Env vars", "plugin_registries": "Plugins/registries",
        "llm_integrations": "LLM integrations",
    }
    for pack, label in surface_labels.items():
        total = rg_data.summary.get(pack, 0)
        top = _top_files_for_pack(rg_data, pack, 3)
        tf = ", ".join(f"`{p}`" for p, _ in top) or "—"
        L.append(f"| {label} | {total} | {tf} |")
    L.append("")

    # Dependencies
    deps = _external_deps(sym)
    L.append("## Top third-party dependencies (by import frequency)")
    L.append("")
    if deps:
        for name, c in deps.most_common(15):
            L.append(f"- `{name}` ({c})")
    else:
        L.append("- None detected (stdlib-only or non-Python).")
    L.append("")

    # Import hubs
    hubs = _import_hubs(sym)
    if hubs:
        L.append("## Internal import hubs (most-imported modules)")
        L.append("")
        for path, c in hubs:
            L.append(f"- `{path}` (imported by {c})")
        L.append("")

    # Config & deployment
    cfg = [r["path"] for r in inv["files"] if r["category"] == "config"][:20]
    dep = [r["path"] for r in inv["files"] if r["category"] == "deployment"][:20]
    L.append("## Configuration & deployment")
    L.append("")
    L.append("- Config files: " + (", ".join(f"`{p}`" for p in cfg) if cfg else "none"))
    L.append("- Deployment files: " + (", ".join(f"`{p}`" for p in dep) if dep else "none"))
    L.append("")

    # Tests
    test_files = [r for r in inv["files"] if r["category"] == "test"]
    modules = sym.get("modules", {})
    test_fns = 0
    for r in test_files:
        p = modules.get(r["path"])
        if p and not getattr(p, "error", None):
            test_fns += sum(1 for s in p.symbols
                            if s["kind"] in {"function", "method"}
                            and s["name"].startswith("test"))
    L.append(f"## Tests")
    L.append("")
    L.append(f"- {len(test_files)} test files, ~{test_fns} test functions "
             f"(see `tests/test-files.jsonl`, `tests/pytest-collect.txt`).")
    L.append("")

    # Docs
    docs = [r["path"] for r in inv["files"] if r["category"] == "docs"]
    L.append("## Documentation")
    L.append("")
    L.append(f"- {len(docs)} doc file(s).")
    for p in [d for d in docs if os.path.basename(d).lower().startswith("readme")][:5]:
        L.append(f"  - `{p}`")
    L.append("")

    # Caveats
    L.append("## Caveats & known gaps")
    L.append("")
    errs = sym.get("errors", [])
    if errs:
        L.append(f"- {len(errs)} Python file(s) failed to parse (see "
                 f"`symbols/symbols.jsonl` note).")
    L.append("- Call/reference edges (`CALLS_APPROX`) and MENTIONS/TESTS_APPROX are "
             "name-resolved and therefore approximate; each carries a `confidence`.")
    if ctx.warnings:
        for w in ctx.warnings:
            L.append(f"- {w}")
    else:
        L.append("- No warnings recorded.")
    L.append("")
    return "\n".join(L) + "\n"


def _artifact_index(ctx: RunContext, inv: dict) -> str:
    L: list[str] = []
    L.append("# Artifact Index")
    L.append("")
    L.append("Every artifact in this bundle, the tool that produced it, and its row "
             "count. See `ARTIFACT_GUIDE.md` for orientation and `run-metadata.json` "
             "for tool versions and timings.")
    L.append("")
    # ctx.artifacts already holds every prior lane's outputs, including
    # derived/repo-summary.md (recorded just before this runs). Append only the
    # artifacts not yet recorded: this index, and the two pipeline-level files
    # written after the derived lane. Dedupe by path as a safety net.
    rows = list(ctx.artifacts)
    rows.append({"path": "derived/artifact-index.md", "produced_by": "derived",
                 "rows": None, "skipped": False, "description": "this file", "note": None})
    rows.append({"path": "ARTIFACT_GUIDE.md", "produced_by": "pipeline",
                 "rows": None, "skipped": False, "description": "orientation guide",
                 "note": None})
    rows.append({"path": "run-metadata.json", "produced_by": "pipeline",
                 "rows": None, "skipped": False, "description": "run metadata",
                 "note": None})
    seen_paths: set[str] = set()
    deduped = []
    for a in rows:
        if a["path"] in seen_paths:
            continue
        seen_paths.add(a["path"])
        deduped.append(a)
    L += artifact_table(deduped)
    L.append("")
    L.append("## Lane → artifact map")
    L.append("")
    lane_map = [
        ("inventory", "inventory/files.jsonl, git-tracked-files.txt, source-coverage.json"),
        ("symbols", "symbols/symbols.jsonl, imports.jsonl, occurrences.jsonl, tags, tags.jsonl"),
        ("rag", "rag/spans.jsonl, chunks.jsonl, bm25.sqlite, rg-results.jsonl, vectors.faiss"),
        ("static", "static/nodes.jsonl, edges.jsonl"),
        ("queries", "queries/rules/rg/*.json, results/rg.jsonl, results/grep-ast/*.md, "
                    "results/semgrep.{json,sarif}, results/ast-grep.json"),
        ("contracts", "contracts/openapi.json, contract-sources.md"),
        ("tests", "tests/pytest-collect.txt, test-files.jsonl"),
        ("derived", "derived/repo-summary.md, artifact-index.md"),
    ]
    for lane, arts in lane_map:
        L.append(f"- **{lane}** → {arts}")
    L.append("")
    return "\n".join(L) + "\n"


def build(ctx: RunContext, inv: dict, sym: dict, rg_data) -> dict:
    summary = _summary(ctx, inv, sym, rg_data)
    write_text(ctx.paths.repo_summary, summary)
    ctx.record(ctx.paths.repo_summary, produced_by="derived",
               description="deterministic human-readable repo overview")

    index = _artifact_index(ctx, inv)
    write_text(ctx.paths.artifact_index, index)
    ctx.record(ctx.paths.artifact_index, produced_by="derived",
               description="machine index of every artifact + counts")

    log("derived: repo-summary.md + artifact-index.md")
    return {"ok": True}
