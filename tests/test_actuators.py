"""A joint with no actuator is a hole gravity can move and nothing can command.

This file pins the three numbers that turn a joint into a drive -- the effort limit, kp and kv --
and the rule that separates them: the torque is a datasheet figure and travels with its source,
while the gains are assumptions and say so. It also pins the consequence: the effort limit stated
in the file is checked against the torque inverse dynamics actually demands, so a limit too small
to hold its own link fails instead of passing.
"""
from __future__ import annotations

import pytest

from pydantic import ValidationError

from ai_cad.compiler.actuators import (
    DEFAULT_KP,
    DEFAULT_KV,
    ActuatorSpec,
    actuators_for,
)
from ai_cad.compiler.bundle_checks import check_limits_and_effort
from ai_cad.compiler.twin_bundle import ActuatorModel, BodyModel, BundleModel, write_mjcf, write_urdf

STALL = 2.941995
RATED = 0.980665
SOURCE = "Feetech ST3215 12 V variant, docs.waveshare.com/ST3215_Servo"

IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _spec(**kwargs) -> ActuatorSpec:
    base = {"torque_nm": STALL, "torque_kind": "stall", "rated_torque_nm": RATED, "source": SOURCE}
    base.update(kwargs)
    return ActuatorSpec(**base)


def _arm(tmp_path) -> BundleModel:
    """Base plus one arm on a hinge about y, carrying its mass 0.2 m out along x.

    Gravity on that mass makes a moment about the hinge, so the inverse-dynamics demand is a real
    number rather than zero: roughly 1 * 9.81 * 0.2 = 1.96 N*m at the reference pose.
    """
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
    )
    arm = BodyModel(
        body_id="arm",
        name="Arm",
        parent="base",
        joint_id="joint_1",
        origin_m=(0.0, 0.0, 0.1),
        axis_dir=(0.0, 1.0, 0.0),
        limits={"lower": -1.0, "upper": 1.0, "velocity": 2.0},
        mass_kg=1.0,
        com_m=(0.2, 0.0, 0.1),
        inertia_6=(unit, unit, unit, 0.0, 0.0, 0.0),
    )
    return BundleModel(name="arm", bodies=[base, arm], total_mass_kg=2.0)


def _driven(tmp_path, torque_nm: float, **kwargs) -> BundleModel:
    model = _arm(tmp_path)
    model.actuators = [
        ActuatorModel(
            name="joint_1_servo",
            joint="joint_1",
            kp=kwargs.get("kp", DEFAULT_KP),
            kv=kwargs.get("kv", DEFAULT_KV),
            torque_nm=torque_nm,
            torque_kind="stall",
            source=SOURCE,
        )
    ]
    return model


class TestASpecificationCannotLookLikeAMeasurement:
    """The torque is a datasheet number; the gains are not. The type refuses to blur them."""

    def test_a_torque_without_a_source_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="indistinguishable from a guess"):
            ActuatorSpec(torque_nm=STALL, torque_kind="stall")

    def test_a_torque_without_a_kind_is_refused(self) -> None:
        # The same number is a ceiling or a continuous rating depending on the line it was read
        # from, and a reader deciding whether a design has margin needs to know which.
        with pytest.raises(ValidationError, match="cannot be read as either"):
            ActuatorSpec(torque_nm=STALL, source=SOURCE)

    def test_a_kind_without_a_torque_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="there is none to describe"):
            ActuatorSpec(torque_kind="stall", source=SOURCE)

    def test_a_source_without_a_torque_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="never written"):
            ActuatorSpec(source=SOURCE)

    def test_a_rated_torque_above_the_ceiling_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="misread datasheet"):
            ActuatorSpec(torque_nm=1.0, torque_kind="rated", rated_torque_nm=2.0, source=SOURCE)

    def test_an_unstated_spec_is_allowed_and_says_so(self) -> None:
        spec = ActuatorSpec()
        assert spec.is_stated() is False
        assert "no torque stated" in spec.describe()

    def test_the_gains_are_declared_assumptions(self) -> None:
        words = " ".join(_spec().assumptions())
        assert "ASSUMPTION" in words
        assert f"kp = {DEFAULT_KP:g}" in words
        assert f"kv = {DEFAULT_KV:g}" in words


