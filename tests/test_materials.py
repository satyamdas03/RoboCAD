"""Tests for the RoboCAD material library."""
from __future__ import annotations

import pytest

from ai_cad.materials import Material, get_material, list_materials, register_material


def test_list_materials_contains_common_materials():
    names = list_materials()
    for expected in ["PLA", "PETG", "ABS", "Aluminum 6061", "Mild Steel", "Copper", "FR4"]:
        assert expected in names


def test_get_material_by_exact_name():
    mat = get_material("PLA")
    assert mat.name == "PLA"
    assert mat.density_kg_m3 == 1250.0
    assert mat.youngs_modulus_mpa == 3500.0
    assert mat.yield_strength_mpa == 65.0
    assert mat.conductivity_w_m_k == 0.13
    assert mat.specific_heat_j_kg_k == 1800.0
    assert mat.emissivity == 0.9
    assert mat.thermal_expansion_per_k == 41e-6


def test_get_material_case_insensitive():
    assert get_material("pla").name == "PLA"
    assert get_material("ALUMINUM 6061").name == "Aluminum 6061"


def test_get_material_unknown_raises():
    with pytest.raises(KeyError):
        get_material("unobtainium")


def test_shear_modulus():
    pla = get_material("PLA")
    expected = pla.youngs_modulus_mpa / (2.0 * (1.0 + pla.poisson_ratio))
    assert pla.shear_modulus_mpa == pytest.approx(expected)


def test_register_material():
    custom = Material(
        name="Custom Foam",
        density_kg_m3=50.0,
        youngs_modulus_mpa=10.0,
        poisson_ratio=0.3,
        yield_strength_mpa=1.0,
        conductivity_w_m_k=0.05,
        specific_heat_j_kg_k=1000.0,
        emissivity=0.9,
        thermal_expansion_per_k=100e-6,
    )
    register_material(custom)
    assert get_material("Custom Foam").density_kg_m3 == 50.0
