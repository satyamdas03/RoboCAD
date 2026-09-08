"""Local asset marketplace for RoboCAD.

Provides a lightweight, file-based marketplace for verified parts, scene
templates, robot templates, world templates, electronics templates, and
aero templates. Items are stored as JSON metadata under
``marketplace/index.json``; asset files live in the source path referenced
by each item.
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_cad.dfm import analyze_dfm
from ai_cad.geda_bridge import load_bundle_manifest, verify_bundle, validate_bundle_with_mujoco
from ai_cad.mesh_quality import check_mesh_quality


class AssetType(str, Enum):
    """Supported marketplace asset kinds."""

    PART = "part"
    SCENE_TEMPLATE = "scene_template"
    ROBOT_TEMPLATE = "robot_template"
    WORLD_TEMPLATE = "world_template"
    ELECTRONICS_TEMPLATE = "electronics_template"
    AERO_TEMPLATE = "aero_template"


class MarketplaceItem(BaseModel):
    """Metadata for one marketplace asset."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)
    asset_type: AssetType = AssetType.PART
    source_path: str = ""
    thumbnail_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    verified: bool = False
    verification_report: dict[str, Any] = Field(default_factory=dict)
    downloads_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None


class MarketplaceImportResult(BaseModel):
    """Result of importing a marketplace asset into a persisted design."""

    design_id: str
    item_id: str
    feature_tree_merged: bool = False
    imported_paths: list[str] = Field(default_factory=list)


DEFAULT_MARKETPLACE_DIR = Path("marketplace")


def _marketplace_dir() -> Path:
    """Return the marketplace root directory."""
    DEFAULT_MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_MARKETPLACE_DIR


def _index_path() -> Path:
    return _marketplace_dir() / "index.json"


def _ensure_index() -> None:
    """Create an empty marketplace index if none exists."""
    path = _index_path()
    if not path.exists():
        path.write_text(json.dumps({"items": []}, indent=2), encoding="utf-8")


def _load_index() -> dict[str, MarketplaceItem]:
    """Load the marketplace index as a map of id -> item."""
    _ensure_index()
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    items: dict[str, MarketplaceItem] = {}
    for raw in data.get("items", []):
        try:
            item = MarketplaceItem(**raw)
            items[item.id] = item
        except Exception:
            continue
    return items


def _save_index(items: dict[str, MarketplaceItem]) -> None:
    """Persist the marketplace index."""
    _ensure_index()
    _index_path().write_text(
        json.dumps(
            {"items": [item.model_dump(mode="json") for item in items.values()]},
            indent=2,
        ),
        encoding="utf-8",
    )


