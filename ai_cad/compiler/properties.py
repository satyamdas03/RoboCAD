"""Exact mass, centre of mass and inertia of a link, from the B-rep, in SI units.

Three facts this module is built around:

1. The kernel gives inertia about the **centre of mass**, not about the shape's origin. That was
   checked against an analytic cube rather than assumed: translating the cube 100 mm leaves every
   diagonal entry unchanged.
2. Instances are combined with the parallel-axis theorem in the link frame. Meshes are never summed
   to estimate mass; a tessellation is a picture of a solid, not the solid.
3. Units. OCC works in the CAD file's units, which for the robots here is millimetres, so volume is
   mm^3 (-> 1e-9 m^3) and the inertia matrix is mm^5 (-> 1e-15 m^5) times density.

A link whose mass properties fail validation is a hard error. A model that loads and simulates with
an impossible inertia is worse than one that refuses to build, because it produces plausible-looking
motion that is wrong.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ai_cad.compiler.materials import Density, density_for, is_printed_material
from ai_cad.compiler.print_model import PrintModel
from ai_cad.importers.models import ImportedAssembly, is_proper_rotation

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]

MM3_TO_M3 = 1.0e-9
MM5_TO_M5 = 1.0e-15


class PropertyError(RuntimeError):
    """Raised when a mass property is missing, non-physical or self-contradictory."""


class MassProperties(BaseModel):
    """Mass, centre of mass and inertia tensor about that centre, in SI units."""

    mass_kg: float = Field(gt=0.0, allow_inf_nan=False)
    com_m: Vec3
    inertia_kg_m2: Mat3
    label: str = ""
    # The source solid was wound inside-out. Volume and every tensor entry come back negated, the
    # centre of mass does not (it is a ratio, so both signs cancel). The magnitudes are the true
    # properties; the flag travels with the number so the report can say so and the collision stage
    # knows the tessellation's normals point inward.
    orientation_flipped: bool = False

    def principal_moments(self) -> tuple[float, float, float]:
        """Eigenvalues of the inertia tensor, ascending. Numpy rather than a closed form: a
        rotation-invariant answer is worth the import, and numpy is already a dependency."""
        import numpy as np

        values = np.linalg.eigvalsh(np.array(self.inertia_kg_m2, dtype=float))
        return (float(values[0]), float(values[1]), float(values[2]))

    def is_finite(self) -> bool:
        numbers = (self.mass_kg, *self.com_m, *(v for row in self.inertia_kg_m2 for v in row))
        return all(math.isfinite(v) for v in numbers)


class PartContribution(BaseModel):
    """One placed part's contribution to its link, after the placement is applied."""

    part_id: str
    instance_ids: list[str] = Field(default_factory=list)
    mass_kg: float
    # As measured by the kernel: the closed solid. This is the upper bound and is always reported,
    # whatever the part is modelled as actually being.
    volume_m3: float
    # The volume the reported mass was computed from. Equal to ``volume_m3`` when no print model was
    # supplied, or when the part is bought in rather than printed.
    effective_volume_m3: float | None = None
    surface_area_m2: float | None = None
    print_modelled: bool = False
    density: Density
    com_m: Vec3
    inertia_kg_m2: Mat3
    orientation_flipped: bool = False


class LinkMassProperties(MassProperties):
    link_id: str = ""
    parts: list[PartContribution] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_measured(self) -> bool:
        """True only when every contribution came from a weighed part."""
        return bool(self.parts) and all(p.density.source == "measured" for p in self.parts)

    @property
    def rests_on_an_assumed_density(self) -> bool:
        return any(p.density.is_assumed for p in self.parts)

    @property
    def solid_mass_kg(self) -> float:
        """The mass at 100% fill, i.e. what every part would weigh cast solid.

        This is the upper bound and it is recoverable from the parts whatever the reported mass was,
        because a part's kernel volume is never overwritten. It equals ``mass_kg`` exactly when no
        print model was applied.
        """
        return sum(p.volume_m3 * p.density.value_kg_m3 for p in self.parts)

    @property
    def print_modelled_parts(self) -> int:
        return sum(1 for p in self.parts if p.print_modelled)

    @property
    def bought_in_parts(self) -> int:
        """Parts whose mass came from a datasheet rather than from a density and a volume."""
        return sum(1 for p in self.parts if p.density.bought_in)


