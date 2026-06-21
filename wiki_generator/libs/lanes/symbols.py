"""Symbols lane — an industry-practice code-intelligence index for Python.

Artifacts:
  symbols/symbols.jsonl      symbol, kind, file, range, signature, parent, doc
  symbols/imports.jsonl      one row per import statement (+ internal resolution)
  symbols/occurrences.jsonl  definitions (exact) + approximate references
  symbols/tags               ctags-format index (universal-ctags or AST-derived)
  symbols/tags.jsonl         ctags JSON-lines index

Python structure comes from the stdlib ``ast`` module. Call/reference resolution
is name-based and therefore approximate; occurrences carry a ``confidence`` field.
"""
from __future__ import annotations

import ast
import os

from .. import config as C
from .. import ids
from ..context import RunContext
from ..tools import run as run_cmd
from ..util import read_text, write_jsonl, write_text, log, module_header_last

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
_ROUTE_ATTRS = {"route", "websocket"} | _HTTP_METHODS


def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _str_const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _doc(node) -> str | None:
    try:
        d = ast.get_docstring(node, clean=True)
    except Exception:
        return None
    if not d:
        return None
    first = d.strip().splitlines()[0].strip()
    return first[:240] if first else None


def _format_arguments(a: ast.arguments) -> str:
    """Render an ``ast.arguments`` node back into a parameter list."""
    parts: list[str] = []

    def ann(arg: ast.arg) -> str:
        s = arg.arg
        if arg.annotation is not None:
            s += f": {_unparse(arg.annotation)}"
        return s

    posonly = list(getattr(a, "posonlyargs", []) or [])
    args = list(a.args or [])
    defaults = list(a.defaults or [])
    all_pos = posonly + args
    # defaults align to the tail of all_pos
    default_map: dict[int, ast.AST] = {}
    if defaults:
        for i, d in enumerate(defaults):
            default_map[len(all_pos) - len(defaults) + i] = d

    for i, arg in enumerate(all_pos):
        s = ann(arg)
        if i in default_map:
            s += f"={_unparse(default_map[i])}"
        parts.append(s)
        if posonly and i == len(posonly) - 1:
            parts.append("/")

    if a.vararg is not None:
        parts.append("*" + ann(a.vararg))
    elif a.kwonlyargs:
        parts.append("*")
    for i, arg in enumerate(a.kwonlyargs or []):
        s = ann(arg)
        kd = (a.kw_defaults or [])[i] if i < len(a.kw_defaults or []) else None
        if kd is not None:
            s += f"={_unparse(kd)}"
        parts.append(s)
    if a.kwarg is not None:
        parts.append("**" + ann(a.kwarg))
    return ", ".join(parts)


def _signature(node, is_async: bool) -> str:
    prefix = "async def " if is_async else "def "
    args = _format_arguments(node.args)
    ret = f" -> {_unparse(node.returns)}" if node.returns is not None else ""
    return f"{prefix}{node.name}({args}){ret}"


