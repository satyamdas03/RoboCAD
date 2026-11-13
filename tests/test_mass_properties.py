"""M3 acceptance: mass and inertia that match an analytic answer, or refuse to exist.

The two halves matter equally. An inertia tensor can be plausible-looking and wrong (a parallel-axis
term applied at the wrong point still yields positive numbers), so every property is checked against
a body whose answer is known in closed form, and against the invariants any rigid body must satisfy.
"""
from __future__ import annotations

import math

import pytest

from ai_cad.compiler.materials import (
    Density,
    density_for,
    measured_density,
)
from ai_cad.compiler.properties import (
    MassProperties,
    PropertyError,
    combine,
    link_properties,
    transform_properties,
    unit_density_properties,
    validate,
    with_density,
)
from ai_cad.importers.models import ImportedAssembly, ImportedInstance, ImportedPart, PartSignature

PLA = 1240.0


# ------------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------------
def cube(side_m: float):
    from build123d import Box

    return Box(side_m * 1e3, side_m * 1e3, side_m * 1e3).wrapped


def cylinder(radius_m: float, height_m: float):
    from build123d import Cylinder

    return Cylinder(radius_m * 1e3, height_m * 1e3).wrapped


def translated(transform: tuple[float, ...], dx: float = 0.0, dy: float = 0.0, dz: float = 0.0):
    m = list(transform)
    m[3] += dx
    m[7] += dy
    m[11] += dz
    return tuple(m)


IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def rot_z_90(dx: float = 0.0) -> tuple[float, ...]:
    m = [0.0] * 16
    m[0:3] = [0.0, -1.0, 0.0]
    m[4:7] = [1.0, 0.0, 0.0]
    m[8:11] = [0.0, 0.0, 1.0]
    m[3], m[7], m[11], m[15] = dx, 0.0, 0.0, 1.0
    return tuple(m)


def signature(volume_m3: float) -> PartSignature:
    return PartSignature(
        volume_m3=volume_m3,
        surface_area_m2=0.0,
        bbox_min_m=(0.0, 0.0, 0.0),
        bbox_max_m=(0.0, 0.0, 0.0),
        face_count=6,
    )


def assembly_of(parts: dict[str, object], placements: list[tuple[str, str, tuple[float, ...]]]):
    """A hand-built assembly, so the compiler is exercised without a CAD file."""
    imported = {}
    for part_id, shape in parts.items():
        imported[part_id] = ImportedPart(
            part_id=part_id, name=part_id, signature=signature(1e-6), shape=shape
        )
    instances = [
        ImportedInstance(
            instance_id=instance_id,
            name=instance_id,
            part_id=part_id,
            transform=transform,
            is_reflected=False,
        )
        for instance_id, part_id, transform in placements
    ]
    return ImportedAssembly(parts=imported, instances=instances)


# ------------------------------------------------------------------------------------------------
# analytic mass, within 0.1%
# ------------------------------------------------------------------------------------------------
class TestAnalyticMass:
    def test_a_cube_weighs_what_a_cube_weighs(self) -> None:
        # 20 mm cube at PLA: 8e-6 m3 * 1240 = 9.92e-3 kg
        props = with_density(unit_density_properties(cube(0.020)), density_for("pla"))
        expected = 0.020**3 * PLA
        assert props.mass_kg == pytest.approx(expected, rel=1e-3)
        assert props.com_m == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)

    def test_a_cylinder_weighs_what_a_cylinder_weighs(self) -> None:
        props = with_density(unit_density_properties(cylinder(0.005, 0.020)), density_for("pla"))
        expected = math.pi * 0.005**2 * 0.020 * PLA
        assert props.mass_kg == pytest.approx(expected, rel=1e-3)

    def test_a_cube_inertia_matches_the_closed_form(self) -> None:
        # I = m * a^2 / 6 about the centre, equal on all three axes.
        side = 0.020
        props = with_density(unit_density_properties(cube(side)), density_for("pla"))
        mass = props.mass_kg
        expected = mass * side**2 / 6.0
        for axis in range(3):
            assert props.inertia_kg_m2[axis][axis] == pytest.approx(expected, rel=1e-3)
        for i in range(3):
            for j in range(3):
                if i != j:
                    assert props.inertia_kg_m2[i][j] == pytest.approx(0.0, abs=expected * 1e-6)

    def test_a_cylinder_inertia_matches_the_closed_form(self) -> None:
        # About its own axis: m r^2 / 2. Transverse: m (3 r^2 + h^2) / 12.
        radius, height = 0.005, 0.020
        props = with_density(unit_density_properties(cylinder(radius, height)), density_for("pla"))
        mass = props.mass_kg
        axial = mass * radius**2 / 2.0
        transverse = mass * (3 * radius**2 + height**2) / 12.0
        # The cylinder's axis is z by construction, so one diagonal is axial, two are transverse.
        diagonals = sorted(props.inertia_kg_m2[i][i] for i in range(3))
        assert diagonals[0] == pytest.approx(axial, rel=2e-3)
        assert diagonals[1] == pytest.approx(transverse, rel=2e-3)
        assert diagonals[2] == pytest.approx(transverse, rel=2e-3)

    def test_mass_scales_linearly_with_density_and_geometry_does_not(self) -> None:
        unit = unit_density_properties(cube(0.010))
        light = with_density(unit, Density(value_kg_m3=1000.0, source="material", material="x"))
        heavy = with_density(unit, Density(value_kg_m3=8000.0, source="material", material="y"))
        assert heavy.mass_kg / light.mass_kg == pytest.approx(8.0, rel=1e-12)
        assert heavy.com_m == pytest.approx(light.com_m)


