"""Generate build123d code from a natural-language prompt using an LLM."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import anthropic
import httpx


DEFAULT_MODEL = os.environ.get("ROBOCAD_MODEL", "claude-3-5-sonnet-20241022")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))


PROMPTS_DIR = Path(__file__).parent / "prompts"


def _anthropic_create(client, *, model, max_tokens, messages, system, temperature):
    """Compatibility wrapper for Anthropic SDK temperature handling.

    Anthropic SDK >=1.0 removed the top-level ``temperature`` parameter from
    ``Messages.create``; it must be passed via ``extra_body``. Newer Claude 5
    models deprecate ``temperature`` entirely, so we drop it for those models.
    """
    major = int(getattr(anthropic, "__version__", "0.0.0").split(".")[0])
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "system": system,
    }
    # Claude 5 family deprecated temperature; omit it to avoid 400 errors.
    if model.startswith("claude-fable-5") or model.startswith("claude-sonnet-5") or model.startswith("claude-opus-5"):
        return client.messages.create(**kwargs)
    if major >= 1:
        kwargs["extra_body"] = {"temperature": temperature}
    else:
        kwargs["temperature"] = temperature
    return client.messages.create(**kwargs)


def _load_system_prompt() -> str:
    path = PROMPTS_DIR / "system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are a CAD programmer. Write build123d Python code for the requested part. Output only a code block."


def _load_feature_tree_system_prompt() -> str:
    path = PROMPTS_DIR / "feature_tree_system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are a CAD assistant. Output only a Feature-Tree JSON document."


def _load_examples() -> list[dict]:
    path = PROMPTS_DIR / "examples.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _looks_like_local_model(model: str) -> bool:
    """Return True for Ollama-style model names (e.g. qwen3-coder:latest)."""
    return ":" in model and not model.startswith("claude-") and not model.startswith("gpt-")


def _anthropic_base_url() -> str:
    """Return the Anthropic API base URL to use.

    Stale process environments sometimes set ANTHROPIC_BASE_URL to the local Ollama
    endpoint. We must not send Anthropic API calls there, and passing ``None`` is
    not enough because the Anthropic SDK still resolves the env var internally, so
    we explicitly return the official endpoint when the env value looks local.
    """
    base = os.environ.get("ANTHROPIC_BASE_URL")
    if base and ("localhost" in base or "127.0.0.1" in base or ":11434" in base):
        return "https://api.anthropic.com"
    return base or "https://api.anthropic.com"


def _first_text_block(response) -> str:
    """Extract the first text block from an Anthropic message response.

    Claude 5 models may emit thinking blocks before text; skip them.
    """
    for block in response.content:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            return block.text
    if response.content and hasattr(response.content[0], "text"):
        return response.content[0].text
    return ""


def _response_has_text(response) -> bool:
    """Return True if the Anthropic response contains at least one text block."""
    return any(
        getattr(block, "type", None) == "text" and hasattr(block, "text")
        for block in response.content
    )


def _build_messages(prompt: str, examples: list[dict]) -> list[dict]:
    """Build the chat message list used by both Anthropic and OpenAI paths."""
    messages: list[dict] = []
    for ex in examples:
        messages.append({"role": "user", "content": f"Prompt: {ex['prompt']}\n\nWrite the build123d code."})
        messages.append({"role": "assistant", "content": f"```python\n{ex['code']}\n```"})
    messages.append({"role": "user", "content": f"Prompt: {prompt}\n\nWrite the build123d code."})
    return messages


def _extract_code_block(text: str) -> Optional[str]:
    """Extract the first fenced python code block from an LLM response.

    Some models (especially during self-correction) return nested or malformed
    fences such as ```python\n```python\n...```. This function strips fence
    markers and returns the executable code inside.
    """
    if not text or not text.strip():
        return None

    # Find the first ```python or ``` fence and the matching close.
    start_match = re.search(r"```(?:python)?(?:\s*\n)", text, re.DOTALL)
    if start_match:
        start = start_match.end()
        rest = text[start:]
        # Find the next closing fence line after the open fence.
        end_match = re.search(r"\n```\s*(?:\n|$)", rest, re.DOTALL)
        if end_match:
            code = rest[: end_match.start()].strip()
            # Remove any accidental nested fence lines. These can appear as
            # leading ```python or standalone ``` markers inside the model's
            # own explanation before the real code block.
            code = re.sub(r"^```(?:python)?\s*$", "", code, flags=re.MULTILINE)
            code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
            code = code.strip()
            if _looks_like_code(code):
                return code

    # Fallback: strip fence markers from the whole response and see if code remains.
    cleaned = re.sub(r"^```(?:python)?\s*$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```(?:python)?\s*\n", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    if _looks_like_code(cleaned):
        return cleaned
    return None


def _looks_like_code(text: str) -> bool:
    """Return True if the cleaned text looks like executable Python CAD code."""
    if not text:
        return False
    markers = ["import ", "from ", "def ", "with BuildPart", "result ="]
    return any(marker in text for marker in markers)


def _wrap_result(raw_response: str, model: str) -> dict:
    """Package an extracted code block (or extraction failure) into the standard dict."""
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


def _generate_with_openai_compatible(
    messages: list[dict],
    *,
    model: str,
    system: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    base_url: str,
) -> dict:
    """Call an OpenAI-compatible chat endpoint (Ollama, etc.) for local models."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": f"Local model API error: {exc}",
        }

    try:
        data = response.json()
        raw = data["choices"][0]["message"]["content"]
    except Exception as exc:
        return {
            "success": False,
            "code": None,
            "raw_response": response.text,
            "model": model,
            "error": f"Failed to parse local model response: {exc}",
        }

    return _wrap_result(raw, model)


def _extract_json_block(text: str) -> Optional[str]:
    """Extract the first JSON object from an LLM response.

    Handles both raw JSON and JSON embedded inside markdown fences.
    """
    # Try ```json ... ``` or ``` ... ``` fences.
    match = re.search(r"```(?:json)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    # Fallback: find the first `{...}` block that parses as JSON.
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return None


def _wrap_feature_tree_result(raw_response: str, model: str) -> dict:
    json_text = _extract_json_block(raw_response)
    if json_text is None:
        return {
            "success": False,
            "feature_tree": None,
            "raw_response": raw_response,
            "model": model,
            "error": "Could not extract a valid JSON object from the response.",
        }
    return {
        "success": True,
        "feature_tree": json_text,
        "raw_response": raw_response,
        "model": model,
        "error": None,
    }


def generate_feature_tree(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    api_key: Optional[str] = None,
) -> dict:
    """Generate a Feature-Tree JSON document from a prompt.

    Returns a dict with keys:
        - success: bool
        - feature_tree: str (raw JSON text) or None
        - raw_response: str
        - model: str
        - error: str or None
    """
    system_prompt = _load_feature_tree_system_prompt()
    messages = [
        {"role": "user", "content": f"Prompt: {prompt}\n\nOutput the Feature-Tree JSON."},
    ]

    if _looks_like_local_model(model):
        result = _generate_with_openai_compatible(
            messages,
            model=model,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            base_url=OLLAMA_BASE_URL,
        )
        # The OpenAI-compatible helper returns a code-style result dict. If the
        # call itself failed (timeout, API error), surface that error directly.
        if not result.get("success") and not result.get("raw_response"):
            return {
                "success": False,
                "feature_tree": None,
                "raw_response": result.get("raw_response", ""),
                "model": model,
                "error": result.get("error", "Local model request failed."),
            }
        # Otherwise repackage the raw response as a feature-tree JSON result.
        return _wrap_feature_tree_result(result.get("raw_response", ""), model)

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "feature_tree": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHROPIC_API_KEY not set.",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
    )
    last_exc: Optional[Exception] = None
    for attempt in range(5):
        try:
            response = _anthropic_create(
                client,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            last_exc = exc
            continue

        raw_response = _first_text_block(response)
        if raw_response:
            return _wrap_feature_tree_result(raw_response, model)

    if last_exc is not None:
        return {
            "success": False,
            "feature_tree": None,
            "raw_response": "",
            "model": model,
            "error": f"API error: {last_exc}",
        }
    return {
        "success": False,
        "feature_tree": None,
        "raw_response": "",
        "model": model,
        "error": "Model returned no text block after retries.",
    }


def generate_model(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 4096,
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
    system_prompt = _load_system_prompt()
    examples = _load_examples()
    messages = _build_messages(prompt, examples)

    if _looks_like_local_model(model):
        return _generate_with_openai_compatible(
            messages,
            model=model,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            base_url=OLLAMA_BASE_URL,
        )

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHROPIC_API_KEY not set.",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
    )
    last_exc: Optional[Exception] = None
    for attempt in range(5):
        try:
            response = _anthropic_create(
                client,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            last_exc = exc
            continue

        raw_response = _first_text_block(response)
        if raw_response:
            return _wrap_result(raw_response, model)

    if last_exc is not None:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": f"API error: {last_exc}",
        }
    return {
        "success": False,
        "code": None,
        "raw_response": "",
        "model": model,
        "error": "Model returned no text block after retries.",
    }


def self_correct_feature_tree(
    prompt: str,
    json_text: str,
    error: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    api_key: Optional[str] = None,
) -> dict:
    """Ask the LLM to fix a feature tree JSON that failed transpilation or validation."""
    system_prompt = _load_feature_tree_system_prompt()
    messages = [
        {"role": "user", "content": f"Prompt: {prompt}\n\nOutput the Feature-Tree JSON."},
        {"role": "assistant", "content": f"```json\n{json_text}\n```"},
        {
            "role": "user",
            "content": (
                "The feature tree above failed with this error:\n"
                f"```\n{error}\n```\n"
                "Please correct the JSON and return the fixed Feature-Tree JSON object only."
            ),
        },
    ]

    if _looks_like_local_model(model):
        last_raw = ""
        for attempt in range(max_retries):
            result = _generate_with_openai_compatible(
                messages,
                model=model,
                system=system_prompt,
                max_tokens=4096,
                temperature=0.0,
                base_url=OLLAMA_BASE_URL,
            )
            if not result["success"]:
                return {
                    "success": False,
                    "feature_tree": None,
                    "raw_response": result.get("raw_response", ""),
                    "model": model,
                    "error": f"API error during self-correction attempt {attempt + 1}: {result['error']}",
                }
            last_raw = result["raw_response"]
            fixed_json = _extract_json_block(last_raw)
            if fixed_json:
                return {
                    "success": True,
                    "feature_tree": fixed_json,
                    "raw_response": last_raw,
                    "model": model,
                    "error": None,
                }
        return {
            "success": False,
            "feature_tree": None,
            "raw_response": last_raw,
            "model": model,
            "error": f"Failed to extract corrected JSON after {max_retries} attempts.",
        }

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "feature_tree": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHROPIC_API_KEY not set.",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
    )
    last_raw = ""
    for attempt in range(max_retries):
        try:
            response = _anthropic_create(
                client,
                model=model,
                max_tokens=4096,
                temperature=0.0,
                system=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            return {
                "success": False,
                "feature_tree": None,
                "raw_response": last_raw,
                "model": model,
                "error": f"API error during self-correction attempt {attempt + 1}: {exc}",
            }

        last_raw = _first_text_block(response)
        fixed_json = _extract_json_block(last_raw)
        if fixed_json:
            return {
                "success": True,
                "feature_tree": fixed_json,
                "raw_response": last_raw,
                "model": model,
                "error": None,
            }

    return {
        "success": False,
        "feature_tree": None,
        "raw_response": last_raw,
        "model": model,
        "error": f"Failed to extract corrected JSON after {max_retries} attempts.",
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

    if _looks_like_local_model(model):
        last_raw = ""
        for attempt in range(max_retries):
            result = _generate_with_openai_compatible(
                messages,
                model=model,
                system=system_prompt,
                max_tokens=2048,
                temperature=0.0,
                base_url=OLLAMA_BASE_URL,
            )
            if not result["success"]:
                return {
                    "success": False,
                    "code": None,
                    "raw_response": result.get("raw_response", ""),
                    "model": model,
                    "error": f"API error during self-correction attempt {attempt + 1}: {result['error']}",
                }
            last_raw = result["raw_response"]
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

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": model,
            "error": "ANTHROPIC_API_KEY not set.",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=_anthropic_base_url(),
    )
    last_raw = ""
    for attempt in range(max_retries):
        try:
            response = _anthropic_create(
                client,
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

        last_raw = _first_text_block(response)
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
