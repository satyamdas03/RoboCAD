"""Electronics and mechatronics co-design analysis for RoboCAD Phase 21.

Provides lightweight reports for PCB/enclosure/connector/cable-channel/fan-mount
stacks, plus IDF (Intermediate Data Format) export for downstream ECAD/MCAD
workflow.  Full silicon EDA (SPICE, lithography, placement-and-route) is
intentionally out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import warnings

import numpy as np
import trimesh

from ai_cad.assembly import compute_instance_transforms
from ai_cad.feature_tree import FeatureTree, Instance, Part, PCBOutline
from ai_cad.geda_bridge.exporter import _build_part_mesh


@dataclass
class ComponentPlacement:
    """A single placed component in the electronics stack."""

    instance_id: str
    part_id: str
    name: str | None
    translation_mm: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    package_name: str
    footprint_mm2: float | None

    def model_dump(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "part_id": self.part_id,
            "name": self.name,
            "translation_mm": self.translation_mm,
            "rotation_deg": self.rotation_deg,
            "package_name": self.package_name,
            "footprint_mm2": self.footprint_mm2,
        }


@dataclass
class PCBInfo:
    """Summary derived from a ``PCBOutline`` feature or a generated PCB part."""

    part_id: str | None
    board_length_mm: float | None
    board_width_mm: float | None
    board_thickness_mm: float
    board_area_mm2: float
    mounting_hole_count: int
    mounting_hole_diameter_mm: float | None
    keepout_count: int
    connector_count: int
    layer_count: int

    def model_dump(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "board_length_mm": self.board_length_mm,
            "board_width_mm": self.board_width_mm,
            "board_thickness_mm": self.board_thickness_mm,
            "board_area_mm2": round(self.board_area_mm2, 4),
            "mounting_hole_count": self.mounting_hole_count,
            "mounting_hole_diameter_mm": self.mounting_hole_diameter_mm,
            "keepout_count": self.keepout_count,
            "connector_count": self.connector_count,
            "layer_count": self.layer_count,
        }


@dataclass
class ElectronicsReport:
    """Result of running electronics analysis on a ``FeatureTree``."""

    design_id: str
    pcb: PCBInfo | None
    component_count: int
    components: list[ComponentPlacement]
    bounding_box_mm: dict[str, float]
    total_volume_mm3: float
    enclosure_internal_volume_mm3: float | None
    estimated_cable_length_mm: float
    warnings: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "pcb": self.pcb.model_dump() if self.pcb else None,
            "component_count": self.component_count,
            "components": [c.model_dump() for c in self.components],
            "bounding_box_mm": self.bounding_box_mm,
            "total_volume_mm3": round(self.total_volume_mm3, 4),
            "enclosure_internal_volume_mm3": self.enclosure_internal_volume_mm3,
            "estimated_cable_length_mm": round(self.estimated_cable_length_mm, 4),
            "warnings": self.warnings,
        }


def _shoelace_area(points: list[tuple[float, float]]) -> float:
    """Signed polygon area; positive for CCW, absolute value returned."""
    if len(points) < 3:
        return 0.0
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _bounding_box_from_vertices(vertices: np.ndarray) -> dict[str, float]:
    """Return min/max extents from an Nx3 vertex array."""
    if vertices.size == 0:
        return {"min_x": 0.0, "min_y": 0.0, "min_z": 0.0,
                "max_x": 0.0, "max_y": 0.0, "max_z": 0.0}
    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    return {
        "min_x": float(mins[0]),
        "min_y": float(mins[1]),
        "min_z": float(mins[2]),
        "max_x": float(maxs[0]),
        "max_y": float(maxs[1]),
        "max_z": float(maxs[2]),
    }


def _extract_pcb_info(part: Part) -> PCBInfo | None:
    """Derive PCB summary from an explicit ``PCBOutline`` feature."""
    for feature in part.features:
        if isinstance(feature, PCBOutline):
            shape = feature.board_shape
            xs = [p[0] for p in shape]
            ys = [p[1] for p in shape]
            length = max(xs) - min(xs) if xs else None
            width = max(ys) - min(ys) if ys else None
            hole_diams: list[float] = []
            for h in feature.mounting_holes:
                if len(h) >= 3:
                    hole_diams.append(float(h[2]))
            return PCBInfo(
                part_id=part.id,
                board_length_mm=length,
                board_width_mm=width,
                board_thickness_mm=feature.board_thickness,
                board_area_mm2=_shoelace_area(shape),
                mounting_hole_count=len(feature.mounting_holes),
                mounting_hole_diameter_mm=float(np.mean(hole_diams)) if hole_diams else None,
                keepout_count=len(feature.keepouts),
                connector_count=len(feature.connector_positions),
                layer_count=feature.layer_count,
            )
    return None


def _part_footprint_from_mesh(mesh: trimesh.Trimesh) -> float | None:
    """Estimate XY footprint from a mesh's axis-aligned bounding box."""
    bounds = mesh.bounds
    if bounds is None:
        return None
    return float((bounds[1, 0] - bounds[0, 0]) * (bounds[1, 1] - bounds[0, 1]))


