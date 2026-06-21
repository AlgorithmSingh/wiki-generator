"""Shared, language-agnostic markdown + deterministic ranking primitives.

These are generic enough that both the decomposition lanes (``libs/lanes``) and
the planner condensates (``libs/digest``) depend on them, so they live at the
``libs`` root rather than inside any one leaf package. Anything domain-specific
(symbol classification, graph labels) stays in its own module.

All ordering is total and stable: counters break ties by key so two runs over
byte-identical inputs produce byte-identical markdown.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


# --- counting ------------------------------------------------------------------
def top(counter: Counter, n: int) -> list[tuple[str, int]]:
    """Top-n ``(key, count)`` pairs, ties broken by key for determinism."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def count_by(items, keyfn) -> Counter:
    """Count ``items`` by ``keyfn``; ``None``/empty keys are dropped."""
    c: Counter = Counter()
    for it in items:
        k = keyfn(it)
        if k is None or k == "":
            continue
        c[k] += 1
    return c


# --- markdown ------------------------------------------------------------------
def md_table(headers: list[str], rows: list[list]) -> list[str]:
    """Render a markdown table (list of lines). Empty rows render as ``_none_``."""
    if not rows:
        return ["_none_", ""]
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    return out


def count_table(counter: Counter, headers: list[str], n: int,
                *, total: int | None = None) -> list[str]:
    """A two-column ``key | count`` table of the top ``n`` entries."""
    rows = [[k, f"{v:,}"] for k, v in top(counter, n)]
    out = md_table(headers, rows)
    if total is not None and len(counter) > n:
        out.insert(len(out) - 1, f"_… {len(counter) - n:,} more not shown_")
    return out


def heading(level: int, text: str) -> list[str]:
    return [f"{'#' * level} {text}", ""]


@dataclass
class Section:
    """A titled block of markdown lines, used to assemble a document."""

    title: str
    level: int = 2
    lines: list[str] | None = None

    def render(self) -> list[str]:
        out = heading(self.level, self.title)
        out.extend(self.lines or ["_none_", ""])
        return out
