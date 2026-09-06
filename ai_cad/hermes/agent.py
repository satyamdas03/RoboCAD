"""HERMES agent — LLM-driven tool parsing and plan generation.

This v1 implementation uses a deterministic JSON-in-text parser so it works with
any model that can emit a fenced JSON block. It intentionally does not require
native tool-use support.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ai_cad.hermes.models import AgentResponse, Message, Plan, PlanStep, ToolCall
from ai_cad.hermes.planner import build_plan
from ai_cad.hermes.tools import HermesToolRegistry


SYSTEM_PROMPT = """You are HERMES, the conversational supervisor for RoboCAD, an AI-powered parametric CAD platform for robotics.

Your job is to help the user across design, simulation, and training. You can propose actions and explain results, but you do NOT execute expensive or design-modifying actions without the user's explicit approval.

Available tools (some require user approval before execution):
{tool_descriptions}

Rules:
1. Read-only tools (get_design_summary, explain_last_failure, get_capabilities, classify_domain, decompose_prompt, propose_redesign) can be called directly.
2. Expensive/modifying tools (generate_design, regenerate_parameters, synthesize_assembly, run_verification, build_world, replay_world, train_brain, train_skill) require approval. If you want to use one, put it in a `plan` or `tool_calls` block and HERMES will ask the user.
3. When explaining failures, cite specific numbers from the report in the context.
4. Keep responses concise and engineering-focused.

When you want to call a tool, respond ONLY with a JSON block inside triple backticks:

```json
{{"tool_calls": [{{"tool": "tool_name", "parameters": {{...}}}}]}}
```

If you want to propose a multi-step plan, use:

```json
{{"plan": {{
  "goal": "short goal",
  "steps": [
    {{"description": "...", "tool": "tool_name", "parameters": {{...}}, "depends_on": []}}
  ]
}}}}
```

If the user asks a question, you may respond in plain text before or after the JSON block.
"""


class HermesAgent:
    """Parse model responses into tool calls and plans."""

    def __init__(self, registry: HermesToolRegistry | None = None) -> None:
        self.registry = registry or HermesToolRegistry()

    def build_system_prompt(self) -> str:
        defs = self.registry.definitions()
        lines = []
        for d in defs:
            params = d.get("parameters", {})
            required = params.get("required", [])
            props = params.get("properties", {})
            prop_lines = []
            for name, spec in props.items():
                req = "required" if name in required else "optional"
                prop_lines.append(f"      {name} ({req}): {spec.get('description', spec.get('type', 'any'))}")
            lines.append(f"- {d['name']}: {d['description']}")
            lines.extend(prop_lines)
        return SYSTEM_PROMPT.format(tool_descriptions="\n".join(lines))

    def prepare_messages(
        self,
        user_message: str,
        history: list[Message] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt()},
        ]
        if context:
            serializable = _json_safe_context(context)
            messages.append({"role": "system", "content": f"Current context: {json.dumps(serializable)}"})
        for msg in history or []:
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def parse_response(self, text: str) -> AgentResponse:
        """Extract JSON tool-call or plan blocks from a raw model response."""
        text = text or ""
        response = AgentResponse(content=text)

        # Try fenced JSON blocks first.
        for block in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL):
            parsed = self._safe_json(block)
            if parsed is None:
                continue
            if "tool_calls" in parsed and isinstance(parsed["tool_calls"], list):
                for call_data in parsed["tool_calls"]:
                    if isinstance(call_data, dict):
                        response.tool_calls.append(
                            ToolCall(
                                tool=call_data.get("tool", ""),
                                parameters=call_data.get("parameters", {}),
                                call_id=call_data.get("call_id", ""),
                            )
                        )
            if parsed.get("plan"):
                response.plan = self._parse_plan(parsed["plan"])

        # Fallback: look for a bare JSON object if no fences.
        if not response.tool_calls and not response.plan:
            parsed = self._safe_json(text)
            if parsed and isinstance(parsed, dict):
                if "tool_calls" in parsed and isinstance(parsed["tool_calls"], list):
                    for call_data in parsed["tool_calls"]:
                        if isinstance(call_data, dict):
                            response.tool_calls.append(
                                ToolCall(
                                    tool=call_data.get("tool", ""),
                                    parameters=call_data.get("parameters", {}),
                                )
                            )
                if parsed.get("plan"):
                    response.plan = self._parse_plan(parsed["plan"])

        return response

    def _safe_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _parse_plan(self, data: dict[str, Any] | None) -> Plan | None:
        if not isinstance(data, dict):
            return None
        steps: list[dict[str, Any]] = []
        for step in data.get("steps", []) or []:
            if isinstance(step, dict):
                steps.append(
                    {
                        "description": step.get("description", ""),
                        "tool": step.get("tool"),
                        "parameters": step.get("parameters", {}),
                        "depends_on": step.get("depends_on", []),
                    }
                )
        if not steps:
            return None
        return build_plan(goal=data.get("goal", ""), steps_data=steps)

    def run(
        self,
        user_message: str,
        history: list[Message] | None = None,
        context: dict[str, Any] | None = None,
        generate_fn: Any | None = None,
    ) -> AgentResponse:
        """Call the LLM and parse the response.

        `generate_fn` must accept a list of message dicts and return a string.
        If no generator is provided, returns a deterministic stub response for tests.
        """
        messages = self.prepare_messages(user_message, history=history, context=context)
        if generate_fn is None:
            return self._stub_response(user_message, context)
        raw = generate_fn(messages)
        return self.parse_response(raw)

    def _stub_response(self, user_message: str, context: dict[str, Any] | None) -> AgentResponse:
        """Deterministic fallback used in tests when no LLM is available."""
        prompt = user_message.lower()
        if "explain" in prompt or "why" in prompt:
            return AgentResponse(
                content="I can explain that. Let me look at the most recent report.",
                tool_calls=[ToolCall(tool="explain_last_failure", parameters={"target": "generic"})],
            )
        if "redesign" in prompt or "fix" in prompt:
            return AgentResponse(
                content="I'll propose a redesign plan.",
                plan=Plan(
                    goal="Address the reported issue",
                    steps=[
                        PlanStep(description="Analyze the current report", tool="explain_last_failure", parameters={"target": "generic"}),
                        PlanStep(description="Propose parameter changes", tool="propose_redesign", parameters={"goal": user_message}),
                    ],
                ),
            )
        if "train" in prompt:
            return AgentResponse(
                content="Training the robot brain requires approval.",
                tool_calls=[ToolCall(tool="train_brain", parameters={})],
            )
        if "world" in prompt:
            return AgentResponse(
                content="I'll build a simulation world for this design.",
                tool_calls=[ToolCall(tool="build_world", parameters={})],
            )
        return AgentResponse(
            content="I'm HERMES. Tell me what you'd like to do: design, simulate, train, or explain a report.",
        )


def _json_safe_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable copy of the context for LLM prompts.

    Backend callables are replaced with placeholder strings so the context dict
    can be serialized without leaking function objects into prompts.
    """
    safe: dict[str, Any] = {}
    for key, value in context.items():
        if callable(value):
            safe[key] = f"<callable:{key}>"
        elif isinstance(value, dict):
            safe[key] = _json_safe_context(value)
        elif isinstance(value, list):
            safe[key] = [
                _json_safe_context(v) if isinstance(v, dict) else ("<callable>" if callable(v) else v)
                for v in value
            ]
        else:
            try:
                json.dumps(value)
                safe[key] = value
            except TypeError:
                safe[key] = str(value)
    return safe
