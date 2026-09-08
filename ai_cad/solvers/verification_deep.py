"""Async deep verification dispatcher for RoboCAD Phase 28C/28E.

This module dispatches closed load cases to pluggable deep adapters:
CalculiX (structural), Elmer (thermal), OpenFOAM (CFD), and a NVIDIA NIM
surrogate fallback. It integrates with the existing VerificationRequest and
VerificationResult models and records every run in the SQLite job store.

Phase 28E adds real-solver dispatch: when CalculiX, ElmerFEM, or OpenFOAM are
installed, the dispatcher actually runs them instead of lightweight estimates.
When a solver is missing the system degrades gracefully to the estimate or the
NVIDIA surrogate, controlled by the ``solver_mode`` parameter
(``auto`` / ``real`` / ``surrogate``).
"""
from __future__ import annotations

import math
import shutil
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ai_cad import cfd, fea, thermal
from ai_cad.materials import Material, get_material
from ai_cad.solvers import calculix_adapter, elmerfem_adapter, openfoam_adapter
from ai_cad.solvers.job_store import JobStatus, JobStore, VerificationJob
from ai_cad.solvers.models import BoundaryCondition, BoundaryConditionType, Mesh
from ai_cad.solvers.nvidia_surrogate import NvidiaSurrogate
from ai_cad.verification_models import LoadCase, VerificationRequest, VerificationResult


# ---------------------------------------------------------------------------
# Deep adapters
# ---------------------------------------------------------------------------

class DeepAdapter(ABC):
    """Base class for a deep verification adapter."""

    name: str
    supported_load_cases: list[LoadCase]

    @abstractmethod
    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        ...


class CalculiXAdapter(DeepAdapter):
    """Structural deep adapter backed by CalculiX when available."""

    name = "calculix"
    supported_load_cases = [
        LoadCase.STATIC_STRESS,
        LoadCase.DROP_TEST,
        LoadCase.THERMAL_EXPANSION,
        LoadCase.FATIGUE_CYCLES,
        LoadCase.FASTENER_PULL_OUT,
    ]

    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        stl_path = _resolve_stl_path(design_dir)
        if stl_path is None:
            return _error(request, "No STL export found for deep structural analysis.")

        mode = _solver_mode_for(request)
        if mode == "surrogate":
            return _structural_estimate(request, stl_path)

        analysis_mesh = _build_analysis_mesh(mesh or stl_path)
        if analysis_mesh is None:
            if mode == "real":
                return _error(request, "Could not build analysis mesh for real CalculiX run.")
            return _structural_estimate(request, stl_path)

        material = _resolve_material(request)
        fixed_face = str(request.parameters.get("fixed_face", "-x"))
        load = float(request.parameters.get("load_magnitude_n", 100.0))
        load_direction = _normalize_direction(
            request.parameters.get("load_direction", (0.0, 0.0, -1.0))
        )
        target_sf = float(request.parameters.get("safety_factor_target", 2.0))

        bc_list = _structural_boundary_conditions(
            analysis_mesh,
            fixed_face=fixed_face,
            load_face=_opposite_face(fixed_face),
            load_magnitude_n=load,
            load_direction=load_direction,
        )

        workdir = design_dir / "deep_results" / _safe_id(request.design_id) / "calculix"
        workdir.mkdir(parents=True, exist_ok=True)

        ccx_available = calculix_adapter._find_ccx() is not None
        if mode == "real" and not ccx_available:
            return _error(request, "CalculiX requested but ccx binary not found on PATH.")

        if ccx_available and mode in ("auto", "real"):
            try:
                analysis_type = "static"
                if request.load_case == LoadCase.THERMAL_EXPANSION:
                    analysis_type = "thermal_expansion"
                elif request.load_case == LoadCase.DROP_TEST:
                    analysis_type = "modal"

                solver_result = calculix_adapter.run_calculix(
                    analysis_mesh,
                    material.name,
                    bc_list,
                    analysis_type=analysis_type,
                    workdir=workdir,
                    run_solver=True,
                    mock=False,
                    timeout=float(request.parameters.get("timeout", 120.0)),
                    delta_temperature_c=float(request.parameters.get("delta_temperature_c", 100.0)),
                    reference_temperature_c=float(request.parameters.get("reference_temperature_c", 20.0)),
                    modes=int(request.parameters.get("modes", 5)),
                )
                return _solver_result_to_verification(
                    request,
                    solver_result,
                    target_sf=target_sf,
                    nodes=analysis_mesh.nodes,
                    suggestions=_extract_structural_suggestions_from_solver(solver_result, target_sf),
                )
            except Exception as exc:
                if mode == "real":
                    return _error(request, f"Real CalculiX run failed: {exc}")
                # auto mode falls through to estimate

        # Fallback estimate
        return _structural_estimate(request, stl_path)


