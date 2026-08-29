"""Small internal 2D geometric constraint solver for RoboCAD sketches.

Phase 10 scope:
- distance, horizontal, vertical, coincident, concentric, equal, fix
- Driving dimensions: distance, radius, diameter, angle
- Non-linear constraints are solved with scipy.optimize.least_squares.

Each sketch entity exposes a set of control points. Constraint references can use
entity IDs ("circle1") or point handles ("line1.start", "circle1.center").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from ai_cad.feature_tree import (
    Constraint,
    Dimension,
    NumericOrString,
    PlaneReference,
    Sketch,
    SketchEntity,
)


@dataclass(frozen=True)
class _Handle:
    """Named control point of a sketch entity."""

    entity_id: str
    point_name: str  # e.g. "center", "start", "end"


@dataclass
class _VariableSet:
    """Maps control-point handles to flat variable indices."""

    x_indices: dict[_Handle, int]
    y_indices: dict[_Handle, int]
    radius_indices: dict[str, int]
    angle_indices: dict[str, int]

    @property
    def size(self) -> int:
        return max(
            (max(self.x_indices.values()) if self.x_indices else -1),
            (max(self.y_indices.values()) if self.y_indices else -1),
            (max(self.radius_indices.values()) if self.radius_indices else -1),
            (max(self.angle_indices.values()) if self.angle_indices else -1),
        ) + 1


def _resolve_value(value: NumericOrString, parameters: dict[str, float]) -> float:
    """Resolve a parameter name or numeric literal to a float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value in parameters:
            return float(parameters[value])
        # Try simple arithmetic literals like "hole_diameter / 2".
        try:
            return float(eval(value, {"__builtins__": {}}, parameters))  # noqa: S307
        except Exception:
            raise ValueError(f"Could not resolve value: {value!r}")
    raise TypeError(f"Unsupported value type: {type(value)}")


def _entity_handles(entity: SketchEntity) -> list[_Handle]:
    """Return the control-point handles for an entity."""
    handles: list[_Handle] = []
    if entity.type in ("rectangle", "circle", "arc", "polygon"):
        handles.append(_Handle(entity.id, "center"))
    if entity.type in ("line",):
        handles.append(_Handle(entity.id, "start"))
        handles.append(_Handle(entity.id, "end"))
    return handles


def _initial_var_value(handle: _Handle, entity: SketchEntity) -> tuple[float, float]:
    """Get the initial (x, y) for a control point from the entity."""
    if handle.point_name == "center":
        cx, cy = entity.center or (0, 0)
        return (_to_float(cx), _to_float(cy))
    if handle.point_name == "start":
        sx, sy = entity.start or (0, 0)
        return (_to_float(sx), _to_float(sy))
    if handle.point_name == "end":
        ex, ey = entity.end or (10, 0)
        return (_to_float(ex), _to_float(ey))
    return (0.0, 0.0)


def _to_float(v: NumericOrString | None) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except ValueError:
        return 0.0


