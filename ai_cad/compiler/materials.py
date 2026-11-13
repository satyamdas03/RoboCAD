"""Densities, and the difference between a measured one and a guessed one.

Mass properties are only as good as the density that multiplies them, and on a real robot the CAD
does not say what the part is made of. The rule this module enforces: a number is either given,
selected by name, or assumed -- and an assumed density is reported as an assumption with a value
and a range, never as a fact. A link whose mass came out of a guess is not the same object as a link
whose mass was measured, and the report has to be able to tell them apart.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Nominal densities in kg/m^3, at room temperature, for the materials a desktop robot is actually
# made from. These are textbook values, not measurements of any particular spool: a printed part's
# real density depends on infill, and a 100% infill assumption on a 40% infill part is a 2.5x error.
MATERIALS: dict[str, float] = {
    "pla": 1240.0,
    "petg": 1270.0,
    "abs": 1040.0,
    "nylon": 1140.0,
    "resin": 1180.0,
    "aluminium": 2700.0,
    "6061": 2700.0,
    "steel": 7850.0,
    "brass": 8500.0,
    "carbon_fibre": 1600.0,
}

# SO-101 is a printed arm, so a printed plastic is the least-wrong default. It is still a default:
# every part that falls back to it is flagged ``assumed`` and carries this range.
DEFAULT_MATERIAL = "pla"
DEFAULT_DENSITY_KG_M3 = MATERIALS[DEFAULT_MATERIAL]
# Printed plastics span roughly 950 to 1400 kg/m^3 with infill, so the interval has to be that wide.
DEFAULT_DENSITY_RANGE_KG_M3 = (950.0, 1400.0)

# A density outside this band is a units error, not a material.
MIN_PLAUSIBLE_DENSITY = 100.0
MAX_PLAUSIBLE_DENSITY = 25_000.0  # osmium is 22,590


class Density(BaseModel):
    """A density with its provenance, so a report can say which links rest on a guess."""

    model_config = ConfigDict(frozen=True)

    value_kg_m3: float = Field(gt=MIN_PLAUSIBLE_DENSITY, lt=MAX_PLAUSIBLE_DENSITY)
    source: str = Field(description="measured | material | assumed")
    material: str | None = None
    range_kg_m3: tuple[float, float] | None = Field(default=None)
    note: str | None = None

    @property
    def is_assumed(self) -> bool:
        return self.source == "assumed"


def density_for(material: str | None, assumed: bool = False) -> Density:
    """Density for a named material, or the labelled default when nothing is known.

    ``assumed=True`` marks the result even when a material name was supplied, because a name in a
    CAD file is a hint about intent, not a statement about the parts on the bench.
    """
    key = (material or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in MATERIALS and not assumed:
        return Density(value_kg_m3=MATERIALS[key], source="material", material=key)
    if key in MATERIALS and assumed:
        return Density(
            value_kg_m3=MATERIALS[key], source="assumed", material=key,
            range_kg_m3=DEFAULT_DENSITY_RANGE_KG_M3,
            note=f"material {key!r} taken from the CAD text, not from a datasheet",
        )
    return Density(
        value_kg_m3=DEFAULT_DENSITY_KG_M3,
        source="assumed",
        material=DEFAULT_MATERIAL,
        range_kg_m3=DEFAULT_DENSITY_RANGE_KG_M3,
        note="no material given; printed plastic assumed, mass scales linearly with density",
    )


def measured_density(mass_kg: float, volume_m3: float, note: str | None = None) -> Density:
    """Density implied by a weighed part. This is the only source that is not a guess."""
    if volume_m3 <= 0.0:
        raise ValueError("cannot derive a density from a non-positive volume")
    value = mass_kg / volume_m3
    if not (MIN_PLAUSIBLE_DENSITY < value < MAX_PLAUSIBLE_DENSITY):
        raise ValueError(
            f"weighed mass {mass_kg!r} kg over volume {volume_m3!r} m3 gives {value:.1f} kg/m3, "
            "which is outside any solid material; check the units"
        )
    return Density(value_kg_m3=value, source="measured", note=note)


__all__ = [
    "DEFAULT_DENSITY_KG_M3",
    "DEFAULT_DENSITY_RANGE_KG_M3",
    "DEFAULT_MATERIAL",
    "MATERIALS",
    "Density",
    "density_for",
    "measured_density",
]
