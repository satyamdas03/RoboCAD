"""HERMES tool executors.

Each executor is a thin wrapper around an existing RoboCAD backend operation.
The actual backend callable is injected at runtime via `_context` so the
`ai_cad.hermes` package stays decoupled from `web.backend.main`.
"""
from __future__ import annotations

from typing import Any

from ai_cad.hermes.explain import _heuristic_redesign, explain_report, propose_redesign
from ai_cad.hermes.validation import validate_tool_parameters


def _get_context(ctx: dict[str, Any] | None) -> dict[str, Any]:
    return ctx or {}


def _require(name: str, ctx: dict[str, Any]) -> Any:
    fn = ctx.get(name)
    if fn is None:
        return {
            "status": "error",
            "message": f"Backend callable {name!r} is not bound in HERMES context",
        }
    return fn


def exec_classify_domain(
    prompt: str,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Classify the domain of a user prompt."""
    fn = _require("classify_domain", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(prompt)


def exec_decompose_prompt(
    prompt: str,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Decompose a multi-domain system prompt."""
    fn = _require("decompose_prompt", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(prompt)


def exec_get_design_summary(
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Return a compact summary of the current design."""
    fn = _require("get_design_summary", _get_context(_context))
    if not callable(fn):
        return fn
    return fn()


def exec_get_capabilities(
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """List RoboCAD capabilities."""
    fn = _require("get_capabilities", _get_context(_context))
    if not callable(fn):
        return fn
    return fn()


def exec_explain_last_failure(
    target: str = "generic",
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Explain the most recent report of a given type."""
    ctx = _get_context(_context)
    report: dict[str, Any] | None = None

    # Prefer the report from context if available.
    latest_reports = ctx.get("latest_reports") or {}
    if isinstance(latest_reports, dict):
        report = latest_reports.get(target)

    # Allow backend-bound explainer to resolve persisted reports.
    backend_explain = ctx.get("explain_report")
    if backend_explain is not None and report is None:
        if callable(backend_explain):
            report = backend_explain(target)
        else:
            return backend_explain

    return {
        "status": "success",
        "target": target,
        "explanation": explain_report(target, report),
        "report": report,
    }


def exec_generate_design(
    prompt: str,
    max_retries: int = 2,
    detect_domain: bool = True,
    decompose: bool = True,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Generate a new design from a natural-language prompt."""
    fn = _require("generate_design", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        prompt=prompt,
        max_retries=max_retries,
        detect_domain=detect_domain,
        decompose=decompose,
    )


def exec_regenerate_parameters(
    parameter_updates: dict[str, float | int],
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Update parameters and regenerate the current design."""
    fn = _require("regenerate_parameters", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(parameter_updates=parameter_updates)


def exec_synthesize_assembly(
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Re-run assembly mate inference."""
    fn = _require("synthesize_assembly", _get_context(_context))
    if not callable(fn):
        return fn
    return fn()


def exec_run_dfm_report(
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Run a DFM report on the current design."""
    fn = _require("run_dfm_report", _get_context(_context))
    if not callable(fn):
        return fn
    return fn()


def exec_run_verification(
    load_case: str = "static_stress",
    materials: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Run a multi-physics verification load case."""
    fn = _require("run_verification", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        load_case=load_case,
        materials=materials or {},
        parameters=parameters or {},
    )


def exec_build_world(
    template: str = "pick_place",
    material: str = "PLA",
    tolerance: float = 0.1,
    randomize: bool = False,
    seed: int | None = None,
    parameters: dict[str, Any] | None = None,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Build a simulation world for the current design."""
    fn = _require("build_world", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        template=template,
        material=material,
        tolerance=tolerance,
        randomize=randomize,
        seed=seed,
        parameters=parameters or {},
    )


def exec_replay_world(
    duration_seconds: float = 3.0,
    fps: float = 10.0,
    body_names: list[str] | None = None,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Replay the most recently built world."""
    fn = _require("replay_world", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        duration_seconds=duration_seconds,
        fps=fps,
        body_names=body_names or [],
    )


def exec_train_brain(
    n_iters: int = 15,
    pop_size: int = 40,
    eval_episodes: int = 10,
    success_rate_threshold: float = 0.7,
    seed: int = 42,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Train an attention-aware robot brain policy."""
    fn = _require("train_brain", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        n_iters=n_iters,
        pop_size=pop_size,
        eval_episodes=eval_episodes,
        success_rate_threshold=success_rate_threshold,
        seed=seed,
    )


def exec_train_skill(
    skill_description: str = "push the block to the goal",
    n_iters: int = 20,
    pop_size: int = 50,
    eval_episodes: int = 10,
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Train a simple push skill using the RoboCompiler CEM pipeline."""
    fn = _require("train_skill", _get_context(_context))
    if not callable(fn):
        return fn
    return fn(
        skill_description=skill_description,
        n_iters=n_iters,
        pop_size=pop_size,
        eval_episodes=eval_episodes,
    )


def exec_propose_redesign(
    goal: str,
    failure_report: dict[str, Any] | None = None,
    target: str = "generic",
    _context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Propose a concrete redesign plan from a failure report or context."""
    ctx = _get_context(_context)
    report = failure_report or {}
    if not report:
        latest_reports = ctx.get("latest_reports") or {}
        if isinstance(latest_reports, dict):
            report = latest_reports.get(target, latest_reports.get("generic", {}))

    generate_fn = ctx.get("generate_fn")
    return propose_redesign(
        goal=goal,
        report=report,
        target=target,
        context=ctx,
        generate_fn=generate_fn if callable(generate_fn) else None,
    )


TOOL_EXECUTORS: dict[str, Any] = {
    "classify_domain": exec_classify_domain,
    "decompose_prompt": exec_decompose_prompt,
    "get_design_summary": exec_get_design_summary,
    "get_capabilities": exec_get_capabilities,
    "explain_last_failure": exec_explain_last_failure,
    "propose_redesign": exec_propose_redesign,
    "generate_design": exec_generate_design,
    "regenerate_parameters": exec_regenerate_parameters,
    "synthesize_assembly": exec_synthesize_assembly,
    "run_dfm_report": exec_run_dfm_report,
    "run_verification": exec_run_verification,
    "build_world": exec_build_world,
    "replay_world": exec_replay_world,
    "train_brain": exec_train_brain,
    "train_skill": exec_train_skill,
}


def execute_tool(
    name: str,
    parameters: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> Any:
    """Validate and execute a HERMES tool by name.

    This is the single entry point used by the tool registry.
    """
    validated = validate_tool_parameters(name, parameters)
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"status": "error", "message": f"No executor registered for tool {name!r}"}
    return executor(**validated, _context=context or {})
