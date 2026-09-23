"""Server-side environment/config loading.

All secrets stay server-side: API keys are read from environment variables
and must never be serialized into API responses, prompts, logs or artifacts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmSettings:
    """Server-side LLM configuration (never exposed to the browser)."""

    api_key: str | None
    api_url: str | None
    model: str
    timeout_s: float


def load_llm_settings(environ: dict[str, str] | None = None) -> LlmSettings:
    """Load LLM settings from the server environment."""
    env = environ if environ is not None else os.environ
    try:
        timeout = float(env.get("LLM_TIMEOUT_S", "30"))
    except (TypeError, ValueError):
        timeout = 30.0
    return LlmSettings(
        api_key=env.get("LLM_API_KEY") or None,
        api_url=env.get("LLM_API_URL") or None,
        model=env.get("LLM_MODEL", "demo-explainer-1.0"),
        timeout_s=timeout,
    )


__all__ = ["LlmSettings", "load_llm_settings"]
