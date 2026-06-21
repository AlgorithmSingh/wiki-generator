"""Step 2: derived/planning-runtime-surfaces.md.

Summarizes the framework/query/contract signals that usually become DeepWiki
sections: routes, workers, CLI, models, config/env, datastore, auth, plugins,
LLM integrations, entrypoints, and the API contract. Built from query results
and native contracts rather than a bespoke schema.
"""
from __future__ import annotations

from collections import defaultdict

from . import ranking as R
from .loader import Bundle

EXAMPLES_PER_PACK = 10

# rg pack -> human section title (order defines the document order).
PACK_TITLES = [
    ("web_routes", "Web routes"),
    ("task_workers", "Tasks / workers"),
    ("cli_commands", "CLI commands"),
    ("models_schemas", "Models / schemas"),
    ("env_vars", "Environment variables"),
    ("config_keys", "Config keys (code)"),
    ("config_file_keys", "Config keys (config files)"),
    ("datastore", "Datastore / storage / cache"),
    ("auth_security", "Auth / security"),
    ("plugin_registries", "Plugins / registries / factories"),
    ("llm_integrations", "LLM integrations"),
    ("entrypoints", "Entrypoints"),
]


def _by_pack(bundle: Bundle) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for hit in bundle.rg_hits:
        grouped[hit.get("pack", "?")].append(hit)
    return grouped


def _api_summary(bundle: Bundle) -> list[str]:
    out: list[str] = []
    spec = bundle.openapi or {}
    paths = spec.get("paths") or {}
    frameworks = spec.get("x-frameworks") or []
    method = "derived" if R.is_derived_contract(spec) else "discovered"
    out.append(f"- Contract source: **{method}**; frameworks: "
               f"{', '.join(frameworks) if frameworks else '—'}")
    out.append(f"- Paths in contract: **{len(paths)}**")
    out.append("")
    rows = []
    for path in sorted(paths)[:40]:
        methods = paths[path]
        verbs = ", ".join(sorted(m.upper() for m in methods if isinstance(methods, dict)))
        rows.append([path, verbs or "—"])
    out += R.md_table(["path", "methods"], rows)
    if len(paths) > 40:
        out.append(f"_… {len(paths) - 40} more paths in contracts/openapi.json_")
        out.append("")
    return out


def build(bundle: Bundle) -> str:
    grouped = _by_pack(bundle)
    L: list[str] = []
    L += R.heading(1, "Planning — Runtime Surfaces")
    L.append("Condensed from `queries/results/rg.jsonl`, `queries/results/grep-ast/*.md`, "
             "`contracts/openapi.json`, and `contracts/contract-sources.md`. "
             "Query hits are lexical and **approximate**.")
    L.append("")

    # Pack overview
    L += R.heading(2, "Surface signal overview")
    rows = [[title, f"{len(grouped.get(pack, [])):,}"] for pack, title in PACK_TITLES]
    L += R.md_table(["surface", "query hits"], rows)

    # API contract
    L += R.heading(2, "API contract")
    L += _api_summary(bundle)

    # Per-pack examples
    for pack, title in PACK_TITLES:
        hits = grouped.get(pack, [])
        L += R.heading(2, f"{title} ({len(hits):,} hits)")
        if not hits:
            L.append("_no hits_")
            L.append("")
            continue
        why = hits[0].get("why", "")
        if why:
            L.append(f"_{why}_")
            L.append("")
        ordered = sorted(hits, key=lambda h: (h.get("path", ""), h.get("line", 0)))
        rows = [[f"{h.get('path', '?')}:{h.get('line', '?')}", h.get("text", "").strip()]
                for h in ordered[:EXAMPLES_PER_PACK]]
        L += R.md_table(["anchor", "match"], rows)
        if len(hits) > EXAMPLES_PER_PACK:
            L.append(f"_… {len(hits) - EXAMPLES_PER_PACK} more in queries/results/rg.jsonl_")
            L.append("")
    return "\n".join(L) + "\n"
