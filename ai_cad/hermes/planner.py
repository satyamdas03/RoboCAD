"""HERMES plan representation and execution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_cad.hermes.gate import ApprovalGate
from ai_cad.hermes.models import Plan, PlanStep, StepStatus, ToolCall, ToolResult
from ai_cad.hermes.tools import HermesToolRegistry


def build_plan(goal: str, steps_data: list[dict[str, Any]]) -> Plan:
    """Build a Plan from a list of step dicts."""
    steps = [PlanStep(**step) for step in steps_data]
    return Plan(goal=goal, steps=steps)


def plan_dependency_order(plan: Plan) -> list[PlanStep]:
    """Return steps in dependency-respecting order (pending steps only)."""
    pending = {step.id: step for step in plan.steps if step.status == StepStatus.pending}
    ordered: list[PlanStep] = []
    visited: set[str] = set()

    def visit(step: PlanStep) -> None:
        if step.id in visited:
            return
        visited.add(step.id)
        for dep_id in step.depends_on:
            dep = pending.get(dep_id)
            if dep:
                visit(dep)
        ordered.append(step)

    for step in pending.values():
        visit(step)
    return ordered


def next_runnable_step(plan: Plan, gate: ApprovalGate | None = None) -> PlanStep | None:
    """Return the next pending step whose dependencies are completed.

    If the next step requires approval and is not yet approved, mark it as
    awaiting_approval and return it so the caller can prompt the user.
    """
    gate = gate or ApprovalGate()
    pending = {step.id: step for step in plan.steps if step.status == StepStatus.pending}
    completed_ids = {step.id for step in plan.steps if step.status == StepStatus.completed}

    for step in plan_dependency_order(plan):
        if step.id not in pending:
            continue
        if any(dep_id not in completed_ids for dep_id in step.depends_on):
            continue
        if gate.requires_approval(step.tool or "") and not step.metadata.get("approved"):
            step.status = StepStatus.awaiting_approval
            step.updated_at = datetime.now(timezone.utc).isoformat()
        return step
    return None


def execute_plan_step(
    plan: Plan,
    step: PlanStep,
    registry: HermesToolRegistry,
    context: dict[str, Any] | None = None,
) -> ToolResult:
    """Execute a single plan step through the tool registry."""
    if step.tool is None:
        step.status = StepStatus.completed
        step.updated_at = datetime.now(timezone.utc).isoformat()
        return ToolResult(call_id="", tool="", status="success", result=None, message="No-op step")

    if step.requires_approval and not step.metadata.get("approved"):
        step.status = StepStatus.awaiting_approval
        step.updated_at = datetime.now(timezone.utc).isoformat()
        return ToolResult(
            call_id="",
            tool=step.tool,
            status="pending_approval",
            message=f"Step {step.id} requires approval before executing {step.tool}",
        )

    step.status = StepStatus.running
    step.updated_at = datetime.now(timezone.utc).isoformat()
    try:
        result = registry.execute(step.tool, step.parameters, context=context)
        step.result = result
        step.status = StepStatus.completed
    except Exception as exc:  # pragma: no cover - general catch
        step.error = str(exc)
        step.status = StepStatus.failed
        return ToolResult(call_id="", tool=step.tool, status="error", message=str(exc))
    finally:
        step.updated_at = datetime.now(timezone.utc).isoformat()

    return ToolResult(
        call_id="",
        tool=step.tool,
        status="success",
        result=result,
        message=f"Executed {step.tool}",
    )


def advance_plan(plan: Plan, registry: HermesToolRegistry, context: dict[str, Any] | None = None) -> list[ToolResult]:
    """Run all currently runnable steps until blocked by approval or completion."""
    results: list[ToolResult] = []
    gate = ApprovalGate()
    while True:
        step = next_runnable_step(plan, gate=gate)
        if step is None:
            break
        if step.status == StepStatus.awaiting_approval:
            results.append(
                ToolResult(
                    call_id="",
                    tool=step.tool or "",
                    status="pending_approval",
                    message=f"Step {step.id} is awaiting approval",
                )
            )
            break
        results.append(execute_plan_step(plan, step, registry, context))
    _update_plan_status(plan)
    return results


def _update_plan_status(plan: Plan) -> None:
    statuses = {step.status for step in plan.steps}
    if not plan.steps or statuses == {StepStatus.completed}:
        plan.status = StepStatus.completed
    elif StepStatus.failed in statuses:
        plan.status = StepStatus.failed
    elif StepStatus.rejected in statuses:
        plan.status = StepStatus.rejected
    elif StepStatus.awaiting_approval in statuses:
        plan.status = StepStatus.awaiting_approval
    elif StepStatus.running in statuses:
        plan.status = StepStatus.running
    else:
        plan.status = StepStatus.pending
    plan.updated_at = datetime.now(timezone.utc).isoformat()


def approve_step(plan: Plan, step_id: str, parameter_overrides: dict[str, Any] | None = None) -> PlanStep:
    """Mark a plan step as approved and merge any parameter overrides."""
    step = plan.step_by_id(step_id)
    if step is None:
        raise KeyError(f"Step {step_id!r} not found in plan")
    if step.status != StepStatus.awaiting_approval:
        raise ValueError(f"Step {step_id!r} is not awaiting approval (status={step.status})")
    if parameter_overrides:
        step.parameters.update(parameter_overrides)
    step.metadata["approved"] = True
    step.status = StepStatus.pending
    step.updated_at = datetime.now(timezone.utc).isoformat()
    return step


def reject_step(plan: Plan, step_id: str, reason: str = "") -> PlanStep:
    """Reject a plan step, marking dependent steps as skipped."""
    step = plan.step_by_id(step_id)
    if step is None:
        raise KeyError(f"Step {step_id!r} not found in plan")
    step.status = StepStatus.rejected
    step.error = reason or "Rejected by user"
    step.updated_at = datetime.now(timezone.utc).isoformat()

    dependent_ids = {s.id for s in plan.steps if step_id in s.depends_on}
    for other in plan.steps:
        if other.id in dependent_ids and other.status == StepStatus.pending:
            other.status = StepStatus.skipped
            other.error = f"Skipped because dependency {step_id} was rejected"
            other.updated_at = datetime.now(timezone.utc).isoformat()
    _update_plan_status(plan)
    return step


def tool_call_to_step(call: ToolCall) -> PlanStep:
    """Convert a single tool call into a plan step."""
    return PlanStep(
        description=f"Execute {call.tool}",
        tool=call.tool,
        parameters=call.parameters,
    )
