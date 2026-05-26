"""Backward-compatible re-exports; use llm_client for provider fallback."""

from __future__ import annotations

from .llm_client import (  # noqa: F401
    DEFAULT_OPENROUTER_MODEL as DEFAULT_MODEL,
    LLMError,
    OpenRouterError,
    chat_completion,
    parse_json_response,
)
