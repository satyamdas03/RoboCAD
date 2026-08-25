"""Persistence layer for RoboCAD FeatureTree JSON sidecars.

Stores ``feature_tree.json`` next to existing design artifacts under
``designs/{design_id}/``. Supports versioning aligned with the code-based
versioning in ``web/backend/main.py``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ai_cad.feature_tree import FeatureTree


def _default_designs_dir() -> Path:
    return Path(os.environ.get("ROBOCAD_DESIGNS_DIR", "designs"))


def _design_dir(design_id: str, designs_dir: Path | None = None) -> Path:
    base = designs_dir or _default_designs_dir()
    return base / design_id


def _tree_path(design_id: str, designs_dir: Path | None = None) -> Path:
    return _design_dir(design_id, designs_dir) / "feature_tree.json"


def _version_tree_path(design_id: str, version_id: str, designs_dir: Path | None = None) -> Path:
    return _design_dir(design_id, designs_dir) / "versions" / version_id / "feature_tree.json"


def save(
    design_id: str,
    tree: FeatureTree,
    designs_dir: Path | None = None,
    version_id: str | None = None,
) -> Path:
    """Persist a feature tree to JSON and return the saved path."""
    if version_id:
        path = _version_tree_path(design_id, version_id, designs_dir)
    else:
        path = _tree_path(design_id, designs_dir)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(tree.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    return path


def load(
    design_id: str,
    designs_dir: Path | None = None,
    version_id: str | None = None,
) -> Optional[FeatureTree]:
    """Load a feature tree from JSON if it exists, otherwise return None."""
    if version_id:
        path = _version_tree_path(design_id, version_id, designs_dir)
    else:
        path = _tree_path(design_id, designs_dir)

    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    return FeatureTree(**data)


def exists(
    design_id: str,
    designs_dir: Path | None = None,
    version_id: str | None = None,
) -> bool:
    if version_id:
        path = _version_tree_path(design_id, version_id, designs_dir)
    else:
        path = _tree_path(design_id, designs_dir)
    return path.exists()


def load_latest(
    design_id: str,
    designs_dir: Path | None = None,
) -> Optional[FeatureTree]:
    """Load the most recent feature tree for a design.

    Prefers the top-level ``feature_tree.json``; if absent, falls back to the
    most recently modified version directory.
    """
    tree = load(design_id, designs_dir)
    if tree is not None:
        return tree

    design_dir = _design_dir(design_id, designs_dir)
    versions_dir = design_dir / "versions"
    if not versions_dir.exists():
        return None

    version_dirs = sorted(
        [d for d in versions_dir.iterdir() if d.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for v_dir in version_dirs:
        path = v_dir / "feature_tree.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return FeatureTree(**data)
    return None