def _resolve_source_path(source_path: str) -> Path:
    """Resolve a source path relative to the repo root."""
    path = Path(source_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path.resolve()


def _asset_files(source_path: str) -> list[str]:
    """Return all files under an asset source directory."""
    path = _resolve_source_path(source_path)
    if not path.exists():
        return []
    if path.is_file():
        return [path.name]
    files: list[str] = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            files.append(str(p.relative_to(path).as_posix()))
    return files


def list_items(
    asset_type: AssetType | None = None,
    tag: str | None = None,
    search: str = "",
    verified_only: bool = False,
) -> list[MarketplaceItem]:
    """Return marketplace items with optional filters."""
    items = _load_index().values()
    if asset_type is not None:
        items = [i for i in items if i.asset_type == asset_type]
    if verified_only:
        items = [i for i in items if i.verified]
    if tag:
        tag_lower = tag.lower()
        items = [i for i in items if tag_lower in [t.lower() for t in i.tags]]
    if search:
        query = search.lower()
        items = [
            i
            for i in items
            if query in i.name.lower()
            or query in i.description.lower()
            or any(query in t.lower() for t in i.tags)
            or query in i.asset_type.value.lower()
        ]
    return sorted(items, key=lambda i: i.created_at, reverse=True)


def get_item(item_id: str) -> MarketplaceItem:
    """Return a single marketplace item by id.

    Raises ``KeyError`` if the item does not exist (matching the endpoint
    expectation).
    """
    item = _load_index().get(item_id)
    if item is None:
        raise KeyError(f"Marketplace item {item_id} not found.")
    return item


def create_item(item: MarketplaceItem) -> MarketplaceItem:
    """Create a new marketplace catalog entry."""
    items = _load_index()
    if item.id in items:
        raise ValueError(f"Marketplace item with id {item.id} already exists.")
    items[item.id] = item
    _save_index(items)
    return item


def create_item_from_upload(
    source_dir: Path | str,
    name: str,
    asset_type: AssetType = AssetType.PART,
    description: str = "",
    author: str = "",
    tags: list[str] | None = None,
) -> MarketplaceItem:
    """Create a marketplace item from an uploaded/extracted archive directory.

    The contents are copied into ``marketplace/uploads/{uuid}/`` so the original
    upload path can be deleted safely. The item ``source_path`` points at the
    copied directory.
    """
    source_dir = Path(source_dir)
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"Upload source directory not found: {source_dir}")

    upload_id = uuid.uuid4().hex
    dest_dir = _marketplace_dir() / "uploads" / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy the archive contents into the stable marketplace directory.
    for src_path in sorted(source_dir.rglob("*")):
        if src_path.is_file():
            rel = src_path.relative_to(source_dir)
            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest)

    item = MarketplaceItem(
        name=name,
        description=description,
        author=author,
        asset_type=asset_type,
        source_path=str(dest_dir.relative_to(Path(__file__).resolve().parent.parent).as_posix()),
        tags=tags or [],
    )
    return create_item(item)


def update_item(item_id: str, updates: dict[str, Any]) -> MarketplaceItem:
    """Update fields of an existing marketplace item."""
    items = _load_index()
    if item_id not in items:
        raise KeyError(f"Marketplace item {item_id} not found.")
    current = items[item_id]
    data = current.model_dump(mode="json")
    data.update(updates)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    item = MarketplaceItem(**data)
    items[item_id] = item
    _save_index(items)
    return item


def delete_item(item_id: str) -> bool:
    """Remove a marketplace item from the catalog."""
    items = _load_index()
    if item_id not in items:
        return False
    del items[item_id]
    _save_index(items)
    return True


def _verify_part_asset(item: MarketplaceItem) -> dict[str, Any]:
    """Run DFM and mesh-quality checks on a part asset."""
    path = _resolve_source_path(item.source_path)
    stl_path = path / "model.stl"
    if not stl_path.exists():
        return {"passed": False, "errors": ["No model.stl found in part source path."], "checks": {}}
    try:
        dfm_report = analyze_dfm(stl_path)
        mesh_report = check_mesh_quality(stl_path)
        passed = dfm_report.valid and mesh_report.is_suitable_for_solver
        return {
            "passed": passed,
            "checks": {
                "dfm": dfm_report.model_dump(),
                "mesh_quality": mesh_report.model_dump(),
            },
        }
    except Exception as exc:
        return {"passed": False, "errors": [str(exc)], "checks": {}}


def _verify_bundle_asset(item: MarketplaceItem) -> dict[str, Any]:
    """Run bundle verification and optional MuJoCo runtime validation."""
    path = _resolve_source_path(item.source_path)
    bundle_dir = path / "bundle"
    if not bundle_dir.exists():
        bundle_dir = path
    try:
        manifest = load_bundle_manifest(bundle_dir)
        verification = verify_bundle(bundle_dir)
        runtime = {"mjcf_loadable": False, "errors": []}
        try:
            runtime_check = validate_bundle_with_mujoco(bundle_dir)
            runtime["mjcf_loadable"] = (
                runtime_check.get("mjcf_loadable", False)
                and runtime_check.get("sim_steps_ok", False)
            )
            runtime["rollout"] = runtime_check
        except Exception as exc:
            runtime["errors"].append(str(exc))
        passed = verification.valid and runtime["mjcf_loadable"]
        return {
            "passed": passed,
            "checks": {
                "runtime": {
                    "bundle_verification": verification.model_dump(mode="json"),
                    "runtime_validation": runtime,
                },
            },
        }
    except Exception as exc:
        return {"passed": False, "errors": [str(exc)], "checks": {}}


