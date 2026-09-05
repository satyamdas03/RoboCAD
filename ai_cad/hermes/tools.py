"""HERMES tool registry.

Tools are thin wrappers around existing RoboCAD backend APIs. They are intentionally
not executed directly from the registry; the planner/agent calls
`execute_plan_step()` with a live backend context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HermesTool:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    executor: Callable[..., Any] | None = None

    def to_function_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class HermesToolRegistry:
    """Registry of actions HERMES can propose and execute."""

    def __init__(self) -> None:
        self._tools: dict[str, HermesTool] = {}
        self._register_defaults()

    def register(self, tool: HermesTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> HermesTool:
        if name not in self._tools:
            raise KeyError(f"Tool {name!r} not found")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.to_function_definition() for tool in self._tools.values()]

    def execute(self, name: str, parameters: dict[str, Any], context: dict[str, Any] | None = None) -> Any:
        tool = self.get(name)
        if tool.executor is None:
            return {"status": "stub", "message": f"Tool {name!r} has no executor"}
        ctx = context or {}
        return tool.executor(**parameters, _context=ctx)

    def _register_defaults(self) -> None:
        # Read-only / planning tools
        self.register(
            HermesTool(
                name="classify_domain",
                description="Classify the domain of a user prompt (mechanical, aero, thermal, electronics, humanoid, multi).",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "User prompt to classify"},
                    },
                    "required": ["prompt"],
                },
            )
        )
        self.register(
            HermesTool(
                name="decompose_prompt",
                description="Decompose a multi-domain system prompt into part families and sub-prompts.",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "System prompt to decompose"},
                    },
                    "required": ["prompt"],
                },
            )
        )
        self.register(
            HermesTool(
                name="explain_last_failure",
                description="Explain the most recent failure or report in plain language.",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Report type: dfm, verification, brain, world_replay, generic"},
                    },
                    "required": ["target"],
                },
            )
        )
        self.register(
            HermesTool(
                name="propose_redesign",
                description="Propose a redesign plan based on a reported failure or user goal.",
                parameters={
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "High-level redesign goal"},
                        "failure_report": {"type": "object", "description": "Failure report to address"},
                    },
                    "required": ["goal"],
                },
            )
        )
        self.register(
            HermesTool(
                name="get_design_summary",
                description="Return a summary of the current design including prompt, domain, validation, and parameters.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            )
        )
        self.register(
            HermesTool(
                name="get_capabilities",
                description="List supported RoboCAD capabilities, templates, and export formats.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            )
        )

        # Design-modifying tools
        self.register(
            HermesTool(
                name="generate_design",
                description="Generate a new parametric design from a natural-language prompt.",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "max_retries": {"type": "integer", "default": 2},
                        "detect_domain": {"type": "boolean", "default": True},
                        "decompose": {"type": "boolean", "default": True},
                    },
                    "required": ["prompt"],
                },
            )
        )
        self.register(
            HermesTool(
                name="regenerate_parameters",
                description="Update one or more editable parameters and regenerate the design.",
                parameters={
                    "type": "object",
                    "properties": {
                        "parameter_updates": {
                            "type": "object",
                            "description": "Map of parameter name to new numeric value",
                        },
                    },
                    "required": ["parameter_updates"],
                },
            )
        )
        self.register(
            HermesTool(
                name="synthesize_assembly",
                description="Re-run mate inference and joint synthesis on the current design's assembly.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            )
        )

        # Analysis tools (read-only but may be slow)
        self.register(
            HermesTool(
                name="run_dfm_report",
                description="Run a DFM/manufacturability report on the current design.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            )
        )
        self.register(
            HermesTool(
                name="run_verification",
                description="Run a multi-physics verification load case on the current design.",
                parameters={
                    "type": "object",
                    "properties": {
                        "load_case": {"type": "string", "default": "static_stress"},
                        "materials": {"type": "object"},
                        "parameters": {"type": "object"},
                    },
                    "required": [],
                },
            )
        )

        # Simulation / training tools
        self.register(
            HermesTool(
                name="build_world",
                description="Build a simulation world from the current design using a world template.",
                parameters={
                    "type": "object",
                    "properties": {
                        "template": {"type": "string", "default": "pick_place"},
                        "material": {"type": "string", "default": "PLA"},
                        "tolerance": {"type": "number", "default": 0.1},
                    },
                    "required": [],
                },
            )
        )
        self.register(
            HermesTool(
                name="replay_world",
                description="Run a deterministic world replay and return trajectories/contacts/sensors.",
                parameters={
                    "type": "object",
                    "properties": {
                        "duration_seconds": {"type": "number", "default": 3.0},
                        "fps": {"type": "number", "default": 10.0},
                    },
                    "required": [],
                },
            )
        )
        self.register(
            HermesTool(
                name="train_brain",
                description="Train an attention-aware policy for the current world using NumPy CEM.",
                parameters={
                    "type": "object",
                    "properties": {
                        "n_iters": {"type": "integer", "default": 15},
                        "pop_size": {"type": "integer", "default": 40},
                        "eval_episodes": {"type": "integer", "default": 10},
                        "success_rate_threshold": {"type": "number", "default": 0.7},
                        "seed": {"type": "integer", "default": 42},
                    },
                    "required": [],
                },
            )
        )
        self.register(
            HermesTool(
                name="train_skill",
                description="Train a simple push skill using the RoboCompiler CEM pipeline.",
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_description": {"type": "string", "default": "push the block to the goal"},
                        "n_iters": {"type": "integer", "default": 20},
                        "pop_size": {"type": "integer", "default": 50},
                        "eval_episodes": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            )
        )
