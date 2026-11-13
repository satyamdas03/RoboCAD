"""Tests for the published-model comparison.

The comparison is the demo's central claim, so what it must not do matters as much as what it does:
it must never scale our numbers to theirs, and it must show a body it could not pair rather than
quietly drop it.
"""
from __future__ import annotations

import textwrap

import pytest

from ai_cad.compiler import compare

URDF = textwrap.dedent(
    """\
    <robot name="toy">
      <link name="base_link">
        <inertial><mass value="0.2"/>
          <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/>
        </inertial>
      </link>
      <link name="arm_link">
        <inertial><mass value="0.1"/>
          <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/>
        </inertial>
      </link>
      <joint name="pan" type="revolute">
        <parent link="base_link"/><child link="arm_link"/>
        <origin xyz="0 0 0.1" rpy="0 0 0"/>
        <axis xyz="0 0 1"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
    </robot>
    """
)

# The same robot with no inertia blocks. MuJoCo refuses it, and the point of this fixture is that a
# comparison which cannot read their axes in the world frame says so instead of comparing a local
# axis against a world axis and reporting a right angle that no joint has.
URDF_NO_INERTIA = textwrap.dedent(
    """\
    <robot name="toy">
      <link name="base_link"><inertial><mass value="0.2"/></inertial></link>
      <link name="arm_link"><inertial><mass value="0.1"/></inertial></link>
      <joint name="pan" type="revolute">
        <parent link="base_link"/><child link="arm_link"/>
        <origin xyz="0 0 0.1" rpy="0 0 0"/>
        <axis xyz="0 0 1"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
    </robot>
    """
)

BUNDLE = {
    "total_mass_kg": 0.9,
    "bodies": [
        {"body_id": "base", "mass_kg": 0.6, "parts": 3, "instances": 5, "assumed_density": True},
        {"body_id": "arm", "mass_kg": 0.3, "parts": 2, "instances": 2, "assumed_density": False},
    ],
    "joints": [{"joint_id": "joint_1", "axis_dir": [0.0, 0.0, 1.0], "limits": None}],
}


@pytest.fixture()
def urdf(tmp_path):
    path = tmp_path / "official.urdf"
    path.write_text(URDF, encoding="utf-8")
    return path


class TestReadUrdf:
    def test_reads_masses_and_joint_limits(self, urdf):
        masses, joints = compare.read_urdf(urdf)
        assert masses == {"base_link": 0.2, "arm_link": 0.1}
        assert joints["pan"]["limits"] == {
            "lower": -1.5,
            "upper": 1.5,
            "effort": 3.0,
            "velocity": 2.0,
        }

    def test_an_external_entity_is_not_expanded(self, tmp_path):
        # A URDF is a file that arrived from somewhere else. defusedxml refuses the entity rather
        # than reading the host's filesystem into the report.
        hostile = tmp_path / "hostile.urdf"
        hostile.write_text(
            '<!DOCTYPE robot [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            '<robot name="r"><link name="l">&x;</link></robot>',
            encoding="utf-8",
        )
        with pytest.raises(Exception):
            compare.read_urdf(hostile)