def _decorator_route(dec) -> dict | None:
    """Detect a route-registration decorator -> {path, methods, framework}."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if isinstance(func, ast.Attribute):
        attr = func.attr
    elif isinstance(func, ast.Name):
        attr = func.id
    else:
        return None
    if attr not in _ROUTE_ATTRS and attr != "add_url_rule":
        return None
    path = None
    for a in dec.args:
        s = _str_const(a)
        if s is not None:
            path = s
            break
    methods = []
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            methods = [_str_const(e) for e in kw.value.elts if _str_const(e)]
    if not methods and attr in _HTTP_METHODS:
        methods = [attr.upper()]
    if attr == "websocket":
        methods = ["WEBSOCKET"]
    if not methods:
        methods = ["GET"]
    # A real route's first positional arg is a URL path. Filters @patch(...) etc.
    if path is None or not path.startswith("/"):
        return None
    if attr in _HTTP_METHODS and not isinstance(func, ast.Attribute):
        return None  # bare @get(...) is not a route
    router_var = func.value.id if isinstance(func, ast.Attribute) \
        and isinstance(func.value, ast.Name) else None
    framework = "flask/quart" if attr in {"route", "add_url_rule"} else "fastapi/starlette"
    return {"path": path, "methods": methods, "framework": framework,
            "router_var": router_var}


def _join_route(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return "/" + prefix.strip("/") + "/" + path.lstrip("/") if path != "/" \
        else "/" + prefix.strip("/")


# Router/blueprint constructors whose prefix kwarg qualifies decorated routes.
_ROUTER_CTORS = {"APIRouter": "prefix", "Blueprint": "url_prefix",
                 "Router": "prefix", "Mount": "path"}


def _str_kw(call: ast.Call, key: str):
    for kw in call.keywords:
        if kw.arg == key:
            return _str_const(kw.value)
    return None


class _ModuleParser:
    """Walks one module's AST, collecting symbols, imports, routes, calls."""

    def __init__(self, text: str, rel_path: str):
        self.path = rel_path
        self.module = ids.module_dotted(rel_path)
        self.text = text
        self.symbols: list[dict] = []
        self.imports: list[dict] = []
        self.routes: list[dict] = []
        self.calls: list[dict] = []     # {caller_symbol_id, name, attr_obj, line}
        self.constants: list[dict] = []
        self.module_doc: str | None = None
        self.error: str | None = None
        self.first_def_line: int | None = None
        self.router_prefixes: dict[str, str] = {}  # var name -> route prefix

    def parse(self) -> "_ModuleParser":
        try:
            tree = ast.parse(self.text)
        except SyntaxError as e:
            self.error = f"SyntaxError: line {e.lineno}: {e.msg}"
            return self
        self.module_doc = _doc(tree)
        self._scan_router_prefixes(tree)
        self._visit_body(tree.body, [], ids.module_symbol_id(self.module))
        self._collect_django_routes(tree)
        return self

    def _scan_router_prefixes(self, tree):
        """router = APIRouter(prefix="/x") / bp = Blueprint(..., url_prefix="/x")."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            f = node.value.func
            ctor = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if ctor not in _ROUTER_CTORS:
                continue
            prefix = _str_kw(node.value, _ROUTER_CTORS[ctor])
            if not prefix:
                continue
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.router_prefixes[t.id] = prefix

    def _collect_django_routes(self, tree):
        """Django registers URLs as path()/re_path()/url() CALLS (not decorators):
        urlpatterns = [path("users/", views.user_list), ...]."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if name not in {"path", "re_path", "url"}:
                continue
            route = _str_const(node.args[0]) if node.args else None
            if route is None:
                continue
            view = _unparse(node.args[1]) if len(node.args) > 1 else None
            self.routes.append({
                "path": route if route.startswith("/") else "/" + route,
                "methods": ["*"], "framework": "django",
                "handler": view, "handler_symbol_id": None,
                "path_file": self.path, "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
            })

    def _visit_body(self, body, scope_chain: list[tuple[str, str]],
                    parent_symbol_id: str):
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._record_import(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._record_callable(node, scope_chain, parent_symbol_id)
            elif isinstance(node, ast.ClassDef):
                self._record_class(node, scope_chain, parent_symbol_id)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and not scope_chain:
                self._record_constant(node)

    def _record_import(self, node):
        if isinstance(node, ast.Import):
            self.imports.append({
                "kind": "import", "module": None, "level": 0,
                "names": [{"name": a.name, "asname": a.asname} for a in node.names],
                "lineno": node.lineno,
            })
        else:
            self.imports.append({
                "kind": "from", "module": node.module, "level": node.level or 0,
                "names": [{"name": a.name, "asname": a.asname} for a in node.names],
                "lineno": node.lineno,
            })

    def _record_constant(self, node):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 2:
                val = _unparse(node.value) if getattr(node, "value", None) else ""
                self.constants.append({"name": t.id, "value": val[:160],
                                       "lineno": node.lineno})

    def _record_callable(self, node, scope_chain, parent_symbol_id):
        is_async = isinstance(node, ast.AsyncFunctionDef)
        parent_kind = scope_chain[-1][1] if scope_chain else None
        kind = "method" if parent_kind == "class" else "function"
        chain = scope_chain + [(node.name, kind)]
        sym_id = ids.symbol_id(self.module, chain)
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if not scope_chain and self.first_def_line is None:
            self.first_def_line = start
        decos = [_unparse(d) for d in node.decorator_list]
        self.symbols.append({
            "symbol_id": sym_id,
            "name": node.name,
            "kind": kind,
            "path": self.path,
            "module": self.module,
            "range": {"start_line": start, "end_line": end},
            "signature": _signature(node, is_async),
            "parent_symbol_id": parent_symbol_id,
            "decorators": decos,
            "bases": [],
            "is_async": is_async,
            "docstring": _doc(node),
            "span_id": ids.span_id(self.path, start, end, kind),
        })
        for d in node.decorator_list:
            r = _decorator_route(d)
            if r:
                prefix = self.router_prefixes.get(r.pop("router_var", None) or "", "")
                if prefix:
                    r["path"] = _join_route(prefix, r["path"])
                    r["router_prefix"] = prefix
                r.update({"handler": node.name, "handler_symbol_id": sym_id,
                          "path_file": self.path, "lineno": start, "end_lineno": end})
                self.routes.append(r)
        self._collect_calls(node, sym_id)
        self._visit_body(node.body, chain, sym_id)

    def _record_class(self, node, scope_chain, parent_symbol_id):
        chain = scope_chain + [(node.name, "class")]
        sym_id = ids.symbol_id(self.module, chain)
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if not scope_chain and self.first_def_line is None:
            self.first_def_line = start
        self.symbols.append({
            "symbol_id": sym_id,
            "name": node.name,
            "kind": "class",
            "path": self.path,
            "module": self.module,
            "range": {"start_line": start, "end_line": end},
            "signature": f"class {node.name}({', '.join(_unparse(b) for b in node.bases)})",
            "parent_symbol_id": parent_symbol_id,
            "decorators": [_unparse(d) for d in node.decorator_list],
            "bases": [_unparse(b) for b in node.bases],
            "is_async": False,
            "docstring": _doc(node),
            "span_id": ids.span_id(self.path, start, end, "class"),
        })
        self._visit_body(node.body, chain, sym_id)

    def _collect_calls(self, fnode, caller_symbol_id: str):
        """Record call sites lexically inside this callable's OWN body, not those
        inside nested defs/classes (each nested scope records its own calls when
        _visit_body recurses into it). ast.walk would descend into nested bodies,
        so we recurse manually and stop at nested scope boundaries.

        Scope is intentionally the function body only. Excluded by design:
          * decorator calls (``@functools.wraps(f)``) — represented separately by
            the DECORATED_BY graph edge, so recording them here would double-count;
          * default-argument call expressions (``def g(a=helper())``) — evaluated
            in the enclosing scope at def time, rare, and noisy;
          * class-body and module-level calls — not part of the call graph between
            callables (CALLS_APPROX edges are an explicitly approximate signal).
        Calls inside comprehensions and lambdas in the body ARE captured.
        """
        def descend(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
                    continue  # a nested scope; handled by its own _collect_calls
                if isinstance(child, ast.Call):
                    self._record_call(child, caller_symbol_id)
                descend(child)
        for stmt in fnode.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # a directly-nested scope; records its own calls
            if isinstance(stmt, ast.Call):
                self._record_call(stmt, caller_symbol_id)
            descend(stmt)

    def _record_call(self, node: ast.Call, caller_symbol_id: str):
        f = node.func
        if isinstance(f, ast.Name):
            self.calls.append({"caller_symbol_id": caller_symbol_id,
                               "name": f.id, "attr_obj": None, "line": node.lineno})
        elif isinstance(f, ast.Attribute):
            self.calls.append({"caller_symbol_id": caller_symbol_id,
                               "name": f.attr, "attr_obj": _unparse(f.value),
                               "line": node.lineno})


# --- import resolution ---------------------------------------------------------
def _src_parts(rel_path: str) -> list[str]:
    """Path components with SOURCE_ROOT_PREFIXES stripped and '.py' removed, but
    keeping '__init__' (needed for correct relative-import `level` arithmetic)."""
    p = rel_path.replace("\\", "/")
    for pref in C.SOURCE_ROOT_PREFIXES:
        if p.startswith(pref):
            p = p[len(pref):]
            break
    for suf in (".py", ".pyi", ".pyx"):
        if p.endswith(suf):
            p = p[: -len(suf)]
            break
    return [x for x in p.split("/") if x]


def _module_to_path(py_files: set[str]) -> dict[str, str]:
    # Key the lookup on the SAME dotted name ids.module_dotted produces (which
    # strips SOURCE_ROOT_PREFIXES like src/), so import strings parsed from code
    # ("from app.db import X") resolve in src-layout repos too.
    m: dict[str, str] = {}
    for f in py_files:
        if not f.endswith(".py"):
            continue
        m[ids.module_dotted(f)] = f
    return m


def _resolve_import_target(imp: dict, cur_file: str, mod2path: dict[str, str]):
    if imp["kind"] == "from":
        base = imp.get("module") or ""
        level = imp.get("level", 0)
        if level:  # relative import — resolve against the src-stripped package
            parts = _src_parts(cur_file)
            parts = parts[: max(0, len(parts) - level)]
            base = ".".join(parts + ([base] if base else []))
        # Prefer a submodule target (`from pkg import submod`) over the package
        # itself, so `from . import users` links to users.py, not __init__.py.
        for n in imp.get("names", []):
            cand = f"{base}.{n['name']}" if base else n["name"]
            if cand in mod2path:
                return mod2path[cand]
        if base in mod2path:
            return mod2path[base]
    else:  # plain import
        for n in imp.get("names", []):
            if n["name"] in mod2path:
                return mod2path[n["name"]]
            top = n["name"].split(".")[0]
            if top in mod2path:
                return mod2path[top]
    return None


# --- ctags ---------------------------------------------------------------------
_CTAGS_KIND_LETTER = {"function": "f", "method": "m", "class": "c", "constant": "v"}
_CTAGS_KIND_NAME = {"function": "function", "method": "member",
                    "class": "class", "constant": "variable"}


def _ctags_pattern(line_text: str) -> str:
    # ctags ex-command search pattern: /^...$/ with magic chars escaped.
    body = line_text.rstrip("\n")
    body = body.replace("\\", "\\\\").replace("/", "\\/")
    return f"/^{body}$/"


def _write_ast_tags(ctx: RunContext, symbols: list[dict], constants_rows: list[dict],
                    file_lines: dict[str, list[str]]) -> tuple[int, int]:
    """Generate ctags-format `tags` and ctags JSON `tags.jsonl` from AST symbols."""
    import json as _json
    entries = []  # (name, path, pattern, kind_letter, line, scope, scope_kind, kind_name)
    rows = []
    all_rows = list(symbols) + constants_rows
    for s in all_rows:
        kind = s["kind"]
        if kind == "module":
            continue  # modules are not ctags entries
        name = s["name"]
        path = s["path"]
        line = s["range"]["start_line"]
        lines = file_lines.get(path)
        text = lines[line - 1] if lines and 0 <= line - 1 < len(lines) else f"{name}"
        pattern = _ctags_pattern(text)
        scope = None
        scope_kind = None
        parent = s.get("parent_symbol_id")
        if kind == "method" and parent:
            # parent symbol id ends with `Class#`
            scope = parent.split("/")[-1].rstrip("#")
            scope_kind = "class"
        entries.append((name, path, pattern, _CTAGS_KIND_LETTER.get(kind, "v"),
                        line, scope, scope_kind, _CTAGS_KIND_NAME.get(kind, "variable")))

    entries.sort(key=lambda e: (e[0], e[1], e[4]))

    # Legacy tags file
    header = [
        "!_TAG_FILE_FORMAT\t2\t/extended format; --format=1 will not append ;\" to lines/",
        "!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted, 2=foldcase/",
        "!_TAG_PROGRAM_NAME\twiki_generator\t//",
    ]
    lines_out = list(header)
    for name, path, pattern, kl, line, scope, scope_kind, _kn in entries:
        fields = [f"line:{line}", "language:Python"]
        if scope and scope_kind:
            fields.append(f"{scope_kind}:{scope}")
        lines_out.append(f"{name}\t{path}\t{pattern};\"\t{kl}\t" + "\t".join(fields))
    write_text(ctx.paths.tags, "\n".join(lines_out) + "\n")

    # JSON-lines (universal-ctags JSON shape)
    for name, path, pattern, _kl, line, scope, scope_kind, kn in entries:
        row = {"_type": "tag", "name": name, "path": path,
               "pattern": pattern, "kind": kn, "line": line, "language": "Python"}
        if scope and scope_kind:
            row["scope"] = scope
            row["scopeKind"] = scope_kind
        rows.append(row)
    n = write_jsonl(ctx.paths.tags_jsonl, rows)
    return len(entries), n


def _run_universal_ctags(ctx: RunContext) -> tuple[int, int] | None:
    """Run universal-ctags over the repo. Returns (tags_lines, json_lines) or None."""
    ctags = ctx.tools.universal_ctags.path
    excludes = []
    for d in C.IGNORE_DIRS:
        excludes += [f"--exclude={d}"]
    # Legacy tags file
    proc1 = run_cmd([ctags, "-R", "--output-format=u-ctags", *excludes,
                     "-f", ctx.paths.tags, ctx.repo], timeout=180)
    if proc1 is None or proc1.returncode not in (0, 1):
        return None
    # Count lines
    try:
        with open(ctx.paths.tags, "r", encoding="utf-8", errors="replace") as f:
            tag_lines = sum(1 for ln in f if not ln.startswith("!_"))
    except OSError:
        tag_lines = 0
    # JSON output to tags.jsonl
    proc2 = run_cmd([ctags, "-R", "--output-format=json", *excludes,
                     "-f", "-", ctx.repo], timeout=180)
    json_lines = 0
    if proc2 is not None and proc2.stdout:
        # ctags JSON emits one object per line already.
        out = [ln for ln in proc2.stdout.splitlines() if ln.strip()]
        write_text(ctx.paths.tags_jsonl, "\n".join(out) + ("\n" if out else ""))
        json_lines = len(out)
    return tag_lines, json_lines


# --- references / occurrences --------------------------------------------------
def _resolve_calls(ctx: RunContext, all_calls, symbols, modules, mod2path):
    """Approximate call resolution -> reference occurrences + CALLS_APPROX edges."""
    # name -> symbol records (definitions); modules are not call targets
    by_name: dict[str, list[dict]] = {}
    for s in symbols:
        if s["kind"] == "module":
            continue
        by_name.setdefault(s["name"], []).append(s)
    # per-module top-level function/class name -> symbol
    top_by_module: dict[str, dict[str, dict]] = {}
    for s in symbols:
        if s["kind"] != "module" and s["parent_symbol_id"] \
                and s["parent_symbol_id"].endswith("/"):
            top_by_module.setdefault(s["module"], {})[s["name"]] = s
    # per-file imported alias -> internal symbol (best effort, module-level)
    alias_to_symbol: dict[str, dict[str, dict]] = {}
    for path, parser in modules.items():
        amap: dict[str, dict] = {}
        for imp in parser.imports:
            tgt = _resolve_import_target(imp, path, mod2path)
            if not tgt:
                continue
            tgt_module = ids.module_dotted(tgt)
            for n in imp.get("names", []):
                alias = n["asname"] or n["name"]
                # from pkg.mod import name  -> name defined in tgt module
                cand = top_by_module.get(tgt_module, {}).get(n["name"])
                if cand:
                    amap[alias] = cand
        alias_to_symbol[path] = amap

    references: list[dict] = []
    calls_edges: list[dict] = []
    unresolved = 0
    for c in all_calls:
        caller = c["caller_symbol_id"]
        path = c["_path"]
        name = c["name"]
        target = None
        confidence = None
        # 1) same-module top-level
        module = ids.module_dotted(path)
        if name in top_by_module.get(module, {}):
            target = top_by_module[module][name]
            confidence = "medium"
        # 2) imported alias (bare name calls)
        elif c["attr_obj"] is None and name in alias_to_symbol.get(path, {}):
            target = alias_to_symbol[path][name]
            confidence = "medium"
        # 3) globally unique symbol name
        elif name in by_name and len(by_name[name]) == 1:
            target = by_name[name][0]
            confidence = "low"
        if target is None:
            unresolved += 1
            continue
        if target["symbol_id"] == caller:
            continue  # ignore trivial self/recursion noise at this approximation
        references.append({
            "symbol_id": target["symbol_id"],
            "path": path,
            "range": {"start_line": c["line"], "end_line": c["line"]},
            "role": "reference",
            "name": name,
            "via": "call",
            "from_symbol_id": caller,
            "confidence": confidence,
        })
        calls_edges.append({
            "from_symbol_id": caller,
            "to_symbol_id": target["symbol_id"],
            "path": path,
            "line": c["line"],
            "confidence": confidence,
        })
    return references, calls_edges, unresolved


def build(ctx: RunContext, inv: dict) -> dict:
    repo = ctx.repo
    py = [r for r in inv["files"] if r["language"] == "python" and r["indexable"]]
    py_all = {r["path"] for r in inv["files"] if r["language"] == "python"}
    mod2path = _module_to_path(py_all)

    modules: dict[str, _ModuleParser] = {}
    symbols: list[dict] = []
    imports_rows: list[dict] = []
    routes: list[dict] = []
    errors: list[dict] = []
    all_calls: list[dict] = []
    constants_rows: list[dict] = []
    file_lines: dict[str, list[str]] = {}

    for rec in py:
        ap = os.path.join(repo, rec["path"])
        text = read_text(ap, C.MAX_FILE_BYTES_FOR_TEXT)
        if text is None:
            continue
        file_lines[rec["path"]] = text.split("\n")
        parser = _ModuleParser(text, rec["path"]).parse()
        modules[rec["path"]] = parser
        if parser.error:
            errors.append({"path": rec["path"], "error": parser.error})
            continue
        # Materialize the module itself as a first-class symbol so that
        # module-header spans and top-level parent_symbol_id links resolve.
        # Guarded on non-empty content to match the rag lane (which skips empty
        # files), keeping the symbol<->span invariant for empty __init__.py etc.
        if text.strip():
            nlines = len(file_lines[rec["path"]])
            hdr_last = module_header_last(parser.first_def_line, nlines)
            symbols.append({
                "symbol_id": ids.module_symbol_id(parser.module),
                "name": parser.module or rec["path"],
                "kind": "module",
                "path": rec["path"],
                "module": parser.module,
                "range": {"start_line": 1, "end_line": max(nlines, 1)},
                "signature": None,
                "parent_symbol_id": None,
                "decorators": [], "bases": [], "is_async": False,
                "docstring": parser.module_doc,
                "span_id": ids.span_id(rec["path"], 1, hdr_last, "module_header"),
            })
        symbols.extend(parser.symbols)
        routes.extend(parser.routes)
        for c in parser.calls:
            c["_path"] = rec["path"]
            all_calls.append(c)
        for con in parser.constants:
            constants_rows.append({
                "name": con["name"], "kind": "constant", "path": rec["path"],
                "module": parser.module,
                "range": {"start_line": con["lineno"], "end_line": con["lineno"]},
                "parent_symbol_id": ids.module_symbol_id(parser.module),
            })
        # imports.jsonl rows (resolved)
        for imp in parser.imports:
            tgt = _resolve_import_target(imp, rec["path"], mod2path)
            imports_rows.append({
                "path": rec["path"],
                "lineno": imp["lineno"],
                "kind": imp["kind"],
                "module": imp.get("module"),
                "level": imp.get("level", 0),
                "names": imp["names"],
                "is_internal": tgt is not None,
                "resolved_path": tgt,
            })

    # symbols.jsonl
    symbols.sort(key=lambda s: (s["path"], s["range"]["start_line"]))
    n_sym = write_jsonl(ctx.paths.symbols_jsonl, symbols)
    ctx.count("symbols/symbols.jsonl", n_sym)
    ctx.record(ctx.paths.symbols_jsonl, produced_by="python ast",
               description="symbol index: id, kind, range, signature, parent, doc",
               rows=n_sym,
               note=f"{len(errors)} parse error(s)" if errors else None)

    # imports.jsonl
    imports_rows.sort(key=lambda r: (r["path"], r["lineno"]))
    n_imp = write_jsonl(ctx.paths.imports_jsonl, imports_rows)
    ctx.count("symbols/imports.jsonl", n_imp)
    ctx.record(ctx.paths.imports_jsonl, produced_by="python ast",
               description="import statements with internal-target resolution",
               rows=n_imp)

    # occurrences.jsonl = definitions + approximate references
    references, calls_edges, unresolved = _resolve_calls(
        ctx, all_calls, symbols, modules, mod2path)
    occ_rows: list[dict] = []
    for s in symbols:
        occ_rows.append({
            "symbol_id": s["symbol_id"],
            "path": s["path"],
            "range": {"start_line": s["range"]["start_line"],
                      "end_line": s["range"]["start_line"]},
            "role": "definition",
            "name": s["name"],
            "confidence": "high",
        })
    occ_rows.extend(references)
    occ_rows.sort(key=lambda r: (r["path"], r["range"]["start_line"], r["role"]))
    n_occ = write_jsonl(ctx.paths.occurrences_jsonl, occ_rows)
    ctx.count("symbols/occurrences.jsonl", n_occ)
    ctx.record(ctx.paths.occurrences_jsonl, produced_by="python ast (approx refs)",
               description="definition occurrences (exact) + name-resolved "
                           "reference occurrences (approximate, with confidence)",
               rows=n_occ,
               note=f"{len(references)} refs resolved, {unresolved} call sites unresolved")
    if unresolved:
        ctx.warn(f"symbols: {unresolved} call sites could not be name-resolved "
                 f"(dynamic dispatch / external); references are approximate.")

    # tags + tags.jsonl
    used_uc = False
    if ctx.tools.universal_ctags.available:
        res = _run_universal_ctags(ctx)
        if res is not None:
            used_uc = True
            tag_lines, json_lines = res
            ctx.count("symbols/tags", tag_lines)
            ctx.count("symbols/tags.jsonl", json_lines)
            ctx.record(ctx.paths.tags, produced_by="universal-ctags",
                       description="ctags symbol index (all languages)", rows=tag_lines)
            ctx.record(ctx.paths.tags_jsonl, produced_by="universal-ctags",
                       description="ctags JSON-lines symbol index", rows=json_lines)
        else:
            ctx.warn("universal-ctags present but failed to run; using AST-derived tags.")
    if not used_uc:
        tag_lines, json_lines = _write_ast_tags(ctx, symbols, constants_rows, file_lines)
        ctx.count("symbols/tags", tag_lines)
        ctx.count("symbols/tags.jsonl", json_lines)
        note = "AST-derived (universal-ctags not available); Python symbols only"
        ctx.record(ctx.paths.tags, produced_by="python ast",
                   description="ctags-format symbol index", rows=tag_lines, note=note)
        ctx.record(ctx.paths.tags_jsonl, produced_by="python ast",
                   description="ctags JSON-lines symbol index", rows=json_lines, note=note)

    log(f"symbols: {n_sym} symbols, {n_imp} imports, {len(routes)} routes, "
        f"{n_occ} occurrences, {len(errors)} parse errors")
    return {
        "symbols": symbols,
        "imports": imports_rows,
        "routes": routes,
        "modules": modules,
        "mod2path": mod2path,
        "errors": errors,
        "calls_edges": calls_edges,
        "constants": constants_rows,
        "file_lines": file_lines,
    }
