"""Tests for the bundle writers and the seven checks.

The writers are tested on a hand-built two-body model rather than on the SO-101 assembly: a
synthetic model makes the expected numbers writable down, so a failure names the writer instead of
the CAD. The SO-101 run is exercised separately in the demo script.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.compiler import bundle_checks
from ai_cad.compiler.twin_bundle import (
    BodyModel,
    BundleError,
    BundleModel,
    write_mjcf,
    write_urdf,
)


def _box_obj(path: Path, half: float = 0.02) -> None:
    """A closed axis-aligned box as an OBJ, wound outward."""
    v = [
        (-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
        (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half),
    ]
    f = [
        (1, 4, 3), (1, 3, 2),
        (5, 6, 7), (5, 7, 8),
        (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6),
        (3, 4, 8), (3, 8, 7),
        (4, 1, 5), (4, 5, 8),
    ]
    lines = [f"v {x} {y} {z}" for x, y, z in v]
    lines += [f"f {a} {b} {c}" for a, b, c in f]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _model(tmp_path: Path, name: str = "toy") -> BundleModel:
    """Two bodies, one hinge about z, each with one box hull."""
    (tmp_path / "meshes").mkdir(exist_ok=True)
    _box_obj(tmp_path / "meshes" / "base_h0.obj")
    _box_obj(tmp_path / "meshes" / "arm_h0.obj")
    # Solid box, 0.04 m cube, 1 kg: I = m/12 * (a^2 + a^2) about each axis.
    unit = 1.0 / 12.0 * (0.04**2 + 0.04**2)
    base = BodyModel(
        body_id="base",
        name="Base",
        parent=None,
        joint_id=None,
        origin_m=(0.0, 0.0, 0.0),
        mass_kg=1.0,
        com_m=(0.0, 0.0, 0.0),
        inertia_6=(unit, unit, unit, 0.0, 0.0, 0.0),
        hull_files=["base_h0.obj"],
        hull_count=1,
        instance_ids=["i1"],
    )
    arm = BodyModel(
        body_id="arm",
        name="Arm",
        parent="base",
        joint_id="joint_1",
        origin_m=(0.0, 0.0, 0.1),
        axis_dir=(0.0, 0.0, 1.0),
        mass_kg=1.0,
        com_m=(0.0, 0.0, 0.1),
        inertia_6=(unit, unit, unit, 0.0, 0.0, 0.0),
        hull_files=["arm_h0.obj"],
        hull_count=1,
        instance_ids=["i2"],
    )
    return BundleModel(name=name, bodies=[base, arm], total_mass_kg=2.0)


class TestWriters:
    def test_mjcf_nests_the_child_under_its_parent(self, tmp_path):
        model = _model(tmp_path)
        text = write_mjcf(model, tmp_path / "model.mjcf").read_text(encoding="utf-8")
        assert '<body name="base" pos="0.000000000 0.000000000 0.000000000">' in text
        assert '<body name="arm" pos="0.000000000 0.000000000 0.100000000">' in text
        assert '<joint name="joint_1"' in text
        assert text.index('name="base"') < text.index('name="arm"')

    def test_urdf_child_origin_is_the_same_offset(self, tmp_path):
        model = _model(tmp_path)
        text = write_urdf(model, tmp_path / "model.urdf").read_text(encoding="utf-8")
        assert '<origin xyz="0.000000000 0.000000000 0.100000000" rpy="0 0 0"/>' in text
        assert '<axis xyz="0.000000000 0.000000000 1.000000000"/>' in text

    def test_urdf_asks_the_reader_not_to_fuse_fixed_joints(self, tmp_path):
        # Without this MuJoCo merges bodies and renumbers them, which makes a name-matched
        # comparison of the two files meaningless.
        text = write_urdf(_model(tmp_path), tmp_path / "model.urdf").read_text(encoding="utf-8")
        assert 'fusestatic="false"' in text

    def test_two_roots_refuse(self, tmp_path):
        model = _model(tmp_path)
        model.bodies[1].parent = None
        with pytest.raises(BundleError, match="exactly one"):
            write_mjcf(model, tmp_path / "model.mjcf")

    def test_inertia_is_written_in_full_not_only_the_diagonal(self, tmp_path):
        model = _model(tmp_path)
        model.bodies[0].inertia_6 = (1e-4, 2e-4, 3e-4, 1e-5, 2e-5, 3e-5)
        text = write_mjcf(model, tmp_path / "model.mjcf").read_text(encoding="utf-8")
        assert "fullinertia=" in text
        assert "0.0001 0.0002 0.0003" in text


class TestInertiaCheck:
    def test_a_sound_tensor_passes(self, tmp_path):
        result = bundle_checks.check_inertia(_model(tmp_path))
        assert result.status == "pass"
        # A cube's three principal moments are equal, so its margin against the triangle inequality
        # is exactly 1.0. Anything at or below zero would be a body that cannot exist.
        assert result.measured["min_triangle_margin"] == pytest.approx(1.0)

    def test_a_tensor_that_cannot_exist_fails(self, tmp_path):
        # One enormous moment and two tiny ones: no mass distribution does this.
        model = _model(tmp_path)
        model.bodies[0].inertia_6 = (1e-6, 1e-6, 1.0, 0.0, 0.0, 0.0)
        result = bundle_checks.check_inertia(model)
        assert result.status == "fail"
        assert "triangle" in result.explanation

    def test_an_asymmetric_tensor_cannot_be_written_at_all(self, tmp_path):
        from ai_cad.compiler.properties import MassProperties
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MassProperties(mass_kg=1.0, com_m=(0, 0, 0), inertia_kg_m2=((1, 0, 0), (0, 1, 0)))


@pytest.mark.mujoco
class TestLoadedChecks:
    def test_both_files_load_and_agree(self, tmp_path):
        model = _model(tmp_path)
        mjcf = write_mjcf(model, tmp_path / "model.mjcf")
        urdf = write_urdf(model, tmp_path / "model.urdf")
        result = bundle_checks.check_pose_equivalence(mjcf, urdf, samples=20)
        assert result.status == "pass", result.explanation
        assert result.measured["worst_error_m"] <= 1e-9
        assert result.measured["bodies_compared"] == 2

    def test_mujoco_loads_with_zero_warnings(self, tmp_path):
        mjcf = write_mjcf(_model(tmp_path), tmp_path / "model.mjcf")
        result = bundle_checks.check_mujoco_load(mjcf)
        assert result.status == "pass", result.explanation
        assert result.measured["warnings"] == []

    def test_separated_bodies_do_not_self_collide(self, tmp_path):
        mjcf = write_mjcf(_model(tmp_path), tmp_path / "model.mjcf")
        result = bundle_checks.check_self_collision(mjcf)
        assert result.status == "pass", result.explanation

    def test_two_bodies_in_the_same_place_do_collide(self, tmp_path):
        model = _model(tmp_path)
        _box_obj(tmp_path / "meshes" / "middle_h0.obj")
        # Insert a body between base and arm, then drop the arm onto the base's position. The overlap
        # is then between bodies that are not parent and child, which is what the check reports.
        middle = model.bodies[0].model_copy(
            update={
                "body_id": "middle",
                "name": "Middle",
                "parent": "base",
                "joint_id": "joint_0",
                "hull_files": ["middle_h0.obj"],
                "instance_ids": ["i3"],
            }
        )
        model.bodies.append(middle)
        model.bodies[1].parent = "middle"
        # 10 mm apart rather than exactly coincident: MuJoCo's convex solver returns no contact at all
        # for two meshes in exactly the same space, so a test at zero offset would pass for the
        # wrong reason. That blind spot is documented on the check itself.
        model.bodies[1].origin_m = (0.01, 0.0, 0.0)
        model.bodies[1].com_m = (0.01, 0.0, 0.0)
        mjcf = write_mjcf(model, tmp_path / "model.mjcf")
        result = bundle_checks.check_self_collision(mjcf)
        assert result.status == "fail"
        assert result.measured["deepest_m"] < 0
        assert ("base", "arm") in [tuple(p) for p in result.measured["non_adjacent_overlaps"]]

    def test_unlimited_joints_are_reported_not_invented(self, tmp_path):
        mjcf = write_mjcf(_model(tmp_path), tmp_path / "model.mjcf")
        result = bundle_checks.check_limits_and_effort(mjcf, {"joint_1": None})
        assert result.status == "warn"
        assert "joint_1" in result.measured["no_limit"]
        assert "CAD carries none" in result.explanation

    def _limited(self, tmp_path):
        model = _model(tmp_path)
        model.bodies[1].limits = {"lower": -1.5, "upper": 1.5, "effort": 3.0, "velocity": 2.0}
        return write_mjcf(model, tmp_path / "model.mjcf")

    def test_a_limit_with_a_source_is_not_a_pass_without_an_effort(self, tmp_path):
        mjcf = self._limited(tmp_path)
        result = bundle_checks.check_limits_and_effort(
            mjcf, {"joint_1": {"lower": -1.5, "upper": 1.5}}, "the published model at abc123"
        )
        # Travel limits alone are half a specification. This model has no actuator, so nothing in it
        # states what torque the joint may be asked for, and the check must not pass on that.
        assert result.status == "warn"
        assert "no actuators" in result.explanation
        assert "abc123" in result.explanation

    def test_a_force_limited_actuator_with_limits_and_a_source_passes(self, tmp_path):
        mjcf = self._with_actuator(
            self._limited(tmp_path), '<motor name="motor0" joint="joint_1" forcerange="-3 3"/>'
        )
        result = bundle_checks.check_limits_and_effort(
            mjcf, {"joint_1": {"lower": -1.5, "upper": 1.5}}, "the published model at abc123"
        )
        assert result.status == "pass"
        assert "abc123" in result.explanation
        assert result.measured["limits_source"] == "the published model at abc123"
        assert result.measured["actuators"]["motor0"]["force_limited"] is True
        assert result.measured["actuators"]["motor0"]["forcerange"] == pytest.approx([-3.0, 3.0])

    def test_a_command_range_is_not_an_effort_limit(self, tmp_path):
        # A motor with a ctrlrange and no forcerange states how far it may be commanded and nothing
        # about the force that command can deliver. Reading ctrlrange as the effort limit turned this
        # check green on a model that never states a torque.
        mjcf = self._with_actuator(
            self._limited(tmp_path), '<motor name="motor0" joint="joint_1" ctrlrange="-1.5 1.5"/>'
        )
        result = bundle_checks.check_limits_and_effort(
            mjcf, {"joint_1": {"lower": -1.5, "upper": 1.5}}, "the published model at abc123"
        )
        assert result.status == "warn"
        assert "no force limit" in result.explanation
        assert result.measured["actuators"]["motor0"]["force_limited"] is False

    @staticmethod
    def _with_actuator(mjcf: Path, act: str) -> Path:
        """Append an actuator to an MJCF the writer produced without one."""
        text = mjcf.read_text(encoding="utf-8")
        assert "<actuator" not in text
        text = text.replace("</mujoco>", f"  <actuator>{act}</actuator>\n</mujoco>")
        mjcf.write_text(text, encoding="utf-8")
        return mjcf

    def test_a_limit_without_a_source_is_not_a_pass(self, tmp_path):
        # The numbers can be right and still be unverifiable: a limit nobody can trace back to a
        # datasheet or a measurement cannot be checked against the machine. The actuator is forced
        # limited so this test fails on the missing source and not on the missing effort.
        mjcf = self._with_actuator(
            self._limited(tmp_path), '<motor name="motor0" joint="joint_1" forcerange="-3 3"/>'
        )
        result = bundle_checks.check_limits_and_effort(mjcf, {"joint_1": {"lower": -1.5, "upper": 1.5}})
        assert result.status == "warn"
        assert "where" in result.explanation

    def test_free_base_stand_is_skipped_for_a_bolted_arm(self):
        result = bundle_checks.check_free_base_stand()
        assert result.status == "skipped"
        assert "legged" in result.explanation


class TestBrepDistance:
    """The B-rep number is what separates a hull artefact from a design interference."""

    def _assembly(self, second_offset_m: float):
        from types import SimpleNamespace

        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        # A 10 mm cube at the origin, and the same cube moved along x by the offset. This is the
        # real arrangement: the STEP reader keeps shape coordinates in MILLIMETRES and converts
        # only the instance transforms to metres. Building the cube in metres here would hide the
        # conversion bug the reader's convention invites — a metre translation applied to a
        # millimetre shape is a thousand times too small and looks like everything overlapping.
        cube = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
        moved = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
        identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        shifted = (1, 0, 0, second_offset_m, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        instances = [
            SimpleNamespace(instance_id="i1", part_id="p1", transform=identity),
            SimpleNamespace(instance_id="i2", part_id="p2", transform=shifted),
        ]
        parts = {
            "p1": SimpleNamespace(shape=cube),
            "p2": SimpleNamespace(shape=moved),
        }
        return SimpleNamespace(instances=instances, parts=parts)

    def test_two_bodies_a_millimetre_apart_measure_that_gap(self):
        result = bundle_checks.brep_distances(
            self._assembly(0.011), {"A": ["i1"], "B": ["i2"]}, [["A", "B"]]
        )
        assert result["A|B"]["distance_m"] == pytest.approx(1.0e-3, abs=1e-9)
        assert result["A|B"]["shape_pairs"] == 1
        # Nothing is shared when there is a gap, so no boolean is run and no volume is claimed.
        assert result["A|B"]["intersection_m3"] is None

    def test_two_bodies_that_really_overlap_measure_zero(self):
        # 0.005 m shift on a 10 mm cube: the solids intersect, so no positive gap can be claimed.
        result = bundle_checks.brep_distances(
            self._assembly(0.005), {"A": ["i1"], "B": ["i2"]}, [["A", "B"]]
        )
        assert result["A|B"]["distance_m"] == pytest.approx(0.0, abs=1e-12)
        # The shared material is the 5 mm x 10 mm x 10 mm intersection: 5e-7 m3.
        assert result["A|B"]["intersection_m3"] == pytest.approx(5.0e-7, rel=1e-6)

    def test_a_body_with_no_solid_is_reported_as_unmeasured_not_as_zero(self):
        from types import SimpleNamespace

        assembly = SimpleNamespace(
            instances=[SimpleNamespace(instance_id="i1", part_id="p1", transform=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))],
            parts={"p1": SimpleNamespace(shape=None)},
        )
        result = bundle_checks.brep_distances(assembly, {"A": ["i1"], "B": []}, [["A", "B"]])
        assert result["A|B"]["distance_m"] is None


class TestNoticeResolution:
    """One notice, one authority: the text in the YAML header is the text a reader opens."""

    def test_a_markdown_notice_wins_over_a_txt_one(self, tmp_path):
        from ai_cad.compiler.compile import read_notice

        (tmp_path / "NOTICE.txt").write_text("OLD NOTICE", encoding="utf-8")
        (tmp_path / "NOTICE.md").write_text("NEW NOTICE", encoding="utf-8")
        assert read_notice(tmp_path) == "NEW NOTICE"

    def test_a_txt_notice_is_still_read_when_it_is_the_only_one(self, tmp_path):
        from ai_cad.compiler.compile import read_notice

        (tmp_path / "NOTICE.txt").write_text("ONLY NOTICE", encoding="utf-8")
        assert read_notice(tmp_path) == "ONLY NOTICE"

    def test_a_directory_with_no_notice_returns_none_rather_than_an_empty_string(self, tmp_path):
        from ai_cad.compiler.compile import read_notice

        assert read_notice(tmp_path) is None


class TestBrepNote:
    """What the report says about the B-rep number, which is the part a reader acts on."""

    def _note(self, row):
        from ai_cad.compiler.compile import _brep_note

        return _brep_note({"wrist|jaw": row})

    def test_a_gap_is_blamed_on_the_hull_and_still_warns_about_inverse_dynamics(self):
        note = self._note({"distance_m": 3.0e-3, "intersection_m3": None, "shape_pairs": 4, "shape_pairs_total": 9})
        assert "3.000 mm apart" in note
        assert "convex hull filling a concavity" in note
        # The gap explains the CAD solids, not the simulator's geometry: MuJoCo still collides the
        # hulls, so the inverse-dynamics torque still includes the forces that separate them.
        assert "inverse dynamics" in note

    def test_a_tangency_sized_shared_volume_still_carries_the_torque_caveat(self):
        # 5.2e-10 m3 is 0.52 mm3 — contact, not one part inside another. The torque caveat does not
        # depend on how much material is shared: the hulls overlap, so the simulator will fight
        # that overlap in inverse dynamics whatever the solids do.
        note = self._note({"distance_m": 0.0, "intersection_m3": 5.2e-10, "shape_pairs": 47, "shape_pairs_total": 47})
        assert "0.52 mm3" in note
        assert "inverse dynamics" in note
        assert "contact forces disabled" in note

    def test_solids_that_touch_without_sharing_material_are_reported_as_contact(self):
        note = self._note({"distance_m": 0.0, "intersection_m3": 0.0, "shape_pairs": 2, "shape_pairs_total": 2})
        assert "in contact without shared volume" in note
        assert "inverse dynamics" in note


class TestExplanationReadsAloud:
    """A check explanation is spoken as well as read, so a fact stated twice is heard as a stutter."""

    def _note(self, row):
        from ai_cad.compiler.compile import _brep_note

        return _brep_note({"wrist|jaw": row})

    ROWS = [
        {"distance_m": 3.0e-3, "intersection_m3": None, "shape_pairs": 4, "shape_pairs_total": 9},
        {"distance_m": 0.0, "intersection_m3": 5.2e-10, "shape_pairs": 47, "shape_pairs_total": 47},
        {"distance_m": 0.0, "intersection_m3": 0.0, "shape_pairs": 2, "shape_pairs_total": 2},
        {"distance_m": None, "intersection_m3": None, "shape_pairs": None, "shape_pairs_total": None},
    ]

    def test_no_sentence_is_said_twice(self):
        import re

        for row in self.ROWS:
            note = self._note(row)
            sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", note) if s.strip()]
            assert len(sentences) == len(set(sentences)), f"a sentence repeats in {note!r}"

    def test_no_long_run_of_words_is_said_twice(self):
        """Near-duplicates slip past an exact-sentence check; a shared 10-word run does not."""
        import re

        for row in self.ROWS:
            words = re.findall(r"[a-z0-9]+", self._note(row).lower())
            runs = [" ".join(words[i:i + 10]) for i in range(len(words) - 9)]
            assert len(runs) == len(set(runs)), "a 10-word run repeats in the explanation"

    def test_the_hull_reason_is_stated_where_a_reader_acts_on_it(self):
        # The overlap is the hull's, not the CAD's; that is the fact the fail status rests on, and it
        # is stated once, in the sentence that also carries the status.
        note = self._note(self.ROWS[1])
        assert note.lower().count("mujoco collides") == 1
        assert "status stays fail" in note
