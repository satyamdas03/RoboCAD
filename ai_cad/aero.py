"""Lightweight aerodynamics analysis stub for RoboCAD Phase 20.

This module provides fast, dependency-free estimates for aero/thermal parts.
It is intentionally a stub: it generates reference-area metrics and thin-airfoil
style coefficients, not high-fidelity CFD. Real CFD integration belongs in
Phase 22.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh


@dataclass
class AeroResult:
    """Result of a lightweight aero analysis pass."""

    success: bool
    lift_coefficient: Optional[float]
    drag_coefficient: Optional[float]
    lift_to_drag_ratio: Optional[float]
    reference_area_mm2: Optional[float]
    stall_warning: bool
    solver: str
    errors: list[str]
    details: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "lift_coefficient": self.lift_coefficient,
            "drag_coefficient": self.drag_coefficient,
            "lift_to_drag_ratio": self.lift_to_drag_ratio,
            "reference_area_mm2": self.reference_area_mm2,
            "stall_warning": self.stall_warning,
            "solver": self.solver,
            "errors": self.errors,
            "details": self.details,
        }


def _load_mesh(stl_path: Path | str) -> trimesh.Trimesh | None:
    try:
        mesh = trimesh.load_mesh(str(stl_path))
    except Exception:
        return None
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            mesh = next(iter(mesh.geometry.values()))
        else:
            return None
    return mesh


def _naca_lookup(naca: str) -> dict[str, float]:
    """Return a tiny lookup table for common NACA 4-digit sections.

    Values are rough estimates for low Reynolds-number / RC-scale flows and are
    not a substitute for wind-tunnel or CFD data.
    """
    # Symmetric / thin sections.
    symmetric = {
        "0006": {"cl_slope": 0.110, "cd0": 0.008, "stall_aoa": 10.0},
        "0009": {"cl_slope": 0.110, "cd0": 0.010, "stall_aoa": 11.0},
        "0012": {"cl_slope": 0.110, "cd0": 0.012, "stall_aoa": 12.0},
        "0015": {"cl_slope": 0.110, "cd0": 0.014, "stall_aoa": 13.0},
        "0021": {"cl_slope": 0.105, "cd0": 0.020, "stall_aoa": 12.0},
    }
    # Cambered sections (approximate).
    cambered = {
        "2412": {"cl0": 0.25, "cl_slope": 0.105, "cd0": 0.013, "stall_aoa": 14.0},
        "2415": {"cl0": 0.30, "cl_slope": 0.105, "cd0": 0.016, "stall_aoa": 14.0},
        "4412": {"cl0": 0.45, "cl_slope": 0.100, "cd0": 0.014, "stall_aoa": 13.0},
        "6412": {"cl0": 0.65, "cl_slope": 0.095, "cd0": 0.015, "stall_aoa": 12.0},
    }
    code = (naca or "0012").strip()
    if code in symmetric:
        return symmetric[code]
    if code in cambered:
        return cambered[code]
    # Generic symmetric fallback.
    return {"cl_slope": 0.110, "cd0": 0.012, "stall_aoa": 12.0}


def _estimate_coefficients(
    mesh: trimesh.Trimesh,
    naca: str,
    angle_of_attack_deg: float,
) -> tuple[float, float, float, bool]:
    """Return (Cl, Cd, reference_area_mm2, stall_warning)."""
    bounds = mesh.bounds
    extents = bounds[1] - bounds[0]
    # Use the two largest extents to define the lifting reference area.
    sorted_extents = np.sort(extents)[::-1]
    reference_area = float(sorted_extents[0] * sorted_extents[1])
    if reference_area <= 0:
        return 0.0, 0.0, 0.0, False

    data = _naca_lookup(naca)
    aoa = float(angle_of_attack_deg)
    cl0 = data.get("cl0", 0.0)
    cl_slope = data["cl_slope"]
    cd0 = data["cd0"]
    stall_aoa = data["stall_aoa"]

    cl = cl0 + cl_slope * aoa
    # Simple quadratic drag polar.
    cd = cd0 + 0.02 * (cl**2)
    stall_warning = abs(aoa) > stall_aoa
    if stall_warning:
        # Crude post-stall lift collapse.
        cl = cl * 0.3

    return cl, cd, reference_area, stall_warning


def run_aero_analysis(
    stl_path: Path | str,
    naca: str = "0012",
    angle_of_attack_deg: float = 0.0,
    flow_velocity_ms: float = 10.0,
) -> AeroResult:
    """Run a lightweight aero estimate on a single STL part.

    Args:
        stl_path: path to the STL file.
        naca: NACA 4-digit code used for coefficient lookup.
        angle_of_attack_deg: freestream angle of attack in degrees.
        flow_velocity_ms: freestream velocity in m/s (used only for reporting).

    Returns:
        AeroResult with lift/drag coefficients, reference area, and stall flag.
    """
    mesh = _load_mesh(stl_path)
    if mesh is None:
        return AeroResult(
            success=False,
            lift_coefficient=None,
            drag_coefficient=None,
            lift_to_drag_ratio=None,
            reference_area_mm2=None,
            stall_warning=False,
            solver="thin_airfoil_stub",
            errors=["Failed to load STL."],
            details={},
        )

    cl, cd, area, stall = _estimate_coefficients(mesh, naca, angle_of_attack_deg)
    l_d = (cl / cd) if cd > 0 else None

    return AeroResult(
        success=True,
        lift_coefficient=round(cl, 4),
        drag_coefficient=round(cd, 4),
        lift_to_drag_ratio=round(l_d, 2) if l_d is not None else None,
        reference_area_mm2=round(area, 4),
        stall_warning=stall,
        solver="thin_airfoil_stub",
        errors=[],
        details={
            "naca": naca,
            "angle_of_attack_deg": angle_of_attack_deg,
            "flow_velocity_ms": flow_velocity_ms,
            "mesh_volume_mm3": float(mesh.volume) if mesh.volume else None,
        },
    )
