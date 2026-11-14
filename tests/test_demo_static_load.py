"""The static-load diagnostic reports gravity, and nothing else wearing gravity's name.

R1.4 asked for the live hold to be retested and, if it still failed, for the reason to be stated
(gains or limits). Getting that answer needed a number for "what does the pose cost to hold", and the
first two attempts at one both produced confident wrong answers: the actuator forcerange on every
joint, then exactly zero on every joint. A diagnostic that can return the force limit as if it were
the load is worse than no diagnostic, because it reads like a measurement. These tests pin the two
failure modes so they cannot come back quietly.
"""
from __future__ import annotations

import pytest

from robocad.demo import _static_load

mujoco = pytest.importorskip("mujoco")

# MuJoCo is optional in the default tier, so the marker keeps a machine without it collectable.
pytestmark = pytest.mark.mujoco

# A one-link arm: a point mass 0.1 m out laterally on a hinge about +y. At the zero pose gravity pulls
# it down, so the gravity torque needed to hold it is m * g * r = 0.1 * 9.81 * 0.1 = 0.0981 N*m. Only
# the magnitude is pinned: which sign it takes is whichever way the hinge's axis happens to point, and
# that is not a property this diagnostic claims to know.
MASS_KG = 0.1
OFFSET_M = 0.1
GRAVITY = 9.81
EXPECTED_NM = MASS_KG * GRAVITY * OFFSET_M


def _model(force_limit: float, joint_range: str = "-1.6 1.6"):
    xml = f"""
<mujoco model="fixture">
  <compiler angle="radian"/>
  <option gravity="0 0 -{GRAVITY}"/>
  <worldbody>
    <body name="arm" pos="0 0 0">
      <joint name="j1" type="hinge" axis="0 1 0" range="{joint_range}"/>
      <geom name="payload" type="sphere" size="0.005" pos="{OFFSET_M} 0 0" mass="{MASS_KG}"/>
    </body>
  </worldbody>
  <actuator>
    <position name="a1" joint="j1" kp="20" forcerange="{-force_limit} {force_limit}"/>
  </actuator>
</mujoco>
"""
    return mujoco.MjModel.from_xml_string(xml)


def test_the_reported_load_is_gravity_and_not_the_force_limit():
    """The first wrong version returned the forcerange here, because a position servo left at ctrl=0
    asks kp*qpos and saturates at its own limit."""
    model = _model(force_limit=0.5)
    load = _static_load(mujoco, model, [0.0])
    assert load is not None
    assert abs(load[0]) == pytest.approx(EXPECTED_NM, abs=5e-3)
    assert abs(load[0]) != pytest.approx(0.5, abs=1e-2)


@pytest.mark.parametrize("force_limit", [0.5, 2.0, 50.0])
def test_the_load_does_not_scale_with_the_force_limit(force_limit):
    model = _model(force_limit=force_limit)
    load = _static_load(mujoco, model, [0.0])
    assert load is not None
    assert abs(load[0]) == pytest.approx(EXPECTED_NM, abs=5e-3)


def test_a_pose_outside_the_joint_range_still_reports_the_load_not_a_limit_force():
    """Limits are a separate constraint vector; if they leak in, the number becomes the solver's."""
    model = _model(force_limit=2.0, joint_range="-0.01 0.01")
    inside = _static_load(mujoco, model, [0.0])
    outside = _static_load(mujoco, model, [0.8])
    assert inside is not None and outside is not None
    # 0.0981 * cos(0.8) = 0.0683; the point is that it is a small, pose-dependent gravity term and
    # not a limit force of the order of the declared range's stiffness.
    assert abs(outside[0]) == pytest.approx(EXPECTED_NM * 0.6967, abs=5e-3)
    assert abs(outside[0]) < 0.5


def test_the_load_is_zero_with_gravity_switched_off():
    """The number has to move when the only thing it claims to measure is removed."""
    model = _model(force_limit=0.5)
    model.opt.gravity[:] = 0.0
    load = _static_load(mujoco, model, [0.0])
    assert load is not None
    assert abs(load[0]) < 1e-6
