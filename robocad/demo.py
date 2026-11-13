"""`robocad demo` — open a compiled bundle in the MuJoCo viewer for an in-person demo.

Two modes, both read only:

- replay: the same analytic joint-space trajectory the page bakes, so what a viewer sees on screen
  and what the presenter sees in the viewer are the same motion.
- hold: the arm is held at an extended pose under position control and the steady-state error is
  printed, which is the quickest way to show what a mass error does to a real controller.

The bundle is never modified. Nothing here talks to hardware.
"""

from __future__ import annotations

import argparse
import collections
import math
import pathlib
import time

from robocad.joints_cli import _safe

# A headless run steps a fixed count so the numbers are repeatable, but a fixed count on a hostile or
# enormous model is an unbounded amount of work. Both bounds apply: the step cap from --seconds, and a
# wall-clock deadline a run may not outlive.
MAX_SECONDS = 600.0
WALL_CLOCK_FACTOR = 20.0

# The steady state is measured over the last 200 steps, so that is all that is kept. Holding every
# sample made the memory of a long run grow with its length for no gain: nothing read the earlier ones.
WINDOW = 200


def _load(path: pathlib.Path):
    import mujoco

    path = path.resolve()
    cwd = pathlib.Path.cwd()
    try:
        # meshdir is relative to the XML, so resolve from its own directory
        import os

        os.chdir(path.parent)
        return mujoco.MjModel.from_xml_path(path.name)
    finally:
        import os

        os.chdir(cwd)


def _headless_steps(seconds: float) -> int:
    """How many 1 ms model steps a headless run takes, from a validated duration.

    A non-finite or negative ``--seconds`` used to reach ``int(round(...))`` unguarded, and a very
    large one asked for an unbounded amount of work before anything was printed. The clamp is the fix
    and it is applied here rather than at three call sites.
    """
    if not math.isfinite(seconds) or seconds <= 0.0:
        raise SystemExit("--seconds must be a finite number greater than zero")
    return int(round(min(seconds, MAX_SECONDS) * 1000.0))


def _replay(mujoco, model, seconds: float, hz: float, live: bool = True) -> int:
    import mujoco.viewer

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    qpos0 = data.qpos.copy()
    centres, spans = [], []
    for j in range(model.njnt):
        lo, hi = model.jnt_range[j]
        if hi <= lo:  # no limits in the bundle: hold the zero pose and say so
            centres.append(0.0)
            spans.append(0.25)
        else:
            centres.append((lo + hi) / 2.0)
            spans.append((hi - lo) / 2.0)

    has_actuators = model.nu > 0
    print(f"replay: {model.nq} joints, {model.nu} actuators, "
          f"{'driving actuators' if has_actuators else 'posing kinematically (bundle has no actuators)'}")

    t0 = time.time()

    def pose_and_step() -> None:
        t = time.time() - t0
        for j in range(model.njnt):
            w = 2.0 * math.pi * (0.18 + 0.05 * j)
            value = centres[j] + spans[j] * 0.3 * math.sin(w * t)
            if has_actuators:
                for a in range(model.nu):
                    if int(model.actuator_trnid[a, 0]) == j:
                        data.ctrl[a] = value
            else:
                data.qpos[j] = value
        if has_actuators:
            mujoco.mj_step(model, data)
        else:
            mujoco.mj_forward(model, data)

    if not live:
        steps = _headless_steps(seconds)
        # Same bound as hold: a step count derived from a duration still costs per-step work that grows
        # with the model, so the run also may not outlive a wall-clock deadline.
        deadline = time.monotonic() + max(1.0, seconds * WALL_CLOCK_FACTOR)
        ran = 0
        while ran < steps and time.monotonic() < deadline:
            pose_and_step()
            ran += 1
        print(f"replay: {steps} step(s) headless, no window")
        return 0

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running() and (time.time() - t0) < seconds:
            pose_and_step()
            viewer.sync()
    return 0


