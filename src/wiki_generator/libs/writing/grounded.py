"""Grounded two-stage generation for one Phase 4 section (opt-in).

Where the freeform path asks the model for finished Markdown and then validates it,
the grounded path asks the model for a structured **claim plan** (referencing
terminal technical strings only by token-bank id), validates that plan
deterministically, and renders the Markdown itself. Terminal technical-token
invention is thereby prevented upstream — the renderer can only emit exact
token-bank strings — instead of being chased after the fact.

This module owns the per-section grounded loop and its audit trail. It reuses the
EXISTING strict section validator (:func:`validate.validate_section_draft`) on the
rendered output unchanged, so the grounded path is never a weaker path: a rendered
section that fails the strict validator is a deterministic defect (raised, not
re-prompted). A bounded, audited re-prompt is permitted only for the LLM-authored
claim plan, capped by ``options.max_rewrite_attempts``, with exact machine-checked
plan diagnostics — never a retry-until-green loop.
"""
from __future__ import annotations

from . import assemble
from . import claim_plan as cp
from .errors import ProviderFailure, WritingValidationFailure
from .options import COVERAGE_MODE_ENHANCEMENT
from .parse import parse_section_response
from .validate import validate_section_draft


def section_obligations(bundle, sid: str):
    """The section's sufficient required-topic obligations (enhancement only), or
    ``None`` in baseline mode (no required-topic planning is enforced)."""
    if getattr(bundle, "coverage_mode", "baseline") != COVERAGE_MODE_ENHANCEMENT:
        return None
    return (bundle.topic_obligations or {}).get(sid) or []


def generate_grounded_section(options, provider, bundle, writing_packet, *,
                              plan_prompt, token_bank, obligations, out_dir):
    """Run the grounded two-stage flow for one section.

    Returns ``(validation, raw_path, attempts, grounded_meta)`` where ``validation``
    is the SAME :class:`SectionValidation` the freeform tail consumes (built from the
    deterministically rendered Markdown). Raises :class:`ProviderFailure` on missing
    provider text and :class:`WritingValidationFailure` when the claim plan cannot be
    validated within the bounded cap, or when the rendered Markdown fails the strict
    section validator (a deterministic render/token-bank defect, never re-prompted)."""
    sid = writing_packet.section_id

    resp = provider.generate(sid, plan_prompt)
    if resp.raw_text is None:
        raise ProviderFailure(
            f"section {sid!r}: provider returned no claim plan "
            f"(finish_reason={resp.finish_reason}; {resp.error})")
    plan, note = parse_section_response(resp.raw_text)
    gen_meta = {"provider_mode": getattr(provider, "mode", options.provider),
                "model": getattr(provider, "model", None),
                "finish_reason": resp.finish_reason, "usage": resp.usage,
                "parse_note": note, "provider_detail": resp.provider_detail,
                "stage": "claim_plan"}
    raw_path, _ = assemble.write_response_audit(
        out_dir, sid, raw_text=resp.raw_text, parsed=plan, generation_meta=gen_meta)

    pv = cp.validate_claim_plan(
        plan, section_id=sid, token_bank=token_bank,
        allowed_evidence_ids=writing_packet.allowed_evidence_ids,
        evidence_index=bundle.evidence_index, obligations=obligations)

    attempts = 0
    rewrite_enabled = options.uses_live_model and options.max_rewrite_attempts > 0
    while not pv.ok and rewrite_enabled and attempts < options.max_rewrite_attempts:
        attempts += 1
        rprompt = cp.build_claim_plan_rewrite_prompt(
            writing_packet, token_bank, resp.raw_text, pv.problem_lines(),
            obligations=obligations)
        resp = provider.generate(sid, rprompt)
        assemble.write_rewrite_audit(
            out_dir, sid, attempts, prompt=rprompt, raw_text=resp.raw_text,
            problems=pv.problem_lines())
        if resp.raw_text is None:
            raise ProviderFailure(
                f"section {sid!r} claim-plan rewrite {attempts}: provider returned "
                f"no text ({resp.error})")
        plan, note = parse_section_response(resp.raw_text)
        pv = cp.validate_claim_plan(
            plan, section_id=sid, token_bank=token_bank,
            allowed_evidence_ids=writing_packet.allowed_evidence_ids,
            evidence_index=bundle.evidence_index, obligations=obligations)

    assemble.write_plan_validation_audit(out_dir, sid, pv)

    if not pv.ok:
        assemble.write_failure_report(
            out_dir, bundle.root, WritingValidationFailure.category,
            f"section {sid!r} claim plan failed validation after {attempts} "
            f"bounded re-prompt(s): {pv.problem_lines()}")
        raise WritingValidationFailure(
            f"section {sid!r} claim plan failed validation: "
            f"{'; '.join(pv.problem_lines())}")

    rendered = cp.render_section(
        pv, token_bank=token_bank, title=writing_packet.title, section_id=sid,
        obligations=obligations)
    draft = cp.rendered_draft(rendered)
    validation = validate_section_draft(
        section_id=sid, draft=draft, parse_note="grounded-render",
        finish_reason=resp.finish_reason, bundle=bundle)

    if validation.status != "pass":
        # The grounded renderer emits only exact, verbatim token-bank strings and
        # renderer-attached citations, so a strict-validator failure here is a
        # deterministic defect in token extraction/rendering — fix upstream, never
        # re-prompt or weaken the validator.
        assemble.write_failure_report(
            out_dir, bundle.root, WritingValidationFailure.category,
            f"section {sid!r} grounded render failed the strict section validator "
            f"(deterministic defect): {validation.rewriteable_problems}")
        raise WritingValidationFailure(
            f"section {sid!r} grounded render failed strict validation "
            f"(deterministic token-bank/render defect): "
            f"{'; '.join(validation.rewriteable_problems)}")

    grounded_meta = {
        "token_bank_path": f"audit/token-banks/{sid}.json",
        "token_count": len(token_bank.tokens),
        "plan_validation_path": f"audit/plans/{sid}.plan-validation.json",
        "claim_count": len(pv.claims),
        "plan_warnings": list(pv.warnings),
        "rewrite_attempts": attempts,
    }
    return validation, raw_path, attempts, grounded_meta
