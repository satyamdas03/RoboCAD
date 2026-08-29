"""System-level decomposition for RoboCAD Phase 18.

Turns a complex, multi-domain prompt such as *"450 mm quadcopter with four motor
arms and an aerodynamic shell"* into a deterministic list of domain-tagged
sub-parts mapped to registered part families.

The engine is intentionally rule-first so the standard Phase 18 test cases are
stable and fast. A lightweight LLM fallback extends coverage for unknown system
prompts.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ai_cad.domain import DOMAIN_KEYWORDS, classify_domain
from ai_cad.feature_tree import Parameter


DEFAULT_MODEL = os.environ.get("ROBOCAD_MODEL", "claude-3-5-sonnet-20241022")


# Nouns that strongly indicate the prompt describes a system, not a single part.
SYSTEM_NOUNS = {
    "quadcopter",
    "drone",
    "uav",
    "robot arm",
    "manipulator",
    "humanoid",
    "biped",
    "quadruped",
    "chassis",
    "frame",
    "vehicle",
    "rover",
    "aircraft",
    "glider",
    "plane",
    "wing",
    "multirotor",
    "hexacopter",
    "octocopter",
}


# Map domain keywords to a preferred default family when no explicit family is given.
DOMAIN_DEFAULT_FAMILY = {
    "mechanical": "bracket",
    "aero": "airfoil",
    "thermal": "heat_sink",
    "electronics": "pcb",
    "humanoid": "limb_segment",
}


# Keyword hints that select a specific family within a domain.
FAMILY_KEYWORDS = {
    "mechanical": {
        "bracket": ["bracket", "mounting plate", "corner bracket"],
        "link": ["arm", "link", "tube", "bar", "strut", "tie"],
        "hub": ["hub", "pulley", "wheel center", "axle hub"],
        "mount": ["mount", "plate", "motor mount", "base plate", "flange"],
    },
    "aero": {
        "airfoil": ["airfoil", "foil", "section"],
        "wing": ["wing", "main wing", "panel"],
        "duct": ["duct", "shroud", "intake", "nozzle"],
    },
    "thermal": {
        "heat_sink": ["heat sink", "heatsink", "fin", "cooler"],
    },
    "electronics": {
        "pcb": ["pcb", "board", "raspberry pi", "arduino", "flight controller", "esc", "motor driver"],
        "enclosure": ["enclosure", "box", "case", "housing"],
        "connector": ["connector", "header", "d-sub", "terminal block", "jst", "pin header", "usb"],
        "cable_channel": ["cable", "wire", "channel", "clip", "harness", "conduit"],
        "fan_mount": ["fan", "vent", "cooler", "blower"],
        "heat_spreader": ["heat spreader", "thermal pad", "vapor chamber", "spreader"],
        "pcb_bracket": ["pcb bracket", "board mount", "standoff"],
    },
    "humanoid": {
        "limb_segment": ["arm", "leg", "limb", "link"],
        "end_effector": ["gripper", "hand", "end effector", "jaw"],
        "foot": ["foot", "feet"],
    },
}


@dataclass
class DecomposedPart:
    """One sub-part produced by decomposition."""

    id: str
    name: str
    domain: str
    family: str
    sub_prompt: str
    count: int = 1
    parameters: list[Parameter] = field(default_factory=list)


@dataclass
class DecompositionResult:
    """Full decomposition plan for a system prompt."""

    prompt: str
    primary_domain: str
    multi_domain: bool
    parts: list[DecomposedPart]
    notes: list[str] = field(default_factory=list)


def _looks_like_local_model(model: str) -> bool:
    return ":" in model and not model.startswith("claude-") and not model.startswith("gpt-")


def _extract_json_block(text: str) -> str | None:
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
    import httpx

    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))
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
    import anthropic

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


def _llm_decompose(prompt: str, model: str) -> dict[str, Any]:
    """Ask the LLM to decompose a system prompt into sub-parts."""
    system = """You are a robotics CAD assistant. Decompose the user's system prompt into a list of mechanical/aero/thermal/electronics/humanoid sub-parts.

Return JSON with this exact shape:
{
  "parts": [
    {"name": "...", "domain": "mechanical", "family": "bracket", "sub_prompt": "...", "count": 1}
  ],
  "notes": ["..."]
}

