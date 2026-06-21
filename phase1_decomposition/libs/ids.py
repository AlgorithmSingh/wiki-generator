"""Stable, cross-artifact identifier scheme.

These IDs are the glue between lanes: a symbol in ``symbols/symbols.jsonl`` is
linked to its span in ``rag/spans.jsonl`` (``span_id``), its chunks in
``rag/chunks.jsonl`` (``chunk_id``), and its node in ``static/nodes.jsonl``
(``node_id``). Keeping the construction in one place guarantees they agree.

Symbol IDs follow a SCIP-flavored descriptor grammar (see the plan example
``python app.api.users/list_users().``):

    python <dotted.module>/<descriptor><descriptor>...

  descriptors:
    Name#     type / class
    name().   function / method
    name.     term (module-level constant)
    (empty)   the module itself  ->  ``python app.api.users/``
"""
from __future__ import annotations

from . import config as C

SCHEME = "python"


def module_dotted(rel_path: str) -> str:
    """Dotted module name for a Python file path, relative to the repo root.

    ``app/api/users.py`` -> ``app.api.users``
    ``app/api/__init__.py`` -> ``app.api``
    ``src/app/main.py`` -> ``app.main`` (a leading ``src/`` is stripped)
    """
    p = rel_path.replace("\\", "/")
    for pref in C.SOURCE_ROOT_PREFIXES:
        if p.startswith(pref):
            p = p[len(pref):]
            break
    for suf in (".py", ".pyi", ".pyx"):
        if p.endswith(suf):
            p = p[: -len(suf)]
            break
    dotted = p.replace("/", ".")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    elif dotted == "__init__":
        dotted = ""
    return dotted


def _descriptor(name: str, kind: str) -> str:
    if kind == "class":
        return f"{name}#"
    if kind in ("function", "method"):
        return f"{name}()."
    if kind == "constant":
        return f"{name}."
    return f"{name}."


def module_symbol_id(module: str) -> str:
    return f"{SCHEME} {module}/"


def symbol_id(module: str, scope_chain: list[tuple[str, str]]) -> str:
    """Build a symbol id from a module and an ordered (name, kind) scope chain.

    ``symbol_id("app.api.users", [("list_users","function")])``
        -> ``python app.api.users/list_users().``
    ``symbol_id("app.db", [("User","class"), ("save","method")])``
        -> ``python app.db/User#save().``
    """
    descr = "".join(_descriptor(n, k) for n, k in scope_chain)
    return f"{SCHEME} {module}/{descr}"


def span_id(path: str, start: int, end: int, kind: str) -> str:
    """A span is a citeable source range; ``kind`` disambiguates nested ranges
    (a class header and the class can begin on the same line)."""
    return f"span:{path}:{start}-{end}:{kind}"


def chunk_id(path: str, start: int, end: int) -> str:
    return f"chunk:{path}:{start}-{end}"


def file_node_id(path: str) -> str:
    return f"file:{path}"


def module_node_id(module: str) -> str:
    # A module's graph node is the same id as its (materialized) module symbol,
    # so symbols.jsonl, spans.jsonl and static/nodes.jsonl all agree on it.
    return symbol_node_id(module_symbol_id(module))


def symbol_node_id(sym_id: str) -> str:
    return f"sym:{sym_id}"


def dependency_node_id(name: str) -> str:
    return f"dep:{name}"


def repo_node_id(name: str) -> str:
    return f"repo:{name}"


def edge_id(src: str, etype: str, dst: str, *, extra: str = "") -> str:
    base = f"{src}|{etype}|{dst}"
    return f"{base}|{extra}" if extra else base
