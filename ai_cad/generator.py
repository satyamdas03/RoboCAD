"""Generate build123d code from a natural-language prompt using an LLM."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import anthropic


DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    path = PROMPTS_DIR / "system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are a CAD programmer. Write build123d Python code for the requested part. Output only a code block."


def _load_examples() -> list[dict]:
    path = PROMPTS_DIR / "examples.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _extract_code_block(text: str) -> Optional[str]:
    """Extract the first fenced python code block from an LLM response."""
    # Try ```python ... ```
    match = re.search(r"```python\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try any ``` block
    match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: if the response looks like code, return it raw
    if "import" in text or "def " in text or "with BuildPart" in text:
        return text.strip()
    return None


def generate_model(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    api_key: Optional[str] = None,
) -> dict:
    """Generate build123d code from a prompt.

    Returns a dict with keys:
        - success: bool
        - code: str or None
        - raw_response: str
        - model: str
        - error: str or None
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHROPIC_API_KEY not set.",
        }

    system_prompt = _load_system_prompt()
    examples = _load_examples()

    messages: list[dict] = []
    for ex in examples:
        messages.append({"role": "user", "content": f"Prompt: {ex['prompt']}\n\nWrite the build123d code."})
        messages.append({"role": "assistant", "content": f"```python\n{ex['code']}\n```"})

    messages.append({"role": "user", "content": f"Prompt: {prompt}\n\nWrite the build123d code."})

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )
    except Exception as exc:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": f"API error: {exc}",
        }

    raw_response = response.content[0].text
    code = _extract_code_block(raw_response)

    if code is None:
        return {
            "success": False,
            "code": None,
            "raw_response": raw_response,
            "model": model,
            "error": "Could not extract a code block from the response.",
        }

    return {
        "success": True,
        "code": code,
        "raw_response": raw_response,
        "model": model,
        "error": None,
    }


def self_correct(
    prompt: str,
    code: str,
    error: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    api_key: Optional[str] = None,
) -> dict:
    """Ask the LLM to fix code that failed to execute."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHAPIC_API_KEY not set.",
        }

    system_prompt = _load_system_prompt()
    messages = [
        {"role": "user", "content": f"Prompt: {prompt}\n\nWrite the build123d code."},
        {"role": "assistant", "content": f"```python\n{code}\n```"},
        {
            "role": "user",
            "content": (
                "The code above failed with this error:\n"
                f"```\n{error}\n```\n"
                "Please fix the code and return the corrected version in a single ```python block."
            ),
        },
    ]

    client = anthropic.Anthropic(api_key=api_key)
    last_raw = ""
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                temperature=0.0,
                system=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            return {
                "success": False,
                "code": None,
                "raw_response": last_raw,
                "model": model,
                "error": f"API error during self-correction attempt {attempt + 1}: {exc}",
            }

        last_raw = response.content[0].text
        fixed_code = _extract_code_block(last_raw)
        if fixed_code:
            return {
                "success": True,
                "code": fixed_code,
                "raw_response": last_raw,
                "model": model,
                "error": None,
            }

    return {
        "success": False,
        "code": None,
        "raw_response": last_raw,
        "model": model,
        "error": f"Failed to extract corrected code after {max_retries} attempts.",
    }