class ElmerAdapter(DeepAdapter):
    """Thermal deep adapter backed by ElmerFEM when available."""

    name = "elmer"
    supported_load_cases = [LoadCase.HEAT_SINK_THERMAL_RESISTANCE, LoadCase.THERMAL_EXPANSION]

    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        stl_path = _resolve_stl_path(design_dir)
        if stl_path is None:
            return _error(request, "No STL export found for deep thermal analysis.")

        mode = _solver_mode_for(request)
        if mode == "surrogate":
            return _thermal_estimate(request, stl_path)

        analysis_mesh = _build_analysis_mesh(mesh or stl_path)
        if analysis_mesh is None:
            if mode == "real":
                return _error(request, "Could not build analysis mesh for real Elmer run.")
            return _thermal_estimate(request, stl_path)

        material = _resolve_material(request)
        heat_flux = float(request.parameters.get("heat_flux_w", 10.0))
        ambient = float(request.parameters.get("ambient_temp_c", 25.0))
        h_conv = float(request.parameters.get("convection_coefficient_w_per_m2_k", 50.0))
        target = float(request.parameters.get("target_theta_c_per_w", 10.0))
        initial_temperature = float(request.parameters.get("initial_temperature_c", ambient))
        load_face = str(request.parameters.get("load_face", "+z"))

        bc_list = _thermal_boundary_conditions(
            analysis_mesh,
            load_face=load_face,
            heat_flux_w=heat_flux,
            ambient_temp_c=ambient,
            convection_coefficient_w_per_m2_k=h_conv,
        )

        elmer_available = elmerfem_adapter._find_elmer() is not None
        if mode == "real" and not elmer_available:
            return _error(request, "ElmerFEM requested but ElmerSolver binary not found on PATH.")

        workdir = design_dir / "deep_results" / _safe_id(request.design_id) / "elmer"
        workdir.mkdir(parents=True, exist_ok=True)

        if elmer_available and mode in ("auto", "real"):
            try:
                if request.load_case == LoadCase.THERMAL_EXPANSION:
                    solver_result = elmerfem_adapter.run_elmer_thermal_stress(
                        analysis_mesh,
                        material.name,
                        bc_list,
                        initial_temperature=initial_temperature,
                        workdir=workdir,
                        run_solver=True,
                        mock=False,
                        timeout=float(request.parameters.get("timeout", 120.0)),
                    )
                else:
                    solver_result = elmerfem_adapter.run_elmer_thermal_conduction(
                        analysis_mesh,
                        material.name,
                        bc_list,
                        initial_temperature=initial_temperature,
                        workdir=workdir,
                        run_solver=True,
                        mock=False,
                        timeout=float(request.parameters.get("timeout", 120.0)),
                    )
                return _solver_result_to_verification(
                    request,
                    solver_result,
                    target_theta=target,
                    ambient=ambient,
                    heat_flux=heat_flux,
                    nodes=analysis_mesh.nodes,
                    suggestions=_extract_thermal_suggestions_from_solver(solver_result, target),
                )
            except Exception as exc:
                if mode == "real":
                    return _error(request, f"Real Elmer run failed: {exc}")

        return _thermal_estimate(request, stl_path)


