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

Available tools:
{tool_descriptions}

When you want to call a tool, respond with a JSON block inside triple backticks:

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

Keep explanations concise and engineering-focused. Cite report values when explaining failures.
"""


class HermesAgent:
    """Parse model responses into tool calls and plans."""

    def __init__(self, registry: HermesToolRegistry | None = None) -> None:
        self.registry = registry or HermesToolRegistry()

    def build_system_prompt(self) -> str:
        defs = self.registry.definitions()
        lines = []
        for d in defs:
            params = json.dumps(d.get("parameters", {}))
            lines.append(f"- {d['name']}: {d['description']} params={params}")
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
            messages.append({"role": "system", "content": f"Current context: {json.dumps(context)}"})
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
            if "tool_calls" in parsed:
                for call_data in parsed["tool_calls"]:
                    response.tool_calls.append(
                        ToolCall(
                            tool=call_data.get("tool", ""),
                            parameters=call_data.get("parameters", {}),
                            call_id=call_data.get("call_id", ""),
                        )
                    )
            if "plan" in parsed:
                response.plan = self._parse_plan(parsed["plan"])

        # Fallback: look for a bare JSON object if no fences.
        if not response.tool_calls and not response.plan:
            parsed = self._safe_json(text)
            if parsed and isinstance(parsed, dict):
                if "tool_calls" in parsed:
                    for call_data in parsed["tool_calls"]:
                        response.tool_calls.append(
                            ToolCall(
                                tool=call_data.get("tool", ""),
                                parameters=call_data.get("parameters", {}),
                            )
                        )
                if "plan" in parsed:
                    response.plan = self._parse_plan(parsed["plan"])

        return response

    def _safe_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _parse_plan(self, data: dict[str, Any]) -> Plan:
        steps: list[dict[str, Any]] = []
        for step in data.get("steps", []):
            steps.append(
                {
                    "description": step.get("description", ""),
                    "tool": step.get("tool"),
                    "parameters": step.get("parameters", {}),
                    "depends_on": step.get("depends_on", []),
                }
            )
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
