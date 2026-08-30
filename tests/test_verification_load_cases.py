"""Tests for deterministic closed load-case templates."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from ai_cad.materials import get_material
from ai_cad.verification_load_cases import (
    drop_test,
    fastener_pull_out,
    fatigue_cycles,
    heat_sink_thermal_resistance,
    joint_torque_check,
    static_stress,
    thermal_expansion,
    wind_tunnel_drag,
)
from ai_cad.verification_models import LoadCase


@pytest.fixture
def box():
    return trimesh.creation.box(extents=(20.0, 10.0, 5.0))


@pytest.fixture
def long_bar():
    return trimesh.creation.box(extents=(100.0, 10.0, 10.0))


def test_static_stress_passes_for_strong_material(long_bar):
    mat = get_material("Aluminum 6061")
    result = static_stress(
        "test",
        long_bar,
        mat,
        {"fixed_face": "-x", "load_magnitude_n": 50.0, "safety_factor_target": 2.0},
    )
    assert result.load_case == LoadCase.STATIC_STRESS
    assert result.passed is True
    assert result.metrics["safety_factor"] >= 2.0
    assert result.metrics["max_stress_mpa"] > 0
    assert result.metrics["max_displacement_mm"] >= 0


def test_static_stress_fails_for_weak_material(long_bar):
    mat = get_material("PLA")
    result = static_stress(
        "test",
        long_bar,
        mat,
        {"fixed_face": "-x", "load_magnitude_n": 1000.0, "safety_factor_target": 2.0},
    )
    assert result.passed is False
    assert "yield_exceeded_or_low_safety_factor" in result.failure_modes
    assert result.redesign_suggestions


def test_static_stress_invalid_geometry():
    mesh = trimesh.creation.box(extents=(0.0, 0.0, 0.0))
    result = static_stress("test", mesh, get_material("PLA"), {"fixed_face": "-x"})
    assert result.passed is False
    assert result.errors


def test_drop_test_reports_metrics(long_bar):
    result = drop_test(
        "test",
        long_bar,
        get_material("PLA"),
        {"drop_height_m": 0.5, "impact_duration_s": 0.005, "safety_factor_target": 2.0},
    )
    assert result.load_case == LoadCase.DROP_TEST
    assert "mass_kg" in result.metrics
    assert "impact_force_n" in result.metrics
    assert "peak_acceleration_g" in result.metrics


def test_thermal_expansion_clearance(box):
    result = thermal_expansion(
        "test",
        box,
        get_material("Aluminum 6061"),
        {"delta_t_c": 100.0, "clearance_mm": 1.0},
    )
    assert result.load_case == LoadCase.THERMAL_EXPANSION
    assert result.metrics["thermal_expansion_mm"] > 0


def test_fatigue_cycles_has_endurance_limit(long_bar):
    result = fatigue_cycles(
        "test",
        long_bar,
        get_material("Aluminum 6061"),
        {"stress_amplitude_mpa": 10.0, "cycles_target": 1e6},
    )
    assert result.load_case == LoadCase.FATIGUE_CYCLES
    assert result.metrics["endurance_limit_mpa"] > 0
    assert result.metrics["cycles_to_failure"] > 0


def test_fastener_pull_out_passes_for_small_load(box):
    result = fastener_pull_out(
        "test",
        box,
        get_material("Aluminum 6061"),
        {"diameter_mm": 3.0, "engagement_length_mm": 6.0, "load_n": 10.0, "safety_factor_target": 2.0},
    )
    assert result.load_case == LoadCase.FASTENER_PULL_OUT
    assert result.passed is True
    assert result.metrics["tensile_capacity_n"] > 0
    assert result.metrics["shear_capacity_n"] > 0
    assert result.metrics["pull_out_capacity_n"] > 0


def test_fastener_pull_out_fails_for_huge_load(box):
    result = fastener_pull_out(
        "test",
        box,
        get_material("PLA"),
        {"diameter_mm": 3.0, "engagement_length_mm": 2.0, "load_n": 10000.0, "safety_factor_target": 2.0},
    )
    assert result.passed is False
    assert "fastener_capacity_exceeded" in result.failure_modes


def test_wind_tunnel_drag_reports_force(box):
    result = wind_tunnel_drag(
        "test",
        box,
        get_material("PLA"),
        {"velocity_m_s": 10.0, "drag_coefficient": 1.0},
    )
    assert result.load_case == LoadCase.WIND_TUNNEL_DRAG
    assert result.metrics["drag_force_n"] >= 0
    assert result.metrics["frontal_area_m2"] > 0


def test_heat_sink_thermal_resistance(box):
    result = heat_sink_thermal_resistance(
        "test",
        box,
        get_material("Aluminum 6061"),
        {"heat_flux_w": 10.0, "convection_coefficient_w_per_m2_k": 50.0, "target_theta_c_per_w": 5.0},
    )
    assert result.load_case == LoadCase.HEAT_SINK_THERMAL_RESISTANCE
    assert result.metrics["thermal_resistance_c_per_w"] > 0
    assert result.metrics["max_temperature_c"] >= 25.0


def test_joint_torque_check_passes():
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    result = joint_torque_check(
        "test",
        mesh,
        get_material("PLA"),
        {"load_mass_kg": 0.1, "arm_length_m": 0.1, "stall_torque_nm": 2.0, "safety_factor_target": 1.5},
    )
    assert result.load_case == LoadCase.JOINT_TORQUE_CHECK
    assert result.passed is True
    assert result.metrics["required_torque_nm"] > 0


def test_joint_torque_check_fails():
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    result = joint_torque_check(
        "test",
        mesh,
        get_material("PLA"),
        {"load_mass_kg": 50.0, "arm_length_m": 1.0, "stall_torque_nm": 2.0, "safety_factor_target": 1.5},
    )
    assert result.passed is False
    assert "joint_torque_insufficient" in result.failure_modes
    assert result.redesign_suggestions
