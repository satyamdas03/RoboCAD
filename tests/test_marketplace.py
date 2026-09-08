"""Tests for the RoboCAD Phase 28B asset marketplace backend."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path for `ai_cad` imports.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad import marketplace as marketplace_module
from ai_cad.marketplace import AssetType, MarketplaceItem
from web.backend import main as main_module
from web.backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_marketplace(tmp_path: Path):
    """Use a temporary marketplace index directory for every test."""
    original_marketplace_dir = marketplace_module._marketplace_dir
    test_marketplace_dir = tmp_path / "marketplace"
    test_marketplace_dir.mkdir(parents=True, exist_ok=True)
    marketplace_module._marketplace_dir = lambda: test_marketplace_dir
    marketplace_module._ensure_index()
    yield
    marketplace_module._marketplace_dir = original_marketplace_dir


@pytest.fixture
def bracket_source() -> Path:
    return REPO_ROOT / "marketplace" / "starter_packs" / "parts" / "bracket"


@pytest.fixture
def scene_source() -> Path:
    return REPO_ROOT / "marketplace" / "starter_packs" / "scene_templates" / "gripper_cube_grasp"


@pytest.fixture
def robot_source() -> Path:
    return REPO_ROOT / "marketplace" / "starter_packs" / "robot_templates" / "manipulator_on_base"


@pytest.fixture(autouse=True)
def clean_designs(tmp_path: Path):
    """Use a temporary designs directory for every test."""
    original = main_module.DESIGNS_DIR
    test_dir = tmp_path / "designs"
    test_dir.mkdir(parents=True, exist_ok=True)
    main_module.DESIGNS_DIR = test_dir
    yield
    main_module.DESIGNS_DIR = original


def _seed_design(design_id: str) -> Path:
    """Create a minimal persisted design directory."""
    design_dir = main_module.DESIGNS_DIR / design_id
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "metadata.json").write_text(
        json.dumps(
            {
                "id": design_id,
                "prompt": "seed design for import",
                "success": True,
                "model": "seed",
                "attempts_used": 1,
                "max_retries": 0,
                "latency_seconds": 0.0,
                "created_at": "2026-09-01T00:00:00Z",
                "exports": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return design_dir


def test_marketplace_crud(bracket_source: Path):
    """Create, list, get, update, and delete marketplace items via endpoints."""
    # CREATE
    create_response = client.post(
        "/marketplace/items",
        json={
            "name": "L-bracket",
            "description": "Parametric L-bracket starter part.",
            "author": "RoboCAD",
            "version": "1.0.0",
            "tags": ["structural", "bracket", "starter"],
            "asset_type": "part",
            "source_path": str(bracket_source),
            "thumbnail_url": None,
            "metadata": {"family": "bracket"},
        },
    )
    assert create_response.status_code == 200
    item = create_response.json()
    assert item["name"] == "L-bracket"
    assert item["asset_type"] == "part"
    assert item["id"] is not None
    item_id = item["id"]

    # LIST
    list_response = client.get("/marketplace/items")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["id"] == item_id

    # GET
    get_response = client.get(f"/marketplace/items/{item_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == item_id

    # FILTER by asset type
    filtered = client.get("/marketplace/items?asset_type=robot_template")
    assert filtered.status_code == 200
    assert filtered.json() == []

    # UPDATE
    update_response = client.post(
        f"/marketplace/items/{item_id}",
        json={"description": "Updated description", "tags": ["structural", "bracket"]},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["description"] == "Updated description"
    assert updated["tags"] == ["structural", "bracket"]

    # DELETE
    delete_response = client.delete(f"/marketplace/items/{item_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert client.get(f"/marketplace/items/{item_id}").status_code == 404


def test_marketplace_verify_badge_part(bracket_source: Path):
    """A part asset is marked verified only after DFM + mesh-quality pass."""
    create_response = client.post(
        "/marketplace/items",
        json={
            "name": "L-bracket",
            "asset_type": "part",
            "source_path": str(bracket_source),
            "tags": ["starter"],
        },
    )
    item_id = create_response.json()["id"]

    # Initially unverified.
    assert create_response.json()["verified"] is False

    verify_response = client.post(f"/marketplace/items/{item_id}/verify")
    assert verify_response.status_code == 200
    verified = verify_response.json()
    assert verified["verified"] is True
    report = verified["verification_report"]
    assert report["passed"] is True
    assert "dfm" in report["checks"]
    assert "mesh_quality" in report["checks"]
    assert report["checks"]["dfm"]["valid"] is True
    assert report["checks"]["mesh_quality"]["is_suitable_for_solver"] is True


def test_marketplace_verify_badge_bundle(scene_source: Path):
    """A scene-template asset is verified via bundle + runtime validation."""
    create_response = client.post(
        "/marketplace/items",
        json={
            "name": "Gripper cube grasp",
            "asset_type": "scene_template",
            "source_path": str(scene_source),
            "tags": ["scene", "starter"],
        },
    )
    item_id = create_response.json()["id"]
    verify_response = client.post(f"/marketplace/items/{item_id}/verify")
    assert verify_response.status_code == 200
    verified = verify_response.json()
    assert verified["verified"] is True
    report = verified["verification_report"]
    assert report["passed"] is True
    assert "runtime" in report["checks"]
    runtime = report["checks"]["runtime"]
    assert runtime["bundle_verification"]["valid"] is True
    assert runtime["runtime_validation"]["mjcf_loadable"] is True


def test_marketplace_download(bracket_source: Path):
    """Download endpoint records a download and returns asset file list."""
    create_response = client.post(
        "/marketplace/items",
        json={
            "name": "L-bracket",
            "asset_type": "part",
            "source_path": str(bracket_source),
        },
    )
    item_id = create_response.json()["id"]

    download_response = client.post(f"/marketplace/items/{item_id}/download")
    assert download_response.status_code == 200
    data = download_response.json()
    assert data["item_id"] == item_id
    assert data["downloads_count"] == 1
    assert "model.stl" in data["files"]


def test_marketplace_import_into_design(bracket_source: Path):
    """Import a marketplace asset into an existing persisted design."""
    design_id = "import_test_design"
    design_dir = _seed_design(design_id)

    create_response = client.post(
        "/marketplace/items",
        json={
            "name": "L-bracket",
            "asset_type": "part",
            "source_path": str(bracket_source),
            "tags": ["starter"],
        },
    )
    item_id = create_response.json()["id"]

    import_response = client.post(f"/marketplace/items/{item_id}/import/{design_id}")
    assert import_response.status_code == 200
    result = import_response.json()
    assert result["design_id"] == design_id
    assert result["item_id"] == item_id
    assert result["feature_tree_merged"] is True
    assert any("feature_tree.json" in p for p in result["imported_paths"])
    assert (design_dir / "imports" / item_id / "model.stl").exists()
    assert (design_dir / "imports" / item_id / "feature_tree.json").exists()

    meta = json.loads((design_dir / "metadata.json").read_text(encoding="utf-8"))
    assert len(meta["imports"]) == 1
    assert meta["imports"][0]["item_id"] == item_id


