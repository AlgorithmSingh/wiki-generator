"""Phase 1 Step 4: assemble the planner upload bundle (``planner-digest/``).

Deterministic, LLM-free packaging of the Step 2 condensates + the Step 3 digest
into one uploadable set for the Phase 2 planning LLM. It does not summarize,
reinterpret, or normalize anything — it only orders and concatenates files that
earlier steps already produced. Writes:

    planner-digest/README_FOR_PLANNER.md     orientation + Phase 2 output contract
    planner-digest/upload-list.md            what was included / excluded + budget
    planner-digest/planner-upload-bundle.md  the one file to upload (concatenation)
    planner-digest/planning-*.md             byte-identical copies of derived/ condensates

File order is fixed (see ``CONDENSATES``). When the upload would exceed the token
budget, OPTIONAL/supporting files are trimmed from the end first; the README and
the planning condensates are never trimmed. If those required files alone exceed
the budget the run fails loudly (``failed=True``) and the reason is written to
``upload-list.md``.
"""
from __future__ import annotations

import math
import os
import shutil
from dataclasses import dataclass

from ..util import read_text, write_text

BUNDLE_NAME = "planner-upload-bundle.md"
README_NAME = "README_FOR_PLANNER.md"
UPLOAD_LIST_NAME = "upload-list.md"

# Step 2 condensates + the Step 3 digest, in reading order. These are copied into
# planner-digest/ and are the required set — never trimmed (alongside the README).
# planning-handles.md leads: the exact retrieval handles come right after the
# README and before the broad summaries, so the planner sees them first.
CONDENSATES = [
    "planning-handles.md",
    "planning-digest.md",
    "planning-symbols.md",
    "planning-graph.md",
    "planning-runtime-surfaces.md",
    "planning-tests.md",
    "planning-gaps.md",
]

# Trimmable supporting artifacts (always offered when present), in bundle order.
SUPPORTING = [
    "ARTIFACT_GUIDE.md",
    "derived/repo-summary.md",
    "derived/artifact-index.md",
    "inventory/source-coverage.json",
    "contracts/contract-sources.md",
]

# Trimmable optional artifacts (included only if present), in bundle order.
OPTIONAL = [
    "contracts/openapi.json",
    "tests/pytest-collect.txt",
    "tests/test-files.jsonl",
]

# Raw backend indexes that must NEVER be uploaded — kept for Phase 3 retrieval.
DO_NOT_UPLOAD = [
    "symbols/symbols.jsonl",
    "symbols/imports.jsonl",
    "symbols/occurrences.jsonl",
    "static/nodes.jsonl",
    "static/edges.jsonl",
    "rag/chunks.jsonl",
    "rag/spans.jsonl",
    "rag/bm25.sqlite",
    "rag/vectors.faiss",
    "rag/vector-metadata.json",
    "queries/results/rg.jsonl",
]

_BEGIN = "<!-- BEGIN INCLUDED FILE: {} -->"
_END = "<!-- END INCLUDED FILE: {} -->"


def estimate_tokens(text: str) -> int:
    """Planning budget estimate: ``ceil(len / 4)``. Not a tokenizer count."""
    return math.ceil(len(text) / 4)


@dataclass
class _Doc:
    label: str          # relative path used in boundary markers + listings
    text: str
    required: bool

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


# --- collection ----------------------------------------------------------------
def _collect(in_dir: str, derived: str, readme_text: str) -> list[_Doc]:
    """Build the ordered candidate list. README + condensates are required."""
    docs: list[_Doc] = [
        _Doc("planner-digest/README_FOR_PLANNER.md", readme_text, required=True),
    ]
    for name in CONDENSATES:
        text = read_text(os.path.join(derived, name))
        if text is not None:
            docs.append(_Doc(f"derived/{name}", text, required=True))
    for rel in SUPPORTING + OPTIONAL:
        text = read_text(os.path.join(in_dir, rel))
        if text is not None:
            docs.append(_Doc(rel, text, required=False))
    return docs


