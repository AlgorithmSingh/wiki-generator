"""Retrieval chunker: AST-aligned chunks for Python, heading sections for
Markdown, logical sections for config/deployment, and line windows otherwise.

Returns plain dicts; the rag lane links each chunk to the spans it overlaps and
persists them. Ported from the proven repo-analysis chunker, re-keyed to the
shared id scheme.
"""
from __future__ import annotations

import re

from . import config as C
from . import ids
from .util import clip, sha256_text, token_estimate

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TOML_SECTION = re.compile(r"^\s*\[+([^\]]+)\]+\s*$")
_YAML_TOPKEY = re.compile(r"^([A-Za-z0-9_.\-]+):")
_DOCKER_STAGE = re.compile(r"^\s*FROM\s+.+?(?:\s+AS\s+(\S+))?\s*$", re.IGNORECASE)


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1:end])


def _mk(rec, start, end, kind, text, *, symbol=None, parent=None, decorators=None,
        doc=None, heading_path=None, section=None) -> dict:
    text = clip(text, C.MAX_CHUNK_CHARS)
    return {
        "chunk_id": ids.chunk_id(rec["path"], start, end),
        "path": rec["path"],
        "range": {"start_line": start, "end_line": end},
        "chunk_type": kind,
        "language": rec["language"],
        "category": rec["category"],
        "symbol_name": symbol,
        "parent_symbol": parent,
        "decorators": decorators or [],
        "docstring": doc,
        "heading_path": heading_path,
        "section_name": section,
        "token_estimate": token_estimate(text),
        "sha256": sha256_text(text),
        "span_ids": [],
        "text": text,
    }


def _split_long(rec, start, end, kind, lines, **meta):
    span = end - start + 1
    if span <= C.MAX_CHUNK_LINES:
        yield _mk(rec, start, end, kind, _slice(lines, start, end), **meta)
        return
    s = start
    part = 0
    while s <= end:
        e = min(s + C.MAX_CHUNK_LINES - 1, end)
        m = dict(meta)
        if m.get("symbol"):
            m["symbol"] = f"{m['symbol']}#part{part}"
        yield _mk(rec, s, e, kind + "_part", _slice(lines, s, e), **m)
        part += 1
        if e == end:
            break
        s = e - C.CHUNK_LINE_OVERLAP + 1


def chunk_python(rec, text, parser) -> list[dict]:
    lines = text.split("\n")
    n = len(lines)
    if parser is None or getattr(parser, "error", None):
        return chunk_window(rec, text, kind="code_window")
    chunks: list[dict] = []
    header_end = parser.first_def_line or n
    hdr_last = max(1, min(header_end - 1, n))
    if hdr_last >= 1 and (parser.imports or parser.constants or parser.module_doc):
        chunks.append(_mk(rec, 1, hdr_last, "module_header", _slice(lines, 1, hdr_last),
                          doc=parser.module_doc, symbol="<module>"))
    syms = parser.symbols
    top = [s for s in syms if s["parent_symbol_id"].endswith("/")]
    route_lines = {r["lineno"] for r in parser.routes}
    for s in top:
        start = s["range"]["start_line"]
        end = min(max(s["range"]["end_line"], start), n)
        if s["kind"] == "class":
            methods = [m for m in syms
                       if m["parent_symbol_id"] == s["symbol_id"] and m["kind"] == "method"
                       and start <= m["range"]["start_line"] <= end]
            methods.sort(key=lambda m: m["range"]["start_line"])
            body_start = methods[0]["range"]["start_line"] - 1 if methods else end
            body_start = max(start, min(body_start, end))
            chunks.append(_mk(rec, start, body_start, "class_header",
                              _slice(lines, start, body_start),
                              symbol=s["name"], decorators=s["decorators"], doc=s["docstring"]))
            for mth in methods:
                ms = mth["range"]["start_line"]
                me = min(max(mth["range"]["end_line"], ms), n)
                kind = "route_handler" if ms in route_lines else "method"
                chunks.extend(_split_long(rec, ms, me, kind, lines, symbol=mth["name"],
                                          parent=s["name"], decorators=mth["decorators"],
                                          doc=mth["docstring"]))
        else:
            kind = "route_handler" if start in route_lines else "function"
            chunks.extend(_split_long(rec, start, end, kind, lines, symbol=s["name"],
                                      decorators=s["decorators"], doc=s["docstring"]))
    return chunks


def chunk_markdown(rec, text) -> list[dict]:
    lines = text.split("\n")
    n = len(lines)
    heads = []
    in_fence = False
    for i, ln in enumerate(lines):
        st = ln.lstrip()
        if st.startswith("```") or st.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    if not heads:
        return chunk_window(rec, text, kind="doc_window")
    chunks: list[dict] = []
    if heads[0][0] > 0:
        chunks.append(_mk(rec, 1, heads[0][0], "doc_section", _slice(lines, 1, heads[0][0]),
                          heading_path="(preamble)"))
    stack: list[tuple[int, str]] = []
    for idx, (li, level, title) in enumerate(heads):
        start = li + 1
        end = heads[idx + 1][0] if idx + 1 < len(heads) else n
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        hp = " > ".join(t for _, t in stack)
        chunks.extend(_split_long(rec, start, end, "doc_section", lines,
                                  heading_path=hp, symbol=title))
    return chunks


