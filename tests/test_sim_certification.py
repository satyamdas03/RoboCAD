"""Tests for the Phase 28E simulation certification engine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.sim_certification import (
    CERTIFICATION_LOAD_CASES,
    CheckResult,
    CertificationResult,
    list_certificates,
    load_certificate,
    run_certification,
)
from ai_cad.solvers.job_store import JobStore


@pytest.fixture
def sample_design(tmp_path: Path) -> Path:
    design_dir = tmp_path / "designs" / "bracket_cert"
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    mesh = trimesh.creation.box(extents=(50.0, 20.0, 5.0))
    mesh.export(str(exports_dir / "model.stl"))
    metadata = {
        "id": "bracket_cert",
        "prompt": "bracket",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-09-01T00:00:00Z",
        "exports": {"stl": "exports/model.stl"},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    return design_dir


@pytest.fixture
def temp_job_store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "cert_jobs.db")


def test_certification_runs_default_suite(
    sample_design: Path,
    temp_job_store: JobStore,
):
    cert = run_certification(
        design_id="bracket_cert",
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert isinstance(cert, CertificationResult)
    assert cert.design_id == "bracket_cert"
    assert 0.0 <= cert.score <= 100.0
    assert cert.certificate_path is not None
    assert cert.certificate_path.exists()

    check_names = {c.name for c in cert.checks}
    assert "load_case_pass_rate" in check_names
    assert "mesh_quality" in check_names


def test_certification_persists_and_loads(
    sample_design: Path,
    temp_job_store: JobStore,
):
    cert = run_certification(
        design_id="bracket_cert",
        design_dir=sample_design,
        job_store=temp_job_store,
        load_cases=[],
    )
    loaded = load_certificate(sample_design, cert.cert_id)
    assert loaded is not None
    assert loaded.cert_id == cert.cert_id
    assert loaded.score == pytest.approx(cert.score, abs=0.01)


def test_list_certificates(
    sample_design: Path,
    temp_job_store: JobStore,
):
    run_certification(
        design_id="bracket_cert",
        design_dir=sample_design,
        job_store=temp_job_store,
        load_cases=[],
    )
    certs = list_certificates(sample_design)
    assert len(certs) >= 1


def test_check_result_model_dump():
    check = CheckResult(name="test", passed=True, score=0.9, weight=0.5, details={"x": 1})
    data = check.details
    assert data == {"x": 1}


def test_certification_load_case_results_present(
    sample_design: Path,
    temp_job_store: JobStore,
):
    cert = run_certification(
        design_id="bracket_cert",
        design_dir=sample_design,
        job_store=temp_job_store,
        load_cases=[],
    )
    assert len(cert.load_case_results) == 0
    assert isinstance(cert.model_dump(), dict)
