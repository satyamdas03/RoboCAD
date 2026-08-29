"""Assembly-level collision and clearance checks for RoboCAD Phase 19.

Builds per-instance trimesh meshes from a FeatureTree, places them by the
assembly's computed instance transforms, and runs pairwise proximity queries
plus optional boolean intersection to estimate overlap volume.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ai_cad.assembly import compute_instance_transforms
from ai_cad.feature_tree import FeatureTree


@dataclass
class CollisionReport:
    """Result of a pairwise assembly collision / clearance check."""

    name: str
    instance_a: str
    instance_b: str
    min_clearance_mm: float
    max_clearance_mm: float | None
    mean_clearance_mm: float | None
    interference_volume_mm3: float | None
    classification: str  # "clearance", "transition", "interference", "unknown"
    details: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "instance_a": self.instance_a,
            "instance_b": self.instance_b,
            "min_clearance_mm": self.min_clearance_mm,
            "max_clearance_mm": self.max_clearance_mm,
            "mean_clearance_mm": self.mean_clearance_mm,
            "interference_volume_mm3": self.interference_volume_mm3,
            "classification": self.classification,
            "details": self.details,
        }


def _sample_signed_distances(
    mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh, samples: int
) -> np.ndarray:
    """Return signed clearances from points on A to mesh B, then B to A.

    Uses the standard clearance convention: positive means the sampled point
    is outside the other mesh (clearance), negative means it is inside
    (interference). Sampling both directions catches cases where one body is
    fully enclosed by the other.
    """
    results: list[np.ndarray] = []
    for src, dst in ((mesh_a, mesh_b), (mesh_b, mesh_a)):
        try:
            points = src.sample(samples)
        except Exception:
            continue
        try:
            unsigned = dst.nearest.on_surface(points)[1]
        except Exception:
            continue
        try:
            inside = dst.contains(points)
            signed = np.where(inside, -unsigned, unsigned)
        except Exception:
            signed = unsigned
        results.append(np.asarray(signed, dtype=float))
    if not results:
        return np.array([], dtype=float)
    return np.concatenate(results)


def _boolean_intersection_volume(
    mesh_a: trimesh.Trimesh, mesh_b: trimesh.Trimesh
) -> float | None:
    """Estimate overlap volume via trimesh boolean intersection."""
    try:
        if mesh_a.is_watertight and mesh_b.is_watertight:
            intersection = mesh_a.intersection(mesh_b)
            if intersection is not None and hasattr(intersection, "volume"):
                return float(intersection.volume)
    except Exception:
        return None
    return None


def check_assembly_collision(
    tree: FeatureTree,
    output_dir: Path,
    *,
    name: str = "assembly_collision",
    clearance_threshold_mm: float = 0.05,
    interference_threshold_mm: float = -0.05,
    samples: int = 2000,
    tolerance: float = 0.1,
) -> list[CollisionReport]:
    """Check collision/clearance between every unique pair of assembly instances.

    Args:
        tree: FeatureTree containing parts and an assembly.
        output_dir: directory used to execute per-part build123d code and cache
            generated STL meshes.
        name: identifier prefix for reports.
        clearance_threshold_mm: minimum positive clearance to classify as
            "clearance".
        interference_threshold_mm: maximum negative clearance to classify as
            "interference".
        samples: number of surface points to sample per mesh for the proximity
            query.
        tolerance: tessellation tolerance passed to the mesh generator.

    Returns:
        A CollisionReport for every unique instance pair in the first assembly.
        Single-instance assemblies return an empty list.
    """
    from ai_cad.geda_bridge.exporter import _build_part_mesh

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not tree.assemblies:
        return []
    assembly = tree.assemblies[0]
    if len(assembly.instances) < 2:
        return []

    parameters = tree.parameter_dict()
    transforms = compute_instance_transforms(tree, assembly, parameters)

    # Cache per unique part_id. FeatureTree instances may reuse parts.
    mesh_cache: dict[str, trimesh.Trimesh] = {}
    instance_meshes: dict[str, trimesh.Trimesh] = {}
    for inst in assembly.instances:
        part = tree.find_part(inst.part_id)
        if part is None:
            continue
        if part.id not in mesh_cache:
            mesh_cache[part.id] = _build_part_mesh(
                part, parameters, output_dir, tolerance=tolerance
            )
        mesh = mesh_cache[part.id].copy()
        M = transforms.get(inst.id, np.eye(4))
        mesh.apply_transform(M)
        instance_meshes[inst.id] = mesh

    reports: list[CollisionReport] = []
    for a_id, b_id in combinations(instance_meshes.keys(), 2):
        mesh_a = instance_meshes[a_id]
        mesh_b = instance_meshes[b_id]

        try:
            distances = _sample_signed_distances(mesh_a, mesh_b, samples)
            if distances.size == 0:
                raise RuntimeError("No proximity samples returned")
            min_d = float(np.min(distances))
            max_d = float(np.max(distances))
            mean_d = float(np.mean(distances))
        except Exception as exc:
            reports.append(
                CollisionReport(
                    name=name,
                    instance_a=a_id,
                    instance_b=b_id,
                    min_clearance_mm=0.0,
                    max_clearance_mm=None,
                    mean_clearance_mm=None,
                    interference_volume_mm3=None,
                    classification="unknown",
                    details={"error": str(exc), "samples": samples},
                )
            )
            continue

        interference_volume = _boolean_intersection_volume(mesh_a, mesh_b)

        if min_d < interference_threshold_mm:
            classification = "interference"
        elif min_d < clearance_threshold_mm:
            classification = "transition"
        else:
            classification = "clearance"

        reports.append(
            CollisionReport(
                name=name,
                instance_a=a_id,
                instance_b=b_id,
                min_clearance_mm=round(min_d, 4),
                max_clearance_mm=round(max_d, 4),
                mean_clearance_mm=round(mean_d, 4),
                interference_volume_mm3=round(interference_volume, 4)
                if interference_volume is not None
                else None,
                classification=classification,
                details={
                    "clearance_threshold_mm": clearance_threshold_mm,
                    "interference_threshold_mm": interference_threshold_mm,
                    "samples": samples,
                },
            )
        )

    return reports