class OpenFOAMAdapter(DeepAdapter):
    """CFD deep adapter: run OpenFOAM case when available, else estimate drag."""

    name = "openfoam"
    supported_load_cases = [LoadCase.WIND_TUNNEL_DRAG]

    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        stl_path = _resolve_stl_path(design_dir)
        if stl_path is None:
            return _error(request, "No STL export found for deep CFD analysis.")

        mode = _solver_mode_for(request)
        if mode == "surrogate":
            return _cfd_estimate(request, stl_path, mesh)

        velocity = float(request.parameters.get("velocity_m_s", 10.0))
        aoa = float(request.parameters.get("angle_of_attack_deg", 0.0))
        output_dir = design_dir / "deep_results" / _safe_id(request.design_id) / "openfoam"
        output_dir.mkdir(parents=True, exist_ok=True)

        surface_mesh = _load_mesh(design_dir)
        if surface_mesh is None:
            if mode == "real":
                return _error(request, "No mesh available for real OpenFOAM run.")
            return _cfd_estimate(request, stl_path, mesh)

        # Convert mm -> m for OpenFOAM.
        scaled_mesh = surface_mesh.copy()
        scaled_mesh.apply_scale(0.001)

        boundary_conditions = {
            "inlet": {
                "U": {"type": "fixedValue", "value": _flow_vector(velocity, aoa)},
                "p": {"type": "zeroGradient"},
            },
            "outlet": {
                "U": {"type": "zeroGradient"},
                "p": {"type": "fixedValue", "value": 0.0},
            },
            "model": {
                "U": {"type": "noSlip"},
                "p": {"type": "zeroGradient"},
            },
            "top": {"U": {"type": "slip"}, "p": {"type": "zeroGradient"}},
            "bottom": {"U": {"type": "slip"}, "p": {"type": "zeroGradient"}},
            "front": {"U": {"type": "slip"}, "p": {"type": "zeroGradient"}},
            "back": {"U": {"type": "slip"}, "p": {"type": "zeroGradient"}},
        }

        reference_values = {
            "flow_velocity_ms": velocity,
            "angle_of_attack_deg": aoa,
            "characteristic_length_m": float(max(scaled_mesh.extents)) if scaled_mesh.extents.any() else 0.1,
            "reference_area_m2": float(scaled_mesh.area) if scaled_mesh.area else 0.001,
            "density_kg_m3": 1.225,
            "kinematic_viscosity_m2_s": 1.5e-5,
        }

        local_foam = openfoam_adapter._local_openfoam_available("simpleFoam")
        use_docker = bool(request.parameters.get("openfoam_use_docker", False)) and openfoam_adapter._docker_available()
        if mode == "real" and not (local_foam or use_docker):
            return _error(request, "OpenFOAM requested but neither local OpenFOAM nor Docker is available.")

        try:
            case_result = openfoam_adapter.build_openfoam_case(
                scaled_mesh,
                output_dir,
                boundary_conditions,
                reference_values=reference_values,
                mesh_name="model.stl",
                domain_scale=float(request.parameters.get("openfoam_domain_scale", 5.0)),
                mesh_scale=1.0,
                background_cells=(20, 20, 20),
                solver="simpleFoam",
                write_force_coeffs=True,
            )
            if not case_result.success and mode == "real":
                return _error(request, f"OpenFOAM case setup failed: {case_result.errors}")
        except Exception as exc:
            if mode == "real":
                return _error(request, f"OpenFOAM case setup failed: {exc}")
            return _cfd_estimate(request, stl_path, mesh)

        if (local_foam or use_docker) and mode in ("auto", "real"):
            try:
                run_result = openfoam_adapter.run_openfoam_case(
                    output_dir,
                    solver="simpleFoam",
                    use_docker=use_docker,
                    timeout=int(request.parameters.get("openfoam_timeout", 1800)),
                )
                cd = float(run_result.coefficients.get("Cd", 0.0))
                if cd <= 0.0:
                    cd = float(run_result.coefficients.get("C_d", 0.0))
                if run_result.run_success and cd > 0.0:
                    frontal_m2 = reference_values["reference_area_m2"]
                    rho = reference_values["density_kg_m3"]
                    drag_force = 0.5 * rho * velocity**2 * frontal_m2 * cd
                    return VerificationResult(
                        design_id=request.design_id,
                        load_case=request.load_case,
                        passed=True,
                        warnings=[],
                        errors=run_result.errors,
                        metrics={
                            "drag_coefficient": round(cd, 4),
                            "drag_force_n": round(drag_force, 6),
                            "reynolds_number": _reynolds_number(velocity, reference_values),
                            "flow_velocity_ms": velocity,
                        },
                        failure_modes=[],
                        redesign_suggestions=_extract_cfd_suggestions(cd, request),
                        raw_output={"solver": "openfoam", **case_result.model_dump(), **run_result.model_dump()},
                    )
                if mode == "real":
                    return _error(request, f"OpenFOAM run did not produce valid Cd: {run_result.errors}")
            except Exception as exc:
                if mode == "real":
                    return _error(request, f"OpenFOAM run failed: {exc}")

        return _cfd_estimate(request, stl_path, mesh)