# ------------------------------------------------------------------------------------------------
# one shape
# ------------------------------------------------------------------------------------------------
def unit_density_properties(shape) -> MassProperties:
    """Volume, CoM and inertia of a solid with density 1 kg/m^3, converted to SI."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    try:
        BRepGProp.VolumeProperties_s(shape, props)
    except Exception as exc:  # pragma: no cover - kernel failure on a broken solid
        raise PropertyError(f"the kernel could not measure this shape: {exc}") from exc
    volume_mm3 = props.Mass()
    com = props.CentreOfMass()
    matrix = props.MatrixOfInertia()
    flipped = volume_mm3 < 0.0
    if flipped:
        # A solid wound inside-out integrates to a negated volume and a uniformly negated tensor.
        # The importer already takes the magnitude of a volume for the same reason, and refusing it
        # here would refuse 53 real parts of this robot over a winding convention. Zero volume is
        # still fatal: that is a face or an open shell, not a body.
        volume_mm3 = -volume_mm3
        sign = -1.0
    else:
        sign = 1.0
    if not math.isfinite(volume_mm3) or volume_mm3 <= 0.0:
        # A shell or a set of faces reports area here, not volume, and silently treating that as a
        # mass would give a part made of nothing.
        raise PropertyError(
            f"shape has no positive volume ({props.Mass()!r}); it is not a closed solid"
        )
    inertia = tuple(
        tuple(matrix.Value(row, col) * MM5_TO_M5 * sign for col in (1, 2, 3)) for row in (1, 2, 3)
    )
    return MassProperties(
        mass_kg=volume_mm3 * MM3_TO_M3,
        com_m=(com.X() * 1e-3, com.Y() * 1e-3, com.Z() * 1e-3),
        inertia_kg_m2=inertia,
        orientation_flipped=flipped,
    )


def surface_area_m2(shape) -> float:
    """Outer surface area of a solid, converted to square metres.

    Needed by the print model, which builds a shell of a given thickness over the surface. A part
    with no area is a degenerate solid and is refused rather than silently treated as zero.
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    try:
        BRepGProp.SurfaceProperties_s(shape, props)
    except Exception as exc:  # pragma: no cover - kernel failure on a broken solid
        raise PropertyError(f"the kernel could not measure this shape's surface: {exc}") from exc
    area_mm2 = props.Mass()
    if not math.isfinite(area_mm2) or area_mm2 <= 0.0:
        raise PropertyError(f"shape has no positive surface area ({area_mm2!r})")
    # 1 mm^2 = 1e-6 m^2
    return area_mm2 * 1.0e-6


def with_density(props: MassProperties, density: Density) -> MassProperties:
    """Apply a density. Mass and inertia scale linearly; the centre of mass does not move."""
    scale = density.value_kg_m3
    return props.model_copy(
        update={
            "mass_kg": props.mass_kg * scale,
            "inertia_kg_m2": tuple(tuple(v * scale for v in row) for row in props.inertia_kg_m2),
        }
    )


# ------------------------------------------------------------------------------------------------
# placement and combination
# ------------------------------------------------------------------------------------------------
def transform_properties(props: MassProperties, transform: tuple[float, ...]) -> MassProperties:
    """Apply a placement. Inertia rotates as a rank-2 tensor; mass does not change."""
    rot, trans = _rotation_translation(transform)
    if not is_proper_rotation(transform):
        raise PropertyError(
            "placement is not a proper rotation; a reflection would need the mirrored solid, and "
            "an inertia computed from the wrong-handed shape is silently wrong"
        )
    com = _mat_vec(rot, props.com_m)
    com = (com[0] + trans[0], com[1] + trans[1], com[2] + trans[2])
    inertia = _mat_mat(_mat_mat(rot, props.inertia_kg_m2), _transpose(rot))
    return props.model_copy(
        update={"com_m": com, "inertia_kg_m2": _symmetrize(inertia)}
    )


def combine(parts: list[MassProperties], label: str = "") -> MassProperties:
    """One rigid body from several, by the parallel-axis theorem."""
    if not parts:
        raise PropertyError("cannot combine zero parts into a link")
    total = sum(p.mass_kg for p in parts)
    if total <= 0.0:
        raise PropertyError("link has no mass")
    com = tuple(sum(p.mass_kg * p.com_m[a] for p in parts) / total for a in range(3))
    inertia = [[0.0] * 3 for _ in range(3)]
    for p in parts:
        d = tuple(p.com_m[a] - com[a] for a in range(3))
        square = sum(v * v for v in d)
        for i in range(3):
            for j in range(3):
                shift = p.mass_kg * ((square if i == j else 0.0) - d[i] * d[j])
                inertia[i][j] += p.inertia_kg_m2[i][j] + shift
    return MassProperties(
        mass_kg=total,
        com_m=com,
        inertia_kg_m2=_symmetrize(tuple(tuple(row) for row in inertia)),
        label=label,
        orientation_flipped=any(p.orientation_flipped for p in parts),
    )


