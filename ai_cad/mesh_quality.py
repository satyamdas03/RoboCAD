"""Mesh-quality pre-checker for RoboCAD solver readiness.

Validates triangulated exports (STL/OBJ) before they are handed to FEA/CFD
solvers. The checks are intentionally conservative: a bad mesh fails fast
instead of crashing an external solver.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ai_cad.verification_models import MeshQualityReport


def load_mesh(stl_path: Path | str) -> trimesh.Trimesh | None:
    """Load a single-body mesh from a file path."""
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


def _bounding_box_m(mesh: trimesh.Trimesh) -> tuple[float, float, float]:
    bounds = mesh.bounds
    extents = bounds[1] - bounds[0]
    return (float(extents[0] * 1e-3), float(extents[1] * 1e-3), float(extents[2] * 1e-3))


def check_mesh_quality(
    stl_path: Path | str | trimesh.Trimesh | None,
    max_aspect_ratio: float = 30.0,
    min_bounding_box_m: float = 1e-6,
    max_bounding_box_m: float = 100.0,
) -> MeshQualityReport:
    """Run a mesh-quality pre-check.

    Args:
        stl_path: path to the mesh file (STL supported) or an already-loaded
            trimesh.Trimesh object.
        max_aspect_ratio: threshold above which a triangle is flagged.
        min_bounding_box_m: parts smaller than this are suspicious.
        max_bounding_box_m: parts larger than this are suspicious.

    Returns:
        MeshQualityReport with is_suitable_for_solver boolean and issue list.
    """
    if isinstance(stl_path, trimesh.Trimesh):
        mesh = stl_path
    elif stl_path is None:
        mesh = None
    else:
        mesh = load_mesh(stl_path)
    if mesh is None:
        return MeshQualityReport(
            is_suitable_for_solver=False,
            triangle_count=0,
            watertight=False,
            non_manifold_edges=0,
            degenerate_triangles=0,
            high_aspect_ratio_triangles=0,
            bounding_box_m=(0.0, 0.0, 0.0),
            issues=["Failed to load mesh file."],
        )

    triangle_count = int(len(mesh.faces))
    if triangle_count == 0:
        return MeshQualityReport(
            is_suitable_for_solver=False,
            triangle_count=0,
            watertight=False,
            non_manifold_edges=0,
            degenerate_triangles=0,
            high_aspect_ratio_triangles=0,
            bounding_box_m=_bounding_box_m(mesh),
            issues=["Mesh has no faces."],
        )

    watertight = bool(mesh.is_watertight)

    # Non-manifold edges: count unique edges that are not shared by exactly two faces.
    non_manifold_edges = 0
    try:
        from collections import Counter

        edge_counts = Counter(tuple(sorted(e)) for e in mesh.edges)
        non_manifold_edges = sum(1 for count in edge_counts.values() if count != 2)
    except Exception:
        non_manifold_edges = 0

    # Degenerate triangles: zero or near-zero area.
    face_areas = mesh.area_faces
    degenerate_triangles = int(np.sum(face_areas < 1e-12))

    # Aspect ratio for each face (longest edge / shortest altitude).
    v0 = mesh.vertices[mesh.faces[:, 0]]
    v1 = mesh.vertices[mesh.faces[:, 1]]
    v2 = mesh.vertices[mesh.faces[:, 2]]
    a = np.linalg.norm(v1 - v0, axis=1)
    b = np.linalg.norm(v2 - v1, axis=1)
    c = np.linalg.norm(v0 - v2, axis=1)
    # Heron's formula for area; avoid div-by-zero.
    s = (a + b + c) / 2.0
    area = np.sqrt(np.maximum(s * (s - a) * (s - b) * (s - c), 0.0))
    shortest_edge = np.minimum(np.minimum(a, b), c)
    # Aspect ratio: longest edge / (2 * area / shortest_edge) = longest * shortest / (2 * area)
    longest_edge = np.maximum(np.maximum(a, b), c)
    with np.errstate(divide="ignore", invalid="ignore"):
        aspect_ratio = np.where(area > 1e-12, (longest_edge * shortest_edge) / (2.0 * area), 0.0)
    aspect_ratio = np.nan_to_num(aspect_ratio, nan=0.0, posinf=0.0, neginf=0.0)
    high_aspect_ratio_triangles = int(np.sum(aspect_ratio > max_aspect_ratio))

    bounding_box_m = _bounding_box_m(mesh)
    max_dim = max(bounding_box_m)
    min_dim = min(bounding_box_m)

    issues: list[str] = []
    if not watertight:
        issues.append("Mesh is not watertight (has boundary edges).")
    if non_manifold_edges > 0:
        issues.append(f"Mesh has {non_manifold_edges} non-manifold edge(s).")
    if degenerate_triangles > 0:
        issues.append(f"Mesh has {degenerate_triangles} degenerate triangle(s).")
    if high_aspect_ratio_triangles > 0:
        issues.append(f"Mesh has {high_aspect_ratio_triangles} high-aspect-ratio triangle(s).")
    if max_dim > max_bounding_box_m:
        issues.append(f"Bounding box too large ({max_dim:.3f} m > {max_bounding_box_m} m).")
    if min_dim < min_bounding_box_m:
        issues.append(f"Bounding box too small ({min_dim:.6f} m < {min_bounding_box_m} m).")

    is_suitable = (
        watertight
        and non_manifold_edges == 0
        and degenerate_triangles == 0
        and high_aspect_ratio_triangles == 0
        and min_bounding_box_m <= max_dim <= max_bounding_box_m
    )

    details: dict[str, Any] = {
        "volume_m3": float(mesh.volume) if mesh.volume else None,
        "surface_area_m2": float(mesh.area) * 1e-6 if mesh.area else None,
        "max_aspect_ratio_threshold": max_aspect_ratio,
    }

    return MeshQualityReport(
        is_suitable_for_solver=is_suitable,
        triangle_count=triangle_count,
        watertight=watertight,
        non_manifold_edges=non_manifold_edges,
        degenerate_triangles=degenerate_triangles,
        high_aspect_ratio_triangles=high_aspect_ratio_triangles,
        bounding_box_m=bounding_box_m,
        issues=issues,
        details=details,
    )
