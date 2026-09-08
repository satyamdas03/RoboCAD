"""Convert deep-solver failures into redesign suggestions.

This is intentionally a rule-based first pass; a future version can ask an
LLM to interpret solver logs and propose parameter changes.
"""
from __future__ import annotations

from typing import Any


def suggest_redesign(
    load_case: str,
    metrics: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> list[str]:
    """Return a list of redesign suggestions given solver results."""
    suggestions: list[str] = []

    if load_case == "static_stress":
        sf = metrics.get("safety_factor", float("inf"))
        if isinstance(sf, (int, float)) and sf < 1.5:
            suggestions.append("Increase wall thickness or add ribs to reduce peak stress.")
            suggestions.append("Switch to a higher-strength material (e.g., PETG, nylon, or aluminum).")
        if any("high stress concentration" in str(w).lower() for w in warnings):
            suggestions.append("Add fillets at sharp internal corners.")

    if load_case == "drop_test":
        if any("impact" in str(e).lower() for e in errors):
            suggestions.append("Increase impact-resistant wall thickness or use a tougher material.")

    if load_case in ("thermal_expansion", "heat_sink_thermal_resistance"):
        max_temp = metrics.get("max_temperature_c", 0.0)
        if isinstance(max_temp, (int, float)) and max_temp > 80.0:
            suggestions.append("Increase fin count or surface area for better cooling.")
            suggestions.append("Use aluminum or copper for higher thermal conductivity.")

    if load_case == "wind_tunnel_drag":
        cd = metrics.get("cd", 0.0)
        if isinstance(cd, (int, float)) and cd > 0.5:
            suggestions.append("Streamline leading edges and reduce frontal area.")

    if load_case == "fatigue_cycles":
        suggestions.append("Reduce stress concentration features and verify material endurance limit.")

    if load_case == "fastener_pull_out":
        suggestions.append("Increase boss diameter or embed length for threaded inserts.")

    if load_case == "joint_torque_check":
        suggestions.append("Verify actuator torque margin and reduce link inertia if needed.")

    if not suggestions and errors:
        suggestions.append("Review solver log and boundary conditions, then re-submit with adjusted geometry.")

    return suggestions