def _last_trimmable(docs: list[_Doc]) -> int | None:
    for i in range(len(docs) - 1, -1, -1):
        if not docs[i].required:
            return i
    return None


# --- rendered files ------------------------------------------------------------
def _readme(repo_root: str, source_bundle: str, generated_at: str,
            condensates: list[str]) -> str:
    L = ["# README for the planning LLM", "",
         f"- Repository: `{repo_root}`",
         f"- Source decomposition: `{source_bundle}`",
         f"- Generated: {generated_at}",
         "",
         "**This is a digest, not raw source.** It is a deterministic, lossy "
         "summary of a Phase 1 decomposition bundle. Counts and rankings are "
         "exact; call edges and lexical query hits are **approximate** and must "
         "be treated as approximate; line anchors point into the full bundle for "
         "Phase 3 retrieval.",
         "",
         "## Digest files (recommended reading order)", ""]
    for i, name in enumerate(condensates, 1):
        L.append(f"{i}. `{name}`")
    L += ["",
          "Supporting artifacts may also be included in the bundle "
          "(`ARTIFACT_GUIDE.md`, `derived/repo-summary.md`, "
          "`derived/artifact-index.md`, `inventory/source-coverage.json`, "
          "`contracts/contract-sources.md`, and — if present — "
          "`contracts/openapi.json`, `tests/pytest-collect.txt`, "
          "`tests/test-files.jsonl`). See `upload-list.md` for the exact set.",
          "",
          "## Your task (Phase 2)", "",
          "You are producing a retrieval **work order**, not final Wiki prose. "
          "Decide what the documentation Wiki should contain and what evidence "
          "each section needs in the later retrieval phase.",
          "",
          "- **Do not** write the final Wiki.",
          "- **Do not** invent evidence.",
          "- Plan sections and their evidence needs only.",
          "- Flag uncertainty whenever a signal is approximate or missing.",
          "",
          "### Exact lanes require exact handles", "",
          "Use exact handles from `planning-handles.md` (or the other "
          "condensates) when filling exact retrieval lanes. **If you cannot name "
          "an exact handle, do not place the item in that exact lane** — move it "
          "to `search_hints[]` instead.",
          "",
          "- `symbols[]`: exact `symbol_id` only. No dotted guesses, repo names, "
          "globs, or `retrieve: …` requests.",
          "- `files[]`: exact repo source **files** only. Never a directory or "
          "trailing-slash path (`agent/component/` is INVALID — use "
          "`agent/component/base.py` or a `search_hints[]` entry). Never put "
          "`derived/planning-*.md` here.",
          "- `contracts[]`: exact `METHOD /path` only. `contracts/openapi.json` "
          "by itself is **not** a contract.",
          "- `tests[]`: exact test file and function/node id when available.",
          "- `graph_nodes[]`: exact `node_id` only (e.g. `dep:pytest`). Never a "
          "display label like `pytest [Dependency]`.",
          "- `query_packs[]`: canonical keys only.",
          "- `search_hints[]`: broad/fuzzy recall text such as "
          "`retrieve: api.apps.*`, `module layout`, or `test function markers`.",
          "- `context_artifacts[]`: digest/condensate docs used to understand the "
          "repo; they are **never** citeable source evidence.",
          "",
          "### Valid JSONL only", "",
          "Every `section-plans.jsonl` line is exactly one complete JSON object: "
          "no bare strings, no comments, no Markdown, no prose between or inside "
          "objects. Put every sentence in a named field — verification work in "
          "`verification_needs[]`, uncertainty in `known_gaps[]`. A single "
          "malformed line invalidates that section plan.",
          "",
          "- BAD:  `{\"section_id\":\"llm-integration\",\"verification_needs\":[],"
          "\"Lexical query hits need verification.\",\"estimated_size\":\"M\"}`",
          "- GOOD: `{\"section_id\":\"llm-integration\",\"verification_needs\":"
          "[\"Lexical query hits need verification.\"],\"known_gaps\":[],"
          "\"estimated_size\":\"M\"}`",
          "",
          "### Diagnostics are not sections", "",
          "`planning-gaps.md` and similar diagnostics are internal planning/"
          "provenance context, not source evidence. Do **not** create a normal "
          "\"Known gaps / unverified\" section from them. Attach uncertainty to the "
          "affected real sections via `verification_needs[]`. Every normal section "
          "must have a real retrieval signal (exact handle, query pack, or search "
          "hint).",
          "",
          "Produce:",
          "",
          "```text",
          "plans/document-plan.json    (DocumentPlan)",
          "plans/document-plan.md      (human-readable plan)",
          "plans/section-plans.jsonl   (one SectionPlan per line)",
          "```",
          "",
          "For each section include its coverage requirements and the retrieval "
          "needs (exact `symbol_id`s / file anchors / canonical query packs / "
          "`METHOD /path` contracts / tests / exact `node_id`s), plus "
          "`search_hints[]` for broad recall, `context_artifacts[]` for digest "
          "docs, and verification needs.",
          ""]
    return "\n".join(L) + "\n"


