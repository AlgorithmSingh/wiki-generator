"""Ripgrep query packs: deterministic regex searches for common Python-repo
surfaces. Run once; the raw machine-readable capture feeds ``rag/rg-results.jsonl``
and the digested per-match rows feed ``queries/results/rg.jsonl``.

These are *query results*, not a canonical fact schema — they point later phases
at where a surface lives, to be confirmed against source spans.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field

from .context import RunContext
from .tools import run as run_cmd
from .util import log

# Each pack: name -> {pattern, globs, why}. Patterns are ripgrep (Rust regex).
PACKS: dict[str, dict] = {
    "web_routes": {
        "pattern": r"@\w+\.(?:route|get|post|put|delete|patch|websocket)\(|add_url_rule\(|"
                   r"@(?:app|router|bp|blueprint|api)\.\w+\(|"
                   r"path\(|re_path\(|url\(|APIRouter\(|Blueprint\(",
        "globs": ["*.py"],
        "why": "HTTP/WebSocket routes (FastAPI/Flask/Django/Starlette)",
    },
    "task_workers": {
        "pattern": r"@(?:app|celery|shared_task|huey|dramatiq)\.?\w*\.?task\b|"
                   r"@shared_task|@task\(|@celery_app\.task|@dramatiq\.actor|"
                   r"\.delay\(|\.apply_async\(|Queue\(|RQ\b|rq\.",
        "globs": ["*.py"],
        "why": "background tasks / job queues (Celery/RQ/Dramatiq/Huey)",
    },
    "cli_commands": {
        "pattern": r"@(?:click|app|cli|group)\.(?:command|group)\(|@command\(|"
                   r"argparse\.ArgumentParser|add_argument\(|add_parser\(|"
                   r"typer\.Typer\(|@app\.callback\(|click\.Group",
        "globs": ["*.py"],
        "why": "CLI command definitions (Click/Typer/argparse)",
    },
    "models_schemas": {
        "pattern": r"class\s+\w+\((?:[^)]*\b(?:Base|Model|BaseModel|Schema|"
                   r"models\.Model|declarative_base|TypedDict|Document)\b[^)]*)\)|"
                   r"\b(?:Column|relationship|mapped_column|Mapped\[|Field\(|"
                   r"CharField|TextField|ForeignKey|@dataclass)\b",
        "globs": ["*.py"],
        "why": "data models / schemas (SQLAlchemy/Django/Pydantic/dataclass)",
    },
    "env_vars": {
        "pattern": r"os\.environ|os\.getenv\(|getenv\(|environ\.get\(|"
                   r"BaseSettings|pydantic_settings|Settings\(",
        "globs": ["*.py"],
        "why": "environment variable / settings access",
    },
    "config_keys": {
        "pattern": r"^[A-Z][A-Z0-9_]{2,}\s*[=:]|settings\.\w+|config\[|"
                   r"\.config\.|Config\b|conf\.|getattr\(settings",
        "globs": ["*.py"],
        "why": "configuration / settings keys in Python code",
    },
    "config_file_keys": {
        # config files use lowercase keys and [section] headers, which the
        # Python-shaped config_keys pattern above never matches.
        "pattern": r"^\s*[A-Za-z_][A-Za-z0-9_.\-]*\s*[:=]|^\s*\[[^\]]+\]",
        "globs": ["*.toml", "*.ini", "*.cfg", "*.env", "*.yaml", "*.yml"],
        "why": "keys / sections in config files (YAML/TOML/INI/env)",
    },
    "plugin_registries": {
        "pattern": r"importlib|__import__|import_module|register\(|registry\b|"
                   r"REGISTRY|FACTORY|factory\b|entry_points|pkg_resources|"
                   r"plugin|get_plugin|load_module|globals\(\)\[",
        "globs": ["*.py"],
        "why": "plugin / registry / factory / dynamic-loading mechanisms",
    },
    "datastore": {
        "pattern": r"\b(?:psycopg2?|asyncpg|sqlalchemy|create_engine|sessionmaker|"
                   r"Session\(|redis|aioredis|pymongo|MongoClient|boto3|"
                   r"elasticsearch|Elasticsearch|sqlite3|cassandra|clickhouse|"
                   r"Cache\(|cache\.|MinIO|minio)\b",
        "globs": ["*.py"],
        "why": "databases / sessions / caches / object stores",
    },
    "auth_security": {
        "pattern": r"\b(?:login_required|current_user|api_key|APIKey|jwt|JWT|"
                   r"oauth|OAuth|Depends\(|HTTPBearer|authenticate|authorize|"
                   r"permission|hash_password|bcrypt|passlib|csrf|middleware|"
                   r"Middleware)\b",
        "globs": ["*.py"],
        "why": "auth / security middleware / dependencies",
    },
    "entrypoints": {
        "pattern": r"if\s+__name__\s*==\s*['\"]__main__['\"]|def\s+main\s*\(|"
                   r"app\.run\(|uvicorn\.run|hypercorn|gunicorn|asyncio\.run\(|"
                   r"run_until_complete",
        "globs": ["*.py"],
        "why": "process entrypoints / server bootstrap",
    },
    "llm_integrations": {
        "pattern": r"\b(?:openai|OpenAI|anthropic|Anthropic|claude|ollama|"
                   r"litellm|langchain|llama_index|cohere|Cohere|huggingface|"
                   r"transformers|google\.generativeai|genai|mistralai)\b",
        "globs": ["*.py"],
        "why": "LLM / AI provider integrations",
    },
}

# Directories ripgrep should never descend into (beyond .gitignore).
_EXCLUDES = ["node_modules", ".venv", "venv", "dist", "build", ".git",
             "site-packages", "__pycache__", ".next", "target"]

_MAX_RAW_PER_PACK = 4000   # safety cap on raw match events captured per pack


@dataclass
class RgData:
    available: bool
    rules: list[dict] = field(default_factory=list)
    raw_events: list[dict] = field(default_factory=list)   # raw rg match events
    matches: list[dict] = field(default_factory=list)      # digested per-match rows
    summary: dict = field(default_factory=dict)            # pack -> total hits
    truncated: list[str] = field(default_factory=list)


def _rule(name: str, spec: dict) -> dict:
    return {
        "name": name,
        "engine": "ripgrep",
        "pattern": spec["pattern"],
        "globs": spec["globs"],
        "why": spec["why"],
    }


def _run_pack(repo: str, rg_path: str, name: str, spec: dict, cap: int) -> dict:
    cmd = [rg_path, "--json", "-e", spec["pattern"]]
    for g in spec["globs"]:
        cmd += ["-g", g]
    for d in _EXCLUDES:
        cmd += ["-g", f"!**/{d}/**"]
    cmd.append(repo)
    proc = run_cmd(cmd, timeout=120)
    out = {"total": 0, "raw": [], "matches": [], "truncated": False}
    if proc is None:
        out["error"] = "rg launch failed/timeout"
        return out
    # ripgrep walks files with a nondeterministic parallel worker pool, so we
    # must collect ALL matches and sort them before applying the caps — sorting
    # after the cap would already have chosen a nondeterministic subset.
    events = []
    for line in (proc.stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "match":
            continue
        d = obj["data"]
        rel = os.path.relpath(d["path"]["text"], repo)
        subs = d.get("submatches", [])
        events.append((
            rel, d["line_number"], (subs[0]["start"] if subs else 0),
            d["lines"]["text"].rstrip("\n"),
            [{"start": s["start"], "end": s["end"], "match": s["match"]["text"]}
             for s in subs],
        ))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    out["total"] = len(events)
    for i, (rel, lineno, _start, text, submatches) in enumerate(events):
        if i < _MAX_RAW_PER_PACK:
            out["raw"].append({"pack": name, "path": rel, "line_number": lineno,
                               "text": text[:400], "submatches": submatches})
        else:
            out["truncated"] = True
        if len(out["matches"]) < cap:
            out["matches"].append({"pack": name, "why": spec["why"], "path": rel,
                                   "line": lineno, "text": text[:240]})
    return out


def run_packs(ctx: RunContext) -> RgData:
    if not ctx.tools.rg.available:
        ctx.warn("ripgrep not available: rag/rg-results.jsonl and "
                 "queries/results/rg.jsonl are empty.")
        return RgData(available=False, rules=[_rule(n, s) for n, s in PACKS.items()])

    data = RgData(available=True)
    repo = ctx.repo
    rg_path = ctx.tools.rg.path or "rg"
    cap = ctx.opts.rg_cap
    for name, spec in PACKS.items():
        data.rules.append(_rule(name, spec))
        res = _run_pack(repo, rg_path, name, spec, cap)
        data.summary[name] = res["total"]
        data.raw_events.extend(res["raw"])
        data.matches.extend(res["matches"])
        if res.get("truncated"):
            data.truncated.append(name)
    if data.truncated:
        ctx.warn(f"rg raw capture truncated at {_MAX_RAW_PER_PACK} matches/pack "
                 f"for: {', '.join(data.truncated)}")
    log(f"rg packs: {data.summary}")
    return data
