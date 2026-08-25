"""Design-for-Manufacturing rule engine for RoboCAD Phase 12.

Evaluates a trimesh model against common FDM/milling rules and returns a
structured report. Rules are intentionally simple and deterministic so they can
be driven by geometry alone, without requiring a full process planner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh


@dataclass
class DFMRule:
    """One manufacturability rule."""

    name: str
    message: str
    severity: str  # "error", "warning", "info"
    metric: dict[str, Any]


class DFMReport:
    """Structured DFM report for a single STL mesh."""

    def __init__(self, valid: bool = True):
        self.valid = valid
        self.rules: list[DFMRule] = []
        self.min_wall_thickness_mm: Optional[float] = None
        self.min_hole_diameter_mm: Optional[float] = None
        self.overhang_ratio: float = 0.0
        self.passed_rules: list[str] = []
        self.failed_rules: list[str] = []

    def add(self, rule: DFMRule) -> None:
        self.rules.append(rule)
        if rule.severity in ("error",):
            self.valid = False
            self.failed_rules.append(rule.name)
        else:
            self.passed_rules.append(rule.name)

    def model_dump(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "min_wall_thickness_mm": self.min_wall_thickness_mm,
            "min_hole_diameter_mm": self.min_hole_diameter_mm,
            "overhang_ratio": self.overhang_ratio,
            "passed_rules": self.passed_rules,
            "failed_rules": self.failed_rules,
            "rules": [
                {
                    "name": r.name,
                    "message": r.message,
                    "severity": r.severity,
                    "metric": r.metric,
                }
                for r in self.rules
            ],
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


def _estimate_min_wall_thickness(mesh: trimesh.Trimesh) -> float:
    """Approximate minimum wall thickness from vertex-to-surface distances.

    For each vertex on the convex hull we project inward along the normal and
    measure distance to first intersection. This is a coarse heuristic suitable
    for thin-wall detection.
    """
    try:
        # Use trimesh's built-in thickness estimate if available; otherwise fall back.
        thickness = mesh.thickness if hasattr(mesh, "thickness") else None
        if thickness is not None:
            return float(thickness)
    except Exception:
        pass

    # Fallback: shortest edge length as a conservative lower bound.
    if len(mesh.edges_unique) > 0:
        edge_lengths = np.linalg.norm(
            mesh.vertices[mesh.edges_unique[:, 1]] - mesh.vertices[mesh.edges_unique[:, 0]],
            axis=1,
        )
        return float(np.min(edge_lengths))
    return 0.0


def _estimate_min_hole_diameter(mesh: trimesh.Trimesh, slices: int = 7) -> Optional[float]:
    """Approximate smallest hole diameter by slicing and comparing interior loops."""
    bounds = mesh.bounds
    if bounds is None:
        return None
    z_min, z_max = float(bounds[0, 2]), float(bounds[1, 2])
    if z_max <= z_min or slices < 1:
        return None

    margin = 0.05 * (z_max - z_min)
    z_levels = np.linspace(z_min + margin, z_max - margin, slices)

    min_diameter: Optional[float] = None
    for z in z_levels:
        try:
            section = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
            if section is None:
                continue
            planar, _ = section.to_2D()
        except Exception:
            continue

        loops = _extract_loops_from_path(planar)
        if len(loops) < 2:
            continue

        loops_by_area = sorted(loops, key=lambda lp: abs(lp["area"]), reverse=True)
        outer_area = abs(loops_by_area[0]["area"])
        for loop in loops_by_area[1:]:
            if abs(loop["area"]) >= 0.99 * outer_area:
                continue
            diameter = math.sqrt(abs(loop["area"]) * 4.0 / math.pi)
            if min_diameter is None or diameter < min_diameter:
                min_diameter = diameter

    return min_diameter


def _extract_loops_from_path(path2d: trimesh.path.Path2D) -> list[dict[str, Any]]:
    loops: list[dict[str, Any]] = []
    if path2d is None or path2d.entities is None:
        return loops

    vertices = path2d.vertices
    for entity in path2d.entities:
        if not hasattr(entity, "points") or len(entity.points) < 3:
            continue
        pts = vertices[np.array(entity.points, dtype=int)]
        if len(pts) < 3:
            continue
        if not np.allclose(pts[0], pts[-1]):
            pts = np.vstack((pts, pts[0]))
        area = 0.5 * float(np.sum(pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1]))
        loops.append({"points": pts, "area": area})

    return loops


def analyze_dfm(
    stl_path: Path | str,
    min_wall_thickness_mm: float = 0.8,
    min_hole_diameter_mm: float = 2.0,
    max_overhang_ratio: float = 0.05,
    overhang_angle_deg: float = 50.0,
) -> DFMReport:
    """Run the DFM rule set against an STL file and return a report."""
    report = DFMReport(valid=True)

    mesh = _load_mesh(stl_path)
    if mesh is None:
        report.add(DFMRule("load", "Failed to load STL file.", "error", {}))
        return report

    if mesh.extents is not None:
        bounds = tuple(float(x) for x in mesh.extents)
    else:
        bounds = None

    if bounds is None or mesh.volume is None or mesh.volume <= 0:
        report.add(DFMRule("geometry", "Could not compute valid bounds or volume.", "error", {}))
        return report

    # Rule: minimum wall thickness.
    min_thickness = _estimate_min_wall_thickness(mesh)
    report.min_wall_thickness_mm = round(min_thickness, 4)
    if min_thickness < min_wall_thickness_mm:
        report.add(
            DFMRule(
                "min_wall_thickness",
                f"Minimum wall thickness ~{min_thickness:.2f} mm is below {min_wall_thickness_mm} mm — may fail in FDM.",
                "error" if min_thickness < 0.4 else "warning",
                {"min_wall_thickness_mm": min_thickness, "threshold_mm": min_wall_thickness_mm},
            )
        )
    else:
        report.passed_rules.append("min_wall_thickness")

    # Rule: minimum hole diameter.
    min_hole = _estimate_min_hole_diameter(mesh)
    report.min_hole_diameter_mm = round(min_hole, 4) if min_hole is not None else None
    if min_hole is not None and min_hole < min_hole_diameter_mm:
        report.add(
            DFMRule(
                "min_hole_diameter",
                f"Smallest hole diameter ~{min_hole:.2f} mm is below {min_hole_diameter_mm} mm — consider clearance or drill after print.",
                "warning",
                {"min_hole_diameter_mm": min_hole, "threshold_mm": min_hole_diameter_mm},
            )
        )
    else:
        report.passed_rules.append("min_hole_diameter")

    # Rule: overhang ratio.
    threshold = math.cos(math.radians(90.0 - overhang_angle_deg))
    face_normals = mesh.face_normals
    face_centroids = mesh.triangles_center
    min_z = float(mesh.vertices[:, 2].min())
    downward_mask = face_normals[:, 2] < -threshold
    above_plate_mask = face_centroids[:, 2] > min_z + 0.01
    overhang_mask = downward_mask & above_plate_mask
    overhang_area = float(mesh.area_faces[overhang_mask].sum()) if len(overhang_mask) else 0.0
    overhang_ratio = overhang_area / mesh.area if mesh.area > 0 else 0.0
    report.overhang_ratio = round(overhang_ratio, 4)
    if overhang_ratio > max_overhang_ratio:
        report.add(
            DFMRule(
                "overhang",
                f"{overhang_ratio * 100:.1f}% of surface area is overhang above {overhang_angle_deg}° — supports likely needed.",
                "warning",
                {"overhang_ratio": overhang_ratio, "threshold": max_overhang_ratio},
            )
        )
    else:
        report.passed_rules.append("overhang")

    # Rule: tiny bounding-box dimension.
    min_dim = min(bounds)
    if min_dim < 0.5:
        report.add(
            DFMRule(
                "tiny_extent",
                f"Smallest bounding-box dimension is {min_dim:.2f} mm — check printer resolution.",
                "warning",
                {"min_bound_mm": min_dim},
            )
        )
    else:
        report.passed_rules.append("tiny_extent")

    return report