Available domains: mechanical, aero, thermal, electronics, humanoid.
Available families by domain:
- mechanical: bracket, link, hub, mount
- aero: airfoil, wing, duct
- thermal: heat_sink
- electronics: pcb, pcb_bracket, enclosure, connector, cable_channel, fan_mount, heat_spreader
- humanoid: limb_segment, end_effector, foot
"""
    messages = [{"role": "user", "content": f"Prompt: {prompt}\n\nReturn only JSON."}]
    try:
        if _looks_like_local_model(model):
            raw = _call_local_model(messages, system=system, model=model)
        else:
            raw = _call_anthropic(messages, system=system, model=model)
        text = _extract_json_block(raw) or raw
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "parts" in parsed:
            return parsed
    except Exception:
        pass
    return {"parts": [], "notes": ["LLM decomposition failed"]}


def _normalize_prompt(prompt: str) -> str:
    return prompt.lower().strip()


def _contains_any(text: str, words: set[str]) -> bool:
    lowered = text.lower()
    for w in words:
        if w in lowered:
            return True
    return False


def _find_number_near(text: str, *keywords: str) -> float | None:
    """Crude heuristic: find a number near one of the given keywords."""
    for kw in keywords:
        pattern = re.compile(rf"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|in)?\s*{re.escape(kw)}", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
        # keyword before number
        pattern2 = re.compile(rf"{re.escape(kw)}.*?(\d+(?:\.\d+)?)\s*(?:mm|cm|m|in)?", re.IGNORECASE)
        match2 = pattern2.search(text)
        if match2:
            try:
                return float(match2.group(1))
            except ValueError:
                continue
    return None


def _select_family(domain: str, sub_prompt: str) -> str:
    """Pick the best part family for a sub-prompt within a domain."""
    text = sub_prompt.lower()
    candidates = FAMILY_KEYWORDS.get(domain, {})
    best = DOMAIN_DEFAULT_FAMILY.get(domain, "bracket")
    best_score = 0
    for family, keywords in candidates.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best = family
    return best


def _count_from_prompt(prompt: str, part_name: str) -> int:
    """Extract repetition count, e.g., 'four motor arms' → 4."""
    text = prompt.lower()
    singular = part_name.rstrip("s")
    plural = singular + "s"
    digits = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    # Find a digit word before singular or plural form (allow one intervening word).
    for word, n in digits.items():
        for form in (plural, singular):
            pattern = re.compile(rf"\b{word}\b\s+\w+?\s+{re.escape(form)}\b", re.IGNORECASE)
            if pattern.search(text):
                return n
            if f"{word} {form}" in text:
                return n
    # Find a numeral before singular or plural form (allow one intervening word).
    for form in (plural, singular):
        pattern = re.compile(rf"(\d+)\s+\w+?\s+{re.escape(form)}\b", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        match = re.search(rf"(\d+)\s*{re.escape(form)}", text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
    return 1


def _rotor_count_from_prompt(prompt: str) -> int:
    """Default rotor count from multirotor type or explicit number."""
    text = prompt.lower()
    if "octocopter" in text or "octo" in text:
        return 8
    if "hexacopter" in text or "hexa" in text:
        return 6
    # Explicit count overrides defaults.
    count = _count_from_prompt(prompt, "arm")
    if count > 1:
        return count
    if "quadcopter" in text or "quad" in text or "drone" in text:
        return 4
    return 4


def _rule_decompose(prompt: str) -> DecompositionResult | None:
    """Try deterministic decomposition for known system classes."""
    text = _normalize_prompt(prompt)
    prediction = classify_domain(prompt, use_embeddings=False)

    # Quadcopter / drone / multirotor
    if any(w in text for w in {"quadcopter", "drone", "multirotor", "hexacopter", "octocopter", "uav"}):
        size = _find_number_near(text, "mm", "frame") or 450.0
        arm_count = _rotor_count_from_prompt(prompt)
        shell = any(w in text for w in {"shell", "body", "cover", "aero", "fairing"})
        parts = []
        # Central frame hub
        parts.append(
            DecomposedPart(
                id="frame_hub",
                name="Central frame hub",
                domain="mechanical",
                family="hub",
                sub_prompt=f"Central quadcopter hub, {size} mm frame",
                parameters=[Parameter(name="hub_diameter", value=size / 4.5, unit="mm")],
            )
        )
        # Motor arms
        parts.append(
            DecomposedPart(
                id="motor_arm",
                name="Motor arm",
                domain="mechanical",
                family="link",
                sub_prompt=f"Quadcopter motor arm, {size} mm frame",
                count=arm_count,
                parameters=[Parameter(name="link_length", value=size / 2.2, unit="mm")],
            )
        )
        # Motor mounts
        parts.append(
            DecomposedPart(
                id="motor_mount",
                name="Motor mount",
                domain="mechanical",
                family="mount",
                sub_prompt="Quadcopter motor mount plate",
                count=arm_count,
            )
        )
        if shell:
            parts.append(
                DecomposedPart(
                    id="aero_shell",
                    name="Aerodynamic shell",
                    domain="aero",
                    family="duct",
                    sub_prompt="Quadcopter aerodynamic shell / shroud",
                )
            )
        return DecompositionResult(
            prompt=prompt,
            primary_domain="mechanical",
            multi_domain=True,
            parts=parts,
            notes=[f"Rule-based quadcopter decomposition, {arm_count} motor arms, {size} mm frame."],
        )

    # Robot arm / manipulator
    if any(w in text for w in {"robot arm", "manipulator", "robotic arm"}):
        parts = []
        parts.append(
            DecomposedPart(
                id="arm_base",
                name="Arm base",
                domain="mechanical",
                family="mount",
                sub_prompt="Robot arm base mounting plate",
            )
        )
        parts.append(
            DecomposedPart(
                id="upper_link",
                name="Upper arm link",
                domain="mechanical",
                family="link",
                sub_prompt="Robot arm upper link",
            )
        )
        parts.append(
            DecomposedPart(
                id="forearm_link",
                name="Forearm link",
                domain="mechanical",
                family="link",
                sub_prompt="Robot arm forearm link",
            )
        )
        if any(w in text for w in {"gripper", "end effector", "hand"}):
            parts.append(
                DecomposedPart(
                    id="gripper",
                    name="Gripper",
                    domain="humanoid",
                    family="end_effector",
                    sub_prompt="Parallel-jaw gripper for robot arm",
                    count=2,
                )
            )
        return DecompositionResult(
            prompt=prompt,
            primary_domain="mechanical",
            multi_domain=True,
            parts=parts,
            notes=["Rule-based robot arm decomposition."],
        )

    # Humanoid / biped / quadruped
    if any(w in text for w in {"humanoid", "biped", "quadruped", "leg", "torso"}):
        parts = []
        parts.append(
            DecomposedPart(
                id="torso_plate",
                name="Torso plate",
                domain="mechanical",
                family="bracket",
                sub_prompt="Humanoid torso mounting bracket",
            )
        )
        leg_count = 2 if "biped" in text or "humanoid" in text else 4
        parts.append(
            DecomposedPart(
                id="thigh",
                name="Thigh segment",
                domain="humanoid",
                family="limb_segment",
                sub_prompt="Humanoid thigh limb segment",
                count=leg_count,
            )
        )
        parts.append(
            DecomposedPart(
                id="shin",
                name="Shin segment",
                domain="humanoid",
                family="limb_segment",
                sub_prompt="Humanoid shin limb segment",
                count=leg_count,
            )
        )
        return DecompositionResult(
            prompt=prompt,
            primary_domain="humanoid",
            multi_domain=True,
            parts=parts,
            notes=[f"Rule-based humanoid decomposition, {leg_count} legs."],
        )

    # Fixed-wing aircraft / glider
    if any(w in text for w in {"aircraft", "glider", "plane", "fixed wing"}):
        parts = []
        parts.append(
            DecomposedPart(
                id="fuselage",
                name="Fuselage bracket",
                domain="mechanical",
                family="bracket",
                sub_prompt="Aircraft fuselage central bracket",
            )
        )
        parts.append(
            DecomposedPart(
                id="main_wing",
                name="Main wing",
                domain="aero",
                family="wing",
                sub_prompt="Aircraft main wing",
                count=2,
            )
        )
        return DecompositionResult(
            prompt=prompt,
            primary_domain="aero",
            multi_domain=True,
            parts=parts,
            notes=["Rule-based fixed-wing decomposition."],
        )

    # Electronics stack / PCB + enclosure + accessories
    electronics_system_keywords = {
        "raspberry pi",
        "arduino",
        "pcb with enclosure",
        "electronics enclosure",
        "motor driver stack",
        "flight controller",
        "esc",
        "board with case",
    }
    if any(w in text for w in electronics_system_keywords):
        parts = [
            DecomposedPart(
                id="pcb",
                name="PCB",
                domain="electronics",
                family="pcb",
                sub_prompt="Main PCB",
            )
        ]
        if any(w in text for w in {"enclosure", "box", "case", "housing"}):
            parts.append(
                DecomposedPart(
                    id="enclosure",
                    name="Enclosure",
                    domain="electronics",
                    family="enclosure",
                    sub_prompt="Electronics enclosure",
                )
            )
        if any(w in text for w in {"fan", "vent", "cooler"}):
            parts.append(
                DecomposedPart(
                    id="fan_mount",
                    name="Fan mount",
                    domain="electronics",
                    family="fan_mount",
                    sub_prompt="Fan vent mount",
                )
            )
        if any(w in text for w in {"connector", "header", "usb", "pin header"}):
            parts.append(
                DecomposedPart(
                    id="connector",
                    name="Connector",
                    domain="electronics",
                    family="connector",
                    sub_prompt="Board connector",
                    count=2,
                )
            )
        if any(w in text for w in {"cable", "wire", "channel", "clip", "harness"}):
            parts.append(
                DecomposedPart(
                    id="cable_channel",
                    name="Cable channel",
                    domain="electronics",
                    family="cable_channel",
                    sub_prompt="Cable routing channel",
                )
            )
        if any(w in text for w in {"heat spreader", "thermal pad", "spreader"}):
            parts.append(
                DecomposedPart(
                    id="heat_spreader",
                    name="Heat spreader",
                    domain="electronics",
                    family="heat_spreader",
                    sub_prompt="Thermal heat spreader",
                )
            )
        return DecompositionResult(
            prompt=prompt,
            primary_domain="electronics",
            multi_domain=True,
            parts=parts,
            notes=["Rule-based electronics stack decomposition."],
        )

    return None


def _llm_decompose_result(prompt: str, model: str | None = None) -> DecompositionResult:
    """Decompose via LLM and normalize the output."""
    model = model or os.environ.get("ROBOCAD_MODEL", DEFAULT_MODEL)
    raw = _llm_decompose(prompt, model)
    parts: list[DecomposedPart] = []
    idx = 0
    for item in raw.get("parts", []):
        idx += 1
        domain = item.get("domain", "mechanical")
        family = item.get("family", DOMAIN_DEFAULT_FAMILY.get(domain, "bracket"))
        parts.append(
            DecomposedPart(
                id=f"part_{idx}",
                name=item.get("name", f"Part {idx}"),
                domain=domain,
                family=family,
                sub_prompt=item.get("sub_prompt", item.get("name", "")),
                count=item.get("count", 1),
            )
        )
    prediction = classify_domain(prompt)
    return DecompositionResult(
        prompt=prompt,
        primary_domain=prediction.primary,
        multi_domain=prediction.multi_domain,
        parts=parts,
        notes=raw.get("notes", []),
    )


def should_decompose(prompt: str) -> bool:
    """Return True if the prompt looks like a system-level, multi-part intent."""
    text = _normalize_prompt(prompt)
    prediction = classify_domain(prompt, use_embeddings=False)
    if prediction.multi_domain:
        return True
    if _contains_any(text, SYSTEM_NOUNS):
        return True
    return False


def decompose(
    prompt: str,
    *,
    use_llm: bool = True,
    model: str | None = None,
) -> DecompositionResult:
    """Decompose a system prompt into domain-tagged sub-parts.

    The engine first tries deterministic rule-based templates for known systems
    (quadcopter, robot arm, humanoid, fixed-wing). If no rule matches and
    ``use_llm`` is True, it falls back to a short LLM call. If that fails too,
    it returns a single-part decomposition in the primary domain.
    """
    rule_result = _rule_decompose(prompt)
    if rule_result is not None:
        return rule_result

    if use_llm:
        llm_result = _llm_decompose_result(prompt, model=model)
        if llm_result.parts:
            return llm_result

    prediction = classify_domain(prompt, use_embeddings=False)
    family = _select_family(prediction.primary, prompt)
    return DecompositionResult(
        prompt=prompt,
        primary_domain=prediction.primary,
        multi_domain=prediction.multi_domain,
        parts=[
            DecomposedPart(
                id="single_part",
                name="Single part",
                domain=prediction.primary,
                family=family,
                sub_prompt=prompt,
            )
        ],
        notes=["No system template matched; treated as single-part intent."],
    )
