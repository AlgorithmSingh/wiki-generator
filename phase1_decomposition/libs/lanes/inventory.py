"""Inventory lane — know what files exist and what role they play.

Artifacts:
  inventory/files.jsonl           one row per file (path/language/category/sha256/…)
  inventory/git-tracked-files.txt canonical tracked-file list (git ls-files)
  inventory/source-coverage.json  counts by category/language/dir + coverage notes
"""
from __future__ import annotations

import os
from collections import Counter

from .. import config as C
from ..context import RunContext
from ..tools import run as run_cmd
from ..util import (line_count, read_text, sha256_file, write_json, write_jsonl,
                    write_text, log)


def _git(ctx: RunContext, *args: str) -> str | None:
    if not ctx.tools.git.available:
        return None
    proc = run_cmd([ctx.tools.git.path or "git", "-C", ctx.repo, *args], timeout=60)
    if proc and proc.returncode == 0:
        return proc.stdout
    return None


def _git_meta(ctx: RunContext) -> dict:
    meta: dict = {}
    head = _git(ctx, "rev-parse", "HEAD")
    if head:
        meta["head_commit"] = head.strip()
    branch = _git(ctx, "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        meta["branch"] = branch.strip()
    remote = _git(ctx, "config", "--get", "remote.origin.url")
    if remote:
        meta["remote"] = remote.strip()
    return meta


def _list_files(ctx: RunContext) -> tuple[list[str], list[str], str]:
    """Return (all relative paths, git-tracked relative paths, method)."""
    out = _git(ctx, "ls-files")
    if out is not None:
        seen: set[str] = set()
        tracked: list[str] = []
        for ln in out.splitlines():
            ln = ln.strip()
            if ln and ln not in seen:
                seen.add(ln)
                tracked.append(ln)
        if tracked:
            return tracked, tracked, "git ls-files"
    # Non-git fallback: walk the tree, skipping ignore dirs.
    files: list[str] = []
    for root, dirs, names in os.walk(ctx.repo):
        dirs[:] = [d for d in dirs if d not in C.IGNORE_DIRS]
        for n in names:
            ap = os.path.join(root, n)
            files.append(os.path.relpath(ap, ctx.repo))
    return files, [], "os.walk"


def build(ctx: RunContext) -> dict:
    repo = ctx.repo
    rels, tracked, method = _list_files(ctx)
    tracked_set = set(tracked)
    git_meta = _git_meta(ctx)

    records: list[dict] = []
    cat_counts: Counter = Counter()
    lang_counts: Counter = Counter()
    cat_bytes: Counter = Counter()
    dir_counts: Counter = Counter()
    excluded = 0

    for rel in sorted(set(rels)):
        rel = rel.replace("\\", "/")
        parts = rel.split("/")
        if any(p in C.IGNORE_DIRS for p in parts):
            excluded += 1
            continue
        ap = os.path.join(repo, rel)
        if not os.path.isfile(ap) or os.path.islink(ap):
            continue
        try:
            size = os.path.getsize(ap)
        except OSError:
            continue
        name = parts[-1]
        ext = os.path.splitext(name)[1].lower()
        cls = C.classify(rel, ext, size)
        lang = C.language_for(ext, name)

        nlines = 0
        if (not cls["is_binary"] and ext in C.TEXT_EXTS
                and size <= C.MAX_FILE_BYTES_FOR_TEXT):
            txt = read_text(ap, C.MAX_FILE_BYTES_FOR_TEXT)
            if txt is not None:
                nlines = line_count(txt)

        indexable = (
            not cls["is_binary"] and not cls["is_generated"]
            and not cls["is_vendor"] and ext in C.TEXT_EXTS
            and size <= C.MAX_FILE_BYTES_FOR_TEXT
        )
        top = parts[0] if len(parts) > 1 else "(root)"
        records.append({
            "path": rel,
            "name": name,
            "ext": ext,
            "language": lang,
            "category": cls["category"],
            "size_bytes": size,
            "line_count": nlines,
            "sha256": sha256_file(ap),
            "git_tracked": rel in tracked_set,
            "is_generated": cls["is_generated"],
            "is_vendor": cls["is_vendor"],
            "is_binary": cls["is_binary"],
            "indexable": indexable,
            "top_dir": top,
        })
        cat_counts[cls["category"]] += 1
        lang_counts[lang] += 1
        cat_bytes[cls["category"]] += size
        dir_counts[top] += 1

    n = write_jsonl(ctx.paths.files_jsonl, records)
    ctx.count("inventory/files.jsonl", n)
    ctx.record(ctx.paths.files_jsonl, produced_by="git ls-files / pathlib",
               description="one row per file: path, language, category, size, "
                           "lines, sha256, git_tracked", rows=n)

    write_text(ctx.paths.git_tracked, "\n".join(tracked) + ("\n" if tracked else ""))
    ctx.record(ctx.paths.git_tracked, produced_by="git ls-files",
               description="canonical tracked-file list", rows=len(tracked),
               note=None if tracked else "not a git repo / no tracked files")

    indexable = sum(1 for r in records if r["indexable"])
    py_files = sum(1 for r in records if r["language"] == "python")
    coverage = {
        "repo_root": repo,
        "git": git_meta,
        "listing_method": method,
        "total_files": len(records),
        "tracked_files": len(tracked),
        "excluded_by_ignore_dirs": excluded,
        "indexable_files": indexable,
        "python_files": py_files,
        "counts_by_category": dict(cat_counts.most_common()),
        "bytes_by_category": dict(cat_bytes.most_common()),
        "counts_by_language": dict(lang_counts.most_common()),
        "counts_by_top_dir": dict(dir_counts.most_common()),
        "primary_language": lang_counts.most_common(1)[0][0] if lang_counts else None,
        "tools": ctx.tools.as_dict(),
        "coverage_notes": [
            "Python-first V1: only .py files receive AST-level structure extraction.",
            "Other source is inventoried and chunked by line windows for "
            "lexical/semantic retrieval, but not parsed for symbols.",
            "generated/vendor/binary files are inventoried but excluded from "
            "chunking/indexing (see is_generated/is_vendor/is_binary).",
        ],
    }
    write_json(ctx.paths.source_coverage, coverage)
    ctx.record(ctx.paths.source_coverage, produced_by="pathlib + classifier",
               description="coverage counts by category/language/dir + notes")

    log(f"inventory: {len(records)} files ({indexable} indexable, {py_files} python) "
        f"via {method}")
    return {"files": records, "git": git_meta, "coverage": coverage,
            "tracked": tracked, "method": method}
