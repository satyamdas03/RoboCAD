"""Per-domain intent parser for RoboCAD Phase 16.

Maps a user prompt (and optional known domain) to a structured ``DomainIntent``
containing parameters, feature stubs, constraints, and notes. The parser uses a
short domain-specific system prompt and the configured LLM; if the LLM call
fails it falls back to a generic mechanical intent with zero confidence.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import anthropic
import httpx
from pydantic import BaseModel, Field

from ai_cad.domain import classify_domain
from ai_cad.feature_tree import Parameter


DEFAULT_MODEL = os.environ.get("ROBOCAD_MODEL", "claude-3-5-sonnet-20241022")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))


_PROMPT_TEMPLATES: dict[str, str] = {
    "mechanical": """Extract structured parameters and features for a mechanical part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: length, width, thickness, hole_diameter, hole_count, material.
""",
    "aero": """Extract structured parameters and features for an aerodynamic/thermal surface from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: chord, span, naca_code, sweep, twist, fin_count, fin_height.
""",
    "thermal": """Extract structured parameters and features for a thermal part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: fin_count, fin_height, base_length, base_width, thermal_load.
""",
    "electronics": """Extract structured parameters and features for an electronics/mechanical co-design part from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: board_length, board_width, mounting_hole_diameter, connector_count.
""",
    "humanoid": """Extract structured parameters and features for a humanoid/robot subsystem from the user prompt.
Return JSON with keys: parameters, features, constraints, notes, confidence.
Example parameters: height, mass, dof, link_length, payload.
""",
}


class DomainIntent(BaseModel):
    """Structured intent extracted from a user prompt for a specific domain."""

    domain: str
    parameters: list[Parameter] = Field(default_factory=list)
    features: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    confidence: float = 0.0


def _looks_like_local_model(model: str) -> bool:
    """Return True for Ollama-style model names (e.g. qwen3-coder:latest)."""
    return ":" in model and not model.startswith("claude-") and not model.startswith("gpt-")


def _extract_json_block(text: str) -> str | None:
    """Return the first JSON object found in ``text``."""
    match = re.search(r"```(?:json)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return None


def _call_local_model(messages: list[dict[str, str]], *, system: str, model: str) -> str:
    """Call an OpenAI-compatible local endpoint and return the raw text."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    response = httpx.post(
        f"{OLLAMA_BASE_URL}/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer ollama"},
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_anthropic(messages: list[dict[str, str]], *, system: str, model: str) -> str:
    """Call the Anthropic Messages API and return the first text block."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    if base_url and ("localhost" in base_url or "127.0.0.1" in base_url or ":11434" in base_url):
        base_url = "https://api.anthropic.com"
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    kwargs = {
        "model": model,
        "max_tokens": 2048,
        "messages": messages,
        "system": system,
    }
    if model.startswith("claude-fable-5") or model.startswith("claude-sonnet-5") or model.startswith("claude-opus-5"):
        response = client.messages.create(**kwargs)
    else:
        major = int(getattr(anthropic, "__version__", "0.0.0").split(".")[0])
        if major >= 1:
            kwargs["extra_body"] = {"temperature": 0.0}
        else:
            kwargs["temperature"] = 0.0
        response = client.messages.create(**kwargs)
    for block in response.content:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            return block.text
    if response.content and hasattr(response.content[0], "text"):
        return response.content[0].text
    return ""


def _llm_extract(prompt: str, domain: str) -> dict[str, Any]:
    """Ask the configured LLM to extract a domain intent as JSON."""
    model = os.environ.get("ROBOCAD_MODEL", DEFAULT_MODEL)
    system = _PROMPT_TEMPLATES.get(domain, _PROMPT_TEMPLATES["mechanical"])
    messages = [
        {"role": "user", "content": f"Prompt: {prompt}\n\nReturn only JSON."},
    ]
    try:
        if _looks_like_local_model(model):
            raw = _call_local_model(messages, system=system, model=model)
        else:
            raw = _call_anthropic(messages, system=system, model=model)
        text = _extract_json_block(raw) or raw
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {
        "parameters": [],
        "features": [],
        "constraints": [],
        "notes": ["LLM fallback failed"],
        "confidence": 0.0,
    }


def parse_domain_intent(prompt: str, domain: str | None = None) -> DomainIntent:
    """Parse a user prompt into a structured intent for the detected or supplied domain."""
    target = domain or classify_domain(prompt).primary
    raw = _llm_extract(prompt, target)
    confidence = raw.get("confidence", 0.0) or 0.0
    # If the LLM could not extract anything and no domain was forced, fall back to
    # the default mechanical domain so downstream code has a stable target.
    if domain is None and confidence == 0.0:
        target = "mechanical"
    params = []
    for p in raw.get("parameters", []):
        try:
            params.append(Parameter(**p))
        except Exception:
            continue
    return DomainIntent(
        domain=target,
        parameters=params,
        features=raw.get("features", []),
        constraints=raw.get("constraints", []),
        notes=raw.get("notes", []),
        confidence=confidence,
    )
