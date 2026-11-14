"""What a bundle can say about a different print assumption, with no CAD kernel in the room.

The print model is linear in infill fraction and piecewise-linear in wall thickness, and a compiled
bundle that records, per part, the kernel's solid volume, the kernel's surface area and the density
used, can answer "what does this weigh at 30 percent infill and a 1.6 mm wall" by arithmetic. The
alternative is re-importing a STEP file and integrating every B-rep again, which needs the kernel,
the file, and about as long as the first compile took.

This module is the arithmetic. It reads only what is inside the bundle, so a recipient who has the
zip and nothing else can open a playground and move a slider.

Two things it refuses to blur:

* A bought-in part does not change with infill. Its mass is a datasheet figure; the bundle carries
  the density that reproduces it, and this module multiplies instances by volume by that density and
  never applies the print model to it. A servo that thins as the slider moves would be a lie.
* A part whose recorded surface area is absent cannot be wall-modelled. The bundle of record predates
  per-part rows, so this module reports ``None`` for that body rather than guessing an area from the
  collision hulls: a hull's surface area is not the B-rep's, and the error would enter the mass
  through the wall term, which at 1.2 mm is the largest term in it.

The model itself is ``PrintModel`` -- the same object the compiler used -- so a playground and a
recompile cannot drift into two different definitions of "20 percent infill".
"""
from __future__ import annotations

import re
from typing import Any

from .print_model import PrintModel


class BundlePrintError(ValueError):
    """The bundle does not carry what a kernel-free recompute needs."""


# The print model string the compiler writes into every bundle: "1.20 mm wall over 20% infill".
_PRINT_MODEL = re.compile(r"([\d.]+)\s*mm wall over\s*([\d.]+)\s*%\s*infill")


def bundle_print_model(bundle: dict[str, Any]) -> PrintModel | None:
    """The print assumption the bundle was compiled at, read from its own print-model string."""
    match = _PRINT_MODEL.search(str(bundle.get("print_model") or ""))
    if not match:
        return None
    return PrintModel(
        wall_thickness_m=float(match.group(1)) / 1000.0,
        infill_fraction=round(float(match.group(2)) / 100.0, 6),
    )


def body_print_terms(body: dict, model: PrintModel) -> tuple[float, float]:
    """The shell mass and the infilled-interior mass of one body, from its own two masses.

    ``printed_mass_kg`` is what the body weighs at the bundle's print model, and ``solid_mass_kg``
    is what it would weigh cast solid. The print model is ``printed = shell + f * interior`` and
    ``solid = shell + interior``, so the shell is ``(printed - f * solid) / (1 - f)``: one equation,
    one unknown, no surface area needed. Bought-in parts sit at their datasheet mass in both figures
    and cancel out of the subtraction, which is why this holds for a body carrying servos.

    It is exact for a body that is entirely printed at this wall. Where a part's wall saturates
    (``A * w >= V``) the body's shell figure is capped at its solid mass, which is the same clamp
    ``PrintModel`` applies per part; the cap is reported by the caller rather than hidden.
    """
    if not (0.0 <= model.infill_fraction < 1.0):
        raise BundlePrintError("infill must be below 1.0 to separate a shell from its interior")
    printed = body.get("printed_mass_kg")
    solid = body.get("solid_mass_kg")
    if printed is None or solid is None:
        raise BundlePrintError(
            f"body {body.get('body_id')!r} records no printed_mass_kg and solid_mass_kg pair, so its"
            " shell cannot be separated from its interior without the CAD kernel"
        )
    shell = (float(printed) - model.infill_fraction * float(solid)) / (1.0 - model.infill_fraction)
    shell = max(0.0, min(shell, float(solid)))
    return shell, float(solid) - shell


