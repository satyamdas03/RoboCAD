"""Approval-gate logic for HERMES tool calls.

HERMES is an observer/proposer first. Some actions are cheap and read-only; others
modify designs or consume significant compute and require explicit user approval.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalGate:
    """Decides whether a given tool call needs human confirmation.

    Attributes:
        expensive_tools: tool names that always require approval.
        read_only_tools: tool names that never require approval.
        default_requires_approval: fallback for tools not in either set.
    """

    expensive_tools: frozenset[str] = frozenset(
        {
            "generate_design",
            "regenerate_parameters",
            "synthesize_assembly",
            "train_brain",
            "train_skill",
            "run_variant_sweep",
            "export_bundle",
        }
    )
    read_only_tools: frozenset[str] = frozenset(
        {
            "classify_domain",
            "decompose_prompt",
            "explain_last_failure",
            "propose_redesign",
            "get_design_summary",
            "get_capabilities",
            "get_status",
        }
    )
    default_requires_approval: bool = False

    def requires_approval(self, tool: str) -> bool:
        if tool in self.read_only_tools:
            return False
        if tool in self.expensive_tools:
            return True
        return self.default_requires_approval

    def classify(self, tool: str) -> str:
        if tool in self.read_only_tools:
            return "read_only"
        if tool in self.expensive_tools:
            return "expensive"
        if self.default_requires_approval:
            return "requires_approval"
        return "read_only"
