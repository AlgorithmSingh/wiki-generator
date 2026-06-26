"""Bounded Phase 2 planner-artifact repair (Patch 2 / Patch 3).

When deterministic normalization leaves a plan that is NOT Phase-3-ready — a
malformed required ``SectionPlan`` JSONL row, an unresolved exact-lane reference,
or a diagnostic-only user section — and Vertex/Gemini is available, this module
re-prompts the planner for *corrected planning artifacts only* (no wiki prose),
validates them with the same strict deterministic parser/normalizer/readiness
gate, and accepts the repair only when readiness passes.

Hard constraints (spec "Patch 2 healing policy"):
- attempts capped (``max_attempts`` ≤ 2);
- every attempt is audited: request, raw bad artifacts, exact errors, response,
  and the validation report are written under ``<out>/repair/``;
- section_ids stay 1:1 with the original DocumentPlan, except a diagnostic-only
  section may be removed or converted to a controlled provenance/meta section;
- if Vertex/Gemini is unavailable, the cap is exhausted, or the repaired artifacts
  still fail validation, this fails LOUDLY (raises) — it never silently continues.

This is a Phase 2 planner-artifact repair before canonical normalization. It is
NOT a Phase 3 retry loop, not a product ``--section`` mode, and Phase 3 never
invokes it. The Gemini call is injected (``client_call``) so it is fully testable.
"""
from __future__ import annotations

import json
import os

from ..util import read_text, write_text
from . import normalize as _normalize
from . import parse as _parse
from . import writer as _writer
from .lookups import Lookups
from .parse import ParseError

DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_LOCATION = "us-central1"
MAX_ATTEMPTS_HARD_CAP = 2


class RepairUnavailable(RuntimeError):
    """Repair is needed but Vertex/Gemini cannot be reached (fail loudly)."""


class RepairFailed(RuntimeError):
    """Repair ran but could not produce valid, Phase-3-ready artifacts."""


REPAIR_SYSTEM = """You repair Phase 2 DeepWiki *planning artifacts*. You output \
ONLY corrected planning artifacts — never wiki prose, never new plan semantics.

You are given the planner's raw `plans/document-plan.json` and \
`plans/section-plans.jsonl`, the exact deterministic readiness errors they \
produced, and a `planning-handles.md` catalog of EXACT retrieval handles. Fix \
every listed error and return the two corrected artifacts.

Hard rules:
- Make the MINIMAL correction. Change ONLY the specific invalid entries named in \
the errors. Keep every already-valid exact handle exactly where it is — do NOT \
move valid `symbol_ids`/`file_anchors`/`contracts`/`tests`/`graph_nodes` into \
`search_hints[]`. For each invalid exact-lane entry: replace it with the correct \
exact handle from `planning-handles.md` if one exists, otherwise move just that \
one entry to `search_hints[]`. Leave all other fields of every section untouched.
- Keep `section_id`s 1:1 with the original DocumentPlan. Do NOT add, rename, or \
reorder sections. You MAY drop a section ONLY if it is flagged \
`diagnostic_only_user_section`, or instead convert it to a controlled provenance \
section by adding `"role":"provenance"` to it.
- Exact lanes hold ONLY exact handles copied from `planning-handles.md`: \
`symbol_ids` exact `symbol_id`; `file_anchors` exact repo files (never a \
directory or trailing-slash path; never `derived/planning-*.md`); `contracts` \
exact `METHOD /path`; `graph_nodes` exact `node_id`; `query_packs` canonical \
keys. If you cannot name an exact handle, move the request to `search_hints[]`.
- `section-plans.jsonl` must be valid JSONL: exactly one complete JSON object per \
line, no bare strings, no comments, no prose between or inside objects. All prose \
belongs in a named field (`verification_needs[]` for verification work, \
`known_gaps[]` for uncertainty).
- `derived/planning-gaps.md` and other diagnostics are internal planning context, \
not source evidence. Do not put them in `file_anchors[]`. Do not create a normal \
"Known gaps / unverified" section from them; attach uncertainty to the affected \
real sections via `verification_needs[]` instead.

Output exactly two fenced blocks, each preceded by a one-line `text` fence naming \
the file:
1. a fence naming `plans/document-plan.json`, then the corrected JSON object;
2. a fence naming `plans/section-plans.jsonl`, then the corrected JSONL.
No other commentary."""


