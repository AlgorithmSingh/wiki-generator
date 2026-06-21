"""Step 2: derived/planning-symbols.md — condensed symbol summary.

Replaces the multi-million-token ``symbols/symbols.jsonl`` for planning with
ranked tables and representative, source-anchored examples.
"""
from __future__ import annotations

from . import ranking as R
from .loader import Bundle

EXAMPLES_PER_SURFACE = 12
TOP_N = 25


def _examples(symbols: list[dict], pred, limit: int) -> list[list[str]]:
    rows = []
    for s in sorted(symbols, key=lambda s: (s.get("path", ""),
                                            (s.get("range") or {}).get("start_line", 0))):
        if pred(s):
            decs = ", ".join(s.get("decorators") or []) or "—"
            rows.append([s.get("name", "?"), s.get("kind", "?"), R.anchor(s), decs])
            if len(rows) >= limit:
                break
    return rows


def build(bundle: Bundle) -> str:
    syms = bundle.symbols
    L: list[str] = []
    L += R.heading(1, "Planning — Symbols")
    L.append("Condensed from `symbols/symbols.jsonl`, `symbols/imports.jsonl`, "
             "`symbols/occurrences.jsonl`. Ranked tables + representative examples; "
             "not the full symbol table.")
    L.append("")

    # Counts by kind
    by_kind = R.count_by(syms, lambda s: s.get("kind"))
    L += R.heading(2, "Symbol counts by kind")
    L += R.md_table(["kind", "count"], [[k, f"{v:,}"] for k, v in R.top(by_kind, 20)])

    # Top modules by symbol count
    by_module = R.symbols_by_module(syms)
    L += R.heading(2, "Top modules by symbol count")
    L += R.count_table(by_module, ["module", "symbols"], TOP_N, total=len(by_module))

    # Top files by class/function/method count
    structural = [s for s in syms if s.get("kind") in ("class", "function", "method")]
    by_file = R.count_by(structural, lambda s: s.get("path"))
    L += R.heading(2, "Top files by class/function/method count")
    L += R.count_table(by_file, ["file", "defs"], TOP_N, total=len(by_file))

    # Largest classes
    classes = [s for s in syms if s.get("kind") == "class"]
    largest = sorted(classes, key=lambda s: (-R.span_lines(s), s.get("path", "")))[:TOP_N]
    L += R.heading(2, "Largest classes (by line span)")
    L += R.md_table(["class", "lines", "anchor"],
                    [[s.get("name", "?"), R.span_lines(s), R.anchor(s)] for s in largest])

    # Most decorated functions/classes
    decorated = [s for s in syms if (s.get("decorators") or [])]
    most_dec = sorted(decorated, key=lambda s: (-len(s.get("decorators") or []),
                                                s.get("path", "")))[:TOP_N]
    L += R.heading(2, "Most-decorated symbols")
    L += R.md_table(["symbol", "decorators", "anchor"],
                    [[s.get("name", "?"), ", ".join(s.get("decorators") or []),
                      R.anchor(s)] for s in most_dec])

    # Runtime-surface symbol examples
    L += R.heading(2, "Route handler symbols (approx, by decorator)")
    L += R.md_table(["name", "kind", "anchor", "decorators"],
                    _examples(syms, R.is_route, EXAMPLES_PER_SURFACE))
    L += R.heading(2, "Worker / task symbols (approx, by decorator)")
    L += R.md_table(["name", "kind", "anchor", "decorators"],
                    _examples(syms, R.is_worker, EXAMPLES_PER_SURFACE))
    L += R.heading(2, "CLI command symbols (approx, by decorator)")
    L += R.md_table(["name", "kind", "anchor", "decorators"],
                    _examples(syms, R.is_cli, EXAMPLES_PER_SURFACE))
    L += R.heading(2, "Model / schema symbols (approx, by base class)")
    L += R.md_table(["name", "kind", "anchor", "bases"],
                    [[s.get("name", "?"), s.get("kind", "?"), R.anchor(s),
                      ", ".join(s.get("bases") or [])]
                     for s in sorted([s for s in syms if R.is_model(s)],
                                     key=lambda s: s.get("path", ""))[:EXAMPLES_PER_SURFACE]])
    L += R.heading(2, "Config / settings symbols (approx, by name)")
    L += R.md_table(["name", "kind", "anchor"],
                    [[s.get("name", "?"), s.get("kind", "?"), R.anchor(s)]
                     for s in sorted([s for s in syms if R.is_config_symbol(s)],
                                     key=lambda s: s.get("path", ""))[:EXAMPLES_PER_SURFACE]])

    # Imports
    imp_targets = R.count_by(bundle.imports, lambda imp: imp.get("module"))
    ext_targets = R.external_import_clusters(bundle.imports)
    L += R.heading(2, "Top imports by frequency")
    L += R.count_table(imp_targets, ["module", "imports"], TOP_N, total=len(imp_targets))
    L += R.heading(2, "External dependency imports (top-level)")
    L += R.count_table(ext_targets, ["package", "imports"], TOP_N, total=len(ext_targets))

    # Parse errors / approximation notes from run metadata
    L += R.heading(2, "Parse / resolution notes")
    notes = [w for w in bundle.warnings if "symbol" in w.lower() or "parse" in w.lower()
             or "resolve" in w.lower()]
    if notes:
        for w in notes:
            L.append(f"- {w}")
    else:
        L.append("- No symbol parse/resolution warnings recorded.")
    L.append("")
    return "\n".join(L) + "\n"