def chunk_window(rec, text, kind="code_window") -> list[dict]:
    lines = text.split("\n")
    n = len(lines)
    chunks = []
    s = 1
    while s <= n:
        e = min(s + C.WINDOW_LINES_NONPY - 1, n)
        chunks.append(_mk(rec, s, e, kind, _slice(lines, s, e)))
        if e == n:
            break
        s = e - C.CHUNK_LINE_OVERLAP + 1
    return chunks


def chunk_config(rec, text) -> list[dict]:
    lines = text.split("\n")
    n = len(lines)
    ext = rec["ext"]
    name = rec["name"].lower()
    if ext == ".toml":
        return _chunk_by_regex(rec, lines, _TOML_SECTION, "toml_section")
    if name.startswith("dockerfile") or rec["language"] == "dockerfile":
        return _chunk_dockerfile(rec, lines)
    if ext in {".yaml", ".yml"} or rec["language"] == "yaml":
        return _chunk_yaml(rec, lines)
    if ext == ".json":
        return list(_split_long(rec, 1, n, "config", lines, symbol=rec["name"]))
    if n <= C.MAX_CHUNK_LINES:
        return [_mk(rec, 1, n, "config", text, symbol=rec["name"])]
    return chunk_window(rec, text, kind="config")


def _chunk_by_regex(rec, lines, pat, kind) -> list[dict]:
    n = len(lines)
    idxs = [i for i, ln in enumerate(lines) if pat.match(ln)]
    if not idxs:
        return [_mk(rec, 1, n, kind, "\n".join(lines), symbol=rec["name"])]
    chunks = []
    if idxs[0] > 0:
        chunks.append(_mk(rec, 1, idxs[0], kind, _slice(lines, 1, idxs[0]), section="(preamble)"))
    for j, i in enumerate(idxs):
        start = i + 1
        end = idxs[j + 1] if j + 1 < len(idxs) else n
        m = pat.match(lines[i])
        sec = m.group(1).strip() if m and m.groups() else lines[i].strip()
        chunks.append(_mk(rec, start, end, kind, _slice(lines, start, end), section=sec, symbol=sec))
    return chunks


def _chunk_dockerfile(rec, lines) -> list[dict]:
    n = len(lines)
    idxs = [i for i, ln in enumerate(lines) if _DOCKER_STAGE.match(ln)]
    if not idxs:
        return [_mk(rec, 1, n, "dockerfile", "\n".join(lines), symbol=rec["name"])]
    chunks = []
    for j, i in enumerate(idxs):
        start = i + 1
        end = idxs[j + 1] if j + 1 < len(idxs) else n
        m = _DOCKER_STAGE.match(lines[i])
        stage = (m.group(1) if m and m.group(1) else f"stage{j}")
        chunks.append(_mk(rec, start, end, "dockerfile_stage", _slice(lines, start, end),
                          section=stage, symbol=stage))
    return chunks


def _chunk_yaml(rec, lines) -> list[dict]:
    n = len(lines)
    top = []
    for i, ln in enumerate(lines):
        if not ln or ln[0] in " #\t-":
            continue
        m = _YAML_TOPKEY.match(ln)
        if m:
            top.append((i, m.group(1)))
    if not top:
        return [_mk(rec, 1, n, "yaml", "\n".join(lines), symbol=rec["name"])]
    chunks = []
    if top[0][0] > 0:
        chunks.append(_mk(rec, 1, top[0][0], "yaml", _slice(lines, 1, top[0][0]), section="(preamble)"))
    for j, (i, key) in enumerate(top):
        start = i + 1
        end = top[j + 1][0] if j + 1 < len(top) else n
        if key == "services":
            chunks.extend(_chunk_compose_services(rec, lines, start, end))
        else:
            chunks.extend(_split_long(rec, start, end, "yaml", lines, section=key, symbol=key))
    return chunks


def _chunk_compose_services(rec, lines, start, end) -> list[dict]:
    svc_idx = []
    base_indent = None
    for i in range(start, end):
        ln = lines[i - 1] if i - 1 < len(lines) else ""
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip(" "))
        if base_indent is None and indent > 0:
            base_indent = indent
        if base_indent is not None and indent == base_indent and ln.rstrip().endswith(":"):
            svc_idx.append((i, ln.strip().rstrip(":")))
    if not svc_idx:
        return list(_split_long(rec, start, end, "yaml", lines, section="services", symbol="services"))
    chunks = []
    for j, (i, name) in enumerate(svc_idx):
        s = i
        e = svc_idx[j + 1][0] - 1 if j + 1 < len(svc_idx) else end
        chunks.append(_mk(rec, s, e, "compose_service", _slice(lines, s, e), section=name, symbol=name))
    return chunks


def chunk_file(rec, text, parser) -> list[dict]:
    """Dispatch a file record + text to the right chunker."""
    lang, cat = rec["language"], rec["category"]
    if lang == "python":
        return chunk_python(rec, text, parser)
    if lang in {"markdown", "rst"} or cat == "docs":
        return chunk_markdown(rec, text)
    if cat == "config" or lang in {"toml", "yaml", "ini", "json", "dotenv"}:
        return chunk_config(rec, text)
    if cat == "deployment":
        if lang in {"yaml", "dockerfile"}:
            return chunk_config(rec, text)
        return chunk_window(rec, text, kind="deploy_window")
    return chunk_window(rec, text, kind="code_window")
