"""Optional Finite Element Analysis wrapper for RoboCAD Phase 12.

This module provides a minimal, dependency-light interface for running
static structural checks on generated parts. It uses CalculiX/ElmerFEM-style
input generation if a solver is available, but for Phase 12 the default
implementation runs a simple cantilever-beam approximation based on geometry
and material properties.

The interface is intentionally pluggable: replace `run_static_analysis` with a
real solver adapter later without changing consumers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh


@dataclass
class FEAResult:
    """Result of a static analysis pass."""

    success: bool
    max_stress_mpa: Optional[float]
    max_displacement_mm: Optional[float]
    safety_factor: Optional[float]
    solver: str
    errors: list[str]
    details: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "max_stress_mpa": self.max_stress_mpa,
            "max_displacement_mm": self.max_displacement_mm,
            "safety_factor": self.safety_factor,
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


def _simple_beam_estimate(
    mesh: trimesh.Trimesh,
    fixed_face: str,
    load_direction: tuple[float, float, float],
    load_magnitude_n: float,
    youngs_modulus_mpa: float,
    yield_strength_mpa: float,
) -> FEAResult:
    """Estimate max stress and deflection using a simple beam model.

    Fixed face determines the cantilever length; load is applied at the centroid
    of the opposite end. This is only meaningful for prismatic/bracket-like parts.
    """
    if mesh.extents is None or mesh.volume is None or mesh.volume <= 0:
        return FEAResult(
            success=False,
            max_stress_mpa=None,
            max_displacement_mm=None,
            safety_factor=None,
            solver="simple_beam",
            errors=["Mesh bounds or volume unavailable."],
            details={},
        )

    bounds = mesh.bounds
    axis_map = {
        "+x": 0,
        "-x": 0,
        "+y": 1,
        "-y": 1,
        "+z": 2,
        "-z": 2,
    }

    if fixed_face not in axis_map:
        return FEAResult(
            success=False,
            max_stress_mpa=None,
            max_displacement_mm=None,
            safety_factor=None,
            solver="simple_beam",
            errors=[f"Unknown fixed_face: {fixed_face}"],
            details={},
        )

    axis = axis_map[fixed_face]
    length = float(bounds[1, axis] - bounds[0, axis])
    if length <= 0:
        return FEAResult(
            success=False,
            max_stress_mpa=None,
            max_displacement_mm=None,
            safety_factor=None,
            solver="simple_beam",
            errors=["Computed length is zero."],
            details={},
        )

    # Approximate cross-sectional area perpendicular to load direction.
    extents = mesh.extents
    area_axes = [i for i in range(3) if i != axis]
    area = float(extents[area_axes[0]] * extents[area_axes[1]])
    if area <= 0:
        return FEAResult(
            success=False,
            max_stress_mpa=None,
            max_displacement_mm=None,
            safety_factor=None,
            solver="simple_beam",
            errors=["Computed cross-sectional area is zero."],
            details={},
        )

    # Rectangular beam moment of inertia about the bending axis.
    b, h = float(extents[area_axes[0]]), float(extents[area_axes[1]])
    I = b * h**3 / 12.0

    # Cantilever with point load at free end.
    max_moment = load_magnitude_n * length
    max_stress = (max_moment * (h / 2.0)) / I if I > 0 else float("inf")
    max_displacement = (load_magnitude_n * length**3) / (3.0 * youngs_modulus_mpa * I) if I > 0 else float("inf")

    safety_factor = yield_strength_mpa / max_stress if max_stress > 0 else None

    return FEAResult(
        success=True,
        max_stress_mpa=round(max_stress, 4),
        max_displacement_mm=round(max_displacement, 4),
        safety_factor=round(safety_factor, 2) if safety_factor is not None else None,
        solver="simple_beam",
        errors=[],
        details={
            "length_mm": length,
            "cross_section_area_mm2": round(area, 4),
            "moment_of_inertia_mm4": round(I, 4),
            "load_magnitude_n": load_magnitude_n,
            "load_direction": load_direction,
            "youngs_modulus_mpa": youngs_modulus_mpa,
            "yield_strength_mpa": yield_strength_mpa,
        },
    )


def run_static_analysis(
    stl_path: Path | str,
    fixed_face: str = "-x",
    load_direction: tuple[float, float, float] = (0, 0, -1),
    load_magnitude_n: float = 100.0,
    material: str = "PLA",
) -> FEAResult:
    """Run a simple static analysis on a single STL part.

    Args:
        stl_path: path to the STL file.
        fixed_face: which face is fully constrained ('+x', '-x', '+y', '-y', '+z', '-z').
        load_direction: unit vector of applied load.
        load_magnitude_n: force magnitude in Newtons.
        material: material name; used to look up Young's modulus and yield strength.

    Returns:
        FEAResult with max stress, displacement, and safety factor.
    """
    material_props = {
        "PLA": {"youngs_modulus_mpa": 3500.0, "yield_strength_mpa": 65.0},
        "PETG": {"youngs_modulus_mpa": 2100.0, "yield_strength_mpa": 80.0},
        "ABS": {"youngs_modulus_mpa": 2200.0, "yield_strength_mpa": 40.0},
        "aluminum": {"youngs_modulus_mpa": 70000.0, "yield_strength_mpa": 270.0},
        "steel": {"youngs_modulus_mpa": 210000.0, "yield_strength_mpa": 250.0},
    }
    props = material_props.get(material.lower(), material_props["PLA"])

    mesh = _load_mesh(stl_path)
    if mesh is None:
        return FEAResult(
            success=False,
            max_stress_mpa=None,
            max_displacement_mm=None,
            safety_factor=None,
            solver="simple_beam",
            errors=["Failed to load STL."],
            details={},
        )

    return _simple_beam_estimate(
        mesh,
        fixed_face=fixed_face,
        load_direction=load_direction,
        load_magnitude_n=load_magnitude_n,
        youngs_modulus_mpa=props["youngs_modulus_mpa"],
        yield_strength_mpa=props["yield_strength_mpa"],
    )
