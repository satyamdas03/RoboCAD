"""ElmerFEM adapter for RoboCAD Phase 28C.

Writes native Elmer mesh files and ``.sif`` case files for thermal conduction
and coupled thermal-stress analyses, optionally runs ``ElmerSolver``, and parses
result summaries.

All adapter functions return a :class:`SolverResult`.  If ElmerFEM is not
installed the run step is skipped.  ``mock=True`` synthesises a result file so
the parser can be exercised without a real solver.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.materials import get_material
from ai_cad.solvers.models import BoundaryCondition, BoundaryConditionType, Mesh, SolverResult


ELMER_BINARIES = ("ElmerSolver", "ElmerSolver.exe", "elmersolver")

# Elmer element type codes used in mesh.elements and mesh.boundary.
_HEX8_CODE = 808
_QUAD4_CODE = 404

_FACE_LOCAL_NODES = {
    "-x": (0, 3, 7, 4),
    "+x": (1, 2, 6, 5),
    "-y": (0, 1, 5, 4),
    "+y": (3, 2, 6, 7),
    "-z": (0, 1, 2, 3),
    "+z": (4, 5, 6, 7),
}


def _find_elmer() -> str | None:
    for name in ELMER_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _face_node_ids(element: np.ndarray, face_nodes: tuple[int, ...]) -> list[int]:
    """Return 1-based node ids for a face of an element."""
    return [int(element[idx]) for idx in face_nodes]


def _generate_boundary_faces(mesh: Mesh, divisions: tuple[int, int, int]) -> list[tuple[int, int, str, list[int]]]:
    """Generate unique boundary face records for a structured hex box mesh.

    Returns a list of ``(boundary_id, parent_element_id, face_name, nodes)``.
    Boundary IDs are assigned sequentially so they can be referenced in the
    ``.sif`` file.
    """
    nx, ny, nz = divisions
    boundary_faces: list[tuple[int, int, str, list[int]]] = []
    bid = 1

    def add(parent_idx: int, face_name: str) -> None:
        nonlocal bid
        elem = mesh.elements[parent_idx]
        nodes = _face_node_ids(elem, _FACE_LOCAL_NODES[face_name])
        boundary_faces.append((bid, parent_idx + 1, face_name, nodes))
        bid += 1

    # -x and +x faces.
    for k in range(nz):
        for j in range(ny):
            add(0 + j * nx + k * nx * ny, "-x")
            add((nx - 1) + j * nx + k * nx * ny, "+x")

    # -y and +y faces.
    for k in range(nz):
        for i in range(nx):
            add(i + 0 * nx + k * nx * ny, "-y")
            add(i + (ny - 1) * nx + k * nx * ny, "+y")

    # -z and +z faces.
    for j in range(ny):
        for i in range(nx):
            add(i + j * nx + 0 * nx * ny, "-z")
            add(i + j * nx + (nz - 1) * nx * ny, "+z")

    return boundary_faces


def _write_elmer_mesh(mesh_dir: Path, mesh: Mesh, boundary_faces: list[tuple[int, int, str, list[int]]]) -> None:
    mesh_dir.mkdir(parents=True, exist_ok=True)

    (mesh_dir / "mesh.header").write_text(
        f"! RoboCAD Elmer mesh header\n{mesh.node_count} {mesh.element_count} {len(boundary_faces)}\n"
    )

    node_lines = [f"! {mesh.node_count}"]
    for i, (x, y, z) in enumerate(mesh.nodes, start=1):
        node_lines.append(f"{i} {x:.6e} {y:.6e} {z:.6e}")
    (mesh_dir / "mesh.nodes").write_text("\n".join(node_lines) + "\n")

    elem_lines = [f"! {mesh.element_count}"]
    for i, elem in enumerate(mesh.elements, start=1):
        elem_lines.append(f"{i} 1 {_HEX8_CODE} " + " ".join(str(n) for n in elem))
    (mesh_dir / "mesh.elements").write_text("\n".join(elem_lines) + "\n")

    bnd_lines = [f"! {len(boundary_faces)}"]
    for bid, parent, _face_name, nodes in boundary_faces:
        # Parent2 = 0 denotes an external boundary.
        bnd_lines.append(f"{bid} {parent} 0 {_QUAD4_CODE} " + " ".join(str(n) for n in nodes))
    (mesh_dir / "mesh.boundary").write_text("\n".join(bnd_lines) + "\n")


def _boundary_id_for_face(face_name: str, boundary_faces: list[tuple[int, int, str, list[int]]]) -> int | None:
    for bid, _parent, name, _nodes in boundary_faces:
        if name == face_name:
            return bid
    return None


def _write_sif_header(sif_lines: list[str]) -> None:
    sif_lines.extend(
        [
            "Header",
            "  CHECK KEYWORDS Warn",
            '  Mesh DB \".\" \"mesh\"',
            '  Results Directory \".\"',
            "End",
            "",
            "Simulation",
            "  Max Output Level = 5",
            "  Coordinate System = Cartesian",
            "  Simulation Type = Steady state",
            "  Steady State Max Iterations = 1",
            "  Output Intervals = 1",
            "  Timestepping Method = BDF",
            "  BDF Order = 1",
            '  Solver Input File = \"case.sif\"',
            '  Post File = \"case.ep\"',
            "End",
            "",
        ]
    )


def _write_material(sif_lines: list[str], material_name: str) -> None:
    mat = get_material(material_name)
    sif_lines.extend(
        [
            "Material 1",
            f'  Name = \"{mat.name}\"',
            f"  Density = {mat.density_kg_m3:.6e}",
            f"  Heat Conductivity = {mat.conductivity_w_m_k:.6e}",
            f"  Heat Capacity = {mat.specific_heat_j_kg_k:.6e}",
            f"  Youngs Modulus = {mat.youngs_modulus_mpa * 1e6:.6e}",
            f"  Poisson Ratio = {mat.poisson_ratio:.6e}",
            f"  Heat Expansion Coefficient = {mat.thermal_expansion_per_k:.6e}",
            "End",
            "",
        ]
    )


def _write_thermal_solver(sif_lines: list[str], solver_index: int = 1) -> None:
    sif_lines.extend(
        [
            f"Solver {solver_index}",
            '  Equation = \"Heat Equation\"',
            '  Procedure = \"HeatSolve\" \"HeatSolver\"',
            "  Variable = Temperature",
            "  Exec Solver = Always",
            "  Stabilize = True",
            "  Bubbles = False",
            "  Lumped Mass Matrix = False",
            "  Optimize Bandwidth = True",
            "  Steady State Convergence Tolerance = 1.0e-5",
            "  Nonlinear System Convergence Tolerance = 1.0e-7",
            "  Nonlinear System Max Iterations = 1",
            "  Nonlinear System Newton After Iterations = 3",
            "  Nonlinear System Newton After Tolerance = 1.0e-3",
            "  Linear System Solver = Direct",
            "  Linear System Direct Method = MUMPS",
            "End",
            "",
        ]
    )


def _write_stress_solver(sif_lines: list[str], solver_index: int = 2) -> None:
    sif_lines.extend(
        [
            f"Solver {solver_index}",
            '  Equation = \"Stress Analysis\"',
            '  Procedure = \"StressSolve\" \"StressSolver\"',
            '  Variable = \"Displacement\"',
            "  Variable Dofs = 3",
            "  Exec Solver = Always",
            "  Stabilize = True",
            "  Bubbles = False",
            "  Lumped Mass Matrix = False",
            "  Optimize Bandwidth = True",
            "  Steady State Convergence Tolerance = 1.0e-5",
            "  Nonlinear System Convergence Tolerance = 1.0e-7",
            "  Nonlinear System Max Iterations = 1",
            "  Linear System Solver = Direct",
            "  Linear System Direct Method = MUMPS",
            "End",
            "",
        ]
    )


def _write_body(sif_lines: list[str], equation_index: int = 1) -> None:
    sif_lines.extend(
        [
            "Body 1",
            "  Target Bodies(1) = 1",
            '  Name = \"Body 1\"',
            f"  Equation = {equation_index}",
            "  Material = 1",
            "End",
            "",
        ]
    )


def _write_boundary_conditions(
    sif_lines: list[str],
    bc_list: list[BoundaryCondition],
    boundary_faces: list[tuple[int, int, str, list[int]]],
) -> dict[str, float]:
    """Write Elmer boundary condition blocks and return thermal extrema."""
    temps: list[float] = []
    for idx, bc in enumerate(bc_list, start=1):
        face_name = bc.region if isinstance(bc.region, str) else None
        if face_name is None:
            continue
        bid = _boundary_id_for_face(face_name, boundary_faces)
        if bid is None:
            continue

        sif_lines.append(f"Boundary Condition {idx}")
        sif_lines.append(f"  Target Boundaries(1) = {bid}")
        sif_lines.append(f'  Name = "{bc.label or face_name}"')

        if bc.bc_type == BoundaryConditionType.FIXED:
            sif_lines.append("  Displacement 1 = 0.0")
            sif_lines.append("  Displacement 2 = 0.0")
            sif_lines.append("  Displacement 3 = 0.0")
        elif bc.bc_type == BoundaryConditionType.TEMPERATURE:
            sif_lines.append(f"  Temperature = {bc.value:.6e}")
            temps.append(float(bc.value))
        elif bc.bc_type == BoundaryConditionType.HEAT_FLUX:
            sif_lines.append(f"  Heat Flux = {bc.value:.6e}")
        elif bc.bc_type == BoundaryConditionType.CONVECTION:
            sif_lines.append(f"  Heat Transfer Coefficient = {bc.value:.6e}")
            ext_temp = bc.direction[0] if bc.direction else 20.0
            sif_lines.append(f"  External Temperature = {float(ext_temp):.6e}")
        elif bc.bc_type == BoundaryConditionType.FORCE:
            direction = bc.direction or (0.0, 0.0, -1.0)
            norm = math.sqrt(sum(float(d) ** 2 for d in direction))
            if norm == 0:
                norm = 1.0
            fx, fy, fz = [float(d) / norm * bc.value for d in direction]
            sif_lines.append(f"  Force 1 = {fx:.6e}")
            sif_lines.append(f"  Force 2 = {fy:.6e}")
            sif_lines.append(f"  Force 3 = {fz:.6e}")

        sif_lines.append("End")
        sif_lines.append("")

    return {"min_temperature": min(temps) if temps else 0.0, "max_temperature": max(temps) if temps else 0.0}


def _write_initial_condition(sif_lines: list[str], temperature: float) -> None:
    sif_lines.extend(
        [
            "Initial Condition 1",
            f"  Temperature = {temperature:.6e}",
            "End",
            "",
        ]
    )


def _write_thermal_case(
    workdir: Path,
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    initial_temperature: float,
) -> tuple[Path, list[tuple[int, int, str, list[int]]], dict[str, float]]:
    divisions = mesh.divisions or _infer_divisions(mesh)
    boundary_faces = _generate_boundary_faces(mesh, divisions)
    _write_elmer_mesh(workdir / "mesh", mesh, boundary_faces)

    sif_lines: list[str] = []
    _write_sif_header(sif_lines)
    _write_body(sif_lines, equation_index=1)
    _write_material(sif_lines, material)
    sif_lines.append("Equation 1")
    sif_lines.append("  Active Solvers(1) = 1")
    sif_lines.append("End")
    sif_lines.append("")
    _write_thermal_solver(sif_lines, solver_index=1)
    temp_extrema = _write_boundary_conditions(sif_lines, bc_list, boundary_faces)
    _write_initial_condition(sif_lines, initial_temperature)

    sif_path = workdir / "case.sif"
    sif_path.write_text("\n".join(sif_lines) + "\n")
    return sif_path, boundary_faces, temp_extrema


def _write_thermal_stress_case(
    workdir: Path,
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    initial_temperature: float,
) -> tuple[Path, list[tuple[int, int, str, list[int]]], dict[str, float]]:
    divisions = mesh.divisions or _infer_divisions(mesh)
    boundary_faces = _generate_boundary_faces(mesh, divisions)
    _write_elmer_mesh(workdir / "mesh", mesh, boundary_faces)

    sif_lines: list[str] = []
    _write_sif_header(sif_lines)
    _write_body(sif_lines, equation_index=1)
    _write_material(sif_lines, material)
    sif_lines.append("Equation 1")
    sif_lines.append("  Active Solvers(2) = 1 2")
    sif_lines.append("End")
    sif_lines.append("")
    _write_thermal_solver(sif_lines, solver_index=1)
    _write_stress_solver(sif_lines, solver_index=2)
    temp_extrema = _write_boundary_conditions(sif_lines, bc_list, boundary_faces)
    _write_initial_condition(sif_lines, initial_temperature)

    sif_path = workdir / "case.sif"
    sif_path.write_text("\n".join(sif_lines) + "\n")
    return sif_path, boundary_faces, temp_extrema


def _infer_divisions(mesh: Mesh) -> tuple[int, int, int]:
    """Recover a reasonable structured division from a box-shaped hexa mesh."""
    n = mesh.node_count
    e = mesh.element_count
    cube = round(e ** (1.0 / 3.0))
    nx = ny = nz = max(int(cube), 1)
    if (nx + 1) * (ny + 1) * (nz + 1) != n:
        bounds = mesh.nodes.min(axis=0), mesh.nodes.max(axis=0)
        extents = bounds[1] - bounds[0]
        total = max(extents.sum(), 1e-9)
        ratios = extents / total
        scale = e / max(ratios.prod(), 1e-12)
        nx = max(int(round((ratios[0] * scale) ** (1.0 / 3.0))), 1)
        ny = max(int(round((ratios[1] * scale) ** (1.0 / 3.0))), 1)
        nz = max(int(round((ratios[2] * scale) ** (1.0 / 3.0))), 1)
    return nx, ny, nz


def _mock_result_summary(
    summary_path: Path,
    mesh: Mesh,
    material_name: str,
    temp_extrema: dict[str, float],
    has_stress: bool,
) -> dict[str, float]:
    """Write a synthetic result summary file for tests."""
    mat = get_material(material_name)
    bounds = mesh.nodes.min(axis=0), mesh.nodes.max(axis=0)
    extents = bounds[1] - bounds[0]
    length = float(max(extents))

    max_temp = temp_extrema.get("max_temperature", 20.0)
    min_temp = temp_extrema.get("min_temperature", 20.0)
    delta_t = max_temp - min_temp

    metrics: dict[str, float] = {
        "max_temperature_c": float(max_temp),
        "min_temperature_c": float(min_temp),
    }

    if has_stress:
        max_stress = max(mat.youngs_modulus_mpa * 1e6 * mat.thermal_expansion_per_k * delta_t, 1.0)
        max_disp = max(mat.thermal_expansion_per_k * delta_t * length, 1e-9)
        metrics["max_stress_mpa"] = max_stress / 1e6
        metrics["max_displacement_mm"] = max_disp * 1000.0
        metrics["safety_factor"] = mat.yield_strength_mpa / max(metrics["max_stress_mpa"], 1e-12)

    lines = [f"{k}: {v:.6e}" for k, v in metrics.items()]
    summary_path.write_text("\n".join(lines) + "\n")
    return metrics


def _parse_result_summary(summary_path: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in summary_path.read_text().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        try:
            metrics[key.strip()] = float(value.strip())
        except ValueError:
            continue
    return metrics


def run_elmer_thermal_conduction(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    initial_temperature: float = 20.0,
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
) -> SolverResult:
    """Run an ElmerFEM steady-state thermal conduction analysis."""
    workdir_path = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="robocad_elmer_"))
    workdir_path.mkdir(parents=True, exist_ok=True)

    sif_path, boundary_faces, temp_extrema = _write_thermal_case(
        workdir_path, mesh, material, bc_list, initial_temperature
    )
    summary_path = workdir_path / "result_summary.txt"

    errors: list[str] = []
    elmer_path = _find_elmer()

    if mock:
        _mock_result_summary(summary_path, mesh, material, temp_extrema, has_stress=False)
    elif run_solver:
        if elmer_path is None:
            errors.append("ElmerSolver not found on PATH; case files written but solver not run.")
        else:
            try:
                result = subprocess.run(
                    [elmer_path, "case.sif"],
                    cwd=workdir_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    errors.append(f"ElmerSolver exited with code {result.returncode}.")
                    if result.stderr:
                        errors.append(result.stderr[:500])
            except subprocess.TimeoutExpired:
                errors.append("ElmerSolver subprocess timed out.")
            except Exception as exc:
                errors.append(f"ElmerSolver run failed: {exc}")

    metrics: dict[str, float] = {}
    if summary_path.exists():
        metrics = _parse_result_summary(summary_path)

    success = bool(metrics) and (not errors or summary_path.exists())

    return SolverResult(
        success=success,
        solver="elmerfem",
        analysis_type="thermal_conduction",
        input_files=[sif_path, workdir_path / "mesh" / "mesh.nodes", workdir_path / "mesh" / "mesh.elements"],
        result_files={"summary": summary_path if summary_path.exists() else None},
        metrics=metrics,
        errors=errors,
        details={
            "elmer_path": elmer_path,
            "boundary_count": len(boundary_faces),
            "node_count": mesh.node_count,
            "element_count": mesh.element_count,
        },
        raw_output={"stdout": "", "stderr": ""},
    )


def run_elmer_thermal_stress(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    initial_temperature: float = 20.0,
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
) -> SolverResult:
    """Run an ElmerFEM coupled thermal-stress analysis."""
    workdir_path = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="robocad_elmer_"))
    workdir_path.mkdir(parents=True, exist_ok=True)

    sif_path, boundary_faces, temp_extrema = _write_thermal_stress_case(
        workdir_path, mesh, material, bc_list, initial_temperature
    )
    summary_path = workdir_path / "result_summary.txt"

    errors: list[str] = []
    elmer_path = _find_elmer()

    if mock:
        _mock_result_summary(summary_path, mesh, material, temp_extrema, has_stress=True)
    elif run_solver:
        if elmer_path is None:
            errors.append("ElmerSolver not found on PATH; case files written but solver not run.")
        else:
            try:
                result = subprocess.run(
                    [elmer_path, "case.sif"],
                    cwd=workdir_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    errors.append(f"ElmerSolver exited with code {result.returncode}.")
                    if result.stderr:
                        errors.append(result.stderr[:500])
            except subprocess.TimeoutExpired:
                errors.append("ElmerSolver subprocess timed out.")
            except Exception as exc:
                errors.append(f"ElmerSolver run failed: {exc}")

    metrics: dict[str, float] = {}
    if summary_path.exists():
        metrics = _parse_result_summary(summary_path)

    success = bool(metrics) and (not errors or summary_path.exists())

    return SolverResult(
        success=success,
        solver="elmerfem",
        analysis_type="thermal_stress",
        input_files=[sif_path, workdir_path / "mesh" / "mesh.nodes", workdir_path / "mesh" / "mesh.elements"],
        result_files={"summary": summary_path if summary_path.exists() else None},
        metrics=metrics,
        errors=errors,
        details={
            "elmer_path": elmer_path,
            "boundary_count": len(boundary_faces),
            "node_count": mesh.node_count,
            "element_count": mesh.element_count,
        },
        raw_output={"stdout": "", "stderr": ""},
    )
