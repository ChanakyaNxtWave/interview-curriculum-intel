from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .env import load_env

DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    """All configured LLM providers failed."""


# Backward-compatible alias
OpenRouterError = LLMError


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    provider: str
    model: str

    @property
    def model_label(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _provider_order() -> list[str]:
    load_env()
    raw = os.environ.get("LLM_PROVIDER_ORDER", "openrouter,groq,gemini")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _env_key(name: str) -> str | None:
    load_env()
    value = os.environ.get(name, "").strip()
    return value or None


def _openrouter_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> ChatCompletionResult:
    api_key = _env_key("OPENROUTER_API_KEY")
    if not api_key:
        raise LLMError("OPENROUTER_API_KEY is not set")

    resolved_model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    site = os.environ.get("OPENROUTER_HTTP_REFERER")
    title = os.environ.get("OPENROUTER_APP_TITLE", "KP Mapping Workflow")
    if site:
        headers["HTTP-Referer"] = site
    headers["X-Title"] = title

    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=payload)

    if resp.status_code >= 400:
        raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"OpenRouter unexpected response: {data}") from exc
    if content is None or not str(content).strip():
        raise LLMError("OpenRouter returned empty content")

    return ChatCompletionResult(content=str(content), provider="openrouter", model=resolved_model)


def _groq_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> ChatCompletionResult:
    api_key = _env_key("GROQ_API_KEY")
    if not api_key:
        raise LLMError("GROQ_API_KEY is not set")

    resolved_model = model or os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(GROQ_URL, headers=headers, json=payload)

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise LLMError(f"Groq {resp.status_code}: {detail}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Groq unexpected response: {data}") from exc
    if content is None or not str(content).strip():
        raise LLMError("Groq returned empty content")

    return ChatCompletionResult(content=str(content), provider="groq", model=resolved_model)


def _gemini_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> ChatCompletionResult:
    api_key = _env_key("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("GEMINI_API_KEY is not set")

    resolved_model = model or os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    url = GEMINI_URL.format(model=resolved_model)

    system_text = ""
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        if role == "system":
            system_text = text if not system_text else f"{system_text}\n\n{text}"
            continue
        gemini_role = "user" if role == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    if not contents:
        raise LLMError("Gemini: no user/model messages after extracting system prompt")

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, params={"key": api_key}, json=body)

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise LLMError(f"Gemini {resp.status_code}: {detail}")

    data = resp.json()
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Gemini unexpected response: {data}") from exc
    if content is None or not str(content).strip():
        raise LLMError("Gemini returned empty content")

    return ChatCompletionResult(content=str(content), provider="gemini", model=resolved_model)


_PROVIDERS: dict[str, Callable[..., ChatCompletionResult]] = {
    "openrouter": _openrouter_chat,
    "groq": _groq_chat,
    "gemini": _gemini_chat,
}


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> ChatCompletionResult:
    """Call LLM providers in order until one succeeds (see LLM_PROVIDER_ORDER)."""
    load_env()
    order = _provider_order()
    errors: list[str] = []

    for name in order:
        fn = _PROVIDERS.get(name)
        if not fn:
            errors.append(f"{name}: unknown provider (skipped)")
            continue
        try:
            # Model override applies only to the first provider (typically OpenRouter).
            provider_model = model if name == order[0] else None
            return fn(
                messages,
                model=provider_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMError as exc:
            errors.append(f"{name}: {exc}")
        except httpx.HTTPError as exc:
            errors.append(f"{name}: HTTP error: {exc}")

    raise LLMError("All LLM providers failed:\n" + "\n".join(errors))
