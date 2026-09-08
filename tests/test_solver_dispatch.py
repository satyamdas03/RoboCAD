"""Tests for the Phase 28C async deep verification dispatcher and job store."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.solvers.job_store import JobStatus, JobStore, VerificationJob
from ai_cad.solvers.verification_deep import (
    CalculiXAdapter,
    DeepVerificationDispatcher,
    ElmerAdapter,
    OpenFOAMAdapter,
    SurrogateAdapter,
    poll_deep_verification,
    run_deep_verification,
    submit_deep_verification,
)
from ai_cad.verification_models import LoadCase, VerificationRequest


@pytest.fixture
def temp_job_store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "verification_jobs.db")


@pytest.fixture
def sample_design(tmp_path: Path) -> Path:
    """Create a persisted design directory with a simple bracket STL."""
    design_dir = tmp_path / "designs" / "bracket_deep"
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    mesh = trimesh.creation.box(extents=(50.0, 20.0, 5.0))
    mesh.export(str(exports_dir / "model.stl"))
    metadata = {
        "id": "bracket_deep",
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


def _make_request(load_case: LoadCase) -> VerificationRequest:
    return VerificationRequest(
        design_id="bracket_deep",
        load_case=load_case,
        parameters={"material": "PLA", "load_magnitude_n": 50},
    )


# ---------------------------------------------------------------------------
# Job store lifecycle
# ---------------------------------------------------------------------------

def test_job_store_submit_and_get(temp_job_store: JobStore):
    request = _make_request(LoadCase.STATIC_STRESS)
    job_id = temp_job_store.submit(request, "calculix")
    assert len(job_id) == 32

    job = temp_job_store.get(job_id)
    assert job is not None
    assert job.design_id == "bracket_deep"
    assert job.load_case == LoadCase.STATIC_STRESS
    assert job.solver_type == "calculix"
    assert job.status == JobStatus.PENDING
    assert job.progress == 0.0
    assert "load_case" in job.inputs


def test_job_store_update_progress_and_status(temp_job_store: JobStore):
    request = _make_request(LoadCase.STATIC_STRESS)
    job_id = temp_job_store.submit(request, "calculix")

    ok = temp_job_store.update(job_id, status=JobStatus.RUNNING, progress=0.33)
    assert ok is True

    job = temp_job_store.get(job_id)
    assert job.status == JobStatus.RUNNING
    assert job.progress == pytest.approx(0.33, abs=0.01)

    result = {"passed": True, "metrics": {"x": 1.0}}
    ok = temp_job_store.update(job_id, status=JobStatus.COMPLETED, progress=1.0, result=result)
    assert ok is True

    job = temp_job_store.get(job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.progress == 1.0
    assert job.result == result


def test_job_store_cancel(temp_job_store: JobStore):
    request = _make_request(LoadCase.STATIC_STRESS)
    job_id = temp_job_store.submit(request, "calculix")
    assert temp_job_store.cancel(job_id) is True

    job = temp_job_store.get(job_id)
    assert job.status == JobStatus.CANCELLED
    assert job.progress == 1.0

    # Cannot cancel an already-terminal job.
    assert temp_job_store.cancel(job_id) is False


def test_job_store_cancel_missing_job(temp_job_store: JobStore):
    assert temp_job_store.cancel("nosuchjob") is False


def test_job_store_list_jobs(temp_job_store: JobStore):
    for i in range(3):
        request = VerificationRequest(
            design_id=f"d{i}",
            load_case=LoadCase.STATIC_STRESS,
            parameters={},
        )
        temp_job_store.submit(request, "calculix")

    all_jobs = temp_job_store.list_jobs(limit=10)
    assert len(all_jobs) == 3

    # Filter by design id.
    d1_jobs = temp_job_store.list_jobs(design_id="d1")
    assert len(d1_jobs) == 1
    assert d1_jobs[0].design_id == "d1"

    # Filter by status.
    pending = temp_job_store.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 3


def test_job_store_terminal_status_update_guard(temp_job_store: JobStore):
    request = _make_request(LoadCase.STATIC_STRESS)
    job_id = temp_job_store.submit(request, "calculix")
    temp_job_store.update(job_id, status=JobStatus.COMPLETED, progress=1.0)

    # Should not be able to move a completed job back to running.
    ok = temp_job_store.update(job_id, status=JobStatus.RUNNING, progress=0.5)
    assert ok is False

    job = temp_job_store.get(job_id)
    assert job.status == JobStatus.COMPLETED


def test_job_store_update_missing_job(temp_job_store: JobStore):
    assert temp_job_store.update("missing", status=JobStatus.RUNNING) is False


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------

def test_dispatcher_routes_structural_to_calculix(temp_job_store: JobStore, sample_design: Path):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    request = _make_request(LoadCase.STATIC_STRESS)
    adapter = dispatcher.adapter_for(request)
    assert isinstance(adapter, CalculiXAdapter)
    assert dispatcher.solver_type_for(request) == "calculix"


def test_dispatcher_routes_drop_test_to_calculix(temp_job_store: JobStore):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    request = _make_request(LoadCase.DROP_TEST)
    assert isinstance(dispatcher.adapter_for(request), CalculiXAdapter)


def test_dispatcher_routes_thermal_to_elmer(temp_job_store: JobStore, sample_design: Path):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    request = VerificationRequest(
        design_id="bracket_deep",
        load_case=LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
        parameters={"heat_flux_w": 5.0, "target_theta_c_per_w": 10.0, "material": "Aluminum 6061"},
    )
    adapter = dispatcher.adapter_for(request)
    assert isinstance(adapter, ElmerAdapter)
    assert dispatcher.solver_type_for(request) == "elmer"


def test_dispatcher_routes_cfd_to_openfoam(temp_job_store: JobStore, sample_design: Path):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    request = VerificationRequest(
        design_id="bracket_deep",
        load_case=LoadCase.WIND_TUNNEL_DRAG,
        parameters={"velocity_m_s": 10.0},
    )
    adapter = dispatcher.adapter_for(request)
    assert isinstance(adapter, OpenFOAMAdapter)
    assert dispatcher.solver_type_for(request) == "openfoam"


def test_dispatcher_explicit_surrogate_override(temp_job_store: JobStore):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    request = VerificationRequest(
        design_id="bracket_deep",
        load_case=LoadCase.STATIC_STRESS,
        parameters={"solver": "surrogate"},
    )
    assert isinstance(dispatcher.adapter_for(request), SurrogateAdapter)
    assert dispatcher.solver_type_for(request) == "surrogate"


def test_dispatcher_unknown_load_case_defaults_to_surrogate(temp_job_store: JobStore):
    dispatcher = DeepVerificationDispatcher(job_store=temp_job_store)
    # Gait feasibility is not explicitly routed by the deep dispatcher.
    request = VerificationRequest(
        design_id="bracket_deep",
        load_case=LoadCase.GAIT_FEASIBILITY,
        parameters={},
    )
    assert isinstance(dispatcher.adapter_for(request), SurrogateAdapter)


# ---------------------------------------------------------------------------
# End-to-end deep verification
# ---------------------------------------------------------------------------

def test_run_deep_verification_structural(sample_design: Path, temp_job_store: JobStore):
    result = run_deep_verification(
        design_id="bracket_deep",
        load_case=LoadCase.STATIC_STRESS,
        params={"material": "PLA", "load_magnitude_n": 50},
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert result.design_id == "bracket_deep"
    assert result.load_case == LoadCase.STATIC_STRESS
    assert result.report_id is not None
    assert "max_stress_mpa" in result.metrics
    assert "safety_factor" in result.metrics
    assert result.redesign_suggestions or not result.passed

    # Verify the job was persisted as completed/failed.
    job = temp_job_store.get(result.report_id)
    assert job is not None
    assert job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
    assert job.result is not None


def test_run_deep_verification_thermal(sample_design: Path, temp_job_store: JobStore):
    result = run_deep_verification(
        design_id="bracket_deep",
        load_case=LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
        params={"heat_flux_w": 5.0, "target_theta_c_per_w": 10.0, "material": "Aluminum 6061"},
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert result.load_case == LoadCase.HEAT_SINK_THERMAL_RESISTANCE
    assert "thermal_resistance_c_per_w" in result.metrics


def test_run_deep_verification_cfd(sample_design: Path, temp_job_store: JobStore):
    result = run_deep_verification(
        design_id="bracket_deep",
        load_case=LoadCase.WIND_TUNNEL_DRAG,
        params={"velocity_m_s": 10.0},
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert result.load_case == LoadCase.WIND_TUNNEL_DRAG
    assert "drag_coefficient" in result.metrics
    assert "drag_force_n" in result.metrics


def test_run_deep_verification_surrogate(sample_design: Path, temp_job_store: JobStore):
    result = run_deep_verification(
        design_id="bracket_deep",
        load_case=LoadCase.STATIC_STRESS,
        params={"solver": "surrogate", "load_magnitude_n": 50},
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert result.load_case == LoadCase.STATIC_STRESS
    assert result.report_id is not None


def test_run_deep_verification_missing_stl(temp_job_store: JobStore, tmp_path: Path):
    design_dir = tmp_path / "designs" / "no_stl"
    design_dir.mkdir(parents=True)
    result = run_deep_verification(
        design_id="no_stl",
        load_case=LoadCase.STATIC_STRESS,
        design_dir=design_dir,
        job_store=temp_job_store,
    )
    assert result.passed is False
    assert result.errors


# ---------------------------------------------------------------------------
# Async submit/poll
# ---------------------------------------------------------------------------

def test_submit_and_poll_deep_verification(sample_design: Path, temp_job_store: JobStore):
    request = VerificationRequest(
        design_id="bracket_deep",
        load_case=LoadCase.STATIC_STRESS,
        parameters={"material": "PLA", "load_magnitude_n": 50},
    )
    job_id = submit_deep_verification(
        request,
        design_dir=sample_design,
        job_store=temp_job_store,
    )
    assert len(job_id) == 32

    # Poll until terminal (with a short timeout for the test).
    for _ in range(50):
        job = poll_deep_verification(job_id, job_store=temp_job_store)
        assert job is not None
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            break
        time.sleep(0.05)

    assert job is not None
    assert job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
    assert job.result is not None


def test_poll_missing_job(temp_job_store: JobStore):
    assert poll_deep_verification("missing", job_store=temp_job_store) is None
