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


def _recover_rectangular_dimensions(link: LinkStructuralProperties) -> tuple[float, float]:
    """Recover width and thickness from area and second moments of area.

    Assumes a rectangular cross-section. ``width`` is the larger in-plane
    dimension and ``thickness`` is the smaller one.
    """
    area = max(link.area_m2, 1e-12)
    i_max = max(link.i_max_m4, 1e-18)
    i_min = max(link.i_min_m4, 1e-18)
    ratio = math.sqrt(i_max / i_min)
    width = math.sqrt(area * ratio)
    thickness = area / width
    return width, thickness


def beam_check(
    link: LinkStructuralProperties,
    load_case: str = "cantilever_payload",
    payload_kg: float = 0.0,
    drop_height_m: float = 0.0,
    safety_factor_target: float = 2.0,
    impact_duration_s: float = 0.005,
) -> BeamCheckResult:
    """Run conservative beam stress and Euler-buckling checks on one link.

    ``load_case`` supports ``cantilever_payload`` and ``simply_supported_payload``.
    The applied load includes payload plus the link's own self-weight.
    """
    material = link.material
    if material is None:
        return BeamCheckResult(
            name=link.name,
            passed=False,
            safety_factor=0.0,
            buckling_safety=0.0,
            max_stress_mpa=0.0,
            critical_buckling_load_n=0.0,
            applied_load_n=0.0,
            failure_modes=["unknown_material"],
            redesign_suggestions=["Specify a known material for structural checks."],
        )

    width_m, thickness_m = _recover_rectangular_dimensions(link)
    length_m = max(link.length_m, 1e-6)
    area_m2 = link.area_m2

    # Applied load = payload + self-weight (conservative point-load approximation).
    self_weight_n = material.density_kg_m3 * area_m2 * length_m * G
    payload_n = payload_kg * G
    applied_load_n = payload_n + self_weight_n

    # Impact factor for drop test.
    impact_factor = 1.0
    if drop_height_m > 0.0:
        impact_velocity = math.sqrt(2.0 * G * drop_height_m)
        peak_accel_g = impact_velocity / (impact_duration_s * G)
        impact_factor = max(1.0, peak_accel_g)
    effective_load_n = applied_load_n * impact_factor

    # Moment and stress about the strong axis (I_max).
    if load_case == "cantilever_payload":
        max_moment = effective_load_n * length_m
        k_buckling = 2.0
    elif load_case == "simply_supported_payload":
        max_moment = effective_load_n * length_m / 4.0
        k_buckling = 1.0
    else:
        # Default to cantilever.
        max_moment = effective_load_n * length_m
        k_buckling = 2.0

    # Distance from neutral axis to extreme fiber for strong-axis bending.
    c_m = width_m / 2.0
    i_max_m4 = max(link.i_max_m4, 1e-18)
    max_stress_pa = (max_moment * c_m) / i_max_m4
    max_stress_mpa = max_stress_pa / 1e6
    safety_factor = material.yield_strength_mpa / max_stress_mpa if max_stress_mpa > 0.0 else float("inf")

    # Euler buckling about the weak axis.
    i_min_m4 = max(link.i_min_m4, 1e-18)
    e_pa = material.youngs_modulus_mpa * 1e6
    critical_buckling_load_n = (math.pi**2 * e_pa * i_min_m4) / ((k_buckling * length_m) ** 2)
    buckling_safety = critical_buckling_load_n / effective_load_n if effective_load_n > 0.0 else float("inf")

    failure_modes: list[str] = []
    suggestions: list[str] = []
    passed = True
    if safety_factor < safety_factor_target:
        passed = False
        failure_modes.append("yield_exceeded")
        suggestions.append(f"Increase thickness or width of {link.name}; current safety factor {safety_factor:.2f}.")
    if buckling_safety < safety_factor_target:
        passed = False
        failure_modes.append("buckling")
        suggestions.append(f"Shorten {link.name} or increase its weak-axis second moment of area; current buckling safety {buckling_safety:.2f}.")
    if not failure_modes:
        suggestions.append("Link passes conservative stress and buckling checks.")

    return BeamCheckResult(
        name=link.name,
        passed=passed,
        safety_factor=safety_factor,
        buckling_safety=buckling_safety,
        max_stress_mpa=max_stress_mpa,
        critical_buckling_load_n=critical_buckling_load_n,
        applied_load_n=applied_load_n,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


def score_candidate_structural(
    tree: FeatureTree,
    payload_kg: float = 0.0,
    material: str = "PLA",
) -> dict[str, Any]:
    """Return a lightweight structural score for a morphology candidate.

    Score is the fraction of structural links that pass stress and buckling
    checks. Returns 1.0 when no structural links are found.
    """
    links = extract_link_properties(tree, material=material)
    if not links:
        return {
            "structural_score": 1.0,
            "links": [],
            "worst_link": None,
            "notes": "no structural links found",
        }
    results = [beam_check(link, "cantilever_payload", payload_kg=payload_kg) for link in links]
    ok = sum(1 for r in results if r.passed)
    score = ok / len(results)
    worst = min(results, key=lambda r: min(r.safety_factor, r.buckling_safety))
    return {
        "structural_score": score,
        "links": [r.__dict__ for r in results],
        "worst_link": worst.name,
        "notes": f"{ok}/{len(results)} links passed",
    }


def run_deep_structural_for_candidate(
    tree: FeatureTree,
    design_dir: Path,
    payload_kg: float = 0.0,
    material: str = "PLA",
    solver_mode: str = "auto",
) -> dict[str, Any]:
    """Dispatch deep structural verification for a morphology candidate.

    Exports the candidate to a bundle, then runs the existing deep verification
    dispatcher in static-stress mode. Falls back gracefully if the solver is
    unavailable or the export fails.
    """
    # Lazy imports avoid circular dependencies at module load time.
    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.solvers.verification_deep import run_deep_verification
    from ai_cad.verification_models import LoadCase

    try:
        export_bundle_from_tree(tree, design_dir)
    except Exception as exc:
        return {"deep_available": False, "error": f"export failed: {exc}"}

    params = {
        "load_magnitude_n": payload_kg * G,
        "safety_factor_target": 2.0,
        "material": material,
        "solver_mode": solver_mode,
    }
    try:
        result = run_deep_verification(
            design_id="candidate",
            load_case=LoadCase.STATIC_STRESS,
            params=params,
            design_dir=design_dir,
        )
    except Exception as exc:
        return {"deep_available": False, "error": f"solver dispatch failed: {exc}"}

    return {
        "deep_available": True,
        "passed": result.passed,
        "metrics": dict(result.metrics),
        "failure_modes": list(result.failure_modes),
        "redesign_suggestions": list(result.redesign_suggestions),
        "errors": list(result.errors),
    }
