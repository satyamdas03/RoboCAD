"""Closed load-case templates for the RoboCAD verification engine.

Every function is deterministic and uses simple mechanics formulas. They are
intentionally conservative pre-solver checks, not replacements for commercial
FEA/CFD packages.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from ai_cad.feature_tree import FeatureTree
from ai_cad.materials import Material, get_material
from ai_cad.verification_models import LoadCase, MeshQualityReport, VerificationResult


def _result(
    design_id: str,
    load_case: LoadCase,
    passed: bool,
    metrics: dict[str, float],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    failure_modes: list[str] | None = None,
    redesign_suggestions: list[str] | None = None,
    mesh_report: MeshQualityReport | None = None,
    raw_output: dict[str, Any] | None = None,
) -> VerificationResult:
    """Build a VerificationResult with normalized empty lists."""
    return VerificationResult(
        design_id=design_id,
        load_case=load_case,
        passed=passed,
        warnings=warnings or [],
        errors=errors or [],
        metrics=metrics,
        failure_modes=failure_modes or [],
        redesign_suggestions=redesign_suggestions or [],
        mesh_report=mesh_report,
        raw_output=raw_output,
    )


def _load_mesh(stl_path: Path | str) -> trimesh.Trimesh | None:
    try:
        mesh = trimesh.load_mesh(str(stl_path))
    except Exception:
        return None
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            mesh = next(iter(mesh.geometry.values()))
        else:
            return None
    return mesh


def _get_axis_index(face: str) -> int:
    axis_map = {"+x": 0, "-x": 0, "+y": 1, "-y": 1, "+z": 2, "-z": 2}
    if face not in axis_map:
        raise ValueError(f"Unknown face: {face}")
    return axis_map[face]


def _resolve_material(params: dict[str, Any], default: str = "PLA") -> Material:
    name = params.get("material", default)
    return get_material(name)


# ---------------------------------------------------------------------------
# Structural
# ---------------------------------------------------------------------------

def static_stress(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Simple cantilever beam stress estimate."""
    fixed_face = params.get("fixed_face", "-x")
    load_magnitude_n = float(params.get("load_magnitude_n", 100.0))
    safety_factor_target = float(params.get("safety_factor_target", 2.0))

    axis = _get_axis_index(fixed_face)
    bounds = mesh.bounds
    length = float(bounds[1, axis] - bounds[0, axis])
    if length <= 0:
        return _result(
            design_id,
            LoadCase.STATIC_STRESS,
            False,
            {},
            errors=["Computed length is zero."],
            failure_modes=["invalid_geometry"],
            redesign_suggestions=["Check that the part has non-zero extents."],
        )

    extents = mesh.extents
    area_axes = [i for i in range(3) if i != axis]
    b, h = float(extents[area_axes[0]]), float(extents[area_axes[1]])
    I = b * h**3 / 12.0
    if I <= 0:
        return _result(
            design_id,
            LoadCase.STATIC_STRESS,
            False,
            {},
            errors=["Computed moment of inertia is zero."],
            failure_modes=["invalid_geometry"],
        )

    max_moment = load_magnitude_n * length
    max_stress = (max_moment * (h / 2.0)) / I
    max_displacement = (load_magnitude_n * length**3) / (3.0 * material.youngs_modulus_mpa * I)
    safety_factor = material.yield_strength_mpa / max_stress if max_stress > 0 else None

    passed = bool(safety_factor is not None and safety_factor >= safety_factor_target)
    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("yield_exceeded_or_low_safety_factor")
        suggestions.append(f"Increase thickness along bending axis (currently h={h:.2f} mm).")
        suggestions.append("Add ribs or switch to a stronger material.")

    metrics = {
        "max_stress_mpa": round(max_stress, 4),
        "max_displacement_mm": round(max_displacement, 4),
        "yield_strength_mpa": material.yield_strength_mpa,
        "safety_factor": round(safety_factor, 2) if safety_factor is not None else 0.0,
        "load_magnitude_n": load_magnitude_n,
        "length_mm": length,
    }
    return _result(
        design_id,
        LoadCase.STATIC_STRESS,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
        raw_output={"moment_of_inertia_mm4": round(I, 4), "cross_section_b_mm": b, "cross_section_h_mm": h},
    )


