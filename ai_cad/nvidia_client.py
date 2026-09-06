"""Generic NVIDIA NIM REST client for vision, chat, and physics-aware generation.

This module wraps the public NVIDIA NIM endpoints (https://integrate.api.nvidia.com/v1)
so RoboCAD can use NVIDIA models for:

* HERMES reasoning (nemotron LLMs)
* Render critique and design inspection (vision-language models)
* Physics-aware scenario generation (cosmos video/world models)

All calls are synchronous HTTP helpers that return parsed text or bytes. Long-running
or streaming calls are delegated to the callers so the client stays simple and testable.
"""
from __future__ import annotations

import os
import base64
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Model IDs from https://build.nvidia.com/models that are useful for RoboCAD.
CHAT_MODEL_NEMOTRON_LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
CHAT_MODEL_NEMOTRON_SUPER = "nvidia/nemotron-3-super-120b-a12b"
CHAT_MODEL_NEMOTRON_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
CHAT_MODEL_LLAMA_3_2_90B_VISION = "meta/llama-3.2-90b-vision-instruct"
CHAT_MODEL_LLAMA_3_2_11B_VISION = "meta/llama-3.2-11b-vision-instruct"
CHAT_MODEL_MUSE_GLIMMER = "nvidia/muse-glimmer-30b"

COSMOS_NANO = "nvidia/cosmos3-nano"
COSMOS_NANO_REASONER = "nvidia/cosmos3-nano-reasoner"

TTS_DEFAULT = "chatterbox-multilingual-tts"
STT_DEFAULT = "nemotron-asr-streaming"


class NvidiaError(Exception):
    """Raised when a NVIDIA NIM call fails."""


class NvidiaClient:
    """Thin client for NVIDIA NIM REST endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NVIDIA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        if not self.api_key:
            raise NvidiaError("NVIDIA_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    def _post(self, path: str, body: dict[str, Any], *, accept: str = "application/json") -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.post(
                url,
                headers=self._headers(accept=accept),
                json=body,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise NvidiaError(
                f"NIM API error {exc.response.status_code}: {exc.response.text[:400]}"
            ) from exc
        except Exception as exc:
            raise NvidiaError(f"NIM request failed: {exc}") from exc

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str = CHAT_MODEL_NEMOTRON_LIGHTNING,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Call a NVIDIA chat-completion model and return the assistant text."""
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post("/chat/completions", body)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise NvidiaError(f"Unexpected chat response shape: {data}") from exc

    def vision(
        self,
        prompt: str,
        image_bytes: bytes,
        *,
        model: str = CHAT_MODEL_LLAMA_3_2_11B_VISION,
        mime_type: str = "image/png",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Ask a vision-language model about an image encoded as base64."""
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            }
        ]
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post("/chat/completions", body)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise NvidiaError(f"Unexpected vision response shape: {data}") from exc

    def generate_scenario(
        self,
        prompt: str,
        *,
        image_bytes: bytes | None = None,
        model: str = COSMOS_NANO,
    ) -> dict[str, Any]:
        """Generate a physics-aware scenario description or asset using Cosmos.

        The current implementation uses the video-generation endpoint shape. If the
        service returns a video URL, it is passed through; if it returns text,
        that text is returned under ``description``. This is an experimental
        integration point that will evolve as the Cosmos NIM contract stabilizes.
        """
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "num_frames": 24,
            "fps": 8,
        }
        if image_bytes:
            body["image"] = base64.b64encode(image_bytes).decode("ascii")
        data = self._post("/video/generations", body)
        # Normalize either a direct video URL/text response.
        return {
            "description": data.get("description") or data.get("prompt") or prompt,
            "video_url": data.get("video_url") or data.get("url"),
            "raw": data,
        }


def build_nvidia_caller(
    model: str | None = None,
    api_key: str | None = None,
) -> callable:
    """Return a HERMES-compatible LLM caller backed by a NVIDIA NIM chat model."""
    client = NvidiaClient(api_key=api_key)
    model = model or os.environ.get("ROBOCAD_MODEL", CHAT_MODEL_NEMOTRON_LIGHTNING)
    # Allow "nvidia/" prefix aliases to be passed through unchanged.
    if model.startswith("nvidia/") or model.startswith("meta/"):
        pass
    elif model in {"nemotron-lightning", "nemotron-super", "nemotron-ultra"}:
        model = {
            "nemotron-lightning": CHAT_MODEL_NEMOTRON_LIGHTNING,
            "nemotron-super": CHAT_MODEL_NEMOTRON_SUPER,
            "nemotron-ultra": CHAT_MODEL_NEMOTRON_ULTRA,
        }[model]

    def caller(messages: list[dict[str, str]]) -> str:
        if not client.available():
            return '{"tool_calls": [], "plan": null, "error": "NVIDIA_API_KEY is not configured"}'
        try:
            return client.chat(messages, model=model)
        except NvidiaError as exc:
            return '{"tool_calls": [], "plan": null, "error": "' + str(exc).replace('"', "'") + '"}'

    return caller
