"""Lightweight thermal analysis stub for RoboCAD Phase 20.

This module provides fast, dependency-free heat-sink estimates: total fin
surface area, thermal resistance, and steady-state temperature rise. It is
intentionally a stub; real thermal simulation belongs in Phase 22.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh


@dataclass
class ThermalResult:
    """Result of a lightweight thermal analysis pass."""

    success: bool
    total_surface_area_mm2: Optional[float]
    base_area_mm2: Optional[float]
    fin_count: Optional[int]
    thermal_resistance_c_per_w: Optional[float]
    max_temperature_c: Optional[float]
    solver: str
    errors: list[str]
    details: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_surface_area_mm2": self.total_surface_area_mm2,
            "base_area_mm2": self.base_area_mm2,
            "fin_count": self.fin_count,
            "thermal_resistance_c_per_w": self.thermal_resistance_c_per_w,
            "max_temperature_c": self.max_temperature_c,
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


def _estimate_fins(mesh: trimesh.Trimesh) -> int:
    """Crude fin count from the number of distinct tall protrusions.

    Splits the mesh into connected components and counts those whose height is
    at least twice their base thickness.
    """
    components = mesh.split(only_watertight=False)
    if len(components) <= 1:
        # A single solid may have no visible fin splitting; default to a guess.
        return 1
    fin_count = 0
    for comp in components:
        extents = comp.extents
        if len(extents) >= 2:
            height = float(extents[2])
            thickness = min(float(extents[0]), float(extents[1]))
            if height > 2.0 * thickness and height > 5.0:
                fin_count += 1
    return max(fin_count, 1)


def _thermal_estimate(
    mesh: trimesh.Trimesh,
    heat_flux_w: float,
    ambient_temp_c: float,
    convection_coefficient_w_per_m2_k: float,
) -> ThermalResult:
    """Estimate thermal performance from surface area and a simple resistance model."""
    if mesh.area is None or mesh.area <= 0:
        return ThermalResult(
            success=False,
            total_surface_area_mm2=None,
            base_area_mm2=None,
            fin_count=None,
            thermal_resistance_c_per_w=None,
            max_temperature_c=None,
            solver="fin_resistance_stub",
            errors=["Mesh surface area unavailable."],
            details={},
        )

    total_area_mm2 = float(mesh.area)
    bounds = mesh.bounds
    extents = bounds[1] - bounds[0]
    # Base is the largest horizontal face; approximate as the footprint.
    base_area_mm2 = float(extents[0] * extents[1])
    fin_count = _estimate_fins(mesh)

    # Convert area to m^2 for the resistance calculation.
    area_m2 = total_area_mm2 * 1e-6
    if area_m2 <= 0:
        return ThermalResult(
            success=False,
            total_surface_area_mm2=None,
            base_area_mm2=None,
            fin_count=None,
            thermal_resistance_c_per_w=None,
            max_temperature_c=None,
            solver="fin_resistance_stub",
            errors=["Computed surface area is zero."],
            details={},
        )

    # R_th = 1 / (h * A); assume natural/forced convection coefficient provided by caller.
    thermal_resistance = 1.0 / (convection_coefficient_w_per_m2_k * area_m2)
    delta_t = heat_flux_w * thermal_resistance
    max_temp = ambient_temp_c + delta_t

    return ThermalResult(
        success=True,
        total_surface_area_mm2=round(total_area_mm2, 4),
        base_area_mm2=round(base_area_mm2, 4),
        fin_count=fin_count,
        thermal_resistance_c_per_w=round(thermal_resistance, 4),
        max_temperature_c=round(max_temp, 2),
        solver="fin_resistance_stub",
        errors=[],
        details={
            "heat_flux_w": heat_flux_w,
            "ambient_temp_c": ambient_temp_c,
            "convection_coefficient_w_per_m2_k": convection_coefficient_w_per_m2_k,
            "mesh_volume_mm3": float(mesh.volume) if mesh.volume else None,
        },
    )


def run_thermal_analysis(
    stl_path: Path | str,
    heat_flux_w: float = 10.0,
    ambient_temp_c: float = 25.0,
    convection_coefficient_w_per_m2_k: float = 50.0,
) -> ThermalResult:
    """Run a lightweight thermal estimate on a single STL part.

    Args:
        stl_path: path to the STL file.
        heat_flux_w: thermal load applied to the part in watts.
        ambient_temp_c: ambient temperature in degrees Celsius.
        convection_coefficient_w_per_m2_k: convective heat transfer coefficient.
            25 is natural convection; 50–100 is weak forced airflow.

    Returns:
        ThermalResult with surface area, thermal resistance, and estimated max temp.
    """
    mesh = _load_mesh(stl_path)
    if mesh is None:
        return ThermalResult(
            success=False,
            total_surface_area_mm2=None,
            base_area_mm2=None,
            fin_count=None,
            thermal_resistance_c_per_w=None,
            max_temperature_c=None,
            solver="fin_resistance_stub",
            errors=["Failed to load STL."],
            details={},
        )

    return _thermal_estimate(
        mesh,
        heat_flux_w=heat_flux_w,
        ambient_temp_c=ambient_temp_c,
        convection_coefficient_w_per_m2_k=convection_coefficient_w_per_m2_k,
    )