def verify_asset(item: MarketplaceItem) -> MarketplaceItem:
    """Run verification checks on an item and return the updated item."""
    if item.asset_type == AssetType.PART:
        report = _verify_part_asset(item)
    elif item.asset_type in (
        AssetType.SCENE_TEMPLATE,
        AssetType.ROBOT_TEMPLATE,
        AssetType.WORLD_TEMPLATE,
    ):
        report = _verify_bundle_asset(item)
    else:
        report = {"passed": True, "checks": {}, "note": "Verification not implemented for this asset type."}

    item.verified = report.get("passed", False)
    item.verification_report = report
    item.updated_at = datetime.now(timezone.utc).isoformat()
    return item


def record_download(item_id: str) -> MarketplaceItem:
    """Increment the download counter for an item."""
    items = _load_index()
    if item_id not in items:
        raise KeyError(f"Marketplace item {item_id} not found.")
    item = items[item_id]
    item.downloads_count += 1
    item.updated_at = datetime.now(timezone.utc).isoformat()
    _save_index(items)
    return item


def import_item_into_design(
    item_id: str,
    design_id: str,
    designs_dir: Path,
) -> MarketplaceImportResult:
    """Copy a marketplace asset into an existing persisted design."""
    item = get_item(item_id)
    design_dir = Path(designs_dir) / design_id
    design_dir.mkdir(parents=True, exist_ok=True)

    imports_dir = design_dir / "imports" / item_id
    imports_dir.mkdir(parents=True, exist_ok=True)

    source = _resolve_source_path(item.source_path)
    imported_paths: list[str] = []
    feature_tree_merged = False

    if source.exists() and source.is_dir():
        for src_path in sorted(source.rglob("*")):
            if src_path.is_file():
                rel = src_path.relative_to(source)
                dest = imports_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest)
                imported_paths.append(str((imports_dir / rel).relative_to(design_dir).as_posix()))

    # Merge feature tree if present.
    design_feature_tree = design_dir / "feature_tree.json"
    imported_feature_tree = imports_dir / "feature_tree.json"
    if imported_feature_tree.exists():
        try:
            imported_data = json.loads(imported_feature_tree.read_text(encoding="utf-8"))
            if design_feature_tree.exists():
                design_data = json.loads(design_feature_tree.read_text(encoding="utf-8"))
                assemblies = design_data.setdefault("assemblies", [])
                imported_assemblies = imported_data.get("assemblies", [])
                assemblies.extend(imported_assemblies)
                parts = design_data.setdefault("parts", [])
                imported_parts = imported_data.get("parts", [])
                # Avoid id collisions by appending a suffix.
                for p in imported_parts:
                    p["id"] = f"{p.get('id', 'imported')}_{item_id[:8]}"
                parts.extend(imported_parts)
                design_feature_tree.write_text(json.dumps(design_data, indent=2), encoding="utf-8")
            else:
                design_feature_tree.write_text(json.dumps(imported_data, indent=2), encoding="utf-8")
            feature_tree_merged = True
        except Exception:
            pass

    # Record import in design metadata.
    meta_path = design_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    else:
        meta = {"id": design_id}
    imports = meta.setdefault("imports", [])
    imports.append(
        {
            "item_id": item_id,
            "name": item.name,
            "asset_type": item.asset_type.value,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    return MarketplaceImportResult(
        design_id=design_id,
        item_id=item_id,
        feature_tree_merged=feature_tree_merged,
        imported_paths=imported_paths,
    )
