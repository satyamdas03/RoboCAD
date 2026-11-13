"""Tests for the servo-mediated kinematic skeleton.

The skeleton is the one stage of the twin that cannot be checked against a simulator, so these tests
pin its two load-bearing claims directly: that a servo's output axis is read from the family of
concentric cylinders on it, and that every instance ends up on exactly one body.
"""
from __future__ import annotations

import pytest

from ai_cad.compiler.kinematics import (
    SERVO_MIN_FACES,
    KinematicsError,
    ServoAxis,
    assign_bodies,
    servo_axis,
)
from ai_cad.importers.features import CylinderFace
from ai_cad.importers.joints import LinkGroup


def face(radius_mm, point=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0), instance="inst_1"):
    return CylinderFace(
        instance_id=instance,
        radius_m=radius_mm / 1e3,
        axis_point=point,
        axis_dir=direction,
        is_bore=True,
    )


def group(link_id, name, instances, lo, hi, role="link"):
    return LinkGroup(
        link_id=link_id,
        name=name,
        instance_ids=list(instances),
        part_ids=[f"part_{link_id}"],
        bbox_min_m=lo,
        bbox_max_m=hi,
        role=role,
    )


class TestServoAxis:
    def test_a_radius_family_wins_over_a_single_boss(self):
        faces = [
            face(8.53, (0, 0, 0.02)),
            face(8.70, (0, 0, 0.02)),
            face(9.80, (0, 0, 0.02)),
            face(20.0, point := (0, 0.05, 0.02)),
        ]
        axis = servo_axis(faces, "servo")
        assert axis.face_count == 3
        assert pytest.approx(axis.radii_m) == [0.00853, 0.0087, 0.0098]
        assert axis.direction == (1.0, 0.0, 0.0)

    def test_a_single_crossing_radius_is_not_a_family(self):
        # One big circle and nothing concentric with it. The radius family on the other axis wins.
        faces = [
            face(20.0),
            face(8.53, (0, 0.02, 0.0), (0, 0, 1)),
            face(9.80, (0, 0.02, 0.0), (0, 0, 1)),
        ]
        axis = servo_axis(faces, "servo")
        assert axis.direction == (0.0, 0.0, 1.0)
        assert axis.face_count == 2

    def test_small_cylinders_are_ignored(self):
        # Below 6 mm a servo is covered in fastener holes. They must not form the winner.
        faces = [face(1.5, (0, 0, i * 1e-3)) for i in range(6)]
        faces += [face(8.53, (0, 0.02, 0), (0, 0, 1)), face(9.80, (0, 0.02, 0), (0, 0, 1))]
        axis = servo_axis(faces, "servo")
        assert axis.direction == (0.0, 0.0, 1.0)

    def test_no_family_refuses_rather_than_guesses(self):
        # Three bosses on three parallel but separate axes: each is its own axis, none is a bearing.
        with pytest.raises(KinematicsError, match="concentric cylinders"):
            servo_axis(
                [face(20.0, (0, 0, 0)), face(15.0, (0, 0.02, 0)), face(10.0, (0, 0.04, 0))],
                "servo",
            )

    def test_no_cylinder_at_all_refuses(self):
        with pytest.raises(KinematicsError, match="no cylindrical face"):
            servo_axis([], "servo")

    def test_direction_is_canonical(self):
        faces = [face(8.53, direction=(-1.0, 0.0, 0.0)), face(9.80, direction=(-1.0, 0.0, 0.0))]
        axis = servo_axis(faces, "servo")
        assert axis.direction[0] > 0.0, "a joint axis pointing backwards is still the same joint"

    def test_anti_parallel_faces_share_one_axis(self):
        # A bore modelled from the other side carries the opposite direction vector.
        faces = [face(8.53), face(9.80, direction=(-1.0, 0.0, 0.0))]
        axis = servo_axis(faces, "servo")
        assert axis.face_count == 2

    def test_faces_on_parallel_but_offset_axes_do_not_merge(self):
        faces = [face(8.53, (0, 0, 0)), face(9.80, (0, 0.01, 0))]
        with pytest.raises(KinematicsError):
            servo_axis(faces, "servo")


