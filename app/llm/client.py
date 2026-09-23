"""LLM-03: LLM client.

Calls one permitted external LLM API with server-side credentials, timeout
and error handling. Returns the frozen ``ExplanationResult`` contract:
explanation text plus status (available / unavailable / failed).

Boundaries (frozen for LLM-03):
  * The API key lives only in server-side settings and the Authorization
    header. It is never placed in prompts, results, logs or artifacts.
  * Transport is injectable (``Transport = Callable[[prompt_text], text]``)
    so success and failure paths are deterministic in tests.
  * Without a transport, the client attempts one HTTP call when a key and
    URL are configured; otherwise it returns controlled ``unavailable``.
  * Timeouts and API errors return controlled ``failed`` — never raise to
    callers, never leak the key in messages.

Explicit failure states use :class:`LlmError` with a stable ``code`` for
validation problems; transport outcomes map to ``ExplanationResult``.

Consumer: FastAPI orchestrator.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Callable

from app.core.config import LlmSettings, load_llm_settings
from app.core.contracts import ExplanationResult, PolicyEvidenceRef
from app.llm.prompt import PromptResult

# Transport: prompt text in, raw model text out. May raise (timeout etc.).
Transport = Callable[[str], str]


class LlmError(ValueError):
    """Controlled client failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class LlmRequest:
    """Sanitized outbound request (key never included)."""

    prompt_text: str
    model: str
    timeout_s: float


def _evidence_refs(prompt: PromptResult) -> list[PolicyEvidenceRef]:
    refs: list[PolicyEvidenceRef] = []
    for chunk_id in prompt.evidence_refs:
        try:
            source_id, _ = chunk_id.split("#", 1)
        except ValueError:
            continue
        refs.append(PolicyEvidenceRef(source_id=source_id, version="1.0.0", chunk_id=chunk_id))
    return refs


def _http_transport(settings: LlmSettings) -> Transport:
    def _call(prompt_text: str) -> str:
        payload = json.dumps({"model": settings.model, "prompt": prompt_text}).encode()
        request = urllib.request.Request(
            settings.api_url or "",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=settings.timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body.get("text") if isinstance(body, dict) else None
        if not text or not str(text).strip():
            raise LlmError("EMPTY_RESPONSE", "LLM API returned no text.")
        return str(text).strip()

    return _call


def explain(
    prompt: PromptResult,
    *,
    settings: LlmSettings | None = None,
    transport: Transport | None = None,
) -> ExplanationResult:
    """Produce an explanation for a rendered prompt (never exposes the key)."""
    if not isinstance(prompt, PromptResult):
        raise LlmError("INVALID_PROMPT", "prompt must be a PromptResult.")
    resolved = settings if settings is not None else load_llm_settings()
    refs = _evidence_refs(prompt)

    call = transport
    if call is None:
        if not resolved.api_key or not resolved.api_url:
            return ExplanationResult(status="unavailable", explanation=None, evidence_refs=refs)
        call = _http_transport(resolved)

    try:
        text = call(prompt.prompt_text)
    except TimeoutError as exc:
        return ExplanationResult(status="failed", explanation=None, evidence_refs=refs)
    except LlmError as exc:
        _ = exc
        return ExplanationResult(status="failed", explanation=None, evidence_refs=refs)
    except Exception:
        return ExplanationResult(status="failed", explanation=None, evidence_refs=refs)

    cleaned = (text or "").strip()
    if not cleaned:
        return ExplanationResult(status="failed", explanation=None, evidence_refs=refs)
    if resolved.api_key and resolved.api_key in cleaned:
        raise LlmError("KEY_LEAK", "Model output echoed the API key; refusing to return it.")
    return ExplanationResult(status="available", explanation=cleaned, evidence_refs=refs)


__all__ = [
    "LlmError",
    "LlmRequest",
    "Transport",
    "explain",
    "load_llm_settings",
]