def _hold(mujoco, model, seconds: float, live: bool = False) -> int:
    if model.nu == 0:
        print("hold mode needs actuators, and this bundle has none. Use replay, or compile a bundle "
              "with actuators.")
        return 2
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    # an extended pose: aim every joint a little away from where it rests
    target = data.qpos.copy()
    for j in range(model.njnt):
        lo, hi = model.jnt_range[j]
        span = (hi - lo) if hi > lo else 0.5
        target[j] = data.qpos[j] + 0.15 * span
    for a in range(model.nu):
        data.ctrl[a] = target[int(model.actuator_trnid[a, 0])]

    # Rolling windows, not full histories: the steady state is read from the last WINDOW steps, and
    # keeping every sample made a long run's memory grow with its length while nothing read them.
    errors: collections.deque[float] = collections.deque(maxlen=WINDOW)
    per_joint = [collections.deque(maxlen=WINDOW) for _ in range(model.nq)]
    peak = 0.0
    saturated = 0

    def step() -> None:
        # The controller is the same with or without a window: the viewer draws the run, it does not
        # drive it. Saturation is counted from the actuator force against its own forcerange, because
        # an actuator that is pinned at its limit is holding the arm with everything it has and the
        # steady error is then a torque shortfall rather than a mass error.
        nonlocal saturated, peak
        for a in range(model.nu):
            data.ctrl[a] = target[int(model.actuator_trnid[a, 0])]
        mujoco.mj_step(model, data)
        worst = float(abs(data.qpos - target).max())
        errors.append(worst)
        peak = max(peak, worst)
        for j in range(model.nq):
            per_joint[j].append(abs(float(data.qpos[j] - target[j])))
        for a in range(model.nu):
            lo, hi = model.actuator_forcerange[a]
            force = abs(float(data.actuator_force[a]))
            limit = max(abs(lo), abs(hi))
            if limit > 0.0 and force >= 0.999 * limit:
                saturated += 1

    if live:
        import mujoco.viewer

        with mujoco.viewer.launch_passive(model, data) as viewer:
            t0 = time.time()
            while viewer.is_running() and (time.time() - t0) < seconds:
                step()
                viewer.sync()
        steps = None
    else:
        steps = _headless_steps(seconds)  # a 1 kHz model step, not wall clock: repeatable
        deadline = time.monotonic() + max(1.0, seconds * WALL_CLOCK_FACTOR)
        ran = 0
        while ran < steps and time.monotonic() < deadline:
            step()
            ran += 1
    steady = sum(errors) / max(1, len(errors))

    print(f"hold: commanded an extended pose for {seconds:.0f} s"
          + ("" if live else f" ({steps} steps, headless)"))
    print(f"steady-state joint error {steady*1000:.2f} mrad "
          f"(peak {peak*1000:.2f} mrad)")
    print("per joint, mean error over the last 200 steps:")
    for j in range(model.nq):
        window = per_joint[j]
        name = _safe(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or f"joint {j}", 64)
        print(f"  {name:24s} {sum(window) / max(1, len(window)) * 1000:8.2f} mrad")
    print(f"actuator saturation: {saturated} step-instances at or above 99.9% of forcerange")
    print("a large steady error at a held pose is what a mass error looks like to a real controller")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="robocad demo")
    parser.add_argument("robot", nargs="?", default="so101")
    parser.add_argument("--bundle", required=True, help="compiled bundle directory or its model.mjcf")
    parser.add_argument("--live", action="store_true", help="open the MuJoCo viewer")
    parser.add_argument("--mode", choices=("replay", "hold"), default="replay")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--hz", type=float, default=100.0)
    args = parser.parse_args(argv)

    path = pathlib.Path(args.bundle)
    if path.is_dir():
        path = path / "model.mjcf"
    if not path.exists():
        print(f"no MJCF at {path}")
        return 2
    # Without a window the run still happens and still prints its numbers. The window draws the run;
    # it is not what produces the measurement, and a demo that could only be measured on a machine
    # with a display could not be measured in CI.
    import mujoco

    model = _load(path)
    if args.mode == "hold":
        return _hold(mujoco, model, args.seconds, live=args.live)
    return _replay(mujoco, model, args.seconds, args.hz, live=args.live)


if __name__ == "__main__":
    raise SystemExit(main())
