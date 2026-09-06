"""HERMES — conversational cross-domain supervisor for RoboCAD.

Public API:
    HermesSession        — persisted conversation + plan state
    HermesAgent          — LLM-driven tool-calling agent
    HermesToolRegistry   — registry of RoboCAD actions HERMES can invoke
    ApprovalGate         — decides which tool calls need human confirmation
    explain_report       — plain-language summaries of DFM/verification/brain reports
    execute_plan_step    — run one plan step through the registry
"""
from __future__ import annotations

from ai_cad.hermes.agent import HermesAgent
from ai_cad.hermes.context import build_design_context
from ai_cad.hermes.executor import execute_tool
from ai_cad.hermes.explain import explain_report
from ai_cad.hermes.gate import ApprovalGate
from ai_cad.hermes.livekit_token import create_agent_token, create_token, livekit_url
from ai_cad.hermes.llm import build_llm_caller
from ai_cad.hermes.models import Plan as HermesPlan, PlanStep as HermesPlanStep
from ai_cad.hermes.planner import execute_plan_step
from ai_cad.hermes.session import HermesSession
from ai_cad.hermes.tools import HermesToolRegistry
from ai_cad.hermes.validation import ValidationErrorMessage, validate_tool_parameters

__all__ = [
    "HermesAgent",
    "ApprovalGate",
    "build_design_context",
    "build_llm_caller",
    "create_agent_token",
    "create_token",
    "explain_report",
    "execute_plan_step",
    "execute_tool",
    "HermesPlan",
    "HermesPlanStep",
    "HermesSession",
    "HermesToolRegistry",
    "livekit_url",
    "validate_tool_parameters",
    "ValidationErrorMessage",
]
