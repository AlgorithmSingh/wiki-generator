"""Step 1 command: build the deterministic artifact bundle.

Wires CLI args into a RunContext and runs the decomposition pipeline.
"""
from __future__ import annotations

import argparse
import os
import sys

from .. import context as _context
from .. import tools as _tools
from ..paths import Paths
from ..pipeline import run as run_pipeline
from ..util import log
from ... import GENERATOR


def _resolve_repo(repo: str) -> str:
    repo = os.path.abspath(os.path.expanduser(repo))
    if not os.path.isdir(repo):
        log(f"error: --repo is not a directory: {repo}")
        sys.exit(2)
    return repo


def run(args: argparse.Namespace) -> int:
    repo = _resolve_repo(args.repo)
    out = os.path.abspath(os.path.expanduser(args.out))
    paths = Paths(repo=repo, out=out)
    paths.ensure()

    opts = _context.Options(
        embeddings=args.embeddings,
        grep_ast=getattr(args, "grep_ast"),
        semgrep=args.semgrep,
        ast_grep=getattr(args, "ast_grep"),
        pytest_collect=getattr(args, "pytest_collect"),
        contracts_import=args.contracts_import,
        rg_cap=args.rg_cap,
    )

    log(f"{GENERATOR}")
    log(f"decomposing repo: {repo}")
    log(f"output bundle:    {out}")
    log("detecting tools ...")
    tools = _tools.detect_all()
    for t in tools.all():
        state = "ok" if t.available else "skip"
        detail = t.version or t.note or ""
        log(f"  [{state}] {t.name}: {detail}")

    ctx = _context.RunContext(paths=paths, tools=tools, opts=opts)
    run_pipeline(ctx)
    return 0
