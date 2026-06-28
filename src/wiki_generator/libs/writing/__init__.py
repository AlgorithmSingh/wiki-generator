"""Phase 4 — grounded writing / synthesis (no retrieval, no repair).

``run(options)`` consumes one clean Phase 1-3 bundle, gates on upstream success,
builds a compact per-section WritingPacket, drives the configured provider
(Gemini Gem import, direct Gemini API, or Vertex AI), validates every draft for
citation/claim discipline, optionally runs one bounded format/citation rewrite,
then assembles the wiki with a citation manifest, audit trail, validation report,
and run report.

Phase 4 never re-runs Phase 3, never repairs the plan, never invents fallback
evidence, and fails closed on missing/stale/forced/unsupported evidence.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import assemble
from . import claim_plan as cp
from .bundle import load_and_gate
from .errors import (
    BadInputArtifact,
    GateFailure,
    Phase4Error,
    ProviderFailure,
    WritingValidationFailure,
)
from .grounded import generate_grounded_section, section_obligations
from .options import WritingOptions
from .packet import build_writing_packet
from .parse import parse_section_response
from .prompt import build_rewrite_prompt, build_section_prompt
from .provider import build_provider
from .token_bank import build_token_bank
from .validate import validate_document, validate_section_draft

__all__ = [
    "run", "WritingOptions", "WritingResult", "BadInputArtifact", "GateFailure",
    "ProviderFailure", "WritingValidationFailure", "Phase4Error",
]


@dataclass
class WritingResult:
    ok: bool
    status: str                              # prepared | pass | fail
    exit_code: int
    provider_mode: str
    model: str | None
    counts: dict = field(default_factory=dict)
    out_dir: str = ""
    files: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    failure_category: str | None = None
    message: str | None = None


def _gem_handoff_note(options, section_ids) -> str:
    rdir = options.responses_in or os.path.join(options.out_dir, "audit", "responses")
    lines = [
        "# Gemini Gem handoff",
        "",
        "Phase 4 prepared one prompt packet per section under "
        "`wiki/audit/prompts/<section_id>.md`. For each section:",
        "",
        "1. Open the prompt file and paste its full contents into the configured "
        "Gemini Gem.",
        "2. Save the Gem's **verbatim** raw response (the JSON object it returns) to:",
        f"   `{rdir}/<section_id>.raw.txt`",
        "3. When every section has a saved response, run validate + assemble:",
        "",
        "```bash",
        "python -m wiki_generator write-wiki \\",
        f"  --bundle {options.bundle_root} \\",
        "  --provider gemini-gem \\",
        f"  --responses-in {rdir} \\",
        "  --validate-and-assemble",
        "```",
        "",
        "Pasted Gem responses are NOT trusted: each is parsed, citation-checked, and "
        "claim-checked exactly like an automated response, and the run fails closed "
        "if any section cannot be grounded.",
        "",
        "## Sections",
        "",
    ]
    lines += [f"- `{sid}` → prompt `wiki/audit/prompts/{sid}.md`, "
              f"response `{sid}.raw.txt`" for sid in section_ids]
    return "\n".join(lines) + "\n"


def run(options: WritingOptions, *, provider=None) -> WritingResult:
    """Execute Phase 4. Raises a classified :class:`Phase4Error` on any
    fail-closed condition (the CLI wrapper maps it to an exit code)."""
    os.makedirs(options.out_dir, exist_ok=True)

    # 1. load + gate (pre-model hard stops)
    bundle = load_and_gate(options)
    warnings = list(bundle.warnings)
    risk = options.truncation_risk()
    if risk:
        warnings.append(risk)

    # 2. build packets + write the exact prompts BEFORE any model call. In grounded
    # mode the per-section prompt asks for a claim plan (not Markdown), and the
    # deterministic token bank is built and audited up front.
    grounded = options.grounded_claim_plan
    prompts_dir = options.prompt_out or os.path.join(
        options.out_dir, "audit", "prompts")
    packets = {sid: build_writing_packet(bundle, sid) for sid in bundle.section_order}
    token_banks: dict = {}
    obligations_by_sid: dict = {}
    if grounded:
        for sid in bundle.section_order:
            token_banks[sid] = build_token_bank(bundle, sid)
            obligations_by_sid[sid] = section_obligations(bundle, sid)
            assemble.write_token_bank(options.out_dir, sid, token_banks[sid])
        prompts = {sid: cp.build_claim_plan_prompt(
            packets[sid], token_banks[sid], obligations=obligations_by_sid[sid])
            for sid in bundle.section_order}
    else:
        prompts = {sid: build_section_prompt(packets[sid])
                   for sid in bundle.section_order}
    prompt_paths = {sid: assemble.write_prompt(prompts_dir, sid, prompts[sid])
                    for sid in bundle.section_order}

    if options.prepare_only:
        note_path = os.path.join(prompts_dir, "README_GEM_HANDOFF.md")
        from ..util import write_text
        write_text(note_path, _gem_handoff_note(options, bundle.section_order))
        return WritingResult(
            ok=True, status="prepared", exit_code=0, provider_mode=options.provider,
            model=options.model_for_metadata, out_dir=options.out_dir,
            counts={"sections": len(bundle.section_order),
                    "prompts_written": len(prompt_paths)},
            files=[prompt_paths[sid] for sid in bundle.section_order] + [note_path],
            warnings=warnings,
            message=f"prepared {len(prompt_paths)} section prompt(s)")

    # 3. provider (injected for tests; built from options otherwise)
    if provider is None:
        provider = build_provider(options)

    rewrite_enabled = options.uses_live_model and options.max_rewrite_attempts > 0

    # 4. generate + validate (+ bounded rewrite) per section, in document order
    generated: list = []
    for sid in bundle.section_order:
        wp = packets[sid]
        grounded_meta = None
        if grounded:
            # grounded: claim-plan -> deterministic plan validation (bounded audited
            # re-prompt) -> deterministic render -> SAME strict section validator.
            validation, raw_path, attempts, grounded_meta = generate_grounded_section(
                options, provider, bundle, wp, plan_prompt=prompts[sid],
                token_bank=token_banks[sid], obligations=obligations_by_sid[sid],
                out_dir=options.out_dir)
        else:
            resp = provider.generate(sid, prompts[sid])
            if resp.raw_text is None:
                raise ProviderFailure(
                    f"section {sid!r}: provider returned no usable text "
                    f"(finish_reason={resp.finish_reason}; {resp.error}); "
                    f"mode={getattr(provider, 'mode', options.provider)}")
            draft, note = parse_section_response(resp.raw_text)
            gen_meta = {"provider_mode": getattr(provider, "mode", options.provider),
                        "model": getattr(provider, "model", None),
                        "finish_reason": resp.finish_reason, "usage": resp.usage,
                        "parse_note": note, "provider_detail": resp.provider_detail}
            raw_path, _ = assemble.write_response_audit(
                options.out_dir, sid, raw_text=resp.raw_text, parsed=draft,
                generation_meta=gen_meta)
            validation = validate_section_draft(
                section_id=sid, draft=draft, parse_note=note,
                finish_reason=resp.finish_reason, bundle=bundle)

            attempts = 0
            while (validation.status == "rewrite" and rewrite_enabled
                   and attempts < options.max_rewrite_attempts):
                attempts += 1
                rprompt = build_rewrite_prompt(wp, resp.raw_text,
                                               validation.rewriteable_problems)
                resp = provider.generate(sid, rprompt)
                assemble.write_rewrite_audit(
                    options.out_dir, sid, attempts, prompt=rprompt,
                    raw_text=resp.raw_text, problems=validation.rewriteable_problems)
                if resp.raw_text is None:
                    raise ProviderFailure(
                        f"section {sid!r} rewrite {attempts}: provider returned no "
                        f"text ({resp.error})")
                draft, note = parse_section_response(resp.raw_text)
                validation = validate_section_draft(
                    section_id=sid, draft=draft, parse_note=note,
                    finish_reason=resp.finish_reason, bundle=bundle)

        if validation.status != "pass":
            assemble.write_failure_report(
                options.out_dir, bundle.root, WritingValidationFailure.category,
                f"section {sid!r} failed writing validation after {attempts} "
                f"rewrite(s): {validation.rewriteable_problems}")
            raise WritingValidationFailure(
                f"section {sid!r} failed writing validation: "
                f"{'; '.join(validation.rewriteable_problems)}")

        section_file = assemble.write_section_markdown(
            options.out_dir, wp.order, sid, validation.markdown)
        record = assemble.generated_section_record(
            bundle, options, writing_packet=wp, validation=validation,
            prompt_path=prompt_paths[sid], raw_path=raw_path,
            section_file=section_file, attempts=attempts)
        if grounded_meta is not None:
            record["grounded"] = grounded_meta
        generated.append(record)

    # 5. assemble document + manifest + metadata + validation + reports
    manifest = assemble.build_citation_manifest(bundle, generated)
    from ..util import write_text
    index_text = assemble.build_index(bundle, generated, manifest)
    write_text(os.path.join(options.out_dir, "index.md"), index_text)

    validation_doc = validate_document(bundle, generated, manifest, options.out_dir)
    assemble.write_validation(options.out_dir, validation_doc)
    # DeepWiki coverage enhancement: emit the deterministic generated-coverage
    # artifacts (written even on failure, so a failed run leaves an auditable matrix).
    if validation_doc.get("generated_coverage") is not None:
        assemble.write_generated_coverage(
            options.out_dir, validation_doc["generated_coverage"])
    document = assemble.write_generated_metadata(
        options.out_dir, bundle, options, generated, manifest, validation_doc)
    report_path = assemble.write_run_report(
        options.out_dir, bundle=bundle, options=options, document=document,
        validation_doc=validation_doc, warnings=warnings)

    counts = {
        "sections": len(bundle.section_order),
        "generated": validation_doc["generated_count"],
        "distinct_citations": validation_doc["distinct_citations"],
        "evidence_available": len(bundle.evidence_index),
    }
    if validation_doc["status"] != "pass":
        raise WritingValidationFailure(
            "final document validation failed: "
            + "; ".join(validation_doc["failures"][:6]))

    return WritingResult(
        ok=True, status="pass", exit_code=0, provider_mode=options.provider,
        model=options.model_for_metadata, counts=counts, out_dir=options.out_dir,
        files=[document["document_path"], document["citation_manifest_path"],
               document["validation_path"], assemble._rel(bundle.root, report_path)],
        warnings=warnings, message="wiki generated and validated")
