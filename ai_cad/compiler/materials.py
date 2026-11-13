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


# Materials that arrive as filament and leave a slicer, so a solid-volume mass is an upper bound.
# Metals and carbon fibre are bought as stock and are solid; applying a print model to them would
# understate a bracket by a factor of several.
PRINTED_MATERIALS: frozenset[str] = frozenset({"pla", "petg", "abs", "nylon", "resin"})


def is_printed_material(material: str | None) -> bool:
    """True when this material is printed rather than bought as solid stock."""
    key = (material or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key in PRINTED_MATERIALS


class Density(BaseModel):
    """A density with its provenance, so a report can say which links rest on a guess."""

    model_config = ConfigDict(frozen=True)

    value_kg_m3: float = Field(gt=MIN_PLAUSIBLE_DENSITY, lt=MAX_PLAUSIBLE_DENSITY)
    source: str = Field(description="measured | material | datasheet | assumed")
    material: str | None = None
    range_kg_m3: tuple[float, float] | None = Field(default=None)
    note: str | None = None
    # A part that arrives from a supplier is a sealed unit: its mass comes off a datasheet, and there
    # is no infill to model because nobody printed it. The B-rep still gives its envelope volume, so
    # the density below is the datasheet mass divided by that volume -- which is the number that makes
    # the kernel's mass, centre of mass and inertia agree with the part on the bench.
    bought_in: bool = False

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


def datasheet_density(
    mass_kg: float,
    volume_m3: float,
    note: str,
    material: str | None = None,
) -> Density:
    """Density that makes a bought-in part weigh its datasheet mass.

    A servo is not a homogenous block of anything, so no material name could give it a density. What
    is known instead is what it weighs and how much space its CAD envelope takes, and their ratio is
    the density that reproduces both. ``note`` must say where the mass came from: a datasheet figure
    without a citation is indistinguishable from a guess, which is the failure this module exists to
    prevent.
    """
    if volume_m3 <= 0.0:
        raise ValueError("cannot derive a bought-in density from a non-positive volume")
    if not note or not note.strip():
        raise ValueError("a datasheet mass needs a citation; pass a note naming the document")
    value = mass_kg / volume_m3
    if not (MIN_PLAUSIBLE_DENSITY < value < MAX_PLAUSIBLE_DENSITY):
        raise ValueError(
            f"datasheet mass {mass_kg!r} kg over CAD volume {volume_m3!r} m3 gives {value:.1f} kg/m3, "
            "which is outside any solid part; check the units or the part's volume"
        )
    return Density(
        value_kg_m3=value,
        source="datasheet",
        material=material,
        bought_in=True,
        note=note.strip(),
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
    "datasheet_density",
    "density_for",
    "measured_density",
]