class TestCompare:
    def _run(self, urdf):
        return compare.compare(
            BUNDLE, urdf, {"base": "base_link", "arm": "arm_link"}, {"joint_1": "pan"}
        )

    def test_ours_and_theirs_are_both_printed_unscaled(self, urdf):
        result = self._run(urdf)
        assert result.ours_total_kg == pytest.approx(0.9)
        assert result.theirs_total_kg == pytest.approx(0.3, abs=1e-9)
        assert result.delta_kg == pytest.approx(0.6)
        assert result.delta_percent == pytest.approx(200.0)

    def test_the_difference_is_in_grams_and_percent(self, urdf):
        result = self._run(urdf)
        base = next(b for b in result.bodies if b.ours == "base")
        assert base.delta_kg == pytest.approx(0.4)
        assert base.delta_percent == pytest.approx(200.0)

    def test_a_body_with_no_counterpart_is_printed_not_dropped(self, urdf):
        result = compare.compare(
            BUNDLE, urdf, {"base": "base_link", "arm": None}, {"joint_1": "pan"}
        )
        arm = next(b for b in result.bodies if b.ours == "arm")
        assert arm.theirs is None
        assert arm.theirs_kg is None
        assert arm.delta_kg is None

    def test_an_assumed_density_is_flagged_in_the_notes(self, urdf):
        assert any("ASSUMED" in note for note in self._run(urdf).notes)

    def test_axes_are_compared_both_ways(self, urdf):
        result = self._run(urdf)
        joint = result.joints[0]
        assert joint.axis_angle_deg == pytest.approx(0.0, abs=1e-9)
        assert joint.ours_limits is None
        assert joint.theirs_limits["upper"] == pytest.approx(1.5)

    def test_an_opposite_axis_is_still_the_same_axis(self, urdf):
        flipped = dict(BUNDLE, joints=[{"joint_id": "joint_1", "axis_dir": [0.0, 0.0, -1.0]}])
        result = compare.compare(flipped, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        assert result.joints[0].axis_angle_deg == pytest.approx(0.0, abs=1e-9)

    def test_their_axis_is_read_in_the_world_frame_not_the_local_one(self, urdf):
        # The URDF states the axis in the joint's own frame. Our axes are CAD-world directions. A
        # comparison across the two conventions reports a right angle wherever the frames differ,
        # which is a fact about the file format and not about the robot.
        result = compare.compare(BUNDLE, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        joint = result.joints[0]
        assert joint.theirs_axis_local == pytest.approx([0.0, 0.0, 1.0])
        assert joint.theirs_axis == pytest.approx([0.0, 0.0, 1.0])

    def test_an_axis_that_cannot_be_read_in_world_is_absent_not_guessed(self, tmp_path):
        broken = tmp_path / "no_inertia.urdf"
        broken.write_text(URDF_NO_INERTIA, encoding="utf-8")
        result = compare.compare(BUNDLE, broken, {"base": "base_link"}, {"joint_1": "pan"})
        assert result.joints[0].axis_angle_deg is None
        assert any("world frame" in note for note in result.notes)

    def test_the_markdown_carries_the_rows_and_the_caveats(self, urdf):
        text = compare.render_markdown(self._run(urdf))
        assert "| `base` | base_link |" in text
        assert "+200.0%" in text
        assert "not adjusted to match" in text.lower() or "adjusted" in text.lower()

    def test_the_html_carries_the_same_rows(self, urdf):
        text = compare.render_html(self._run(urdf))
        assert "<code>base</code>" in text
        assert "+200.0%" in text
        assert "Against" in text

    def test_a_fill_fraction_is_derived_only_when_a_volume_is_known(self, urdf):
        with_volume = dict(
            BUNDLE,
            bodies=[
                {"body_id": "base", "mass_kg": 0.6, "solid_volume_m3": 1.0e-3},
                {"body_id": "arm", "mass_kg": 0.3},
            ],
        )
        result = compare.compare(with_volume, urdf, {"base": "base_link", "arm": "arm_link"}, {})
        base = next(b for b in result.bodies if b.ours == "base")
        arm = next(b for b in result.bodies if b.ours == "arm")
        # 0.2 kg of published mass over 1e-3 m3 of solid PLA.
        assert base.implied_fill == pytest.approx(0.2 / (1.0e-3 * 1240.0))
        assert arm.implied_fill is None

    def test_unclassified_volume_is_not_counted_as_printed(self, urdf):
        # The servos on this file are named SOLID and ZK_122, so the name classifier cannot place
        # them. Counting their volume as printed plastic would inflate exactly the column that
        # exists to isolate printed plastic, so it is left out and the note says so.
        with_roles = dict(
            BUNDLE,
            bodies=[
                {
                    "body_id": "base",
                    "mass_kg": 0.6,
                    "role_volume_m3": {"link": 1.0e-4, "unclassified": 9.0e-4},
                }
            ],
        )
        result = compare.compare(with_roles, urdf, {"base": "base_link"}, {})
        base = next(b for b in result.bodies if b.ours == "base")
        assert base.ours_printed_upper_kg == pytest.approx(1.0e-4 * 1240.0)
        assert any("generic names" in note for note in result.notes)

    def test_a_bundle_without_role_volumes_prints_a_dash_not_a_zero(self, urdf):
        result = self._run(urdf)
        base = next(b for b in result.bodies if b.ours == "base")
        assert base.ours_printed_upper_kg is None

    def test_part_and_instance_counts_are_read_under_the_bundle_field_names(self, urdf):
        # bundle.json writes part_count/instance_count. Reading only parts/instances printed 0 parts
        # and 0 instances beside a body that has both.
        bundle = dict(
            BUNDLE,
            bodies=[{"body_id": "base", "mass_kg": 0.6, "part_count": 4, "instance_count": 9}],
        )
        result = compare.compare(bundle, urdf, {"base": "base_link"}, {})
        assert result.bodies[0].ours_parts == 4
        assert result.bodies[0].ours_instances == 9

    def test_the_assumed_density_flag_is_read_under_the_producer_spelling(self, urdf):
        # The fixture above spells the flag the way the report's body rows do, so it could not catch
        # a reader that only knows that spelling. This row comes from the model that writes
        # bundle.json, so the field name under test is the producer's own and cannot drift from it.
        from ai_cad.compiler.twin_bundle import BodyModel

        row = BodyModel(
            body_id="base",
            name="Base",
            mass_kg=0.6,
            com_m=(0.0, 0.0, 0.0),
            inertia_6=(1e-4, 1e-4, 1e-4, 0.0, 0.0, 0.0),
            rests_on_an_assumed_density=True,
        ).model_dump()
        assert "rests_on_an_assumed_density" in row
        assert "assumed_density" not in row
        bundle = {"total_mass_kg": 0.6, "bodies": [row], "joints": []}
        result = compare.compare(bundle, urdf, {"base": "base_link"}, {})
        assert result.bodies[0].assumed_density is True
        assert any("ASSUMED" in note for note in result.notes)

    def test_the_servo_figure_is_read_against_their_total(self, urdf):
        # The note must do the arithmetic from the total and the joints it was given, not carry a
        # sentence typed to fit an earlier run. The text this replaced claimed six 55 g servos
        # outweighed their whole 632 g model, which is false by nearly a factor of two.
        bundle = dict(
            BUNDLE,
            joints=[
                {"joint_id": "j1", "parent_body": "base", "axis_dir": [0, 0, 1]},
                {"joint_id": "j2", "parent_body": "arm", "axis_dir": [0, 0, 1]},
            ],
        )
        result = compare.compare(
            bundle,
            urdf,
            {"base": "base_link", "arm": "arm_link"},
            {},
            actuator_mass_kg=0.055,
            actuator_mass_source="Feetech STS3215 at 55 g",
        )
        note = next(n for n in result.notes if "Feetech STS3215" in n)
        assert "2 actuators" in note
        assert "110 g" in note
        assert "37% of their total" in note
        assert "190 g" in note

    def test_without_a_servo_mass_the_note_refuses_to_read_a_fill_fraction(self, urdf):
        result = self._run(urdf)
        note = next(n for n in result.notes if "official model accounts for" in n)
        assert "cannot say whether" in note
        assert "upper bound" in note

    def test_a_servo_mass_without_a_source_is_refused(self, urdf):
        with pytest.raises(ValueError):
            compare.compare(BUNDLE, urdf, {"base": "base_link"}, {}, actuator_mass_kg=0.055)

    def test_printed_fill_removes_the_servo_that_link_carries(self, urdf):
        bundle = dict(
            BUNDLE,
            bodies=[
                {
                    "body_id": "base",
                    "mass_kg": 0.6,
                    "solid_volume_m3": 2.0e-4,
                    "role_volume_m3": {"link": 2.0e-4},
                }
            ],
            joints=[{"joint_id": "j1", "parent_body": "base", "axis_dir": [0, 0, 1]}],
        )
        result = compare.compare(
            bundle, urdf, {"base": "base_link"}, {}, actuator_mass_kg=0.055,
            actuator_mass_source="a datasheet",
        )
        base = result.bodies[0]
        # (0.2 kg published - 0.055 kg servo) over 2e-4 m3 of solid PLA at 1240 kg/m3.
        assert base.printed_fill == pytest.approx((0.2 - 0.055) / (2.0e-4 * 1240.0))
        assert base.implied_fill == pytest.approx(0.2 / (2.0e-4 * 1240.0))

    def test_a_body_with_no_printed_part_shows_a_dash_not_a_fill(self, urdf):
        bundle = dict(
            BUNDLE,
            bodies=[{"body_id": "base", "mass_kg": 0.6, "role_volume_m3": {"unclassified": 3e-4}}],
            joints=[{"joint_id": "j1", "parent_body": "base", "axis_dir": [0, 0, 1]}],
        )
        result = compare.compare(
            bundle, urdf, {"base": "base_link"}, {}, actuator_mass_kg=0.055,
            actuator_mass_source="a datasheet",
        )
        assert result.bodies[0].printed_fill is None
        assert "—" in compare.render_markdown(result)


# A three-joint arm, so the rigid frame fit has enough anchors to be determined. The joints point
# three different ways on purpose: a datum rotation cannot hide behind axes that all share one line.
URDF_CHAIN = textwrap.dedent(
    """\
    <robot name="chain">
      <link name="base_link"><inertial><mass value="0.2"/>
        <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/></inertial></link>
      <link name="l1"><inertial><mass value="0.15"/>
        <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/></inertial></link>
      <link name="l2"><inertial><mass value="0.1"/>
        <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/></inertial></link>
      <link name="l3"><inertial><mass value="0.05"/>
        <inertia ixx="1e-4" iyy="1e-4" izz="1e-4" ixy="0" ixz="0" iyz="0"/></inertial></link>
      <joint name="j1" type="revolute">
        <parent link="base_link"/><child link="l1"/>
        <origin xyz="0 0 0.05" rpy="0 0 0"/><axis xyz="0 0 1"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
      <joint name="j2" type="revolute">
        <parent link="l1"/><child link="l2"/>
        <origin xyz="0.08 0 0.06" rpy="0 0 0"/><axis xyz="0 1 0"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
      <joint name="j3" type="revolute">
        <parent link="l2"/><child link="l3"/>
        <origin xyz="0.10 0.02 0.04" rpy="0 0 0"/><axis xyz="1 0 0"/>
        <limit lower="-1.5" upper="1.5" effort="3" velocity="2"/>
      </joint>
    </robot>
    """
)


@pytest.fixture()
def chain(tmp_path):
    path = tmp_path / "chain.urdf"
    path.write_text(URDF_CHAIN, encoding="utf-8")
    return path


def _their_joints(urdf_path):
    return compare.world_joint_frames(urdf_path)


def _ours_as_theirs(frames, rotation, translation):
    """A bundle whose joints sit at the given transform of theirs: the same robot, other datum."""
    import numpy as np

    joints = []
    for index, (name, (axis, anchor)) in enumerate(frames.items(), start=1):
        joints.append(
            {
                "joint_id": f"joint_{index}",
                "axis_dir": [float(v) for v in rotation @ np.asarray(axis, float)],
                "axis_point": [
                    float(v) for v in rotation @ np.asarray(anchor, float) + np.asarray(translation, float)
                ],
                "limits": {"lower": -1.0, "upper": 1.0, "effort": 1.0, "velocity": 1.0},
            }
        )
    return dict(BUNDLE, joints=joints)


JOINT_MAP_CHAIN = {"joint_1": "j1", "joint_2": "j2", "joint_3": "j3"}


class TestFrameAlignment:
    def test_our_datum_is_carried_onto_theirs_before_an_angle_is_read(self, chain):
        # Ours is theirs moved to another origin and turned about an axis that shares no line with
        # any joint. Compared raw, that datum would show up as joint error; fitted, it disappears and
        # whatever is left is the robot.
        import numpy as np

        angle = np.radians(37.0)
        axis = np.asarray([1.0, 2.0, 3.0]) / np.linalg.norm([1.0, 2.0, 3.0])
        k = np.asarray([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rotation = np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)
        bundle = _ours_as_theirs(_their_joints(chain), rotation, [0.4, -0.2, 0.9])
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert result.alignment is not None
        assert result.alignment.joints_used == 3
        assert result.alignment.rms_point_m == pytest.approx(0.0, abs=1e-9)
        assert result.alignment.worst_point_m == pytest.approx(0.0, abs=1e-9)
        for joint in result.joints:
            assert joint.ours_axis_in_theirs is not None
            assert joint.axis_angle_deg == pytest.approx(0.0, abs=1e-6)
            assert joint.anchor_delta_m == pytest.approx(0.0, abs=1e-9)

    def test_the_fit_reports_the_transform_it_applied(self, chain):
        import numpy as np

        # Ours was built as ``theirs`` turned a quarter turn about z and then shifted, so the fit --
        # which carries ours onto theirs -- must report the inverse: the opposite quarter turn, and
        # minus that turn applied to the shift.
        rotation = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        shift = np.asarray([0.1, 0.2, 0.3])
        bundle = _ours_as_theirs(_their_joints(chain), rotation, shift)
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        vector = np.asarray(result.alignment.rotation_deg)
        assert np.linalg.norm(vector) == pytest.approx(90.0, abs=1e-6)
        assert vector[2] == pytest.approx(-90.0, abs=1e-6), "the turn must have the opposite sign"
        assert np.asarray(result.alignment.translation_m) == pytest.approx(
            -(rotation.T @ shift), abs=1e-9
        )

    def test_a_joint_that_really_disagrees_still_shows_after_the_fit(self, chain):
        # The fit must not absorb a real error, but a fit over three directions cannot attribute all
        # of one joint's error to that joint either: the least-squares rotation splits it. So the
        # claim tested here is the one that is true -- the joint that is wrong is the one reported as
        # worst, and its error stays clearly visible rather than vanishing into the frame.
        import numpy as np

        frames = _their_joints(chain)
        bundle = _ours_as_theirs(frames, np.eye(3), [0.0, 0.0, 0.0])
        tilt = np.radians(10.0)
        # Their second axis is +Y; ours leans ten degrees off it towards +X.
        bundle["joints"][1]["axis_dir"] = [float(np.sin(tilt)), float(np.cos(tilt)), 0.0]
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        errors = [j.axis_angle_deg for j in result.joints]
        assert errors.index(max(errors)) == 1, "the wrong joint must be the one reported as worst"
        assert errors[1] >= 4.0, f"a ten degree error was reduced to {errors[1]:.2f}"
        assert result.alignment.worst_axis_deg == pytest.approx(errors[1], abs=1e-9)

    def test_the_fit_reports_how_many_rotations_fitted_equally(self, chain):
        # On an arm whose joints share directions, several rotations can fit the axes to the same
        # tolerance. Saying so is the difference between a measurement and a choice presented as one.
        import numpy as np

        bundle = _ours_as_theirs(_their_joints(chain), np.eye(3), [0.0, 0.0, 0.0])
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert result.alignment.rotations_tied >= 1
        if result.alignment.rotations_tied > 1:
            assert any("did not decide the datum" in note for note in result.notes)

    def test_an_axis_that_points_the_other_way_is_not_a_rotation_error(self, chain):
        # A revolute axis has no natural sense. If ours points the opposite way on two joints, the
        # fit must reverse those senses and report ~0 degrees, not put a half turn in the rotation.
        import numpy as np

        bundle = _ours_as_theirs(_their_joints(chain), np.eye(3), [0.0, 0.0, 0.0])
        bundle["joints"][0]["axis_dir"] = [-v for v in bundle["joints"][0]["axis_dir"]]
        bundle["joints"][2]["axis_dir"] = [-v for v in bundle["joints"][2]["axis_dir"]]
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert result.alignment.worst_axis_deg == pytest.approx(0.0, abs=1e-6)
        assert sorted(result.alignment.axis_signs) == [-1, -1, 1]
        assert any("had to be reversed" in note for note in result.notes)

    def test_a_rotation_fitted_to_anchors_is_not_used_to_hide_a_pose_difference(self, chain):
        # Move one joint's anchor far from where theirs sits while leaving every direction correct.
        # The rotation must stay the identity -- the anchors have no vote on it -- and the distance
        # must be reported as an anchor residual rather than spent turning the model.
        import numpy as np

        bundle = _ours_as_theirs(_their_joints(chain), np.eye(3), [0.0, 0.0, 0.0])
        bundle["joints"][2]["axis_point"] = [
            float(bundle["joints"][2]["axis_point"][0] + 0.05),
            float(bundle["joints"][2]["axis_point"][1]),
            float(bundle["joints"][2]["axis_point"][2]),
        ]
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert np.linalg.norm(result.alignment.rotation_deg) < 1e-6
        assert result.alignment.worst_point_m > 0.02

    def test_joint_spacings_need_no_frame_at_all(self, chain):
        # A rigid transform moves both ends of a segment by the same amount, so the spacing survives
        # any datum. This is the joint-geometry claim that does not depend on the fit being right.
        import numpy as np

        angle = np.radians(63.0)
        axis = np.asarray([3.0, -1.0, 2.0]) / np.linalg.norm([3.0, -1.0, 2.0])
        k = np.asarray([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rotation = np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)
        bundle = _ours_as_theirs(_their_joints(chain), rotation, [1.5, -2.0, 0.75])
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert len(result.link_spacings) == 2
        for spacing in result.link_spacings:
            assert spacing.delta_m == pytest.approx(0.0, abs=1e-9)
        text = compare.render_markdown(result)
        assert "no frame needed" in text
        assert "Joint-to-joint spacing" in compare.render_html(result)

    def test_fewer_than_three_placed_joints_prints_no_alignment_and_says_so(self, urdf):
        bundle = dict(
            BUNDLE,
            joints=[
                {"joint_id": "joint_1", "axis_dir": [0.0, 0.0, 1.0], "axis_point": [0.0, 0.0, 0.0]}
            ],
        )
        result = compare.compare(bundle, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        assert result.alignment is None
        assert any("No rigid frame alignment" in note for note in result.notes)
        # No fit means no carried axis, and the angle is read raw across the two datums.
        assert result.joints[0].ours_axis_in_theirs is None
        assert result.joints[0].axis_angle_deg == pytest.approx(0.0, abs=1e-9)

    def test_both_renderings_carry_the_fit_and_its_residuals(self, chain):
        import numpy as np

        bundle = _ours_as_theirs(_their_joints(chain), np.eye(3), [0.1, 0.0, 0.0])
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        markdown = compare.render_markdown(result)
        html = compare.render_html(result)
        assert "## Frame alignment" in markdown
        assert "joints used | 3" in markdown
        assert "anchor delta (mm)" in markdown
        assert "<h3>Frame alignment</h3>" in html
        assert "anchor residual, RMS (mm)" in html

    def test_the_anchor_residual_is_reported_rather_than_blamed_on_the_axes(self, chain):
        # Theirs is read at zero; ours is read in whatever pose the CAD was saved in, and a rigid
        # transform cannot undo a joint angle. The two residuals are therefore separate numbers, and
        # the report says what the anchor one can and cannot mean.
        import numpy as np

        bundle = _ours_as_theirs(_their_joints(chain), np.eye(3), [0.0, 0.0, 0.0])
        result = compare.compare(bundle, chain, {}, JOINT_MAP_CHAIN)
        assert result.alignment.rms_axis_deg == pytest.approx(0.0, abs=1e-6)
        assert any("pose the two files were stored in" in note for note in result.notes)
        assert any("Only the perpendicular part" in note for note in result.notes)


class TestThePrintEstimateColumn:
    """A bundle built with a print model reports an estimate; one built without must not invent it."""

    def _bundle(self, **extra):
        import copy

        bundle = copy.deepcopy(BUNDLE)
        bundle["bodies"][0].update(extra)
        return bundle

    def test_no_estimate_reads_as_a_dash_not_as_a_copy_of_the_bound(self, urdf):
        result = compare.compare(BUNDLE, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        assert result.bodies[0].ours_print_estimate_kg is None
        assert "| — |" in compare.render_markdown(result)

    def test_the_estimate_is_read_from_the_body_row(self, urdf):
        bundle = self._bundle(printed_mass_kg=0.42, bought_in_parts=2)
        result = compare.compare(bundle, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        assert result.bodies[0].ours_print_estimate_kg == pytest.approx(0.42)
        assert result.bodies[0].bought_in_parts == 2
        assert "0.4200" in compare.render_markdown(result)
        assert "0.4200" in compare.render_html(result)

    def test_the_note_says_it_is_a_model_and_names_the_bought_in_parts(self, urdf):
        bundle = self._bundle(printed_mass_kg=0.42, bought_in_parts=2)
        result = compare.compare(bundle, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        joined = " ".join(result.notes)
        assert "model, not a measurement" in joined
        assert "2 bought-in part(s)" in joined
        # without an estimate the note has nothing to explain and is absent
        plain = compare.compare(BUNDLE, urdf, {"base": "base_link"}, {"joint_1": "pan"})
        assert not any("model, not a measurement" in note for note in plain.notes)
