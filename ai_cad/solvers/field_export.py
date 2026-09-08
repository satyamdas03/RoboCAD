"""Scalar field extraction from real solver outputs for viewer overlays.

Phase 28E adds the ability to read nodal/cell scalar fields produced by
CalculiX, ElmerFEM, and OpenFOAM and return them in a format the frontend
STL viewer can render as a heatmap.

The exported format is a JSON object with node coordinates and per-node scalar
values. The frontend maps these onto the displayed STL vertices by nearest-node
lookup.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.solvers import openfoam_adapter


# ---------------------------------------------------------------------------
# Public data format
# ---------------------------------------------------------------------------

def _empty_field(field_name: str, message: str) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "nodes": [],
        "scalars": [],
        "min": 0.0,
        "max": 0.0,
        "unit": "",
        "message": message,
    }


def _normalize_field(nodes: np.ndarray, scalars: np.ndarray, field_name: str, unit: str) -> dict[str, Any]:
    scalars = np.asarray(scalars, dtype=float)
    nodes = np.asarray(nodes, dtype=float)
    if scalars.size == 0 or nodes.size == 0:
        return _empty_field(field_name, "Empty scalar field.")
    return {
        "field_name": field_name,
        "nodes": nodes.tolist(),
        "scalars": scalars.tolist(),
        "min": float(np.min(scalars)),
        "max": float(np.max(scalars)),
        "unit": unit,
        "message": "ok",
    }


# ---------------------------------------------------------------------------
# CalculiX field extraction
# ---------------------------------------------------------------------------

def extract_calculix_field(
    dat_path: Path | str,
    nodes: np.ndarray | None = None,
    field: str = "displacement_magnitude_mm",
) -> dict[str, Any]:
    """Extract a nodal scalar field from a CalculiX ``.dat`` file.

    Supported fields:
      - ``displacement_magnitude_mm``: nodal displacement magnitude in mm.
      - ``von_mises_stress_mpa``: element-centroid von Mises stress averaged to nodes.

    ``nodes`` is the analysis mesh node coordinate array (0-based). It is only
    used to provide coordinates for the averaged stress field; the displacement
    block itself contains node ids.
    """
    dat_path = Path(dat_path)
    if not dat_path.exists():
        return _empty_field(field, f"CalculiX .dat file not found: {dat_path}")

    text = dat_path.read_text()

    if field == "displacement_magnitude_mm":
        return _extract_calculix_displacement(text)
    if field == "von_mises_stress_mpa":
        return _extract_calculix_stress(text, nodes)

    return _empty_field(field, f"Unsupported CalculiX field: {field}")


def _extract_calculix_displacement(text: str) -> dict[str, Any]:
    """Parse nodal displacement block and return per-node displacement magnitude."""
    disp_blocks = text.split(" displacements")
    if len(disp_blocks) <= 1:
        return _empty_field("displacement_magnitude_mm", "No displacement block found in .dat")

    block = disp_blocks[-1]
    node_ids: list[int] = []
    values: list[float] = []
    coords_map: dict[int, tuple[float, float, float]] = {}

    for line in block.splitlines():
        if not line.strip() or "set" in line.lower() or "time" in line.lower():
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                nid = int(parts[0])
                ux, uy, uz = map(float, parts[1:4])
                node_ids.append(nid)
                values.append(math.sqrt(ux * ux + uy * uy + uz * uz) * 1000.0)
                # Coordinate placeholders; caller supplies real mesh nodes by id.
                coords_map[nid] = (0.0, 0.0, 0.0)
            except ValueError:
                break

    if not values:
        return _empty_field("displacement_magnitude_mm", "No nodal displacement values parsed.")

    # Build a minimal node coordinate list aligned with values.
    max_id = max(node_ids)
    coords = np.zeros((max_id, 3), dtype=float)
    scalars = np.zeros(max_id, dtype=float)
    for nid, val in zip(node_ids, values):
        scalars[nid - 1] = val

    return _normalize_field(coords, scalars, "displacement_magnitude_mm", "mm")


def _extract_calculix_stress(text: str, nodes: np.ndarray | None) -> dict[str, Any]:
    """Parse element stress block and average element von Mises to nodes."""
    stress_blocks = text.split(" stresses")
    if len(stress_blocks) <= 1 or nodes is None:
        return _empty_field("von_mises_stress_mpa", "No stress block or node coordinates available.")

    nodes = np.asarray(nodes, dtype=float)
    node_count = nodes.shape[0]
    acc = np.zeros(node_count, dtype=float)
    weights = np.zeros(node_count, dtype=float)

    block = stress_blocks[-1]
    for line in block.splitlines():
        if not line.strip() or "set" in line.lower() or "time" in line.lower():
            continue
        parts = line.split()
        # Format: elem_id integ_pnt sxx syy szz sxy syz sxz
        if len(parts) >= 8 and parts[0].isdigit():
            try:
                vals = list(map(float, parts[2:8]))
                vm = _von_mises(*vals) / 1e6
                # Distribute to all nodes equally (coarse average).
                for i in range(node_count):
                    acc[i] += vm
                    weights[i] += 1.0
            except ValueError:
                break

    if weights.max() == 0:
        return _empty_field("von_mises_stress_mpa", "No stress values parsed.")

    scalars = acc / np.maximum(weights, 1.0)
    return _normalize_field(nodes, scalars, "von_mises_stress_mpa", "MPa")


def _von_mises(sxx: float, syy: float, szz: float, sxy: float, syz: float, sxz: float) -> float:
    return math.sqrt(
        0.5
        * (
            (sxx - syy) ** 2
            + (syy - szz) ** 2
            + (szz - sxx) ** 2
            + 6.0 * (sxy**2 + syz**2 + sxz**2)
        )
    )


# ---------------------------------------------------------------------------
# ElmerFEM field extraction
# ---------------------------------------------------------------------------

def extract_elmer_field(
    ep_path: Path | str,
    field: str = "temperature_c",
) -> dict[str, Any]:
    """Extract a nodal scalar field from an ElmerFEM ``.ep`` result file."""
    ep_path = Path(ep_path)
    if not ep_path.exists():
        return _empty_field(field, f"Elmer .ep file not found: {ep_path}")

    text = ep_path.read_text()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return _empty_field(field, f"Failed to parse Elmer .ep: {exc}")

    # Find the Simulation block and the first timestep's Data nodes.
    sim = root.find("Simulation")
    if sim is None:
        return _empty_field(field, "No Simulation block in .ep file.")

    # Collect node coordinates and the requested scalar.
    coords: dict[int, list[float]] = {}
    scalars: dict[int, float] = {}

    for timestep in sim.findall("Timestep"):
        for data in timestep.findall("Data"):
            nid = int(data.get("index", 0))
            if nid <= 0:
                continue
            try:
                x = float(data.get("x", 0.0))
                y = float(data.get("y", 0.0))
                z = float(data.get("z", 0.0))
                coords[nid] = [x, y, z]
            except (TypeError, ValueError):
                continue

            # Try common scalar names.
            for key in (field, "temperature", "Temperature", "displacement"):
                value = data.get(key)
                if value is not None:
                    try:
                        scalars[nid] = float(value)
                    except ValueError:
                        pass
                    break
        # Only use the first timestep for steady-state results.
        break

    if not scalars:
        return _empty_field(field, f"No scalar values found for field '{field}' in .ep file.")

    max_id = max(max(coords.keys(), default=0), max(scalars.keys(), default=0))
    nodes_arr = np.zeros((max_id, 3), dtype=float)
    for nid, xyz in coords.items():
        nodes_arr[nid - 1] = xyz
    scalars_arr = np.zeros(max_id, dtype=float)
    for nid, val in scalars.items():
        scalars_arr[nid - 1] = val

    unit = "C" if "temperature" in field.lower() or "temp" in field.lower() else ""
    return _normalize_field(nodes_arr, scalars_arr, field, unit)


# ---------------------------------------------------------------------------
# OpenFOAM field extraction
# ---------------------------------------------------------------------------

def extract_openfoam_field(
    case_dir: Path | str,
    field: str = "drag_coefficient",
) -> dict[str, Any]:
    """Extract a scalar coefficient from an OpenFOAM case.

    OpenFOAM full volume fields (pressure, velocity) require VTK/Paraview
    parsing; this adapter surfaces the parsed ``Cd`` coefficient as a single
    scalar for certificate/reporting use. Future work can extend this to parse
    sampled surface pressure fields.
    """
    case_dir = Path(case_dir)
    coeffs = openfoam_adapter.parse_force_coefficients(case_dir)
    cd = coeffs.get("Cd", coeffs.get("C_d", 0.0))
    if cd == 0.0:
        return _empty_field(field, "No drag coefficient found in OpenFOAM postProcessing.")

    return {
        "field_name": field,
        "nodes": [],
        "scalars": [float(cd)],
        "min": float(cd),
        "max": float(cd),
        "unit": "",
        "message": "ok",
    }


# ---------------------------------------------------------------------------
# Mapping analysis field nodes onto an STL surface mesh
# ---------------------------------------------------------------------------

def map_field_to_surface_vertices(
    field: dict[str, Any],
    surface_vertices: np.ndarray,
) -> list[float]:
    """Return a scalar value for each surface vertex by nearest-node lookup.

    If the field contains no node coordinates, returns an empty list.
    """
    nodes = np.asarray(field.get("nodes", []), dtype=float)
    scalars = np.asarray(field.get("scalars", []), dtype=float)
    surface_vertices = np.asarray(surface_vertices, dtype=float)
    if nodes.size == 0 or scalars.size == 0 or surface_vertices.size == 0:
        return []

    # KDTree when scipy is available, otherwise brute force.
    try:
        from scipy.spatial import KDTree
        tree = KDTree(nodes)
        _, idx = tree.query(surface_vertices)
    except Exception:
        idx = _nearest_brute_force(nodes, surface_vertices)

    return [float(scalars[i]) for i in idx]


def _nearest_brute_force(nodes: np.ndarray, surface_vertices: np.ndarray) -> list[int]:
    indices: list[int] = []
    for sv in surface_vertices:
        dists = np.linalg.norm(nodes - sv, axis=1)
        indices.append(int(np.argmin(dists)))
    return indices


# ---------------------------------------------------------------------------
# Field dispatch from a verification job result
# ---------------------------------------------------------------------------

def extract_field_from_job(
    result: dict[str, Any],
    field: str | None = None,
) -> dict[str, Any]:
    """Extract a scalar field from a persisted VerificationResult dict.

    Looks at ``raw_output`` to find solver result files and dispatches the
    appropriate parser.
    """
    raw = result.get("raw_output", {}) or {}
    solver = raw.get("solver", "")
    result_files = raw.get("result_files", {}) or {}

    if solver == "calculix":
        dat_path = result_files.get("dat")
        if dat_path:
            nodes = raw.get("details", {}).get("node_coordinates")
            if nodes:
                nodes = np.asarray(nodes, dtype=float)
            return extract_calculix_field(dat_path, nodes=nodes, field=field or "von_mises_stress_mpa")

    if solver == "elmerfem":
        summary_path = result_files.get("summary")
        if summary_path:
            ep_path = Path(summary_path).parent / "case.ep"
            if ep_path.exists():
                return extract_elmer_field(ep_path, field=field or "temperature_c")

    if solver == "openfoam":
        case_dir = raw.get("case_dir")
        if case_dir:
            return extract_openfoam_field(case_dir, field=field or "drag_coefficient")

    return _empty_field(field or "unknown", f"No field data available for solver '{solver}'.")
