"""CalculiX adapter for RoboCAD Phase 28C.

Writes ``.inp`` files for static/modal/thermal-expansion analyses, optionally
runs ``ccx``, and parses ``.dat`` output for displacements, stresses, and
eigenfrequencies.

All adapter functions return a :class:`SolverResult`.  If CalculiX is not
installed, input files are still written and the run step is skipped.  Pass
``mock=True`` in tests to synthesize a plausible ``.dat`` file and exercise the
parser.
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


CCX_BINARIES = ("ccx", "ccx_2.21", "ccx_2.20", "ccx_2.19", "CalculiX")


def _find_ccx() -> str | None:
    for name in CCX_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _chunked(ids: list[int], size: int = 16) -> list[list[int]]:
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def _get_region_node_set(mesh: Mesh, region: str | list[int], label: str) -> str:
    """Return the name of a node set that covers ``region``."""
    if isinstance(region, str):
        if region not in mesh.node_sets:
            raise ValueError(f"Region '{region}' not found in mesh node_sets.")
        return region
    nset_name = f"nset_{label}" if label else "nset_custom"
    mesh.node_sets.setdefault(nset_name, list(map(int, region)))
    return nset_name


def _write_node_section(lines: list[str], mesh: Mesh) -> None:
    lines.append("*NODE, NSET=Nall")
    for i, (x, y, z) in enumerate(mesh.nodes, start=1):
        lines.append(f"{i}, {x:.6e}, {y:.6e}, {z:.6e}")


def _write_element_section(lines: list[str], mesh: Mesh) -> None:
    lines.append("*ELEMENT, TYPE=C3D8R, ELSET=Eall")
    for i, elem in enumerate(mesh.elements, start=1):
        lines.append(f"{i}, " + ", ".join(str(n) for n in elem))


def _write_named_node_sets(lines: list[str], mesh: Mesh) -> None:
    for name, ids in mesh.node_sets.items():
        lines.append(f"*NSET, NSET={name}")
        for chunk in _chunked(ids, size=16):
            lines.append(", ".join(str(n) for n in chunk))


def _write_material_section(lines: list[str], material_name: str) -> None:
    mat = get_material(material_name)
    lines.append(f"*MATERIAL, NAME={mat.name.replace(' ', '_')}")
    lines.append("*ELASTIC")
    lines.append(f"{mat.youngs_modulus_mpa * 1e6:.6e}, {mat.poisson_ratio:.6e}")
    lines.append("*DENSITY")
    lines.append(f"{mat.density_kg_m3:.6e}")
    lines.append("*EXPANSION")
    lines.append(f"{mat.thermal_expansion_per_k:.6e}")


def _write_solid_section(lines: list[str], material_name: str) -> None:
    mat_name = get_material(material_name).name.replace(" ", "_")
    lines.append("*SOLID SECTION, ELSET=Eall, MATERIAL=" + mat_name)


def _write_static_step(lines: list[str], mesh: Mesh, bc_list: list[BoundaryCondition], thermal_load: dict[str, Any] | None = None) -> None:
    lines.append("*STEP")
    lines.append("*STATIC")
    _write_bcs_and_loads(lines, mesh, bc_list)
    if thermal_load:
        ref_temp = float(thermal_load.get("reference_temperature_c", 20.0))
        delta_t = float(thermal_load.get("delta_temperature_c", 0.0))
        lines.append("*TEMPERATURE")
        lines.append(f"Nall, {ref_temp + delta_t:.6e}")
    lines.append("*NODE PRINT, NSET=Nall")
    lines.append("U")
    lines.append("*EL PRINT, ELSET=Eall")
    lines.append("S")
    lines.append("*END STEP")


def _write_modal_step(lines: list[str], mesh: Mesh, bc_list: list[BoundaryCondition], modes: int) -> None:
    lines.append("*STEP")
    lines.append("*FREQUENCY")
    lines.append(str(max(int(modes), 1)))
    _write_bcs_and_loads(lines, mesh, bc_list)
    lines.append("*NODE PRINT, NSET=Nall")
    lines.append("U")
    lines.append("*END STEP")


def _write_bcs_and_loads(lines: list[str], mesh: Mesh, bc_list: list[BoundaryCondition]) -> None:
    fixed_bcs = [bc for bc in bc_list if bc.bc_type == BoundaryConditionType.FIXED]
    force_bcs = [bc for bc in bc_list if bc.bc_type == BoundaryConditionType.FORCE]
    temp_bcs = [bc for bc in bc_list if bc.bc_type == BoundaryConditionType.TEMPERATURE]

    for bc in fixed_bcs:
        nset = _get_region_node_set(mesh, bc.region, bc.label or "fixed")
        lines.append("*BOUNDARY")
        lines.append(f"{nset}, 1, 3, 0.0")

    for bc in temp_bcs:
        nset = _get_region_node_set(mesh, bc.region, bc.label or "temp")
        lines.append("*BOUNDARY")
        lines.append(f"{nset}, 11, 11, {bc.value:.6e}")

    for bc in force_bcs:
        nset = _get_region_node_set(mesh, bc.region, bc.label or "load")
        ids = mesh.node_sets[nset]
        if not ids:
            continue
        total_force = float(bc.value)
        direction = bc.direction or (0.0, 0.0, -1.0)
        norm = math.sqrt(sum(float(d) ** 2 for d in direction))
        if norm == 0:
            continue
        per_node = total_force / len(ids)
        dx, dy, dz = [float(d) / norm * per_node for d in direction]
        lines.append("*CLOAD")
        if abs(dx) > 1e-18:
            lines.append(f"{nset}, 1, {dx:.6e}")
        if abs(dy) > 1e-18:
            lines.append(f"{nset}, 2, {dy:.6e}")
        if abs(dz) > 1e-18:
            lines.append(f"{nset}, 3, {dz:.6e}")


def _write_inp(
    workdir: Path,
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    analysis_type: str,
    **params: Any,
) -> Path:
    inp_path = workdir / "analysis.inp"
    lines: list[str] = [
        "*Heading",
        f" RoboCAD CalculiX {analysis_type} analysis",
        "*Preprint, echo=NO, model=NO, history=NO, contact=NO",
    ]

    _write_node_section(lines, mesh)
    _write_element_section(lines, mesh)
    _write_named_node_sets(lines, mesh)
    _write_material_section(lines, material)
    _write_solid_section(lines, material)

    if analysis_type == "static":
        _write_static_step(lines, mesh, bc_list)
    elif analysis_type == "modal":
        _write_modal_step(lines, mesh, bc_list, modes=int(params.get("modes", 5)))
    elif analysis_type == "thermal_expansion":
        _write_static_step(lines, mesh, bc_list, thermal_load=params)
    else:
        raise ValueError(f"Unsupported CalculiX analysis_type: {analysis_type}")

    inp_path.write_text("\n".join(lines) + "\n")
    return inp_path


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


def _parse_calculix_dat(dat_path: Path, analysis_type: str) -> dict[str, float]:
    """Parse CalculiX ``.dat`` ASCII output.

    Supports nodal displacements, element stresses, and eigenfrequency tables.
    """
    metrics: dict[str, float] = {}
    text = dat_path.read_text()

    disp_blocks = text.split(" displacements")
    if len(disp_blocks) > 1:
        block = disp_blocks[-1]
        max_disp = 0.0
        for line in block.splitlines():
            if not line.strip() or "set" in line.lower() or "time" in line.lower():
                continue
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                try:
                    ux, uy, uz = map(float, parts[1:4])
                    mag = math.sqrt(ux * ux + uy * uy + uz * uz)
                    if mag > max_disp:
                        max_disp = mag
                except ValueError:
                    break
        if max_disp > 0:
            metrics["max_displacement_mm"] = max_disp * 1000.0

    stress_blocks = text.split(" stresses")
    if len(stress_blocks) > 1:
        block = stress_blocks[-1]
        max_vm = 0.0
        for line in block.splitlines():
            if not line.strip() or "set" in line.lower() or "time" in line.lower():
                continue
            parts = line.split()
            if len(parts) >= 8 and parts[0].isdigit():
                try:
                    vals = list(map(float, parts[2:8]))
                    vm = _von_mises(*vals)
                    if vm > max_vm:
                        max_vm = vm
                except ValueError:
                    break
        if max_vm > 0:
            metrics["max_stress_mpa"] = max_vm / 1e6

    if "E I G E N V A L U E" in text:
        freq_hz: list[float] = []
        capture = False
        for line in text.splitlines():
            if "E I G E N V A L U E" in line:
                capture = True
                continue
            if capture and line.strip():
                parts = line.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    try:
                        eigen = float(parts[1])
                        freq = math.sqrt(max(eigen, 0.0)) / (2.0 * math.pi)
                        freq_hz.append(freq)
                    except ValueError:
                        break
        if freq_hz:
            metrics["first_natural_frequency_hz"] = freq_hz[0]
            metrics["mode_count"] = float(len(freq_hz))

    return metrics


def _mock_dat_for_static(
    dat_path: Path,
    mesh: Mesh,
    bc_list: list[BoundaryCondition],
    material_name: str,
    thermal: bool = False,
    delta_t: float = 0.0,
) -> None:
    """Write a plausible CalculiX-style ``.dat`` file for tests/ mocks."""
    mat = get_material(material_name)
    bounds = mesh.nodes.min(axis=0), mesh.nodes.max(axis=0)
    extents = bounds[1] - bounds[0]

    fixed_axis: int | None = None
    for bc in bc_list:
        if bc.bc_type == BoundaryConditionType.FIXED and isinstance(bc.region, str):
            axis_map = {"-x": 0, "+x": 0, "-y": 1, "+y": 1, "-z": 2, "+z": 2}
            fixed_axis = axis_map.get(bc.region[0:2])
            break

    length = float(extents[0])
    if fixed_axis is not None:
        length = float(extents[fixed_axis])

    axis = int(np.argmax(extents))
    area_axes = [i for i in range(3) if i != axis]
    b, h = float(extents[area_axes[0]]), float(extents[area_axes[1]])
    I = b * h**3 / 12.0 if (b > 0 and h > 0) else 1e-12

    total_force = sum(float(bc.value) for bc in bc_list if bc.bc_type == BoundaryConditionType.FORCE)
    E_si = mat.youngs_modulus_mpa * 1e6

    max_disp = (total_force * length**3) / (3.0 * E_si * I) if I > 0 else 1e-9
    max_stress = (total_force * length * (h / 2.0)) / I if I > 0 else 1.0

    if thermal:
        max_stress += E_si * mat.thermal_expansion_per_k * delta_t
        max_disp += mat.thermal_expansion_per_k * delta_t * length

    max_stress = max(max_stress, 1.0)
    max_disp = max(max_disp, 1e-9)

    lines = []
    lines.append(" displacements (vx,vy,vz) for set Nall and time  1.0000000e+00\n")
    for i in range(1, mesh.node_count + 1):
        factor = (i % 5) / max(mesh.node_count, 1)
        ux, uy, uz = 0.0, 0.0, -max_disp * factor
        lines.append(f" {i} {ux:.6e} {uy:.6e} {uz:.6e}")
    lines.append("")
    lines.append(" stresses (elem, integ.pnt.,sxx,syy,szz,sxy,syz,sxz) for set Eall and time  1.0000000e+00\n")
    for i in range(1, mesh.element_count + 1):
        sxx = max_stress * (i / max(mesh.element_count, 1))
        syy = sxx * 0.1
        szz = sxx * 0.05
        sxy = syz = sxz = sxx * 0.02
        lines.append(f" {i} 1 {sxx:.6e} {syy:.6e} {szz:.6e} {sxy:.6e} {syz:.6e} {sxz:.6e}")
    lines.append("")

    dat_path.write_text("\n".join(lines) + "\n")


def _mock_dat_for_modal(dat_path: Path, modes: int) -> None:
    lines = [
        "    E I G E N V A L U E   O U T P U T",
        "",
        " MODE NO    EIGENVALUE                    FREQUENCY",
    ]
    for m in range(1, max(int(modes), 1) + 1):
        eigen = float(m) * 1e4
        freq = math.sqrt(eigen) / (2.0 * math.pi)
        lines.append(f" {m} {eigen:.6e}            {freq:.6e}")
    dat_path.write_text("\n".join(lines) + "\n")


def run_calculix(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    analysis_type: str = "static",
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
    **params: Any,
) -> SolverResult:
    """Run a CalculiX analysis (static, modal, or thermal expansion)."""
    if workdir is None:
        workdir_path = Path(tempfile.mkdtemp(prefix="robocad_calculix_"))
    else:
        workdir_path = Path(workdir)
        workdir_path.mkdir(parents=True, exist_ok=True)

    inp_path = _write_inp(workdir_path, mesh, material, bc_list, analysis_type, **params)
    dat_path = workdir_path / "analysis.dat"
    frd_path = workdir_path / "analysis.frd"

    errors: list[str] = []
    ccx_path = _find_ccx()

    if mock:
        if analysis_type == "modal":
            _mock_dat_for_modal(dat_path, int(params.get("modes", 5)))
        else:
            _mock_dat_for_static(
                dat_path,
                mesh,
                bc_list,
                material,
                thermal=(analysis_type == "thermal_expansion"),
                delta_t=float(params.get("delta_temperature_c", 0.0)),
            )
    elif run_solver:
        if ccx_path is None:
            errors.append("CalculiX (ccx) not found on PATH; input file written but solver not run.")
        else:
            try:
                result = subprocess.run(
                    [ccx_path, "-i", "analysis"],
                    cwd=workdir_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    errors.append(f"CalculiX exited with code {result.returncode}.")
                    if result.stderr:
                        errors.append(result.stderr[:500])
            except subprocess.TimeoutExpired:
                errors.append("CalculiX subprocess timed out.")
            except Exception as exc:
                errors.append(f"CalculiX run failed: {exc}")

    metrics: dict[str, float] = {}
    if dat_path.exists():
        metrics = _parse_calculix_dat(dat_path, analysis_type)

    if "max_stress_mpa" in metrics and analysis_type != "modal":
        try:
            mat = get_material(material)
            metrics["safety_factor"] = mat.yield_strength_mpa / max(metrics["max_stress_mpa"], 1e-12)
        except KeyError:
            pass

    success = bool(metrics) and (not errors or dat_path.exists())

    return SolverResult(
        success=success,
        solver="calculix",
        analysis_type=analysis_type,
        input_files=[inp_path],
        result_files={"dat": dat_path if dat_path.exists() else None, "frd": frd_path if frd_path.exists() else None},
        metrics=metrics,
        errors=errors,
        details={"ccx_path": ccx_path, "node_count": mesh.node_count, "element_count": mesh.element_count},
        raw_output={"stdout": "", "stderr": ""},
    )


def run_calculix_static(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
) -> SolverResult:
    """Convenience wrapper for a CalculiX static stress analysis."""
    return run_calculix(mesh, material, bc_list, analysis_type="static", workdir=workdir, run_solver=run_solver, mock=mock, timeout=timeout)


def run_calculix_modal(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    modes: int = 5,
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
) -> SolverResult:
    """Convenience wrapper for a CalculiX modal frequency analysis."""
    return run_calculix(
        mesh, material, bc_list, analysis_type="modal", workdir=workdir, run_solver=run_solver, mock=mock, timeout=timeout, modes=modes
    )


def run_calculix_thermal_expansion(
    mesh: Mesh,
    material: str,
    bc_list: list[BoundaryCondition],
    delta_temperature_c: float = 100.0,
    reference_temperature_c: float = 20.0,
    workdir: Path | str | None = None,
    run_solver: bool = True,
    mock: bool = False,
    timeout: float = 120.0,
) -> SolverResult:
    """Convenience wrapper for a thermal-expansion stress analysis."""
    return run_calculix(
        mesh,
        material,
        bc_list,
        analysis_type="thermal_expansion",
        workdir=workdir,
        run_solver=run_solver,
        mock=mock,
        timeout=timeout,
        delta_temperature_c=delta_temperature_c,
        reference_temperature_c=reference_temperature_c,
    )
