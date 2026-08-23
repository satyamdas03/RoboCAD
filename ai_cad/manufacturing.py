"""Manufacturability analysis for generated STL models.

Reports basic metrics useful for 3D printing and machining:
- bounding box, volume, surface area
- overhang analysis for FDM printing
- minimum hole diameter / thin feature detection
- rough print-time heuristic
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh


# FDM printers typically struggle with overhangs beyond ~45-55 degrees.
DEFAULT_OVERHANG_ANGLE_DEG = 50.0

# Layer height used for the rough print-time heuristic (mm).
DEFAULT_LAYER_HEIGHT_MM = 0.2

# Typical FDM print speed (mm/s) for heuristic.
DEFAULT_PRINT_SPEED_MM_S = 50.0


def _estimate_min_hole_diameter(mesh: trimesh.Trimesh, slices: int = 7) -> Optional[float]:
    """Estimate the smallest hole diameter by slicing the mesh along Z.

    Cross-sections produce one or more closed loops. The loop with the largest
    absolute area is treated as the outer profile; any additional loops at the
    same Z height are interior holes. The hole diameter is approximated by the
    area-equivalent circle diameter.
    """
    bounds = mesh.bounds
    if bounds is None:
        return None
    z_min, z_max = float(bounds[0, 2]), float(bounds[1, 2])
    if z_max <= z_min or slices < 1:
        return None

    # Avoid slicing right at the very top/bottom where sections can be degenerate.
    margin = 0.05 * (z_max - z_min)
    z_levels = np.linspace(z_min + margin, z_max - margin, slices)

    min_diameter: Optional[float] = None
    for z in z_levels:
        try:
            section = mesh.section(plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
            if section is None:
                continue
            planar, _transform = section.to_2D()
        except Exception:
            continue

        loops = _extract_loops_from_path(planar)
        if len(loops) < 2:
            continue

        # Largest loop by area is the outer profile; smaller loops are holes.
        loops_by_area = sorted(loops, key=lambda lp: abs(lp["area"]), reverse=True)
        outer_area = abs(loops_by_area[0]["area"])
        for loop in loops_by_area[1:]:
            if abs(loop["area"]) >= 0.99 * outer_area:
                # Same-size loops are not holes; skip to avoid false positives.
                continue
            diameter = math.sqrt(abs(loop["area"]) * 4.0 / math.pi)
            if min_diameter is None or diameter < min_diameter:
                min_diameter = diameter

    return min_diameter


def _extract_loops_from_path(path2d: trimesh.path.Path2D) -> list[dict[str, Any]]:
    """Return closed loops from a Path2D with their signed polygon area."""
    loops: list[dict[str, Any]] = []
    if path2d is None or path2d.entities is None:
        return loops

    vertices = path2d.vertices
    for entity in path2d.entities:
        if not hasattr(entity, "points") or len(entity.points) < 3:
            continue
        # entity.points are indices of the polyline vertices in path order.
        pts = vertices[np.array(entity.points, dtype=int)]
        if len(pts) < 3:
            continue
        # Close the loop if it isn't already.
        if not np.allclose(pts[0], pts[-1]):
            pts = np.vstack((pts, pts[0]))
        # Shoelace area.
        area = 0.5 * float(np.sum(pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1]))
        loops.append({"points": pts, "area": area})

    return loops


def analyze_model(
    stl_path: Optional[Path | str],
    overhang_angle_deg: float = DEFAULT_OVERHANG_ANGLE_DEG,
    layer_height_mm: float = DEFAULT_LAYER_HEIGHT_MM,
    print_speed_mm_s: float = DEFAULT_PRINT_SPEED_MM_S,
) -> dict[str, Any]:
    """Return a manufacturing report for an STL file.

    Args:
        stl_path: path to the STL file.
        overhang_angle_deg: faces whose normal makes an angle greater than this
            from the vertical (Z+) are considered overhangs.
        layer_height_mm: layer height for print-time heuristic.
        print_speed_mm_s: assumed print speed for heuristic.

    Returns:
        dict with keys:
            - valid: bool
            - bounds_mm: [dx, dy, dz] or None
            - volume_cm3: float or None
            - surface_area_cm2: float or None
            - overhangs: list of face indices considered overhangs
            - overhang_area_mm2: total area of overhang faces
            - overhang_ratio: fraction of total surface area that is overhang
            - min_hole_diameter_mm: smallest detected hole diameter, or None
            - min_feature_size_mm: approximate smallest wall/thickness
            - estimated_print_time_min: rough print time estimate
            - issues: list of human-readable manufacturability warnings
            - errors: list of blocking errors
    """
    result: dict[str, Any] = {
        "valid": False,
        "bounds_mm": None,
        "volume_cm3": None,
        "surface_area_cm2": None,
        "overhangs": [],
        "overhang_area_mm2": 0.0,
        "overhang_ratio": 0.0,
        "min_hole_diameter_mm": None,
        "min_feature_size_mm": None,
        "estimated_print_time_min": None,
        "issues": [],
        "errors": [],
    }

    if stl_path is None:
        result["errors"].append("No STL file was provided.")
        return result

    stl_path = Path(stl_path)
    if not stl_path.exists():
        result["errors"].append(f"STL file not found: {stl_path}")
        return result

    try:
        mesh = trimesh.load_mesh(str(stl_path))
    except Exception as exc:
        result["errors"].append(f"Failed to load STL: {exc}")
        return result

    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            mesh = next(iter(mesh.geometry.values()))
        else:
            result["errors"].append("STL contains multiple bodies; manufacturing report not supported for scenes.")
            return result

    if mesh.extents is not None:
        result["bounds_mm"] = tuple(float(x) for x in mesh.extents)
    if mesh.volume is not None and mesh.volume > 0:
        result["volume_cm3"] = round(mesh.volume / 1000.0, 4)
    if mesh.area is not None and mesh.area > 0:
        result["surface_area_cm2"] = round(mesh.area / 100.0, 4)

    result["valid"] = result["bounds_mm"] is not None and result["volume_cm3"] is not None

    if not result["valid"]:
        result["errors"].append("Could not compute model bounds or volume.")
        return result

    # Overhang analysis: faces whose normal points downward enough and whose
    # centroid is not sitting directly on the build plate (lowest Z). The build
    # plate itself is supported, so it is not a printability issue.
    threshold = math.cos(math.radians(90.0 - overhang_angle_deg))  # sin(angle_from_horizontal)
    face_normals = mesh.face_normals
    face_centroids = mesh.triangles_center
    min_z = float(mesh.vertices[:, 2].min())
    z_tolerance = 0.01  # mm

    # Face points downward more than the threshold angle.
    cos_to_z = face_normals[:, 2]
    downward_mask = cos_to_z < -threshold
    # Not sitting on the build plate.
    above_plate_mask = face_centroids[:, 2] > min_z + z_tolerance
    overhang_mask = downward_mask & above_plate_mask
    overhang_faces = np.where(overhang_mask)[0].tolist()

    if len(overhang_faces) > 0:
        face_areas = mesh.area_faces
        overhang_area = float(face_areas[overhang_mask].sum())
        result["overhangs"] = overhang_faces
        result["overhang_area_mm2"] = round(overhang_area, 4)
        result["overhang_ratio"] = round(overhang_area / mesh.area, 4) if mesh.area > 0 else 0.0

    # Hole / thin feature detection via edges.
    edges = mesh.edges_unique
    if len(edges) > 0:
        edge_lengths = np.linalg.norm(
            mesh.vertices[edges[:, 1]] - mesh.vertices[edges[:, 0]], axis=1
        )
        result["min_feature_size_mm"] = round(float(np.min(edge_lengths)), 4)

        # Hole diameter estimation: take horizontal cross-sections and look for
    # closed interior loops (holes). The smallest hole diameter is reported.
    min_diameter = _estimate_min_hole_diameter(mesh)
    if min_diameter is not None:
        result["min_hole_diameter_mm"] = round(min_diameter, 4)

    # Basic print-time heuristic.
    if result["volume_cm3"] is not None and result["bounds_mm"] is not None:
        volume_mm3 = result["volume_cm3"] * 1000.0
        height_mm = result["bounds_mm"][2]
        num_layers = max(1, int(height_mm / layer_height_mm))
        # Simplified: per-layer area * number of layers / speed, plus shell time.
        # This is intentionally rough; real slicers do much more work.
        avg_cross_section_mm2 = volume_mm3 / max(height_mm, layer_height_mm)
        shell_perimeter_mm = 2.0 * (result["bounds_mm"][0] + result["bounds_mm"][1])
        infill_time_s = (avg_cross_section_mm2 * num_layers * layer_height_mm) / print_speed_mm_s
        shell_time_s = (shell_perimeter_mm * num_layers * layer_height_mm) / print_speed_mm_s
        total_time_min = (infill_time_s + shell_time_s) / 60.0
        result["estimated_print_time_min"] = round(max(total_time_min, 1.0), 1)

    # Issue flags.
    if result["overhang_ratio"] > 0.05:
        result["issues"].append(
            f"{result['overhang_ratio'] * 100:.1f}% of surface area is overhang above {overhang_angle_deg}° — supports likely needed."
        )

    min_dim = min(result["bounds_mm"])
    if min_dim < 0.5:
        result["issues"].append(f"Smallest bounding-box dimension is {min_dim:.2f} mm — very thin features may fail to print.")

    if result["min_hole_diameter_mm"] is not None and result["min_hole_diameter_mm"] < 2.0:
        result["issues"].append(
            f"Detected hole diameter ~{result['min_hole_diameter_mm']:.2f} mm — may be too small for FDM without clearance."
        )

    if result["min_feature_size_mm"] is not None and result["min_feature_size_mm"] < 0.5:
        result["issues"].append(
            f"Minimum detected feature size ~{result['min_feature_size_mm']:.2f} mm — check printer resolution."
        )

    return result