# ------------------------------------------------------------------------------------------------
# the kernel's reference point, verified rather than assumed
# ------------------------------------------------------------------------------------------------
class TestKernelConventions:
    def test_translating_a_part_moves_its_centre_and_not_its_inertia(self) -> None:
        """The kernel reports inertia about the centre of mass. If it reported it about the origin,
        moving the cube 100 mm would inflate every diagonal by m*d^2 = 1e-6 * 1e-2."""
        base = unit_density_properties(cube(0.010))
        moved = transform_properties(base, translated(IDENTITY, dx=0.100))
        assert moved.com_m[0] == pytest.approx(0.100, abs=1e-9)
        for i in range(3):
            assert moved.inertia_kg_m2[i][i] == pytest.approx(base.inertia_kg_m2[i][i], rel=1e-6)

    def test_a_rotated_instance_keeps_its_principal_moments(self) -> None:
        """Rotating a body cannot change what it is; only which axis each moment belongs to."""
        from build123d import Box

        shape = Box(10, 40, 25).wrapped  # deliberately not symmetric
        base = unit_density_properties(shape)
        turned = transform_properties(base, rot_z_90())
        assert turned.mass_kg == pytest.approx(base.mass_kg)
        assert turned.principal_moments() == pytest.approx(base.principal_moments(), rel=1e-9)
        # ...while the diagonal of the tensor in world axes is a different ordering.
        assert turned.inertia_kg_m2[0][0] == pytest.approx(base.inertia_kg_m2[1][1], rel=1e-9)
        assert turned.inertia_kg_m2[1][1] == pytest.approx(base.inertia_kg_m2[0][0], rel=1e-9)

    def test_a_reflection_is_refused_rather_than_folded_into_a_rotation(self) -> None:
        mirrored = list(IDENTITY)
        mirrored[0] = -1.0
        with pytest.raises(PropertyError, match="proper rotation"):
            transform_properties(unit_density_properties(cube(0.010)), tuple(mirrored))

    def test_a_non_solid_shape_is_refused(self) -> None:
        from build123d import Box

        face = Box(10, 10, 10).faces()[0].wrapped
        with pytest.raises(PropertyError):
            unit_density_properties(face)

    def test_an_inside_out_solid_is_measured_and_flagged(self) -> None:
        """A real SO-101 part (0603 resistor) is a valid solid whose faces are wound inward, so the
        kernel returns a negated volume and a uniformly negated tensor. Refusing it would refuse 53
        parts of the demo robot over a winding convention; silently flipping it would hide it."""
        from build123d import Box
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Solid

        solid = Box(10, 10, 10).solid().wrapped
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        explorer = TopExp_Explorer(solid, TopAbs_FACE)
        while explorer.More():
            builder.Add(compound, TopoDS.Face_s(explorer.Current()).Reversed())
            explorer.Next()
        sewing = BRepBuilderAPI_Sewing(1e-6)
        sewing.Add(compound)
        sewing.Perform()
        inside_out = TopoDS_Solid()
        builder.MakeSolid(inside_out)
        builder.Add(inside_out, sewing.SewedShape())

        props = unit_density_properties(inside_out)
        expected = unit_density_properties(solid)
        assert props.orientation_flipped is True
        assert props.mass_kg == pytest.approx(expected.mass_kg, rel=1e-9)
        assert props.com_m == pytest.approx(expected.com_m, abs=1e-9)
        for i in range(3):
            for j in range(3):
                assert props.inertia_kg_m2[i][j] == pytest.approx(
                    expected.inertia_kg_m2[i][j], rel=1e-9
                )
        validate(props)