class SurrogateAdapter(DeepAdapter):
    """Universal surrogate adapter using the NVIDIA NIM client or shape lookup."""

    name = "surrogate"
    supported_load_cases = list(LoadCase)

    def __init__(self, surrogate: NvidiaSurrogate | None = None) -> None:
        self.surrogate = surrogate or NvidiaSurrogate()

    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        if mesh is None:
            return _error(request, "No mesh available for surrogate prediction.")

        material = _resolve_material(request)
        quantity = _quantity_for_load_case(request.load_case)
        prediction = self.surrogate.predict(mesh, quantity, request.parameters, material)

        # Normalize metric keys into the VerificationResult metrics dict.
        metrics: dict[str, float] = {}
        for key, value in prediction.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[key] = float(value)

        # Determine pass/fail from whatever metric is available.
        passed = True
        if "safety_factor" in metrics and metrics["safety_factor"] < 2.0:
            passed = False
        if "max_temperature_c" in metrics and metrics["max_temperature_c"] > 100.0:
            passed = False

        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=passed,
            warnings=prediction.get("warnings", []),
            errors=[],
            metrics=metrics,
            failure_modes=[],
            redesign_suggestions=_extract_surrogate_suggestions(prediction, request),
            raw_output={"solver": prediction.get("solver", "surrogate"), "quantity": quantity},
        )


# ---------------------------------------------------------------------------
# Solver mode helpers
# ---------------------------------------------------------------------------

def _solver_mode_for(request: VerificationRequest) -> str:
    """Return ``auto``, ``real``, or ``surrogate`` for this request."""
    mode = str(request.parameters.get("solver_mode", "auto")).lower()
    if mode in ("real", "surrogate"):
        return mode
    return "auto"


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------

def _build_analysis_mesh(shape_or_mesh: trimesh.Trimesh | Path | str) -> Mesh | None:
    """Create a coarse hexahedral analysis mesh from an STL or trimesh mesh.

    The box mesh covers the bounding box of the part so that existing CalculiX
    and Elmer hexahedral adapters can run without requiring Gmsh/Netgen. Real
    boundary-conforming meshing can be swapped in here later.
    """
    try:
        if isinstance(shape_or_mesh, (Path, str)):
            mesh = trimesh.load_mesh(str(shape_or_mesh))
        else:
            mesh = shape_or_mesh
        if isinstance(mesh, trimesh.Scene):
            if len(mesh.geometry) == 1:
                mesh = next(iter(mesh.geometry.values()))
            else:
                return None
        mesh.fix_normals()
        mesh.merge_vertices()
    except Exception:
        return None

    bounds = mesh.bounds
    origin = bounds[0].tolist()
    extents = (bounds[1] - bounds[0]).tolist()
    if any(e <= 0 for e in extents):
        return None

    # Use at least 4 divisions per axis and scale with the largest dimension.
    max_dim = max(extents)
    divisions = [max(4, int(round(extents[i] / max_dim * 8))) for i in range(3)]
    divisions = tuple(max(2, d) for d in divisions)

    return Mesh.box(extents=extents, origin=origin, divisions=divisions)


# ---------------------------------------------------------------------------
# Boundary-condition helpers
# ---------------------------------------------------------------------------

def _structural_boundary_conditions(
    mesh: Mesh,
    fixed_face: str,
    load_face: str,
    load_magnitude_n: float,
    load_direction: tuple[float, float, float],
) -> list[BoundaryCondition]:
    bcs: list[BoundaryCondition] = []
    if fixed_face in mesh.node_sets:
        bcs.append(
            BoundaryCondition(
                bc_type=BoundaryConditionType.FIXED,
                region=fixed_face,
                label="fixed",
            )
        )
    if load_face in mesh.node_sets:
        bcs.append(
            BoundaryCondition(
                bc_type=BoundaryConditionType.FORCE,
                region=load_face,
                value=load_magnitude_n,
                direction=load_direction,
                label="load",
            )
        )
    return bcs


def _thermal_boundary_conditions(
    mesh: Mesh,
    load_face: str,
    heat_flux_w: float,
    ambient_temp_c: float,
    convection_coefficient_w_per_m2_k: float,
) -> list[BoundaryCondition]:
    bcs: list[BoundaryCondition] = []
    if load_face in mesh.node_sets:
        bcs.append(
            BoundaryCondition(
                bc_type=BoundaryConditionType.HEAT_FLUX,
                region=load_face,
                value=heat_flux_w,
                label="heat_source",
            )
        )
    # Apply convection to all exterior faces except the heat source.
    for face in ("-x", "+x", "-y", "+y", "-z", "+z"):
        if face in mesh.node_sets and face != load_face:
            bcs.append(
                BoundaryCondition(
                    bc_type=BoundaryConditionType.CONVECTION,
                    region=face,
                    value=convection_coefficient_w_per_m2_k,
                    direction=(ambient_temp_c, 0.0, 0.0),
                    label=f"convection_{face}",
                )
            )
    return bcs