def drop_test(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate peak deceleration from a drop and compare to yield stress.

    Uses a simplified impact factor: sigma_impact = sigma_static * impact_factor.
    """
    drop_height_m = float(params.get("drop_height_m", 1.0))
    impact_duration_s = float(params.get("impact_duration_s", 0.005))
    safety_factor_target = float(params.get("safety_factor_target", 2.0))

    mass_kg = float(mesh.volume) * 1e-9 * material.density_kg_m3 if mesh.volume else 0.0
    if mass_kg <= 0:
        return _result(
            design_id,
            LoadCase.DROP_TEST,
            False,
            {},
            errors=["Computed mass is zero."],
            failure_modes=["invalid_geometry"],
        )

    impact_velocity = math.sqrt(2.0 * 9.81 * drop_height_m)
    peak_acceleration_g = impact_velocity / (impact_duration_s * 9.81)
    impact_force_n = mass_kg * peak_acceleration_g * 9.81

    # Reuse static stress geometry with impact force.
    static_result = static_stress(
        design_id,
        mesh,
        material,
        {**params, "load_magnitude_n": impact_force_n, "safety_factor_target": safety_factor_target},
    )
    impact_stress = static_result.metrics.get("max_stress_mpa", 0.0) * peak_acceleration_g
    safety_factor = material.yield_strength_mpa / impact_stress if impact_stress > 0 else None
    passed = bool(safety_factor is not None and safety_factor >= safety_factor_target)

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("impact_yield_exceeded")
        suggestions.append("Increase wall thickness or add impact-absorbing features.")
        suggestions.append("Switch to a tougher material (PETG/Nylon/TPU).")

    metrics = {
        "mass_kg": round(mass_kg, 6),
        "impact_velocity_m_s": round(impact_velocity, 4),
        "peak_acceleration_g": round(peak_acceleration_g, 2),
        "impact_force_n": round(impact_force_n, 4),
        "impact_stress_mpa": round(impact_stress, 4),
        "safety_factor": round(safety_factor, 2) if safety_factor is not None else 0.0,
    }
    return _result(
        design_id,
        LoadCase.DROP_TEST,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


def thermal_expansion(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate linear expansion from a temperature rise."""
    delta_t_c = float(params.get("delta_t_c", 50.0))
    clearance_mm = float(params.get("clearance_mm", 0.5))

    bounds = mesh.bounds
    lengths = [float(bounds[1, i] - bounds[0, i]) for i in range(3)]
    max_length = max(lengths)
    delta_l_mm = max_length * material.thermal_expansion_per_k * delta_t_c
    passed = delta_l_mm <= clearance_mm

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("thermal_clearance_exceeded")
        suggestions.append("Increase clearance gaps or add compliant mounts.")
        suggestions.append("Switch to a lower thermal-expansion material (e.g., Titanium, FR4).")

    metrics = {
        "max_dimension_mm": round(max_length, 4),
        "delta_t_c": delta_t_c,
        "thermal_expansion_mm": round(delta_l_mm, 6),
        "clearance_mm": clearance_mm,
        "thermal_expansion_per_k": material.thermal_expansion_per_k,
    }
    return _result(
        design_id,
        LoadCase.THERMAL_EXPANSION,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


def fatigue_cycles(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Rough S-N estimate using a generic exponent for metals/polymers."""
    stress_amplitude_mpa = float(params.get("stress_amplitude_mpa", 20.0))
    cycles_target = float(params.get("cycles_target", 1e6))
    endurance_fraction = float(params.get("endurance_fraction", 0.4))

    endurance_limit = material.yield_strength_mpa * endurance_fraction
    # Simplified Basquin: N = C / sigma^b. Calibrate so endurance_limit -> cycles_target.
    b = 8.0 if material.yield_strength_mpa > 100.0 else 6.0
    C = cycles_target * (endurance_limit ** b)
    if stress_amplitude_mpa <= 0:
        cycles_to_failure = float("inf")
    else:
        cycles_to_failure = C / (stress_amplitude_mpa ** b)

    passed = cycles_to_failure >= cycles_target
    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("fatigue_life_below_target")
        suggestions.append("Reduce stress concentration or increase cross-section.")
        suggestions.append("Switch to a higher-endurance material or add fillets.")

    metrics = {
        "stress_amplitude_mpa": stress_amplitude_mpa,
        "endurance_limit_mpa": round(endurance_limit, 4),
        "cycles_to_failure": round(cycles_to_failure, 2),
        "cycles_target": cycles_target,
    }
    return _result(
        design_id,
        LoadCase.FATIGUE_CYCLES,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


def fastener_pull_out(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate shear/tensile capacity of a common machine screw."""
    diameter_mm = float(params.get("diameter_mm", 3.0))
    engagement_length_mm = float(params.get("engagement_length_mm", 6.0))
    load_n = float(params.get("load_n", 500.0))
    safety_factor_target = float(params.get("safety_factor_target", 2.0))

    area_mm2 = math.pi * (diameter_mm / 2.0) ** 2
    shear_strength_mpa = material.yield_strength_mpa * 0.6
    tensile_capacity_n = area_mm2 * material.yield_strength_mpa
    shear_capacity_n = area_mm2 * shear_strength_mpa
    thread_shear_area = math.pi * diameter_mm * engagement_length_mm
    pull_out_capacity_n = thread_shear_area * shear_strength_mpa

    min_capacity = min(tensile_capacity_n, shear_capacity_n, pull_out_capacity_n)
    safety_factor = min_capacity / load_n if load_n > 0 else float("inf")
    passed = safety_factor >= safety_factor_target

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("fastener_capacity_exceeded")
        suggestions.append(f"Increase screw engagement length (currently {engagement_length_mm} mm).")
        suggestions.append("Use a larger diameter or stronger material.")

    metrics = {
        "diameter_mm": diameter_mm,
        "engagement_length_mm": engagement_length_mm,
        "load_n": load_n,
        "tensile_capacity_n": round(tensile_capacity_n, 4),
        "shear_capacity_n": round(shear_capacity_n, 4),
        "pull_out_capacity_n": round(pull_out_capacity_n, 4),
        "safety_factor": round(safety_factor, 2),
    }
    return _result(
        design_id,
        LoadCase.FASTENER_PULL_OUT,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Aero / CFD
# ---------------------------------------------------------------------------

def wind_tunnel_drag(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate drag force on the frontal area of the part."""
    velocity_m_s = float(params.get("velocity_m_s", 10.0))
    drag_coefficient = float(params.get("drag_coefficient", 1.0))
    air_density_kg_m3 = float(params.get("air_density_kg_m3", 1.225))

    # Frontal area: projection on the smallest bounding-box face.
    extents_m = mesh.extents * 1e-3
    areas = [extents_m[i] * extents_m[j] for (i, j) in [(0, 1), (0, 2), (1, 2)]]
    frontal_area_m2 = min(areas)

    drag_force_n = 0.5 * air_density_kg_m3 * velocity_m_s**2 * drag_coefficient * frontal_area_m2
    # Simple power estimate: P = F * v.
    power_w = drag_force_n * velocity_m_s

    passed = True  # Drag is a metric, not a hard pass/fail unless overridden.
    threshold_n = float(params.get("drag_threshold_n", 50.0))
    if drag_force_n > threshold_n:
        passed = False

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("drag_force_above_threshold")
        suggestions.append("Reduce frontal area or streamline the shape.")
        suggestions.append("Add fairings or reduce drag coefficient.")

    metrics = {
        "velocity_m_s": velocity_m_s,
        "frontal_area_m2": round(frontal_area_m2, 8),
        "drag_coefficient": drag_coefficient,
        "drag_force_n": round(drag_force_n, 6),
        "drag_power_w": round(power_w, 6),
        "drag_threshold_n": threshold_n,
    }
    return _result(
        design_id,
        LoadCase.WIND_TUNNEL_DRAG,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Thermal
# ---------------------------------------------------------------------------

def heat_sink_thermal_resistance(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate total thermal resistance of a heat sink part."""
    heat_flux_w = float(params.get("heat_flux_w", 10.0))
    ambient_temp_c = float(params.get("ambient_temp_c", 25.0))
    convection_coefficient_w_per_m2_k = float(params.get("convection_coefficient_w_per_m2_k", 50.0))
    target_theta_c_per_w = float(params.get("target_theta_c_per_w", 5.0))

    if mesh.area is None or mesh.area <= 0:
        return _result(
            design_id,
            LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
            False,
            {},
            errors=["Mesh surface area unavailable."],
            failure_modes=["invalid_geometry"],
        )

    total_area_m2 = float(mesh.area) * 1e-6
    bounds = mesh.bounds
    extents_m = (bounds[1] - bounds[0]) * 1e-3
    base_thickness_m = min(extents_m) if len(extents_m) >= 3 else 0.002
    base_area_m2 = float(extents_m[0] * extents_m[1])

    # Convection resistance over total surface area.
    r_conv = 1.0 / (convection_coefficient_w_per_m2_k * total_area_m2)
    # Conduction resistance through base plate.
    r_cond = base_thickness_m / (material.conductivity_w_m_k * base_area_m2) if base_area_m2 > 0 else 0.0
    r_total = r_conv + r_cond
    delta_t = heat_flux_w * r_total
    max_temp = ambient_temp_c + delta_t

    passed = r_total <= target_theta_c_per_w
    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("thermal_resistance_too_high")
        suggestions.append("Increase fin count or fin height to raise surface area.")
        suggestions.append("Use a more conductive material (Copper/Aluminum) or forced airflow.")

    metrics = {
        "total_surface_area_m2": round(total_area_m2, 8),
        "base_area_m2": round(base_area_m2, 8),
        "base_thickness_m": round(base_thickness_m, 6),
        "thermal_resistance_c_per_w": round(r_total, 6),
        "target_theta_c_per_w": target_theta_c_per_w,
        "delta_t_c": round(delta_t, 4),
        "max_temperature_c": round(max_temp, 4),
    }
    return _result(
        design_id,
        LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Dynamics
# ---------------------------------------------------------------------------

def joint_torque_check(
    design_id: str,
    mesh: trimesh.Trimesh,
    material: Material,
    params: dict[str, Any],
) -> VerificationResult:
    """Estimate required joint torque to hold or lift a load."""
    load_mass_kg = float(params.get("load_mass_kg", 1.0))
    arm_length_m = float(params.get("arm_length_m", 0.2))
    stall_torque_nm = float(params.get("stall_torque_nm", 2.0))
    safety_factor_target = float(params.get("safety_factor_target", 1.5))

    required_torque_nm = load_mass_kg * 9.81 * arm_length_m
    safety_factor = stall_torque_nm / required_torque_nm if required_torque_nm > 0 else float("inf")
    passed = safety_factor >= safety_factor_target

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("joint_torque_insufficient")
        suggestions.append("Select a higher-torque actuator.")
        suggestions.append("Reduce arm length or load mass, or add a counterbalance/gearbox.")

    metrics = {
        "load_mass_kg": load_mass_kg,
        "arm_length_m": arm_length_m,
        "required_torque_nm": round(required_torque_nm, 6),
        "stall_torque_nm": stall_torque_nm,
        "safety_factor": round(safety_factor, 2),
    }
    return _result(
        design_id,
        LoadCase.JOINT_TORQUE_CHECK,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Humanoid / legged robot checks
# ---------------------------------------------------------------------------

def humanoid_stability_check(
    design_id: str,
    tree: FeatureTree,
    params: dict[str, Any],
) -> VerificationResult:
    """Check support polygon, ZMP, and gait feasibility for a legged design."""
    from ai_cad.stability import StabilityReport, check_stability, stability_summary

    robot_mass_kg = float(params.get("robot_mass_kg", 20.0))
    com_height_m = params.get("com_height_m")
    if com_height_m is not None:
        com_height_m = float(com_height_m)
    lateral_accel_m_s2 = float(params.get("lateral_accel_m_s2", 0.5))

    report = check_stability(tree, robot_mass_kg, com_height_m, lateral_accel_m_s2)
    summary = stability_summary(report)
    passed = report.statically_stable and report.dynamically_stable and report.gait_feasible

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not report.statically_stable:
        failure_modes.append("static_stability_margin_low")
        suggestions.append("Increase foot size or stance width; lower CoM height.")
    if not report.dynamically_stable:
        failure_modes.append("zmp_exits_support_polygon")
        suggestions.append("Increase lateral support margin or reduce lateral acceleration budget.")
    if not report.gait_feasible:
        failure_modes.append("gait_feasibility_gate_failed")
        suggestions.append("Increase support polygon area and ensure at least two contact feet.")

    return _result(
        design_id,
        LoadCase.STABILITY_CHECK,
        passed,
        summary,
        warnings=report.warnings,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
        raw_output=summary,
    )


def reachable_workspace_check(
    design_id: str,
    tree: FeatureTree,
    params: dict[str, Any],
) -> VerificationResult:
    """Sample reachable workspace of a target end-effector / foot."""
    from ai_cad.kinematic_tree import sample_reachable_workspace

    end_effector_id = str(params.get("end_effector_id", "hand_r"))
    samples_per_joint = int(params.get("samples_per_joint", 5))

    result = sample_reachable_workspace(tree, end_effector_id, samples_per_joint=samples_per_joint)
    envelope = result.get("envelope_mm", (0.0, 0.0, 0.0))
    volume = result.get("volume_estimate_mm3", 0.0)
    min_envelope = float(params.get("min_envelope_mm", 100.0))
    min_volume = float(params.get("min_volume_mm3", 1e6))

    passed = all(e >= min_envelope for e in envelope) and volume >= min_volume

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not passed:
        failure_modes.append("reachable_workspace_too_small")
        suggestions.append("Increase limb segment lengths or joint limits.")
        suggestions.append("Verify the end-effector id exists in the assembly.")

    metrics = {
        "end_effector_id": end_effector_id,
        "point_count": float(result.get("point_count", 0)),
        "envelope_x_mm": round(envelope[0], 4),
        "envelope_y_mm": round(envelope[1], 4),
        "envelope_z_mm": round(envelope[2], 4),
        "volume_estimate_mm3": round(volume, 4),
    }
    return _result(
        design_id,
        LoadCase.REACHABLE_WORKSPACE,
        passed,
        metrics,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
        raw_output=result,
    )


def gait_feasibility_check(
    design_id: str,
    tree: FeatureTree,
    params: dict[str, Any],
) -> VerificationResult:
    """Aggregate gait feasibility: stability + workspace of swing foot."""
    from ai_cad.stability import check_stability

    robot_mass_kg = float(params.get("robot_mass_kg", 20.0))
    lateral_accel_m_s2 = float(params.get("lateral_accel_m_s2", 0.5))
    report = check_stability(tree, robot_mass_kg, lateral_accel_m_s2=lateral_accel_m_s2)

    # Workspace check for one foot as a swing leg proxy.
    from ai_cad.kinematic_tree import sample_reachable_workspace

    swing_foot_id = str(params.get("swing_foot_id", "foot_l"))
    workspace = sample_reachable_workspace(tree, swing_foot_id, samples_per_joint=4)
    envelope = workspace.get("envelope_mm", (0.0, 0.0, 0.0))
    min_step_height = float(params.get("min_step_height_mm", 30.0))
    min_step_length = float(params.get("min_step_length_mm", 50.0))

    passed = report.gait_feasible and envelope[2] >= min_step_height and envelope[0] >= min_step_length

    failure_modes: list[str] = []
    suggestions: list[str] = []
    if not report.gait_feasible:
        failure_modes.append("stability_gate_failed")
        suggestions.append("Increase support polygon or lower CoM.")
    if envelope[2] < min_step_height:
        failure_modes.append("insufficient_step_height")
        suggestions.append("Increase shin/ankle length or joint limits to raise foot.")
    if envelope[0] < min_step_length:
        failure_modes.append("insufficient_step_length")
        suggestions.append("Increase thigh length or hip pitch range.")

    metrics = {
        "gait_feasible": 1.0 if report.gait_feasible else 0.0,
        "statically_stable": 1.0 if report.statically_stable else 0.0,
        "dynamically_stable": 1.0 if report.dynamically_stable else 0.0,
        "swing_envelope_x_mm": round(envelope[0], 4),
        "swing_envelope_y_mm": round(envelope[1], 4),
        "swing_envelope_z_mm": round(envelope[2], 4),
    }
    return _result(
        design_id,
        LoadCase.GAIT_FEASIBILITY,
        passed,
        metrics,
        warnings=report.warnings,
        failure_modes=failure_modes,
        redesign_suggestions=suggestions,
    )
