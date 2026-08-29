"""Transpile a RoboCAD FeatureTree into executable build123d Python code.

Phase 9 scope:
- single-part designs
- base-plane sketches (XY, YZ, ZX)
- sketch entities: rectangle, circle, line, arc
- features: extrude (add/subtract), revolve, fillet, chamfer, shell,
  mirror, linear_pattern, circular_pattern
- constraints and dimensions stored but not solved (Phase 10)

The generated script defines a top-level variable ``result`` that is the final
build123d shape, matching the contract expected by ``ai_cad.executor``.
"""
from __future__ import annotations

import textwrap
from typing import Any

from ai_cad.feature_tree import (
    EdgeSelector,
    Feature,
    FeatureTree,
    NumericOrString,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)
from ai_cad.sketch_solver import solve_sketch


def transpile(tree: FeatureTree, parameters: dict[str, float] | None = None) -> str:
    """Convert a feature tree into a build123d Python script."""
    if not tree.parts:
        raise ValueError("Feature tree has no parts to transpile.")

    parameters = parameters or tree.parameter_dict()

    lines: list[str] = []
    lines.append("from build123d import *")
    lines.append("")

    # Global parameter assignments.
    for param in tree.parameters:
        lines.append(_emit_parameter(param))
    lines.append("")

    # For Phase 9 we transpile the first part only.
    part = tree.parts[0]
    lines.extend(_transpile_part(part, parameters))
    lines.append("")
    lines.append("result = part.part")

    return "\n".join(lines)


def _emit_parameter(param: Parameter) -> str:
    """Emit a module-level parameter assignment."""
    value = param.value
    if isinstance(value, str):
        # Try to emit as a literal float/int if the string is numeric.
        try:
            float(value)
            rendered = value
        except ValueError:
            rendered = value
    else:
        rendered = str(int(value)) if isinstance(value, int) and value == int(value) else str(float(value))

    comment = f"  # param: {param.description}" if param.description else ""
    return f"{param.name} = {rendered}{comment}"


def _transpile_part(part: Part, parameters: dict[str, float], var_name: str = "part") -> list[str]:
    """Transpile a single part's sketches and features into a BuildPart context."""
    lines: list[str] = []
    lines.append(f"with BuildPart() as {var_name}:")

    sketch_blocks: list[str] = []
    for sketch in part.sketches:
        solved = solve_sketch(sketch, parameters)
        sketch_blocks.append(_transpile_sketch(solved))

    feature_blocks: list[str] = []
    for feature in part.features:
        if not feature.enabled:
            continue
        feature_blocks.append(_transpile_feature(feature, part, var_name=var_name))

    body_lines = []
    for block in sketch_blocks + feature_blocks:
        body_lines.extend(textwrap.indent(block, "    ").splitlines())

    if not body_lines:
        body_lines.append("    pass")

    lines.extend(body_lines)
    return lines


def _transpile_sketch(sketch: Sketch) -> str:
    """Emit a BuildSketch block for a sketch profile.

    Entity lines are indented so the block can be placed inside a BuildPart context.
    """
    plane_expr = _plane_expression(sketch.plane)
    lines: list[str] = []
    lines.append(f"with BuildSketch({plane_expr}) as {sketch.id}:")

    if not sketch.entities:
        lines.append("    pass")
    else:
        for entity in sketch.entities:
            lines.append(f"    {_transpile_entity(entity)}")

    return "\n".join(lines)


def _plane_expression(plane: PlaneReference) -> str:
    if plane.type == "base":
        name = plane.name or "XY"
        return {
            "XY": "Plane.XY",
            "YZ": "Plane.YZ",
            "ZX": "Plane.ZX",
        }.get(name, f"Plane.{name}")
    if plane.type == "face":
        face = plane.face_name or "top"
        return f"{plane.feature_id}.faces().sort_by(Axis.Z)[-1]" if face == "top" else f"{plane.feature_id}.faces().sort_by(Axis.Z)[0]"
    if plane.type == "offset":
        csys = plane.from_csys_id or "origin"
        offset = _render_value(plane.offset_z)
        return f"Plane(origin=(0,0,{offset}), z_dir=(0,0,1))"
    return "Plane.XY"


def _transpile_entity(entity: SketchEntity) -> str:
    etype = entity.type
    if etype == "rectangle":
        center = _render_point(entity.center, default=(0, 0))
        width = _render_value(entity.width, default=10)
        height = _render_value(entity.height, default=10)
        angle = _render_value(entity.angle, default=0)
        return f"Rectangle(width={width}, height={height}, align=Align.CENTER).rotate(Axis.Z, {angle}).move(Location({center}))"
    if etype == "circle":
        center = _render_point(entity.center, default=(0, 0))
        radius = _render_value(entity.radius, default=5)
        return f"Circle(radius={radius}).move(Location({center}))"
    if etype == "line":
        start = _render_point(entity.start, default=(0, 0))
        end = _render_point(entity.end, default=(10, 0))
        return f"Line({start}, {end})"
    if etype == "arc":
        center = _render_point(entity.center, default=(0, 0))
        radius = _render_value(entity.radius, default=5)
        start_angle = _render_value(entity.start_angle, default=0)
        end_angle = _render_value(entity.end_angle, default=90)
        return f"CenterArc(center={center}, radius={radius}, start_angle={start_angle}, end_angle={end_angle - start_angle})"
    if etype == "polygon":
        sides = entity.sides or 6
        center = _render_point(entity.center, default=(0, 0))
        radius = _render_value(entity.radius, default=5)
        return f"RegularPolygon(radius={radius}, side_count={sides}).move(Location({center}))"
    raise ValueError(f"Unsupported sketch entity type: {etype}")


