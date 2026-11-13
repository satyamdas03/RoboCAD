"""Tests for M2 joint inference.

Most of these build an ``ImportedAssembly`` and a cylinder list by hand. That is deliberate: the
rule under test is the bore/shaft matching and the review contract, neither of which needs a CAD
kernel, and a hand-built case can state its geometry to the micron. One kernel test proves the part
only the kernel can prove — that a hole reads as a bore and a boss as a shaft.

The real SO-101 result is recorded in the M2 notes, not asserted here: it is third-party geometry,
and a test that depends on a 20 MB file nobody can check in would rot.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pydantic", reason="joint inference needs the model layer")

from ai_cad.importers.features import CylinderFace  # noqa: E402
from ai_cad.importers.joints import (  # noqa: E402
    MAX_PAIR_GAP_M,
    JointProposal,
    ProposedJoint,
    diff_proposals,
    group_links,
    infer_joints,
    read_proposal,
    write_proposal,
)
from ai_cad.importers.models import (  # noqa: E402
    ImportedAssembly,
    ImportedInstance,
    ImportedPart,
    PartSignature,
)

IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


# --------------------------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------------------------
def _part(part_id: str, lo, hi) -> ImportedPart:
    size = tuple(h - l for h, l in zip(hi, lo))
    volume = size[0] * size[1] * size[2]
    area = 2.0 * (size[0] * size[1] + size[1] * size[2] + size[0] * size[2])
    return ImportedPart(
        part_id=part_id,
        name=part_id,
        signature=PartSignature(
            volume_m3=volume,
            surface_area_m2=area,
            bbox_min_m=lo,
            bbox_max_m=hi,
            face_count=6,
            face_type_counts={"Plane": 6},
        ),
    )


def _assembly(specs) -> ImportedAssembly:
    """``specs`` is ``[(group_name, part_id, bbox_lo, bbox_hi), ...]``; one instance per spec."""
    parts: dict[str, ImportedPart] = {}
    instances: list[ImportedInstance] = []
    for index, (group, part_id, lo, hi) in enumerate(specs):
        parts.setdefault(part_id, _part(part_id, lo, hi))
        instances.append(
            ImportedInstance(
                instance_id=f"i{index}",
                name=group,
                part_id=part_id,
                transform=IDENTITY,
                assembly_path=("root", group),
            )
        )
    return ImportedAssembly(root_name="root", parts=parts, instances=instances)


def _cyl(instance_id: str, radius: float, point, direction, is_bore: bool) -> CylinderFace:
    return CylinderFace(
        instance_id=instance_id,
        radius_m=radius,
        axis_point=point,
        axis_dir=direction,
        is_bore=is_bore,
        area_m2=1e-4,
    ).normalized()


# Two 20 mm cubes sharing a face at x = 0.02, so the bodies touch.
LEFT = ("arm", "arm", (0.0, 0.0, 0.0), (0.02, 0.02, 0.02))
RIGHT = ("wrist", "wrist", (0.02, 0.0, 0.0), (0.04, 0.02, 0.02))
FAR = ("gripper", "gripper", (0.5, 0.0, 0.0), (0.52, 0.02, 0.02))


def _touching_pair():
    asm = _assembly([LEFT, RIGHT])
    # Coaxial means one shared line, not merely a parallel one: both axes run through
    # (y, z) = (0.01, 0.01), so the only difference between them is where along the line they start.
    cylinders = [
        _cyl("i0", 0.003, (0.01, 0.01, 0.01), (1.0, 0.0, 0.0), is_bore=True),   # hole in arm
        _cyl("i1", 0.003, (0.03, 0.01, 0.01), (-1.0, 0.0, 0.0), is_bore=False),  # boss on wrist
    ]
    return asm, cylinders


# --------------------------------------------------------------------------------------------
# inference
# --------------------------------------------------------------------------------------------
class TestInference:
    def test_a_coaxial_bore_and_shaft_become_one_proposed_joint(self):
        asm, cylinders = _touching_pair()
        proposal = infer_joints(asm, cylinders=cylinders)

        assert len(proposal.joints) == 1
        joint = proposal.joints[0]
        assert joint.evidence.radius_m == pytest.approx(0.003)
        assert joint.evidence.radial_gap_m == pytest.approx(0.0, abs=1e-9)
        assert joint.evidence.axis_offset_m == pytest.approx(0.0, abs=1e-9)
        # The shaft side is the parent, the bore side the child: convention, documented in code.
        assert joint.parent_link == "wrist"
        assert joint.child_link == "arm"
        # The axis direction is reported without depending on which side it came from.
        assert abs(joint.axis_dir[0]) == pytest.approx(1.0)

    def test_a_proposed_joint_is_never_presented_as_verified(self):
        asm, cylinders = _touching_pair()
        joint = infer_joints(asm, cylinders=cylinders).joints[0]
        assert joint.review_required is True
        # Limits are unknown from geometry alone. Writing a guessed range would be inventing a
        # number the machine has not confirmed, so it stays None until a human supplies it.
        assert joint.limits is None
        assert 0.0 < joint.confidence <= 0.95

    def test_axis_direction_does_not_change_the_match(self):
        # The same interface with the boss modelled in the opposite direction must still match.
        _, cylinders = _touching_pair()
        flipped = [
            cylinders[0],
            cylinders[1].model_copy(update={"axis_dir": (1.0, 0.0, 0.0)}),
        ]
        asm, _ = _touching_pair()
        assert len(infer_joints(asm, cylinders=flipped).joints) == 1

    def test_measured_axis_offset_beyond_tolerance_is_not_jointed(self):
        asm, cylinders = _touching_pair()
        shifted = [
            cylinders[0],
            cylinders[1].model_copy(update={"axis_point": (0.03, 0.012, 0.01)}),  # 2 mm off
        ]
        assert infer_joints(asm, cylinders=shifted).joints == []

    def test_a_loose_fit_beyond_the_radial_tolerance_is_not_jointed(self):
        asm, cylinders = _touching_pair()
        loose = [
            cylinders[0],
            cylinders[1].model_copy(update={"radius_m": 0.0036}),  # 0.6 mm clearance
        ]
        assert infer_joints(asm, cylinders=loose).joints == []

    def test_two_bores_or_two_shafts_are_not_a_joint(self):
        asm, cylinders = _touching_pair()
        both_bores = [cylinders[0], cylinders[1].model_copy(update={"is_bore": True})]
        both_shafts = [
            cylinders[0].model_copy(update={"is_bore": False}),
            cylinders[1],
        ]
        assert infer_joints(asm, cylinders=both_bores).joints == []
        assert infer_joints(asm, cylinders=both_shafts).joints == []

    def test_tiny_holes_are_not_treated_as_bearing_seats(self):
        asm, cylinders = _touching_pair()
        tiny = [
            cylinders[0].model_copy(update={"radius_m": 0.001}),
            cylinders[1].model_copy(update={"radius_m": 0.001}),
        ]
        assert infer_joints(asm, cylinders=tiny).joints == []

    def test_a_jointed_pair_is_not_also_listed_as_unresolved(self):
        asm, cylinders = _touching_pair()
        proposal = infer_joints(asm, cylinders=cylinders)
        assert proposal.joints, "fixture should produce a joint"
        assert proposal.unresolved_pairs == []

    def test_bodies_far_apart_are_not_listed_as_unresolved_pairs(self):
        asm, cylinders = _touching_pair()
        far = _assembly([LEFT, RIGHT, FAR])
        cylinders = cylinders + [
            _cyl("i2", 0.003, (0.5, 0.01, 0.0), (0.0, 0.0, 1.0), is_bore=True),
        ]
        proposal = infer_joints(far, cylinders=cylinders)
        listed = {(u["parent_link"], u["child_link"]) for u in proposal.unresolved_pairs}
        for a, b in listed:
            assert not ({a, b} == {"arm", "gripper"} and MAX_PAIR_GAP_M < 0.4)
        # The only pair within reach is wrist <-> gripper, which is far outside the gap.
        assert all("gripper" not in pair for pair in listed)

    def test_missing_interface_between_touching_bodies_is_listed(self):
        asm, _ = _touching_pair()
        proposal = infer_joints(asm, cylinders=[])
        assert len(proposal.unresolved_pairs) == 1
        entry = proposal.unresolved_pairs[0]
        assert {entry["parent_link"], entry["child_link"]} == {"arm", "wrist"}
        assert "reason" in entry and "next_step" in entry

    def test_fastener_groups_are_folded_into_the_nearest_link(self):
        asm = _assembly([LEFT, RIGHT, ("M3 Screw DIN 912", "screw", (0.0, 0.0, 0.0), (0.002, 0.002, 0.002))])
        links = group_links(asm)
        names = {g.name for g in links}
        assert not any("Screw" in n for n in names), names
        host = next(g for g in links if g.name == "arm")
        assert "i2" in host.instance_ids

    def test_link_ids_drop_the_cad_version_suffix_and_stay_unique(self):
        # SO-101 carries seven identical servos under one name and a " v12:1" suffix on every label.
        asm = _assembly(
            [
                ("Base_SO101 v12:1", "base", (0.0, 0.0, 0.0), (0.01, 0.01, 0.01)),
                ("ST3215 Servo v2:1", "servo", (0.02, 0.0, 0.0), (0.03, 0.01, 0.01)),
                ("ST3215 Servo v2:2", "servo2", (0.04, 0.0, 0.0), (0.05, 0.01, 0.01)),
            ]
        )
        ids = [g.link_id for g in group_links(asm)]
        assert ids == ["base_so101", "st3215_servo", "st3215_servo_2"], ids
        assert [g.name for g in group_links(asm)] == ["Base_SO101", "ST3215 Servo", "ST3215 Servo"]

    def test_summary_states_the_tolerances_that_produced_it(self):
        asm, cylinders = _touching_pair()
        summary = infer_joints(asm, cylinders=cylinders).summary
        assert summary["joints"] == 1
        assert summary["cylinders_extracted"] >= 2
        assert set(summary["tolerances"]) == {
            "min_radius_m", "radial_match_m", "axis_offset_m", "parallel_dot", "max_pair_gap_m"
        }


class TestCycles:
    def _joint(self, joint_id: str, parent: str, child: str, confidence: float) -> ProposedJoint:
        return ProposedJoint(
            joint_id=joint_id,
            parent_link=parent,
            child_link=child,
            axis_point=(0.0, 0.0, 0.0),
            axis_dir=(0.0, 0.0, 1.0),
            evidence={
                "radius_m": 0.003,
                "radial_gap_m": 0.0,
                "axis_offset_m": 0.0,
                "face_pairs": 4,
            },
            confidence=confidence,
        )

    def test_a_loop_keeps_the_stronger_joints_and_reports_the_one_it_dropped(self):
        from ai_cad.importers.joints import _spanning_tree

        kept, dropped = _spanning_tree(
            [
                self._joint("joint_01", "a", "b", 0.9),
                self._joint("joint_02", "b", "c", 0.8),
                self._joint("joint_03", "a", "c", 0.4),
            ]
        )
        assert [j.joint_id for j in kept] == ["joint_01", "joint_02"]
        assert [j.joint_id for j in dropped] == ["joint_03"]


# --------------------------------------------------------------------------------------------
# guards: a CAD file is untrusted input
# --------------------------------------------------------------------------------------------
class TestGuards:
    def test_inference_refuses_to_run_past_its_deadline(self):
        from ai_cad.importers.joints import JointInferenceError

        asm, cylinders = _touching_pair()
        with pytest.raises(JointInferenceError, match="budget"):
            infer_joints(asm, cylinders=cylinders, budget_s=-1.0)

    def test_pairing_cap_is_reported_not_hidden(self, monkeypatch):
        import ai_cad.importers.joints as mod

        asm, cylinders = _touching_pair()
        monkeypatch.setattr(mod, "MAX_PAIRING_BODIES", 1)
        proposal = mod.infer_joints(asm, cylinders=cylinders)
        assert any("pairing cap" in w for w in proposal.warnings)

    def test_unresolved_pairs_are_capped_with_a_warning(self, monkeypatch):
        import ai_cad.importers.joints as mod

        asm, _ = _touching_pair()
        monkeypatch.setattr(mod, "MAX_UNRESOLVED_PAIRS", 0)
        proposal = mod.infer_joints(asm, cylinders=[])
        assert proposal.unresolved_pairs == []
        assert any("not listed" in w for w in proposal.warnings)

    def test_link_bbox_is_computed_from_rotated_corners(self):
        # Adding translation to a part's local box is only right for an unrotated placement. This
        # is the box the gap test uses to decide whether a pair is examined at all, so an
        # under-estimate would silently drop real joints.
        import math

        c, s = math.cos(math.pi / 2), math.sin(math.pi / 2)
        rotated = (
            c, -s, 0.0, 0.0,
            s, c, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        asm = ImportedAssembly(
            parts={"p": _part("p", (0.0, 0.0, 0.0), (0.04, 0.01, 0.01))},
            instances=[
                ImportedInstance(
                    instance_id="i0",
                    name="arm",
                    part_id="p",
                    transform=rotated,
                    assembly_path=("root", "arm"),
                )
            ],
        )
        group = group_links(asm)[0]
        # A 0.04 x 0.01 x 0.01 box turned 90 degrees about Z spans 0.01 in x and 0.04 in y.
        assert group.bbox_min_m == pytest.approx((-0.01, 0.0, 0.0), abs=1e-9)
        assert group.bbox_max_m == pytest.approx((0.0, 0.04, 0.01), abs=1e-9)

    def test_cylinder_cap_is_announced_and_marks_the_proposal_partial(self, monkeypatch):
        import ai_cad.importers.joints as mod

        asm, cylinders = _touching_pair()
        monkeypatch.setattr(mod, "MAX_CYLINDERS_PER_LINK", 0)
        proposal = mod.infer_joints(asm, cylinders=cylinders)
        assert proposal.partial is True
        assert any("largest faces only" in w for w in proposal.warnings)

    def test_a_complete_run_is_not_marked_partial(self):
        asm, cylinders = _touching_pair()
        assert infer_joints(asm, cylinders=cylinders).partial is False

    def test_radius_index_does_not_miss_a_match_across_a_bucket_boundary(self):
        # The radius index exists so the pairing loop is not the product of two face counts. The
        # risk it introduces is a match hidden by which bucket a radius falls into, so this test
        # sits exactly on a boundary: 3.0 mm and 3.5 mm are in adjacent buckets and 0.5 mm apart,
        # which is the largest gap the rule accepts.
        asm, _ = _touching_pair()
        cylinders = [
            _cyl("i0", 0.0030, (0.01, 0.01, 0.01), (1.0, 0.0, 0.0), is_bore=True),
            _cyl("i1", 0.0035, (0.03, 0.01, 0.01), (-1.0, 0.0, 0.0), is_bore=False),
        ]
        joints = infer_joints(asm, cylinders=cylinders).joints
        assert len(joints) == 1
        assert joints[0].evidence.radius_m == pytest.approx(0.00325)

    def test_the_face_pair_comparison_checks_its_deadline(self):
        # The body-pair loop checks the deadline once per body pair, which is not enough: one pair
        # of dense bodies can run for a long time inside the face comparison. The cap on faces per
        # body is generous enough that this must be bounded on its own.
        import time as _time

        import ai_cad.importers.joints as mod

        left = [_cyl("i0", 0.003, (0.01, 0.01, 0.01), (1.0, 0.0, 0.0), is_bore=True)] * 600
        right = [_cyl("i1", 0.003, (0.03, 0.01, 0.01), (-1.0, 0.0, 0.0), is_bore=False)] * 600
        with pytest.raises(mod.JointInferenceError, match="budget"):
            mod._best_interface(left, right, deadline=_time.monotonic() - 1.0, budget_s=1.0)

    def test_bodies_that_do_not_touch_are_never_matched(self):
        # 10 cm apart with geometrically coaxial faces. No bearing spans that gap, and the bbox
        # test that rejects it runs before the cylinder comparison that would accept it.
        asm = _assembly(
            [
                LEFT,
                ("wrist", "wrist", (0.1, 0.0, 0.0), (0.12, 0.02, 0.02)),
            ]
        )
        cylinders = [
            _cyl("i0", 0.003, (0.01, 0.01, 0.01), (1.0, 0.0, 0.0), is_bore=True),
            _cyl("i1", 0.003, (0.11, 0.01, 0.01), (-1.0, 0.0, 0.0), is_bore=False),
        ]
        assert infer_joints(asm, cylinders=cylinders).joints == []

    def test_cylinder_extraction_refuses_a_part_with_too_many_faces(self):
        pytest.importorskip("OCP.BRepPrimAPI")
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        from ai_cad.importers.features import FeatureExtractionError, extract_cylinders

        shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
        asm = _assembly([LEFT])
        asm.parts["arm"] = asm.parts["arm"].model_copy(update={"shape": shape})
        with pytest.raises(FeatureExtractionError, match="faces"):
            extract_cylinders(asm, max_faces_per_shape=2)

    def test_cylinder_extraction_refuses_past_its_deadline(self):
        pytest.importorskip("OCP.BRepPrimAPI")
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        from ai_cad.importers.features import FeatureExtractionError, extract_cylinders

        shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
        asm = _assembly([LEFT])
        asm.parts["arm"] = asm.parts["arm"].model_copy(update={"shape": shape})
        with pytest.raises(FeatureExtractionError, match="budget"):
            extract_cylinders(asm, budget_s=-1.0)

    def test_cylinder_output_is_capped_rather_than_truncated(self):
        pytest.importorskip("OCP.BRepPrimAPI")
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        from ai_cad.importers.features import FeatureExtractionError, extract_cylinders

        shape = BRepPrimAPI_MakeCylinder(3.0, 10.0).Shape()
        asm = _assembly([LEFT])
        asm.parts["arm"] = asm.parts["arm"].model_copy(update={"shape": shape})
        with pytest.raises(FeatureExtractionError, match="cylinder faces"):
            extract_cylinders(asm, max_cylinders=0)

    def test_a_part_is_read_once_however_often_it_is_placed(self):
        pytest.importorskip("OCP.BRepPrimAPI")
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        from ai_cad.importers.features import extract_cylinders

        shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
        one = _assembly([LEFT])
        one.parts["arm"] = one.parts["arm"].model_copy(update={"shape": shape})

        two = _assembly([LEFT, ("arm2", "arm", (0.0, 0.0, 0.0), (0.02, 0.02, 0.02))])
        two.parts["arm"] = two.parts["arm"].model_copy(update={"shape": shape})

        calls = []
        import ai_cad.importers.features as mod

        original = mod._part_cylinders

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        mod._part_cylinders = counting
        try:
            extract_cylinders(one, budget_s=None)
            assert len(calls) == 1
            calls.clear()
            extract_cylinders(two, budget_s=None)
            assert len(calls) == 1, "the same part must be interrogated once, not once per placement"
        finally:
            mod._part_cylinders = original


# --------------------------------------------------------------------------------------------
# the file a reviewer reads
# --------------------------------------------------------------------------------------------
class TestProposalFile:
    def test_round_trip_preserves_the_proposal_and_its_review_flag(self, tmp_path):
        asm, cylinders = _touching_pair()
        proposal = infer_joints(asm, cylinders=cylinders)
        out = write_proposal(proposal, tmp_path / "robot.joints.proposed.yaml")

        text = out.read_text(encoding="utf-8")
        assert text.startswith("# RoboCAD joint proposal")
        assert "PROPOSAL" in text
        assert "Review before use" in text
        assert "schema: robocad.joints/1" in text

        back = read_proposal(out)
        assert isinstance(back, JointProposal)
        assert back.status == "proposed"
        assert back.schema_version == "robocad.joints/1"
        assert [j.joint_id for j in back.joints] == [j.joint_id for j in proposal.joints]
        assert back.joints[0].review_required is True
        assert back.joints[0].limits is None

    def test_a_third_party_notice_is_carried_in_the_file(self, tmp_path):
        asm, cylinders = _touching_pair()
        proposal = infer_joints(asm, cylinders=cylinders)
        out = write_proposal(
            proposal,
            tmp_path / "p.yaml",
            notice="Robot CAD: Example Robotics, Apache-2.0\nChanges: metadata inferred only",
        )
        text = out.read_text(encoding="utf-8")
        assert "# Robot CAD: Example Robotics, Apache-2.0" in text
        assert "# Changes: metadata inferred only" in text
        # The notice must stay comments: a reader must still be able to parse the file.
        assert read_proposal(out).status == "proposed"

    def test_diff_reports_a_moved_axis(self):
        asm, cylinders = _touching_pair()
        before = infer_joints(asm, cylinders=cylinders)
        # Move the bore line 0.4 mm: still inside the match tolerance, so the same joint is found
        # and the difference is in where its axis sits.
        moved = [
            cylinders[0].model_copy(update={"axis_point": (0.01, 0.0104, 0.01)}),
            cylinders[1],
        ]
        after = infer_joints(asm, cylinders=moved)

        changes = diff_proposals(before, after)
        assert changes["added"] == [] and changes["removed"] == []
        assert changes["changed"][0]["joint_id"] == before.joints[0].joint_id
        assert "axis_position" in changes["changed"][0]["fields"]

    def test_a_point_that_slides_along_the_same_axis_is_not_a_moved_axis(self):
        # The recorded point is chosen for readability (it is projected from the link bounding
        # boxes), so it can slide along the axis without the axis moving. Reporting that as a moved
        # joint would make the revision diff cry wolf on every grouping change.
        asm, cylinders = _touching_pair()
        before = infer_joints(asm, cylinders=cylinders)
        joint = before.joints[0]
        slid_point = tuple(joint.axis_point[i] + 0.05 * joint.axis_dir[i] for i in range(3))
        after = before.model_copy(
            update={"joints": [joint.model_copy(update={"axis_point": slid_point})]}
        )
        assert diff_proposals(before, after)["changed"] == []


# --------------------------------------------------------------------------------------------
# the CLI a reviewer actually runs
# --------------------------------------------------------------------------------------------
class TestCli:
    def test_diff_prints_nothing_to_change_for_identical_proposals(self, tmp_path, capsys):
        from robocad.joints_cli import main as cli_main

        asm, cylinders = _touching_pair()
        path = write_proposal(infer_joints(asm, cylinders=cylinders), tmp_path / "p.yaml")
        assert cli_main(["diff", str(path), str(path)]) == 0
        assert "no joint changes" in capsys.readouterr().out

    def test_diff_names_the_joint_that_moved(self, tmp_path, capsys):
        from robocad.joints_cli import main as cli_main

        asm, cylinders = _touching_pair()
        before = write_proposal(infer_joints(asm, cylinders=cylinders), tmp_path / "before.yaml")
        moved = [
            cylinders[0].model_copy(update={"axis_point": (0.01, 0.0104, 0.01)}),
            cylinders[1],
        ]
        after = write_proposal(infer_joints(asm, cylinders=moved), tmp_path / "after.yaml")

        assert cli_main(["diff", str(before), str(after)]) == 0
        out = capsys.readouterr().out
        assert "axis_position" in out
        assert "axis moved 0.40 mm" in out

    def test_a_missing_file_is_an_error_not_a_traceback(self, tmp_path, capsys):
        from robocad.joints_cli import main as cli_main

        assert cli_main(["diff", str(tmp_path / "nope.yaml"), str(tmp_path / "nope2.yaml")]) == 2
        assert "no such file" in capsys.readouterr().err

    def test_propose_reports_a_bad_step_file_without_crashing(self, tmp_path, capsys):
        from robocad.joints_cli import main as cli_main

        junk = tmp_path / "junk.step"
        junk.write_bytes(b"not a step file\n" * 4)
        assert cli_main(["propose", str(junk)]) == 2
        assert "cannot import" in capsys.readouterr().err

    def test_control_characters_from_a_yaml_are_escaped_on_the_terminal(self, tmp_path, capsys):
        # A shared proposal can carry ESC sequences in a link name. Printing them raw would let the
        # file repaint the reviewer's terminal; the file keeps the bytes, the terminal does not.
        from robocad.joints_cli import main as cli_main

        asm, cylinders = _touching_pair()
        before = infer_joints(asm, cylinders=cylinders)
        after = before.model_copy(deep=True)
        after.joints[0].parent_link = "\x1b[2J\x1b[31mEVIL"
        before_path = write_proposal(before, tmp_path / "before.yaml")
        after_path = write_proposal(after, tmp_path / "after.yaml")

        assert cli_main(["diff", str(before_path), str(after_path)]) == 0
        out = capsys.readouterr().out
        assert "\x1b" not in out
        assert "?[2J?[31mEVIL" in out

    def test_a_parser_error_quoting_the_file_is_also_escaped(self, tmp_path, capsys):
        # The YAML parser quotes the offending content in its error message, and that content came
        # from the file. The error path needs the same escape as the success path.
        from robocad.joints_cli import main as cli_main

        bad = tmp_path / "bad.yaml"
        bad.write_text("schema: robocad.joints/1\n\x1b[2Jbogus: [unclosed\n", encoding="utf-8")
        assert cli_main(["diff", str(bad), str(bad)]) == 2
        err = capsys.readouterr().err
        assert "\x1b" not in err
        assert "cannot read proposal" in err


# --------------------------------------------------------------------------------------------
# kernel: the one thing only the CAD kernel can prove
# --------------------------------------------------------------------------------------------
class TestBoreVersusShaft:
    def test_a_hole_reads_as_a_bore_and_a_boss_reads_as_a_shaft(self):
        pytest.importorskip("OCP.BRepPrimAPI")
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        from ai_cad.importers.features import extract_cylinders

        plate = BRepPrimAPI_MakeBox(20.0, 20.0, 10.0).Shape()
        hole = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(10.0, 10.0, -1.0), gp_Dir(0, 0, 1)), 3.0, 12.0
        ).Shape()
        bored = BRepAlgoAPI_Cut(plate, hole).Shape()

        boss = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(10.0, 10.0, 10.0), gp_Dir(0, 0, 1)), 3.0, 8.0
        ).Shape()

        def as_assembly(shape, instance_id):
            return ImportedAssembly(
                parts={
                    "p": ImportedPart(
                        part_id="p",
                        name="p",
                        signature=_part("p", (0.0, 0.0, 0.0), (0.02, 0.02, 0.02)).signature,
                        shape=shape,
                    )
                },
                instances=[
                    ImportedInstance(
                        instance_id=instance_id,
                        name=instance_id,
                        part_id="p",
                        transform=IDENTITY,
                        assembly_path=("root", instance_id),
                    )
                ],
            )

        bores = [
            c for c in extract_cylinders(as_assembly(bored, "plate")) if c.radius_m > 2.9e-3
        ]
        assert bores, "no cylinder found in the bored plate"
        # The hole's wall faces into the void, which is what makes it a bore.
        assert all(c.is_bore for c in bores), [(c.radius_m, c.is_bore) for c in bores]

        shafts = [
            c for c in extract_cylinders(as_assembly(boss, "boss")) if c.radius_m > 2.9e-3
        ]
        assert shafts, "no cylinder found on the boss"
        assert not any(c.is_bore for c in shafts), [(c.radius_m, c.is_bore) for c in shafts]