def _upload_list(included: list[_Doc], trimmed: list[_Doc], total_tokens: int,
                 budget_tokens: int, generated_at: str, failed: bool,
                 required_tokens: int) -> str:
    L = ["# Upload list", "",
         f"Generated: {generated_at}", "",
         f"Target budget: **{budget_tokens:,} tokens** "
         "(estimate rule: `ceil(chars / 4)`).", "",
         f"**Easiest:** upload the single concatenated file "
         f"`planner-digest/{BUNDLE_NAME}` (it contains everything below). "
         "Otherwise upload the individual files in this order:", "",
         "## Included (in bundle order)", "",
         "| # | file | est. chars | est. tokens |",
         "|---|---|---|---|"]
    for i, d in enumerate(included, 1):
        L.append(f"| {i} | `{d.label}` | {d.chars:,} | {d.tokens:,} |")
    L.append(f"| | **TOTAL** | | **{total_tokens:,}** |")
    L.append("")
    if failed:
        L += [f"> **FAIL — required files alone exceed the budget** "
              f"({required_tokens:,} > {budget_tokens:,} tokens). The bundle was "
              "still written, but it is over budget. Raise `--budget-tokens` or "
              "shrink the condensates (`--budget-tokens` on `condense`/`digest`).",
              ""]
    else:
        status = "PASS ✅" if total_tokens <= budget_tokens else "OVER BUDGET ⚠️"
        L += [f"Budget result: **{status}** "
              f"({total_tokens:,} / {budget_tokens:,} tokens).", ""]
    if trimmed:
        L += ["## Trimmed to fit the budget (not uploaded)", "",
              "Re-run with a larger `--budget-tokens` to include these:", ""]
        for d in trimmed:
            L.append(f"- `{d.label}` (~{d.tokens:,} tokens)")
        L.append("")
    L += ["## Do NOT upload (raw backend indexes — kept for Phase 3 retrieval)", ""]
    for rel in DO_NOT_UPLOAD:
        L.append(f"- `{rel}`")
    L.append("")
    return "\n".join(L) + "\n"


