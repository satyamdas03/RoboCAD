"""Validate a generated CAD model for basic manufacturability and sanity."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import trimesh


def validate_model(stl_path: Optional[Path]) -> dict[str, Any]:
    """Run sanity checks on an exported STL file.

    Returns a dict with:
        - valid: bool
        - manifold: bool
        - watertight: bool
        - bounds_mm: tuple[float, float, float] or None
        - volume_mm3: float or None
        - surface_area_mm2: float or None
        - warnings: list[str]
        - errors: list[str]
    """
    result: dict[str, Any] = {
        "valid": False,
        "manifold": False,
        "watertight": False,
        "bounds_mm": None,
        "volume_mm3": None,
        "surface_area_mm2": None,
        "warnings": [],
        "errors": [],
    }

    if stl_path is None or not stl_path.exists():
        result["errors"].append("No STL file was produced.")
        return result

    try:
        mesh = trimesh.load_mesh(str(stl_path))
    except Exception as exc:
        result["errors"].append(f"Failed to load STL: {exc}")
        return result

    # Ensure we have a Trimesh object (trimesh.load may return Scene).
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            mesh = next(iter(mesh.geometry.values()))
        else:
            result["errors"].append("STL contains multiple bodies; validation not supported for scenes.")
            return result

    result["manifold"] = bool(mesh.is_watertight and mesh.is_winding_consistent)
    result["watertight"] = bool(mesh.is_watertight)
    result["bounds_mm"] = tuple(float(x) for x in mesh.extents)
    result["volume_mm3"] = float(mesh.volume)
    result["surface_area_mm2"] = float(mesh.area)

    if not result["watertight"]:
        result["errors"].append("Model is not watertight.")
    if not result["manifold"]:
        result["warnings"].append("Model may not be manifold.")

    # Sanity checks
    if any(x <= 0 for x in result["bounds_mm"]):
        result["errors"].append("Model has zero or negative extent in at least one dimension.")

    min_dim = min(result["bounds_mm"])
    if min_dim < 0.5:
        result["warnings"].append(f"Smallest dimension is {min_dim:.2f} mm — very thin features may be hard to manufacture.")

    if result["volume_mm3"] is not None and result["volume_mm3"] <= 0:
        result["errors"].append("Model has zero or negative volume.")

    result["valid"] = len(result["errors"]) == 0
    return result