def _opposite_face(face: str) -> str:
    return {"-x": "+x", "+x": "-x", "-y": "+y", "+y": "-y", "-z": "+z", "+z": "-z"}.get(face, "+x")


def _normalize_direction(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return (0.0, 0.0, -1.0)
    return (float(value[0]), float(value[1]), float(value[2]))


def _flow_vector(velocity: float, aoa_deg: float) -> list[float]:
    aoa = math.radians(aoa_deg)
    return [float(velocity * math.cos(aoa)), float(velocity * math.sin(aoa)), 0.0]


def _reynolds_number(velocity: float, reference_values: dict[str, float]) -> float:
    l = reference_values.get("characteristic_length_m", 0.1)
    nu = reference_values.get("kinematic_viscosity_m2_s", 1.5e-5)
    return round(velocity * l / nu, 2)


def _safe_id(design_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in design_id)


# ---------------------------------------------------------------------------
# Estimate fallbacks
# ---------------------------------------------------------------------------

def _structural_estimate(request: VerificationRequest, stl_path: Path) -> VerificationResult:
    material = _resolve_material(request)
    fixed_face = str(request.parameters.get("fixed_face", "-x"))
    load = float(request.parameters.get("load_magnitude_n", 100.0))
    target_sf = float(request.parameters.get("safety_factor_target", 2.0))

    fea_result = fea.run_static_analysis(
        stl_path,
        fixed_face=fixed_face,
        load_magnitude_n=load,
        material=material.name,
    )

    passed = bool(
        fea_result.success
        and fea_result.safety_factor is not None
        and fea_result.safety_factor >= target_sf
    )

    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=passed,
        warnings=["CalculiX not available; using lightweight structural estimate."],
        errors=fea_result.errors if not fea_result.success else [],
        metrics={
            "max_stress_mpa": fea_result.max_stress_mpa or 0.0,
            "max_displacement_mm": fea_result.max_displacement_mm or 0.0,
            "safety_factor": fea_result.safety_factor or 0.0,
        },
        failure_modes=["yield_exceeded"] if not passed else [],
        redesign_suggestions=_extract_structural_suggestions(fea_result, request),
        raw_output={"solver": fea_result.solver, **fea_result.details},
    )


def _thermal_estimate(request: VerificationRequest, stl_path: Path) -> VerificationResult:
    heat_flux = float(request.parameters.get("heat_flux_w", 10.0))
    ambient = float(request.parameters.get("ambient_temp_c", 25.0))
    h_conv = float(request.parameters.get("convection_coefficient_w_per_m2_k", 50.0))
    target = float(request.parameters.get("target_theta_c_per_w", 10.0))

    thermal_result = thermal.run_thermal_analysis(
        stl_path,
        heat_flux_w=heat_flux,
        ambient_temp_c=ambient,
        convection_coefficient_w_per_m2_k=h_conv,
    )

    if not thermal_result.success:
        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=False,
            errors=thermal_result.errors,
            metrics={},
            redesign_suggestions=["Check mesh surface area and retry."],
        )

    theta = thermal_result.thermal_resistance_c_per_w or float("inf")
    passed = theta <= target

    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=passed,
        warnings=["ElmerFEM not available; using lightweight thermal estimate."],
        errors=[],
        metrics={
            "thermal_resistance_c_per_w": theta,
            "max_temperature_c": thermal_result.max_temperature_c or 0.0,
            "surface_area_mm2": thermal_result.total_surface_area_mm2 or 0.0,
            "fin_count": float(thermal_result.fin_count or 0),
        },
        failure_modes=["excessive_thermal_resistance"] if not passed else [],
        redesign_suggestions=_extract_thermal_suggestions(thermal_result, request),
        raw_output={"solver": thermal_result.solver, **thermal_result.details},
    )


