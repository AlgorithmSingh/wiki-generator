"""Step 2: derived/planning-gaps.md — make uncertainty explicit.

Lists skipped tools, parse errors, unresolved-call counts, missing vectors/specs,
and any warnings the decomposition emitted, so the planning LLM does not mistake
approximate evidence for ground truth.
"""
from __future__ import annotations

from . import ranking as R
from .loader import Bundle


def build(bundle: Bundle) -> str:
    L: list[str] = []
    L += R.heading(1, "Planning — Gaps & Uncertainty")
    L.append("What was skipped, approximated, or unverified in this decomposition. "
             "Read this before trusting any single signal.")
    L.append("")

    # Skipped / unavailable tools
    tools = bundle.tools or {}
    rows = []
    for name in sorted(tools):
        info = tools[name] or {}
        status = "✅ used" if info.get("available") else "⏭️ skipped"
        rows.append([name, status, info.get("note") or info.get("version") or "—"])
    L += R.heading(2, "Tool availability")
    L += R.md_table(["tool", "status", "detail"], rows)

    # Vectors / contracts specifics
    L += R.heading(2, "Retrieval & contract gaps")
    emb = (tools.get("embeddings") or {})
    if not emb.get("available"):
        L.append("- Vector lane skipped: `rag/vectors.faiss` not written. "
                 "Retrieval relies on BM25 + ripgrep only.")
    spec = bundle.openapi or {}
    if R.is_derived_contract(spec):
        L.append("- OpenAPI contract is **derived** from route decorators (or empty); "
                 "request/response schemas are unknown.")
    L.append("")

    # Approximation counts
    L += R.heading(2, "Approximation signals")
    unresolved = next((w for w in bundle.warnings if "could not be name-resolved" in w
                       or "resolve" in w.lower()), None)
    if unresolved:
        L.append(f"- {unresolved}")
    call_edges = sum(1 for e in bundle.edges if e.get("type") == "CALLS_APPROX")
    L.append(f"- `CALLS_APPROX` edges (approximate call graph): **{call_edges:,}**.")
    L.append("- Lexical query hits (`queries/results/rg.jsonl`) are substring matches, "
             "not semantically verified.")
    L.append("")

    # Raw warnings
    L += R.heading(2, "All decomposition warnings")
    if bundle.warnings:
        for w in bundle.warnings:
            L.append(f"- {w}")
    else:
        L.append("- None recorded.")
    L.append("")
    return "\n".join(L) + "\n"