def _naca_4digit_points(code: str, chord: float, n: int = 40) -> list[tuple[float, float]]:
    """Return a simplified NACA 4-digit airfoil point set.

    The profile uses the standard NACA 4-digit thickness form. Camber is ignored
    in this simplified sketch representation; the result is a symmetric foil.
    """
    code = code.strip()
    if len(code) != 4 or not code.isdigit():
        raise ValueError(f"NACA 4-digit code must be four digits, got {code!r}")
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    tt = int(code[2:4]) / 100.0
    pts: list[tuple[float, float]] = []
    # Upper surface from leading to trailing edge.
    for i in range(n + 1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (
            0.2969 * xc**0.5
            - 0.1260 * xc
            - 0.3516 * xc**2
            + 0.2843 * xc**3
            - 0.1015 * xc**4
        )
        pts.append((x, yt))
    # Lower surface from trailing to leading edge.
    for i in range(n, -1, -1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (
            0.2969 * xc**0.5
            - 0.1260 * xc
            - 0.3516 * xc**2
            + 0.2843 * xc**3
            - 0.1015 * xc**4
        )
        pts.append((x, -yt))
    return pts


def _solve_airfoils(sketch: Sketch) -> dict[str, list[tuple[float, float]]]:
    """Compute point sets for any airfoil entities in the sketch."""
    points: dict[str, list[tuple[float, float]]] = {}
    for entity in sketch.entities:
        if entity.type == "airfoil" and entity.naca and entity.chord is not None:
            chord = _to_float(entity.chord)
            points[entity.id] = _naca_4digit_points(entity.naca, chord)
    return points


def _build_variables(sketch: Sketch) -> tuple[np.ndarray, _VariableSet]:
    """Build the flat variable vector and index map for a sketch."""
    x_indices: dict[_Handle, int] = {}
    y_indices: dict[_Handle, int] = {}
    radius_indices: dict[str, int] = {}
    angle_indices: dict[str, int] = {}
    values: list[float] = []

    for entity in sketch.entities:
        for handle in _entity_handles(entity):
            idx = len(values)
            x_indices[handle] = idx
            values.append(_initial_var_value(handle, entity)[0])
            idx = len(values)
            y_indices[handle] = idx
            values.append(_initial_var_value(handle, entity)[1])
        if entity.radius is not None:
            radius_indices[entity.id] = len(values)
            values.append(_to_float(entity.radius))
        if entity.angle is not None:
            angle_indices[entity.id] = len(values)
            values.append(math.radians(_to_float(entity.angle)))

    return np.array(values, dtype=float), _VariableSet(
        x_indices=x_indices,
        y_indices=y_indices,
        radius_indices=radius_indices,
        angle_indices=angle_indices,
    )


def _parse_reference(ref: str, entities: dict[str, SketchEntity]) -> _Handle | None:
    """Parse an entity ID or entity.point reference into a handle."""
    if "." in ref:
        entity_id, point_name = ref.split(".", 1)
        if entity_id in entities:
            return _Handle(entity_id, point_name)
        return None
    if ref in entities:
        entity = entities[ref]
        handles = _entity_handles(entity)
        if handles:
            # Default point: center for circles/rects/arcs/polygons, start for lines.
            return handles[0]
    return None


def _point_residuals(
    p1: _Handle,
    p2: _Handle,
    var_set: _VariableSet,
    vars_vec: np.ndarray,
) -> tuple[float, float]:
    """Return (x1-x2, y1-y2) residuals for two handles."""
    x1 = vars_vec[var_set.x_indices[p1]]
    y1 = vars_vec[var_set.y_indices[p1]]
    x2 = vars_vec[var_set.x_indices[p2]]
    y2 = vars_vec[var_set.y_indices[p2]]
    return (x1 - x2, y1 - y2)


def _distance(
    p1: _Handle,
    p2: _Handle,
    var_set: _VariableSet,
    vars_vec: np.ndarray,
) -> float:
    dx, dy = _point_residuals(p1, p2, var_set, vars_vec)
    return math.hypot(dx, dy)


def _build_residuals(
    sketch: Sketch,
    var_set: _VariableSet,
    parameters: dict[str, float],
) -> list[tuple[str, callable]]:
    """Return a list of (description, residual_function) pairs."""
    entities = {e.id: e for e in sketch.entities}
    residuals: list[tuple[str, callable]] = []

    for constraint in sketch.constraints:
        refs = [_parse_reference(r, entities) for r in constraint.entities]
        if any(r is None for r in refs):
            continue
        handles = [r for r in refs if r is not None]
        ct = constraint.type

        if ct == "coincident" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            residuals.append(
                (f"coincident {p1} == {p2}", lambda v, p1=p1, p2=p2, vs=var_set: _point_residuals(p1, p2, vs, v))
            )
        elif ct == "concentric" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            residuals.append(
                (f"concentric {p1} == {p2}", lambda v, p1=p1, p2=p2, vs=var_set: _point_residuals(p1, p2, vs, v))
            )
        elif ct == "horizontal" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            residuals.append(
                (f"horizontal {p1}-{p2}", lambda v, p1=p1, p2=p2, vs=var_set: (v[vs.y_indices[p1]] - v[vs.y_indices[p2]],))
            )
        elif ct == "vertical" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            residuals.append(
                (f"vertical {p1}-{p2}", lambda v, p1=p1, p2=p2, vs=var_set: (v[vs.x_indices[p1]] - v[vs.x_indices[p2]],))
            )
        elif ct == "fix" and len(handles) >= 1:
            p = handles[0]
            target = _initial_var_value(p, entities[p.entity_id])
            residuals.append(
                (f"fix {p}", lambda v, p=p, tx=target[0], ty=target[1], vs=var_set: (
                    v[vs.x_indices[p]] - tx,
                    v[vs.y_indices[p]] - ty,
                ))
            )
        elif ct == "equal" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            # If both have radii, equalize radii; otherwise equalize distance from origin (length proxy).
            if p1.entity_id in var_set.radius_indices and p2.entity_id in var_set.radius_indices:
                residuals.append(
                    (f"equal radius {p1.entity_id} == {p2.entity_id}",
                     lambda v, e1=p1.entity_id, e2=p2.entity_id, vs=var_set: (
                         v[vs.radius_indices[e1]] - v[vs.radius_indices[e2]],
                     ))
                )
            else:
                residuals.append(
                    (f"equal length {p1}-{p2}",
                     lambda v, p1=p1, p2=p2, vs=var_set: (
                         math.hypot(v[vs.x_indices[p1]], v[vs.y_indices[p1]])
                         - math.hypot(v[vs.x_indices[p2]], v[vs.y_indices[p2]]),
                     ))
                )

    for dimension in sketch.dimensions:
        refs = [_parse_reference(r, entities) for r in dimension.entities]
        if any(r is None for r in refs):
            continue
        handles = [r for r in refs if r is not None]
        target = _resolve_value(dimension.value, parameters)
        dt = dimension.type

        if dt in ("distance",) and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            residuals.append(
                (f"distance {dimension.name}={target}",
                 lambda v, p1=p1, p2=p2, t=target, vs=var_set: (
                     _distance(p1, p2, vs, v) - t,
                 ))
            )
        elif dt in ("radius",) and len(handles) >= 1:
            eid = handles[0].entity_id
            if eid in var_set.radius_indices:
                residuals.append(
                    (f"radius {dimension.name}={target}",
                     lambda v, eid=eid, t=target, vs=var_set: (v[vs.radius_indices[eid]] - t,))
                )
        elif dt in ("diameter",) and len(handles) >= 1:
            eid = handles[0].entity_id
            if eid in var_set.radius_indices:
                residuals.append(
                    (f"diameter {dimension.name}={target}",
                     lambda v, eid=eid, t=target, vs=var_set: (v[vs.radius_indices[eid]] - t / 2,))
                )
        elif dt == "angle" and len(handles) >= 2:
            p1, p2 = handles[0], handles[1]
            target_rad = math.radians(target)
            residuals.append(
                (f"angle {dimension.name}={target}",
                 lambda v, p1=p1, p2=p2, t=target_rad, vs=var_set: (
                     math.atan2(v[vs.y_indices[p2]] - v[vs.y_indices[p1]],
                                v[vs.x_indices[p2]] - v[vs.x_indices[p1]])
                     - t,
                 ))
            )

    return residuals


def solve_sketch(sketch: Sketch | list[SketchEntity], parameters: dict[str, float] | None = None) -> Sketch:
    """Return a new Sketch with constraints and driving dimensions solved.

    Uses scipy.optimize.least_squares to minimize the residuals. If no constraints
    or dimensions are present, the original sketch is returned unchanged.
    Airfoil entities are always converted to point sets.
    """
    if isinstance(sketch, list):
        sketch = Sketch(
            id="sketch",
            plane=PlaneReference(type="base", name="XY"),
            entities=sketch,
        )

    parameters = parameters or {}
    airfoil_points = _solve_airfoils(sketch)

    if not sketch.constraints and not sketch.dimensions:
        if airfoil_points:
            return sketch.model_copy(update={"points": airfoil_points}, deep=True)
        return sketch

    vars_vec, var_set = _build_variables(sketch)
    residuals = _build_residuals(sketch, var_set, parameters)

    if not residuals:
        if airfoil_points:
            return sketch.model_copy(update={"points": airfoil_points}, deep=True)
        return sketch

    def objective(v: np.ndarray) -> np.ndarray:
        return np.concatenate([np.atleast_1d(r(v)) for _, r in residuals])

    # Use 'trf' so under-determined systems (fewer residuals than variables) still
    # converge; add a tiny regularization term to keep the solution near the initial
    # sketch when constraints are loose.
    def regularized_objective(v: np.ndarray) -> np.ndarray:
        base = objective(v)
        reg = 1e-6 * (v - vars_vec)
        return np.concatenate([base, reg])

    result = least_squares(regularized_objective, vars_vec, method="trf", max_nfev=2000)
    solved = result.x

    # Build a new sketch with solved values.
    new_entities = []
    entities = {e.id: e for e in sketch.entities}
    for entity in sketch.entities:
        data: dict[str, Any] = entity.model_dump(mode="json")
        handle_center = _Handle(entity.id, "center")
        if handle_center in var_set.x_indices:
            x = solved[var_set.x_indices[handle_center]]
            y = solved[var_set.y_indices[handle_center]]
            data["center"] = (round(float(x), 6), round(float(y), 6))
        handle_start = _Handle(entity.id, "start")
        if handle_start in var_set.x_indices:
            x = solved[var_set.x_indices[handle_start]]
            y = solved[var_set.y_indices[handle_start]]
            data["start"] = (round(float(x), 6), round(float(y), 6))
        handle_end = _Handle(entity.id, "end")
        if handle_end in var_set.x_indices:
            x = solved[var_set.x_indices[handle_end]]
            y = solved[var_set.y_indices[handle_end]]
            data["end"] = (round(float(x), 6), round(float(y), 6))
        if entity.id in var_set.radius_indices:
            data["radius"] = round(float(solved[var_set.radius_indices[entity.id]]), 6)
        if entity.id in var_set.angle_indices:
            data["angle"] = round(float(math.degrees(solved[var_set.angle_indices[entity.id]])), 6)
        new_entities.append(SketchEntity(**data))

    # Merge any airfoil points into the solved sketch points.
    final_points = {**airfoil_points, **sketch.points}

    return Sketch(
        id=sketch.id,
        name=sketch.name,
        plane=sketch.plane,
        entities=new_entities,
        constraints=sketch.constraints,
        dimensions=sketch.dimensions,
        points=final_points,
    )
