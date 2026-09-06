"""AI render critique for RoboCAD 3D previews.

Uses a NVIDIA vision-language model to inspect a screenshot of the generated
model and report visual issues (clipping, orientation, lighting, proportions,
manufacturability red flags). The critique is returned as structured JSON so the
frontend can highlight problems or auto-correct the view.
"""
from __future__ import annotations

import json
import os
from typing import Any

from ai_cad.nvidia_client import (
    CHAT_MODEL_LLAMA_3_2_11B_VISION,
    CHAT_MODEL_MUSE_GLIMMER,
    NvidiaClient,
    NvidiaError,
)


DEFAULT_PROMPT = """You are an expert CAD visualization reviewer. Inspect this rendered 3D model screenshot and identify any visual or engineering issues that would make the design look unprofessional or hard to evaluate.

Look for:
- Clipped or off-screen geometry
- Bad default camera angle / orientation
- Z-fighting, holes, flipped normals, missing faces
- Poor proportions or obviously wrong scale
- Features too small to see or overly dominant
- Lighting that hides detail

Return ONLY a JSON object with this exact shape:
{
  "score": 0-100,
  "issues": [
    {"severity": "low|medium|high", "category": "camera|geometry|lighting|scale|other", "message": "..."}
  ],
  "suggestions": ["..."],
  "safe_to_show_user": true|false
}
Do not include any commentary outside the JSON."""


class RenderCritiqueError(Exception):
    """Raised when render critique cannot be produced."""


def critique_render(
    image_bytes: bytes,
    *,
    model: str | None = None,
    prompt: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run a VLM on a render screenshot and return a structured critique.

    Args:
        image_bytes: PNG/JPEG screenshot bytes.
        model: NVIDIA vision model ID; defaults to llama-3.2-11b-vision-instruct.
        prompt: Override the default critique prompt.
        api_key: Optional NVIDIA API key; otherwise ``NVIDIA_API_KEY`` env is used.

    Returns:
        Parsed critique JSON with score, issues, suggestions, and safe_to_show_user.
    """
    client = NvidiaClient(api_key=api_key)
    if not client.available():
        return _fallback(image_bytes)

    model = model or os.environ.get("ROBOCAD_RENDER_CRITIQUE_MODEL", CHAT_MODEL_LLAMA_3_2_11B_VISION)
    prompt = prompt or DEFAULT_PROMPT

    try:
        text = client.vision(prompt, image_bytes, model=model)
        return _extract_json(text)
    except NvidiaError as exc:
        raise RenderCritiqueError(str(exc)) from exc
    except Exception as exc:
        raise RenderCritiqueError(f"Render critique failed: {exc}") from exc


def _fallback(_image_bytes: bytes) -> dict[str, Any]:
    """Return a neutral fallback when no NVIDIA key is configured."""
    return {
        "score": 75,
        "issues": [],
        "suggestions": ["NVIDIA_API_KEY is not configured; enable AI render critique in settings."],
        "safe_to_show_user": True,
    }


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object found in the model response."""
    text = text.strip()
    # Strip markdown fences if the model wraps JSON.
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return _default_critique(text)
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return _default_critique(text)


def _default_critique(raw_text: str) -> dict[str, Any]:
    return {
        "score": 70,
        "issues": [
            {
                "severity": "low",
                "category": "other",
                "message": "The critique model did not return valid JSON; falling back to a neutral review.",
            }
        ],
        "suggestions": ["Verify the render critique prompt and NVIDIA model response format."],
        "safe_to_show_user": True,
        "raw_response": raw_text[:2000],
    }
