"""Load a clean Phase 1-3 bundle and run every Phase 4 precondition gate.

Phase 4 reads (never re-runs) the upstream artifacts: the document plan, section
plans, readiness report, retrieval validation, evidence manifest, and the
per-section EvidencePackets. It then runs five hard gates before any model call:

1. readiness PASS / Failures 0;
2. retrieval validation ``status: pass`` with all required contract checks;
3. no forced or stale provenance (Phase 3 not run with ``--force`` after a
   readiness ``FAIL``; packet SHAs match the live section plans; ids/order/counts
   are one coherent bundle);
4. source-evidence hygiene (no evidence sourced from ``plans/``, ``derived/``,
   planner context, readiness reports, or prior wiki output);
5. all section packets present, one per planned section, each ``validation: pass``.

A failed gate is a hard stop that points back at the phase that owns the fix; it
never repairs, re-retrieves, or invents fallback evidence. The validated bundle
exposes a canonical :class:`EvidenceIndex` keyed by ``evidence_id`` — the only
citeable source evidence for final prose.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .. import util
from ..context_docs import is_generated_context_path, looks_like_context_artifact
from ..evidence.schema import validate_packet
from .errors import BadInputArtifact, GateFailure
from .generated_coverage import (
    build_content_block_obligations,
    build_topic_obligations,
    read_enhancement_gates,
)
from .options import ENFORCING_COVERAGE_MODES

# Bundle subtrees / docs that may never be cited as source evidence.
_NON_SOURCE_PREFIXES = ("plans/", "derived/", "planner-digest/", "wiki/")
_READINESS_REL = "plans/phase3-readiness-report.md"
_RETRIEVAL_VALIDATION_REL = "evidence/retrieval-validation.json"
_EVIDENCE_MANIFEST_REL = "evidence/evidence-manifest.json"
_DOCUMENT_PLAN_REL = "plans/document-plan.json"
_SECTION_PLANS_REL = "plans/section-plans.jsonl"

# Contract checks the retrieval validation MUST contain and pass (spec Gate 2).
_REQUIRED_CONTRACT_CHECKS = (
    "all_sections_have_packets",
    "document_plan_valid",
    "section_plans_valid_jsonl",
    "section_plans_cover_order",
    "capabilities_consistent",
    "packets_schema_valid",
    "evidence_anchors_resolve",
    "no_plan_only_evidence",
    "no_context_artifact_evidence",
)

_STATUS_RE = re.compile(r"^[*_\s]*status[*_\s]*[:：][*_\s]*([A-Za-z]+)", re.IGNORECASE)
_FAILURES_RE = re.compile(r"^[*_\s]*failures[*_\s]*[:：][*_\s]*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class EvidenceItem:
    """One citeable evidence record, resolved from a validated EvidencePacket."""

    evidence_id: str
    section_id: str          # the section whose packet owns this evidence
    lane: str
    type: str
    confidence: str
    source: dict
    excerpt: str
    provenance: dict
    scores: dict
    packet_path: str         # bundle-relative path of the owning packet


@dataclass
class WritingBundle:
    """A loaded, fully-gated Phase 1-3 bundle ready for synthesis."""

    root: str
    document_plan: dict
    section_order: list
    section_plans: dict                       # sid -> section plan row
    section_raw_by_id: dict                   # sid -> stripped raw jsonl line
    packets: dict                             # sid -> packet dict
    packet_paths: dict                        # sid -> bundle-relative path
    evidence_index: dict                      # evidence_id -> EvidenceItem
    section_evidence_ids: dict                # sid -> set[evidence_id]
    retrieval_validation: dict
    readiness_status: dict                    # {"status","failures","warnings"}
    manifest: dict
    run_metadata: dict | None
    gate_report: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # DeepWiki coverage enhancement (opt-in; baseline leaves these inert).
    coverage_mode: str = "baseline"
    evidenced_coverage: dict | None = None    # parsed evidence/evidenced-coverage.json
    topic_obligations: dict = field(default_factory=dict)  # sid -> [obligation]
    # expanded mode: sid -> [content-block obligation] (Phase E content blocks).
    content_block_obligations: dict = field(default_factory=dict)

    def evidence(self, evidence_id: str) -> EvidenceItem | None:
        return self.evidence_index.get(evidence_id)


# --- small typed readers ------------------------------------------------------
def _abs(bundle_root: str, rel: str) -> str:
    return os.path.join(bundle_root, rel)


def _read_json(path: str, label: str):
    if not os.path.isfile(path):
        raise BadInputArtifact(f"missing required artifact: {label} ({path})")
    try:
        return util.read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        raise BadInputArtifact(f"invalid JSON in {label}: {e}") from e


def _read_section_plans(path: str) -> tuple[dict, dict]:
    if not os.path.isfile(path):
        raise BadInputArtifact(
            f"missing required artifact: {_SECTION_PLANS_REL} ({path})")
    plans: dict = {}
    raw_by_id: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                s = line.strip()
                if not s:
                    continue
                try:
                    row = json.loads(s)
                except json.JSONDecodeError as e:
                    raise BadInputArtifact(
                        f"invalid JSONL in {_SECTION_PLANS_REL} line {n}: {e}") from e
                sid = row.get("section_id")
                if not sid:
                    raise BadInputArtifact(
                        f"{_SECTION_PLANS_REL} line {n} missing 'section_id'")
                if sid in plans:
                    raise BadInputArtifact(
                        f"{_SECTION_PLANS_REL} has duplicate section_id {sid!r}")
                plans[sid] = row
                raw_by_id[sid] = s
    except OSError as e:
        raise BadInputArtifact(f"cannot read {_SECTION_PLANS_REL}: {e}") from e
    return plans, raw_by_id


def _load_packets(bundle_root: str, section_order: list) -> tuple[dict, dict]:
    """Load one packet per planned section from ``evidence/packets/<sid>.json``.

    Missing or invalid packet JSON is a bad input artifact (the producer Phase 3
    must emit one per section)."""
    packets: dict = {}
    paths: dict = {}
    for sid in section_order:
        rel = os.path.join("evidence", "packets", f"{sid}.json")
        path = _abs(bundle_root, rel)
        if not os.path.isfile(path):
            raise BadInputArtifact(
                f"missing EvidencePacket for section {sid!r}: {rel}")
        try:
            packets[sid] = util.read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            raise BadInputArtifact(f"invalid EvidencePacket JSON {rel}: {e}") from e
        paths[sid] = rel.replace(os.sep, "/")
    return packets, paths


# --- gates --------------------------------------------------------------------
def parse_readiness(text: str) -> dict:
    """Parse the readiness report's status/failures/warnings. Raises BadInputArtifact
    if the required ``Status:``/``Failures:`` lines are absent (unparseable)."""
    status = None
    failures = None
    warnings = None
    for line in text.splitlines():
        if status is None:
            m = _STATUS_RE.match(line)
            if m:
                status = m.group(1).upper()
                continue
        if failures is None:
            m = _FAILURES_RE.match(line)
            if m:
                failures = int(m.group(1))
                continue
        if warnings is None:
            m = re.match(r"^[*_\s]*warnings[*_\s]*[:：][*_\s]*(\d+)", line, re.IGNORECASE)
            if m:
                warnings = int(m.group(1))
    if status is None or failures is None:
        raise BadInputArtifact(
            f"{_READINESS_REL} did not parse: missing Status/Failures lines")
    return {"status": status, "failures": failures, "warnings": warnings}


def gate_readiness(readiness: dict) -> list[dict]:
    checks = []
    ok_status = readiness["status"] == "PASS"
    checks.append(_check("readiness_status_pass", ok_status,
                         f"Status: {readiness['status']}"))
    ok_fail = readiness["failures"] == 0
    checks.append(_check("readiness_failures_zero", ok_fail,
                         f"Failures: {readiness['failures']}"))
    return checks


def gate_retrieval_validation(val: dict, section_order: list) -> list[dict]:
    checks: list[dict] = []
    checks.append(_check("retrieval_status_pass", val.get("status") == "pass",
                         f"status: {val.get('status')!r}"))
    checks.append(_check("retrieval_failure_category_null",
                         val.get("failure_category") is None,
                         f"failure_category: {val.get('failure_category')!r}"))
    counts = val.get("counts") or {}
    exp = counts.get("sections_expected")
    proc = counts.get("sections_processed")
    wrote = counts.get("packets_written")
    coherent = exp == proc == wrote == len(section_order)
    checks.append(_check(
        "retrieval_counts_consistent", coherent,
        f"expected={exp} processed={proc} written={wrote} "
        f"plan_sections={len(section_order)}"))

    by_name = {c.get("name"): c for c in (val.get("contract_checks") or [])}
    for name in _REQUIRED_CONTRACT_CHECKS:
        c = by_name.get(name)
        if c is None:
            checks.append(_check(f"contract:{name}", False, "missing from validation"))
        else:
            checks.append(_check(f"contract:{name}", c.get("status") == "pass",
                                 c.get("details", "")))
    # Any *present* contract check that is not 'pass' also fails the gate.
    for c in (val.get("contract_checks") or []):
        nm = c.get("name")
        if nm not in _REQUIRED_CONTRACT_CHECKS and c.get("status") != "pass":
            checks.append(_check(f"contract:{nm}", False,
                                 f"present but status={c.get('status')!r}"))
    return checks


def _phase3_force_in_manifest(manifest_text: str) -> tuple[bool, list[str]]:
    """Inspect a command manifest for a Phase 3 invocation carrying ``--force``.

    Returns (force_found, phase3_command_lines). Only the *invoked* command lines
    are inspected (TSV: name<TAB>command<TAB>exit), so a ``--force`` that appears
    merely inside a ``--help`` transcript is never mistaken for a real run."""
    forced = False
    phase3_lines: list[str] = []
    for line in manifest_text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        command = parts[1] if len(parts) >= 2 else line
        toks = command.split()
        is_phase3 = ("retrieve-evidence" in toks
                     or any("phase3_retrieve_evidence" in t for t in toks)
                     or "retrieve-evidence" in command)
        if not is_phase3:
            continue
        phase3_lines.append(command.strip())
        if "--force" in toks:
            forced = True
    return forced, phase3_lines


def gate_force_provenance(bundle_root: str, *, accept_no_force: bool) -> list[dict]:
    """No Phase 3 ``--force`` after readiness FAIL, established from provenance.

    Strong signal: a command manifest present in the bundle that contains no
    forced Phase 3 invocation. If no manifest exists, fail closed unless the
    operator explicitly asserts ``--accept-no-force``."""
    checks: list[dict] = []
    manifest_rel = None
    for rel in ("command-manifest.tsv", "command-manifest.txt"):
        if os.path.isfile(_abs(bundle_root, rel)):
            manifest_rel = rel
            break
    if manifest_rel is not None:
        text = util.read_text(_abs(bundle_root, manifest_rel)) or ""
        forced, phase3_lines = _phase3_force_in_manifest(text)
        checks.append(_check(
            "no_phase3_force", not forced,
            f"command manifest `{manifest_rel}`: "
            + (f"{len(phase3_lines)} Phase 3 invocation(s), none forced"
               if not forced else "Phase 3 invoked with --force")))
        checks.append(_check(
            "force_provenance_available", True,
            f"force provenance read from `{manifest_rel}`"))
    else:
        checks.append(_check(
            "force_provenance_available", bool(accept_no_force),
            "no command manifest in bundle; "
            + ("operator asserted --accept-no-force"
               if accept_no_force
               else "pass --accept-no-force only if Phase 3 ran without --force "
                    "after a readiness PASS")))
    return checks


def gate_stale_and_coherent(bundle: "WritingBundle | _PreBundle") -> list[dict]:
    """Packet SHAs match the live section plans; ids/order/title/counts cohere."""
    checks: list[dict] = []
    section_order = bundle.section_order
    n_extra = set(bundle.packets) - set(section_order)
    checks.append(_check("no_extra_packets", not n_extra,
                         f"unexpected packets: {sorted(n_extra)}" if n_extra
                         else "packet set == section_order"))
    for index, sid in enumerate(section_order):
        plan = bundle.section_plans.get(sid)
        pkt = bundle.packets.get(sid)
        if plan is None:
            checks.append(_check(f"section_plan_present:{sid}", False,
                                 "no SectionPlan row for planned section"))
            continue
        if pkt is None:
            checks.append(_check(f"packet_present:{sid}", False, "no packet"))
            continue
        raw = bundle.section_raw_by_id.get(sid)
        expected_sha = f"sha256:{util.sha256_text(raw)}" if raw is not None else None
        got_sha = (pkt.get("source_plan") or {}).get("section_plan_sha256")
        checks.append(_check(
            f"section_plan_sha:{sid}", expected_sha == got_sha,
            "fresh" if expected_sha == got_sha
            else f"stale packet: plan={expected_sha} packet={got_sha}"))
        want_order = plan.get("order") if isinstance(plan.get("order"), int) \
            else index + 1
        checks.append(_check(
            f"packet_order:{sid}", pkt.get("order") == want_order,
            f"plan order={want_order} packet order={pkt.get('order')}"))
        plan_title = plan.get("title") or sid
        checks.append(_check(
            f"packet_title:{sid}", (pkt.get("title") or sid) == plan_title,
            f"plan title={plan_title!r} packet title={pkt.get('title')!r}"))
    return checks


def gate_source_hygiene(bundle: "WritingBundle | _PreBundle") -> list[dict]:
    """No evidence sources point at non-source bundle subtrees / context docs."""
    checks: list[dict] = []
    offenders: list[str] = []
    for sid, pkt in bundle.packets.items():
        for ev in pkt.get("evidence") or []:
            src = ev.get("source") or {}
            for key in ("artifact", "path"):
                ref = str(src.get(key) or "")
                if not ref:
                    continue
                norm = ref.replace("\\", "/")
                if (norm.startswith(_NON_SOURCE_PREFIXES)
                        or is_generated_context_path(norm)
                        or looks_like_context_artifact(norm)
                        or norm == _READINESS_REL):
                    offenders.append(
                        f"{sid}/{ev.get('evidence_id')}: source.{key}={ref}")
    checks.append(_check("no_non_source_evidence", not offenders,
                         f"{len(offenders)} offending source(s): "
                         + "; ".join(offenders[:5]) if offenders
                         else "all evidence sources are repo source"))
    return checks


def gate_packets_present(bundle: "WritingBundle | _PreBundle") -> list[dict]:
    """One valid packet per planned section: schema-valid, validation pass,
    unique well-formed evidence IDs prefixed by the section."""
    checks: list[dict] = []
    for sid in bundle.section_order:
        pkt = bundle.packets.get(sid)
        if pkt is None:
            checks.append(_check(f"packet:{sid}", False, "missing packet"))
            continue
        if pkt.get("section_id") != sid:
            checks.append(_check(f"packet_section_id:{sid}", False,
                                 f"packet.section_id={pkt.get('section_id')!r}"))
        schema_errors = validate_packet(pkt)
        checks.append(_check(f"packet_schema:{sid}", not schema_errors,
                             "; ".join(schema_errors[:3]) if schema_errors
                             else "schema valid"))
        vstatus = (pkt.get("validation") or {}).get("status")
        # A provenance/meta packet is non-source and carries no evidence; it is a
        # valid pass but is never a normal citeable section.
        checks.append(_check(f"packet_validation_pass:{sid}", vstatus == "pass",
                             f"validation.status={vstatus!r}"))
        ids = [ev.get("evidence_id") for ev in pkt.get("evidence") or []]
        from .schema import EVIDENCE_ID_RE
        malformed = [i for i in ids if not (isinstance(i, str) and EVIDENCE_ID_RE.match(i))]
        prefix = f"ev:{sid}:"
        wrong_prefix = [i for i in ids if isinstance(i, str) and not i.startswith(prefix)]
        dupes = len(ids) != len(set(ids))
        ok_ids = not malformed and not wrong_prefix and not dupes
        checks.append(_check(
            f"packet_evidence_ids:{sid}", ok_ids,
            f"malformed={malformed[:2]} wrong_prefix={wrong_prefix[:2]} dupes={dupes}"
            if not ok_ids else f"{len(ids)} unique ids"))
    return checks


def _check(name: str, ok: bool, details: str) -> dict:
    return {"name": name, "status": "pass" if ok else "fail", "details": details}


# --- a lightweight pre-bundle so gates can run before the index is built ------
@dataclass
class _PreBundle:
    section_order: list
    section_plans: dict
    section_raw_by_id: dict
    packets: dict


def _build_evidence_index(packets: dict, packet_paths: dict) -> tuple[dict, dict]:
    index: dict = {}
    section_ids: dict = {}
    for sid, pkt in packets.items():
        owned: set = set()
        for ev in pkt.get("evidence") or []:
            eid = ev.get("evidence_id")
            owned.add(eid)
            index[eid] = EvidenceItem(
                evidence_id=eid,
                section_id=sid,
                lane=ev.get("lane"),
                type=ev.get("type"),
                confidence=ev.get("confidence"),
                source=ev.get("source") or {},
                excerpt=ev.get("excerpt") or "",
                provenance=ev.get("provenance") or {},
                scores=ev.get("scores") or {},
                packet_path=packet_paths.get(sid, ""),
            )
        section_ids[sid] = owned
    return index, section_ids


def load_and_gate(options) -> WritingBundle:
    """Load every Phase 4 input and run all five gates. Raises BadInputArtifact /
    GateFailure on a fail-closed condition; returns a validated :class:`WritingBundle`."""
    root = options.bundle_root
    if not os.path.isdir(root):
        raise BadInputArtifact(f"not a bundle directory: {root}")

    # 1. inputs (any missing/invalid input is a hard, pre-model stop)
    doc = _read_json(_abs(root, _DOCUMENT_PLAN_REL), _DOCUMENT_PLAN_REL)
    section_order = doc.get("section_order")
    if not isinstance(section_order, list) or not section_order:
        raise BadInputArtifact(f"{_DOCUMENT_PLAN_REL} has no non-empty 'section_order'")
    if len(section_order) != len(set(section_order)):
        raise BadInputArtifact(f"{_DOCUMENT_PLAN_REL} section_order has duplicates")

    section_plans, section_raw_by_id = _read_section_plans(
        _abs(root, _SECTION_PLANS_REL))

    readiness_text = util.read_text(_abs(root, _READINESS_REL))
    if readiness_text is None:
        raise BadInputArtifact(f"missing required artifact: {_READINESS_REL}")
    readiness = parse_readiness(readiness_text)

    val = _read_json(_abs(root, _RETRIEVAL_VALIDATION_REL), _RETRIEVAL_VALIDATION_REL)
    manifest = _read_json(_abs(root, _EVIDENCE_MANIFEST_REL), _EVIDENCE_MANIFEST_REL)
    run_metadata = None
    rm_path = _abs(root, "run-metadata.json")
    if os.path.isfile(rm_path):
        try:
            run_metadata = util.read_json(rm_path)
        except (OSError, ValueError):
            run_metadata = None

    packets, packet_paths = _load_packets(root, section_order)
    pre = _PreBundle(section_order=list(section_order), section_plans=section_plans,
                     section_raw_by_id=section_raw_by_id, packets=packets)

    # 2..5 gates — accumulate the full report, then fail closed once if any failed.
    gate_report: list[dict] = []
    gate_report += [{"gate": "readiness", **c} for c in gate_readiness(readiness)]
    gate_report += [{"gate": "retrieval_validation", **c}
                    for c in gate_retrieval_validation(val, list(section_order))]
    gate_report += [{"gate": "force_provenance", **c}
                    for c in gate_force_provenance(
                        root, accept_no_force=options.accept_no_force)]
    gate_report += [{"gate": "stale_coherent", **c}
                    for c in gate_stale_and_coherent(pre)]
    gate_report += [{"gate": "source_hygiene", **c} for c in gate_source_hygiene(pre)]
    gate_report += [{"gate": "packets_present", **c} for c in gate_packets_present(pre)]

    failed = [c for c in gate_report if c["status"] != "pass"]
    if failed:
        summary = "; ".join(f"[{c['gate']}/{c['name']}] {c['details']}"
                            for c in failed[:8])
        more = "" if len(failed) <= 8 else f" (+{len(failed) - 8} more)"
        raise GateFailure(
            f"{len(failed)} precondition gate check(s) failed: {summary}{more}")

    index, section_ids = _build_evidence_index(packets, packet_paths)
    coverage_mode = getattr(options, "coverage_mode", "baseline")
    bundle = WritingBundle(
        root=root, document_plan=doc, section_order=list(section_order),
        section_plans=section_plans, section_raw_by_id=section_raw_by_id,
        packets=packets, packet_paths=packet_paths, evidence_index=index,
        section_evidence_ids=section_ids, retrieval_validation=val,
        readiness_status=readiness, manifest=manifest, run_metadata=run_metadata,
        gate_report=gate_report, warnings=[], coverage_mode=coverage_mode)

    # Gate 6 (enhancement mode only): the Phase 2 planned-coverage gate and the
    # Phase 3 evidenced-coverage gate must be present, enforced, and passing BEFORE
    # any provider call. Phase 4 consumes these upstream artifacts; it never re-runs
    # Phase 2/3, repairs plans, retrieves evidence, or synthesizes evidence. A
    # missing/baseline/failed upstream gate is a pre-provider GateFailure (exit 3).
    if coverage_mode in ENFORCING_COVERAGE_MODES:
        gate_failures, evidenced = read_enhancement_gates(root, val)
        if gate_failures:
            summary = "; ".join(gate_failures[:6])
            more = "" if len(gate_failures) <= 6 else \
                f" (+{len(gate_failures) - 6} more)"
            raise GateFailure(
                f"{coverage_mode} coverage mode requires passing upstream gates: "
                f"{summary}{more}")
        bundle.evidenced_coverage = evidenced
        bundle.topic_obligations = build_topic_obligations(evidenced)
        # Expanded mode additionally carries content-block obligations (Phase E).
        bundle.content_block_obligations = build_content_block_obligations(evidenced)
    return bundle
