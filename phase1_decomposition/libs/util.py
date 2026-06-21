"""Shared utilities: hashing, text IO, JSON/JSONL writers, logging."""
from __future__ import annotations

import hashlib
import json
import os
import sys


# --- Hashing -------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def sha256_file(path: str) -> str | None:
    """Stream a file's bytes into a sha256 digest. None if unreadable."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


# --- Text IO -------------------------------------------------------------------
def read_text(path: str, max_bytes: int | None = None) -> str | None:
    """Read a text file, returning None for binary/oversized/unreadable files."""
    try:
        size = os.path.getsize(path)
        if max_bytes is not None and size > max_bytes:
            return None
        with open(path, "rb") as f:
            raw = f.read()
        if b"\x00" in raw[:8000]:
            return None  # looks binary
        return raw.decode("utf-8", "replace")
    except (OSError, ValueError):
        return None


def line_count(text: str) -> int:
    if not text:
        return 0
    n = text.count("\n")
    return n + (0 if text.endswith("\n") else 1)


def clip(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n…[truncated]"


def token_estimate(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token)."""
    return (len(text) + 3) // 4


def module_header_last(first_def_line: int | None, nlines: int) -> int:
    """Last line of a Python module's header region (imports/constants/docstring,
    above the first def/class). Shared by the symbols and rag lanes so the module
    symbol and its module_header span agree on the same range/id."""
    if not nlines:
        return 1
    header_end = first_def_line or nlines
    return max(1, min(header_end - 1, nlines))


def slug(text: str, maxlen: int = 64) -> str:
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/.":
            out.append("-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")[:maxlen] or "item"


# --- JSON / JSONL --------------------------------------------------------------
def write_json(path: str, obj, *, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False, default=str)
        f.write("\n")


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_jsonl(path: str, rows) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str))
            f.write("\n")
            n += 1
    return n


def read_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# --- Logging -------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[phase1] {msg}", file=sys.stderr, flush=True)