def _normalize_text(bundle_dir: str, text: str, lookups: Lookups,
                    provider: str | None) -> _normalize.Result:
    raw = _parse.parse(text)
    return _normalize.normalize(raw, lookups, "plans/phase2-repair-input.md", provider)


def _extract_document_plan_for_identity(text: str) -> dict | None:
    """Best-effort extraction of only the DocumentPlan from a malformed raw
    response so repair can still enforce 1:1 section identity. This does NOT pick
    a SectionPlans block and therefore does not weaken the strict parser's
    ambiguity checks."""
    warnings: list[str] = []
    try:
        blocks = _parse._label_blocks(_parse._scan_blocks(text))  # type: ignore[attr-defined]
        obj = _parse._pick_document_plan(blocks, warnings, text)  # type: ignore[attr-defined]
    except ParseError:
        return None
    return obj if isinstance(obj, dict) else None


def _section_order_from_document_plan(document_plan: dict | None) -> list[str]:
    if not isinstance(document_plan, dict):
        return []
    order: list[str] = []
    for section in document_plan.get("sections") or []:
        if isinstance(section, dict):
            sid = section.get("id") or section.get("section_id")
            if isinstance(sid, str) and sid:
                order.append(sid)
    return order


def _parse_error_targets(message: str, document_plan: dict | None) -> dict:
    return {
        "sections": {},
        "parse_diagnostics": [{
            "severity": "failure",
            "reason": "raw_planning_response_parse_error",
            "message": message,
            "remediation": (
                "Return exactly one unambiguous `plans/document-plan.json` block "
                "and exactly one unambiguous `plans/section-plans.jsonl` block. "
                "Do not include extra JSONL/NDJSON fences, empty JSONL fences, "
                "or alternate SectionPlans candidates."
            ),
        }],
        "diagnostic_only_sections": [],
        "document_plan_section_order": _section_order_from_document_plan(document_plan),
    }


def repair_targets(result: _normalize.Result) -> dict:
    """Serializable per-section readiness errors + parse diagnostics for the prompt."""
    failures = _writer._readiness_failures(result)
    return {
        "sections": {sid: errs for sid, errs in failures.items() if errs},
        "parse_diagnostics": [d for d in result.parse_diagnostics
                              if d.get("severity") == "failure"],
        "diagnostic_only_sections": sorted(
            sid for sid, errs in failures.items()
            for e in errs if e.get("reason") == "diagnostic_only_user_section"),
    }


def _handles_text(bundle_dir: str) -> str:
    for rel in ("derived/planning-handles.md", "planner-digest/planning-handles.md"):
        text = read_text(os.path.join(bundle_dir, rel))
        if text:
            return text
    return ""