class TestTheFileCarriesTheDrive:
    def _mjcf(self, tmp_path, model) -> str:
        return write_mjcf(model, tmp_path / "model.mjcf").read_text(encoding="utf-8")

    def test_one_position_actuator_per_joint(self, tmp_path) -> None:
        text = self._mjcf(tmp_path, _driven(tmp_path, STALL))
        assert "<actuator>" in text
        assert text.count("<position ") == 1
        assert 'joint="joint_1"' in text
        assert 'kp="20"' in text and 'kv="1"' in text and 'gear="1"' in text

    def test_the_force_limit_is_the_datasheet_figure_and_is_symmetric(self, tmp_path) -> None:
        text = self._mjcf(tmp_path, _driven(tmp_path, STALL))
        assert f'forcerange="{-STALL:.6f} {STALL:.6f}"' in text

    def test_the_command_range_is_the_travel_range(self, tmp_path) -> None:
        # A position servo commanded past the joint limit pushes into it and spends current doing
        # nothing, so the command range and the travel range are the same interval.
        text = self._mjcf(tmp_path, _driven(tmp_path, STALL))
        assert 'ctrlrange="-1.000000000 1.000000000"' in text

    def test_without_a_spec_there_is_no_actuator_block(self, tmp_path) -> None:
        # The old behaviour has to stay reachable: a caller who supplies no torque gets no invented
        # one, and the report says the model cannot be driven.
        assert "<actuator" not in self._mjcf(tmp_path, _arm(tmp_path))

    def test_an_unstated_spec_writes_no_force_range(self, tmp_path) -> None:
        model = _arm(tmp_path)
        model.actuators = [
            ActuatorModel(name="joint_1_servo", joint="joint_1", kp=DEFAULT_KP, kv=DEFAULT_KV)
        ]
        text = self._mjcf(tmp_path, model)
        assert "<actuator>" in text
        assert "forcerange" not in text

    def test_an_actuator_naming_a_missing_joint_is_refused(self, tmp_path) -> None:
        from ai_cad.compiler.twin_bundle import BundleError

        model = _arm(tmp_path)
        model.actuators = [
            ActuatorModel(name="ghost", joint="joint_9", kp=DEFAULT_KP, kv=DEFAULT_KV)
        ]
        with pytest.raises(BundleError, match="nowhere to go"):
            write_mjcf(model, tmp_path / "model.mjcf")


class TestTheUrdfNeverClaimsZeroEffort:
    def test_the_urdf_effort_is_the_actuator_torque(self, tmp_path) -> None:
        text = write_urdf(_driven(tmp_path, STALL), tmp_path / "model.urdf").read_text(encoding="utf-8")
        assert f'effort="{STALL:.6f}"' in text

    def test_no_effort_no_limit_element_rather_than_effort_zero(self, tmp_path) -> None:
        # effort="0" is a claim that the joint can exert nothing, which nobody stated.
        text = write_urdf(_arm(tmp_path), tmp_path / "model.urdf").read_text(encoding="utf-8")
        assert 'effort="0' not in text
        assert "no effort stated" in text


class TestTheEffortHalfCanFail:
    """A limit that is stated but too small is worse than a missing one: it looks checked."""

    def test_a_joint_that_cannot_hold_its_own_link_fails(self, tmp_path) -> None:
        path = write_mjcf(_driven(tmp_path, 1.0), tmp_path / "model.mjcf")
        result = check_limits_and_effort(path, {"joint_1": {"lower": -1.0, "upper": 1.0}}, SOURCE)
        assert result.status == "fail"
        assert "more torque than their actuator states" in result.explanation
        assert result.measured["over_limit"][0]["joint"] == "joint_1"
        assert result.measured["over_limit"][0]["required_nm"] == pytest.approx(1.962, rel=0.02)

    def test_a_joint_that_can_hold_its_own_link_passes_and_reports_the_margin(
        self, tmp_path
    ) -> None:
        path = write_mjcf(_driven(tmp_path, STALL), tmp_path / "model.mjcf")
        result = check_limits_and_effort(path, {"joint_1": {"lower": -1.0, "upper": 1.0}}, SOURCE)
        assert result.status == "pass"
        row = result.measured["torque_demand"]["joint_1_servo"]
        assert row["required_nm"] == pytest.approx(1.962, rel=0.02)
        assert row["ratio"] == pytest.approx(1.962 / STALL, rel=0.02)
        assert "of its" in result.explanation and "a sample of poses" in result.explanation

    def test_over_the_continuous_rating_warns_even_under_the_ceiling(self, tmp_path) -> None:
        # The torque figure is a stall torque: survivable for a moment and not for a duty cycle.
        path = write_mjcf(_driven(tmp_path, 3.0), tmp_path / "model.mjcf")
        result = check_limits_and_effort(
            path,
            {"joint_1": {"lower": -1.0, "upper": 1.0}},
            SOURCE,
            rated_torque_nm=1.5,
        )
        assert result.status == "warn"
        assert "continuous rating" in result.explanation
        assert result.measured["over_continuous"][0]["required_nm"] == pytest.approx(1.962, rel=0.02)

    def test_the_demand_is_measured_not_guessed(self, tmp_path) -> None:
        # Triple the mass and the required torque triples: the number comes out of the model.
        model = _driven(tmp_path, STALL)
        model.bodies[1].mass_kg = 3.0
        path = write_mjcf(model, tmp_path / "model.mjcf")
        result = check_limits_and_effort(path, {"joint_1": {"lower": -1.0, "upper": 1.0}}, SOURCE)
        assert result.measured["torque_demand"]["joint_1_servo"]["required_nm"] == pytest.approx(
            5.886, rel=0.02
        )
        assert result.status == "fail"


