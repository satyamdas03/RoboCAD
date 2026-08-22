"""Guess which editable parameter controls a clicked face.

The heuristic uses:
1. The clicked face's world-space normal to determine the dominant axis (X/Y/Z).
2. The mesh bounding box to map that axis to a dimension (length/width/thickness).
3. The list of extracted parameters to find the parameter whose value is closest to
   the relevant dimension and whose name semantically matches the axis.

This is intentionally a best-effort guess — it is meant to speed up editing, not
replace the explicit parameter panel.
"""
from __future__ import annotations

import math
from typing import Optional

from ai_cad.models import CADParameter


_AXIS_NAMES = {
    0: ("length", "width", "hole_spacing_x"),
    1: ("width", "length", "hole_spacing_y", "depth"),
    2: ("thickness", "height", "depth"),
}

_AXIS_KEYWORDS = {
    0: {"length", "long", "x", "hole_spacing_x", "spacing_x"},
    1: {"width", "y", "hole_spacing_y", "spacing_y", "depth"},
    2: {"thickness", "height", "z", "depth"},
}


def _dominant_axis(normal: tuple[float, float, float]) -> int:
    """Return the index (0=X, 1=Y, 2=Z) of the largest absolute component."""
    abs_n = [abs(v) for v in normal]
    return int(abs_n.index(max(abs_n)))


def _axis_extent(bounds_mm: tuple[float, float, float], axis: int) -> float:
    """Return the object's overall size along the given axis."""
    return float(bounds_mm[axis])


def _semantic_score(name: str, axis: int) -> float:
    """Score how semantically likely a parameter name is for the axis.

    Returns a value between 0 and 1. Higher means stronger match.
    """
    lower = name.lower()
    keywords = _AXIS_KEYWORDS[axis]
    for kw in keywords:
        if kw in lower:
            return 1.0
    # Fallback: does the name contain letters common to the generic axis names?
    generic = _AXIS_NAMES[axis]
    for g in generic:
        # Partial match, e.g. "plate_length" contains "length".
        if g in lower:
            return 1.0
    return 0.0


def guess_parameter(
    parameters: list[CADParameter],
    bounds_mm: tuple[float, float, float],
    face_normal: tuple[float, float, float],
    face_centroid: tuple[float, float, float] | None = None,
) -> dict:
    """Return the most likely parameter for the clicked face plus confidence.

    Args:
        parameters: editable parameters extracted from the generated code.
        bounds_mm: object bounding-box dimensions [dx, dy, dz].
        face_normal: world-space unit normal of the clicked face.
        face_centroid: world-space centroid of the clicked face (currently unused
            but reserved for future improvements such as signed-distance checks).

    Returns:
        dict with keys:
            - guessed_parameter: name of the best-matching parameter or None.
            - suggested_value: current value of that parameter.
            - confidence: 0-1 score combining axis fit and semantic fit.
            - axis: 0/1/2 (X/Y/Z).
            - reason: short human-readable explanation.
    """
    if not parameters:
        return {
            "guessed_parameter": None,
            "suggested_value": None,
            "confidence": 0.0,
            "axis": None,
            "reason": "No parameters available.",
        }

    axis = _dominant_axis(face_normal)
    extent = _axis_extent(bounds_mm, axis)
    axis_labels = ["X", "Y", "Z"]
    axis_name = axis_labels[axis]

    best: Optional[CADParameter] = None
    best_score = -1.0

    for param in parameters:
        value = float(param.value)
        # Relative error compared to the object's extent along this axis.
        size_score = 1.0 - min(abs(value - extent) / max(extent, 1.0), 1.0)
        semantic = _semantic_score(param.name, axis)

        # Combined score: strong preference for semantic match, then size match.
        # If semantic match exists, score is high; otherwise rely on size.
        if semantic >= 1.0:
            score = 0.7 + 0.3 * size_score
        else:
            score = 0.4 * size_score

        if score > best_score:
            best_score = score
            best = param

    if best is None:
        return {
            "guessed_parameter": None,
            "suggested_value": None,
            "confidence": 0.0,
            "axis": axis,
            "reason": f"No parameter matched the {axis_name} face.",
        }

    reason = f"{axis_name}-facing face; guessed '{best.name}' ({best.value}{best.unit or 'mm'})"
    return {
        "guessed_parameter": best.name,
        "suggested_value": best.value,
        "confidence": round(best_score, 3),
        "axis": axis,
        "reason": reason,
    }
