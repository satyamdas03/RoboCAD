"""Pydantic models for the RoboCAD GEDA Bridge simulation bundles."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class InertialData(BaseModel):
    """Mass properties for a single rigid body in SI units."""

    mass_kg: float
    center_of_mass_m: tuple[float, float, float]
    inertia_tensor_kg_m2: tuple[
        float, float, float, float, float, float
    ] = Field(
        description="Inertia tensor about CoM as (Ixx, Iyy, Izz, Ixy, Ixz, Iyz)."
    )
    principal_moments_kg_m2: tuple[float, float, float] | None = None
    principal_axes: list[tuple[float, float, float]] | None = None
    density_kg_m3: float
    material: str


class BundlePart(BaseModel):
    """One instance / link in the exported simulation bundle."""

    part_id: str
    instance_id: str | None = None
    name: str
    material: str
    density_kg_m3: float
    mesh_file: str
    inertial: InertialData
    transform_m: list[list[float]] | None = None


class BundlePaths(BaseModel):
    """Filesystem paths to generated bundle artifacts."""

    directory: Path
    manifest_json: Path
    meshes_dir: Path
    urdf: Path
    mjcf: Path
    inertial_json: Path
    zip: Path | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(**kwargs)
        for key in ("directory", "manifest_json", "meshes_dir", "urdf", "mjcf", "inertial_json", "zip"):
            value = data.get(key)
            if isinstance(value, Path):
                data[key] = value.as_posix()
        return data


class BundleManifest(BaseModel):
    """Top-level manifest describing a simulation-ready asset bundle."""

    schema_version: str = "2.0.0"
    design_id: str | None = None
    name: str
    created_at: str
    generator: str = "RoboCAD GEDA Bridge"
    length_unit: str = "m"
    mass_unit: str = "kg"
    parts: list[BundlePart] = Field(default_factory=list)


class BundleVerification(BaseModel):
    """Verification report for a generated bundle."""

    valid: bool = False
    all_watertight: bool = False
    all_masses_positive: bool = False
    all_inertia_positive_definite: bool = False
    all_com_inside_hull: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
