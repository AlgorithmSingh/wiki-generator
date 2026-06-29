"""Phase 1 deterministic coverage-signal expansion (Milestone 2 slice).

Given a decomposition :class:`~..digest.loader.Bundle`, this module derives, for
every mandatory DeepWiki :class:`~.taxonomy.TopicFamily`, a *planner-facing
coverage signal*: where in the repository that topic family most likely lives,
how strong the signal is, which canonical ``coverage_labels[]`` a future PagePlan
should declare for it, and useful ``search_hints[]`` ideas. Low-signal and missing
families are reported explicitly, never hidden.

Hard discipline (mirrors the rest of the pipeline):

- **Deterministic, LLM-free, network-free.** Detection is pure path / pattern /
  query-pack / symbol-name scanning of artifacts Phase 1 already produced
  (``inventory/files.jsonl``, ``queries/results/rg.jsonl``, ``symbols/symbols.jsonl``,
  ``contracts/openapi.json``). No model call, no embedding, no I/O of its own.
- **Planner CONTEXT, not evidence.** A detected signal tells the planner *where to
  look*, so it can plan a page and tag a coverage label. It is NEVER citeable
  Phase 3 evidence — repo claims must still cite exact handles from
  ``planning-handles.md`` and resolve through the citation manifest.
- **Honest matching.** Directory tokens match whole path segments; basename and
  symbol tokens match on alphanumeric word boundaries (so ``research`` never
  satisfies ``search`` and ``memoryless`` never satisfies ``memory``). Generated,
  vendored, and binary files are skipped — they are not topic signals.

The detector registry lives here (separate from ``taxonomy.py``) so the Phase-2
plan-text validator and the Phase-1 source detector stay independently focused; an
import-time invariant asserts the two never drift apart in family coverage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .taxonomy import MANDATORY_TOPIC_FAMILIES, family_by_key, family_keys

COVERAGE_SIGNALS_SCHEMA_VERSION = "phase1-coverage-signals-v1"

# Per-family display + per-family caps so the markdown stays compact and the JSON
# bounded regardless of repository size.
_MAX_PATHS_PER_FAMILY = 15
_MAX_SYMBOLS_PER_FAMILY = 12
_MAX_QUERY_EXAMPLES = 3
_MAX_GLOSSARY_TERMS = 24

STATUS_PRESENT = "present"
STATUS_LOW = "low"
STATUS_MISSING = "missing"
STATUS_SYNTHESIZED = "synthesized"


# --- detector model -----------------------------------------------------------
@dataclass(frozen=True)
class FamilyDetector:
    """Deterministic source-detection rules for one topic family.

    ``extensions``     file extensions (lower-case, with dot) that signal the family.
    ``dir_tokens``     whole path-segment (directory) names that signal the family.
    ``basename_exact`` exact lower-cased basenames that signal the family.
    ``basename_tokens``word/phrase signals matched on alphanumeric boundaries inside
                       a file's basename.
    ``path_prefixes``  lower-cased path prefixes (``str.startswith``) that signal it.
    ``query_packs``    ripgrep pack names (``queries/results/rg.jsonl``) that signal it.
    ``symbol_tokens``  word signals matched on boundaries inside a ``symbol_id``/name.
    ``search_hints``   curated ``search_hints[]`` ideas for a future PagePlan.
    ``synthesized``    True for a family with no direct source files (the glossary),
                       which the planner synthesizes from repo-wide vocabulary.
    """

    extensions: tuple[str, ...] = ()
    dir_tokens: tuple[str, ...] = ()
    basename_exact: tuple[str, ...] = ()
    basename_tokens: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    query_packs: tuple[str, ...] = ()
    symbol_tokens: tuple[str, ...] = ()
    search_hints: tuple[str, ...] = ()
    synthesized: bool = False


# RAGFlow-informed but generic. Tokens are chosen to be distinctive: a broad,
# generic file must not accidentally satisfy a deep family. Overlap between two
# genuinely-related families (e.g. a task server under ``svr/``) is acceptable —
# these are recall hints, not exclusive classifications.
DETECTORS: dict[str, FamilyDetector] = {
    "frontend": FamilyDetector(
        extensions=(".tsx", ".jsx", ".vue", ".svelte", ".scss", ".less"),
        dir_tokens=("web", "frontend", "ui", "i18n", "locales", "locale"),
        basename_exact=("package.json", "tsconfig.json", ".umirc.ts",
                        "tailwind.config.js", "tailwind.config.ts", "vite.config.ts"),
        basename_tokens=("tailwind", "umirc", "vite", "webpack", "i18n"),
        search_hints=("frontend module layout, routing, and state management",
                      "i18n locale resource files",
                      "ui component library directory"),
    ),
    "memory": FamilyDetector(
        dir_tokens=("memory",),
        basename_tokens=("memory",),
        symbol_tokens=("memory",),
        search_hints=("memory api and storage modules",
                      "episodic / semantic / procedural memory implementation"),
    ),
    "queue-system": FamilyDetector(
        dir_tokens=("queue", "queues", "workers", "svr"),
        basename_tokens=("queue", "worker", "celery", "dramatiq", "huey",
                         "consumer", "broker", "scheduler"),
        query_packs=("task_workers",),
        symbol_tokens=("celery", "taskqueue"),
        search_hints=("task queue names and worker registration",
                      "redis streams producers/consumers and task lifecycle"),
    ),
    "helm-k8s": FamilyDetector(
        dir_tokens=("helm", "charts", "chart", "kubernetes", "k8s", "kube"),
        basename_exact=("chart.yaml", "values.yaml"),
        basename_tokens=("values", "ingress", "deployment", "statefulset",
                         "configmap"),
        search_hints=("helm chart values and templates",
                      "kubernetes manifests, services, and ingress"),
    ),
    "ci-cd-build": FamilyDetector(
        dir_tokens=(".github", "workflows"),
        basename_exact=("dockerfile", "makefile", "docker-compose.yml",
                        "docker-compose.yaml", "jenkinsfile", ".dockerignore"),
        basename_tokens=("dockerfile", "docker-compose", "makefile"),
        path_prefixes=(".github/",),
        search_hints=("docker build flow and image publishing",
                      "github actions / ci workflows and release scripts"),
    ),
    "go-native": FamilyDetector(
        extensions=(".go",),
        dir_tokens=("cmd", "golang"),
        basename_exact=("go.mod",),
        search_hints=("go server / native component entrypoints and build modes",
                      "python ↔ go integration points"),
    ),
    "retrieval-internals": FamilyDetector(
        basename_tokens=("rerank", "ranker", "retriever", "retrieval", "hybrid",
                         "recall", "dealer", "docstore"),
        symbol_tokens=("rerank", "retriever", "hybrid", "dealer", "docstore"),
        search_hints=("document store abstraction and index selection",
                      "hybrid search, reranking, filtering, and citation insertion"),
    ),
    "doc-processing": FamilyDetector(
        dir_tokens=("deepdoc", "mineru", "parsers"),
        basename_tokens=("parser", "chunk", "chunker", "ocr", "layout",
                         "deepdoc", "mineru", "embedding"),
        symbol_tokens=("parser", "chunk", "ocr", "layout"),
        search_hints=("parser factory and DeepDoc/MinerU operators",
                      "chunking strategy, embedding, and upload-to-index stages"),
    ),
    "llm-internals": FamilyDetector(
        dir_tokens=("llm",),
        basename_tokens=("llmbundle", "chat_model", "embedding_model",
                         "rerank_model", "cv_model", "provider"),
        query_packs=("llm_integrations",),
        symbol_tokens=("llmbundle",),
        search_hints=("LLMBundle, model registration, and provider implementations",
                      "tool/function calling, retry/backoff, and usage tracking"),
    ),
    "user-tenant-admin-health": FamilyDetector(
        dir_tokens=("admin",),
        basename_tokens=("tenant", "admin", "health", "probe", "user_service",
                         "user_app"),
        symbol_tokens=("tenant", "admin"),
        search_hints=("user/tenant management and admin routes/services",
                      "health endpoints, status probes, and system settings"),
    ),
    "sandbox-executor": FamilyDetector(
        dir_tokens=("sandbox",),
        basename_tokens=("sandbox",),
        symbol_tokens=("sandbox",),
        search_hints=("sandbox manager and provider registry",
                      "code execution tool and security boundaries"),
    ),
    "migrations-operations": FamilyDetector(
        dir_tokens=("migration", "migrations", "alembic"),
        basename_tokens=("migration", "migrate", "alembic", "oceanbase",
                         "upgrade", "schema_sync"),
        symbol_tokens=("migration", "migrate"),
        search_hints=("database migrations and schema sync",
                      "ES→OceanBase migration, reset/admin utility scripts"),
    ),
    "glossary": FamilyDetector(
        synthesized=True,
        search_hints=("repo-specific component/service/queue/data-store names",
                      "acronyms and concepts used across the guide"),
    ),
}


def _assert_detectors_well_formed() -> None:
    """Every mandatory family has exactly one detector; non-synthesized detectors
    declare at least one source signal. Keeps the registry honest if it is edited
    later, and guarantees it never drifts from ``taxonomy.family_keys()``."""
    if set(DETECTORS) != set(family_keys()):
        raise ValueError("DETECTORS keys must equal taxonomy.family_keys()")
    for key, det in DETECTORS.items():
        if det.synthesized:
            continue
        if not (det.extensions or det.dir_tokens or det.basename_exact
                or det.basename_tokens or det.path_prefixes or det.query_packs
                or det.symbol_tokens):
            raise ValueError(f"detector {key!r} declares no source signal")


_assert_detectors_well_formed()


# --- coverage-signal result model ---------------------------------------------
@dataclass
class FamilySignal:
    """The deterministic Phase-1 coverage signal for one topic family."""

    key: str
    label: str
    status: str                                     # present|low|missing|synthesized
    suggested_labels: list = field(default_factory=list)   # coverage_labels[] ideas
    file_count: int = 0
    query_hit_count: int = 0
    symbol_count: int = 0
    candidate_paths: list = field(default_factory=list)    # [{path,category,reasons}]
    query_packs: list = field(default_factory=list)        # [{pack,hits,examples}]
    symbols: list = field(default_factory=list)            # matched symbol_ids
    synthesized_from: list = field(default_factory=list)   # glossary-only term seeds
    search_hints: list = field(default_factory=list)       # PagePlan search_hints[]
    notes: list = field(default_factory=list)              # low-signal/missing notes

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "suggested_labels": list(self.suggested_labels),
            "file_count": self.file_count,
            "query_hit_count": self.query_hit_count,
            "symbol_count": self.symbol_count,
            "candidate_paths": list(self.candidate_paths),
            "query_packs": list(self.query_packs),
            "symbols": list(self.symbols),
            "synthesized_from": list(self.synthesized_from),
            "search_hints": list(self.search_hints),
            "notes": list(self.notes),
        }


@dataclass
class CoverageSignals:
    """Whole-bundle coverage signals across the mandatory topic taxonomy."""

    schema_version: str
    repo_root: str
    family_count: int
    present_count: int
    low_count: int
    missing_count: int
    synthesized_count: int
    families: list = field(default_factory=list)           # FamilySignal

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "repo_root": self.repo_root,
            "citeable_as_evidence": False,
            "role": "planner_context",
            "family_count": self.family_count,
            "present_count": self.present_count,
            "low_count": self.low_count,
            "missing_count": self.missing_count,
            "synthesized_count": self.synthesized_count,
            "families": [f.to_dict() for f in self.families],
        }


# --- matching helpers ---------------------------------------------------------
def _bounded(text: str, phrase: str) -> bool:
    """Whole-word / whole-phrase boundary match on already-lower-cased ``text``.

    A signal must not match inside a larger alphanumeric run: ``search`` must not
    match ``research``, ``memory`` must not match ``memoryless``. Internal
    separators (``.``, ``_``, ``-``) in a basename count as boundaries, so
    ``task_queue`` matches the ``queue`` token and ``docker-compose.yml`` matches
    the ``docker-compose`` phrase."""
    if not phrase:
        return False
    pat = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pat, text) is not None


def _basename(path_lower: str) -> str:
    return path_lower.rsplit("/", 1)[-1]


def _dir_segments(path_lower: str) -> list:
    parts = path_lower.split("/")
    return parts[:-1]   # directories only (exclude the basename)


def _file_reasons(row: dict, det: FamilyDetector) -> list:
    """Why (if at all) this inventory row signals the detector's family. Returns a
    sorted, de-duplicated list of reason strings, or ``[]`` for no match."""
    path = str(row.get("path") or "")
    if not path:
        return []
    low = path.replace("\\", "/").lower()
    base = _basename(low)
    ext = str(row.get("ext") or "").lower()
    if not ext and "." in base:
        ext = "." + base.rsplit(".", 1)[-1]
    dirs = set(_dir_segments(low))

    reasons: set[str] = set()
    if ext and ext in det.extensions:
        reasons.add(f"ext:{ext}")
    for tok in det.dir_tokens:
        if tok in dirs:
            reasons.add(f"dir:{tok}")
    if base in det.basename_exact:
        reasons.add(f"file:{base}")
    for tok in det.basename_tokens:
        if _bounded(base, tok):
            reasons.add(f"name:{tok}")
    for pref in det.path_prefixes:
        if low.startswith(pref):
            reasons.add(f"path:{pref}")
    return sorted(reasons)


def _is_skippable(row: dict) -> bool:
    """Generated / vendored / binary files are inventoried but are not topic
    signals — skip them so the digest stays source-grounded."""
    return bool(row.get("is_generated") or row.get("is_vendor")
                or row.get("is_binary"))


def family_candidates(files: list, det: FamilyDetector) -> list:
    """All non-skippable inventory rows that signal ``det``'s family, as
    ``{path, category, reasons}`` dicts sorted by path.

    Uncapped on purpose: the per-family detector slices it to a compact display
    set, while the Phase-A topic-catalog facet builder needs the full list to
    cluster a family's files into subsystems. Sharing this one helper keeps the
    detector and the catalog from ever disagreeing on which files signal a
    family. Deterministic: identical input → identical output."""
    candidates: list[dict] = []
    for row in files:
        if _is_skippable(row):
            continue
        reasons = _file_reasons(row, det)
        if reasons:
            candidates.append({
                "path": str(row.get("path") or ""),
                "category": row.get("category") or "?",
                "reasons": reasons,
            })
    candidates.sort(key=lambda c: c["path"])
    return candidates


def _status_for(file_count: int, query_hit_count: int, symbol_count: int) -> str:
    if file_count == 0 and query_hit_count == 0 and symbol_count == 0:
        return STATUS_MISSING
    if file_count >= 3 or query_hit_count >= 5 or symbol_count >= 3:
        return STATUS_PRESENT
    return STATUS_LOW


def status_for(file_count: int, query_hit_count: int = 0,
               symbol_count: int = 0) -> str:
    """Public wrapper over the canonical signal-strength thresholds so the
    Phase-A topic catalog classifies a facet's file signal exactly as the
    per-family detector does (``present`` ≥3 files, else ``low``, else
    ``missing``)."""
    return _status_for(file_count, query_hit_count, symbol_count)


_NOTE_MISSING = ("No Phase-1 source signal detected for this family. If the "
                 "repository genuinely lacks it, record the absence in the page "
                 "plan's known_gaps[]; do not invent a page or fabricate evidence.")
_NOTE_LOW = ("Weak Phase-1 signal (few candidate sources). Confirm against source "
             "before planning a deep child page; otherwise fold it into a parent "
             "page and flag the uncertainty in verification_needs[].")
_NOTE_CONTEXT = ("Candidate sources are planner CONTEXT for retrieval, not citeable "
                 "evidence — cite exact handles from planning-handles.md instead.")


# --- detection ----------------------------------------------------------------
def _detect_family(key: str, label: str, suggested_labels: list,
                   files: list, rg_hits_by_pack: dict, symbols: list) -> FamilySignal:
    det = DETECTORS[key]

    # 1) candidate files from the inventory (skip generated/vendor/binary).
    candidates = family_candidates(files, det)
    file_count = len(candidates)

    # 2) ripgrep query-pack signals (counts + a few example anchors).
    query_packs: list[dict] = []
    query_hit_count = 0
    for pack in det.query_packs:
        hits = rg_hits_by_pack.get(pack, [])
        if not hits:
            continue
        query_hit_count += len(hits)
        examples = sorted({f"{h.get('path', '?')}:{h.get('line', '?')}"
                           for h in hits})[:_MAX_QUERY_EXAMPLES]
        query_packs.append({"pack": pack, "hits": len(hits), "examples": examples})

    # 3) symbol-name signals (boundary-matched against symbol_id and name).
    matched_syms: list[str] = []
    if det.symbol_tokens:
        for sym in symbols:
            sid = str(sym.get("symbol_id") or "")
            hay = (sid + " " + str(sym.get("name") or "")).lower()
            if any(_bounded(hay, tok) for tok in det.symbol_tokens):
                matched_syms.append(sid)
    matched_syms = sorted(set(matched_syms))
    symbol_count = len(matched_syms)

    status = _status_for(file_count, query_hit_count, symbol_count)
    notes: list[str] = []
    if status == STATUS_MISSING:
        notes.append(_NOTE_MISSING)
    elif status == STATUS_LOW:
        notes.append(_NOTE_LOW)
    if status in (STATUS_PRESENT, STATUS_LOW):
        notes.append(_NOTE_CONTEXT)

    overflow = ""
    if file_count > _MAX_PATHS_PER_FAMILY:
        overflow = (f"+{file_count - _MAX_PATHS_PER_FAMILY} more candidate "
                    "paths in coverage-signals.json")

    sig = FamilySignal(
        key=key, label=label, status=status,
        suggested_labels=list(suggested_labels),
        file_count=file_count, query_hit_count=query_hit_count,
        symbol_count=symbol_count,
        candidate_paths=candidates[:_MAX_PATHS_PER_FAMILY],
        query_packs=query_packs,
        symbols=matched_syms[:_MAX_SYMBOLS_PER_FAMILY],
        search_hints=list(det.search_hints),
        notes=notes)
    if overflow:
        sig.notes.append(overflow)
    return sig


def _top_dirs(bundle) -> list:
    """Repo top-level directories by file count (planner glossary seed)."""
    cov = getattr(bundle, "coverage", None) or {}
    by_dir = cov.get("counts_by_top_dir")
    if isinstance(by_dir, dict) and by_dir:
        return [d for d in by_dir if d and d != "(root)"]
    seen: list[str] = []
    for row in getattr(bundle, "files", []) or []:
        top = row.get("top_dir")
        if top and top != "(root)" and top not in seen:
            seen.append(top)
    return sorted(seen)


def derive_coverage_signals(bundle) -> CoverageSignals:
    """Derive per-family planner-facing coverage signals from a Phase-1 bundle.

    Reads ``bundle.files`` (inventory), ``bundle.rg_hits`` (query packs), and
    ``bundle.symbols`` only. Pure and deterministic: identical input → identical
    output, with no timestamps so the JSON/Markdown are byte-stable across runs."""
    files = list(getattr(bundle, "files", []) or [])
    symbols = list(getattr(bundle, "symbols", []) or [])
    rg_hits_by_pack: dict[str, list] = {}
    for h in getattr(bundle, "rg_hits", []) or []:
        pack = h.get("pack")
        if pack:
            rg_hits_by_pack.setdefault(pack, []).append(h)

    cov = getattr(bundle, "coverage", None) or {}
    repo_root = cov.get("repo_root") or getattr(bundle, "root", "") or ""

    families: list[FamilySignal] = []
    for fam in MANDATORY_TOPIC_FAMILIES:
        taxo = family_by_key(fam.key)
        suggested = [fam.key] + sorted(taxo.coverage_labels if taxo else ())
        if DETECTORS[fam.key].synthesized:
            families.append(_synthesized_family(fam.key, fam.label, suggested,
                                                families, bundle))
        else:
            families.append(_detect_family(fam.key, fam.label, suggested,
                                           files, rg_hits_by_pack, symbols))

    present = sum(1 for f in families if f.status == STATUS_PRESENT)
    low = sum(1 for f in families if f.status == STATUS_LOW)
    missing = sum(1 for f in families if f.status == STATUS_MISSING)
    synth = sum(1 for f in families if f.status == STATUS_SYNTHESIZED)
    return CoverageSignals(
        schema_version=COVERAGE_SIGNALS_SCHEMA_VERSION,
        repo_root=repo_root, family_count=len(families),
        present_count=present, low_count=low, missing_count=missing,
        synthesized_count=synth, families=families)


def _synthesized_family(key: str, label: str, suggested_labels: list,
                        prior: list, bundle) -> FamilySignal:
    """The glossary: no direct source files. Seed it from the other families that
    DO have signal plus the repo's top-level directories, so the planner can build
    terminology from real, named subsystems rather than inventing it."""
    det = DETECTORS[key]
    seeds: list[str] = [f"{f.label} ({f.key})" for f in prior
                        if f.status in (STATUS_PRESENT, STATUS_LOW)]
    seeds += [f"top-dir: {d}" for d in _top_dirs(bundle)]
    seeds = seeds[:_MAX_GLOSSARY_TERMS]
    notes = [
        ("Glossary is SYNTHESIZED, not located: it has no single source file. "
         "Build it from the named subsystems, services, queue names, and "
         "data-store terms surfaced by the other families and the handles "
         "catalog."),
        _NOTE_CONTEXT,
    ]
    return FamilySignal(
        key=key, label=label, status=STATUS_SYNTHESIZED,
        suggested_labels=list(suggested_labels),
        synthesized_from=seeds, search_hints=list(det.search_hints), notes=notes)


# --- planner-facing markdown --------------------------------------------------
_STATUS_MARK = {
    STATUS_PRESENT: "✅ present",
    STATUS_LOW: "🟡 low signal",
    STATUS_MISSING: "❌ missing",
    STATUS_SYNTHESIZED: "🧩 synthesized",
}


def canonical_label_line() -> str:
    """The thirteen canonical coverage labels, comma-joined and code-quoted."""
    return ", ".join(f"`{k}`" for k in family_keys())


def render_signals_markdown(signals: CoverageSignals) -> str:
    """Render the planner-facing ``planning-coverage-signals.md`` digest.

    Always includes the canonical coverage-label vocabulary and a loud
    non-citeable-context warning, and lists every family (including missing /
    low-signal ones) so gaps are visible rather than hidden."""
    L: list[str] = [
        "# Planning — DeepWiki Coverage Signals",
        "",
        "Deterministic, source-derived signals for the 13 mandatory DeepWiki topic "
        "families. They tell the Phase 2 planner WHERE each family most likely "
        "lives in this repository so it can plan a page (or child page) and tag it "
        "with a canonical `coverage_labels[]` value.",
        "",
        "> ⚠️ **Planner CONTEXT, not evidence.** These signals are deterministic "
        "path / pattern / query-pack / symbol scans of the Phase 1 decomposition "
        "bundle. A detected signal is a hint to retrieve, **not** a verified fact "
        "and **not citeable Phase 3 evidence**. Repo-specific claims must still "
        "cite exact handles from `planning-handles.md` that resolve through the "
        "citation manifest. Do **not** put any path from this file in a "
        "SectionPlan `files[]` lane on the strength of this digest alone.",
        "",
        "## Canonical coverage labels",
        "",
        "Tag each planned page with one of these canonical `coverage_labels[]` "
        "values (a broad parent page does NOT count as coverage for a deep child "
        "topic unless that child has its own page, label, and evidence):",
        "",
        canonical_label_line(),
        "",
        "## Coverage-signal summary",
        "",
        f"- Families with signal: **{signals.present_count} present**, "
        f"{signals.low_count} low, {signals.missing_count} missing, "
        f"{signals.synthesized_count} synthesized "
        f"(of {signals.family_count}).",
        "",
        "| family | suggested label | status | files | query hits | symbols |",
        "|---|---|---|---|---|---|",
    ]
    for f in signals.families:
        mark = _STATUS_MARK.get(f.status, f.status)
        L.append(f"| {f.label} | `{f.key}` | {mark} | {f.file_count} | "
                 f"{f.query_hit_count} | {f.symbol_count} |")
    L += ["", "## Per-family signals", ""]
    for f in signals.families:
        L += _render_family(f)
    L.append("_Deterministic Phase 1 output. Planner context only; never citeable "
             "evidence._")
    return "\n".join(L) + "\n"


def _render_family(f: FamilySignal) -> list:
    mark = _STATUS_MARK.get(f.status, f.status)
    L = [f"### `{f.key}` — {f.label}", "",
         f"- Status: **{mark}** "
         f"(files {f.file_count}, query hits {f.query_hit_count}, "
         f"symbols {f.symbol_count})",
         f"- Suggested `coverage_labels[]`: "
         + ", ".join(f"`{x}`" for x in f.suggested_labels)]
    if f.candidate_paths:
        shown = len(f.candidate_paths)
        L.append(f"- Candidate sources ({shown} shown):")
        for c in f.candidate_paths:
            reasons = ", ".join(c["reasons"])
            L.append(f"  - `{c['path']}` ({c['category']}) — {reasons}")
    if f.query_packs:
        for qp in f.query_packs:
            ex = "; ".join(f"`{e}`" for e in qp["examples"])
            L.append(f"- Query pack `{qp['pack']}`: {qp['hits']} hits"
                     + (f" (e.g. {ex})" if ex else ""))
    if f.symbols:
        L.append("- Candidate symbols: "
                 + ", ".join(f"`{s}`" for s in f.symbols))
    if f.synthesized_from:
        L.append("- Synthesize from: "
                 + ", ".join(f"`{s}`" for s in f.synthesized_from))
    if f.search_hints:
        L.append("- Suggested `search_hints[]`: "
                 + "; ".join(f"\"{h}\"" for h in f.search_hints))
    for note in f.notes:
        L.append(f"- Note: {note}")
    L.append("")
    return L