def build_repair_user(raw_response_text: str, targets: dict, handles: str,
                      prior_problems: list[str] | None = None,
                      obligation_diagnostics: list | None = None) -> str:
    parts = [
        "Fix the planning artifacts below so the deterministic readiness gate "
        "passes. Return corrected `plans/document-plan.json` and "
        "`plans/section-plans.jsonl` only.",
        "",
        "## Readiness errors to fix (deterministic)",
        "```json",
        json.dumps(targets, indent=2, sort_keys=True),
        "```",
    ]
    if obligation_diagnostics:
        parts += [
            "",
            "## Topic-obligation gate failures to fix (enhancement mode)",
            "Each required topic below has NO complete exact citeable evidence "
            "obligation. For each, add or fix its `topic_evidence_requirements[]` "
            "row: `required:true`, and `source_fields[]` naming the EXACT normalized "
            "lanes — `retrieval_needs.files[i]`, `retrieval_needs.symbols[i]`, "
            "`retrieval_needs.contracts[i]`, `retrieval_needs.tests[i]`, or "
            "`retrieval_needs.query_packs[i]` — that ground the topic, and make sure "
            "the matching exact handle is actually present in that section's "
            "`evidence_needs`. Do NOT invent evidence. Do NOT rely on broad recall "
            "(`search_hints`/`graph_nodes`) — broad recall is never sufficient for a "
            "required topic. Raw `evidence_needs.*` source-field names are normalized "
            "by Phase 2 only when they resolve exactly; prefer canonical "
            "`retrieval_needs.*` names.",
            "```json",
            json.dumps(obligation_diagnostics, indent=2, sort_keys=True),
            "```",
        ]
    if prior_problems:
        parts += ["",
                  "## Your previous attempt still failed validation — also fix:",
                  *[f"- {p}" for p in prior_problems]]
    parts += [
        "",
        "## Raw planner response to repair (VERBATIM — includes any malformed or "
        "invalid lines exactly as the planner produced them)",
        raw_response_text.strip(),
    ]
    if handles.strip():
        parts += ["", "## planning-handles.md (copy EXACT handles from here)",
                  "```text", handles.strip(), "```"]
    return "\n".join(parts)


def _enhancement_gates(result: _normalize.Result):
    """Run the Phase 2 enhancement gates over a normalized result.

    Returns ``(problems, obligation_diagnostics, gate_dicts)``:

    - ``problems`` — human-readable gate-failure strings; empty iff BOTH the
      planned-coverage gate and the topic-obligation gate pass (i.e. the plan is
      acceptable for enhancement-mode Phase 3);
    - ``obligation_diagnostics`` — the per-topic remediation list fed back to the
      repair model so it can fix exactly the underspecified required topics;
    - ``gate_dicts`` — the machine-readable verdict recorded in the repair audit.

    Read-only: it never edits/synthesizes/heals the plan. (Lazy import of the
    coverage package mirrors ``writer._coverage_summary_md`` and avoids any import
    cycle at module load.)"""
    from .. import coverage as _coverage

    document_plan, sections = result.document_plan, result.sections
    cov_gate = _coverage.gate_plan_coverage(document_plan, sections,
                                            mode=_coverage.MODE_ENHANCEMENT)
    ob_gate = _coverage.gate_topic_obligations(document_plan, sections,
                                               mode=_coverage.MODE_ENHANCEMENT)
    problems: list[str] = []
    if not cov_gate.passed:
        missing = ", ".join(cov_gate.report.missing_mandatory) or "(unknown)"
        problems.append("planned-coverage gate FAIL: missing mandatory topic "
                        f"families: {missing}")
    if not ob_gate.passed:
        r = ob_gate.report
        problems.append(
            f"topic-obligation gate FAIL: {r.incomplete_count}/"
            f"{r.required_topic_count} required topic(s) lack a complete exact "
            "citeable evidence obligation; blocking sections: "
            + (", ".join(r.blocking_sections) or "(none)"))
    gate_dicts = {
        "coverage_mode": _coverage.MODE_ENHANCEMENT,
        "planned_coverage": cov_gate.to_dict(),
        "topic_obligations": ob_gate.to_dict(),
    }
    return problems, list(ob_gate.report.diagnostics), gate_dicts


def _section_ids_ok_for_order(orig_order: list[str], new: _normalize.Result,
                              removable: set[str]) -> list[str]:
    """Return a list of 1:1 section-id violations (empty == ok). A removable
    (diagnostic-only) section may be absent or converted; nothing may be added."""
    if not orig_order:
        return []
    orig_ids = set(orig_order)
    new_ids = set(new.document_plan["section_order"])
    problems = []
    added = new_ids - orig_ids
    if added:
        problems.append(f"repair added sections not in the original plan: "
                        f"{sorted(added)}")
    removed = (orig_ids - new_ids) - removable
    if removed:
        problems.append(f"repair removed non-diagnostic sections: {sorted(removed)}")
    return problems