def _package_name_for_part(part_id: str) -> str:
    """Simple IDF package naming convention."""
    return f"PKG_{part_id.upper()}"


def run_electronics_analysis(
    tree: FeatureTree,
    output_dir: Path,
    *,
    tolerance: float = 0.1,
) -> ElectronicsReport:
    """Analyse an electronics/mechatronics ``FeatureTree``.

    Builds per-part meshes, computes stack bounding box and volume, extracts
    PCB information, and estimates a simple cable-run length from component
    placements.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parameters = tree.parameter_dict()
    assembly = tree.assemblies[0] if tree.assemblies else None
    transforms: dict[str, np.ndarray] = {}
    if assembly:
        transforms = compute_instance_transforms(tree, assembly, parameters)

    mesh_cache: dict[str, trimesh.Trimesh] = {}
    placed_meshes: list[tuple[str, trimesh.Trimesh]] = []
    components: list[ComponentPlacement] = []
    pcb: PCBInfo | None = None
    enclosure_volume: float | None = None
    warnings_list: list[str] = []

    instances = assembly.instances if assembly else []
    for inst in instances:
        part = tree.find_part(inst.part_id)
        if part is None:
            warnings_list.append(f"Instance {inst.id} references missing part {inst.part_id}")
            continue

        # Cache + transform mesh.
        try:
            if part.id not in mesh_cache:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    mesh_cache[part.id] = _build_part_mesh(
                        part, parameters, output_dir, tolerance=tolerance
                    )
            mesh = mesh_cache[part.id].copy()
        except Exception as exc:
            warnings_list.append(f"Failed to build mesh for '{part.id}': {exc}")
            continue

        M = transforms.get(inst.id, np.eye(4))
        mesh.apply_transform(M)
        placed_meshes.append((inst.id, mesh))

        # Extract PCB info from the original part, not the transformed mesh.
        if part.id in ("pcb", "main_pcb") and pcb is None:
            pcb = _extract_pcb_info(part)
            if pcb is None:
                # Synthesised PCB with no explicit outline: derive from mesh.
                b = mesh.bounds
                pcb = PCBInfo(
                    part_id=part.id,
                    board_length_mm=float(b[1, 0] - b[0, 0]) if b is not None else None,
                    board_width_mm=float(b[1, 1] - b[0, 1]) if b is not None else None,
                    board_thickness_mm=float(b[1, 2] - b[0, 2]) if b is not None else 1.6,
                    board_area_mm2=_part_footprint_from_mesh(mesh) or 0.0,
                    mounting_hole_count=0,
                    mounting_hole_diameter_mm=None,
                    keepout_count=0,
                    connector_count=0,
                    layer_count=2,
                )

        if part.id == "enclosure":
            enclosure_volume = float(mesh.volume) if mesh.is_watertight else None

        # Component placement record.
        t = M[:3, 3]
        rot = _matrix_to_euler(M[:3, :3])
        components.append(
            ComponentPlacement(
                instance_id=inst.id,
                part_id=part.id,
                name=inst.name or part.id,
                translation_mm=(round(float(t[0]), 4), round(float(t[1]), 4), round(float(t[2]), 4)),
                rotation_deg=rot,
                package_name=_package_name_for_part(part.id),
                footprint_mm2=_part_footprint_from_mesh(mesh),
            )
        )

    # Whole-system bounding box + volume.
    if placed_meshes:
        all_vertices = np.vstack([m.vertices for _, m in placed_meshes])
        bbox = _bounding_box_from_vertices(all_vertices)
        total_volume = sum(float(m.volume) if m.is_watertight else 0.0 for _, m in placed_meshes)
    else:
        bbox = _bounding_box_from_vertices(np.zeros((0, 3)))
        total_volume = 0.0

    # Simple cable-length heuristic: sum of pairwise XY distances for placed
    # components that look like connectors or cable channels.
    cable_points: list[tuple[float, float]] = [
        c.translation_mm[:2]
        for c in components
        if c.part_id in ("connector", "cable_channel", "fan_mount")
    ]
    cable_length = 0.0
    for i in range(len(cable_points) - 1):
        p1 = np.array(cable_points[i])
        p2 = np.array(cable_points[i + 1])
        cable_length += float(np.linalg.norm(p2 - p1))

    return ElectronicsReport(
        design_id=tree.design_id,
        pcb=pcb,
        component_count=len(components),
        components=components,
        bounding_box_mm=bbox,
        total_volume_mm3=total_volume,
        enclosure_internal_volume_mm3=enclosure_volume,
        estimated_cable_length_mm=cable_length,
        warnings=warnings_list,
    )


def _matrix_to_euler(R: np.ndarray) -> tuple[float, float, float]:
    """Tait-Bryan XYZ Euler angles in degrees from a rotation matrix."""
    sy = np.sqrt(float(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0]))
    if sy > 1e-6:
        x = np.arctan2(R[2, 1], R[2, 2])
        y = np.arctan2(-R[2, 0], sy)
        z = np.arctan2(R[1, 0], R[0, 0])
    else:
        x = np.arctan2(-R[1, 2], R[1, 1])
        y = np.arctan2(-R[2, 0], sy)
        z = 0.0
    return (
        round(float(np.degrees(x)), 4),
        round(float(np.degrees(y)), 4),
        round(float(np.degrees(z)), 4),
    )


def _find_pcb_outline(tree: FeatureTree) -> PCBOutline | None:
    """Return the first ``PCBOutline`` feature found in the tree."""
    for part in tree.parts:
        for feature in part.features:
            if isinstance(feature, PCBOutline):
                return feature
    return None


def _part_mesh_bounds(
    tree: FeatureTree,
    output_dir: Path,
    parameters: dict[str, Any],
    part_id: str,
) -> np.ndarray | None:
    """Return a part's axis-aligned bounding box (2x3) from its generated mesh."""
    part = tree.find_part(part_id)
    if part is None:
        return None
    try:
        mesh = _build_part_mesh(part, parameters, output_dir)
        return mesh.bounds
    except Exception:
        return None


