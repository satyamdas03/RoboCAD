"""Material library for RoboCAD multi-physics verification.

Provides thermal and mechanical properties for common robotics materials.
Properties are representative room-temperature values and are intentionally
approximate: real design work should substitute measured or supplier data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Material:
    """Engineering material with structural and thermal properties."""

    name: str
    density_kg_m3: float
    youngs_modulus_mpa: float
    poisson_ratio: float
    yield_strength_mpa: float
    conductivity_w_m_k: float
    specific_heat_j_kg_k: float
    emissivity: float
    thermal_expansion_per_k: float
    notes: str = ""

    @property
    def shear_modulus_mpa(self) -> float:
        """Approximate shear modulus G = E / (2 * (1 + nu))."""
        return self.youngs_modulus_mpa / (2.0 * (1.0 + self.poisson_ratio))


_MATERIALS: dict[str, Material] = {
    "PLA": Material(
        name="PLA",
        density_kg_m3=1250.0,
        youngs_modulus_mpa=3500.0,
        poisson_ratio=0.36,
        yield_strength_mpa=65.0,
        conductivity_w_m_k=0.13,
        specific_heat_j_kg_k=1800.0,
        emissivity=0.9,
        thermal_expansion_per_k=41e-6,
        notes="Common 3D-printed thermoplastic.",
    ),
    "PETG": Material(
        name="PETG",
        density_kg_m3=1270.0,
        youngs_modulus_mpa=2100.0,
        poisson_ratio=0.38,
        yield_strength_mpa=80.0,
        conductivity_w_m_k=0.19,
        specific_heat_j_kg_k=1700.0,
        emissivity=0.9,
        thermal_expansion_per_k=70e-6,
        notes="Tougher 3D-printed thermoplastic.",
    ),
    "ABS": Material(
        name="ABS",
        density_kg_m3=1050.0,
        youngs_modulus_mpa=2200.0,
        poisson_ratio=0.35,
        yield_strength_mpa=40.0,
        conductivity_w_m_k=0.16,
        specific_heat_j_kg_k=1500.0,
        emissivity=0.9,
        thermal_expansion_per_k=90e-6,
        notes="3D-printed thermoplastic, lower strength than PLA.",
    ),
    "Nylon 12": Material(
        name="Nylon 12",
        density_kg_m3=1020.0,
        youngs_modulus_mpa=1700.0,
        poisson_ratio=0.39,
        yield_strength_mpa=85.0,
        conductivity_w_m_k=0.25,
        specific_heat_j_kg_k=1700.0,
        emissivity=0.9,
        thermal_expansion_per_k=90e-6,
        notes="SLS/ MJF structural polymer.",
    ),
    "Aluminum 6061": Material(
        name="Aluminum 6061",
        density_kg_m3=2700.0,
        youngs_modulus_mpa=70000.0,
        poisson_ratio=0.33,
        yield_strength_mpa=270.0,
        conductivity_w_m_k=167.0,
        specific_heat_j_kg_k=896.0,
        emissivity=0.35,
        thermal_expansion_per_k=23.6e-6,
        notes="General-purpose structural aluminum alloy.",
    ),
    "Mild Steel": Material(
        name="Mild Steel",
        density_kg_m3=7850.0,
        youngs_modulus_mpa=210000.0,
        poisson_ratio=0.30,
        yield_strength_mpa=250.0,
        conductivity_w_m_k=50.0,
        specific_heat_j_kg_k=486.0,
        emissivity=0.5,
        thermal_expansion_per_k=12.0e-6,
        notes="Low-carbon steel, common for robot frames.",
    ),
    "Copper": Material(
        name="Copper",
        density_kg_m3=8960.0,
        youngs_modulus_mpa=117000.0,
        poisson_ratio=0.34,
        yield_strength_mpa=70.0,
        conductivity_w_m_k=401.0,
        specific_heat_j_kg_k=385.0,
        emissivity=0.07,
        thermal_expansion_per_k=16.5e-6,
        notes="Excellent conductor; used for heat spreaders and traces.",
    ),
    "Brass": Material(
        name="Brass",
        density_kg_m3=8500.0,
        youngs_modulus_mpa=100000.0,
        poisson_ratio=0.33,
        yield_strength_mpa=140.0,
        conductivity_w_m_k=109.0,
        specific_heat_j_kg_k=380.0,
        emissivity=0.35,
        thermal_expansion_per_k=19.0e-6,
        notes="Machinable copper alloy.",
    ),
    "Titanium 6Al-4V": Material(
        name="Titanium 6Al-4V",
        density_kg_m3=4430.0,
        youngs_modulus_mpa=113800.0,
        poisson_ratio=0.31,
        yield_strength_mpa=880.0,
        conductivity_w_m_k=6.7,
        specific_heat_j_kg_k=560.0,
        emissivity=0.45,
        thermal_expansion_per_k=8.6e-6,
        notes="High-strength, low-density aerospace/robot alloy.",
    ),
    "FR4": Material(
        name="FR4",
        density_kg_m3=1850.0,
        youngs_modulus_mpa=22000.0,
        poisson_ratio=0.14,
        yield_strength_mpa=345.0,
        conductivity_w_m_k=0.3,
        specific_heat_j_kg_k=1200.0,
        emissivity=0.9,
        thermal_expansion_per_k=14.0e-6,
        notes="Printed-circuit-board substrate.",
    ),
    "CopperTrace": Material(
        name="CopperTrace",
        density_kg_m3=8960.0,
        youngs_modulus_mpa=117000.0,
        poisson_ratio=0.34,
        yield_strength_mpa=70.0,
        conductivity_w_m_k=401.0,
        specific_heat_j_kg_k=385.0,
        emissivity=0.07,
        thermal_expansion_per_k=16.5e-6,
        notes="Alias for copper; used for PCB traces/heat spreaders.",
    ),
}


def list_materials() -> list[str]:
    """Return all registered material names."""
    return sorted(_MATERIALS.keys())


def get_material(name: str) -> Material:
    """Look up a material by name with case-insensitive fallback.

    Raises:
        KeyError: if the material is not registered.
    """
    if name in _MATERIALS:
        return _MATERIALS[name]
    lower = name.lower()
    for key, mat in _MATERIALS.items():
        if key.lower() == lower or mat.name.lower() == lower:
            return mat
    raise KeyError(f"Material '{name}' not found. Registered: {list_materials()}")


def register_material(material: Material) -> None:
    """Register a custom material at runtime."""
    _MATERIALS[material.name] = material
