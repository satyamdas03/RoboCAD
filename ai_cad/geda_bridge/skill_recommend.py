"""Phase 15B — skill-to-scene recommendation for the GEDA Bridge.

Maps a natural-language skill or task description ("push the block to the green
goal", "grasp a cube", "hang the bracket on a hook") to a standard scene template
and a default training configuration. This is the first link in the
video/skill → generated part → trained policy pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SkillRecommendation:
    """Recommended scene template + training config for a skill."""

    skill_description: str
    template: str
    confidence: float
    goal_pos: tuple[float, float, float]
    block_start: tuple[float, float, float] | None = None
    policy_config: dict[str, Any] | None = None
    reasoning: str = ""


_SCENE_KEYWORDS: dict[str, dict[str, Any]] = {
    "wedge_push_block": {
        "keywords": {"push", "slide", "move", "shove", "nudge", "block", "wedge"},
        "goal_pos": (0.55, 0.0, 0.49),
        "block_start": (0.25, 0.0, 0.49),
        "policy_config": {"n_iters": 20, "pop_size": 50, "success_radius_m": 0.06},
    },
    "gripper_cube_grasp": {
        "keywords": {"grasp", "grip", "pick", "lift", "cube", "hold", "take"},
        "goal_pos": (0.0, 0.0, 0.6),
        "policy_config": {"n_iters": 20, "pop_size": 50, "success_radius_m": 0.05},
    },
    "bracket_hook_hang": {
        "keywords": {"hang", "hook", "bracket", "mount", "suspend"},
        "goal_pos": (0.4, 0.0, 0.55),
        "policy_config": {"n_iters": 20, "pop_size": 50, "success_radius_m": 0.04},
    },
    "peg_insertion": {
        "keywords": {"insert", "peg", "plug", "hole", "assemble"},
        "goal_pos": (0.3, 0.0, 0.45),
        "policy_config": {"n_iters": 25, "pop_size": 60, "success_radius_m": 0.03},
    },
}


def recommend_skill(skill_description: str) -> SkillRecommendation:
    """Recommend a scene template and default training config for a skill.

    Confidence is computed as the Jaccard-like overlap between the skill words
    and each template's keyword set. The best matching template wins. Unknown
    skills fall back to wedge_push_block with low confidence.
    """
    desc_lower = skill_description.lower()
    words = set(_tokenize(desc_lower))

    best_template = "wedge_push_block"
    best_score = 0.0
    best_reasoning = "Fallback to generic push template (low confidence)."

    for template, meta in _SCENE_KEYWORDS.items():
        keywords = meta["keywords"]
        overlap = len(words & keywords)
        union = len(words | keywords)
        score = overlap / max(1, union) if union else 0.0
        # Boost exact phrase matches.
        if any(kw in desc_lower for kw in keywords):
            score += 0.1
        if score > best_score:
            best_score = score
            best_template = template
            matched = words & keywords
            best_reasoning = f"Matched keywords: {sorted(matched)}" if matched else f"Partial match on template '{template}'."

    meta = _SCENE_KEYWORDS[best_template]
    confidence = min(1.0, best_score)
    return SkillRecommendation(
        skill_description=skill_description,
        template=best_template,
        confidence=confidence,
        goal_pos=meta["goal_pos"],
        block_start=meta.get("block_start"),
        policy_config=meta["policy_config"],
        reasoning=best_reasoning,
    )


def _tokenize(text: str) -> list[str]:
    """Very light tokenization: lowercase alphanumeric words."""
    import re
    return re.findall(r"[a-z0-9]+", text)


def list_skills() -> dict[str, Any]:
    """Return the supported skill templates and their keywords for UI discovery."""
    return {
        template: {
            "keywords": sorted(meta["keywords"]),
            "goal_pos": meta["goal_pos"],
            "policy_config": meta["policy_config"],
        }
        for template, meta in _SCENE_KEYWORDS.items()
    }
