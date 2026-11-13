"""A printed part is a shell over infill, not a casting, and the difference must be visible.

The compiler's solid-volume mass is an upper bound and stays reported. This file pins the model that
turns that bound into an estimate: the shell/infill rule, its caps, the fact that it applies only to
printed materials, and the fact that its assumptions reach the link's warnings instead of staying
inside a number.
"""
from __future__ import annotations

import pytest

from ai_cad.compiler.materials import is_printed_material
from ai_cad.compiler.print_model import (
    DEFAULT_INFILL_FRACTION,
    DEFAULT_WALL_THICKNESS_M,
    INFILL_SENSITIVITY,
    PrintModel,
    is_solid_at_this_wall,
)
from ai_cad.compiler.properties import PropertyError, link_properties, surface_area_m2

PLA = 1240.0


def cube(side_m: float):
    from build123d import Box

    return Box(side_m * 1e3, side_m * 1e3, side_m * 1e3).wrapped


def thin_plate(side_m: float, thickness_m: float):
    from build123d import Box

    return Box(side_m * 1e3, side_m * 1e3, thickness_m * 1e3).wrapped


IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def assembly_of(parts: dict[str, object], placements: list[tuple[str, str, tuple[float, ...]]]):
    from ai_cad.importers.models import (
        ImportedAssembly,
        ImportedInstance,
        ImportedPart,
        PartSignature,
    )

    imported = {
        part_id: ImportedPart(
            part_id=part_id,
            name=part_id,
            signature=PartSignature(
                volume_m3=1e-6,
                surface_area_m2=0.0,
                bbox_min_m=(0.0, 0.0, 0.0),
                bbox_max_m=(0.0, 0.0, 0.0),
                face_count=6,
            ),
            shape=shape,
        )
        for part_id, shape in parts.items()
    }
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


class TestTheVolumeRule:
    def test_shell_plus_infill_is_the_reported_volume(self) -> None:
        model = PrintModel(wall_thickness_m=0.0012, infill_fraction=0.2)
        solid, area = 1.0e-5, 2.0e-3
        shell = area * 0.0012
        expected = shell + 0.2 * (solid - shell)
        assert model.effective_volume_m3(solid, area) == pytest.approx(expected, rel=1e-12)
        assert model.shell_volume_m3(solid, area) == pytest.approx(shell, rel=1e-12)

    def test_a_part_thinner_than_its_wall_prints_solid(self) -> None:
        model = PrintModel()
        # 40 x 40 x 0.3 mm plate: volume 0.48 cm3, area 3.24 cm2, so area * wall > volume.
        plate = thin_plate(0.040, 0.0003)
        solid = 0.040 * 0.040 * 0.0003
        area = surface_area_m2(plate)
        assert area * model.wall_thickness_m > solid
        assert model.effective_volume_m3(solid, area) == pytest.approx(solid, rel=1e-12)
        assert model.mass_factor(solid, area) == pytest.approx(1.0, rel=1e-12)
        assert is_solid_at_this_wall(solid, area, model) is True

    def test_the_model_never_exceeds_the_solid_and_never_undercuts_the_wall(self) -> None:
        model = PrintModel()
        for solid in (1.0e-9, 1.0e-6, 1.0e-4, 1.0e-2):
            for area in (1.0e-5, 1.0e-3, 1.0e-1):
                effective = model.effective_volume_m3(solid, area)
                shell = model.shell_volume_m3(solid, area)
                assert shell <= solid + 1e-18
                assert effective <= solid * (1.0 + 1e-12)
                assert effective >= shell
                assert 0.0 < model.mass_factor(solid, area) <= 1.0

    def test_zero_infill_leaves_only_the_wall(self) -> None:
        model = PrintModel(infill_fraction=0.0)
        solid, area = 1.0e-5, 2.0e-3
        assert model.effective_volume_m3(solid, area) == pytest.approx(area * 0.0012, rel=1e-12)

    def test_full_infill_is_the_solid(self) -> None:
        model = PrintModel(infill_fraction=1.0)
        solid, area = 1.0e-5, 2.0e-3
        assert model.effective_volume_m3(solid, area) == pytest.approx(solid, rel=1e-12)

    def test_sensitivity_rows_keep_the_wall_and_sweep_the_infill(self) -> None:
        rows = PrintModel(wall_thickness_m=0.0016).sensitivity()
        assert [r.infill_fraction for r in rows] == list(INFILL_SENSITIVITY)
        assert {r.wall_thickness_m for r in rows} == {0.0016}
        # more infill is always heavier
        solid, area = 1.0e-5, 2.0e-3
        volumes = [r.effective_volume_m3(solid, area) for r in rows]
        assert volumes == sorted(volumes)


