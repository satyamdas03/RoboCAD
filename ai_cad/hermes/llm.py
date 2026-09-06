"""Pluggable LLM caller for HERMES.

Provides a `generate_fn(messages) -> str` compatible with `HermesAgent.run()`.
Supports Anthropic Claude and OpenAI-compatible local endpoints (Ollama).
Tests can pass a deterministic mock instead.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import anthropic
import httpx

from ai_cad.generator import DEFAULT_MODEL, OLLAMA_BASE_URL, OLLAMA_TIMEOUT
from ai_cad.nvidia_client import build_nvidia_caller


HermesCaller = Callable[[list[dict[str, str]]], str]


def _anthropic_base_url() -> str:
    """Return the official Anthropic endpoint, ignoring stale local overrides."""
    base = os.environ.get("ANTHROPIC_BASE_URL")
    if base and ("localhost" in base or "127.0.0.1" in base or ":11434" in base):
        return "https://api.anthropic.com"
    return base or "https://api.anthropic.com"


def _looks_like_local_model(model: str) -> bool:
    return ":" in model and not model.startswith("claude-") and not model.startswith("gpt-")


def _anthropic_create(client, *, model: str, max_tokens: int, messages: list[dict], system: str):
    """Compatibility wrapper for Anthropic SDK temperature handling."""
    major = int(getattr(anthropic, "__version__", "0.0.0").split(".")[0])
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "system": system,
    }
    if model.startswith("claude-fable-5") or model.startswith("claude-sonnet-5") or model.startswith("claude-opus-5"):
        return client.messages.create(**kwargs)
    if major >= 1:
        kwargs["extra_body"] = {"temperature": 0.0}
    else:
        kwargs["temperature"] = 0.0
    return client.messages.create(**kwargs)


def _first_text_block(response) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            return block.text
    if response.content and hasattr(response.content[0], "text"):
        return response.content[0].text
    return ""


def _call_anthropic(messages: list[dict[str, str]], model: str, api_key: str | None) -> str:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return '{"tool_calls": []}'

    client = anthropic.Anthropic(api_key=api_key, base_url=_anthropic_base_url())
    system = ""
    chat_messages = list(messages)
    if chat_messages and chat_messages[0].get("role") == "system":
        system = chat_messages[0].get("content", "")
        chat_messages = chat_messages[1:]

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = _anthropic_create(
                client,
                model=model,
                max_tokens=4096,
                messages=chat_messages,
                system=system,
            )
            text = _first_text_block(response)
            if text:
                return text
        except Exception as exc:
            last_exc = exc
            continue

    error_msg = f"LLM call failed: {last_exc}" if last_exc else "Model returned no text."
    return '{"tool_calls": [], "plan": null, "error": "' + error_msg.replace('"', "'") + '"}'


def _call_ollama(messages: list[dict[str, str]], model: str, base_url: str) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.0,
    }
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        return '{"tool_calls": [], "plan": null, "error": "' + str(exc).replace('"', "'") + '"}'


def _looks_like_nvidia_model(model: str) -> bool:
    return (
        model.startswith("nvidia/")
        or model.startswith("meta/")
        or model.startswith("chatterbox")
        or model in {"nemotron-lightning", "nemotron-super", "nemotron-ultra"}
    )


def build_llm_caller(
    model: str | None = None,
    api_key: str | None = None,
) -> HermesCaller:
    """Return a caller function for HermesAgent.run().

    The returned function accepts a list of message dicts and returns the raw
    model response text. In test environments with no API key, a local model,
    or an explicit OLLAMA endpoint, the caller falls back to an Ollama path.
    """
    model = model or os.environ.get("ROBOCAD_MODEL", DEFAULT_MODEL)
    if _looks_like_nvidia_model(model):
        return build_nvidia_caller(model=model, api_key=api_key)
    if _looks_like_local_model(model):
        base_url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
        return lambda messages: _call_ollama(messages, model, base_url)
    return lambda messages: _call_anthropic(messages, model, api_key)


def deterministic_mock_caller(response_text: str) -> HermesCaller:
    """Return a caller that always returns the provided response text."""
    return lambda messages: response_text
