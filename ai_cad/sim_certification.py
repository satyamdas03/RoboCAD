"""Simulation certification engine for RoboCAD Phase 28E.

A certification run exercises a design against a closed suite of multi-physics
load cases. It can compare real solver results against the surrogate estimate
(A/B mode), computes a readiness score, and persists a signed-ish certificate
JSON that can be downloaded from the frontend.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.solvers.job_store import JobStore
from ai_cad.solvers.verification_deep import run_deep_verification, solver_availability
from ai_cad.verification import run_verification
from ai_cad.verification_models import LoadCase, VerificationRequest, VerificationResult


# Default certification suite.
CERTIFICATION_LOAD_CASES: list[LoadCase] = [
    LoadCase.MESH_QUALITY,
    LoadCase.STATIC_STRESS,
    LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
    LoadCase.WIND_TUNNEL_DRAG,
]


@dataclass
class CheckResult:
    """Result of one certification check."""

    name: str
    passed: bool
    score: float
    weight: float
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class CertificationResult:
    """Outcome of a full simulation certification run."""

    cert_id: str
    design_id: str
    score: float
    passed: bool
    checks: list[CheckResult]
    load_case_results: list[dict[str, Any]]
    ab_comparisons: list[dict[str, Any]]
    certificate_path: Path | None = None
    created_at: float = field(default_factory=time.time)

    def model_dump(self) -> dict[str, Any]:
        return {
            "cert_id": self.cert_id,
            "design_id": self.design_id,
            "score": round(self.score, 2),
            "passed": self.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "score": round(c.score, 2),
                    "weight": c.weight,
                    "details": c.details,
                    "errors": c.errors,
                }
                for c in self.checks
            ],
            "load_case_results": self.load_case_results,
            "ab_comparisons": self.ab_comparisons,
            "certificate_path": str(self.certificate_path) if self.certificate_path else None,
            "created_at": self.created_at,
        }


def _safe_metric(result: dict[str, Any], key: str) -> float | None:
    value = result.get("metrics", {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _run_load_case(
    design_id: str,
    design_dir: Path,
    load_case: LoadCase,
    solver_mode: str,
    parameters: dict[str, Any],
    job_store: JobStore,
) -> dict[str, Any]:
    params = {**parameters, "solver_mode": solver_mode}
    if load_case == LoadCase.MESH_QUALITY:
        request = VerificationRequest(
            design_id=design_id,
            load_case=load_case,
            parameters=params,
        )
        result = run_verification(request, design_dir=design_dir)
    else:
        result = run_deep_verification(
            design_id=design_id,
            load_case=load_case,
            params=params,
            design_dir=design_dir,
            job_store=job_store,
        )
    return result.model_dump(mode="json")


def _compare_ab(
    real_result: dict[str, Any],
    surrogate_result: dict[str, Any],
    metric_keys: list[str],
    rtol: float = 0.25,
) -> dict[str, Any]:
    """Compare real and surrogate metrics, returning per-key agreement."""
    comparisons: dict[str, Any] = {}
    discrepancies: list[str] = []
    for key in metric_keys:
        real = _safe_metric(real_result, key)
        surr = _safe_metric(surrogate_result, key)
        if real is None or surr is None or abs(real) < 1e-12:
            comparisons[key] = {"real": real, "surrogate": surr, "agreement": None}
            continue
        diff = abs(real - surr) / abs(real)
        comparisons[key] = {"real": real, "surrogate": surr, "agreement": 1.0 - min(diff, 1.0)}
        if diff > rtol:
            discrepancies.append(f"{key}: real={real:.4g} vs surrogate={surr:.4g} (diff={diff:.1%})")

    return {
        "load_case": real_result.get("load_case"),
        "metric_comparisons": comparisons,
        "discrepancies": discrepancies,
        "agreement_ok": len(discrepancies) == 0,
    }


def run_certification(
    design_id: str,
    design_dir: Path,
    job_store: JobStore | None = None,
    load_cases: list[LoadCase] | None = None,
    parameters: dict[str, Any] | None = None,
    ab_mode: bool = True,
    output_dir: Path | None = None,
) -> CertificationResult:
    """Run the simulation certification suite and return a scored certificate.

    Args:
        design_id: persisted design identifier.
        design_dir: directory holding the design files.
        job_store: optional shared JobStore.
        load_cases: list of load cases to run; defaults to a representative suite.
        parameters: base parameters for all load cases.
        ab_mode: if True, also run surrogate and compare against real results.
        output_dir: directory to write the certificate JSON.

    Returns:
        CertificationResult with score, per-check results, and persisted path.
    """
    job_store = job_store or JobStore()
    load_cases = load_cases if load_cases is not None else CERTIFICATION_LOAD_CASES
    parameters = parameters or {}
    if output_dir is None:
        output_dir = design_dir / "certificates"
    output_dir.mkdir(parents=True, exist_ok=True)

    availability = solver_availability()
    real_available = {s["name"]: s["available"] for s in availability.get("solvers", [])}

    checks: list[CheckResult] = []
    load_case_results: list[dict[str, Any]] = []
    ab_comparisons: list[dict[str, Any]] = []

    # Real-solver availability check.
    real_names = [name for name, available in real_available.items() if available and name != "surrogate"]
    availability_score = min(len(real_names) / 3.0, 1.0)
    checks.append(
        CheckResult(
            name="real_solver_availability",
            passed=availability_score >= 0.5,
            score=availability_score,
            weight=0.15,
            details={"available_solvers": real_names},
        )
    )

    # Run each load case.
    case_passed = 0
    case_total = 0
    for load_case in load_cases:
        case_total += 1
        auto_result = _run_load_case(
            design_id, design_dir, load_case, "auto", parameters, job_store
        )
        load_case_results.append({"mode": "auto", "result": auto_result})

        passed = auto_result.get("passed", False)
        if passed:
            case_passed += 1

        # A/B comparison when a real solver was used.
        raw_output = auto_result.get("raw_output") or {}
        solver_used = (
            raw_output.get("solver")
            or (raw_output.get("details") or {}).get("solver")
        )
        if ab_mode and solver_used not in (None, "", "surrogate"):
            surrogate_result = _run_load_case(
                design_id, design_dir, load_case, "surrogate", parameters, job_store
            )
            metric_keys = list(auto_result.get("metrics", {}).keys())
            comparison = _compare_ab(auto_result, surrogate_result, metric_keys)
            ab_comparisons.append(comparison)

    # Load-case pass-rate check.
    pass_rate = case_passed / max(case_total, 1)
    checks.append(
        CheckResult(
            name="load_case_pass_rate",
            passed=pass_rate >= 0.75,
            score=pass_rate,
            weight=0.50,
            details={"passed": case_passed, "total": case_total},
        )
    )

    # Mesh quality check from the first mesh_quality result if present.
    mesh_result = next((r for r in load_case_results if r["result"].get("load_case") == "mesh_quality"), None)
    if mesh_result:
        mesh_report = mesh_result["result"].get("mesh_report", {})
        mesh_ok = bool(mesh_report.get("is_suitable_for_solver", False))
        checks.append(
            CheckResult(
                name="mesh_quality",
                passed=mesh_ok,
                score=1.0 if mesh_ok else 0.0,
                weight=0.15,
                details={
                    "watertight": mesh_report.get("watertight"),
                    "triangle_count": mesh_report.get("triangle_count"),
                    "issues": mesh_report.get("issues", []),
                },
            )
        )
    else:
        checks.append(
            CheckResult(
                name="mesh_quality",
                passed=True,
                score=1.0,
                weight=0.15,
                details={"note": "mesh_quality load case not included in this run"},
            )
        )

    # Safety margin bonus.
    sf_values: list[float] = []
    for r in load_case_results:
        sf = _safe_metric(r["result"], "safety_factor")
        if sf is not None:
            sf_values.append(sf)
    if sf_values:
        min_sf = min(sf_values)
        margin_score = min(min_sf / 2.0, 1.0)
    else:
        margin_score = 1.0
    checks.append(
        CheckResult(
            name="safety_factor_margin",
            passed=margin_score >= 0.8,
            score=margin_score,
            weight=0.20,
            details={"min_safety_factor": min(sf_values) if sf_values else None},
        )
    )

    # Compute weighted score.
    total_weight = sum(c.weight for c in checks)
    score = sum(c.score * c.weight for c in checks) / total_weight if total_weight else 0.0
    score = max(0.0, min(1.0, score))
    passed = all(c.passed for c in checks) and score >= 0.75

    cert_id = uuid.uuid4().hex
    cert = CertificationResult(
        cert_id=cert_id,
        design_id=design_id,
        score=score * 100.0,
        passed=passed,
        checks=checks,
        load_case_results=load_case_results,
        ab_comparisons=ab_comparisons,
    )

    cert_path = output_dir / f"{cert_id}.json"
    cert_path.write_text(json.dumps(cert.model_dump(), indent=2), encoding="utf-8")
    cert.certificate_path = cert_path

    return cert


def load_certificate(design_dir: Path, cert_id: str) -> CertificationResult | None:
    """Load a persisted certificate JSON."""
    cert_path = design_dir / "certificates" / f"{cert_id}.json"
    if not cert_path.exists():
        return None
    try:
        data = json.loads(cert_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    checks = [CheckResult(**c) for c in data.get("checks", [])]
    return CertificationResult(
        cert_id=data["cert_id"],
        design_id=data["design_id"],
        score=data["score"],
        passed=data["passed"],
        checks=checks,
        load_case_results=data.get("load_case_results", []),
        ab_comparisons=data.get("ab_comparisons", []),
        certificate_path=Path(data["certificate_path"]) if data.get("certificate_path") else None,
        created_at=data.get("created_at", time.time()),
    )


def list_certificates(design_dir: Path) -> list[CertificationResult]:
    """Return all certificates found under a design directory."""
    cert_dir = design_dir / "certificates"
    if not cert_dir.exists():
        return []
    results: list[CertificationResult] = []
    for path in cert_dir.glob("*.json"):
        cert = load_certificate(design_dir, path.stem)
        if cert:
            results.append(cert)
    return sorted(results, key=lambda c: c.created_at, reverse=True)