def printed_mass_at(
    bundle: dict[str, Any],
    infill: float | None = None,
    wall_mm: float | None = None,
) -> dict[str, Any]:
    """Every printed mass a bundle implies at another infill and wall, with no kernel and no STEP.

    ``infill`` is a fraction (0.30 for "30 percent"); ``wall_mm`` is millimetres, the unit the
    bundle's own print-model string uses. Either may be omitted to keep the bundle's own value.

    Two routes, in order of provenance:

    * ``part_rows`` -- the bundle records ``part_properties`` per part, so ``PrintModel`` is applied
      to the kernel's volume and surface area exactly as the compiler did.
    * ``body_linear`` -- the bundle records only per-body printed and solid masses, so the shell is
      recovered from those two (see :func:`body_print_terms`) and every other infill is the same
      line evaluated elsewhere. A wall change scales the shell mass by the wall ratio, because
      ``shell = rho * A * w`` is linear in ``w`` until a part goes solid; where that happens the
      body is clamped to its solid mass and the clamp is named in ``warnings``.

    Both routes are the compiler's own model, and the result says which one answered.
    """
    own = bundle_print_model(bundle)
    bodies = bundle.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        raise BundlePrintError("bundle carries no bodies")

    if own is not None:
        fraction = own.infill_fraction if infill is None else float(infill)
        wall = own.wall_thickness_m if wall_mm is None else float(wall_mm) / 1000.0
    else:
        fraction = 0.20 if infill is None else float(infill)
        wall = 0.0012 if wall_mm is None else float(wall_mm) / 1000.0
    target = PrintModel(wall_thickness_m=wall, infill_fraction=fraction)
    if not (0.0 <= fraction < 1.0):
        raise BundlePrintError(f"infill {fraction:g} is outside the printable range 0-1")

    warnings: list[str] = []

    per_part = records_per_part((bodies[0] or {}).get("part_properties"))
    if per_part:
        got = printed_mass_from_bundle(bundle, target)
        return {
            "total_kg": got["total_kg"],
            "solid_kg": got["solid_kg"],
            "by_body": got["by_body"],
            "method": "part_rows",
            "print_model": target.describe(),
            "warnings": warnings,
        }

    wall_ratio = 1.0
    if own is not None and own.wall_thickness_m > 0:
        wall_ratio = wall / own.wall_thickness_m
    total = 0.0
    solid_total = 0.0
    by_body: dict[str, float] = {}
    for body in bodies:
        if own is None:
            raise BundlePrintError(
                "the bundle states no print model and no per-part rows: nothing here says what its"
                " printed mass was measured against"
            )
        shell, interior = body_print_terms(body, own)
        solid = shell + interior
        scaled_shell = min(solid, shell * wall_ratio)
        if shell * wall_ratio > solid + 1e-12:
            warnings.append(
                f"{body.get('body_id')}: the shell reaches the whole solid at {wall * 1000:.2f} mm "
                "wall, so this body is reported solid rather than shelled"
            )
        mass = scaled_shell + fraction * (solid - scaled_shell)
        by_body[str(body.get("body_id") or body.get("name") or "?")] = mass
        total += mass
        solid_total += solid
    return {
        "total_kg": total,
        "solid_kg": solid_total,
        "by_body": by_body,
        "method": "body_linear",
        "print_model": target.describe(),
        "warnings": warnings,
    }



def _part_row(part: dict) -> dict:
    for key in ("part_id", "instances", "volume_m3", "density_kg_m3"):
        if key not in part:
            raise BundlePrintError(f"part row carries no {key!r}: {sorted(part)}")
    return part


def part_mass_kg(part: dict, model: PrintModel) -> float:
    """One part's mass at one print assumption. No kernel, no file, just its recorded numbers."""
    row = _part_row(part)
    instances = int(row["instances"])
    volume = float(row["volume_m3"])
    density = float(row["density_kg_m3"])
    printed = bool(row.get("printed", False)) and not bool(row.get("bought_in", False))
    if not printed:
        # Bought in, or a material that is not printed: the solid is the part.
        return instances * volume * density
    area = row.get("surface_area_m2")
    if area is None:
        raise BundlePrintError(
            f"part {row['part_id']!r} is printed but carries no surface_area_m2, so its wall cannot "
            "be modelled: recompile the bundle to record it"
        )
    return instances * density * model.effective_volume_m3(volume, float(area))


def printed_mass_from_bundle(bundle: dict[str, Any], model: PrintModel) -> dict[str, Any]:
    """Total and per-body printed mass from the bundle's own per-part rows.

    Returns ``{"total_kg", "by_body", "solid_kg", "parts_modelled", "parts_bought_in"}``. A body with
    no per-part rows is reported as ``None`` in ``by_body`` rather than as a zero: a zero would read
    as a weightless link.
    """
    bodies = bundle.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        raise BundlePrintError("bundle carries no bodies")
    total = 0.0
    solid = 0.0
    by_body: dict[str, float | None] = {}
    modelled = 0
    bought_in = 0
    for body in bodies:
        body_id = str(body.get("body_id") or body.get("name") or "?")
        rows = body.get("part_properties")
        if not records_per_part(rows):
            by_body[body_id] = None
            continue
        body_total = 0.0
        for row in rows:
            body_total += part_mass_kg(row, model)
            solid += int(row["instances"]) * float(row["volume_m3"]) * float(row["density_kg_m3"])
            if bool(row.get("printed", False)) and not bool(row.get("bought_in", False)):
                modelled += 1
            else:
                bought_in += 1
        by_body[body_id] = body_total
        total += body_total
    return {
        "total_kg": total,
        "solid_kg": solid,
        "by_body": by_body,
        "parts_modelled": modelled,
        "parts_bought_in": bought_in,
        "print_model": model.describe(),
    }


def records_per_part(rows: Any) -> bool:
    """True when this is a per-part row list rather than absent or per-body only."""
    return isinstance(rows, list) and bool(rows) and isinstance(rows[0], dict)


def mass_at_infill(bundle: dict[str, Any], infill: float, wall_m: float | None = None) -> dict:
    """Convenience: the total at one infill fraction, optionally at another wall."""
    model = PrintModel(infill_fraction=infill) if wall_m is None else PrintModel(
        wall_thickness_m=wall_m, infill_fraction=infill
    )
    return printed_mass_from_bundle(bundle, model)
