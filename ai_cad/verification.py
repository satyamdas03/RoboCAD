"""Multi-physics verification engine for RoboCAD.

The engine dispatches deterministic closed load-case templates to lightweight
backends (structural formulas, thermal formulas, CFD estimates, multibody
estimates). It is intentionally not a replacement for commercial solvers: every
backend is a pre-solver gate that fails bad geometry fast and produces redesign
suggestions.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from pathlib import Path
from typing import Any

import trimesh

from ai_cad.assembly_collision import check_assembly_collision
from ai_cad.materials import Material, get_material
from ai_cad.mesh_quality import check_mesh_quality
from ai_cad.verification_load_cases import (
    drop_test,
    fastener_pull_out,
    fatigue_cycles,
    gait_feasibility_check,
    heat_sink_thermal_resistance,
    humanoid_stability_check,
    joint_torque_check,
    reachable_workspace_check,
    static_stress,
    thermal_expansion,
    wind_tunnel_drag,
)
from ai_cad.verification_models import LoadCase, MeshQualityReport, VerificationRequest, VerificationResult


# ---------------------------------------------------------------------------
# Bounded in-memory report cache with TTL and LRU eviction.
# ---------------------------------------------------------------------------
class _TimedLRUCache:
    """Thread-safe LRU cache with a per-entry TTL in seconds."""

    def __init__(self, maxsize: int = 128, ttl_seconds: float = 600.0):
        self.maxsize = max(maxsize, 1)
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        self._store: OrderedDict[str, tuple[float, VerificationResult]] = OrderedDict()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, (expires_at, _) in self._store.items() if now > expires_at]
        for key in expired:
            self._store.pop(key, None)

    def get(self, key: str) -> VerificationResult | None:
        with self._lock:
            self._evict_expired()
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            # Move to end (most recently used).
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: VerificationResult) -> None:
        with self._lock:
            self._evict_expired()
            self._store[key] = (time.monotonic() + self.ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired()
            return len(self._store)


_REPORTS = _TimedLRUCache(maxsize=128, ttl_seconds=600.0)


def get_report(report_id: str) -> VerificationResult | None:
    """Retrieve a cached verification report by id."""
    return _REPORTS.get(report_id)


# ---------------------------------------------------------------------------
# Solver backend abstraction
# ---------------------------------------------------------------------------

class SolverBackend(ABC):
    """Base class for a verification backend."""

    name: str
    supported_load_cases: list[LoadCase]

    @abstractmethod
    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        ...


class StructuralFormulaBackend(SolverBackend):
    """Deterministic structural checks using simple mechanics formulas."""

    name = "structural_formula"
    supported_load_cases = [
        LoadCase.STATIC_STRESS,
        LoadCase.DROP_TEST,
        LoadCase.THERMAL_EXPANSION,
        LoadCase.FATIGUE_CYCLES,
        LoadCase.FASTENER_PULL_OUT,
    ]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        if mesh is None:
            return _error(request, "No mesh available for structural analysis.")
        material = _resolve_material(request)
        case = request.load_case
        if case == LoadCase.STATIC_STRESS:
            return static_stress(request.design_id, mesh, material, request.parameters)
        if case == LoadCase.DROP_TEST:
            return drop_test(request.design_id, mesh, material, request.parameters)
        if case == LoadCase.THERMAL_EXPANSION:
            return thermal_expansion(request.design_id, mesh, material, request.parameters)
        if case == LoadCase.FATIGUE_CYCLES:
            return fatigue_cycles(request.design_id, mesh, material, request.parameters)
        if case == LoadCase.FASTENER_PULL_OUT:
            return fastener_pull_out(request.design_id, mesh, material, request.parameters)
        return _error(request, f"Unsupported structural load case: {case}")


class ThermalFormulaBackend(SolverBackend):
    """Deterministic thermal checks using fin/surface resistance formulas."""

    name = "thermal_formula"
    supported_load_cases = [LoadCase.HEAT_SINK_THERMAL_RESISTANCE]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        if mesh is None:
            return _error(request, "No mesh available for thermal analysis.")
        material = _resolve_material(request, default="Aluminum 6061")
        return heat_sink_thermal_resistance(
            request.design_id, mesh, material, request.parameters
        )


class CFDEstimateBackend(SolverBackend):
    """Lightweight aero/CFD estimates from mesh frontal area."""

    name = "cfd_estimate"
    supported_load_cases = [LoadCase.WIND_TUNNEL_DRAG]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        if mesh is None:
            return _error(request, "No mesh available for CFD estimate.")
        material = _resolve_material(request, default="PLA")
        return wind_tunnel_drag(request.design_id, mesh, material, request.parameters)


class MultibodyEstimateBackend(SolverBackend):
    """Joint/actuator capacity checks using kinematic data."""

    name = "multibody_estimate"
    supported_load_cases = [LoadCase.JOINT_TORQUE_CHECK]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        # This backend does not strictly require a mesh; use a placeholder.
        material = _resolve_material(request, default="PLA")
        if mesh is None:
            # Create a nominal 1 mm cube mesh so the formula can still run.
            mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
        return joint_torque_check(request.design_id, mesh, material, request.parameters)


class MeshQualityBackend(SolverBackend):
    """Mesh-quality pre-check backend."""

    name = "mesh_quality"
    supported_load_cases = [LoadCase.MESH_QUALITY]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        if mesh is None:
            stl_path = _resolve_stl_path(request.design_id, design_dir)
            if not stl_path or not stl_path.exists():
                return _error(request, "No STL export found for mesh-quality check.")
            report = check_mesh_quality(stl_path)
        else:
            report = check_mesh_quality(mesh)
        passed = report.is_suitable_for_solver
        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=passed,
            warnings=[],
            errors=report.issues if not passed else [],
            metrics={
                "triangle_count": float(report.triangle_count),
                "non_manifold_edges": float(report.non_manifold_edges),
                "degenerate_triangles": float(report.degenerate_triangles),
                "high_aspect_ratio_triangles": float(report.high_aspect_ratio_triangles),
            },
            failure_modes=["mesh_quality_issue"] if not passed else [],
            redesign_suggestions=["Remesh the part with smaller tolerance."] if not passed else [],
            mesh_report=report,
        )


class AssemblyClearanceBackend(SolverBackend):
    """Assembly-level clearance/interference backend."""

    name = "assembly_clearance"
    supported_load_cases = [LoadCase.ASSEMBLY_CLEARANCE]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        feature_tree_path = design_dir / "feature_tree.json"
        if not feature_tree_path.exists():
            return _error(request, "No feature tree found for assembly clearance check.")
        try:
            from ai_cad.feature_tree import FeatureTree

            tree = FeatureTree(**json.loads(feature_tree_path.read_text(encoding="utf-8")))
        except Exception as exc:
            return _error(request, f"Failed to load feature tree: {exc}")
        if not tree.assemblies:
            return _error(request, "No assembly found for clearance check.")
        try:
            reports = check_assembly_collision(tree, design_dir / "collision", samples=500)
        except Exception as exc:
            return _error(request, f"Failed to run collision check: {exc}")
        pairs = [r.model_dump() for r in reports]
        worst = min(pairs, key=lambda p: p["min_clearance_mm"]) if pairs else None
        min_clearance = worst["min_clearance_mm"] if worst else float("inf")
        passed = min_clearance >= request.parameters.get("clearance_threshold_mm", 0.05)
        return VerificationResult(
            design_id=request.design_id,
            load_case=request.load_case,
            passed=passed,
            warnings=[],
            errors=[],
            metrics={"pair_count": float(len(pairs)), "min_clearance_mm": min_clearance},
            failure_modes=["assembly_interference"] if not passed else [],
            redesign_suggestions=["Check mate offsets and part tolerances."] if not passed else [],
            raw_output={"pairs": pairs, "worst": worst},
        )


class RoboticEstimateBackend(SolverBackend):
    """Humanoid / legged robot checks using the kinematic tree and stability gate."""

    name = "robotic_estimate"
    supported_load_cases = [
        LoadCase.STABILITY_CHECK,
        LoadCase.REACHABLE_WORKSPACE,
        LoadCase.GAIT_FEASIBILITY,
    ]

    def solve(
        self,
        request: VerificationRequest,
        design_dir: Path,
        mesh: trimesh.Trimesh | None,
    ) -> VerificationResult:
        feature_tree_path = design_dir / "feature_tree.json"
        if not feature_tree_path.exists():
            return _error(request, "No feature tree found for robotic check.")
        try:
            from ai_cad.feature_tree import FeatureTree

            tree = FeatureTree(**json.loads(feature_tree_path.read_text(encoding="utf-8")))
        except Exception as exc:
            return _error(request, f"Failed to load feature tree: {exc}")

        case = request.load_case
        if case == LoadCase.STABILITY_CHECK:
            return humanoid_stability_check(request.design_id, tree, request.parameters)
        if case == LoadCase.REACHABLE_WORKSPACE:
            return reachable_workspace_check(request.design_id, tree, request.parameters)
        if case == LoadCase.GAIT_FEASIBILITY:
            return gait_feasibility_check(request.design_id, tree, request.parameters)
        return _error(request, f"Unsupported robotic load case: {case}")


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

_BACKENDS: dict[LoadCase, SolverBackend] = {}


def _register_backend(backend: SolverBackend) -> None:
    for case in backend.supported_load_cases:
        _BACKENDS[case] = backend


_register_backend(StructuralFormulaBackend())
_register_backend(ThermalFormulaBackend())
_register_backend(CFDEstimateBackend())
_register_backend(MultibodyEstimateBackend())
_register_backend(RoboticEstimateBackend())
_register_backend(MeshQualityBackend())
_register_backend(AssemblyClearanceBackend())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _load_single_mesh(stl_path: Path) -> trimesh.Trimesh | None:
    """Load an STL file and normalize a trimesh.Scene to a single Trimesh."""
    try:
        loaded = trimesh.load_mesh(stl_path)
    except Exception:
        return None
    if isinstance(loaded, trimesh.Scene):
        if len(loaded.geometry) == 1:
            return next(iter(loaded.geometry.values()))
        return None
    return loaded


class _MeshCache:
    """Load an STL mesh once and share it across backends in one request."""

    def __init__(self, stl_path: Path | None):
        self.stl_path = stl_path
        self._mesh: trimesh.Trimesh | None = None
        self._loaded = False

    @property
    def mesh(self) -> trimesh.Trimesh | None:
        if not self._loaded and self.stl_path and self.stl_path.exists():
            self._mesh = _load_single_mesh(self.stl_path)
            self._loaded = True
        return self._mesh


def _resolve_stl_path(design_id: str, design_dir: Path | None = None) -> Path | None:
    """Locate the default STL export for a design."""
    if design_dir is None:
        # Default layout used by web/backend/main.py.
        design_dir = Path("designs") / design_id
    candidates = [
        design_dir / "exports" / "model.stl",
        design_dir / "model.stl",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_material(request: VerificationRequest, default: str = "PLA") -> Material:
    """Pick a material from the request map or use the default."""
    name = request.parameters.get("material", default)
    # If a per-part material map is provided, prefer the first part's material.
    if request.materials:
        name = next(iter(request.materials.values()))
    return get_material(name)


def _error(request: VerificationRequest, message: str) -> VerificationResult:
    return VerificationResult(
        design_id=request.design_id,
        load_case=request.load_case,
        passed=False,
        errors=[message],
        metrics={},
    )


def run_verification(
    request: VerificationRequest,
    design_dir: Path | None = None,
) -> VerificationResult:
    """Run a single verification load case and return a structured report.

    Args:
        request: VerificationRequest with design_id, load_case, and parameters.
        design_dir: optional explicit design directory; defaults to designs/{id}.

    Returns:
        VerificationResult with metrics, pass/fail, and redesign suggestions.
    """
    if design_dir is None:
        design_dir = Path("designs") / request.design_id

    backend = _BACKENDS.get(request.load_case)
    if backend is None:
        return _error(request, f"No backend registered for load case: {request.load_case}")

    stl_path = _resolve_stl_path(request.design_id, design_dir)
    mesh_cache = _MeshCache(stl_path)

    result = backend.solve(request, design_dir, mesh_cache.mesh)
    # Always attach a report id and cache it.
    report_id = uuid.uuid4().hex
    result.report_id = report_id
    _REPORTS.set(report_id, result)
    return result
