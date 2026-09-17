"""Structural dynamics checks for RoboCAD morphology candidates.

Extracts link cross-section properties from robot templates and runs lightweight
beam bending / buckling checks. The lightweight formulas are conservative
pre-solver estimates; optional deep verification can be dispatched through the
existing CalculiX adapter for top-N candidates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_cad.feature_tree import FeatureTree, Part
from ai_cad.materials import Material, get_material


G = 9.80665


@dataclass
class LinkStructuralProperties:
    """Cross-section and material properties for one structural link."""

    name: str
    length_m: float
    area_m2: float
    i_min_m4: float
    i_max_m4: float
    r_min_m: float
    r_max_m: float
    material_name: str
    material: Material | None = None


@dataclass
class BeamCheckResult:
    """Outcome of a beam stress / buckling check."""

    name: str
    passed: bool
    safety_factor: float
    buckling_safety: float
    max_stress_mpa: float
    critical_buckling_load_n: float
    applied_load_n: float
    failure_modes: list[str]
    redesign_suggestions: list[str]


def _param_value(params: dict[str, Any], *names: str, default: float = 0.0) -> float:
    """Return the first matching parameter value in meters."""
    for name in names:
        if name in params:
            try:
                return float(params[name])
            except (TypeError, ValueError):
                continue
    return default


def _is_structural_part(part: Part) -> bool:
    """Return True if this part looks like a structural link."""
    return part.family in {"limb_segment", "link", "bracket"}


def _extract_dimensions_from_part(part: Part, tree_params: dict[str, Any]) -> dict[str, float]:
    """Try to read length/width/thickness from part parameters or tree parameters."""
    part_params: dict[str, Any] = {}
    if hasattr(part, "metadata") and isinstance(part.metadata, dict):
        part_params.update(part.metadata.get("parameters", {}))
    # Parameters may also be stored at the tree level with prefixed names.
    names = {
        "length": ("segment_length", "link_length", f"{part.id}_length"),
        "width": ("segment_width", "link_width", f"{part.id}_width"),
        "thickness": ("segment_thickness", "link_thickness", f"{part.id}_thickness"),
    }
    dims: dict[str, float] = {}
    for key, candidates in names.items():
        value_mm = _param_value(tree_params, *candidates)
        if value_mm <= 0.0 and part_params:
            value_mm = _param_value(part_params, *candidates)
        dims[key] = value_mm * 1e-3  # mm -> m
    return dims


def extract_link_properties(tree: FeatureTree, material: str = "PLA") -> list[LinkStructuralProperties]:
    """Extract structural-link properties from a morphology candidate.

    Looks for parts with family ``limb_segment``, ``link``, or ``bracket`` and
    computes cross-sectional area and second moments of area from the part
    dimensions. Falls back to conservative rectangle estimates when dimensions
    are missing.
    """
    tree_params = tree.parameter_dict() if hasattr(tree, "parameter_dict") else {}
    material_obj: Material | None = None
    try:
        material_obj = get_material(material)
    except KeyError:
        material_obj = None

    links: list[LinkStructuralProperties] = []
    for part in tree.parts:
        if not _is_structural_part(part):
            continue
        dims = _extract_dimensions_from_part(part, tree_params)
        length_m = dims.get("length", 0.0)
        width_m = dims.get("width", 0.0)
        thickness_m = dims.get("thickness", 0.0)

        # If dimensions are missing, estimate from parameter names commonly used
        # in robot templates.
        if length_m <= 0.0:
            length_m = _param_value(tree_params, "thigh_length", "shin_length", "upper_arm_length", "forearm_length", default=150.0) * 1e-3
        if width_m <= 0.0:
            width_m = _param_value(tree_params, "segment_width", "link_width", default=30.0) * 1e-3
        if thickness_m <= 0.0:
            thickness_m = _param_value(tree_params, "segment_thickness", "link_thickness", default=8.0) * 1e-3

        # Match length to the part name when possible.
        name_lower = (part.name or part.id).lower()
        if "thigh" in name_lower:
            length_m = _param_value(tree_params, "thigh_length", default=length_m * 1e3) * 1e-3
        elif "shin" in name_lower:
            length_m = _param_value(tree_params, "shin_length", default=length_m * 1e3) * 1e-3
        elif "upper_arm" in name_lower:
            length_m = _param_value(tree_params, "upper_arm_length", default=length_m * 1e3) * 1e-3
        elif "forearm" in name_lower:
            length_m = _param_value(tree_params, "forearm_length", default=length_m * 1e3) * 1e-3

        area_m2 = max(width_m * thickness_m, 1e-8)
        # Second moments of area for a rectangle about centroidal axes.
        i_strong = width_m * thickness_m**3 / 12.0
        i_weak = thickness_m * width_m**3 / 12.0
        i_min_m4 = min(i_weak, i_strong)
        i_max_m4 = max(i_weak, i_strong)
        r_min_m = math.sqrt(max(i_min_m4 / area_m2, 1e-12))
        r_max_m = math.sqrt(max(i_max_m4 / area_m2, 1e-12))

        links.append(
            LinkStructuralProperties(
                name=part.name or part.id,
                length_m=length_m,
                area_m2=area_m2,
                i_min_m4=i_min_m4,
                i_max_m4=i_max_m4,
                r_min_m=r_min_m,
                r_max_m=r_max_m,
                material_name=material,
                material=material_obj,
            )
        )
    return links
