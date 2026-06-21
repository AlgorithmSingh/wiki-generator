"""Step 2: derived/planning-tests.md — test coverage signals.

Condensed from ``tests/test-files.jsonl`` + ``tests/pytest-collect.txt`` plus
``TESTS_APPROX`` edges. Reports counts, top directories, subsystem grouping, and
whether the inventory came from pytest collection or a static scan.
"""
from __future__ import annotations

from . import ranking as R
from .loader import Bundle

TOP_N = 25


def _test_dir(path: str) -> str:
    parts = str(path).split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else "(root)"


def build(bundle: Bundle) -> str:
    tfs = bundle.test_files
    L: list[str] = []
    L += R.heading(1, "Planning — Tests")
    L.append("Condensed from `tests/test-files.jsonl`, `tests/pytest-collect.txt`, "
             "and static `TESTS_APPROX` edges.")
    L.append("")

    total_files = len(tfs)
    total_fns = sum(int(t.get("test_functions") or 0) for t in tfs)
    total_classes = sum(int(t.get("test_classes") or 0) for t in tfs)
    total_fixtures = sum(int(t.get("fixtures") or 0) for t in tfs)
    L += R.heading(2, "Totals")
    L += R.md_table(["metric", "value"], [
        ["test files", f"{total_files:,}"],
        ["test functions", f"{total_fns:,}"],
        ["test classes", f"{total_classes:,}"],
        ["fixtures", f"{total_fixtures:,}"],
    ])

    # Collection status
    L += R.heading(2, "Collection status")
    pc = bundle.pytest_collect or ""
    skipped = (not pc.strip()) or "skip" in pc.lower() or "static" in pc.lower()
    if skipped:
        L.append("- ⚠️ pytest collection was **skipped or static-only**; counts come "
                 "from the static scan, not live import.")
    else:
        L.append("- pytest collection ran; see `tests/pytest-collect.txt`.")
    for w in bundle.warnings:
        if "pytest" in w.lower() or "test" in w.lower():
            L.append(f"- {w}")
    L.append("")

    # Top directories
    by_dir = R.count_by(tfs, lambda t: _test_dir(t.get("path", "")))
    L += R.heading(2, "Top test directories")
    L += R.count_table(by_dir, ["directory", "test files"], TOP_N, total=len(by_dir))

    # By framework hint
    by_fw = R.count_by(tfs, lambda t: t.get("framework_hint"))
    L += R.heading(2, "Frameworks (by hint)")
    if by_fw:
        L += R.md_table(["framework", "files"], [[k, f"{v:,}"] for k, v in R.top(by_fw, 15)])
    else:
        L.append("- No framework hints detected.")
        L.append("")

    # Heaviest test files by function count
    heavy = sorted(tfs, key=lambda t: (-int(t.get("test_functions") or 0),
                                       t.get("path", "")))[:TOP_N]
    heavy = [t for t in heavy if int(t.get("test_functions") or 0) > 0]
    L += R.heading(2, "Heaviest test files (by test function count)")
    L += R.md_table(["file", "test fns"],
                    [[t.get("path", "?"), int(t.get("test_functions") or 0)] for t in heavy])

    # TESTS_APPROX coverage
    tested = R.count_by([e for e in bundle.edges if e.get("type") == "TESTS_APPROX"],
                        lambda e: e.get("dst"))
    L += R.heading(2, "Most-referenced targets by tests (TESTS_APPROX, approximate)")
    if tested:
        L += R.md_table(["target node", "test edges"],
                        [[k, f"{v:,}"] for k, v in R.top(tested, TOP_N)])
    else:
        L.append("- No `TESTS_APPROX` edges recorded.")
        L.append("")
    return "\n".join(L) + "\n"