class TestAssignBodies:
    def test_every_other_group_goes_to_the_nearest_chain_body(self):
        links = [
            group("base", "Base", ["a1"], (0, 0, 0), (0.1, 0.1, 0.1)),
            group("arm", "Arm", ["a2"], (1.0, 0, 0), (1.1, 0.1, 0.1)),
            group("servo", "ST3215", ["s1"], (0.95, 0, 0), (1.05, 0.1, 0.1), role="actuator"),
        ]
        bodies, seen = assign_bodies(links, ["base", "arm"])
        by_id = {b.body_id: b for b in bodies}
        assert "s1" in by_id["arm"].instance_ids
        assert by_id["arm"].attached_groups == {"servo": 1}
        assert seen == {"a1": "base", "a2": "arm", "s1": "arm"}

    def test_the_chain_bodies_come_first_and_in_order(self):
        links = [
            group("base", "Base", [], (0, 0, 0), (0.1, 0.1, 0.1)),
            group("arm", "Arm", [], (1, 0, 0), (1.1, 0.1, 0.1)),
        ]
        bodies, _ = assign_bodies(links, ["base", "arm"])
        assert [b.body_id for b in bodies] == ["base", "arm"]

    def test_a_missing_chain_name_refuses(self):
        links = [group("base", "Base", [], (0, 0, 0), (0.1, 0.1, 0.1))]
        with pytest.raises(KinematicsError, match="does not contain"):
            assign_bodies(links, ["base", "arm"])

    def test_an_instance_on_two_links_refuses(self):
        links = [
            group("base", "Base", ["shared"], (0, 0, 0), (0.1, 0.1, 0.1)),
            group("arm", "Arm", ["shared"], (1, 0, 0), (1.1, 0.1, 0.1)),
        ]
        with pytest.raises(KinematicsError, match="assigned to both"):
            assign_bodies(links, ["base", "arm"])


class TestApplyLimits:
    def _skeleton(self):
        from ai_cad.compiler.kinematics import BodyAssignment, DerivedJoint, Skeleton

        return Skeleton(
            bodies=[
                BodyAssignment(body_id="base", name="Base", instance_ids=["a"]),
                BodyAssignment(body_id="arm", name="Arm", instance_ids=["b"]),
            ],
            joints=[
                DerivedJoint(
                    joint_id="joint_1",
                    parent_body="base",
                    child_body="arm",
                    axis_point=(0.0, 0.0, 0.0),
                    axis_dir=(0.0, 0.0, 1.0),
                    servo="servo",
                    horn_instance="horn",
                )
            ],
        )

    def test_a_source_is_recorded_with_the_numbers(self):
        from ai_cad.compiler.kinematics import apply_limits

        skeleton = apply_limits(
            self._skeleton(), {"joint_1": {"lower": -1.7, "upper": 1.7}}, "a datasheet, page 4"
        )
        joint = skeleton.joints[0]
        assert joint.limits == {"lower": -1.7, "upper": 1.7}
        assert joint.limits_source == "a datasheet, page 4"

    def test_a_joint_the_file_omits_stays_unknown(self):
        from ai_cad.compiler.kinematics import apply_limits

        skeleton = apply_limits(self._skeleton(), {"joint_9": {"lower": 0, "upper": 1}}, "src")
        assert skeleton.joints[0].limits is None
        assert skeleton.joints[0].limits_source is None
        assert "unknown" in skeleton.summary["limits"]

    def test_an_impossible_range_refuses(self):
        from ai_cad.compiler.kinematics import apply_limits

        with pytest.raises(KinematicsError, match="not a usable range"):
            apply_limits(self._skeleton(), {"joint_1": {"lower": 1.0, "upper": -1.0}}, "src")

    def test_a_non_finite_limit_refuses(self):
        from ai_cad.compiler.kinematics import apply_limits

        with pytest.raises(KinematicsError, match="not a usable range"):
            apply_limits(
                self._skeleton(), {"joint_1": {"lower": float("-inf"), "upper": 1.0}}, "src"
            )

    def test_the_header_states_the_limits_the_body_carries(self, tmp_path):
        # A hardcoded "UNKNOWN" header used to sit above a body full of sourced limits. A file that
        # contradicts itself is worse than one that says less.
        from ai_cad.compiler.kinematics import apply_limits, write_skeleton

        skeleton = apply_limits(
            self._skeleton(), {"joint_1": {"lower": -1.7, "upper": 1.7}}, "a datasheet, page 4"
        )
        text = write_skeleton(skeleton, tmp_path / "robot.joints.yaml").read_text(encoding="utf-8")
        header = text.split("schema:")[0]
        assert "UNKNOWN" not in header
        assert "a datasheet, page 4" in header

    def test_without_limits_the_header_still_says_unknown(self, tmp_path):
        from ai_cad.compiler.kinematics import write_skeleton

        text = write_skeleton(self._skeleton(), tmp_path / "robot.joints.yaml").read_text(
            encoding="utf-8"
        )
        assert "Joint limits are UNKNOWN" in text


class TestServoAxisModel:
    def test_radii_are_reported_so_a_reviewer_can_check_them(self):
        axis = ServoAxis(
            servo_link_id="s",
            direction=(0.0, 0.0, 1.0),
            point=(0.0, 0.0, 0.0),
            radii_m=[0.00853],
            face_count=2,
        )
        assert axis.radii_m == [0.00853]
        assert SERVO_MIN_FACES == 2
