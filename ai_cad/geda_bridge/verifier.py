"""Verify a GEDA Bridge simulation bundle before it is handed to a simulator."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from ai_cad.geda_bridge.models import BundleManifest, BundleVerification


def _is_positive_definite(tensor: tuple[float, float, float, float, float, float]) -> bool:
    """Check that a symmetric inertia tensor (Ixx, Iyy, Izz, Ixy, Ixz, Iyz) is positive-definite."""
    ixx, iyy, izz, ixy, ixz, iyz = tensor
    M = np.array([
        [ixx, ixy, ixz],
        [ixy, iyy, iyz],
        [ixz, iyz, izz],
    ])
    return bool(np.all(np.linalg.eigvals(M) > 0))


def _com_inside_hull(mesh_m: trimesh.Trimesh, com: tuple[float, float, float]) -> bool:
    """Check whether the center of mass lies inside the convex hull of the mesh."""
    if len(mesh_m.vertices) < 4:
        return False
    hull = mesh_m.convex_hull
    contains = hull.contains([com])
    return bool(contains[0]) if len(contains) > 0 else False


def verify_bundle(bundle_dir: Path) -> BundleVerification:
    """Run sanity checks on every mesh and inertial block in a bundle."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / "manifest.json"
    verification = BundleVerification()

    if not manifest_path.exists():
        verification.errors.append("manifest.json not found in bundle.")
        return verification

    try:
        manifest = BundleManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as exc:
        verification.errors.append(f"Failed to parse manifest.json: {exc}")
        return verification

    watertight_count = 0
    mass_positive_count = 0
    inertia_positive_count = 0
    com_inside_count = 0

    for part in manifest.parts:
        mesh_path = bundle_dir / part.mesh_file
        if not mesh_path.exists():
            verification.errors.append(f"Mesh missing for part '{part.name}': {part.mesh_file}")
            continue

        try:
            mesh = trimesh.load_mesh(mesh_path)
            if isinstance(mesh, trimesh.Scene):
                if len(mesh.geometry) == 1:
                    mesh = next(iter(mesh.geometry.values()))
                else:
                    verification.errors.append(f"Part '{part.name}' mesh contains multiple bodies.")
                    continue
        except Exception as exc:
            verification.errors.append(f"Failed to load mesh for '{part.name}': {exc}")
            continue

        if mesh.is_watertight:
            watertight_count += 1
        else:
            verification.warnings.append(f"Part '{part.name}' mesh is not watertight.")

        if part.inertial.mass_kg > 0:
            mass_positive_count += 1
        else:
            verification.errors.append(f"Part '{part.name}' mass is not positive ({part.inertial.mass_kg}).")

        if _is_positive_definite(part.inertial.inertia_tensor_kg_m2):
            inertia_positive_count += 1
        else:
            verification.errors.append(f"Part '{part.name}' inertia tensor is not positive-definite.")

        # CoM check requires meter-scale mesh; STL is already exported in meters.
        if _com_inside_hull(mesh, part.inertial.center_of_mass_m):
            com_inside_count += 1
        else:
            verification.warnings.append(f"Part '{part.name}' CoM lies outside convex hull.")

    n = len(manifest.parts)
    verification.all_watertight = watertight_count == n
    verification.all_masses_positive = mass_positive_count == n
    verification.all_inertia_positive_definite = inertia_positive_count == n
    verification.all_com_inside_hull = com_inside_count == n
    verification.valid = (
        verification.all_watertight
        and verification.all_masses_positive
        and verification.all_inertia_positive_definite
        and verification.all_com_inside_hull
        and len(verification.errors) == 0
    )

    return verification
