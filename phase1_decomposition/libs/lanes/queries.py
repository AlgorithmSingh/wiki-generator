"""Queries lane — deterministic pattern searches over common repo surfaces.

Artifacts:
  queries/rules/rg/<pack>.json     the query-pack rule definitions
  queries/results/rg.jsonl         digested per-match rows (pack-tagged)
  queries/results/grep-ast/<pack>.md   AST-context previews (grep-ast or built-in)
  queries/results/semgrep.json     semgrep results (or a well-formed skip note)
  queries/results/semgrep.sarif    semgrep SARIF (or a minimal valid skeleton)
  queries/results/ast-grep.json    ast-grep results (or a well-formed skip note)

These are query *results*, not a canonical fact schema.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

from .. import config as C
from ... import SCHEMA_VERSION
from ..context import RunContext
from ..tools import run as run_cmd
from ..util import read_text, write_json, write_jsonl, write_text, log


def _write_rules(ctx: RunContext, rg_data) -> int:
    n = 0
    for rule in rg_data.rules:
        write_json(os.path.join(ctx.paths.queries_rules_rg, f"{rule['name']}.json"), rule)
        n += 1
    ctx.record(ctx.paths.queries_rules_rg, produced_by="phase1 query packs",
               description="ripgrep rule definitions (one JSON per pack)", rows=n)
    return n


def _write_digest(ctx: RunContext, rg_data) -> int:
    n = write_jsonl(ctx.paths.rg_jsonl, rg_data.matches)
    ctx.count("queries/results/rg.jsonl", n)
    ctx.record(ctx.paths.rg_jsonl, produced_by="ripgrep --json",
               description="digested per-match rows (pack/path/line/text)", rows=n,
               note=None if rg_data.available else "ripgrep unavailable")
    return n


# --- grep-ast previews ---------------------------------------------------------
def _enclosing_symbol(parser, line: int):
    best = None
    for s in getattr(parser, "symbols", []):
        # extend the start upward over decorator lines (ast.lineno is the def line)
        a = s["range"]["start_line"] - len(s.get("decorators") or [])
        b = s["range"]["end_line"]
        if a <= line <= b:
            if best is None or (b - a) < (best["range"]["end_line"]
                                          - best["range"]["start_line"]):
                best = s
    return best


def _builtin_preview(ctx: RunContext, sym: dict, rule: dict,
                     matches: list[dict]) -> str:
    """Deterministic AST-aware preview: each match shown inside its enclosing
    Python symbol, with a few context lines. The built-in equivalent of grep-ast."""
    modules = sym.get("modules", {})
    file_lines = sym.get("file_lines", {})
    cap = ctx.opts.max_grep_ast_matches
    L = [f"# grep-ast preview — `{rule['name']}`", "",
         f"_{rule['why']}_", "",
         f"Pattern: `{rule['pattern']}`", ""]
    if not matches:
        L.append("_No matches._")
        return "\n".join(L) + "\n"
    by_file = defaultdict(list)
    for m in matches:
        by_file[m["path"]].append(m)
    shown = 0
    for path in sorted(by_file):
        if shown >= cap:
            break
        L.append(f"## `{path}`")
        L.append("")
        parser = modules.get(path)
        lines = file_lines.get(path)
        if lines is None:
            txt = read_text(os.path.join(ctx.repo, path), C.MAX_FILE_BYTES_FOR_TEXT)
            lines = txt.split("\n") if txt else []
        for m in sorted(by_file[path], key=lambda x: x["line"]):
            if shown >= cap:
                L.append("")
                L.append(f"_…more matches in this pack truncated at {cap}._")
                break
            ln = m["line"]
            enc = _enclosing_symbol(parser, ln) if parser else None
            if enc:
                L.append(f"- **L{ln}** in `{enc['symbol_id']}` — "
                         f"`{enc.get('signature') or enc['name']}`")
            else:
                L.append(f"- **L{ln}** (module level)")
            lo = max(1, ln - 2)
            hi = min(len(lines), ln + 2)
            L.append("")
            L.append("```python")
            for i in range(lo, hi + 1):
                marker = "›" if i == ln else " "
                content = lines[i - 1] if i - 1 < len(lines) else ""
                L.append(f"{marker} {i:>5} {content}")
            L.append("```")
            L.append("")
            shown += 1
    return "\n".join(L) + "\n"


def _grep_ast_preview(ctx: RunContext, rule: dict, files: list[str]) -> str | None:
    """Run the real grep-ast tool on a small file set; None if it fails."""
    if not files:
        return None
    cmd = [sys.executable, "-m", "grep_ast.main", "--no-color", "-n",
           rule["pattern"], *files]
    proc = run_cmd(cmd, timeout=60)
    if proc is None or proc.returncode != 0 or "Traceback" in (proc.stderr or ""):
        return None
    out = proc.stdout or ""
    if not out.strip():
        return None
    header = (f"# grep-ast preview — `{rule['name']}`\n\n_{rule['why']}_\n\n"
              f"Pattern: `{rule['pattern']}`\n\n```\n")
    return header + out.rstrip("\n") + "\n```\n"


def _previews(ctx: RunContext, sym: dict, rg_data) -> None:
    by_pack = defaultdict(list)
    for m in rg_data.matches:
        by_pack[m["pack"]].append(m)
    use_grep_ast = (ctx.tools.grep_ast.available and ctx.opts.grep_ast != "off") \
        or ctx.opts.grep_ast == "on"
    method = "grep-ast" if use_grep_ast else "built-in AST preview"
    n = 0
    for rule in rg_data.rules:
        pack = rule["name"]
        matches = by_pack.get(pack, [])
        content = None
        if use_grep_ast:
            top_files = []
            seen = set()
            for m in matches:
                if m["path"] not in seen:
                    seen.add(m["path"])
                    top_files.append(os.path.join(ctx.repo, m["path"]))
                if len(top_files) >= 12:
                    break
            if top_files:
                content = _grep_ast_preview(ctx, rule, top_files)
                if content is None:
                    # Real failure (had files, got nothing): degrade for all packs.
                    ctx.warn("grep-ast failed at runtime; using built-in AST previews.")
                    use_grep_ast = False
                    method = "built-in AST preview"
        if content is None:
            content = _builtin_preview(ctx, sym, rule, matches)
        write_text(os.path.join(ctx.paths.queries_grep_ast, f"{pack}.md"), content)
        n += 1
    ctx.count("queries/results/grep-ast", n)
    ctx.record(ctx.paths.queries_grep_ast, produced_by=method,
               description="AST-context previews per query pack (markdown)", rows=n,
               note=None if ctx.tools.grep_ast.available else
               "grep-ast unavailable; built-in AST preview used")


# --- semgrep -------------------------------------------------------------------
def _semgrep(ctx: RunContext) -> None:
    want = ctx.opts.semgrep
    avail = ctx.tools.semgrep.available
    if want == "off" or (want == "auto" and not avail):
        reason = "disabled" if want == "off" else (ctx.tools.semgrep.note or "not installed")
        _skip_semgrep(ctx, reason)
        return
    if want == "on" and not avail:
        _skip_semgrep(ctx, "semgrep requested but not installed")
        ctx.warn("--semgrep on but semgrep is not installed.")
        return
    # Run semgrep with the auto config (registry rules). Network may be needed.
    proc = run_cmd([ctx.tools.semgrep.path, "scan", "--config", "auto",
                    "--json", "--quiet", ctx.repo], timeout=300)
    if proc is None or proc.returncode not in (0, 1) or not (proc.stdout or "").strip():
        _skip_semgrep(ctx, "semgrep run failed (no rules/network or error)")
        ctx.warn("semgrep run failed; wrote skip notes.")
        return
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        _skip_semgrep(ctx, "semgrep produced unparseable JSON")
        return
    write_json(ctx.paths.semgrep_json, data)
    n = len(data.get("results", []))
    ctx.count("queries/results/semgrep.json", n)
    ctx.record(ctx.paths.semgrep_json, produced_by="semgrep",
               description="semgrep findings (JSON)", rows=n)
    # SARIF
    sarif = run_cmd([ctx.tools.semgrep.path, "scan", "--config", "auto",
                     "--sarif", "--quiet", ctx.repo], timeout=300)
    if sarif is not None and (sarif.stdout or "").strip():
        write_text(ctx.paths.semgrep_sarif, sarif.stdout)
        ctx.record(ctx.paths.semgrep_sarif, produced_by="semgrep",
                   description="semgrep findings (SARIF)")
    else:
        _write_empty_sarif(ctx, "semgrep SARIF run failed")


def _skip_semgrep(ctx: RunContext, reason: str) -> None:
    write_json(ctx.paths.semgrep_json, {
        "schema_version": SCHEMA_VERSION, "tool": "semgrep", "skipped": True,
        "reason": reason, "results": [], "errors": []})
    ctx.record(ctx.paths.semgrep_json, produced_by="(skipped)",
               description="semgrep findings", skipped=True, note=reason)
    _write_empty_sarif(ctx, reason)


def _write_empty_sarif(ctx: RunContext, reason: str) -> None:
    write_json(ctx.paths.semgrep_sarif, {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
                   "Schemata/sarif-schema-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "semgrep", "rules": []}},
                  "results": [], "properties": {"skipped": True, "reason": reason}}],
    })
    ctx.record(ctx.paths.semgrep_sarif, produced_by="(skipped)",
               description="semgrep SARIF", skipped=True, note=reason)


# --- ast-grep ------------------------------------------------------------------
# A few language-agnostic structural patterns for Python surfaces.
_AST_GREP_PATTERNS = [
    {"id": "function-def", "pattern": "def $NAME($$$ARGS): $$$BODY"},
    {"id": "async-function-def", "pattern": "async def $NAME($$$ARGS): $$$BODY"},
    {"id": "class-def", "pattern": "class $NAME($$$BASES): $$$BODY"},
]


def _ast_grep(ctx: RunContext) -> None:
    want = ctx.opts.ast_grep
    avail = ctx.tools.ast_grep.available
    if want == "off" or (want == "auto" and not avail):
        reason = "disabled" if want == "off" else (ctx.tools.ast_grep.note or "not installed")
        _skip_ast_grep(ctx, reason)
        return
    if want == "on" and not avail:
        _skip_ast_grep(ctx, "ast-grep requested but not installed")
        ctx.warn("--ast-grep on but ast-grep is not installed.")
        return
    binary = ctx.tools.ast_grep.path
    all_matches = []
    for pat in _AST_GREP_PATTERNS:
        proc = run_cmd([binary, "run", "-p", pat["pattern"], "-l", "python",
                        "--json", ctx.repo], timeout=180)
        if proc is None or not (proc.stdout or "").strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            continue
        for m in (data if isinstance(data, list) else []):
            m["_rule_id"] = pat["id"]
            all_matches.append(m)
    if not all_matches:
        _skip_ast_grep(ctx, "ast-grep produced no matches or failed")
        return
    write_json(ctx.paths.ast_grep_json, {"tool": "ast-grep",
                                         "patterns": _AST_GREP_PATTERNS,
                                         "matches": all_matches})
    ctx.count("queries/results/ast-grep.json", len(all_matches))
    ctx.record(ctx.paths.ast_grep_json, produced_by="ast-grep",
               description="structural pattern matches (JSON)", rows=len(all_matches))


def _skip_ast_grep(ctx: RunContext, reason: str) -> None:
    write_json(ctx.paths.ast_grep_json, {
        "schema_version": SCHEMA_VERSION, "tool": "ast-grep", "skipped": True,
        "reason": reason, "patterns": _AST_GREP_PATTERNS, "matches": []})
    ctx.record(ctx.paths.ast_grep_json, produced_by="(skipped)",
               description="ast-grep structural matches", skipped=True, note=reason)


def build(ctx: RunContext, inv: dict, sym: dict, rg_data) -> dict:
    n_rules = _write_rules(ctx, rg_data)
    n_digest = _write_digest(ctx, rg_data)
    _previews(ctx, sym, rg_data)
    _semgrep(ctx)
    _ast_grep(ctx)
    log(f"queries: {n_rules} rg rules, {n_digest} digested matches, "
        f"semgrep={'on' if ctx.tools.semgrep.available else 'skip'}, "
        f"ast-grep={'on' if ctx.tools.ast_grep.available else 'skip'}")
    return {"rules": n_rules, "matches": n_digest}