# ------------------------------------------------------------------------------------------------
# combination, against a hand-computed parallel-axis answer
# ------------------------------------------------------------------------------------------------
class TestCombination:
    def test_two_cubes_combine_by_the_parallel_axis_theorem(self) -> None:
        side = 0.010
        mass = side**3 * PLA
        own = mass * side**2 / 6.0
        d = 0.010  # each cube's centre is 10 mm from the pair's centre
        first = with_density(unit_density_properties(cube(side)), density_for("pla"))
        second = transform_properties(first, translated(IDENTITY, dx=2 * d))
        both = combine([first, second], label="pair")
        assert both.mass_kg == pytest.approx(2 * mass, rel=1e-9)
        assert both.com_m == pytest.approx((d, 0.0, 0.0), abs=1e-9)
        # Offset along x: I_xx untouched, I_yy and I_zz each gain m*d^2 per cube.
        assert both.inertia_kg_m2[0][0] == pytest.approx(2 * own, rel=1e-6)
        assert both.inertia_kg_m2[1][1] == pytest.approx(2 * (own + mass * d**2), rel=1e-6)
        assert both.inertia_kg_m2[2][2] == pytest.approx(2 * (own + mass * d**2), rel=1e-6)

    def test_combining_nothing_is_an_error_not_an_empty_body(self) -> None:
        with pytest.raises(PropertyError):
            combine([])


# ------------------------------------------------------------------------------------------------
# the property test the acceptance gate names
# ------------------------------------------------------------------------------------------------
class TestInvariants:
    @pytest.mark.parametrize("seed", range(12))
    def test_generated_bodies_are_positive_definite_and_satisfy_the_triangle_inequality(
        self, seed: int
    ) -> None:
        """Deterministic pseudo-random bodies: every one must be a body a simulator could integrate."""
        import random

        from build123d import Box

        rng = random.Random(seed)
        members: list[MassProperties] = []
        for index in range(rng.randint(1, 4)):
            size = rng.uniform(0.005, 0.06)
            shape = Box(size * 1e3, rng.uniform(0.005, 0.06) * 1e3, rng.uniform(0.005, 0.06) * 1e3)
            moved = transform_properties(
                unit_density_properties(shape.wrapped),
                translated(IDENTITY, *(rng.uniform(-0.1, 0.1) for _ in range(3))),
            )
            members.append(moved)
        body = combine(members, label=f"seed{seed}")
        validate(body)  # raises on failure
        moments = body.principal_moments()
        assert all(m > 0.0 for m in moments), moments
        assert moments[2] <= moments[0] + moments[1] + 1e-12 * moments[2]
        for i in range(3):
            for j in range(3):
                assert body.inertia_kg_m2[i][j] == pytest.approx(body.inertia_kg_m2[j][i])


