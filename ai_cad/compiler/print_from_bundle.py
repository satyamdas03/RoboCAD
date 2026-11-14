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

import math
import re
from typing import Any

from .print_model import PrintModel


class BundlePrintError(ValueError):
    """The bundle does not carry what a kernel-free recompute needs."""


# The print model string the compiler writes into every bundle: "1.20 mm wall over 20% infill".
_PRINT_MODEL = re.compile(r"([\d.]+)\s*mm wall over\s*([\d.]+)\s*%\s*infill")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def safe_text(value: Any, limit: int = 120) -> str:
    """Bundle-supplied text made safe for a terminal, a log or a chat line.

    A bundle arrives inside an archive from somewhere else, so a body id can carry escape sequences
    that move a cursor or recolour a terminal. The caller prints ids, and the caller's reader may be
    a speech tool: no control characters and a bounded length here means neither ever sees them.
    """
    return _CONTROL.sub("", str(value))[:limit]


def _finite(value: Any, what: str) -> float:
    """A number from the bundle, or a refusal.

    ``float("nan")`` parses fine and then poisons every sum it enters, and a string where a number
    belongs raises ``TypeError`` from deep inside the arithmetic. Both become the same declared
    error, so a caller's ``except BundlePrintError`` covers every malformed shape.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise BundlePrintError(f"{what} is not a number: {safe_text(value)!r}") from None
    if not math.isfinite(number):
        raise BundlePrintError(f"{what} is not finite: {safe_text(value)!r}")
    return number


def bundle_print_model(bundle: dict[str, Any]) -> PrintModel | None:
    """The print assumption the bundle was compiled at, read from its own print-model string."""
    text = bundle.get("print_model")
    match = _PRINT_MODEL.search(str(text or ""))
    if not match:
        return None
    wall = _finite(match.group(1), "print-model wall") / 1000.0
    infill = round(_finite(match.group(2), "print-model infill") / 100.0, 6)
    try:
        return PrintModel(wall_thickness_m=wall, infill_fraction=infill)
    except ValueError as error:  # pydantic ValidationError is a ValueError
        raise BundlePrintError(
            f"the bundle's print model is not a printable assumption: {safe_text(error)}"
        ) from None


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
            f"body {safe_text(body.get('body_id'))!r} records no printed_mass_kg and solid_mass_kg"
            " pair, so its shell cannot be separated from its interior without the CAD kernel"
        )
    printed_kg = _finite(printed, "printed_mass_kg")
    solid_kg = _finite(solid, "solid_mass_kg")
    if solid_kg < 0.0 or printed_kg < 0.0:
        raise BundlePrintError(
            f"body {safe_text(body.get('body_id'))!r} records a negative mass, which is not a body"
        )
    shell = (printed_kg - model.infill_fraction * solid_kg) / (1.0 - model.infill_fraction)
    shell = max(0.0, min(shell, solid_kg))
    return shell, solid_kg - shell


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
    if not all(isinstance(body, dict) for body in bodies):
        raise BundlePrintError("bundle carries a body that is not an object")

    # The caller's numbers, before anything is built on them: a string or a NaN here would reach the
    # model and the refusal would come from pydantic or from the middle of a sum.
    fraction = _finite(
        0.20 if infill is None and own is None else (own.infill_fraction if infill is None else infill),
        "infill",
    )
    wall = _finite(
        1.2 if wall_mm is None and own is None
        else (own.wall_thickness_m * 1000.0 if wall_mm is None else wall_mm),
        "wall_mm",
    ) / 1000.0
    try:
        target = PrintModel(wall_thickness_m=wall, infill_fraction=fraction)
    except ValueError as error:  # pydantic ValidationError is a ValueError
        raise BundlePrintError(f"not a printable assumption: {safe_text(error)}") from None
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
                f"{safe_text(body.get('body_id') or body.get('name') or '?')}: the shell reaches the"
                f" whole solid at {wall * 1000:.2f} mm wall, so this body is reported solid rather "
                "than shelled"
            )
        mass = scaled_shell + fraction * (solid - scaled_shell)
        by_body[safe_text(body.get("body_id") or body.get("name") or "?")] = mass
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
    if not isinstance(part, dict):
        raise BundlePrintError(f"a part row is {type(part).__name__}, not an object")
    for key in ("part_id", "instances", "volume_m3", "density_kg_m3"):
        if key not in part:
            raise BundlePrintError(f"part row carries no {key!r}: {sorted(part)}")
    return part


def _instances(value: Any) -> int:
    """A count of placed parts, or a refusal. Half an instance is not a quantity."""
    number = _finite(value, "instances")
    if number < 0 or number != int(number):
        raise BundlePrintError(f"instances {safe_text(value)!r} is not a whole count")
    return int(number)


def part_mass_kg(part: dict, model: PrintModel) -> float:
    """One part's mass at one print assumption. No kernel, no file, just its recorded numbers."""
    row = _part_row(part)
    instances = _instances(row["instances"])
    volume = _finite(row["volume_m3"], "volume_m3")
    density = _finite(row["density_kg_m3"], "density_kg_m3")
    printed = bool(row.get("printed", False)) and not bool(row.get("bought_in", False))
    if not printed:
        # Bought in, or a material that is not printed: the solid is the part.
        return instances * volume * density
    area = row.get("surface_area_m2")
    if area is None:
        raise BundlePrintError(
            f"part {safe_text(row['part_id'])!r} is printed but carries no surface_area_m2, so its"
            " wall cannot be modelled: recompile the bundle to record it"
        )
    return instances * density * model.effective_volume_m3(
        volume, _finite(area, "surface_area_m2")
    )


def printed_mass_from_bundle(bundle: dict[str, Any], model: PrintModel) -> dict[str, Any]:
    """Total and per-body printed mass from the bundle's own per-part rows.

    Returns ``{"total_kg", "by_body", "solid_kg", "parts_modelled", "parts_bought_in"}``. A body with
    no per-part rows is reported as ``None`` in ``by_body`` rather than as a zero: a zero would read
    as a weightless link.
    """
    bodies = bundle.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        raise BundlePrintError("bundle carries no bodies")
    if not all(isinstance(body, dict) for body in bodies):
        raise BundlePrintError("bundle carries a body that is not an object")
    total = 0.0
    solid = 0.0
    by_body: dict[str, float | None] = {}
    modelled = 0
    bought_in = 0
    for body in bodies:
        # The key is printed by the caller and may be spoken aloud: control characters and unbounded
        # length come out here, once, rather than at each of a caller's print sites.
        body_id = safe_text(body.get("body_id") or body.get("name") or "?")
        rows = body.get("part_properties")
        if not records_per_part(rows):
            by_body[body_id] = None
            continue
        body_total = 0.0
        for row in rows:
            body_total += part_mass_kg(row, model)
            # The same validated triple `part_mass_kg` just read: one definition of a malformed row.
            _part_row(row)
            solid += (
                _instances(row["instances"])
                * _finite(row["volume_m3"], "volume_m3")
                * _finite(row["density_kg_m3"], "density_kg_m3")
            )
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
    fraction = _finite(infill, "infill")
    wall = None if wall_m is None else _finite(wall_m, "wall_m")
    try:
        model = PrintModel(infill_fraction=fraction) if wall is None else PrintModel(
            wall_thickness_m=wall, infill_fraction=fraction
        )
    except ValueError as error:  # pydantic ValidationError is a ValueError
        raise BundlePrintError(f"not a printable assumption: {safe_text(error)}") from None
    return printed_mass_from_bundle(bundle, model)
