"""Structured parametric feature-tree model for RoboCAD.

This module defines Pydantic models for the Feature-Tree JSON Schema v2.0.0
documented in ``docs/feature_tree_schema.md``. A feature tree is a symbolic,
editable design history that can be transpiled to ``build123d`` code.

Phase 9 scope:
- single-part designs
- base-plane sketches (XY, YZ, ZX)
- rectangle, circle, line, arc sketch entities
- extrude, revolve, fillet, chamfer, shell, mirror, linear_pattern,
  circular_pattern features
- constraints and dimensions stored but not yet solved (Phase 10)

Phase 16-17 additions:
- domain tags on features, parts, assemblies, and the top-level tree
- kinematic joints for mechanisms and humanoid/robot systems
- surface features for aero/thermal geometry
- PCB outlines for electronics co-design
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


NumericOrString = float | int | str


class Parameter(BaseModel):
    """Named editable value used throughout the feature tree."""

    name: str = Field(..., description="Unique identifier.")
    value: NumericOrString = Field(..., description="Current numeric value or expression string.")
    unit: str = Field(default="mm", description="Unit string.")
    description: str | None = Field(default=None)
    expression: str | None = Field(default=None)
    min: float | None = Field(default=None)
    max: float | None = Field(default=None)


class CoordinateSystem(BaseModel):
    """Named 3D coordinate system used by planes, features, and mates."""

    id: str
    name: str | None = None
    origin: tuple[float, float, float]
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]
    z_axis: tuple[float, float, float]


class PlaneReference(BaseModel):
    """Reference to a sketch plane."""

    type: Literal["base", "face", "offset"]
    name: str | None = None
    feature_id: str | None = None
    face_name: str | None = None
    from_csys_id: str | None = None
    offset_z: NumericOrString | None = None


class SketchEntity(BaseModel):
    """2D entity inside a sketch."""

    model_config = {"extra": "allow"}

    type: Literal["rectangle", "circle", "line", "arc", "polygon", "airfoil"]
    id: str
    # Common geometric fields. Not all apply to every type.
    center: tuple[NumericOrString, NumericOrString] | None = None
    width: NumericOrString | None = None
    height: NumericOrString | None = None
    radius: NumericOrString | None = None
    angle: NumericOrString | None = None
    start: tuple[NumericOrString, NumericOrString] | None = None
    end: tuple[NumericOrString, NumericOrString] | None = None
    start_angle: NumericOrString | None = None
    end_angle: NumericOrString | None = None
    sides: int | None = None
    # Airfoil-specific fields.
    naca: str | None = None
    chord: NumericOrString | None = None


class Constraint(BaseModel):
    """Geometric constraint between sketch entities."""

    type: Literal[
        "horizontal",
        "vertical",
        "parallel",
        "perpendicular",
        "coincident",
        "concentric",
        "equal",
        "symmetric",
        "tangent",
        "fix",
    ]
    entities: list[str]


class Dimension(BaseModel):
    """Driving dimension tied to a parameter."""

    name: str
    type: Literal["distance", "diameter", "radius", "angle"]
    entities: list[str]
    value: NumericOrString


class Sketch(BaseModel):
    """2D profile consumed by features."""

    id: str
    name: str | None = None
    plane: PlaneReference
    entities: list[SketchEntity] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    points: dict[str, list[tuple[float, float]]] = Field(
        default_factory=dict,
        description="Solved point sets for special entities such as airfoils.",
    )


class EdgeSelector(BaseModel):
    """Selector describing which edges a fillet/chamfer applies to."""

    type: Literal["all", "feature_edges", "last_feature"]
    feature_id: str | None = None


class Feature(BaseModel):
    """Single modeling operation (extrude, fillet, pattern, etc.)."""

    model_config = {"extra": "allow"}

    id: str
    domain: str = "mechanical"
    type: Literal[
        "extrude",
        "revolve",
        "fillet",
        "chamfer",
        "shell",
        "mirror",
        "linear_pattern",
        "circular_pattern",
    ]
    name: str | None = None
    enabled: bool = True
    depends_on: list[str] = Field(default_factory=list)
    sketch_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_feature_refs(self):
        if self.type in ("extrude", "revolve") and not self.sketch_id:
            raise ValueError(f"{self.type} feature must reference a sketch_id")
        return self


class KinematicJoint(BaseModel):
    """Joint connecting two links in a mechanism or robot."""

    id: str
    type: Literal["revolute", "prismatic", "spherical", "fixed"]
    parent_link: str
    child_link: str
    origin: tuple[float, float, float]
    axis: tuple[float, float, float] | None = None
    limits: tuple[float, float] | None = None


class SurfaceFeature(BaseModel):
    """Aero/thermal surface feature such as an airfoil, wing, duct, or heat sink."""

    model_config = {"extra": "allow"}

    id: str
    domain: str = "aero"
    type: Literal["airfoil", "wing", "duct", "heat_sink", "propeller_blade"]
    profile: dict[str, Any]


class PCBOutline(BaseModel):
    """Electronics co-design outline: board shape, mounting holes, keepouts.

    Phase 21 adds board thickness, edge clearance, connector cutout positions,
    and layer count so the outline can be transpiled into a realistic 3D PCB.
    """

    model_config = {"extra": "allow"}

    id: str
    domain: str = "electronics"
    board_shape: list[tuple[float, float]]
    board_thickness: float = 1.6
    edge_clearance: float = 1.0
    mounting_holes: list[tuple[float, float, float]] = Field(default_factory=list)
    keepouts: list[dict[str, Any]] = Field(default_factory=list)
    connector_positions: list[dict[str, Any]] = Field(default_factory=list)
    layer_count: int = 2


class Part(BaseModel):
    """Named sequence of sketches + features."""

    id: str
    domain: str = "mechanical"
    name: str | None = None
    family: str | None = None
    color: str | None = None
    material: str | None = None
    sketches: list[Sketch] = Field(default_factory=list)
    features: list[Annotated[Feature | SurfaceFeature | PCBOutline, Field()]] = Field(default_factory=list)
    default_csys_id: str = "origin"


class MateEntity(BaseModel):
    """One side of a mate relationship."""

    instance_id: str
    csys_id: str | None = None
    feature_id: str | None = None
    entity_id: str | None = None


class Mate(BaseModel):
    """Geometric relationship between part instances."""

    id: str
    name: str | None = None
    type: Literal[
        "coincident",
        "concentric",
        "distance",
        "angle",
        "parallel",
        "perpendicular",
        "fixed",
        "revolute",
        "prismatic",
    ]
    entities: list[MateEntity]
    parameters: dict[str, Any] = Field(default_factory=dict)


class Instance(BaseModel):
    """Placed copy of a part inside an assembly."""

    id: str
    part_id: str
    name: str | None = None
    transform: dict[str, Any] | None = None
    parameters: dict[str, NumericOrString] = Field(default_factory=dict)


class Assembly(BaseModel):
    """Collection of instances + mates + joints."""

    id: str
    domain: str = "mechanical"
    name: str | None = None
    instances: list[Instance] = Field(default_factory=list)
    mates: list[Mate] = Field(default_factory=list)
    joints: list[KinematicJoint] = Field(default_factory=list)


class FeatureTree(BaseModel):
    """Top-level document representing an editable parametric design."""

    schema_version: str = "2.0.0"
    design_id: str
    domain: str = "mechanical"
    prompt: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model: str | None = None
    units: str = "mm"
    parameters: list[Parameter] = Field(default_factory=list)
    coordinate_systems: list[CoordinateSystem] = Field(
        default_factory=lambda: [
            CoordinateSystem(
                id="origin",
                name="Global origin",
                origin=(0, 0, 0),
                x_axis=(1, 0, 0),
                y_axis=(0, 1, 0),
                z_axis=(0, 0, 1),
            )
        ]
    )
    parts: list[Part] = Field(default_factory=list)
    assemblies: list[Assembly] = Field(default_factory=list)
    features: list[Annotated[Feature | SurfaceFeature | PCBOutline, Field()]] = Field(
        default_factory=list,
        description="Top-level domain-specific features that are not tied to a single part.",
    )

    def parameter_dict(self) -> dict[str, NumericOrString]:
        """Return name → value mapping for all parameters."""
        return {p.name: p.value for p in self.parameters}

    def find_part(self, part_id: str) -> Part | None:
        for part in self.parts:
            if part.id == part_id:
                return part
        return None

    def find_feature(self, part_id: str, feature_id: str) -> Feature | None:
        part = self.find_part(part_id)
        if part is None:
            return None
        for feature in part.features:
            if feature.id == feature_id:
                return feature
        return None

    def find_sketch(self, part_id: str, sketch_id: str) -> Sketch | None:
        part = self.find_part(part_id)
        if part is None:
            return None
        for sketch in part.sketches:
            if sketch.id == sketch_id:
                return sketch
        return None

    def update_parameter(self, name: str, value: NumericOrString) -> "FeatureTree":
        """Return a new tree with one parameter value updated."""
        updated = self.model_copy(deep=True)
        for p in updated.parameters:
            if p.name == name:
                p.value = value
                p.expression = None
                break
        return updated

    def validate_tree(self) -> list[str]:
        """Lightweight structural validation. Returns list of error messages."""
        errors: list[str] = []
        if not self.parts:
            errors.append("Feature tree has no parts.")
        for part in self.parts:
            sketch_ids = {s.id for s in part.sketches}
            feature_ids = {f.id for f in part.features}
            for f in part.features:
                if f.sketch_id and f.sketch_id not in sketch_ids:
                    errors.append(
                        f"Feature '{f.id}' references missing sketch '{f.sketch_id}'."
                    )
                for dep in f.depends_on:
                    if dep not in feature_ids:
                        errors.append(
                            f"Feature '{f.id}' depends on missing feature '{dep}'."
                        )
        return errors