class TestWhichMaterialsItAppliesTo:
    def test_filament_materials_are_printed(self) -> None:
        for name in ("pla", "petg", "ABS", "nylon", "resin"):
            assert is_printed_material(name) is True

    def test_stock_materials_are_not(self) -> None:
        for name in ("aluminium", "6061", "steel", "brass", "carbon_fibre"):
            assert is_printed_material(name) is False

    def test_nothing_supplied_is_not_printed(self) -> None:
        assert is_printed_material(None) is False
        assert is_printed_material("") is False


class TestLinkWiring:
    def test_the_solid_mass_is_still_reported_alongside_the_printed_one(self) -> None:
        side = 0.020
        asm = assembly_of({"block": cube(side)}, [("i0", "block", IDENTITY)])
        solid_mass = side**3 * PLA
        plain = link_properties(asm, "arm", ["i0"])

        model = PrintModel()
        printed = link_properties(asm, "arm", ["i0"], print_model=model)

        assert plain.mass_kg == pytest.approx(solid_mass, rel=1e-3)
        assert plain.parts[0].volume_m3 == pytest.approx(side**3, rel=1e-3)
        assert plain.parts[0].effective_volume_m3 is None
        assert plain.parts[0].print_modelled is False

        area = 6 * side**2
        assert printed.parts[0].surface_area_m2 == pytest.approx(area, rel=1e-6)
        expected = model.effective_volume_m3(side**3, area)
        assert printed.parts[0].effective_volume_m3 == pytest.approx(expected, rel=1e-6)
        assert printed.mass_kg == pytest.approx(expected * PLA, rel=1e-3)
        # the solid figure is untouched, so a report can print the bound and the estimate together
        assert printed.parts[0].volume_m3 == pytest.approx(side**3, rel=1e-3)
        assert printed.mass_kg < plain.mass_kg

    def test_the_inertia_scales_with_the_mass_and_stays_physical(self) -> None:
        asm = assembly_of({"block": cube(0.020)}, [("i0", "block", IDENTITY)])
        plain = link_properties(asm, "arm", ["i0"])
        printed = link_properties(asm, "arm", ["i0"], print_model=PrintModel())
        factor = printed.mass_kg / plain.mass_kg
        for i in range(3):
            for j in range(3):
                assert printed.inertia_kg_m2[i][j] == pytest.approx(
                    plain.inertia_kg_m2[i][j] * factor, rel=1e-9
                )
        # a physically valid tensor survives the scaling, and the centre of mass does not move
        for moment in printed.principal_moments():
            assert moment > 0.0
        assert printed.com_m == pytest.approx(plain.com_m, abs=1e-12)

    def test_a_metal_part_is_not_print_modelled(self) -> None:
        from ai_cad.compiler.materials import Density

        asm = assembly_of({"bracket": cube(0.020)}, [("i0", "bracket", IDENTITY)])
        steel = Density(value_kg_m3=7850.0, source="material", material="steel")
        plain = link_properties(asm, "arm", ["i0"], {"bracket": steel})
        printed = link_properties(
            asm, "arm", ["i0"], {"bracket": steel}, print_model=PrintModel()
        )
        assert printed.mass_kg == pytest.approx(plain.mass_kg, rel=1e-12)
        assert printed.parts[0].print_modelled is False
        assert printed.parts[0].surface_area_m2 is None

    def test_the_assumption_reaches_the_link_warnings(self) -> None:
        asm = assembly_of({"block": cube(0.020)}, [("i0", "block", IDENTITY)])
        model = PrintModel(wall_thickness_m=0.0016, infill_fraction=0.25)
        printed = link_properties(asm, "arm", ["i0"], print_model=model)
        joined = " ".join(printed.warnings)
        assert "1.60 mm wall over 25% infill" in joined
        assert "model, not a measurement" in joined
        assert "centre of mass" in joined
        # and the density assumption is still disclosed, not replaced by the new one
        assert "assumed density" in joined
        assert printed.rests_on_an_assumed_density is True

    def test_the_area_cache_is_shared_across_links(self) -> None:
        asm = assembly_of(
            {"block": cube(0.020)},
            [("i0", "block", IDENTITY), ("i1", "block", IDENTITY)],
        )
        cache: dict[str, float] = {}
        for link in ("a", "b"):
            link_properties(asm, link, ["i0"], print_model=PrintModel(), area_cache=cache)
        assert list(cache) == ["block"]

    def test_surface_area_matches_the_closed_form_for_a_cube(self) -> None:
        for side in (0.010, 0.020, 0.050):
            assert surface_area_m2(cube(side)) == pytest.approx(6 * side**2, rel=1e-9)

    def test_surface_area_matches_the_closed_form_for_a_cylinder(self) -> None:
        from build123d import Cylinder

        radius, height = 0.008, 0.030
        shape = Cylinder(radius * 1e3, height * 1e3).wrapped
        expected = 2 * 3.141592653589793 * radius * height + 2 * 3.141592653589793 * radius**2
        assert surface_area_m2(shape) == pytest.approx(expected, rel=1e-6)


