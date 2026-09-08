"""Async deep verification dispatcher for RoboCAD Phase 28C.

This module dispatches closed load cases to pluggable deep adapters:
CalculiX (structural), Elmer (thermal), OpenFOAM (CFD), and a NVIDIA NIM
surrogate fallback. It integrates with the existing VerificationRequest and
VerificationResult models and records every run in the SQLite job store.
"""
from __future__ import annotations

import shutil
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import trimesh

from ai_cad import cfd, fea, thermal
from ai_cad.materials import Material, get_material
from ai_cad.solvers.job_store import JobStatus, JobStore, VerificationJob
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
    """Structural deep adapter backed by the lightweight FEA stub."""

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

        material = _resolve_material(request)
        fixed_face = request.parameters.get("fixed_face", "-x")
        load = float(request.parameters.get("load_magnitude_n", 100.0))

        fea_result = fea.run_static_analysis(
            stl_path,
            fixed_face=fixed_face,
            load_magnitude_n=load,
            material=material.name,
        )

        target_sf = float(request.parameters.get("safety_factor_target", 2.0))
        passed = bool(
            fea_result.success
            and fea_result.safety_factor is not None
            and fea_result.safety_factor >= target_sf
        )
        suggestions = _extract_structural_suggestions(fea_result, request)

        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=passed,
            warnings=[],
            errors=fea_result.errors if not fea_result.success else [],
            metrics={
                "max_stress_mpa": fea_result.max_stress_mpa or 0.0,
                "max_displacement_mm": fea_result.max_displacement_mm or 0.0,
                "safety_factor": fea_result.safety_factor or 0.0,
            },
            failure_modes=["yield_exceeded"] if not passed else [],
            redesign_suggestions=suggestions,
            raw_output={"solver": fea_result.solver, **fea_result.details},
        )


class ElmerAdapter(DeepAdapter):
    """Thermal deep adapter backed by the lightweight thermal stub."""

    name = "elmer"
    supported_load_cases = [LoadCase.HEAT_SINK_THERMAL_RESISTANCE]

    def run(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        stl_path = _resolve_stl_path(design_dir)
        if stl_path is None:
            return _error(request, "No STL export found for deep thermal analysis.")

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
        suggestions = _extract_thermal_suggestions(thermal_result, request)

        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=passed,
            warnings=[],
            errors=[],
            metrics={
                "thermal_resistance_c_per_w": theta,
                "max_temperature_c": thermal_result.max_temperature_c or 0.0,
                "surface_area_mm2": thermal_result.total_surface_area_mm2 or 0.0,
                "fin_count": float(thermal_result.fin_count or 0),
            },
            failure_modes=["excessive_thermal_resistance"] if not passed else [],
            redesign_suggestions=suggestions,
            raw_output={"solver": thermal_result.solver, **thermal_result.details},
        )


class OpenFOAMAdapter(DeepAdapter):
    """CFD deep adapter: export OpenFOAM case stub and estimate drag."""

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

        velocity = float(request.parameters.get("velocity_m_s", 10.0))
        output_dir = design_dir / "deep_cfd"
        output_dir.mkdir(parents=True, exist_ok=True)

        cfd_result = cfd.export_cfd_mesh_from_stl(
            stl_path,
            output_dir,
            solver="openfoam_stub",
            flow_velocity_ms=velocity,
            characteristic_length_m=0.1,
        )

        if not cfd_result.success:
            return VerificationResult(
                design_id=request.design_id,
                load_case=request.load_case,
                passed=False,
                errors=cfd_result.errors,
                metrics={},
                redesign_suggestions=["Check surface mesh quality and retry."],
            )

        ref = cfd_result.reference_values
        reynolds = ref.get("reynolds_number", 1e5)
        # Drag coefficient rough estimate: 24/Re for laminar sphere baseline,
        # capped to a blunt-body upper bound of 1.2.
        cd_est = min(1.2, max(0.1, 24.0 / max(reynolds, 1.0)))
        frontal_m2 = float(mesh.area) * 1e-6 if mesh else 0.001
        rho = 1.225
        drag_force = 0.5 * rho * velocity**2 * frontal_m2 * cd_est

        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=True,
            warnings=["OpenFOAM case is a stub; run real solver for high-fidelity drag."],
            errors=[],
            metrics={
                "drag_coefficient": round(cd_est, 4),
                "drag_force_n": round(drag_force, 6),
                "reynolds_number": float(reynolds),
                "flow_velocity_ms": velocity,
            },
            failure_modes=[],
            redesign_suggestions=_extract_cfd_suggestions(cd_est, request),
            raw_output={
                "solver": cfd_result.solver,
                "mesh_path": str(cfd_result.mesh_path) if cfd_result.mesh_path else None,
                "config_path": str(cfd_result.solver_config_path) if cfd_result.solver_config_path else None,
                **ref,
            },
        )


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
# Dispatcher
# ---------------------------------------------------------------------------

_LOAD_CASE_ROUTING: dict[LoadCase, str] = {
    LoadCase.STATIC_STRESS: "calculix",
    LoadCase.DROP_TEST: "calculix",
    LoadCase.THERMAL_EXPANSION: "calculix",
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
        """Run a deep verification synchronously and persist a completed job.

        If ``job_id`` is provided, that job record is updated in place instead of
        creating a new one. This lets async submission reuse the pending job id.
        """
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
    """Return availability of each deep-analysis solver backend."""
    return {
        "solvers": [
            {"name": "calculix", "available": shutil.which("ccx") is not None},
            {"name": "elmer", "available": shutil.which("ElmerSolver") is not None},
            {"name": "openfoam", "available": shutil.which("simpleFoam") is not None or shutil.which("foamRun") is not None},
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
    """High-level synchronous entry point for deep verification.

    Args:
        design_id: persisted design identifier.
        load_case: LoadCase enum or string name.
        params: case-specific parameters; may include ``solver`` to force an adapter.
        design_dir: optional explicit design directory.
        job_store: optional JobStore instance.

    Returns:
        VerificationResult with metrics, pass/fail, and redesign suggestions.
    """
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