def _cfd_estimate(
    request: VerificationRequest,
    stl_path: Path,
    mesh: trimesh.Trimesh | None,
) -> VerificationResult:
    velocity = float(request.parameters.get("velocity_m_s", 10.0))

    cfd_result = cfd.export_cfd_mesh_from_stl(
        stl_path,
        Path(tempfile.mkdtemp(prefix="robocad_cfd_")),
        solver="openfoam_stub",
        flow_velocity_ms=velocity,
        characteristic_length_m=0.1,
    )

    ref = cfd_result.reference_values
    reynolds = ref.get("reynolds_number", 1e5)
    cd_est = min(1.2, max(0.1, 24.0 / max(reynolds, 1.0)))
    frontal_m2 = float(mesh.area) * 1e-6 if mesh else 0.001
    rho = 1.225
    drag_force = 0.5 * rho * velocity**2 * frontal_m2 * cd_est

    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=True,
        warnings=["OpenFOAM not available; using empirical drag estimate."],
        errors=cfd_result.errors if not cfd_result.success else [],
        metrics={
            "drag_coefficient": round(cd_est, 4),
            "drag_force_n": round(drag_force, 6),
            "reynolds_number": float(reynolds),
            "flow_velocity_ms": velocity,
        },
        failure_modes=[],
        redesign_suggestions=_extract_cfd_suggestions(cd_est, request),
        raw_output={"solver": cfd_result.solver, **ref},
    )


# ---------------------------------------------------------------------------
# Result conversion helpers
# ---------------------------------------------------------------------------

def _solver_result_to_verification(
    request: VerificationRequest,
    solver_result: calculix_adapter.SolverResult | elmerfem_adapter.SolverResult,
    target_sf: float = 2.0,
    target_theta: float = 10.0,
    ambient: float = 25.0,
    heat_flux: float = 10.0,
    nodes: np.ndarray | None = None,
    suggestions: list[str] | None = None,
) -> VerificationResult:
    metrics = dict(solver_result.metrics)
    passed = True
    warnings: list[str] = []
    errors = list(solver_result.errors)
    failure_modes: list[str] = []

    if "safety_factor" in metrics:
        if metrics["safety_factor"] < target_sf:
            passed = False
            failure_modes.append("yield_exceeded")
    elif "max_stress_mpa" in metrics:
        try:
            mat = get_material(_resolve_material(request).name)
            sf = mat.yield_strength_mpa / max(metrics["max_stress_mpa"], 1e-12)
            metrics["safety_factor"] = sf
            if sf < target_sf:
                passed = False
                failure_modes.append("yield_exceeded")
        except Exception:
            pass

    if "max_temperature_c" in metrics and "min_temperature_c" in metrics:
        max_temp = metrics["max_temperature_c"]
        theta = (max_temp - ambient) / max(heat_flux, 1e-12)
        metrics["thermal_resistance_c_per_w"] = round(theta, 4)
        if theta > target_theta:
            passed = False
            failure_modes.append("excessive_thermal_resistance")

    if solver_result.errors:
        warnings.append("Real solver produced errors; inspect logs before trusting results.")
        if not metrics:
            passed = False

    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=passed,
        warnings=warnings,
        errors=errors,
        metrics=metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions or [],
        raw_output={
            "solver": solver_result.solver,
            "node_coordinates": (nodes.tolist() if nodes is not None else None),
            **solver_result.model_dump(),
        },
    )


def _extract_structural_suggestions_from_solver(
    solver_result: calculix_adapter.SolverResult,
    target_sf: float,
) -> list[str]:
    suggestions: list[str] = []
    sf = solver_result.metrics.get("safety_factor", 0.0)
    max_disp = solver_result.metrics.get("max_displacement_mm", 0.0)
    if sf < target_sf:
        suggestions.append("Increase wall thickness or add ribs in the bending direction.")
        suggestions.append("Switch to a stronger material (e.g., PETG, Nylon, or aluminum).")
        suggestions.append("Reduce unsupported span or add a gusset/bracket.")
    if max_disp > 1.0:
        suggestions.append("Increase moment of inertia to limit deflection.")
    return suggestions


def _extract_thermal_suggestions_from_solver(
    solver_result: elmerfem_adapter.SolverResult,
    target_theta: float,
) -> list[str]:
    suggestions: list[str] = []
    theta = solver_result.metrics.get("thermal_resistance_c_per_w", 0.0)
    if theta > target_theta:
        suggestions.append("Increase total fin surface area or fin count.")
        suggestions.append("Improve airflow (higher convection coefficient) over the heat sink.")
        suggestions.append("Use a higher-conductivity material such as aluminum or copper.")
    return suggestions


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_LOAD_CASE_ROUTING: dict[LoadCase, str] = {
    LoadCase.STATIC_STRESS: "calculix",
    LoadCase.DROP_TEST: "calculix",
    LoadCase.THERMAL_EXPANSION: "elmer",
    LoadCase.FATIGUE_CYCLES: "calculix",
    LoadCase.FASTENER_PULL_OUT: "calculix",
    LoadCase.HEAT_SINK_THERMAL_RESISTANCE: "elmer",
    LoadCase.WIND_TUNNEL_DRAG: "openfoam",
}


