"""Generic NVIDIA NIM REST client for vision, chat, and physics-aware generation.

This module wraps the public NVIDIA NIM endpoints (https://integrate.api.nvidia.com/v1)
so RoboCAD can use NVIDIA models for:

* HERMES reasoning (nemotron LLMs)
* Render critique and design inspection (vision-language models)
* Physics-aware scenario generation (cosmos reasoning models)

All calls are synchronous HTTP helpers that return parsed text or bytes. Long-running
or streaming calls are delegated to the callers so the client stays simple and testable.
"""
from __future__ import annotations

import json
import os
import base64
import re
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Model IDs available through the hosted NVIDIA NIM endpoint used by RoboCAD.
# These are validated against https://integrate.api.nvidia.com/v1/models with a
# valid NVIDIA_API_KEY. Self-hosted NIMs on other base URLs may support more
# models, but the defaults below are guaranteed on the hosted catalog.
CHAT_MODEL_NEMOTRON_LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
CHAT_MODEL_NEMOTRON_SUPER = "nvidia/nemotron-3-super-120b-a12b"
CHAT_MODEL_NEMOTRON_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
CHAT_MODEL_LLAMA_3_2_90B_VISION = "meta/llama-3.2-90b-vision-instruct"
CHAT_MODEL_LLAMA_3_2_11B_VISION = "meta/llama-3.2-11b-vision-instruct"
CHAT_MODEL_MUSE_GLIMMER = "nvidia/muse-glimmer-30b"

# Cosmos video-generation NIMs are primarily self-hosted. The hosted catalog
# exposes a small reasoning model, so scenario generation is implemented as a
# structured reasoning call rather than a true video-generation call.
COSMOS_REASON_8B = "nvidia/cosmos-reason2-8b"
COSMOS_NANO = "nvidia/cosmos3-nano"  # self-hosted only
COSMOS_NANO_REASONER = "nvidia/cosmos3-nano-reasoner"  # self-hosted only

# Hosted audio NIMs are not currently exposed on integrate.api.nvidia.com.
# These defaults are kept for self-hosted / future hosted endpoints.
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
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate a physics-aware scenario description using a Cosmos/Nemotron model.

        Hosted NVIDIA NIM does not currently expose the Cosmos video-generation
        endpoint, so this implementation uses a structured chat-completion call
        to produce a JSON scenario description. The returned dict preserves the
        same shape as before for backward compatibility: ``description``,
        ``video_url`` (None when no video is produced), and ``raw``.
        """
        model = model or os.environ.get("ROBOCAD_SCENARIO_MODEL")
        # If a self-hosted video-generation model is configured, warn clearly.
        if model in {COSMOS_NANO, COSMOS_NANO_REASONER} and self.base_url == DEFAULT_BASE_URL:
            return {
                "description": prompt,
                "video_url": None,
                "note": (
                    f"{model} is a self-hosted NIM on the hosted catalog. "
                    "Set NVIDIA_BASE_URL to your NIM endpoint to generate video."
                ),
                "raw": {},
            }

        # Hosted video-generation NIMs are not available for this account, so we use a
        # structured chat call. The Super model follows JSON instructions far more
        # reliably than Lightning for these small structured outputs.
        structured_model = model or CHAT_MODEL_NEMOTRON_SUPER

        system_prompt = (
            "You are a robotics world-builder. Given a user prompt, produce a structured "
            "scenario description useful for MuJoCo/Isaac Sim simulation. "
            "Return ONLY a compact JSON object with no markdown fences and no explanation."
        )
        user_prompt = (
            f"Scenario prompt: {prompt}\n\n"
            "Return JSON with this exact schema:\n"
            '{"title": str, "description": str, "terrain": str, "objects": [str], '
            '"robot_tasks": [str], "physics_notes": [str], "difficulty": "easy|medium|hard"}'
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Reference image:"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            )

        try:
            response_text = self.chat(
                messages=messages,
                model=structured_model,
                temperature=0.3,
                max_tokens=512,
            )
        except NvidiaError:
            # Fall back to the default chat model if the requested model is unavailable.
            response_text = self.chat(
                messages=messages,
                model=CHAT_MODEL_NEMOTRON_LIGHTNING,
                temperature=0.3,
                max_tokens=512,
            )

        # Extract JSON object from response text.
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        parsed: dict[str, Any] = {}
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = {}
        if not parsed:
            parsed = {
                "title": "Generated scenario",
                "description": prompt,
                "terrain": "flat",
                "objects": [],
                "robot_tasks": [],
                "physics_notes": ["NVIDIA NIM did not return valid JSON"],
                "difficulty": "medium",
            }

        return {
            "description": parsed.get("description", prompt),
            "video_url": None,
            "note": "Text scenario generated by NVIDIA NIM; video generation requires self-hosted Cosmos NIM.",
            "raw": parsed,
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
