"""Slow tests for simulation certification on robot designs (Milestone G)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_cad.robot_templates import humanoid_template
from ai_cad.sim_certification import run_certification
from ai_cad.solvers.job_store import JobStore

pytestmark = pytest.mark.slow


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


@pytest.fixture
def robot_design_dir(tmp_path: Path) -> Path:
    design_dir = tmp_path / "designs" / "humanoid_cert"
    design_dir.mkdir(parents=True, exist_ok=True)
    tree = humanoid_template()
    (design_dir / "feature_tree.json").write_text(
        json.dumps(tree.model_dump(mode="json")), encoding="utf-8"
    )
    metadata = {
        "id": "humanoid_cert",
        "prompt": "biped humanoid robot",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-09-01T00:00:00Z",
        "exports": {},
        "tags": ["robot"],
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return design_dir


@pytest.fixture
def temp_job_store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "cert_jobs.db")


def test_robot_certification_check_present_for_robot(
    robot_design_dir: Path,
    temp_job_store: JobStore,
):
    _skip_if_no_mujoco()
    cert = run_certification(
        design_id="humanoid_cert",
        design_dir=robot_design_dir,
        job_store=temp_job_store,
        load_cases=[],
    )
    check_names = {c.name for c in cert.checks}
    assert "robot_randomized_world_certification" in check_names