def export_idf(
    tree: FeatureTree,
    output_dir: Path,
    design_id: str,
    *,
    board_name: str = "ROBOCAD_PCB",
    units: str = "MM",
    tolerance: float = 0.1,
) -> dict[str, Path]:
    """Export an IDF v3.0 board file (.emn) and package library (.emp).

    Also writes a minimal ISO-10303-21 STEP placeholder (.step) so downstream
    MCAD tools have a companion solid file.  The IDF files are textual and
    can be validated with a simple line-based parser.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parameters = tree.parameter_dict()

    emn_path = output_dir / f"{design_id}.emn"
    emp_path = output_dir / f"{design_id}.emp"
    step_path = output_dir / f"{design_id}.step"

    pcb = _find_pcb_outline(tree)
    if pcb is None:
        # Fallback: try to derive from a generated pcb part.
        pcb_bounds = _part_mesh_bounds(tree, output_dir, parameters, "pcb")
        if pcb_bounds is not None:
            xmin, ymin, _ = pcb_bounds[0]
            xmax, ymax, _ = pcb_bounds[1]
            pcb = PCBOutline(
                id="pcb_fallback",
                board_shape=[
                    (float(xmin), float(ymin)),
                    (float(xmax), float(ymin)),
                    (float(xmax), float(ymax)),
                    (float(xmin), float(ymax)),
                ],
                board_thickness=float(pcb_bounds[1, 2] - pcb_bounds[0, 2]),
            )
        else:
            raise ValueError(
                "Cannot export IDF: FeatureTree has no PCBOutline and no 'pcb' part."
            )

    # Board file (.emn)
    emn_lines = [
        ".BOARD_OUTLINE EMCIDF",
        f"{units}",
        f"{board_name}",
        f"{len(pcb.board_shape)}",
    ]
    for x, y in pcb.board_shape:
        emn_lines.append(f"{x:.6f} {y:.6f}")
    emn_lines.append(f"{pcb.board_thickness:.6f}")
    # Mounting holes as drilled holes.
    emn_lines.append(f"{len(pcb.mounting_holes)}")
    for h in pcb.mounting_holes:
        x, y, d = h
        emn_lines.append(f"DRILL {x:.6f} {y:.6f} {d:.6f}")
    # Placed components from the first assembly.
    emn_lines.append(".PLACEMENT")
    assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly:
        transforms = compute_instance_transforms(tree, assembly, parameters)
        for inst in assembly.instances:
            if inst.part_id == "pcb":
                continue
            M = transforms.get(inst.id, np.eye(4))
            tx, ty, tz = M[:3, 3]
            rot = _matrix_to_euler(M[:3, :3])
            pkg = _package_name_for_part(inst.part_id)
            emn_lines.append(
                f"{inst.id} {pkg} {tx:.6f} {ty:.6f} {tz:.6f} {rot[0]:.4f} {rot[1]:.4f} {rot[2]:.4f}"
            )
    emn_lines.append(".END_PLACEMENT")
    emn_lines.append(".END_BOARD_OUTLINE")
    emn_path.write_text("\n".join(emn_lines) + "\n", encoding="utf-8")

    # Package library (.emp) — one package per non-pcb part.
    emp_lines = [".ELECTRICAL_MECHANICAL_DATA", units]
    unique_parts = {
        inst.part_id for inst in (assembly.instances if assembly else [])
    } - {"pcb"}
    for part_id in sorted(unique_parts):
        part = tree.find_part(part_id)
        if part is None:
            continue
        bounds = _part_mesh_bounds(tree, output_dir, parameters, part_id)
        if bounds is None:
            continue
        lx = float(bounds[1, 0] - bounds[0, 0])
        ly = float(bounds[1, 1] - bounds[0, 1])
        lz = float(bounds[1, 2] - bounds[0, 2])
        pkg = _package_name_for_part(part_id)
        emp_lines.append(f".PACKAGE {pkg}")
        emp_lines.append(f"{lx:.6f} {ly:.6f} {lz:.6f}")
        emp_lines.append("0 0")
        emp_lines.append(".END_PACKAGE")
    emp_lines.append(".END_ELECTRICAL_MECHANICAL_DATA")
    emp_path.write_text("\n".join(emp_lines) + "\n", encoding="utf-8")

    # Minimal STEP placeholder.
    step_lines = [
        "ISO-10303-21;",
        "HEADER;",
        f"FILE_DESCRIPTION(('RoboCAD IDF companion STEP for {design_id}'), '2;1');",
        "FILE_NAME('companion.step', '', (), (), '', '', '');",
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 3 1 1 }'));",
        "ENDSEC;",
        "DATA;",
        "#1 = CARTESIAN_POINT('', (0.0, 0.0, 0.0));",
        "#2 = DIRECTION('', (0.0, 0.0, 1.0));",
        "#3 = DIRECTION('', (1.0, 0.0, 0.0));",
        "#4 = AXIS2_PLACEMENT_3D('', #1, #2, #3);",
        "ENDSEC;",
        "END-ISO-10303-21;",
    ]
    step_path.write_text("\n".join(step_lines) + "\n", encoding="utf-8")

    return {"emn": emn_path, "emp": emp_path, "step": step_path}
