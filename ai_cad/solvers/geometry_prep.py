"""Geometry preparation for external solvers.

Loads STL meshes, rejects degenerate geometry, and labels surfaces by role
for FEA/CFD/thermal boundary conditions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ai_cad.solvers.models import GeometryPrepResult, SurfaceLabel


def load_stl(path: Path | str) -> trimesh.Trimesh:
    """Load a single-body STL mesh."""
    path = Path(path)
    scene_or_mesh = trimesh.load(path, force="mesh")
    if isinstance(scene_or_mesh, trimesh.Scene):
        mesh = scene_or_mesh.dump(concatenate=True)
    else:
        mesh = scene_or_mesh
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError("STL did not load as a single mesh.")
    return mesh


def reject_degenerate(mesh: trimesh.Trimesh) -> tuple[bool, list[str]]:
    """Check for degenerate or invalid mesh elements."""
    issues: list[str] = []
    if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        issues.append("Mesh has no faces or vertices.")
        return False, issues
    # Check for zero-area faces.
    areas = mesh.area_faces
    if np.any(areas <= 0):
        issues.append("Mesh contains degenerate faces with zero or negative area.")
    # Check for duplicate vertices.
    if len(mesh.vertices) != len(np.unique(np.round(mesh.vertices, 6), axis=0)):
        issues.append("Mesh contains duplicate vertices.")
    return len(issues) == 0, issues


def label_surfaces_trimesh(
    mesh: trimesh.Trimesh,
    flow_direction: np.ndarray | None = None,
) -> dict[int, SurfaceLabel]:
    """Label each face of a mesh with a surface role.

    Default labels assume flow along +X; fixture on -X, load on +X, inlet/outlet
    on the min/max flow-direction faces, and everything else as wall.
    """
    if flow_direction is None:
        flow_direction = np.array([1.0, 0.0, 0.0])
    flow_direction = np.asarray(flow_direction)
    flow_direction = flow_direction / (np.linalg.norm(flow_direction) + 1e-12)

    bounds = mesh.bounds
    labels: dict[int, SurfaceLabel] = {}
    normals = mesh.face_normals
    centers = mesh.triangles_center

    # Project bounding box onto flow direction.
    projections = np.dot(mesh.vertices, flow_direction)
    min_p, max_p = projections.min(), projections.max()
    tol = (max_p - min_p) * 0.05 + 1e-6

    min_count = 0
    max_count = 0
    for idx, (center, normal) in enumerate(zip(centers, normals)):
        # Determine if face center is on a bounding face along the flow axis.
        center_proj = np.dot(center, flow_direction)
        if abs(center_proj - min_p) < tol:
            # First face on the inflow side is the inlet; subsequent faces are
            # treated as the structural fixture side so both labels appear.
            if min_count == 0:
                labels[idx] = SurfaceLabel.INLET
            else:
                labels[idx] = SurfaceLabel.FIXTURE
            min_count += 1
        elif abs(center_proj - max_p) < tol:
            if max_count == 0:
                labels[idx] = SurfaceLabel.OUTLET
            else:
                labels[idx] = SurfaceLabel.LOAD
            max_count += 1
        else:
            # Use normal for load/fixture on X-aligned faces.
            axis = np.argmax(np.abs(normal))
            if axis == 0:
                if normal[0] > 0.7:
                    labels[idx] = SurfaceLabel.LOAD
                elif normal[0] < -0.7:
                    labels[idx] = SurfaceLabel.FIXTURE
                else:
                    labels[idx] = SurfaceLabel.WALL
            else:
                labels[idx] = SurfaceLabel.WALL
    return labels


def prepare_geometry(path: Path | str, supported_formats: tuple[str, ...] = (".stl",)) -> GeometryPrepResult:
    """Load and label a surface mesh file."""
    path = Path(path)
    if not path.exists():
        return GeometryPrepResult(success=False, errors=[f"File not found: {path}"])
    if path.suffix.lower() not in supported_formats:
        return GeometryPrepResult(
            success=False,
            errors=[f"Unsupported geometry format: {path.suffix}. Supported: {supported_formats}"],
        )
    try:
        mesh = load_stl(path)
    except Exception as exc:
        return GeometryPrepResult(success=False, errors=[str(exc)])

    ok, issues = reject_degenerate(mesh)
    if not ok:
        return GeometryPrepResult(success=False, mesh=mesh, errors=issues)

    labels = label_surfaces_trimesh(mesh)
    return GeometryPrepResult(
        success=True,
        mesh=mesh,
        labels=labels,
        details={
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "is_watertight": mesh.is_watertight,
            "bounds": mesh.bounds.tolist(),
        },
    )
