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
import math
import pathlib
import time


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


def _replay(mujoco, model, seconds: float, hz: float) -> int:
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
    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running() and (time.time() - t0) < seconds:
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
            viewer.sync()
    return 0


def _hold(mujoco, model, seconds: float) -> int:
    import mujoco.viewer

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

    errors = []
    with mujoco.viewer.launch_passive(model, data) as viewer:
        t0 = time.time()
        while viewer.is_running() and (time.time() - t0) < seconds:
            for a in range(model.nu):
                data.ctrl[a] = target[int(model.actuator_trnid[a, 0])]
            mujoco.mj_step(model, data)
            viewer.sync()
            errors.append(float(abs(data.qpos - target).max()))
        steady = sum(errors[-200:]) / max(1, len(errors[-200:]))

    print(f"hold: commanded an extended pose for {seconds:.0f} s")
    print(f"steady-state joint error {steady*1000:.2f} mrad "
          f"(peak {max(errors)*1000:.2f} mrad)")
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
    if not args.live:
        print("this command is for a live viewer; pass --live. Nothing else is implemented yet.")
        return 0

    import mujoco

    model = _load(path)
    if args.mode == "hold":
        return _hold(mujoco, model, args.seconds)
    return _replay(mujoco, model, args.seconds, args.hz)


if __name__ == "__main__":
    raise SystemExit(main())
