"""Structured response models for the RoboCAD generation pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_cad.feature_tree import FeatureTree


class CADParameter(BaseModel):
    """A named, editable numeric parameter extracted from generated code."""

    name: str
    value: float | int
    unit: str = "mm"
    description: str | None = None


class ExportPaths(BaseModel):
    """Filesystem paths to generated artifacts."""

    step: Path | None = None
    stl: Path | None = None
    script: Path | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(**kwargs)
        for key in ("step", "stl", "script"):
            value = data.get(key)
            if isinstance(value, Path):
                data[key] = value.as_posix()
        return data


class ValidationReport(BaseModel):
    """Geometry/manufacturability validation report for a generated STL."""

    valid: bool = False
    manifold: bool = False
    watertight: bool = False
    bounds_mm: tuple[float, float, float] | None = None
    volume_mm3: float | None = None
    surface_area_mm2: float | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ManufacturingReport(BaseModel):
    """Manufacturability report for a generated STL."""

    valid: bool = False
    bounds_mm: tuple[float, float, float] | None = None
    volume_cm3: float | None = None
    surface_area_cm2: float | None = None
    overhangs: list[int] = Field(default_factory=list)
    overhang_area_mm2: float = 0.0
    overhang_ratio: float = 0.0
    min_hole_diameter_mm: float | None = None
    min_feature_size_mm: float | None = None
    estimated_print_time_min: float | None = None
    issues: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    """Full result of a single RoboCAD generate() call."""

    prompt: str
    success: bool = False
    code: str | None = None
    parameters: list[CADParameter] = Field(default_factory=list)
    exports: ExportPaths = Field(default_factory=ExportPaths)
    validation: ValidationReport | None = None
    manufacturing: ManufacturingReport | None = None
    feature_tree: FeatureTree | None = None
    attempts_used: int = 0
    max_retries: int = 0
    model: str = "unknown"
    error: str | None = None
    traceback: str | None = None
    explanation: str | None = None
    latency_seconds: float | None = None
