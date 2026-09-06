"""Parameter validation for HERMES tool calls.

Each tool declares a Pydantic model. Executors validate parameters before
invoking backend callables, so malformed LLM calls fail fast with a clear error.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ValidationErrorMessage(Exception):
    """Raised when tool parameters fail validation."""

    def __init__(self, tool: str, detail: str) -> None:
        self.tool = tool
        self.detail = detail
        super().__init__(f"Tool {tool!r} parameter validation failed: {detail}")


class ClassifyDomainParams(BaseModel):
    prompt: str = Field(..., min_length=1)


class DecomposePromptParams(BaseModel):
    prompt: str = Field(..., min_length=1)


class ExplainLastFailureParams(BaseModel):
    target: str = Field(..., pattern=r"^(dfm|verification|brain|world_replay|generic)$")


class ProposeRedesignParams(BaseModel):
    goal: str = Field(..., min_length=1)
    failure_report: dict[str, Any] = Field(default_factory=dict)
    target: str = Field(default="generic")


class GenerateDesignParams(BaseModel):
    prompt: str = Field(..., min_length=1)
    max_retries: int = Field(default=2, ge=0, le=5)
    detect_domain: bool = Field(default=True)
    decompose: bool = Field(default=True)


class RegenerateParametersParams(BaseModel):
    parameter_updates: dict[str, float | int] = Field(..., min_length=1)


class RunVerificationParams(BaseModel):
    load_case: str = Field(default="static_stress")
    materials: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class BuildWorldParams(BaseModel):
    template: str = Field(default="pick_place")
    material: str = Field(default="PLA")
    tolerance: float = Field(default=0.1, gt=0.0, le=1.0)
    randomize: bool = Field(default=False)
    seed: int | None = Field(default=None)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReplayWorldParams(BaseModel):
    duration_seconds: float = Field(default=3.0, gt=0.0, le=30.0)
    fps: float = Field(default=10.0, gt=0.0, le=60.0)
    body_names: list[str] = Field(default_factory=list)


class TrainBrainParams(BaseModel):
    n_iters: int = Field(default=15, ge=1, le=100)
    pop_size: int = Field(default=40, ge=4, le=200)
    eval_episodes: int = Field(default=10, ge=1, le=50)
    success_rate_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    seed: int = Field(default=42)


class TrainSkillParams(BaseModel):
    skill_description: str = Field(default="push the block to the goal", min_length=1)
    n_iters: int = Field(default=20, ge=5, le=100)
    pop_size: int = Field(default=50, ge=10, le=200)
    eval_episodes: int = Field(default=10, ge=1, le=50)


TOOL_PARAMETER_SCHEMAS: dict[str, type[BaseModel]] = {
    "classify_domain": ClassifyDomainParams,
    "decompose_prompt": DecomposePromptParams,
    "explain_last_failure": ExplainLastFailureParams,
    "propose_redesign": ProposeRedesignParams,
    "generate_design": GenerateDesignParams,
    "regenerate_parameters": RegenerateParametersParams,
    "run_verification": RunVerificationParams,
    "build_world": BuildWorldParams,
    "replay_world": ReplayWorldParams,
    "train_brain": TrainBrainParams,
    "train_skill": TrainSkillParams,
}


def validate_tool_parameters(tool: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize parameters for a named tool.

    Returns the validated parameter dict. Raises ValidationErrorMessage on failure.
    """
    schema = TOOL_PARAMETER_SCHEMAS.get(tool)
    if schema is None:
        # Tools without declared schemas accept any parameters.
        return dict(parameters)
    try:
        return schema(**parameters).model_dump()
    except ValidationError as exc:
        errors = exc.errors()
        detail = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in errors
        )
        raise ValidationErrorMessage(tool, detail) from exc
