"""Resolves every input/output location for a decomposition run.

The output layout is the artifact bundle described in PHASE1_DECOMPOSITION_PLAN.md::

    <out>/
      ARTIFACT_GUIDE.md
      run-metadata.json
      inventory/{files.jsonl,git-tracked-files.txt,source-coverage.json}
      symbols/{symbols.jsonl,imports.jsonl,occurrences.jsonl,tags,tags.jsonl}
      rag/{spans.jsonl,chunks.jsonl,bm25.sqlite,rg-results.jsonl,
           vectors.faiss,vector-metadata.json}
      static/{nodes.jsonl,edges.jsonl}
      queries/rules/rg/*.json
      queries/results/{rg.jsonl,semgrep.json,semgrep.sarif,ast-grep.json,grep-ast/*.md}
      contracts/{openapi.json,contract-sources.md}
      tests/{pytest-collect.txt,test-files.jsonl}
      derived/{repo-summary.md,artifact-index.md}
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Paths:
    repo: str   # absolute path to the repo being decomposed
    out: str    # absolute path to the output bundle root

    # --- lane directories ------------------------------------------------------
    @property
    def inventory(self) -> str:
        return os.path.join(self.out, "inventory")

    @property
    def symbols(self) -> str:
        return os.path.join(self.out, "symbols")

    @property
    def rag(self) -> str:
        return os.path.join(self.out, "rag")

    @property
    def static(self) -> str:
        return os.path.join(self.out, "static")

    @property
    def queries(self) -> str:
        return os.path.join(self.out, "queries")

    @property
    def queries_rules_rg(self) -> str:
        return os.path.join(self.queries, "rules", "rg")

    @property
    def queries_results(self) -> str:
        return os.path.join(self.queries, "results")

    @property
    def queries_grep_ast(self) -> str:
        return os.path.join(self.queries_results, "grep-ast")

    @property
    def contracts(self) -> str:
        return os.path.join(self.out, "contracts")

    @property
    def tests(self) -> str:
        return os.path.join(self.out, "tests")

    @property
    def derived(self) -> str:
        return os.path.join(self.out, "derived")

    # --- named files -----------------------------------------------------------
    def f(self, *parts: str) -> str:
        return os.path.join(self.out, *parts)

    @property
    def artifact_guide(self) -> str:
        return self.f("ARTIFACT_GUIDE.md")

    @property
    def run_metadata(self) -> str:
        return self.f("run-metadata.json")

    @property
    def files_jsonl(self) -> str:
        return os.path.join(self.inventory, "files.jsonl")

    @property
    def git_tracked(self) -> str:
        return os.path.join(self.inventory, "git-tracked-files.txt")

    @property
    def source_coverage(self) -> str:
        return os.path.join(self.inventory, "source-coverage.json")

    @property
    def symbols_jsonl(self) -> str:
        return os.path.join(self.symbols, "symbols.jsonl")

    @property
    def imports_jsonl(self) -> str:
        return os.path.join(self.symbols, "imports.jsonl")

    @property
    def occurrences_jsonl(self) -> str:
        return os.path.join(self.symbols, "occurrences.jsonl")

    @property
    def tags(self) -> str:
        return os.path.join(self.symbols, "tags")

    @property
    def tags_jsonl(self) -> str:
        return os.path.join(self.symbols, "tags.jsonl")

    @property
    def spans_jsonl(self) -> str:
        return os.path.join(self.rag, "spans.jsonl")

    @property
    def chunks_jsonl(self) -> str:
        return os.path.join(self.rag, "chunks.jsonl")

    @property
    def bm25_sqlite(self) -> str:
        return os.path.join(self.rag, "bm25.sqlite")

    @property
    def rg_results_jsonl(self) -> str:
        return os.path.join(self.rag, "rg-results.jsonl")

    @property
    def vectors_faiss(self) -> str:
        return os.path.join(self.rag, "vectors.faiss")

    @property
    def vector_metadata(self) -> str:
        return os.path.join(self.rag, "vector-metadata.json")

    # --- Step 5 retrieval-substrate outputs ------------------------------------
    @property
    def vector_metadata_jsonl(self) -> str:
        return os.path.join(self.rag, "vector-metadata.jsonl")

    @property
    def retrieval_capabilities(self) -> str:
        return os.path.join(self.rag, "retrieval-capabilities.json")

    @property
    def retrieval_report(self) -> str:
        return os.path.join(self.rag, "retrieval-substrate-report.md")

    @property
    def vector_build_report(self) -> str:
        return os.path.join(self.rag, "vector-build-report.md")

    @property
    def retrieval_smoke(self) -> str:
        return os.path.join(self.rag, "retrieval-smoke-tests.jsonl")

    @property
    def nodes_jsonl(self) -> str:
        return os.path.join(self.static, "nodes.jsonl")

    @property
    def edges_jsonl(self) -> str:
        return os.path.join(self.static, "edges.jsonl")

    @property
    def rg_jsonl(self) -> str:
        return os.path.join(self.queries_results, "rg.jsonl")

    @property
    def semgrep_json(self) -> str:
        return os.path.join(self.queries_results, "semgrep.json")

    @property
    def semgrep_sarif(self) -> str:
        return os.path.join(self.queries_results, "semgrep.sarif")

    @property
    def ast_grep_json(self) -> str:
        return os.path.join(self.queries_results, "ast-grep.json")

    @property
    def openapi_json(self) -> str:
        return os.path.join(self.contracts, "openapi.json")

    @property
    def contract_sources(self) -> str:
        return os.path.join(self.contracts, "contract-sources.md")

    @property
    def pytest_collect(self) -> str:
        return os.path.join(self.tests, "pytest-collect.txt")

    @property
    def test_files_jsonl(self) -> str:
        return os.path.join(self.tests, "test-files.jsonl")

    @property
    def repo_summary(self) -> str:
        return os.path.join(self.derived, "repo-summary.md")

    @property
    def artifact_index(self) -> str:
        return os.path.join(self.derived, "artifact-index.md")

    def ensure(self) -> None:
        for d in (self.out, self.inventory, self.symbols, self.rag, self.static,
                  self.queries, self.queries_rules_rg, self.queries_results,
                  self.queries_grep_ast, self.contracts, self.tests, self.derived):
            os.makedirs(d, exist_ok=True)

    def rel(self, abspath: str) -> str:
        """Path of an artifact relative to the bundle root (for guides)."""
        return os.path.relpath(abspath, self.out)
