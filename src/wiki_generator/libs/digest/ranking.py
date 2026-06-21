"""Digest-specific ranking + classification helpers.

The generic, language-agnostic primitives (``top``, ``count_by``, ``md_table``,
``count_table``, ``heading``, ``Section``) live in ``libs/markdown.py`` so the
lanes can share them; they are re-exported here so summarizers keep importing one
module. Everything below is specific to interpreting *symbols/graph/contracts*
for planning, which is why it belongs to the digest layer.
"""
from __future__ import annotations

from collections import Counter

# Re-export the shared primitives so summarizers use a single `ranking` surface.
from ..markdown import Section, count_by, count_table, heading, md_table, top

__all__ = [
    "Section", "count_by", "count_table", "heading", "md_table", "top",
    "is_route", "is_worker", "is_cli", "is_model", "is_config_symbol",
    "span_lines", "anchor", "is_derived_contract",
    "symbols_by_module", "external_import_clusters",
]

# --- symbol classification -----------------------------------------------------
# Decorator/base substrings (lowercased) that mark a runtime surface. Heuristic
# and intentionally broad; the digest labels them "approximate".
ROUTE_DECORATORS = ("route", ".get", ".post", ".put", ".patch", ".delete",
                    ".websocket", "app.", "router.", "blueprint", "api_view",
                    "requestmapping", "getmapping", "postmapping")
WORKER_DECORATORS = ("task", "shared_task", "celery", "periodic", "cron",
                    "scheduled", "rq.", "huey", "dramatiq")
CLI_DECORATORS = ("command", "click", "group", "argument", "option", "app.command")
MODEL_BASES = ("basemodel", "model", "schema", "table", "document", "dataclass",
               "namedtuple", "typeddict", "declarative_base")
CONFIG_NAMES = ("settings", "config", "configuration", "appconfig", "basesettings")


def _lower_any(values) -> str:
    return " ".join(str(v).lower() for v in (values or []))


def is_route(sym: dict) -> bool:
    decs = _lower_any(sym.get("decorators"))
    return any(tok in decs for tok in ROUTE_DECORATORS)


def is_worker(sym: dict) -> bool:
    decs = _lower_any(sym.get("decorators"))
    return any(tok in decs for tok in WORKER_DECORATORS)


def is_cli(sym: dict) -> bool:
    decs = _lower_any(sym.get("decorators"))
    return any(tok in decs for tok in CLI_DECORATORS)


def is_model(sym: dict) -> bool:
    if sym.get("kind") != "class":
        return False
    bases = _lower_any(sym.get("bases"))
    return any(tok in bases for tok in MODEL_BASES)


def is_config_symbol(sym: dict) -> bool:
    name = str(sym.get("name", "")).lower()
    return name in CONFIG_NAMES or name.endswith("settings") or name.endswith("config")


def span_lines(sym: dict) -> int:
    r = sym.get("range") or {}
    try:
        return max(0, int(r.get("end_line", 0)) - int(r.get("start_line", 0)) + 1)
    except (TypeError, ValueError):
        return 0


def anchor(sym: dict) -> str:
    """`path:start-end` source anchor for a symbol, or `path` if unknown."""
    path = sym.get("path", "?")
    r = sym.get("range") or {}
    s, e = r.get("start_line"), r.get("end_line")
    if s and e:
        return f"{path}:{s}-{e}"
    return str(path)


# --- contract classification ---------------------------------------------------
def is_derived_contract(spec: dict) -> bool:
    """True when the OpenAPI spec was statically derived (or is empty) rather
    than discovered/imported. ``x-derived-by`` is the canonical Step-1 marker;
    an empty path set also means there is no authoritative contract to trust.
    Every digest summarizer must use this one signal so they never disagree."""
    spec = spec or {}
    return bool(spec.get("x-derived-by")) or not spec.get("paths")


# --- shared symbol/import derivations (used by >1 summarizer) -------------------
def symbols_by_module(symbols: list[dict]) -> Counter:
    """Symbol count keyed by dotted module."""
    return count_by(symbols, lambda s: s.get("module"))


def external_import_clusters(imports: list[dict]) -> Counter:
    """Top-level external package -> import count (``is_internal`` is false)."""
    c: Counter = Counter()
    for imp in imports:
        mod = imp.get("module")
        if mod and not imp.get("is_internal"):
            c[str(mod).split(".")[0]] += 1
    return c