class TestBoughtInParts:
    def test_a_datasheet_density_reproduces_the_datasheet_mass(self) -> None:
        from ai_cad.compiler.materials import datasheet_density

        volume = 4.0e-5
        density = datasheet_density(0.055, volume, "Feetech STS3215 specification: 55 +/- 1 g")
        assert density.value_kg_m3 * volume == pytest.approx(0.055, rel=1e-12)
        assert density.bought_in is True
        assert density.source == "datasheet"
        assert density.is_assumed is False

    def test_a_mass_without_a_citation_is_refused(self) -> None:
        from ai_cad.compiler.materials import datasheet_density

        with pytest.raises(ValueError):
            datasheet_density(0.055, 4.0e-5, "   ")
        with pytest.raises(ValueError):
            datasheet_density(0.055, 0.0, "some datasheet")

    def test_an_envelope_too_small_for_the_mass_is_refused(self) -> None:
        from ai_cad.compiler.materials import datasheet_density

        # 55 g in a 1 mm cube would be 55000 kg/m3, which is no solid part.
        with pytest.raises(ValueError):
            datasheet_density(0.055, 1.0e-9, "some datasheet")

    def test_the_print_model_leaves_a_bought_in_part_at_its_datasheet_mass(self) -> None:
        from ai_cad.compiler.materials import datasheet_density

        asm = assembly_of({"servo": cube(0.020)}, [("i0", "servo", IDENTITY)])
        volume = 0.020**3
        servo = datasheet_density(0.055, volume, "Feetech STS3215 specification")
        plain = link_properties(asm, "arm", ["i0"], {"servo": servo})
        printed = link_properties(asm, "arm", ["i0"], {"servo": servo}, print_model=PrintModel())
        assert plain.mass_kg == pytest.approx(0.055, rel=1e-6)
        assert printed.mass_kg == pytest.approx(0.055, rel=1e-6)
        assert printed.parts[0].print_modelled is False
        assert printed.parts[0].surface_area_m2 is None
        assert printed.bought_in_parts == 1
        assert printed.print_modelled_parts == 0