def _transpile_feature(feature: Feature, part: Part, var_name: str = "part") -> str:
    ftype = feature.type
    params = feature.parameters

    if ftype == "extrude":
        amount = _render_value(params.get("amount"), default=10)
        direction = params.get("direction", "positive")
        mode = params.get("mode", "add")
        mode_expr = {"add": "Mode.ADD", "subtract": "Mode.SUBTRACT", "intersect": "Mode.INTERSECT"}.get(mode, "Mode.ADD")
        # build123d extrude uses positive amount for ADD and negative for SUBTRACT in the same mode.
        if direction == "negative" and mode == "subtract":
            amount = f"-{amount}"
        sketch_id = feature.sketch_id
        if not sketch_id:
            raise ValueError(f"extrude feature '{feature.id}' has no sketch_id")
        return f"extrude({sketch_id}.sketch, amount={amount}, mode={mode_expr})"

    if ftype == "revolve":
        axis = params.get("axis", {})
        angle = _render_value(params.get("angle", 360))
        sketch_id = feature.sketch_id
        if not sketch_id:
            raise ValueError(f"revolve feature '{feature.id}' has no sketch_id")
        # Phase 9: assume axis is the Y axis of the sketch plane.
        return f"revolve(axis=Axis.Y, angle={angle})"

    if ftype == "fillet":
        radius = _render_value(params.get("radius"), default=1)
        selector = _render_edge_selector(params.get("edges"), var_name=var_name)
        return f"fillet({selector}, radius={radius})"

    if ftype == "chamfer":
        distance = _render_value(params.get("distance"), default=1)
        distance1 = params.get("distance1")
        distance2 = params.get("distance2")
        selector = _render_edge_selector(params.get("edges"), var_name=var_name)
        if distance1 is not None and distance2 is not None:
            return f"chamfer({selector}, length={_render_value(distance1)}, length2={_render_value(distance2)})"
        return f"chamfer({selector}, length={distance})"

    if ftype == "shell":
        thickness = _render_value(params.get("thickness"), default=1)
        faces = params.get("faces_to_remove", [])
        if faces:
            # Map semantic face names to selectors and wrap in a list for hollow().
            face_exprs = [
                f"{var_name}.faces().sort_by(Axis.Z)[-1]" if f == "top" else f"{var_name}.faces().sort_by(Axis.Z)[0]"
                for f in faces
            ]
            face_expr = ", ".join(face_exprs)
            return f"{var_name}.part.hollow([{face_expr}], thickness={thickness})"
        return f"{var_name}.part.hollow([], thickness={thickness})"

    if ftype == "mirror":
        feature_ids = params.get("feature_ids", [])
        plane = params.get("plane", {"type": "base", "name": "YZ"})
        plane_expr = _plane_expression(PlaneReference(**plane))
        # Mirror in build123d works on the active part; feature_ids are ignored in this simple transpile.
        return f"mirror(about={plane_expr})"

    if ftype == "linear_pattern":
        feature_ids = params.get("feature_ids", [])
        spacing_x = _render_value(params.get("spacing_x"), default=10)
        spacing_y = _render_value(params.get("spacing_y"), default=10)
        count_x = params.get("count_x", 1)
        count_y = params.get("count_y", 1)
        return f"with GridLocations({spacing_x}, {spacing_y}, {count_x}, {count_y}):\n    pass"

    if ftype == "circular_pattern":
        feature_ids = params.get("feature_ids", [])
        axis = params.get("axis", {"type": "csys_axis", "csys_id": "origin", "axis": "z"})
        count = params.get("count", 4)
        total_angle = params.get("total_angle", 360)
        return f"with PolarLocations(radius=0, count={count}, start_angle=0, stop_angle={total_angle}):\n    pass"

    raise ValueError(f"Unsupported feature type: {ftype}")


def _render_point(value: Any, default: tuple[Any, Any]) -> str:
    if value is None:
        value = default
    x, y = value
    return f"({_render_value(x)}, {_render_value(y)})"


def _render_value(value: NumericOrString | None, default: NumericOrString | None = None) -> str:
    if value is None:
        if default is None:
            raise ValueError("Missing required value")
        value = default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(float(value))


def _render_edge_selector(selector: Any, var_name: str = "part") -> str:
    if selector is None:
        return f"{var_name}.edges()"
    if isinstance(selector, dict):
        sel_type = selector.get("type")
        if sel_type == "all":
            return f"{var_name}.edges()"
        if sel_type == "feature_edges":
            fid = selector.get("feature_id", var_name)
            return f"{fid}.edges()"
        if sel_type == "last_feature":
            return f"{var_name}.edges()"
    if isinstance(selector, EdgeSelector):
        return _render_edge_selector(selector.model_dump(), var_name=var_name)
    return f"{var_name}.edges()"