# ------------------------------------------------------------------------------------------------
# validation is a hard error, not a warning
# ------------------------------------------------------------------------------------------------
class TestRefusal:
    def body(self, **overrides) -> MassProperties:
        base = MassProperties(
            mass_kg=1.0,
            com_m=(0.0, 0.0, 0.0),
            inertia_kg_m2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )
        return base.model_copy(update=overrides)

    def test_a_negative_definite_tensor_is_refused(self) -> None:
        with pytest.raises(PropertyError, match="positive definite"):
            validate(self.body(inertia_kg_m2=((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))

    def test_an_impossible_triangle_is_refused(self) -> None:
        # No body has one moment larger than the sum of the other two.
        with pytest.raises(PropertyError, match="triangle"):
            validate(self.body(inertia_kg_m2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 10.0))))

    def test_an_asymmetric_tensor_is_refused(self) -> None:
        with pytest.raises(PropertyError, match="symmetric"):
            validate(self.body(inertia_kg_m2=((1.0, 0.5, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))

    def test_a_non_finite_tensor_is_refused(self) -> None:
        with pytest.raises(PropertyError, match="non-finite"):
            validate(self.body(inertia_kg_m2=((float("nan"), 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))))

    def test_a_centre_of_mass_outside_the_body_is_refused(self) -> None:
        with pytest.raises(PropertyError, match="outside"):
            validate(self.body(com_m=(5.0, 0.0, 0.0)), bbox=((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)))


# ------------------------------------------------------------------------------------------------
# assembly wiring, provenance
# ------------------------------------------------------------------------------------------------
class TestAssemblyWiring:
    def test_a_link_is_measured_from_its_instances_and_admits_the_density_is_a_guess(self) -> None:
        asm = assembly_of(
            {"plate": cube(0.010)},
            [("i0", "plate", IDENTITY), ("i1", "plate", translated(IDENTITY, dx=0.020))],
        )
        link = link_properties(asm, "base", ["i0", "i1"])
        assert link.mass_kg == pytest.approx(2 * 0.010**3 * PLA, rel=1e-3)
        assert link.com_m[0] == pytest.approx(0.010, abs=1e-6)
        assert link.is_measured is False
        assert link.rests_on_an_assumed_density is True
        assert len(link.parts) == 2
        assert any("assumed density" in w for w in link.warnings)

    def test_a_weighed_part_is_reported_as_measured(self) -> None:
        asm = assembly_of({"plate": cube(0.010)}, [("i0", "plate", IDENTITY)])
        volume = 0.010**3
        link = link_properties(
            asm,
            "base",
            ["i0"],
            {"plate": measured_density(mass_kg=volume * 1400.0, volume_m3=volume)},
        )
        assert link.is_measured is True
        assert link.rests_on_an_assumed_density is False
        assert link.warnings == []

    def test_the_same_part_placed_twice_is_measured_once(self) -> None:
        asm = assembly_of(
            {"plate": cube(0.010)},
            [("i0", "plate", IDENTITY), ("i1", "plate", translated(IDENTITY, dx=0.020))],
        )
        cache: dict = {}
        link_properties(asm, "base", ["i0", "i1"], cache=cache)
        assert list(cache) == ["plate"]

    def test_an_unknown_instance_or_part_is_refused(self) -> None:
        asm = assembly_of({"plate": cube(0.010)}, [("i0", "plate", IDENTITY)])
        with pytest.raises(PropertyError, match="unknown instance"):
            link_properties(asm, "base", ["nope"])
        with pytest.raises(PropertyError, match="no instances"):
            link_properties(asm, "base", [])

    def test_a_part_flagged_not_solid_is_refused(self) -> None:
        asm = assembly_of({"plate": cube(0.010)}, [("i0", "plate", IDENTITY)])
        asm.parts["plate"].is_solid = False
        with pytest.raises(PropertyError, match="not a closed solid"):
            link_properties(asm, "base", ["i0"])


# ------------------------------------------------------------------------------------------------
# densities
# ------------------------------------------------------------------------------------------------
class TestDensities:
    def test_an_unknown_material_is_labelled_assumed_with_a_range(self) -> None:
        density = density_for(None)
        assert density.source == "assumed"
        assert density.range_kg_m3 is not None
        assert density.is_assumed is True

    def test_a_named_material_is_not_an_assumption_but_a_cad_hint_is(self) -> None:
        assert density_for("aluminium").source == "material"
        hinted = density_for("aluminium", assumed=True)
        assert hinted.source == "assumed"
        assert hinted.value_kg_m3 == pytest.approx(2700.0)

    def test_a_weighed_density_is_the_only_measured_source(self) -> None:
        assert measured_density(1.0, 1.0 / 1400.0).source == "measured"

    def test_an_absurd_measured_density_is_refused(self) -> None:
        # 1 kg over a litre is water; 1 kg over a cubic metre is aerogel and a units error here.
        with pytest.raises(ValueError, match="outside any solid material"):
            measured_density(1.0, 1.0)
        with pytest.raises(ValueError, match="non-positive"):
            measured_density(1.0, 0.0)
