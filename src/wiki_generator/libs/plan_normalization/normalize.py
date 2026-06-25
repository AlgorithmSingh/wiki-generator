"""Shape a parsed raw plan into the normalized Phase 2 plan artifacts.

Merges the DocumentPlan section metadata (title / order / parent / purpose /
rationale / priority) with the matching SectionPlan (goal / coverage / questions
/ evidence needs), resolves every reference against the Phase 1 indexes via
:class:`~wiki_generator.libs.plan_normalization.lookups.Lookups`, and
collects unresolved references. Deterministic; no LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..context_docs import looks_like_context_artifact as _looks_like_context_artifact
from ..context_docs import normalize_section_role
from .lookups import Lookups
from .parse import RawPlan

_CLEAN_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIR_SEG = re.compile(r"[/_.\-]+")


def _dir_recall_text(ref) -> str:
    """Deterministic BM25/vector recall text for a directory-like file anchor:
    the cleaned path plus its path segments as words (no prose inference)."""
    p = str(ref).strip().rstrip("/")
    words = [seg for seg in _DIR_SEG.split(p) if seg]
    return " ".join([p, *words]) if words else (p or str(ref).strip())

PLAN_SCHEMA = "phase2-plan-v1"
SECTION_SCHEMA = "phase2-section-plan-v1"


def _contract_ref(c):
    """A ``METHOD /path`` handle string from a contract item that may be a dict."""
    if not isinstance(c, dict):
        return c
    ref = c.get("operation_ref") or c.get("input")
    if not ref and c.get("method") and c.get("path"):
        ref = f"{c['method']} {c['path']}"
    return ref if ref is not None else c.get("path")


def _test_ref(t):
    """A test-file (optionally ``path::function``) handle string from a dict item."""
    if not isinstance(t, dict):
        return t
    if t.get("input"):
        return t["input"]
    path = t.get("path")
    fn = t.get("function") or t.get("nodeid")
    if path and fn:
        return f"{path}::{fn}"
    return path


@dataclass
class Result:
    document_plan: dict
    sections: list[dict]
    unresolved: list[dict]
    warnings: list[str]
    raw_document_plan: dict
    raw_section_plans: list[dict]
    parse_diagnostics: list[dict] = field(default_factory=list)

    @property
    def counts(self) -> dict:
        by_type: dict[str, int] = {}
        for u in self.unresolved:
            # Patch 1: a safely-routed broad directory ref is a warning, not a
            # rejected reference — it must not inflate the unresolved tally.
            if not u.get("blocking", True):
                continue
            by_type[u["type"]] = by_type.get(u["type"], 0) + 1
        return {
            "sections": len(self.sections),
            "unresolved_total": sum(by_type.values()),
            "unresolved_by_type": by_type,
        }


def _slugify(text: str) -> str:
    s = re.sub(r"[^0-9a-z]+", "-", (text or "").casefold()).strip("-")
    return s or "section"


def _section_id(raw_id, title, used: set[str]) -> str:
    base = raw_id if (raw_id and _CLEAN_SLUG.match(str(raw_id))) else _slugify(
        title or str(raw_id or ""))
    cand, n = base, 2
    while cand in used:
        cand, n = f"{base}-{n}", n + 1
    used.add(cand)
    return cand


def _dedup(seq) -> list:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# --- Milestone 2: coverage-enhanced planning fields ---------------------------
_LABEL_CLEAN = re.compile(r"[^0-9a-z]+")


def _coverage_label(x) -> str | None:
    """Normalize one coverage label to the taxonomy's kebab-case form (e.g.
    ``"Queue System"`` / ``"queue_system"`` → ``"queue-system"``), so an explicit
    planner declaration matches the deterministic topic-family taxonomy exactly.
    Returns ``None`` for empty/garbage input. Deterministic; no inference."""
    if x is None:
        return None
    s = _LABEL_CLEAN.sub("-", str(x).casefold()).strip("-")
    return s or None


def _clean_labels(*sources) -> list[str]:
    """Deduped, order-preserving list of kebab-normalized coverage labels merged
    from several optional planner fields (SectionPlan + DocumentPlan meta)."""
    out, seen = [], set()
    for src in sources:
        for x in _as_list(src):
            lbl = _coverage_label(x)
            if lbl and lbl not in seen:
                seen.add(lbl)
                out.append(lbl)
    return out


def _str_list(*sources) -> list[str]:
    """Deduped, order-preserving list of non-empty strings merged from several
    optional planner fields (verbatim — no normalization, this is prose/topics)."""
    out, seen = [], set()
    for src in sources:
        for x in _as_list(src):
            if x is None:
                continue
            s = x if isinstance(x, str) else str(x)
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


# Lane field names a topic_evidence_requirements[] source_field may point at, and
# the acceptable retrieval lanes a topic may declare. These are the exact
# (citeable-evidence) lanes; broad-recall fields (graph_nodes / search_hints) are
# preserved verbatim but never count as exact evidence in Phase 3 enhancement mode.
_TER_ACCEPTABLE_LANES = ("file_anchor", "symbol_anchor", "contract", "test",
                         "query_pack")


def _topic_evidence_requirements(plan: dict) -> list[dict]:
    """Preserve the additive ``topic_evidence_requirements[]`` SectionPlan field.

    This is the deterministic bridge a coverage-enhanced plan provides from a
    required topic to the exact ``retrieval_needs.*`` source fields that must
    yield citeable evidence (spec "Deterministic topic-to-evidence mapping"). It
    is **optional and additive**: a baseline/legacy plan that omits it normalizes
    to ``[]`` and is unaffected. No inference and no synthesis — only structural
    normalization of what the planner authored:

    - keep items that are objects with a non-empty ``topic`` string;
    - ``source_fields[]`` kept verbatim as authored (Phase 3 resolves them against
      the normalized ``retrieval_needs.*`` entries and exact-request coverage);
    - ``required`` defaults to ``True`` (the gate enforces required topics);
    - ``min_items`` is a positive int (default ``1``);
    - ``acceptable_lanes`` defaults to the exact lanes when absent/empty.
    """
    out: list[dict] = []
    for item in _as_list(plan.get("topic_evidence_requirements")):
        if not isinstance(item, dict):
            continue
        topic = item.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            continue
        source_fields = [str(s).strip() for s in _as_list(item.get("source_fields"))
                         if str(s).strip()]
        min_items = item.get("min_items")
        min_items = min_items if isinstance(min_items, int) and min_items >= 1 else 1
        lanes = [str(x).strip() for x in _as_list(item.get("acceptable_lanes"))
                 if str(x).strip()]
        out.append({
            "topic": topic.strip(),
            "required": bool(item.get("required", True)),
            "source_fields": source_fields,
            "min_items": min_items,
            "acceptable_lanes": lanes or list(_TER_ACCEPTABLE_LANES),
        })
    return out


def _resolve_needs(section_id: str, ev: dict, lk: Lookups,
                   unresolved: list[dict], warnings: list[str]) -> dict:
    """Resolve a section's evidence needs into exact retrieval lanes.

    Readiness contract: an exact lane (``symbols``/``files``/``contracts``/
    ``tests``/``graph_nodes``) keeps ONLY resolvable handles. Anything that does
    not resolve to an exact handle — vague text, a non-exact contract, a graph
    display label, an unresolved path — is recorded in ``unresolved`` and routed
    to ``search_hints[]`` (BM25/vector recall text). Planner-context docs
    (``derived/planning-*.md``) are routed to ``context_artifacts[]`` and never
    become citeable ``files`` evidence.
    """
    qpacks, symbols, files, contracts, tests, graph_nodes = [], [], [], [], [], []
    search_hints: list[dict] = []
    context_artifacts: list[dict] = []
    hint_seen: set[str] = set()
    ca_seen: set[str] = set()

    def add_hint(text, scope, reason, source_field=None, source_input=None) -> None:
        if text is None:
            return
        t = str(text).strip()
        if not t or t.casefold() in hint_seen:
            return
        hint_seen.add(t.casefold())
        entry = {"text": t, "scope": list(scope), "reason": reason}
        if source_field is not None:
            entry["source_field"] = source_field
        if source_input is not None:
            entry["source_input"] = source_input
        search_hints.append(entry)

    def add_context_artifact(path, role: str = "planner_context") -> None:
        if not path:
            return
        p = str(path).strip()
        if not p or p in ca_seen:
            return
        ca_seen.add(p)
        context_artifacts.append({"path": p, "role": role,
                                  "citeable_as_evidence": False})

    # --- query packs --------------------------------------------------------
    for q in _as_list(ev.get("query_packs")):
        ref = q if isinstance(q, str) else str(q)
        key = lk.resolve_query_pack(ref)
        if key:
            qpacks.append(key)
        else:
            unresolved.append({"section_id": section_id, "type": "query_pack",
                               "input": q, "reason": "no_match", "candidates": []})
            warnings.append(f"[{section_id}] unresolved query pack: {ref!r}")
            add_hint(ref, ["queries"], "unknown query pack")

    # --- symbols (exact symbol_id / unique alias only) ----------------------
    sym_in = ev.get("symbols")
    if sym_in is None:
        sym_in = ev.get("symbol_ids")
    for sy in _as_list(sym_in):
        ref = sy.get("input") if isinstance(sy, dict) else sy
        r = lk.resolve_symbol(str(ref))
        if r.resolution in ("exact", "unique_alias"):
            symbols.append({"input": ref, "symbol_id": r.symbol_id,
                            "resolution": r.resolution, "candidates": r.candidates})
        else:
            reason = "ambiguous" if r.resolution == "ambiguous" else "no_match"
            unresolved.append({"section_id": section_id, "type": "symbol",
                               "input": ref, "reason": reason,
                               "candidates": r.candidates})
            warnings.append(f"[{section_id}] {r.resolution} symbol: {ref!r}")
            add_hint(ref, ["source"], f"unresolved symbol ({r.resolution})")

    # --- files (real source files; digests -> context_artifacts) ------------
    files_in = ev.get("files")
    if files_in is None:
        files_in = ev.get("file_anchors")
    for fa in _as_list(files_in):
        ref = fa.get("input") if isinstance(fa, dict) else fa
        # A planner-context digest doc is the ONLY thing routed to context_artifacts.
        ctx_path = _looks_like_context_artifact(ref)
        if ctx_path is not None:
            add_context_artifact(ctx_path)
            unresolved.append({"section_id": section_id, "type": "file",
                               "input": ref, "reason": "context_only",
                               "candidates": []})
            warnings.append(
                f"[{section_id}] planner-context doc moved out of files[]: {ref!r}")
            continue
        r = lk.resolve_file(str(ref))
        if r.resolution in ("file_exists", "unique_suffix"):
            files.append({"input": ref, "path": r.path, "anchor": r.anchor,
                          "anchor_confidence": r.anchor_confidence,
                          "resolution": r.resolution, "candidates": r.candidates})
            if r.anchor is not None and r.anchor_confidence in (
                    "file_only", "unresolved"):
                add_hint(r.anchor, ["source"],
                         "loose file anchor (lexical hint, not an exact span)")
        elif r.resolution == "digest_artifact":
            # resolve_file matched a bundle artifact basename. If it is a genuine
            # planner-context doc, relocate it; otherwise it is a real evidence
            # artifact (e.g. contracts/openapi.json — cited by the contract lane)
            # mistakenly placed in files[], so treat it as a recall hint, NOT a
            # context_artifact (which would wrongly flag its legitimate citation).
            cap = _looks_like_context_artifact(r.path)
            if cap is not None:
                add_context_artifact(cap)
                unresolved.append({"section_id": section_id, "type": "file",
                                   "input": ref, "reason": "context_only",
                                   "candidates": []})
                warnings.append(
                    f"[{section_id}] planner-context doc moved out of files[]: {ref!r}")
            else:
                unresolved.append({"section_id": section_id, "type": "file",
                                   "input": ref, "reason": "no_match",
                                   "candidates": []})
                warnings.append(
                    f"[{section_id}] non-source bundle artifact in files[]: {ref!r}")
                add_hint(ref, ["source"], "non-source bundle artifact")
        elif r.resolution != "ambiguous" and lk.is_directory_like(ref):
            # Patch 1: a directory / trailing-slash / path-prefix reference is a
            # useful retrieval *neighbourhood* ("agent/component/"), not an exact
            # citeable file. Route it to search_hints[] (BM25/vector recall text)
            # with full traceability, and record a NON-blocking warning — readiness
            # warns, it does not fail on a safely-routed broad directory ref.
            add_hint(_dir_recall_text(ref), ["source", "bm25", "vector"],
                     "directory-like file anchor routed to search_hints (Patch 1)",
                     source_field="file_anchors[]", source_input=str(ref))
            unresolved.append({
                "section_id": section_id, "type": "file", "input": ref,
                "reason": "directory_like_routed",
                "code": "broad_directory_ref_routed_to_search_hints",
                "source_field": "file_anchors[]",
                "normalized_to": "retrieval_needs.search_hints[]",
                "blocking": False, "candidates": []})
            warnings.append(
                f"[{section_id}] directory-like file anchor routed to "
                f"search_hints[]: {ref!r}")
        else:
            reason = "ambiguous" if r.resolution == "ambiguous" else "no_match"
            unresolved.append({"section_id": section_id, "type": "file",
                               "input": ref, "reason": reason,
                               "candidates": r.candidates})
            warnings.append(f"[{section_id}] {r.resolution} file: {ref!r}")
            add_hint(ref, ["source"], f"unresolved file ({r.resolution})")

    # --- contracts (exact METHOD /path only) --------------------------------
    for c in _as_list(ev.get("contracts")):
        ref = _contract_ref(c)
        res = lk.resolve_contract(ref)
        if res["resolution"] == "exact":
            contracts.append(res)
        else:
            unresolved.append({"section_id": section_id, "type": "contract",
                               "input": ref, "reason": res["resolution"],
                               "candidates": res.get("methods", [])})
            warnings.append(
                f"[{section_id}] non-exact contract ({res['resolution']}): {ref!r}")
            add_hint(ref, ["source", "query_pack:web_routes"],
                     f"non-exact contract ({res['resolution']})")

    # --- tests (exact test file / unique suffix) ----------------------------
    for t in _as_list(ev.get("tests")):
        ref = _test_ref(t)
        res = lk.resolve_test(ref)
        if res["resolution"] in ("test_file", "unique_suffix", "file_exists"):
            tests.append(res)
        else:
            unresolved.append({"section_id": section_id, "type": "test",
                               "input": ref, "reason": res["resolution"],
                               "candidates": res.get("candidates", [])})
            warnings.append(
                f"[{section_id}] non-exact test ({res['resolution']}): {ref!r}")
            add_hint(ref, ["tests"], f"non-exact test ({res['resolution']})")

    # --- graph nodes (exact node_id only; display labels -> hints) ----------
    for g in _as_list(ev.get("graph_nodes")):
        ref = (g.get("node_id") or g.get("input")) if isinstance(g, dict) else g
        r = lk.resolve_graph_node(ref)
        if r.resolution in ("exact", "display_label", "unique_name"):
            graph_nodes.append(r.node_id)
        else:
            unresolved.append({"section_id": section_id, "type": "graph",
                               "input": ref, "reason": r.resolution,
                               "candidates": r.candidates})
            warnings.append(
                f"[{section_id}] unresolved graph node ({r.resolution}): {ref!r}")
            add_hint(ref, ["graph"], f"unresolved graph node ({r.resolution})")

    # --- planner-provided non-exact lanes (already correctly placed) --------
    for h in _as_list(ev.get("search_hints")):
        if isinstance(h, dict):
            add_hint(h.get("text") or h.get("input"), h.get("scope") or [],
                     h.get("reason") or "planner search hint")
        else:
            add_hint(h, [], "planner search hint")
    for ca in _as_list(ev.get("context_artifacts")):
        if isinstance(ca, dict):
            raw = ca.get("path") or ca.get("input")
            role = ca.get("role") or "planner_context"
        else:
            raw, role = ca, "planner_context"
        # Only genuine digest/condensate docs are context_artifacts. A real
        # evidence artifact a planner mislabels as context (e.g.
        # contracts/openapi.json) must NOT enter context_artifacts, or the
        # validator would flag that artifact's legitimate citations.
        cap = _looks_like_context_artifact(raw) if raw else None
        if cap is not None:
            add_context_artifact(cap, role)

    return {
        "query_packs": _dedup(qpacks),
        "symbols": symbols,
        "files": files,
        "contracts": contracts,
        "tests": tests,
        "graph_nodes": _dedup(graph_nodes),
        "search_hints": search_hints,
        "context_artifacts": context_artifacts,
    }


def _expected_types(needs: dict) -> list[str]:
    """Derive expected evidence types from resolvable work only.

    Every exact lane has already been pruned to resolvable handles, so a
    non-empty lane means resolvable work exists. ``graph`` additionally applies
    when a resolvable symbol or file can seed the graph lane (spec rule 5), not
    only when explicit graph nodes are present.
    """
    order = [("symbols", "symbols"), ("files", "files"),
             ("query_packs", "queries"), ("contracts", "contracts"),
             ("tests", "tests"), ("graph_nodes", "graph")]
    out = [label for key, label in order if needs.get(key)]
    if "graph" not in out and (needs.get("symbols") or needs.get("files")):
        out.append("graph")
    return out


def _build_section(nid: str, order: int, meta: dict | None, plan: dict | None,
                   lk: Lookups, unresolved: list[dict],
                   warnings: list[str]) -> dict:
    meta = meta or {}
    plan = plan or {}
    sec_warnings: list[str] = []
    if not meta:
        sec_warnings.append("section present in section-plans but not in DocumentPlan")
    if not plan:
        sec_warnings.append("section present in DocumentPlan but has no SectionPlan")

    title = meta.get("title") or plan.get("title") or nid
    ev = plan.get("evidence_needs") or {}
    before = len(unresolved)
    needs = _resolve_needs(nid, ev, lk, unresolved, warnings)
    section_warnings = sec_warnings + [
        f"{u['type']} {u['reason']}: {u['input']}" for u in unresolved[before:]]

    # Patch 3: a section's role. "provenance"/"meta" sections are controlled
    # provenance notes handled OUTSIDE the normal source-evidence lanes; everything
    # else is a normal source-evidence section that must carry real retrieval signal.
    role = normalize_section_role(
        meta.get("role") or meta.get("kind") or meta.get("section_role")
        or plan.get("role") or plan.get("kind") or plan.get("section_role"))

    # Milestone 2 (DeepWiki coverage enhancement): preserve the optional
    # coverage-enhanced planning fields so the deterministic coverage validator
    # (libs.coverage) can evaluate planned-topic obligations off the normalized
    # plan. All additive and optional — a baseline plan that omits them is
    # unaffected. `parent_section_id` (a hierarchy pointer for parent/child pages)
    # is captured here as the planner provided it and resolved against the planned
    # section ids in a post-pass by ``normalize``; `parent` keeps its existing
    # (raw DocumentPlan meta) value for backward compatibility.
    raw_parent = (meta.get("parent") if meta.get("parent") is not None
                  else (plan.get("parent_section_id") or plan.get("parent_id")
                        or plan.get("parent")))

    return {
        "schema_version": SECTION_SCHEMA,
        "section_id": nid,
        "section_role": role,
        "title": title,
        "order": order,
        "parent": meta.get("parent"),
        "parent_section_id": raw_parent,
        "coverage_labels": _clean_labels(plan.get("coverage_labels"),
                                         meta.get("coverage_labels")),
        "priority": meta.get("priority"),
        "purpose": meta.get("purpose") or plan.get("goal") or "",
        "goal": plan.get("goal") or "",
        "rationale": meta.get("rationale"),
        "required_topics": _str_list(plan.get("coverage_requirements"),
                                     plan.get("required_topics")),
        "topic_evidence_requirements": _topic_evidence_requirements(plan),
        "key_questions": _str_list(plan.get("key_questions")),
        "expected_sources": _str_list(plan.get("expected_sources"),
                                      plan.get("expected_source_handles")),
        "retrieval_needs": needs,
        "expected_evidence_types": _expected_types(needs),
        "depends_on": _as_list(plan.get("depends_on")),
        "verification_needs": _as_list(plan.get("verification_needs")),
        "estimated_size": plan.get("estimated_size"),
        "known_gaps": _as_list(plan.get("known_gaps")),
        "normalization_warnings": section_warnings,
    }


def _document_plan(doc: dict, section_order: list[str], lk: Lookups,
                   source_raw_rel: str, provider: str | None,
                   unresolved_count: int, warnings: list[str]) -> dict:
    repo = doc.get("repo")
    if isinstance(repo, dict):
        repo_name = repo.get("name") or lk.repo_name
        repo_root = repo.get("root") or lk.repo_root
    else:
        repo_name = repo or lk.repo_name
        repo_root = lk.repo_root
    audience = doc.get("audience")
    if isinstance(audience, list):
        audience = ", ".join(str(a) for a in audience)
    return {
        "schema_version": PLAN_SCHEMA,
        "repo": {"name": repo_name, "root": repo_root},
        "title": doc.get("title") or f"{repo_name} Documentation Plan",
        "purpose": doc.get("purpose") or doc.get("one_line_purpose") or "",
        "summary": doc.get("summary") or "",
        "audience": audience or "",
        "section_order": section_order,
        "coverage_goals": _as_list(doc.get("coverage_goals")),
        "known_gaps": _as_list(doc.get("known_gaps")),
        "source_raw_response": source_raw_rel,
        "provider": provider,
        "normalization": {
            "generated_by": "wiki_generator normalize-plan",
            "unresolved_count": unresolved_count,
            "warnings": warnings,
        },
    }


def _resolve_parents(sections: list[dict], id_map: dict[str, str],
                     warnings: list[str]) -> None:
    """Resolve each section's ``parent_section_id`` to a normalized planned id.

    A parent reference the planner wrote against a raw id/title is mapped onto the
    real normalized ``section_id`` when possible. A self-reference is dropped; an
    unresolvable reference is kept verbatim with a NON-blocking warning (the
    hierarchy hint is preserved, never silently lost, and never fails readiness)."""
    for s in sections:
        raw_parent = s.get("parent_section_id")
        if not isinstance(raw_parent, str) or not raw_parent.strip():
            s["parent_section_id"] = None
            continue
        key = raw_parent.strip()
        resolved = id_map.get(key)
        if resolved is None and _CLEAN_SLUG.match(key):
            resolved = id_map.get(_slugify(key))
        if resolved == s["section_id"]:
            s["parent_section_id"] = None
            warnings.append(f"[{s['section_id']}] parent references itself; dropped")
        elif resolved:
            s["parent_section_id"] = resolved
        else:
            s["parent_section_id"] = key
            warnings.append(
                f"[{s['section_id']}] parent_section_id {key!r} does not match any "
                "planned section id (kept as a hierarchy hint, non-blocking)")


def normalize(raw: RawPlan, lk: Lookups, source_raw_rel: str,
              provider: str | None) -> Result:
    warnings: list[str] = list(raw.warnings)
    unresolved: list[dict] = []
    doc = raw.document_plan

    meta_sections = [s for s in _as_list(doc.get("sections")) if isinstance(s, dict)]
    plans_by_id = {sp.get("section_id"): sp for sp in raw.section_plans
                   if isinstance(sp, dict) and sp.get("section_id")}
    plans_by_title = {sp.get("title"): sp for sp in raw.section_plans
                      if isinstance(sp, dict) and sp.get("title")}

    used: set[str] = set()
    sections: list[dict] = []
    consumed: set[int] = set()
    order = 0
    # Map every raw planner id/title onto its normalized section_id so a parent
    # reference (which the planner writes against raw ids) resolves to a real
    # planned section. First write wins on a collision.
    id_map: dict[str, str] = {}

    def _remember(nid: str, *keys) -> None:
        for k in keys:
            if isinstance(k, str) and k and k not in id_map:
                id_map[k] = nid

    for s in meta_sections:
        order += 1
        oid = s.get("id")
        title = s.get("title")
        nid = _section_id(oid, title, used)
        _remember(nid, nid, oid, title)
        plan = plans_by_id.get(oid)
        if plan is not None and id(plan) in consumed:
            plan = None  # already used by an earlier section (duplicate id)
        if plan is None and title is not None:
            cand = plans_by_title.get(title)
            if cand is not None and id(cand) not in consumed:
                plan = cand
        if plan is not None:
            consumed.add(id(plan))
        sections.append(_build_section(nid, order, s, plan, lk, unresolved, warnings))

    # SectionPlans with no matching DocumentPlan entry, in their original order.
    for sp in raw.section_plans:
        if not isinstance(sp, dict) or id(sp) in consumed:
            continue
        order += 1
        nid = _section_id(sp.get("section_id"), sp.get("title"), used)
        _remember(nid, nid, sp.get("section_id"), sp.get("title"))
        warnings.append(f"[{nid}] in section-plans but missing from DocumentPlan")
        sections.append(_build_section(nid, order, None, sp, lk, unresolved, warnings))

    _resolve_parents(sections, id_map, warnings)

    section_order = [s["section_id"] for s in sections]
    document_plan = _document_plan(doc, section_order, lk, source_raw_rel,
                                   provider, len(unresolved), warnings)
    return Result(document_plan=document_plan, sections=sections,
                  unresolved=unresolved, warnings=warnings,
                  raw_document_plan=doc, raw_section_plans=raw.section_plans,
                  parse_diagnostics=list(raw.parse_diagnostics))