def _gemini_client_call(*, model, project, location, api_key,
                        max_output_tokens, temperature):
    """Build a ``call(system, user) -> text`` over Vertex AI or the Gemini API.

    Returns ``(call, mode)`` or raises :class:`RepairUnavailable` if neither a
    Vertex project nor a ``GEMINI_API_KEY`` is configured / the SDK is missing."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RepairUnavailable(
            "the google-genai SDK is not installed (pip install "
            "'wiki-generator[vertex]')") from e

    if project:
        client = genai.Client(vertexai=True, project=project, location=location)
        mode = f"vertex (project={project}, location={location}, model={model})"
    elif api_key:
        client = genai.Client(api_key=api_key)
        mode = f"gemini api key (model={model})"
    else:
        raise RepairUnavailable(
            "no Vertex project (--project / $GOOGLE_CLOUD_PROJECT) and no "
            "$GEMINI_API_KEY; bounded Phase 2 repair cannot run")

    def call(system: str, user: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=temperature,
            max_output_tokens=max_output_tokens)
        try:
            resp = client.models.generate_content(model=model, contents=user,
                                                  config=config)
        except Exception as e:  # SDK/quota/credential/network error -> loud failure
            raise RepairFailed(
                f"Gemini call failed: {type(e).__name__}: {e}") from e
        text = getattr(resp, "text", None)
        if not text:
            cands = getattr(resp, "candidates", None) or []
            fr = getattr(cands[0], "finish_reason", "?") if cands else "?"
            raise RepairFailed(f"model returned no text (finish_reason={fr})")
        return text

    return call, mode


def repair_plan(bundle_dir: str, raw_path: str, out_dir: str, *,
                provider: str | None = "gemini", max_attempts: int = 2,
                project: str | None = None, location: str | None = None,
                model: str = DEFAULT_MODEL, api_key: str | None = None,
                max_output_tokens: int = 32768, temperature: float = 0.1,
                coverage_mode: str = "baseline", client_call=None) -> dict:
    """Normalize ``raw_path``; if it is not acceptable, run bounded Gemini repair
    until it is, then write the canonical plan artifacts to ``out_dir``.

    Acceptance depends on ``coverage_mode``:

    - ``baseline`` (default, unchanged): the old Phase-3 readiness gate only.
    - ``enhancement``: readiness **plus** the deterministic Phase 2 enhancement
      gates (planned coverage + topic obligations). A repair that only passes the
      old readiness but fails the topic-obligation gate is **rejected**; the exact
      topic-obligation diagnostics are fed into the next attempt, and after the hard
      cap it fails loudly. This closes the live-run failure where bounded repair
      reported readiness PASS while strict enhancement normalization still failed
      the topic-obligation gate.

    Raises :class:`RepairUnavailable` / :class:`RepairFailed` on loud failure.
    ``client_call`` may be injected (a ``(system, user) -> text`` callable) for
    testing; otherwise a Vertex/Gemini client is built on demand."""
    from .. import coverage as _coverage

    bundle_dir = os.path.abspath(os.path.expanduser(bundle_dir))
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    max_attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS_HARD_CAP))
    enhancement = coverage_mode == _coverage.MODE_ENHANCEMENT

    text = read_text(raw_path)
    if text is None:
        raise FileNotFoundError(f"raw response not readable: {raw_path}")
    lookups = Lookups.load(bundle_dir)
    result: _normalize.Result | None
    initial_parse_error: str | None = None
    initial_document_plan: dict | None = None
    try:
        result = _normalize_text(bundle_dir, text, lookups, provider)
    except ParseError as e:
        # A malformed/ambiguous LLM-authored planning response is still a valid
        # bounded-repair candidate. Keep the strict parser fail-closed for normal
        # acceptance, but feed the exact parse failure into Step 1b instead of
        # crashing before the audited repair attempt can run.
        result = None
        initial_parse_error = str(e)
        initial_document_plan = _extract_document_plan_for_identity(text)

    # Acceptance: readiness AND (enhancement mode) the planned-coverage +
    # topic-obligation enhancement gates. A plan that already passes readiness but
    # fails an enhancement gate is NOT accepted — it requires bounded repair.
    if result is not None and _writer.readiness_pass(result):
        gate_problems, _, gate_dicts = (
            _enhancement_gates(result) if enhancement else ([], [], None))
        if not gate_problems:
            _writer.write_all(out_dir, result, strict=False, strict_pass=True)
            return {"repaired": False, "attempts": 0, "readiness_pass": True,
                    "coverage_mode": coverage_mode,
                    "enhancement_gates": gate_dicts, "out_dir": out_dir}

    # If even the DocumentPlan is ambiguous/missing, there is no safe section-ID
    # identity baseline. Do not ask a model to choose or invent one.
    if result is None and initial_document_plan is None:
        repair_dir = os.path.join(out_dir, "repair")
        problem = ("raw response did not contain an unambiguous DocumentPlan; "
                   "cannot safely run bounded repair without a section identity baseline")
        _write_repair_report(repair_dir, "not-started", 0,
                             [{"attempt": 0, "ok": False, "problems": [problem]}],
                             accepted=False)
        raise RepairFailed(f"{problem}. See {repair_dir}/repair-report.md")

    # Repair is required. Establish the client now so unavailability fails loudly
    # BEFORE we claim to have started repairing.
    mode = "injected"
    if client_call is None:
        client_call, mode = _gemini_client_call(
            model=model, project=project, location=location, api_key=api_key,
            max_output_tokens=max_output_tokens, temperature=temperature)

    repair_dir = os.path.join(out_dir, "repair")
    orig_result = result  # section ids stay 1:1 with the ORIGINAL plan when parsed
    if orig_result is not None:
        removable = {sid for sid, errs in _writer._readiness_failures(orig_result).items()
                     for e in errs if e.get("reason") == "diagnostic_only_user_section"}
        orig_order = list(orig_result.document_plan["section_order"])
    else:
        removable = set()
        orig_order = _section_order_from_document_plan(initial_document_plan)
    handles = _handles_text(bundle_dir)
    audit: list[dict] = []
    last_problems: list[str] = []
    current_raw = text  # the verbatim artifact the model must repair (Patch 2 §4)
    current_parse_error = initial_parse_error

    for attempt in range(1, max_attempts + 1):
        targets = (repair_targets(result) if result is not None else
                   _parse_error_targets(current_parse_error or "raw response did not parse",
                                        initial_document_plan))
        # Enhancement mode: feed the EXACT topic-obligation diagnostics for the
        # current (residual) plan into the prompt so the model fixes the precise
        # underspecified required topics (not merely the old readiness errors).
        ob_diags_fed: list = []
        if enhancement and result is not None:
            _, ob_diags_fed, _ = _enhancement_gates(result)
        user = build_repair_user(current_raw, targets, handles,
                                 last_problems if attempt > 1 else None,
                                 obligation_diagnostics=ob_diags_fed or None)
        adir = os.path.join(repair_dir, f"attempt-{attempt}")
        write_text(os.path.join(adir, "repair-request.txt"),
                   REPAIR_SYSTEM + "\n\n===== USER =====\n\n" + user)
        # The raw bad artifact saved verbatim (this attempt's input) + the original.
        write_text(os.path.join(adir, "raw-bad-artifacts.md"), current_raw)
        write_text(os.path.join(adir, "errors.json"),
                   json.dumps(targets, indent=2, sort_keys=True))
        if enhancement:
            # Audit: the topic-obligation diagnostics fed to the model this attempt.
            write_text(os.path.join(adir, "obligation-diagnostics-fed.json"),
                       json.dumps(ob_diags_fed, indent=2, sort_keys=True))

        try:
            response = client_call(REPAIR_SYSTEM, user)
        except RepairFailed as e:
            last_problems = [str(e)]
            write_text(os.path.join(adir, "validation.json"),
                       json.dumps({"ok": False, "problems": last_problems}, indent=2))
            audit.append({"attempt": attempt, "ok": False, "problems": last_problems})
            continue
        write_text(os.path.join(adir, "repair-response.md"), response)

        problems: list[str] = []
        gate_dicts = None
        new_result = None
        try:
            new_result = _normalize_text(bundle_dir, response, lookups, provider)
            current_parse_error = None
        except ParseError as e:
            current_parse_error = str(e)
            problems.append(f"repaired response did not parse: {e}")
        if new_result is not None:
            parse_fail = [d for d in new_result.parse_diagnostics
                          if d.get("severity") == "failure"]
            if parse_fail:
                problems.append(f"{len(parse_fail)} malformed JSONL row(s) remain "
                                "after repair")
            problems += _section_ids_ok_for_order(orig_order, new_result, removable)
            if not _writer.readiness_pass(new_result):
                fails = {sid: [e["reason"] for e in errs]
                         for sid, errs in _writer._readiness_failures(new_result).items()
                         if errs}
                problems.append(f"readiness still FAIL: {fails}")
            # Enhancement mode: a repair that only passes old readiness but fails the
            # planned-coverage / topic-obligation gates is REJECTED here (spec
            # "Enhancement repair contract"). The strict post-repair gate verdict is
            # recorded for the audit either way.
            if enhancement:
                gate_problems, _, gate_dicts = _enhancement_gates(new_result)
                problems += gate_problems
            # diff/mapping artifact for review (spec acceptance #5).
            new_order = list(new_result.document_plan["section_order"])
            write_text(os.path.join(adir, "section-mapping.json"), json.dumps({
                "original_section_order": orig_order,
                "repaired_section_order": new_order,
                "removed": sorted(set(orig_order) - set(new_order)),
                "added": sorted(set(new_order) - set(orig_order)),
                "converted_to_provenance": sorted(
                    s["section_id"] for s in new_result.sections
                    if s.get("section_role") == "provenance"),
                "diagnostic_only_removable": sorted(removable),
            }, indent=2))
            if enhancement and gate_dicts is not None:
                # Audit: the final post-repair enhancement-gate verdict this attempt.
                write_text(os.path.join(adir, "enhancement-gates.json"),
                           json.dumps(gate_dicts, indent=2, sort_keys=True))

        write_text(os.path.join(adir, "validation.json"),
                   json.dumps({"ok": not problems, "problems": problems}, indent=2))
        audit.append({"attempt": attempt, "ok": not problems, "problems": problems})

        if not problems and new_result is not None:
            written = _writer.write_all(out_dir, new_result, strict=False,
                                        strict_pass=True)
            write_text(os.path.join(adir, "accepted-response.md"), response)
            _write_repair_report(repair_dir, mode, attempt, audit, accepted=True)
            return {"repaired": True, "attempts": attempt, "readiness_pass": True,
                    "coverage_mode": coverage_mode, "enhancement_gates": gate_dicts,
                    "out_dir": written["out_dir"], "client_mode": mode}

        last_problems = problems
        current_raw = response  # next attempt repairs the model's latest output
        if new_result is not None:
            result = new_result  # feed the residual failures into the next attempt

    _write_repair_report(repair_dir, mode, max_attempts, audit, accepted=False)
    raise RepairFailed(
        f"bounded Phase 2 repair exhausted {max_attempts} attempt(s); last "
        f"problems: {last_problems}. See {repair_dir}/repair-report.md")


def _write_repair_report(repair_dir, mode, attempts, audit, *, accepted) -> None:
    L = ["# Phase 2 planner-artifact repair report", "",
         f"Outcome: {'ACCEPTED' if accepted else 'FAILED'}",
         f"Client: {mode}",
         f"Attempts: {attempts}", "",
         "## Attempts", ""]
    for a in audit:
        L.append(f"- attempt {a['attempt']}: {'ok' if a['ok'] else 'rejected'}")
        for p in a.get("problems") or []:
            L.append(f"  - {p}")
    write_text(os.path.join(repair_dir, "repair-report.md"), "\n".join(L) + "\n")
