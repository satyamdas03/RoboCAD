"""Pydantic models for the RoboCAD multi-physics verification engine."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LoadCase(str, Enum):
    """Deterministic closed load-case templates supported by the engine."""

    STATIC_STRESS = "static_stress"
    DROP_TEST = "drop_test"
    THERMAL_EXPANSION = "thermal_expansion"
    FATIGUE_CYCLES = "fatigue_cycles"
    FASTENER_PULL_OUT = "fastener_pull_out"
    WIND_TUNNEL_DRAG = "wind_tunnel_drag"
    HEAT_SINK_THERMAL_RESISTANCE = "heat_sink_thermal_resistance"
    JOINT_TORQUE_CHECK = "joint_torque_check"
    MESH_QUALITY = "mesh_quality"
    ASSEMBLY_CLEARANCE = "assembly_clearance"


class VerificationRequest(BaseModel):
    """Request to run a single verification load case on a design."""

    design_id: str
    load_case: LoadCase
    materials: dict[str, str] = Field(
        default_factory=dict,
        description="Map of part_id to material name.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Case-specific overrides, e.g. load_magnitude_n, heat_flux_w.",
    )


class MeshQualityReport(BaseModel):
    """Result of a mesh-quality pre-check."""

    is_suitable_for_solver: bool
    triangle_count: int
    watertight: bool
    non_manifold_edges: int
    degenerate_triangles: int
    high_aspect_ratio_triangles: int
    bounding_box_m: tuple[float, float, float]
    issues: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """Pass/fail report for a single load case."""

    design_id: str
    load_case: LoadCase
    passed: bool
    report_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_modes: list[str] = Field(default_factory=list)
    redesign_suggestions: list[str] = Field(default_factory=list)
    mesh_report: MeshQualityReport | None = None
    raw_output: dict[str, Any] | None = None
