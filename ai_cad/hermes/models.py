"""Pydantic models for HERMES sessions, messages, plans, and tool calls."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class Message(BaseModel):
    role: Role
    content: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(default_factory=lambda: "tc_" + _token())


class ToolResult(BaseModel):
    call_id: str
    tool: str
    status: str  # "success" | "error" | "pending_approval"
    result: Any = None
    message: str = ""


class StepStatus(str, Enum):
    pending = "pending"
    awaiting_approval = "awaiting_approval"
    running = "running"
    completed = "completed"
    failed = "failed"
    rejected = "rejected"
    skipped = "skipped"


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: "step_" + _token())
    description: str
    tool: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.pending
    requires_approval: bool = False
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: "plan_" + _token())
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    status: StepStatus = StepStatus.pending
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def step_by_id(self, step_id: str) -> PlanStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


class Session(BaseModel):
    id: str = Field(default_factory=lambda: "hermes_" + _token())
    design_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    plans: list[Plan] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "idle"  # idle | running | awaiting_approval | error | done
    pending_tool_calls: list[ToolCall] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def active_plan(self) -> Plan | None:
        for plan in reversed(self.plans):
            if plan.status not in (StepStatus.completed.value, StepStatus.failed.value, StepStatus.rejected.value):
                return plan
        return None


class AgentResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    plan: Plan | None = None


class ApprovalRequest(BaseModel):
    session_id: str
    step_id: str
    approved: bool
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)


class ExplainRequest(BaseModel):
    session_id: str
    target: str  # e.g. "dfm", "verification", "brain", "world_replay"
    report: dict[str, Any] | None = None


def _token(length: int = 8) -> str:
    import secrets
    return secrets.token_hex(length // 2)