def _quantity_for_load_case(load_case: LoadCase) -> str:
    if load_case in {
        LoadCase.STATIC_STRESS,
        LoadCase.DROP_TEST,
        LoadCase.FATIGUE_CYCLES,
        LoadCase.FASTENER_PULL_OUT,
    }:
        return "stress"
    if load_case in {LoadCase.HEAT_SINK_THERMAL_RESISTANCE, LoadCase.THERMAL_EXPANSION}:
        return "thermal"
    if load_case == LoadCase.WIND_TUNNEL_DRAG:
        return "drag"
    return "value"


class DeepVerificationDispatcher:
    """Routes requests to deep adapters and records jobs."""

    def __init__(
        self,
        job_store: JobStore | None = None,
        surrogate: NvidiaSurrogate | None = None,
    ) -> None:
        self.job_store = job_store or JobStore()
        self.adapters: dict[str, DeepAdapter] = {
            "calculix": CalculiXAdapter(),
            "elmer": ElmerAdapter(),
            "openfoam": OpenFOAMAdapter(),
            "surrogate": SurrogateAdapter(surrogate=surrogate),
        }

    def solver_type_for(self, request: VerificationRequest) -> str:
        explicit = request.parameters.get("solver")
        if explicit and explicit in self.adapters:
            return str(explicit)
        return _LOAD_CASE_ROUTING.get(request.load_case, "surrogate")

    def adapter_for(self, request: VerificationRequest) -> DeepAdapter:
        return self.adapters[self.solver_type_for(request)]

    def run_sync(
        self,
        request: VerificationRequest,
        design_dir: Path,
        job_id: str | None = None,
    ) -> VerificationResult:
        """Run a deep verification synchronously and persist a completed job."""
        solver_type = self.solver_type_for(request)
        if job_id is None:
            job_id = self.job_store.submit(request, solver_type)

        mesh = _load_mesh(design_dir)
        adapter = self.adapter_for(request)

        self.job_store.update(job_id, status=JobStatus.RUNNING, progress=0.25)

        try:
            result = adapter.run(request, design_dir, mesh)
            self.job_store.update(
                job_id,
                status=JobStatus.COMPLETED if result.passed else JobStatus.FAILED,
                progress=1.0,
                result=result.model_dump(),
            )
            result.report_id = job_id
            return result
        except Exception as exc:
            self.job_store.update(
                job_id,
                status=JobStatus.FAILED,
                progress=1.0,
                error=str(exc),
            )
            return _error(request, f"Deep solver failed: {exc}")

    def submit(
        self,
        request: VerificationRequest,
        design_dir: Path,
    ) -> str:
        """Submit an async job and start a background thread."""
        solver_type = self.solver_type_for(request)
        job_id = self.job_store.submit(request, solver_type)

        def _run() -> None:
            self.run_sync(request, design_dir, job_id=job_id)

        threading.Thread(target=_run, daemon=True).start()
        return job_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_deep_verification(
    request: VerificationRequest,
    design_dir: Path | None = None,
    job_store: JobStore | None = None,
) -> str:
    """Submit a deep verification job asynchronously."""
    if design_dir is None:
        design_dir = Path("designs") / request.design_id
    dispatcher = DeepVerificationDispatcher(job_store=job_store)
    return dispatcher.submit(request, design_dir)


def poll_deep_verification(
    job_id: str,
    job_store: JobStore | None = None,
) -> VerificationJob | None:
    """Poll the job store for current job status and result."""
    store = job_store or JobStore()
    return store.get(job_id)


def cancel_deep_verification(
    job_id: str,
    job_store: JobStore | None = None,
) -> bool:
    """Cancel a queued or running deep verification job."""
    store = job_store or JobStore()
    return store.cancel(job_id)