class TestNamesAreDerivedNotTyped:
    def test_one_actuator_name_per_joint_in_the_order_given(self) -> None:
        pairs = actuators_for(["joint_1", "joint_2"], _spec())
        assert pairs == [("joint_1_servo", "joint_1"), ("joint_2_servo", "joint_2")]


class TestTheReportOnlyClaimsWhatItWrote:
    def test_no_spec_says_the_model_cannot_be_driven(self) -> None:
        from ai_cad.compiler.compile import _drive_note

        note = _drive_note(None, 6)
        assert "declares no actuators" in note
        assert "limits_and_effort does not pass" in note

    def test_an_unstated_torque_is_reported_rather_than_filled_in(self) -> None:
        from ai_cad.compiler.compile import _drive_note

        note = _drive_note(ActuatorSpec(), 6)
        assert "no force limit" in note
        assert "none was invented" in note

    def test_a_stated_torque_carries_its_kind_source_and_assumptions(self) -> None:
        from ai_cad.compiler.compile import _drive_note

        note = _drive_note(_spec(), 6)
        assert "2.94199 N*m stall" in note
        assert SOURCE in note
        assert "ASSUMPTION" in note


def _box_obj(path, half_m: float) -> None:
    h = half_m
    corners = [
        (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
        (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
    ]
    faces = [
        (1, 2, 3), (1, 3, 4), (5, 8, 7), (5, 7, 6),
        (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3),
        (3, 7, 8), (3, 8, 4), (4, 8, 5), (4, 5, 1),
    ]
    lines = [f"v {x} {y} {z}" for x, y, z in corners]
    lines += [f"f {a} {b} {c}" for a, b, c in faces]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestContactForcesAreNotActuatorLoad:
    """The hulls are a proxy; where two of them overlap the solver pushes them apart.

    Reading that push as actuator load made one joint on the SO-101 read 1,110 N*m against a
    2.94 N*m limit. The measurement therefore runs with contacts disabled, and this test is the
    model that would catch it coming back.
    """

    def _overlapping(self, tmp_path) -> Path:
        (tmp_path / "meshes").mkdir(parents=True, exist_ok=True)
        _box_obj(tmp_path / "meshes" / "base_h0.obj", 0.1)
        _box_obj(tmp_path / "meshes" / "arm_h0.obj", 0.02)
        _box_obj(tmp_path / "meshes" / "tool_h0.obj", 0.02)
        unit = 1.0 / 12.0 * (0.04**2 + 0.04**2)
        base = BodyModel(
            body_id="base", name="Base", parent=None, origin_m=(0.0, 0.0, 0.0), mass_kg=1.0,
            com_m=(0.0, 0.0, 0.0), inertia_6=(unit, unit, unit, 0.0, 0.0, 0.0),
            hull_files=["base_h0.obj"], hull_count=1,
        )
        arm = BodyModel(
            body_id="arm", name="Arm", parent="base", joint_id="joint_1",
            origin_m=(0.0, 0.0, 0.1), axis_dir=(0.0, 1.0, 0.0),
            limits={"lower": -1.0, "upper": 1.0, "velocity": 2.0}, mass_kg=1.0,
            com_m=(0.1, 0.0, 0.1), inertia_6=(unit, unit, unit, 0.0, 0.0, 0.0),
            hull_files=["arm_h0.obj"], hull_count=1,
        )
        # A sibling of the arm, not its child, so MuJoCo's adjacency rule does not excuse the pair.
        tool = BodyModel(
            body_id="tool", name="Tool", parent="base", joint_id=None,
            origin_m=(0.0, 0.0, 0.1), mass_kg=0.1, com_m=(0.16, 0.0, 0.1),
            inertia_6=(unit * 0.1, unit * 0.1, unit * 0.1, 0.0, 0.0, 0.0),
            hull_files=["tool_h0.obj"], hull_count=1,
        )
        model = BundleModel(name="overlap", bodies=[base, arm, tool], total_mass_kg=2.1)
        model.actuators = [
            ActuatorModel(name="joint_1_servo", joint="joint_1", kp=DEFAULT_KP, kv=DEFAULT_KV,
                          torque_nm=STALL, torque_kind="stall", source=SOURCE)
        ]
        return write_mjcf(model, tmp_path / "model.mjcf")

    def test_the_measurement_is_gravity_scale_not_contact_scale(self, tmp_path) -> None:
        path = self._overlapping(tmp_path)
        result = check_limits_and_effort(path, {"joint_1": {"lower": -1.0, "upper": 1.0}}, SOURCE)
        row = result.measured["torque_demand"]["joint_1_servo"]
        assert result.measured["contacts_disabled_for_measurement"] is True
        assert row["required_nm"] < 10.0, row
        assert "contacts disabled" in result.explanation
