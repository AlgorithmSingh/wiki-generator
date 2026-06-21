"""Shape a parsed raw plan into the normalized Phase 2 plan artifacts.

Merges the DocumentPlan section metadata (title / order / parent / purpose /
rationale / priority) with the matching SectionPlan (goal / coverage / questions
/ evidence needs), resolves every reference against the Phase 1 indexes via
:class:`~phase1_decomposition.libs.plan_normalization.lookups.Lookups`, and
collects unresolved references. Deterministic; no LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lookups import Lookups
from .parse import RawPlan

_CLEAN_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PLAN_SCHEMA = "phase2-plan-v1"
SECTION_SCHEMA = "phase2-section-plan-v1"


@dataclass
class Result:
    document_plan: dict
    sections: list[dict]
    unresolved: list[dict]
    warnings: list[str]
    raw_document_plan: dict
    raw_section_plans: list[dict]

    @property
    def counts(self) -> dict:
        by_type: dict[str, int] = {}
        for u in self.unresolved:
            by_type[u["type"]] = by_type.get(u["type"], 0) + 1
        return {
            "sections": len(self.sections),
            "unresolved_total": len(self.unresolved),
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


def _resolve_needs(section_id: str, ev: dict, lk: Lookups,
                   unresolved: list[dict], warnings: list[str]) -> dict:
    qpacks, symbols, files, contracts, tests = [], [], [], [], []

    for q in _as_list(ev.get("query_packs")):
        ref = q if isinstance(q, str) else str(q)
        key = lk.resolve_query_pack(ref)
        if key:
            qpacks.append(key)
        else:
            unresolved.append({"section_id": section_id, "type": "query_pack",
                               "input": q, "reason": "no_match", "candidates": []})
            warnings.append(f"[{section_id}] unresolved query pack: {ref!r}")

    sym_in = ev.get("symbols")
    if sym_in is None:
        sym_in = ev.get("symbol_ids")
    for sy in _as_list(sym_in):
        ref = sy.get("input") if isinstance(sy, dict) else sy
        r = lk.resolve_symbol(str(ref))
        symbols.append({"input": ref, "symbol_id": r.symbol_id,
                        "resolution": r.resolution, "candidates": r.candidates})
        if r.resolution in ("no_match", "ambiguous"):
            unresolved.append({"section_id": section_id, "type": "symbol",
                               "input": ref,
                               "reason": "ambiguous" if r.resolution == "ambiguous"
                               else "no_match", "candidates": r.candidates})
            warnings.append(f"[{section_id}] {r.resolution} symbol: {ref!r}")

    files_in = ev.get("files")
    if files_in is None:
        files_in = ev.get("file_anchors")
    for fa in _as_list(files_in):
        ref = fa.get("input") if isinstance(fa, dict) else fa
        r = lk.resolve_file(str(ref))
        files.append({"input": ref, "path": r.path, "anchor": r.anchor,
                      "anchor_confidence": r.anchor_confidence,
                      "resolution": r.resolution, "candidates": r.candidates})
        if r.resolution in ("no_match", "ambiguous"):
            unresolved.append({"section_id": section_id, "type": "file",
                               "input": ref,
                               "reason": "ambiguous" if r.resolution == "ambiguous"
                               else "no_match", "candidates": r.candidates})
            warnings.append(f"[{section_id}] {r.resolution} file: {ref!r}")

    for c in _as_list(ev.get("contracts")):
        res = lk.resolve_contract(c)
        contracts.append(res)
        if res["resolution"] == "no_match":
            unresolved.append({"section_id": section_id, "type": "contract",
                               "input": c, "reason": "no_match", "candidates": []})
            warnings.append(f"[{section_id}] unresolved contract: {c!r}")

    for t in _as_list(ev.get("tests")):
        res = lk.resolve_test(t)
        tests.append(res)
        if res["resolution"] == "ambiguous":
            unresolved.append({"section_id": section_id, "type": "test",
                               "input": t, "reason": "ambiguous",
                               "candidates": res.get("candidates", [])})
            warnings.append(f"[{section_id}] ambiguous test: {t!r}")

    graph_nodes = [g if isinstance(g, str) else str(g)
                   for g in _as_list(ev.get("graph_nodes"))]

    return {
        "query_packs": _dedup(qpacks),
        "symbols": symbols,
        "files": files,
        "contracts": contracts,
        "tests": tests,
        "graph_nodes": graph_nodes,
    }


def _expected_types(needs: dict) -> list[str]:
    order = [("symbols", "symbols"), ("files", "files"),
             ("query_packs", "queries"), ("contracts", "contracts"),
             ("tests", "tests"), ("graph_nodes", "graph")]
    return [label for key, label in order if needs.get(key)]


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

    return {
        "schema_version": SECTION_SCHEMA,
        "section_id": nid,
        "title": title,
        "order": order,
        "parent": meta.get("parent"),
        "priority": meta.get("priority"),
        "purpose": meta.get("purpose") or plan.get("goal") or "",
        "goal": plan.get("goal") or "",
        "rationale": meta.get("rationale"),
        "required_topics": _as_list(plan.get("coverage_requirements")),
        "key_questions": _as_list(plan.get("key_questions")),
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
            "generated_by": "phase1_decomposition normalize-plan",
            "unresolved_count": unresolved_count,
            "warnings": warnings,
        },
    }


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

    for s in meta_sections:
        order += 1
        oid = s.get("id")
        title = s.get("title")
        nid = _section_id(oid, title, used)
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
        warnings.append(f"[{nid}] in section-plans but missing from DocumentPlan")
        sections.append(_build_section(nid, order, None, sp, lk, unresolved, warnings))

    section_order = [s["section_id"] for s in sections]
    document_plan = _document_plan(doc, section_order, lk, source_raw_rel,
                                   provider, len(unresolved), warnings)
    return Result(document_plan=document_plan, sections=sections,
                  unresolved=unresolved, warnings=warnings,
                  raw_document_plan=doc, raw_section_plans=raw.section_plans)
