"""Tests lane — test inventory in a known test-runner format.

Artifacts:
  tests/pytest-collect.txt    `pytest --collect-only -q` output (best effort)
  tests/test-files.jsonl      static scan of test files + test-symbol counts

The full suite is never run. ``pytest --collect-only`` imports test modules and
conftest (executing top-level code), so collection of an external repo may be
partial when that repo's dependencies are not installed here — captured output
notes this; the static scan is always reliable.
"""
from __future__ import annotations

import os
import sys

from ..context import RunContext
from ..tools import run as run_cmd
from ..util import write_jsonl, write_text, log


def _framework_hint(parser) -> str:
    hints = set()
    for s in getattr(parser, "symbols", []):
        if s["kind"] == "class" and any("TestCase" in b for b in s.get("bases", [])):
            hints.add("unittest")
        for d in s.get("decorators", []):
            if "pytest" in d or "fixture" in d:
                hints.add("pytest")
    if not hints:
        hints.add("pytest")  # default discovery convention
    return "+".join(sorted(hints))


def _scan_test_files(ctx: RunContext, inv: dict, sym: dict) -> list[dict]:
    modules = sym.get("modules", {})
    rows = []
    for rec in inv["files"]:
        if rec["category"] != "test":
            continue
        row = {
            "path": rec["path"],
            "language": rec["language"],
            "line_count": rec["line_count"],
            "test_functions": 0,
            "test_classes": 0,
            "fixtures": 0,
            "framework_hint": None,
        }
        parser = modules.get(rec["path"])
        if parser is not None and not getattr(parser, "error", None):
            tf = tc = fx = 0
            for s in parser.symbols:
                if s["kind"] in {"function", "method"} and s["name"].startswith("test"):
                    tf += 1
                if s["kind"] == "class" and (s["name"].startswith("Test")
                                             or any("TestCase" in b for b in s.get("bases", []))):
                    tc += 1
                if any("fixture" in d for d in s.get("decorators", [])):
                    fx += 1
            row.update(test_functions=tf, test_classes=tc, fixtures=fx,
                       framework_hint=_framework_hint(parser))
        rows.append(row)
    rows.sort(key=lambda r: r["path"])
    return rows


def _pytest_collect(ctx: RunContext) -> tuple[bool, str]:
    want = ctx.opts.pytest_collect
    if want == "off":
        return False, "pytest --collect-only disabled (--pytest-collect off)."
    if not ctx.tools.pytest.available:
        return False, ("pytest is not importable in this environment; "
                       "test inventory comes from the static scan only.")
    proc = run_cmd([sys.executable, "-m", "pytest", "--collect-only", "-q",
                    "-p", "no:cacheprovider", ctx.repo], cwd=ctx.repo, timeout=180)
    if proc is None:
        return False, "pytest --collect-only timed out or failed to launch."
    out = (proc.stdout or "") + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
    header = (f"# pytest --collect-only -q (exit {proc.returncode})\n"
              f"# repo: {ctx.repo}\n"
              f"# NOTE: collection imports test modules + conftest. Errors below are\n"
              f"#       typically missing target-repo dependencies, not test failures.\n\n")
    return True, header + out


def build(ctx: RunContext, inv: dict, sym: dict | None = None) -> dict:
    sym = sym or {}
    rows = _scan_test_files(ctx, inv, sym)
    n = write_jsonl(ctx.paths.test_files_jsonl, rows)
    ctx.count("tests/test-files.jsonl", n)
    total_tests = sum(r["test_functions"] for r in rows)
    ctx.record(ctx.paths.test_files_jsonl, produced_by="python ast scan",
               description="test files with test/fixture counts + framework hint",
               rows=n, note=f"{total_tests} test functions across {n} files")

    ran, content = _pytest_collect(ctx)
    write_text(ctx.paths.pytest_collect, content + ("\n" if not content.endswith("\n") else ""))
    ctx.record(ctx.paths.pytest_collect,
               produced_by="pytest --collect-only" if ran else "(skipped)",
               description="pytest test collection", skipped=not ran,
               note=None if ran else "static scan only (see test-files.jsonl)")
    if not ran:
        ctx.warn(content.strip().splitlines()[0] if content else "pytest collect skipped")

    log(f"tests: {n} test files, {total_tests} test functions, "
        f"pytest-collect={'ran' if ran else 'skipped'}")
    return {"test_files": n, "test_functions": total_tests, "pytest_ran": ran}