def link_properties(
    assembly: ImportedAssembly,
    link_id: str,
    instance_ids: list[str],
    density_by_part: dict[str, Density] | None = None,
    *,
    assumed_density: bool = True,
    cache: dict[str, MassProperties] | None = None,
    area_cache: dict[str, float] | None = None,
    bbox: tuple[Vec3, Vec3] | None = None,
    print_model: PrintModel | None = None,
) -> LinkMassProperties:
    """Mass properties for one link, from its parts, with provenance per part.

    ``density_by_part`` is the override file's job (``robot.materials.yaml`` in M3's full form). With
    nothing supplied, every part falls back to the labelled default, and the link records that its
    mass rests on an assumption.

    ``cache`` is shared across links: the kernel measures each *unique* part once, however many times
    it is placed. Without it a 259-instance assembly re-measures the same 83 B-reps 259 times.
    """
    if not instance_ids:
        raise PropertyError(f"link {link_id} has no instances")
    instances = {inst.instance_id: inst for inst in assembly.instances}
    unit_cache = cache if cache is not None else {}
    contributions: list[PartContribution] = []
    warnings: list[str] = []
    for instance_id in instance_ids:
        inst = instances.get(instance_id)
        if inst is None:
            raise PropertyError(f"link {link_id} names unknown instance {instance_id}")
        part = assembly.parts.get(inst.part_id)
        if part is None:
            raise PropertyError(f"instance {instance_id} names unknown part {inst.part_id}")
        if not part.is_solid:
            raise PropertyError(
                f"part {part.part_id} is not a closed solid; mass properties would be meaningless"
            )
        shape = getattr(part, "shape", None)
        if shape is None:
            raise PropertyError(
                f"part {part.part_id} has no shape; mass properties need the B-rep, not a mesh"
            )
        if part.part_id not in unit_cache:
            unit_cache[part.part_id] = unit_density_properties(shape)
        density = (density_by_part or {}).get(part.part_id) or density_for(None, assumed=assumed_density)
        unit = unit_cache[part.part_id]
        solid_volume_m3 = unit.mass_kg
        area = None
        effective_volume_m3 = solid_volume_m3
        modelled = False
        if (
            print_model is not None
            and is_printed_material(density.material)
            and not density.bought_in
        ):
            # Surface area is a kernel call per unique part, so it is cached like the volume. Both
            # caches are keyed by part_id because the same B-rep is placed many times.
            if area_cache is not None:
                if part.part_id not in area_cache:
                    area_cache[part.part_id] = surface_area_m2(shape)
                area = area_cache[part.part_id]
            else:
                area = surface_area_m2(shape)
            effective_volume_m3 = print_model.effective_volume_m3(solid_volume_m3, area)
            modelled = True
        local = with_density(unit, density)
        if modelled:
            # Scaling both mass and inertia by the same factor is the cheap approximation: it keeps
            # the tensor physically valid while accepting that a hollow part's inertia is not its
            # solid inertia times a scalar. The warning below says so in words the report carries.
            factor = 0.0 if solid_volume_m3 <= 0.0 else effective_volume_m3 / solid_volume_m3
            local = local.model_copy(
                update={
                    "mass_kg": local.mass_kg * factor,
                    "inertia_kg_m2": tuple(
                        tuple(v * factor for v in row) for row in local.inertia_kg_m2
                    ),
                }
            )
        placed = transform_properties(local, inst.transform)
        contributions.append(
            PartContribution(
                part_id=part.part_id,
                instance_ids=[instance_id],
                mass_kg=placed.mass_kg,
                volume_m3=solid_volume_m3,
                effective_volume_m3=effective_volume_m3 if modelled else None,
                surface_area_m2=area,
                print_modelled=modelled,
                density=density,
                com_m=placed.com_m,
                inertia_kg_m2=placed.inertia_kg_m2,
                orientation_flipped=placed.orientation_flipped,
            )
        )
    body = combine(
        [
            MassProperties(
                mass_kg=c.mass_kg, com_m=c.com_m, inertia_kg_m2=c.inertia_kg_m2, label=c.part_id
            )
            for c in contributions
        ],
        label=link_id,
    )
    if any(c.density.is_assumed for c in contributions):
        warnings.append(
            f"{sum(1 for c in contributions if c.density.is_assumed)} of {len(contributions)} "
            f"part(s) in {link_id} use an assumed density ({density_for(None).value_kg_m3:.0f} "
            "kg/m3); mass and inertia scale linearly with it"
        )
    modelled = [c for c in contributions if c.print_modelled]
    if modelled and print_model is not None:
        shell_only = sum(
            1
            for c in modelled
            if c.surface_area_m2 is not None
            and print_model.shell_volume_m3(c.volume_m3, c.surface_area_m2) >= c.volume_m3
        )
        warnings.append(
            f"{len(modelled)} of {len(contributions)} part(s) in {link_id} were massed as printed "
            f"parts at {print_model.describe()} rather than as solids; this is a model, not a "
            f"measurement, and {shell_only} of them are thinner than one wall so print solid"
        )
        warnings.append(
            f"the printed-part model in {link_id} holds each part's centre of mass at its solid "
            "centre and scales its inertia tensor by the same factor as its mass; a hollow part's "
            "true centre of mass moves toward its shell and its true inertia is not a scalar "
            "multiple of the solid's"
        )
    flipped = [c.part_id for c in contributions if c.orientation_flipped]
    if flipped:
        named = ", ".join(sorted(set(flipped))[:5])
        more = len(set(flipped)) - 5
        warnings.append(
            f"{len(set(flipped))} part(s) in {link_id} are valid solids wound inside-out in the "
            f"source CAD ({named}{' and more' if more > 0 else ''}); volume and inertia taken as "
            "magnitudes, and their meshes' face normals point inward"
        )
    result = LinkMassProperties(
        mass_kg=body.mass_kg,
        com_m=body.com_m,
        inertia_kg_m2=body.inertia_kg_m2,
        label=link_id,
        link_id=link_id,
        parts=contributions,
        warnings=warnings,
    )
    # A link built from real parts must still be a body a simulator can integrate. Failing here
    # reports the link, not a stack trace in MuJoCo three stages later.
    validate(result, bbox)
    return result


