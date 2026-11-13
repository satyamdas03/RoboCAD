"""Tests for STEP assembly import.

Fixtures are generated at test time rather than committed: a tiny assembly built through XCAF and
written to STEP exercises the same reader path the real 20 MB SO-101 file takes, while keeping the
expected part, instance and unit numbers small enough to assert exactly.

The real file is not in the repo (20 MB, third-party). Local verification against it is recorded in
the M1 notes, not here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("OCP.BRepPrimAPI", reason="STEP import needs the OCP kernel installed")

from ai_cad.importers import (  # noqa: E402
    ImportedAssembly,
    ImportedInstance,
    ImportedPart,
    PartSignature,
    determinant,
    is_proper_rotation,
    rotation_error,
)
from ai_cad.importers.step_import import (  # noqa: E402
    StepImporter,
    StepImportError,
    import_step,
    iter_shapes,
)

IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


# --------------------------------------------------------------------------------------------
# fixture builders
# --------------------------------------------------------------------------------------------
def _translated(x: float = 0.0, y: float = 0.0, z: float = 0.0):
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(trsf)


def _write_step(path: Path, parts_spec) -> Path:
    """Write a small assembly to STEP.

    ``parts_spec`` is a list of ``(part_name, (dx, dy, dz), [(component_name, translation), ...])``.
    Each part is defined once and referenced by every component, which is what a real assembly does.
    """
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    asm = shape_tool.NewShape()
    TDataStd_Name.Set_s(asm, TCollection_ExtendedString("fixture_asm"))

    for part_name, size, components in parts_spec:
        solid = BRepPrimAPI_MakeBox(*size).Shape()
        part_label = shape_tool.AddShape(solid, False)
        TDataStd_Name.Set_s(part_label, TCollection_ExtendedString(part_name))
        for comp_name, transform in components:
            comp = shape_tool.AddComponent(asm, part_label, transform)
            if comp_name:
                TDataStd_Name.Set_s(comp, TCollection_ExtendedString(comp_name))

    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    assert writer.Transfer(doc, STEPControl_AsIs)
    status = writer.Write(str(path))
    assert "RetDone" in str(status), f"STEP write failed: {status}"
    assert path.stat().st_size > 0
    return path


@pytest.fixture(scope="module")
def assembly_step(tmp_path_factory) -> Path:
    """One rail placed twice and one plate placed once, in millimetres."""
    out = tmp_path_factory.mktemp("step_import") / "fixture.step"
    return _write_step(
        out,
        [
            ("rail", (10.0, 20.0, 30.0), [("rail_a", _translated()), ("rail_b", _translated(0, 0, 100))]),
            ("plate", (10.0, 10.0, 10.0), [("", _translated(50, 0, 0))]),
        ],
    )


# --------------------------------------------------------------------------------------------
# transform maths
# --------------------------------------------------------------------------------------------
class TestTransforms:
    def test_identity_is_a_proper_rotation(self):
        assert determinant(IDENTITY) == pytest.approx(1.0)
        assert rotation_error(IDENTITY) == pytest.approx(0.0)
        assert is_proper_rotation(IDENTITY)

    def test_reflection_has_negative_determinant(self):
        mirrored = list(IDENTITY)
        mirrored[0] = -1.0  # x -> -x, a mirror through the YZ plane
        m = tuple(mirrored)
        assert determinant(m) == pytest.approx(-1.0)
        # A reflection is orthogonal, so the orthonormality test alone cannot spot it.
        assert rotation_error(m) == pytest.approx(0.0)
        assert not is_proper_rotation(m)

    def test_rotation_is_proper_and_detects_as_such(self):
        import math

        c, s = math.cos(math.pi / 2), math.sin(math.pi / 2)
        m = (c, -s, 0.0, 0.0, s, c, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        assert determinant(m) == pytest.approx(1.0, abs=1e-12)
        assert is_proper_rotation(m)

    def test_scale_is_not_a_proper_rotation(self):
        scaled = list(IDENTITY)
        scaled[0] = 2.0
        m = tuple(scaled)
        assert not is_proper_rotation(m)
        assert rotation_error(m) > 1.0

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError):
            determinant((1.0, 0.0, 0.0))
        with pytest.raises(ValueError):
            rotation_error((1.0, 0.0, 0.0))


# --------------------------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------------------------
def _sig(**overrides) -> PartSignature:
    base = dict(
        volume_m3=6e-6,
        surface_area_m2=2.2e-3,
        bbox_min_m=(0.0, 0.0, 0.0),
        bbox_max_m=(0.01, 0.02, 0.03),
        face_count=6,
        face_type_counts={"Plane": 6},
    )
    base.update(overrides)
    return PartSignature(**base)


class TestModels:
    def test_signature_keys_are_stable_and_deduplicate(self):
        assert _sig().key() == _sig().key()

    def test_signature_key_separates_different_geometry(self):
        assert _sig().key() != _sig(face_count=8).key()
        assert _sig().key() != _sig(volume_m3=6.1e-6).key()  # 100 mm^3 apart

    def test_signature_key_ignores_sub_tolerance_noise(self):
        # Identity is quantized at 1 mm^3 volume, 1 mm^2 area and 1 um extent, so measurement noise
        # below that is the same part, and anything a designer would state differently is not.
        assert _sig().key() == _sig(volume_m3=6e-6 + 1e-12).key()
        assert _sig().key() == _sig(bbox_max_m=(0.01, 0.02, 0.03 + 1e-9)).key()
        assert _sig().key() != _sig(bbox_max_m=(0.01, 0.02, 0.030001)).key()

    def test_instance_reflection_flag_must_match_transform(self):
        mirrored = tuple(-1.0 if i in (0, 5, 10) else v for i, v in enumerate(IDENTITY))
        with pytest.raises(ValueError):
            ImportedInstance(
                instance_id="i1", name="n", part_id="p1", transform=mirrored, is_reflected=False
            )
        inst = ImportedInstance(
            instance_id="i1", name="n", part_id="p1", transform=mirrored, is_reflected=True
        )
        assert inst.is_reflected

    def test_part_rejects_non_finite_measurements(self):
        with pytest.raises(ValueError):
            ImportedPart(part_id="p1", name="n", signature=_sig(volume_m3=float("inf")))

    def test_assembly_counts(self):
        asm = ImportedAssembly(
            parts={
                "p1": ImportedPart(part_id="p1", name="rail", signature=_sig()),
            },
            instances=[
                ImportedInstance(instance_id="i1", name="a", part_id="p1", transform=IDENTITY),
                ImportedInstance(instance_id="i2", name="b", part_id="p1", transform=IDENTITY),
            ],
        )
        assert asm.part_count == 1
        assert asm.instance_count == 2
        assert len(asm.instances_by_part()["p1"]) == 2


# --------------------------------------------------------------------------------------------
# STEP import
# --------------------------------------------------------------------------------------------
class TestStepImport:
    def test_parts_are_deduplicated_by_geometry_not_by_placement(self, assembly_step):
        asm = import_step(assembly_step)
        assert asm.part_count == 2
        assert asm.instance_count == 3
        reused = [pid for pid, insts in asm.instances_by_part().items() if len(insts) == 2]
        assert len(reused) == 1

    def test_units_are_metres(self, assembly_step):
        asm = import_step(assembly_step)
        rail = next(p for p in asm.parts.values() if p.name == "rail")
        # 10 x 20 x 30 mm = 6000 mm^3 = 6e-6 m^3, and the bbox is 0.01 x 0.02 x 0.03 m.
        assert rail.signature.volume_m3 == pytest.approx(6e-6, rel=1e-9)
        size = tuple(
            hi - lo
            for hi, lo in zip(rail.signature.bbox_max_m, rail.signature.bbox_min_m)
        )
        assert size == pytest.approx((0.01, 0.02, 0.03), rel=1e-6)

    def test_transforms_are_rigid_and_carry_the_placement(self, assembly_step):
        asm = import_step(assembly_step)
        rail_insts = [
            i
            for i in asm.instances
            if asm.parts[i.part_id].name == "rail"
        ]
        zs = sorted(round(i.transform[11], 6) for i in rail_insts)
        assert zs == [0.0, 0.1]  # 100 mm up, expressed in metres
        for inst in asm.instances:
            assert is_proper_rotation(inst.transform)
            assert not inst.is_reflected

    def test_names_never_leak_internal_label_references(self, assembly_step):
        asm = import_step(assembly_step)
        assert asm.root_name == "fixture_asm"
        for inst in asm.instances:
            assert inst.name
            assert not inst.name.startswith("=>[")

    def test_assembly_path_starts_at_the_root(self, assembly_step):
        asm = import_step(assembly_step)
        for inst in asm.instances:
            assert inst.assembly_path[0] == "fixture_asm"

    def test_clean_file_imports_without_warnings(self, assembly_step):
        assert import_step(assembly_step).warnings == []

    def test_iter_shapes_yields_one_entry_per_instance(self, assembly_step):
        asm = import_step(assembly_step)
        pairs = list(iter_shapes(asm))
        assert len(pairs) == asm.instance_count
        assert all(shape is not None for _, shape in pairs)

    def test_signature_survives_the_step_round_trip(self, assembly_step):
        asm = import_step(assembly_step)
        rail = next(p for p in asm.parts.values() if p.name == "rail")
        assert rail.signature.face_count == 6
        assert rail.signature.face_type_counts.get("Plane") == 6

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(StepImportError, match="no such STEP file"):
            import_step(tmp_path / "nope.step")

    def test_oversized_file_is_refused_before_parsing(self, assembly_step):
        with pytest.raises(StepImportError, match="import limit"):
            StepImporter(max_bytes=128).read(assembly_step)

    def test_parse_budget_is_enforced(self, assembly_step):
        with pytest.raises(StepImportError, match="budget"):
            StepImporter(parse_budget_s=1e-9).read(assembly_step)

    def test_non_step_content_fails_loudly(self, tmp_path):
        junk = tmp_path / "junk.step"
        junk.write_bytes(b"this is not a STEP file\n" * 10)
        with pytest.raises(StepImportError):
            import_step(junk)


class TestReflections:
    """Reflection handling at the two places it can go wrong: the transform and the STEP round trip."""

    def test_mirror_placement_is_flagged_and_kept_out_of_proper_rotations(self):
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
        from OCP.TopLoc import TopLoc_Location

        from ai_cad.importers.step_import import _toploc_to_matrix

        trsf = gp_Trsf()
        trsf.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))  # mirror through the YZ plane
        world = _toploc_to_matrix(TopLoc_Location(trsf))

        assert determinant(world) == pytest.approx(-1.0)
        # The reflection is orthogonal, so an orthonormality check alone says "fine".
        assert rotation_error(world) == pytest.approx(0.0)
        # It is nonetheless not a proper rotation, which is the gate the physics stages use before
        # applying a part's inertia to an instance.
        assert not is_proper_rotation(world)

        inst = ImportedInstance(
            instance_id="i1", name="left", part_id="p1", transform=world, is_reflected=True
        )
        assert inst.is_reflected
        with pytest.raises(ValueError):
            ImportedInstance(
                instance_id="i1", name="left", part_id="p1", transform=world, is_reflected=False
            )

    def test_step_round_trip_rewrites_a_mirrored_placement(self, tmp_path):
        """Documents a real OCC behaviour that limits what the reflection flag can promise.

        Built in memory, a mirrored placement has determinant -1. Written to STEP and read back, OCC
        hands us a proper 180 degree rotation instead: STEP's cartesian transformation has no
        left-handed form here, so the mirroring is silently lost. Consequence: ``is_reflected`` is
        true for every left-handed placement the reader actually delivers, but it cannot detect a
        mirror that a STEP writer already converted. If a future OCC preserves it, this test flips
        and the compiler gains reflection detection it did not have.
        """
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_AsIs
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFApp import XCAFApp_Application
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

        part_label = shape_tool.AddShape(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape(), False)
        TDataStd_Name.Set_s(part_label, TCollection_ExtendedString("mirrored_part"))
        asm = shape_tool.NewShape()
        TDataStd_Name.Set_s(asm, TCollection_ExtendedString("mirror_asm"))
        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
        shape_tool.AddComponent(asm, part_label, TopLoc_Location(mirror))
        shape_tool.UpdateAssemblies()

        out = tmp_path / "mirror.step"
        writer = STEPCAFControl_Writer()
        assert writer.Transfer(doc, STEPControl_AsIs)
        writer.Write(str(out))

        asm_back = import_step(out)
        inst = asm_back.instances[0]
        assert inst.is_reflected == (determinant(inst.transform) < 0.0)  # invariant always holds
        assert determinant(inst.transform) > 0.0, "OCC preserved the mirror; update the docstring"

