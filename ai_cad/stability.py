"""Dynamic stability and gait feasibility checks for RoboCAD legged systems.

Rule-based checks intended as a pre-simulation gate. We use conservative
hand-calculations, not a commercial multibody dynamics package.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ai_cad.feature_tree import FeatureTree


G = 9.80665


@dataclass
class StabilityReport:
    """Result of static/dynamic stability checks."""

    support_polygon_m2: float
    polygon_inside: bool
    zmp_x_m: float
    zmp_y_m: float
    zmp_margin_m: float
    statically_stable: bool
    dynamically_stable: bool
    max_inclination_deg: float
    gait_feasible: bool
    warnings: list[str]


def _polygon_area(points: list[tuple[float, float]]) -> float:
    """Shoelace formula for 2D polygon area."""
    if len(points) < 3:
        return 0.0
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _point_in_polygon(point: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = point
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def _polygon_margin(point: tuple[float, float], poly: list[tuple[float, float]]) -> float:
    """Return minimum distance from point to any polygon edge."""
    x, y = point
    min_dist = float("inf")
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            continue
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        px = x1 + t * dx
        py = y1 + t * dy
        dist = math.hypot(x - px, y - py)
        min_dist = min(min_dist, dist)
    return min_dist if math.isfinite(min_dist) else 0.0


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return the convex hull of a set of 2D points using Andrew's monotone chain."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _feet_polygon(tree: FeatureTree) -> list[tuple[float, float]]:
    """Collect foot contact-corner positions and return their convex hull."""
    assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return []

    params = tree.parameter_dict()
    foot_length_mm = 100.0
    foot_width_mm = 60.0
    try:
        foot_length_mm = float(params.get("foot_length", foot_length_mm))
        foot_width_mm = float(params.get("foot_width", foot_width_mm))
    except (TypeError, ValueError):
        pass
    half_l = foot_length_mm * 0.0005
    half_w = foot_width_mm * 0.0005

    corners: list[tuple[float, float]] = []
    for inst in assembly.instances:
        part = tree.find_part(inst.part_id)
        family = (part.family if part else "") or ""
        if "foot" in family.lower():
            tx = inst.transform or {}
            translation = tx.get("translation") or (0.0, 0.0, 0.0)
            cx, cy = float(translation[0]) * 0.001, float(translation[1]) * 0.001
            corners.extend(
                [
                    (cx - half_l, cy - half_w),
                    (cx - half_l, cy + half_w),
                    (cx + half_l, cy - half_w),
                    (cx + half_l, cy + half_w),
                ]
            )

    return _convex_hull(corners)


def check_stability(
    tree: FeatureTree,
    robot_mass_kg: float = 20.0,
    com_height_m: float | None = None,
    lateral_accel_m_s2: float = 0.5,
) -> StabilityReport:
    """Run conservative stability checks on a legged/humanoid design."""
    warnings: list[str] = []
    feet = _feet_polygon(tree)
    if len(feet) < 2:
        warnings.append("Fewer than two feet detected; stability checks assume at least a biped.")

    # If no foot parts, infer from robot height / domain.
    robot_height = 1.0
    params = tree.parameter_dict()
    rh = params.get("robot_height")
    if rh is not None:
        try:
            robot_height = float(rh) * 0.001
        except (TypeError, ValueError):
            robot_height = 1.0
    if not feet:
        hip_width = robot_height * 0.12
        feet = [(-hip_width / 2, 0.0), (hip_width / 2, 0.0)]
        warnings.append("No explicit foot instances; using default biped stance.")

    area = _polygon_area(feet)

    # Estimate CoM projection at center of support polygon unless given.
    if com_height_m is None:
        com_height_m = robot_height * 0.55

    centroid = np.array([0.0, 0.0])
    if feet:
        pts = np.array(feet)
        centroid = pts.mean(axis=0)
    com_x = float(centroid[0])
    com_y = float(centroid[1])

    polygon_inside = _point_in_polygon((com_x, com_y), feet)
    margin = _polygon_margin((com_x, com_y), feet)

    # Static: projection must be inside support polygon.
    statically_stable = polygon_inside and margin > 0.01

    # ZMP under lateral acceleration: zmp = com + (com_height / g) * a_lateral.
    zmp_x = com_x + (com_height_m / G) * lateral_accel_m_s2
    zmp_y = com_y  # no sagittal accel in this simple check
    zmp_inside = _point_in_polygon((zmp_x, zmp_y), feet)
    zmp_margin = _polygon_margin((zmp_x, zmp_y), feet)
    dynamically_stable = zmp_inside and zmp_margin > 0.01

    # Max inclination before CoM exits support polygon along narrow direction.
    if margin > 0 and com_height_m > 0:
        max_inclination_rad = math.atan(margin / com_height_m)
    else:
        max_inclination_rad = 0.0
    max_inclination_deg = math.degrees(max_inclination_rad)

    # Gait feasibility: simplest heuristic based on support area, ZMP margin,
    # and minimum leg count.
    gait_feasible = len(feet) >= 2 and area > 0.005 and zmp_margin > 0.02

    if not statically_stable:
        warnings.append("Static stability margin is small or zero; robot may topple when standing still.")
    if not dynamically_stable:
        warnings.append("ZMP exits support polygon under nominal lateral acceleration.")
    if not gait_feasible:
        warnings.append("Gait feasibility gate failed; increase stance width or reduce CoM height.")

    return StabilityReport(
        support_polygon_m2=round(area, 6),
        polygon_inside=polygon_inside,
        zmp_x_m=round(zmp_x, 6),
        zmp_y_m=round(zmp_y, 6),
        zmp_margin_m=round(zmp_margin, 6),
        statically_stable=statically_stable,
        dynamically_stable=dynamically_stable,
        max_inclination_deg=round(max_inclination_deg, 2),
        gait_feasible=gait_feasible,
        warnings=warnings,
    )


def stability_summary(report: StabilityReport | None) -> dict[str, Any]:
    """Serialize stability report for API responses."""
    if report is None:
        return {}
    return {
        "support_polygon_m2": report.support_polygon_m2,
        "polygon_inside": report.polygon_inside,
        "zmp_x_m": report.zmp_x_m,
        "zmp_y_m": report.zmp_y_m,
        "zmp_margin_m": report.zmp_margin_m,
        "statically_stable": report.statically_stable,
        "dynamically_stable": report.dynamically_stable,
        "max_inclination_deg": report.max_inclination_deg,
        "gait_feasible": report.gait_feasible,
        "warning_count": float(len(report.warnings or [])),
    }