# ------------------------------------------------------------------------------------------------
# validation -- a hard error, not a warning
# ------------------------------------------------------------------------------------------------
def validate(props: MassProperties, bbox: tuple[Vec3, Vec3] | None = None,
             tolerance: float = 1e-9) -> None:
    """Reject a mass property that no rigid body could have.

    Symmetric, positive definite, principal moments satisfying the triangle inequality, and -- when
    the link's box is known -- a centre of mass inside it. The triangle inequality is the one that
    catches a bad combination of parts: two heavy parts far apart inflate I_major past the sum of the
    other two only if the parallel-axis terms were applied to the wrong point.
    """
    if not props.is_finite():
        raise PropertyError(f"{props.label or 'body'} has a non-finite mass property")
    inertia = props.inertia_kg_m2
    for i in range(3):
        for j in range(i + 1, 3):
            scale = max(abs(inertia[i][j]), abs(inertia[j][i]), 1e-15)
            if abs(inertia[i][j] - inertia[j][i]) > tolerance * 1e3 * scale:
                raise PropertyError(f"{props.label or 'body'} inertia tensor is not symmetric")
    if not _leading_minors_positive(inertia):
        raise PropertyError(f"{props.label or 'body'} inertia tensor is not positive definite")
    moments = props.principal_moments()
    if moments[0] < 0.0:
        raise PropertyError(f"{props.label or 'body'} has a negative principal moment")
    if moments[2] > moments[0] + moments[1] + 1e-12 * max(moments[2], 1e-15):
        raise PropertyError(
            f"{props.label or 'body'} violates the triangle inequality: principal moments "
            f"{moments[0]:.6g}, {moments[1]:.6g}, {moments[2]:.6g}"
        )
    if bbox is not None:
        lo, hi = bbox
        if any(not (lo[a] - 1e-9 <= props.com_m[a] <= hi[a] + 1e-9) for a in range(3)):
            raise PropertyError(
                f"{props.label or 'body'} centre of mass {props.com_m} lies outside its bounding "
                f"box {lo}..{hi}"
            )


# ------------------------------------------------------------------------------------------------
# small matrix helpers, kept here so the module has no hidden numeric dependency beyond validation
# ------------------------------------------------------------------------------------------------
def _rotation_translation(transform: tuple[float, ...]):
    m = transform
    rot = ((m[0], m[1], m[2]), (m[4], m[5], m[6]), (m[8], m[9], m[10]))
    return rot, (m[3], m[7], m[11])


def _mat_vec(m: Mat3, v: Vec3) -> Vec3:
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def _mat_mat(a: Mat3, b: Mat3) -> Mat3:
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )


def _transpose(m: Mat3) -> Mat3:
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def _symmetrize(m: Mat3) -> Mat3:
    return tuple(
        tuple((m[i][j] + m[j][i]) / 2.0 for j in range(3)) for i in range(3)
    )


def _leading_minors_positive(m: Mat3, tolerance: float = 0.0) -> bool:
    d1 = m[0][0]
    d2 = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    return d1 > tolerance and d2 > tolerance and det > tolerance


__all__ = [
    "LinkMassProperties",
    "MassProperties",
    "PartContribution",
    "PropertyError",
    "combine",
    "link_properties",
    "transform_properties",
    "unit_density_properties",
    "validate",
    "with_density",
]
