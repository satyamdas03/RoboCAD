"""GEDA Bridge — export RoboCAD designs to simulation-ready bundles."""
from __future__ import annotations

from ai_cad.geda_bridge.exporter import (
    compute_inertial,
    export_bundle_from_mesh,
    export_bundle_from_shape,
    export_bundle_from_tree,
    material_density,
    shape_to_trimesh,
)
from ai_cad.geda_bridge.models import (
    BundleManifest,
    BundlePart,
    BundlePaths,
    BundleVerification,
    InertialData,
)
from ai_cad.geda_bridge.packager import package_bundle, package_bundle_paths
from ai_cad.geda_bridge.verifier import verify_bundle

__all__ = [
    "compute_inertial",
    "export_bundle_from_mesh",
    "export_bundle_from_shape",
    "export_bundle_from_tree",
    "material_density",
    "shape_to_trimesh",
    "BundleManifest",
    "BundlePart",
    "BundlePaths",
    "BundleVerification",
    "InertialData",
    "package_bundle",
    "package_bundle_paths",
    "verify_bundle",
]
