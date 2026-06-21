"""External-tool detection, a safe subprocess runner, and runtime self-tests.

Phase 1 prefers the simplest reliable producer for each artifact but does not
exclude stronger tools when they are present. Every optional tool is probed at
startup; lanes consult :class:`Tools` and degrade gracefully (writing a clear
skip note into the artifact and a warning into ARTIFACT_GUIDE) when a tool is
missing or broken, rather than failing the run.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field


@dataclass
class ToolInfo:
    name: str
    available: bool
    path: str | None = None
    version: str | None = None
    note: str | None = None


def run(cmd: list[str], *, cwd: str | None = None, timeout: int = 120,
        input_text: str | None = None) -> subprocess.CompletedProcess | None:
    """Run a command, capturing text output. Returns None on launch failure or
    timeout (never raises). Callers inspect ``.returncode``/``.stdout``."""
    try:
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, input=input_text,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _which(name: str) -> str | None:
    return shutil.which(name)


def _module_importable(modnames: list[str]) -> tuple[bool, str | None]:
    """Probe importability in a clean subprocess so a heavy/broken import never
    pollutes the running interpreter."""
    code = "import importlib,sys\n" + \
        "".join(f"importlib.import_module({m!r})\n" for m in modnames) + \
        "print('OK')"
    proc = run([sys.executable, "-c", code], timeout=60)
    if proc is None:
        return False, "probe failed (timeout)"
    if proc.returncode == 0 and "OK" in proc.stdout:
        return True, None
    err = (proc.stderr or "").strip().splitlines()
    return False, (err[-1] if err else "import failed")


def _detect_git() -> ToolInfo:
    p = _which("git")
    if not p:
        return ToolInfo("git", False, note="not on PATH")
    proc = run([p, "--version"], timeout=20)
    ver = proc.stdout.strip() if proc and proc.returncode == 0 else None
    return ToolInfo("git", True, p, ver)


def _detect_rg() -> ToolInfo:
    p = _which("rg")
    if not p:
        return ToolInfo("rg", False, note="ripgrep not on PATH; rg query packs skipped")
    proc = run([p, "--version"], timeout=20)
    ver = proc.stdout.splitlines()[0].strip() if proc and proc.returncode == 0 else None
    return ToolInfo("rg", True, p, ver)


def _detect_universal_ctags() -> ToolInfo:
    p = _which("ctags")
    if not p:
        return ToolInfo("universal-ctags", False,
                        note="no ctags on PATH; AST-derived tags will be used")
    proc = run([p, "--version"], timeout=20)
    out = (proc.stdout + proc.stderr) if proc else ""
    if "Universal Ctags" in out:
        ver = out.splitlines()[0].strip()
        return ToolInfo("universal-ctags", True, p, ver)
    return ToolInfo("universal-ctags", False, p,
                    note="ctags present but not Universal Ctags (no JSON tags); "
                         "AST-derived tags will be used")


def _detect_semgrep() -> ToolInfo:
    p = _which("semgrep")
    if not p:
        return ToolInfo("semgrep", False, note="not installed; semgrep results skipped")
    proc = run([p, "--version"], timeout=30)
    ver = proc.stdout.strip() if proc and proc.returncode == 0 else None
    return ToolInfo("semgrep", True, p, ver)


def _detect_ast_grep() -> ToolInfo:
    p = _which("ast-grep") or _which("sg")
    if not p:
        return ToolInfo("ast-grep", False, note="not installed; ast-grep results skipped")
    proc = run([p, "--version"], timeout=30)
    ver = proc.stdout.strip() if proc and proc.returncode == 0 else None
    return ToolInfo("ast-grep", True, p, ver)


def _detect_pytest() -> ToolInfo:
    """pytest is run as ``python -m pytest`` so it lives in whatever interpreter
    runs this CLI (collection of an external repo still needs that repo's deps)."""
    ok, err = _module_importable(["pytest"])
    if not ok:
        return ToolInfo("pytest", False, note="pytest not importable; static test scan only")
    proc = run([sys.executable, "-m", "pytest", "--version"], timeout=30)
    ver = (proc.stdout or proc.stderr or "").strip().splitlines()[:1] if proc else None
    return ToolInfo("pytest", True, sys.executable, ver[0] if ver else None)


def _detect_embeddings() -> ToolInfo:
    ok, err = _module_importable(["faiss", "numpy", "model2vec"])
    if ok:
        return ToolInfo("embeddings", True, sys.executable,
                        note="faiss + numpy + model2vec importable")
    return ToolInfo("embeddings", False, note=f"faiss/numpy/model2vec not importable ({err})")


def _detect_grep_ast() -> ToolInfo:
    """grep-ast is finicky across tree-sitter versions, so we run a real
    self-test on a tiny snippet rather than trusting importability."""
    ok, _ = _module_importable(["grep_ast"])
    if not ok:
        return ToolInfo("grep-ast", False,
                        note="grep_ast not importable; built-in AST preview used")
    proc = run([sys.executable, "-m", "grep_ast.main", "--no-color", "-n",
                "def", _selftest_file()], timeout=30)
    if proc is not None and proc.returncode == 0 and "def " in (proc.stdout or "") \
            and "Traceback" not in (proc.stderr or ""):
        return ToolInfo("grep-ast", True, sys.executable, note="self-test passed")
    reason = "self-test failed (tree-sitter API mismatch)"
    if proc and proc.stderr:
        last = proc.stderr.strip().splitlines()[-1:]
        if last:
            reason = f"self-test failed: {last[0][:120]}"
    return ToolInfo("grep-ast", False, note=f"{reason}; built-in AST preview used")


_SELFTEST_PATH: str | None = None


def _cleanup_selftest_file() -> None:
    """atexit hook: remove the throwaway self-test file if it was created."""
    path = _SELFTEST_PATH
    if path:
        try:
            os.remove(path)
        except OSError:
            pass  # already gone / reclaimed by the OS — nothing to clean up


def _selftest_file() -> str:
    """A tiny throwaway .py file grep-ast can parse for its self-test. Created
    once per process and unlinked at interpreter exit (it must outlive the
    grep-ast subprocess call, so try/finally can't be used here)."""
    global _SELFTEST_PATH
    if _SELFTEST_PATH is None:
        fd, path = tempfile.mkstemp(suffix="_p1_selftest.py")
        with os.fdopen(fd, "w") as f:
            f.write("def selftest_marker():\n    return 1\n")
        _SELFTEST_PATH = path
        atexit.register(_cleanup_selftest_file)
    return _SELFTEST_PATH


@dataclass
class Tools:
    git: ToolInfo
    rg: ToolInfo
    universal_ctags: ToolInfo
    semgrep: ToolInfo
    ast_grep: ToolInfo
    pytest: ToolInfo
    embeddings: ToolInfo
    grep_ast: ToolInfo
    extras: dict = field(default_factory=dict)

    def all(self) -> list[ToolInfo]:
        return [self.git, self.rg, self.universal_ctags, self.semgrep,
                self.ast_grep, self.pytest, self.embeddings, self.grep_ast]

    def as_dict(self) -> dict:
        return {
            t.name: {"available": t.available, "version": t.version, "note": t.note}
            for t in self.all()
        }


def detect_all() -> Tools:
    return Tools(
        git=_detect_git(),
        rg=_detect_rg(),
        universal_ctags=_detect_universal_ctags(),
        semgrep=_detect_semgrep(),
        ast_grep=_detect_ast_grep(),
        pytest=_detect_pytest(),
        embeddings=_detect_embeddings(),
        grep_ast=_detect_grep_ast(),
    )