def _bundle(repo_root: str, source_bundle: str, generated_at: str,
            included: list[_Doc], trimmed: list[_Doc]) -> str:
    L = ["# Planner Upload Bundle", "",
         "## What this is", "",
         f"- Repository: `{repo_root}`",
         f"- Source decomposition: `{source_bundle}`",
         f"- Generated: {generated_at}",
         "",
         "A deterministic, single-file concatenation of the Phase 1 planner "
         "digest (Steps 2/3) for this repository. It is a **digest, not raw "
         "source**: counts and rankings are exact, while call edges and lexical "
         "query hits are approximate and line anchors point back into the full "
         "decomposition bundle for Phase 3 retrieval.",
         "",
         "## Planning task", "",
         "You are the Phase 2 planning LLM. Decide what the documentation Wiki "
         "should contain and what evidence each section needs in the later "
         "retrieval phase. **Do not** write the final Wiki and **do not** invent "
         "evidence. The included `README_FOR_PLANNER.md` has the exact output "
         "contract.",
         "",
         "## Included files", ""]
    for d in included:
        L.append(f"- `{d.label}` (~{d.tokens:,} tokens)")
    if trimmed:
        L += ["", "_Trimmed to fit the token budget (not included):_"]
        for d in trimmed:
            L.append(f"- `{d.label}` (~{d.tokens:,} tokens)")
    L += ["", "## Excluded raw backend artifacts", "",
          "These large indexes are intentionally **not** included; they remain "
          "in the decomposition bundle for Phase 3 retrieval:", ""]
    for rel in DO_NOT_UPLOAD:
        L.append(f"- `{rel}`")
    L += ["", "## Phase 2 required output", "",
          "```text",
          "plans/document-plan.json    (DocumentPlan)",
          "plans/document-plan.md      (human-readable plan)",
          "plans/section-plans.jsonl   (one SectionPlan per line)",
          "```",
          "",
          "Each SectionPlan must list its coverage requirements and retrieval "
          "needs (symbol ids / file anchors / query packs / contracts / tests) "
          "and flag any approximate or missing evidence.",
          ""]
    for d in included:
        L.append(_BEGIN.format(d.label))
        L.append("")
        L.append(d.text.rstrip("\n"))
        L.append("")
        L.append(_END.format(d.label))
        L.append("")
    return "\n".join(L) + "\n"


# --- entry point ---------------------------------------------------------------
def assemble(in_dir: str, out_dir: str, budget_tokens: int,
             generated_at: str, repo_root: str) -> dict:
    """Assemble the planner-digest/ upload package. Deterministic; no LLM.

    Returns a report dict: ``out_dir``, ``files`` (written into out_dir),
    ``included``/``trimmed`` labels, ``total_tokens``, ``required_tokens``,
    ``within_budget`` and ``failed`` (required files alone exceed the budget).
    """
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    derived = os.path.join(in_dir, "derived")

    # 1. Copy the condensates into the package as byte-identical copies.
    copied: list[str] = []
    for name in CONDENSATES:
        src = os.path.join(derived, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(out_dir, name))
            copied.append(name)

    # 2. README (included first in the bundle, so build/write it up front).
    readme_text = _readme(repo_root, in_dir, generated_at, copied)
    write_text(os.path.join(out_dir, README_NAME), readme_text)

    # 3. Ordered candidates, then trim OPTIONAL/supporting from the end to fit.
    docs = _collect(in_dir, derived, readme_text)
    required_tokens = sum(d.tokens for d in docs if d.required)
    failed = required_tokens > budget_tokens
    included = list(docs)
    trimmed: list[_Doc] = []
    if not failed:
        while sum(d.tokens for d in included) > budget_tokens:
            idx = _last_trimmable(included)
            if idx is None:
                break
            trimmed.insert(0, included.pop(idx))
    total_tokens = sum(d.tokens for d in included)

    # 4. upload-list.md (the accounting) + planner-upload-bundle.md (the payload).
    write_text(os.path.join(out_dir, UPLOAD_LIST_NAME),
               _upload_list(included, trimmed, total_tokens, budget_tokens,
                            generated_at, failed, required_tokens))
    bundle_text = _bundle(repo_root, in_dir, generated_at, included, trimmed)
    write_text(os.path.join(out_dir, BUNDLE_NAME), bundle_text)

    return {
        "out_dir": out_dir,
        "files": [README_NAME, *copied, UPLOAD_LIST_NAME, BUNDLE_NAME],
        "included": [d.label for d in included],
        "trimmed": [d.label for d in trimmed],
        "total_tokens": total_tokens,
        "required_tokens": required_tokens,
        "within_budget": (not failed) and total_tokens <= budget_tokens,
        "failed": failed,
        "bundle": BUNDLE_NAME,
        "bundle_tokens": estimate_tokens(bundle_text),
    }
