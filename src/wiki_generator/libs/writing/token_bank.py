"""Deterministic per-section *token bank* for Phase 4 grounded generation.

The token bank is the upstream-prevention foundation for the claim/token planning
slice. For one section it extracts, from that section's validated EvidencePacket
items, the exact terminal *technical tokens* the writer is allowed to emit:
routes, file paths, imports, module/class/function/method names, env vars,
commands, JSON pointers, package names, and code/config literals.

The single load-bearing invariant is **verbatim grounding**: every
``TokenEntry.token`` is a verbatim substring of the excerpt or serialized
``source``/``provenance`` metadata of at least one of its ``evidence_ids``. A
token is therefore extracted only because it already appears in cited evidence;
it is never synthesized. In particular a *composite* technical string (a dotted
name like ``quart_auth.AuthUser`` or ``Parser._pdf``, a normalized route like
``/api/{api_version}``, a JSON path like ``data.graph``, or a route-family
ellipsis like ``/api/v1/...``) lands in the bank ONLY when that exact composite
appears verbatim in evidence. The downstream claim plan may reference terminal
technical strings only by ``token_id``; the renderer substitutes the exact bank
string. Synthesized composites are thus unrepresentable in the grounded path —
they are not in the bank, so there is no id to select.

This module is pure and deterministic: same evidence in, byte-identical bank out.
It never calls a model and never mutates the bundle.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .schema import TOKEN_BANK_SCHEMA_VERSION

# --- token kinds --------------------------------------------------------------
# Stable, documented kind vocabulary. Kinds are advisory metadata for the writer
# and the audit trail; the verbatim invariant — not the kind label — is what
# keeps a token grounded.
K_ROUTE = "route"
K_HTTP_METHOD = "http_method"
K_FILE_PATH = "file_path"
K_JSON_POINTER = "json_pointer"
K_ENV_VAR = "env_var"
K_COMMAND = "command"
K_MODULE = "module"
K_PACKAGE = "package"
K_IMPORT = "import"
K_SYMBOL = "symbol"
K_LITERAL = "literal"

KINDS = frozenset({
    K_ROUTE, K_HTTP_METHOD, K_FILE_PATH, K_JSON_POINTER, K_ENV_VAR, K_COMMAND,
    K_MODULE, K_PACKAGE, K_IMPORT, K_SYMBOL, K_LITERAL,
})

# When the same exact string is discovered as more than one kind, keep the most
# specific/safest single kind (one entry per distinct string keeps the bank and
# its ids clean). Lower number == higher priority.
_KIND_PRIORITY = {
    K_ROUTE: 0, K_HTTP_METHOD: 1, K_FILE_PATH: 2, K_JSON_POINTER: 3,
    K_ENV_VAR: 4, K_COMMAND: 5, K_MODULE: 6, K_PACKAGE: 7, K_IMPORT: 8,
    K_SYMBOL: 9, K_LITERAL: 10,
}

# File extensions that retag a dotted/slashed token as a file path rather than a
# dotted symbol (so ``service_conf.yaml`` is not mistaken for ``module.attr``).
_FILE_EXTS = frozenset({
    "py", "pyi", "js", "jsx", "ts", "tsx", "go", "rs", "java", "rb", "php",
    "c", "h", "cc", "cpp", "hpp", "cs", "sh", "bash", "zsh", "yaml", "yml",
    "json", "toml", "ini", "cfg", "conf", "env", "md", "mdx", "txt", "tpl",
    "template", "sql", "proto", "tf", "dockerfile", "lock",
})

# Conservative command leaders: a line beginning with one of these is captured
# verbatim as a ``command`` token.
_COMMAND_LEADERS = frozenset({
    "docker", "docker-compose", "python", "python3", "pip", "pip3", "uv",
    "npm", "npx", "yarn", "pnpm", "make", "bash", "sh", "zsh", "git", "curl",
    "wget", "kubectl", "helm", "pytest", "go", "cargo", "poetry", "gunicorn",
    "uvicorn", "celery", "flask", "alembic",
})


# --- token entry --------------------------------------------------------------
@dataclass
class TokenEntry:
    """One exact, verbatim-grounded terminal technical token.

    ``token_id`` is a stable handle (``tok:<section_id>:<NNNN>``); ``token`` is the
    exact string; ``kind`` is advisory; ``evidence_ids`` are the citeable items the
    token appears in (the writer must cite at least one when selecting it); and
    ``provenance`` records, per evidence id, *how* the token was found (audit only)."""

    token_id: str
    token: str
    kind: str
    evidence_ids: list = field(default_factory=list)
    provenance: list = field(default_factory=list)  # [{evidence_id, via}]

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "token": self.token,
            "kind": self.kind,
            "evidence_ids": list(self.evidence_ids),
            "provenance": [dict(p) for p in self.provenance],
        }


@dataclass
class TokenBank:
    """The per-section token bank: a stable, deduplicated list of entries plus
    cheap lookups by id and by exact string."""

    section_id: str
    tokens: list = field(default_factory=list)   # list[TokenEntry]

    def by_id(self) -> dict:
        return {t.token_id: t for t in self.tokens}

    def by_token(self) -> dict:
        return {t.token: t for t in self.tokens}

    def to_dict(self) -> dict:
        return {
            "schema_version": TOKEN_BANK_SCHEMA_VERSION,
            "section_id": self.section_id,
            "count": len(self.tokens),
            "tokens": [t.to_dict() for t in self.tokens],
        }


# --- extraction regexes (all matches are verbatim substrings of the source) ---
_IMPORT_FROM_RE = re.compile(r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]+(.+?)[ \t]*$",
                             re.MULTILINE)
_IMPORT_PLAIN_RE = re.compile(r"^[ \t]*import[ \t]+([\w.]+(?:[ \t]+as[ \t]+\w+)?)[ \t]*$",
                              re.MULTILINE)
_CLASS_DEF_RE = re.compile(r"\bclass[ \t]+([A-Za-z_]\w*)")
_FUNC_DEF_RE = re.compile(r"\b(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)")
# A dotted composite: a.b, a.b.c, Class.method, module.symbol — captured ONLY when
# it appears verbatim. (Never assembled from separate tokens.)
_DOTTED_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")
# A leading-slash token: a route (/agents, /api/{id}) or an absolute path
# (/ragflow/conf/service_conf.yaml). Includes the ASCII ellipsis ``...`` and the
# unicode ellipsis glyph so a verbatim route-family token can be banked when (and
# only when) it actually appears in evidence. The lookbehind keeps the leading
# slash at a token boundary so a mid-path slash is not split out of a larger path
# (e.g. ``pkg/api/routes.py`` does not yield a bogus ``/api/routes.py``).
_SLASH_TOKEN_RE = re.compile(r"(?<![\w.])/[A-Za-z0-9_./{}:…-]+")
_METHOD_PATH_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)[ \t]+(/[A-Za-z0-9_./{}:…-]*)")
_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
# A relative path with a slash and a file extension (pkg/svc.py, docker/entrypoint.sh).
_REL_PATH_RE = re.compile(r"\b[\w.+-]+(?:/[\w.+-]+)+\.[A-Za-z0-9]{1,8}\b")


def _ext(token: str) -> str | None:
    base = token.rstrip("/")
    dot = base.rfind(".")
    if dot < 0 or dot == len(base) - 1:
        return None
    return base[dot + 1:].lower()


def _classify_slash_token(tok: str) -> str:
    """A leading-slash token is a file path when it ends in a known file
    extension, otherwise a route (``/api/{id}``, ``/agents``, ``/api/v1/...``)."""
    ext = _ext(tok)
    if ext and ext in _FILE_EXTS:
        return K_FILE_PATH
    return K_ROUTE


def _classify_dotted_token(tok: str) -> str:
    """A dotted token is a file path when its last segment is a file extension
    (``service_conf.yaml``), otherwise a dotted symbol (``module.attr``)."""
    ext = _ext(tok)
    if ext and ext in _FILE_EXTS:
        return K_FILE_PATH
    return K_SYMBOL


# --- per-evidence extraction --------------------------------------------------
def _structured_candidates(source: dict, provenance: dict) -> list:
    """Exact tokens from an evidence item's structured ``source``/``provenance``
    metadata. Each value is, by definition, a verbatim field value."""
    out: list = []

    def add(value, kind, via):
        if isinstance(value, str) and value.strip():
            out.append((value.strip(), kind, via))

    add(source.get("route"), K_ROUTE, "source.route")
    add(source.get("public_route"), K_ROUTE, "source.public_route")
    add(source.get("method"), K_HTTP_METHOD, "source.method")
    add(source.get("path"), K_FILE_PATH, "source.path")
    add(source.get("symbol_name"), K_SYMBOL, "source.symbol_name")
    add(source.get("json_pointer"), K_JSON_POINTER, "source.json_pointer")
    add(provenance.get("x_source"), K_FILE_PATH, "provenance.x_source")
    return out


def _excerpt_candidates(excerpt: str) -> list:
    """Exact technical tokens scanned out of an evidence excerpt. Every returned
    string is a substring of ``excerpt`` (so the verbatim invariant holds), and
    composites are captured only when they appear literally — never assembled."""
    out: list = []
    if not excerpt:
        return out

    # imports: capture the module path, its top-level package, each imported name,
    # and the full import line. A package context is NEVER joined to a name.
    for m in _IMPORT_FROM_RE.finditer(excerpt):
        module, names = m.group(1), m.group(2)
        out.append((module, K_MODULE, "excerpt:import_from.module"))
        top = module.split(".", 1)[0]
        if top != module:
            out.append((top, K_PACKAGE, "excerpt:import_from.package"))
        out.append((m.group(0).strip(), K_IMPORT, "excerpt:import_from.line"))
        for piece in names.split(","):
            name = piece.strip()
            if name in ("(", ")", "", "*"):
                continue
            name = name.strip("()").strip()
            for part in re.split(r"\s+as\s+", name):
                part = part.strip()
                if re.fullmatch(r"[A-Za-z_]\w*", part):
                    out.append((part, K_SYMBOL, "excerpt:import_from.name"))
    for m in _IMPORT_PLAIN_RE.finditer(excerpt):
        spec = m.group(1)
        module = re.split(r"\s+as\s+", spec)[0].strip()
        alias = None
        if " as " in spec:
            alias = spec.split(" as ", 1)[1].strip()
        out.append((module, K_MODULE, "excerpt:import.module"))
        top = module.split(".", 1)[0]
        if top != module:
            out.append((top, K_PACKAGE, "excerpt:import.package"))
        if alias and re.fullmatch(r"[A-Za-z_]\w*", alias):
            out.append((alias, K_SYMBOL, "excerpt:import.alias"))

    for m in _CLASS_DEF_RE.finditer(excerpt):
        out.append((m.group(1), K_SYMBOL, "excerpt:class_def"))
    for m in _FUNC_DEF_RE.finditer(excerpt):
        out.append((m.group(1), K_SYMBOL, "excerpt:func_def"))

    for m in _METHOD_PATH_RE.finditer(excerpt):
        out.append((m.group(1), K_HTTP_METHOD, "excerpt:method"))
        out.append((m.group(2), _classify_slash_token(m.group(2)), "excerpt:method_path"))

    for m in _DOTTED_RE.finditer(excerpt):
        tok = m.group(0)
        out.append((tok, _classify_dotted_token(tok), "excerpt:dotted"))
    for m in _SLASH_TOKEN_RE.finditer(excerpt):
        tok = m.group(0).rstrip("/") or m.group(0)
        out.append((tok, _classify_slash_token(tok), "excerpt:slash_token"))
    for m in _REL_PATH_RE.finditer(excerpt):
        out.append((m.group(0), K_FILE_PATH, "excerpt:rel_path"))
    for m in _ENV_RE.finditer(excerpt):
        out.append((m.group(0), K_ENV_VAR, "excerpt:env_var"))

    for raw_line in excerpt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        leader = line.split()[0] if line.split() else ""
        if leader in _COMMAND_LEADERS and " " in line:
            out.append((line, K_COMMAND, "excerpt:command"))
    return out


# --- bank assembly ------------------------------------------------------------
def build_token_bank(bundle, section_id: str) -> TokenBank:
    """Deterministically build the token bank for one section from its validated
    evidence. Tokens are deduplicated by exact string (most-specific kind wins),
    sorted by ``(kind, token)``, and assigned stable ``tok:<section_id>:NNNN`` ids."""
    # token string -> {"kind", "evidence_ids": set, "provenance": list}
    acc: dict = {}

    eids = sorted(bundle.section_evidence_ids.get(section_id, set()))
    for eid in eids:
        item = bundle.evidence_index.get(eid)
        if item is None:
            continue
        candidates = _structured_candidates(item.source or {}, item.provenance or {})
        candidates += _excerpt_candidates(item.excerpt or "")
        for token, kind, via in candidates:
            if not token or kind not in KINDS:
                continue
            rec = acc.get(token)
            if rec is None:
                rec = {"kind": kind, "evidence_ids": set(), "provenance": []}
                acc[token] = rec
            elif _KIND_PRIORITY[kind] < _KIND_PRIORITY[rec["kind"]]:
                rec["kind"] = kind
            rec["evidence_ids"].add(eid)
            prov = {"evidence_id": eid, "via": via}
            if prov not in rec["provenance"]:
                rec["provenance"].append(prov)

    ordered = sorted(acc.items(),
                     key=lambda kv: (_KIND_PRIORITY[kv[1]["kind"]], kv[0]))
    tokens: list = []
    for i, (token, rec) in enumerate(ordered, 1):
        tokens.append(TokenEntry(
            token_id=f"tok:{section_id}:{i:04d}",
            token=token,
            kind=rec["kind"],
            evidence_ids=sorted(rec["evidence_ids"]),
            provenance=sorted(rec["provenance"],
                              key=lambda p: (p["evidence_id"], p["via"])),
        ))
    return TokenBank(section_id=section_id, tokens=tokens)


def token_grounding_text(item) -> str:
    """The text a token must be a verbatim substring of to count as grounded in
    one evidence ``item``: its excerpt plus its serialized source/provenance."""
    return "\n".join([
        item.excerpt or "",
        json.dumps(item.source or {}, ensure_ascii=False, sort_keys=True, default=str),
        json.dumps(item.provenance or {}, ensure_ascii=False, sort_keys=True,
                   default=str),
    ])


def verify_bank_grounding(bundle, bank: TokenBank) -> list:
    """Return a list of integrity violations (empty == every token is verbatim in
    at least one of its evidence items). Used by tests and as a defensive
    self-check; deterministic code never ships an ungrounded token bank."""
    problems: list = []
    for entry in bank.tokens:
        if not entry.evidence_ids:
            problems.append(f"{entry.token_id} ({entry.token!r}) has no evidence_ids")
            continue
        ok = False
        for eid in entry.evidence_ids:
            item = bundle.evidence_index.get(eid)
            if item is not None and entry.token in token_grounding_text(item):
                ok = True
                break
        if not ok:
            problems.append(
                f"{entry.token_id} ({entry.token!r}) is not a verbatim substring of "
                f"any of its evidence items {entry.evidence_ids}")
    return problems