class TestTheBundleCarriesBothFigures:
    def _bundle(self, print_model):
        from ai_cad.compiler.kinematics import BodyAssignment, Skeleton
        from ai_cad.compiler.twin_bundle import build_bundle

        asm = assembly_of({"block": cube(0.020)}, [("i0", "block", IDENTITY)])
        skeleton = Skeleton(
            bodies=[BodyAssignment(body_id="arm", name="Arm", instance_ids=["i0"], part_ids=["block"])]
        )
        model, props, _ = build_bundle(skeleton, asm, name="toy", print_model=print_model)
        return model, props["arm"]

    def test_without_a_print_model_there_is_no_estimate(self) -> None:
        model, props = self._bundle(None)
        body = model.bodies[0]
        assert body.printed_mass_kg is None
        assert body.solid_mass_kg == pytest.approx(body.mass_kg, rel=1e-12)
        assert model.total_solid_mass_kg == pytest.approx(model.total_mass_kg, rel=1e-12)
        assert body.print_model is None

    def test_with_a_print_model_the_bound_and_the_estimate_both_survive(self) -> None:
        model, props = self._bundle(PrintModel(wall_thickness_m=0.0012, infill_fraction=0.20))
        body = model.bodies[0]
        assert body.print_model == "1.20 mm wall over 20% infill"
        assert body.printed_parts == 1
        assert body.printed_mass_kg == pytest.approx(body.mass_kg, rel=1e-12)
        assert body.solid_mass_kg == pytest.approx(props.solid_mass_kg, rel=1e-12)
        assert body.printed_mass_kg < body.solid_mass_kg
        assert model.total_solid_mass_kg > model.total_mass_kg


def test_the_defaults_are_the_stated_ones() -> None:
    model = PrintModel()
    assert model.wall_thickness_m == DEFAULT_WALL_THICKNESS_M == 0.0012
    assert model.infill_fraction == DEFAULT_INFILL_FRACTION == 0.20
    assert INFILL_SENSITIVITY == (0.15, 0.20, 0.30)


class TestActuatorsArriveWithADatasheetMass:
    """A servo is bought, not printed. Its mass cannot come out of its envelope volume."""

    def _assembly(self, side_m: float):
        from ai_cad.importers.models import ImportedAssembly, ImportedInstance, ImportedPart, PartSignature

        part = ImportedPart(
            part_id="servo",
            name="Servo motor",
            signature=PartSignature(
                volume_m3=side_m**3,
                surface_area_m2=0.0,
                bbox_min_m=(0.0, 0.0, 0.0),
                bbox_max_m=(0.0, 0.0, 0.0),
                face_count=6,
            ),
            shape=cube(side_m),
        )
        return ImportedAssembly(
            parts={"servo": part},
            instances=[
                ImportedInstance(
                    instance_id="i0",
                    name="i0",
                    part_id="servo",
                    transform=IDENTITY,
                    is_reflected=False,
                )
            ],
        )

    def test_an_actuator_gets_the_density_that_reproduces_its_datasheet_mass(self) -> None:
        from ai_cad.compiler.compile import actuator_densities

        densities, skipped = actuator_densities(self._assembly(0.020), 0.055, "Feetech STS3215 spec")
        assert skipped == []
        assert densities["servo"].bought_in is True
        assert densities["servo"].value_kg_m3 * 0.020**3 == pytest.approx(0.055, rel=1e-9)

    def test_a_part_the_classifier_does_not_call_an_actuator_is_left_alone(self) -> None:
        from ai_cad.compiler.compile import actuator_densities

        assembly = self._assembly(0.020)
        assembly.parts["servo"] = assembly.parts["servo"].model_copy(
            update={"name": "Upper arm"}
        )
        densities, _ = actuator_densities(assembly, 0.055, "Feetech STS3215 spec")
        assert densities == {}

    def test_an_impossible_envelope_is_reported_and_not_invented(self) -> None:
        from ai_cad.compiler.compile import actuator_densities

        densities, skipped = actuator_densities(self._assembly(0.001), 0.055, "Feetech STS3215 spec")
        assert densities == {}
        assert len(skipped) == 1
        assert "kept an assumed density" in skipped[0]

    def test_a_datasheet_mass_without_a_source_is_refused(self) -> None:
        from ai_cad.compiler.compile import actuator_densities

        with pytest.raises(ValueError):
            actuator_densities(self._assembly(0.020), 0.055, "")
