"""Provider abstraction for the three required Phase 4 execution modes.

- ``gemini-gem`` — manual Gemini Gem handoff. Phase 4 prepares prompt packets;
  the operator pastes them into the configured Gem and saves the verbatim raw
  responses; this provider *imports* those files. No API call is made. Gem
  responses are never trusted: they pass the same parser, citation resolver, and
  unsupported-claim checks as automated ones.
- ``direct-gemini-api`` — ``google-genai`` with a ``GEMINI_API_KEY`` (NOT Vertex).
- ``vertex-ai`` — ``google-genai`` with ``GOOGLE_GENAI_USE_VERTEXAI=true`` plus a
  project + location.

Every provider returns a :class:`SectionResponse` carrying the verbatim text, a
finish reason, and token usage when available, so the orchestrator can audit raw
prompts/responses and fail closed on truncation. A provider object can be
injected into the orchestrator for tests so no live call is ever required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import ProviderFailure
from .options import PROVIDER_GEMINI_API, PROVIDER_GEMINI_GEM, PROVIDER_VERTEX


@dataclass
class SectionResponse:
    raw_text: str | None
    finish_reason: str
    usage: dict | None = None
    error: str | None = None
    provider_detail: str | None = None


def normalize_finish_reason(value) -> str:
    """Normalize an SDK finish-reason enum/str to a bare token (e.g. ``STOP``)."""
    if value is None:
        return "UNKNOWN"
    name = getattr(value, "name", None)
    if name:
        return str(name)
    text = str(value)
    return text.rsplit(".", 1)[-1] if "." in text else text


# --- Gemini Gem import (manual handoff) ---------------------------------------
class GemImportProvider:
    mode = PROVIDER_GEMINI_GEM
    model = None

    def __init__(self, responses_dir: str):
        self.responses_dir = responses_dir
        self.detail = f"gemini-gem import from {responses_dir}"

    def generate(self, section_id: str, prompt: str) -> SectionResponse:
        # Accept a few conventional names for the operator's saved response.
        for name in (f"{section_id}.raw.txt", f"{section_id}.txt",
                     f"{section_id}.raw.md", f"{section_id}.md", f"{section_id}.json"):
            path = os.path.join(self.responses_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except OSError as e:
                    return SectionResponse(None, "ERROR", error=str(e),
                                           provider_detail=self.detail)
                return SectionResponse(text, "imported", provider_detail=path)
        return SectionResponse(
            None, "missing",
            error=(f"no pasted Gem response for section {section_id!r} under "
                   f"{self.responses_dir} (expected {section_id}.raw.txt)"),
            provider_detail=self.detail)


# --- direct Gemini API / Vertex AI via google-genai ---------------------------
class GenAIProvider:
    def __init__(self, *, vertexai: bool, model: str, temperature: float,
                 max_output_tokens: int, project: str | None = None,
                 location: str | None = None, api_key: str | None = None):
        self.mode = PROVIDER_VERTEX if vertexai else PROVIDER_GEMINI_API
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as e:
            raise ProviderFailure(
                "the google-genai SDK is not installed "
                "(pip install 'wiki-generator[vertex]')") from e
        self._types = types
        if vertexai:
            if not project or not location:
                raise ProviderFailure(
                    "vertex provider requires a project and location "
                    "(--project/$GOOGLE_CLOUD_PROJECT, --location/$GOOGLE_CLOUD_LOCATION)")
            try:
                self._client = genai.Client(vertexai=True, project=project,
                                            location=location)
            except Exception as e:  # credential / config error
                raise ProviderFailure(
                    f"could not initialize Vertex client: {type(e).__name__}: {e}") from e
            self.detail = (f"vertex (project={project}, location={location}, "
                           f"model={model})")
        else:
            if not api_key:
                raise ProviderFailure(
                    "direct Gemini API mode requires $GEMINI_API_KEY (NOT Vertex); "
                    "do not set GOOGLE_GENAI_USE_VERTEXAI=true for this mode")
            try:
                self._client = genai.Client(api_key=api_key)
            except Exception as e:
                raise ProviderFailure(
                    f"could not initialize Gemini API client: {type(e).__name__}: {e}") \
                    from e
            self.detail = f"direct gemini api (model={model})"

    def generate(self, section_id: str, prompt: str) -> SectionResponse:
        config = self._types.GenerateContentConfig(
            temperature=self.temperature, max_output_tokens=self.max_output_tokens)
        try:
            resp = self._client.models.generate_content(
                model=self.model, contents=prompt, config=config)
        except Exception as e:  # quota / network / safety / credential
            return SectionResponse(None, "ERROR",
                                   error=f"{type(e).__name__}: {e}",
                                   provider_detail=self.detail)
        cands = getattr(resp, "candidates", None) or []
        finish = normalize_finish_reason(
            getattr(cands[0], "finish_reason", None) if cands else None)
        usage = None
        um = getattr(resp, "usage_metadata", None)
        if um is not None:
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", None),
                "output_tokens": getattr(um, "candidates_token_count", None),
                "total_tokens": getattr(um, "total_token_count", None),
            }
        text = getattr(resp, "text", None)
        if not text:
            return SectionResponse(
                None, finish or "EMPTY",
                error=f"model returned no text (finish_reason={finish})",
                usage=usage, provider_detail=self.detail)
        return SectionResponse(text, finish or "STOP", usage=usage,
                               provider_detail=self.detail)


def build_provider(options):
    """Construct the provider for ``options`` (or raise ProviderFailure).

    The gem provider needs a responses directory for the generate path; the
    api/vertex providers build a google-genai client and fail loudly on missing
    credentials/config."""
    if options.provider == PROVIDER_GEMINI_GEM:
        responses_dir = options.responses_in or os.path.join(
            options.out_dir, "audit", "responses")
        return GemImportProvider(responses_dir)
    if options.provider == PROVIDER_GEMINI_API:
        return GenAIProvider(
            vertexai=False, model=options.model, temperature=options.temperature,
            max_output_tokens=options.max_output_tokens, api_key=options.api_key)
    if options.provider == PROVIDER_VERTEX:
        return GenAIProvider(
            vertexai=True, model=options.model, temperature=options.temperature,
            max_output_tokens=options.max_output_tokens,
            project=options.project, location=options.location)
    raise ProviderFailure(f"unknown provider mode: {options.provider}")