def solver_availability() -> dict[str, Any]:
    """Return availability and version/path info for each deep solver."""
    def _which(name: str) -> str | None:
        return shutil.which(name)

    ccx = calculix_adapter._find_ccx()
    elmer = elmerfem_adapter._find_elmer()
    foam = openfoam_adapter._local_openfoam_available("simpleFoam")

    return {
        "solvers": [
            {
                "name": "calculix",
                "available": ccx is not None,
                "path": ccx,
                "binaries": list(calculix_adapter.CCX_BINARIES),
            },
            {
                "name": "elmer",
                "available": elmer is not None,
                "path": elmer,
                "binaries": list(elmerfem_adapter.ELMER_BINARIES),
            },
            {
                "name": "openfoam",
                "available": foam,
                "path": shutil.which("simpleFoam") or shutil.which("foamRun"),
                "binaries": ["simpleFoam", "foamRun"],
            },
            {"name": "surrogate", "available": True},
        ]
    }


def run_deep_verification(
    design_id: str,
    load_case: str | LoadCase,
    params: dict[str, Any] | None = None,
    design_dir: Path | None = None,
    job_store: JobStore | None = None,
) -> VerificationResult:
    """High-level synchronous entry point for deep verification."""
    lc = load_case if isinstance(load_case, LoadCase) else LoadCase(load_case)
    request = VerificationRequest(
        design_id=design_id,
        load_case=lc,
        parameters=params or {},
    )
    if design_dir is None:
        design_dir = Path("designs") / design_id
    dispatcher = DeepVerificationDispatcher(job_store=job_store)
    return dispatcher.run_sync(request, design_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_stl_path(design_dir: Path) -> Path | None:
    candidates = [
        design_dir / "exports" / "model.stl",
        design_dir / "model.stl",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_mesh(design_dir: Path) -> trimesh.Trimesh | None:
    stl_path = _resolve_stl_path(design_dir)
    if stl_path is None:
        return None
    try:
        mesh = trimesh.load_mesh(str(stl_path))
    except Exception:
        return None
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            return next(iter(mesh.geometry.values()))
        return None
    return mesh


def _resolve_material(request: VerificationRequest, default: str = "PLA") -> Material:
    name = request.parameters.get("material", default)
    if request.materials:
        name = next(iter(request.materials.values()))
    try:
        return get_material(name)
    except KeyError:
        return get_material(default)


def _error(request: VerificationRequest, message: str) -> VerificationResult:
    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=False,
        errors=[message],
        metrics={},
        redesign_suggestions=["Verify the design has a valid STL export and retry."],
    )


def _extract_structural_suggestions(fea_result: fea.FEAResult, request: VerificationRequest) -> list[str]:
    suggestions: list[str] = []
    sf = fea_result.safety_factor
    target = float(request.parameters.get("safety_factor_target", 2.0))
    if sf is None or sf < target:
        suggestions.append("Increase wall thickness or add ribs in the bending direction.")
        suggestions.append("Switch to a stronger material (e.g., PETG, Nylon, or aluminum).")
        suggestions.append("Reduce unsupported span or add a gusset/bracket.")
    if fea_result.max_displacement_mm and fea_result.max_displacement_mm > 1.0:
        suggestions.append("Increase moment of inertia to limit deflection.")
    return suggestions


def _extract_thermal_suggestions(thermal_result: thermal.ThermalResult, request: VerificationRequest) -> list[str]:
    suggestions: list[str] = []
    target = float(request.parameters.get("target_theta_c_per_w", 10.0))
    theta = thermal_result.thermal_resistance_c_per_w
    if theta is not None and theta > target:
        suggestions.append("Increase total fin surface area or fin count.")
        suggestions.append("Improve airflow (higher convection coefficient) over the heat sink.")
        suggestions.append("Use a higher-conductivity material such as aluminum or copper.")
    return suggestions


def _extract_cfd_suggestions(cd: float, request: VerificationRequest) -> list[str]:
    suggestions: list[str] = []
    if cd > 0.5:
        suggestions.append("Streamline leading edges and reduce frontal area.")
        suggestions.append("Add fairings or remove blunt protrusions.")
    return suggestions


def _extract_surrogate_suggestions(prediction: dict[str, Any], request: VerificationRequest) -> list[str]:
    suggestions: list[str] = []
    if "safety_factor" in prediction and prediction["safety_factor"] < 2.0:
        suggestions.append("Increase structural section to raise safety factor.")
    if "max_temperature_c" in prediction and prediction["max_temperature_c"] > 80.0:
        suggestions.append("Increase cooling surface area or improve convection.")
    if "drag_coefficient" in prediction and prediction["drag_coefficient"] > 0.5:
        suggestions.append("Reduce frontal area or round leading edges.")
    if not suggestions:
        suggestions.append("Surrogate estimate complete; review metrics before detailed simulation.")
    return suggestions
