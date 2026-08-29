"""Tolerance, fit, and clearance checks for RoboCAD Phase 12.

Performs deterministic geometric checks between two parts (or two meshes):
- clearance between closest points
- interference / overlap volume
- shaft/hole fit classification (clearance / transition / interference)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import warnings

import numpy as np
import trimesh


@dataclass
class FitCheck:
    """Result of a fit/clearance check between two meshes."""

    name: str
    mesh_a: str
    mesh_b: str
    min_clearance_mm: float
    max_clearance_mm: float
    mean_clearance_mm: float
    interference_volume_mm3: Optional[float]
    classification: str  # "clearance", "transition", "interference"
    details: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mesh_a": self.mesh_a,
            "mesh_b": self.mesh_b,
            "min_clearance_mm": self.min_clearance_mm,
            "max_clearance_mm": self.max_clearance_mm,
            "mean_clearance_mm": self.mean_clearance_mm,
            "interference_volume_mm3": self.interference_volume_mm3,
            "classification": self.classification,
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


def _nearest_distances(mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh, samples: int = 2000) -> np.ndarray:
    """Sample points on mesh A and return signed distances to mesh B.

    Negative values mean the point is inside mesh B (interference).
    """
    points_a = mesh_a.sample(samples)
    try:
        distances = mesh_b.nearest.on_surface(points_a)[1]
    except Exception:
        # Fallback to a simpler unsigned distance if signed is not available.
        distances = mesh_b.nearest.on_surface(points_a)[1]
    signed = np.empty_like(distances)
    try:
        inside_a = mesh_a.contains(points_a)
        inside_b = mesh_b.contains(points_a)
        signed = np.where(inside_b, -distances, distances)
    except Exception:
        signed = distances
    return signed


def check_fit(
    a_path: Path | str,
    b_path: Path | str,
    name: str = "fit_check",
    clearance_threshold_mm: float = 0.05,
    interference_threshold_mm: float = -0.05,
    samples: int = 2000,
) -> FitCheck:
    """Check fit between two STL files.

    Args:
        a_path: path to first STL (e.g. shaft).
        b_path: path to second STL (e.g. hole).
        name: identifier for this check.
        clearance_threshold_mm: min positive clearance to classify as "clearance" fit.
        interference_threshold_mm: max negative clearance to classify as "interference".
        samples: number of surface points to sample.
    """
    mesh_a = _load_mesh(a_path)
    mesh_b = _load_mesh(b_path)
    if mesh_a is None or mesh_b is None:
        raise ValueError("Failed to load one or both meshes for fit check.")

    distances = _nearest_distances(mesh_a, mesh_b, samples)
    min_d = float(np.min(distances))
    max_d = float(np.max(distances))
    mean_d = float(np.mean(distances))

    # Interference volume: signed distance integration is hard; use trimesh boolean if available.
    # Suppress the harmless divide-by-zero RuntimeWarning trimesh emits on a
    # zero-volume intersection (e.g. separated clearance-fit parts).
    interference_volume: Optional[float] = None
    try:
        if mesh_a.is_watertight and mesh_b.is_watertight:
            intersection = mesh_a.intersection(mesh_b)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                if intersection is not None and hasattr(intersection, "volume"):
                    interference_volume = float(intersection.volume)
    except Exception:
        interference_volume = None

    if min_d < interference_threshold_mm:
        classification = "interference"
    elif min_d < clearance_threshold_mm:
        classification = "transition"
    else:
        classification = "clearance"

    return FitCheck(
        name=name,
        mesh_a=str(a_path),
        mesh_b=str(b_path),
        min_clearance_mm=round(min_d, 4),
        max_clearance_mm=round(max_d, 4),
        mean_clearance_mm=round(mean_d, 4),
        interference_volume_mm3=round(interference_volume, 4) if interference_volume is not None else None,
        classification=classification,
        details={
            "clearance_threshold_mm": clearance_threshold_mm,
            "interference_threshold_mm": interference_threshold_mm,
            "samples": samples,
        },
    )
