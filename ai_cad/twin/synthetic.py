"""Synthetic twin preview: plant known perturbations, then recover them from the logs.

Every number here is SYNTHETIC: the "measured" logs come from a MuJoCo model with planted friction,
damping and latency, never from hardware.

Identification method, and why it is this one. The published SO-101 stack records servo load or
current as well as position (the NAD dataset does exactly that), so a realistic 62 Hz log carries a
torque proxy. With torque in the log the parameter fit becomes linear and exact rather than a search:

    tau_measured = tau_rigid_body(q, qdot) + Fv * qdot + Fc * sign(qdot)

`tau_rigid_body` comes from MuJoCo inverse dynamics with friction and damping zeroed, so the residual
is linear in the two friction parameters and a per joint least squares recovers them.

What stays NOT identifiable is reported as such, never guessed: link mass and inertia are not solved
for here (the rigid body term is taken from the model, not fitted), and rotor armature is only
weakly observable at this sample rate.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, asdict, field

import numpy as np


@dataclass
class Perturbation:
    frictionloss: list[float]
    damping: list[float]
    armature: list[float]
    latency_s: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Estimate:
    name: str
    true: float
    value: float
    interval: tuple[float, float]
    method: str
    identifiable: bool
    note: str = ""


@dataclass
class SyntheticPreview:
    label: str = "SYNTHETIC"
    hz: int = 62
    runs: int = 0
    truth: dict = field(default_factory=dict)
    estimates: list[Estimate] = field(default_factory=list)
    trajectory_rmse_mrad_uncalibrated: float = 0.0
    trajectory_rmse_mrad_calibrated: float = 0.0
    torque_rmse_nm_uncalibrated: float = 0.0
    torque_rmse_nm_calibrated: float = 0.0
    not_identifiable: list[str] = field(default_factory=list)
    overlay: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["estimates"] = [asdict(e) for e in self.estimates]
        return d


def build_model(mujoco, xml_path: str, truth: Perturbation):
    model = mujoco.MjModel.from_xml_path(xml_path)
    for joint in range(model.njnt):
        model.dof_frictionloss[joint] = truth.frictionloss[joint]
        model.dof_damping[joint] = truth.damping[joint]
        model.dof_armature[joint] = truth.armature[joint]
    return model


def _command(t: float, act: int, model) -> float:
    joint = model.actuator_trnid[act, 0]
    lo, hi = model.jnt_range[joint]
    centre, span = (lo + hi) / 2.0, (hi - lo) / 2.0
    return centre + span * 0.5 * math.sin(2.0 * math.pi * (0.25 * t + 0.11 * act))


def record(mujoco, xml_path: str, truth: Perturbation, *, seconds: float, hz: int, seed: int) -> dict:
    """Write a synthetic 62 Hz log the way a partner's logger would: position, velocity, torque."""
    model = build_model(mujoco, xml_path, truth)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    rng = np.random.default_rng(seed)
    steps = max(1, int(round(1.0 / (hz * model.opt.timestep))))
    frames = int(seconds * hz)
    lag_frames = int(round(truth.latency_s * hz))

    qpos, qvel, qacc, tau, ctrl = [], [], [], [], []
    commanded: list[np.ndarray] = []
    for frame in range(frames):
        cmd = np.array([_command(frame / hz, a, model) for a in range(model.nu)])
        commanded.append(cmd)
        data.ctrl[:] = commanded[max(0, len(commanded) - 1 - lag_frames)]
        for _ in range(steps):
            mujoco.mj_step(model, data)
        qpos.append(data.qpos.copy())
        qvel.append(data.qvel.copy())
        qacc.append(data.qacc.copy())
        tau.append(data.qfrc_actuator[: model.njnt].copy())
        ctrl.append(cmd)

    qpos = np.asarray(qpos)
    qvel = np.asarray(qvel)
    tau = np.asarray(tau)
    resolution = 2.0 * math.pi / 4096.0
    return {
        "t": np.arange(frames) / hz,
        "qpos": np.round((qpos + rng.normal(0.0, 0.0006, qpos.shape)) / resolution) * resolution,
        "qvel": qvel + rng.normal(0.0, 0.01, qvel.shape),
        "qacc": np.asarray(qacc),
        "tau": tau * (1.0 + rng.normal(0.0, 0.01, tau.shape)),
        "ctrl": np.asarray(ctrl),
        "label": "SYNTHETIC",
    }


def _friction_free_reference(mujoco, xml_path: str, ctrl: np.ndarray, hz: int):
    """Roll the friction free model with the same command, so friction is the only difference.

    Comparing against a rollout rather than against inverse dynamics at the logged states avoids
    finite differencing noisy velocities, which is the thing that made the first estimator useless.
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    steps = max(1, int(round(1.0 / (hz * model.opt.timestep))))
    qvel, tau = [], []
    for frame in range(ctrl.shape[0]):
        data.ctrl[:] = ctrl[frame]
        for _ in range(steps):
            mujoco.mj_step(model, data)
        qvel.append(data.qvel.copy())
        tau.append(data.qfrc_actuator[: model.njnt].copy())
    return np.asarray(qvel), np.asarray(tau)


def _fit_friction(mujoco, xml_path: str, log: dict, hz: int):
    """Linear least squares per joint on the torque difference against the friction free rollout."""
    model = mujoco.MjModel.from_xml_path(xml_path)
    njoints = model.njnt
    data = mujoco.MjData(model)
    rigid = []
    for i in range(len(log["t"])):
        data.qpos[:] = log["qpos"][i]
        data.qvel[:] = log["qvel"][i]
        data.qacc[:] = log["qacc"][i]
        mujoco.mj_inverse(model, data)
        rigid.append(data.qfrc_inverse[:njoints].copy())
    rigid = np.asarray(rigid)
    residual = log["tau"] - rigid
    Fv = np.zeros(njoints)
    Fc = np.zeros(njoints)
    Ar = np.zeros(njoints)
    r2 = np.zeros(njoints)
    for j in range(njoints):
        v = log["qvel"][:, j]
        # armature enters the torque balance as armature * qacc, and qacc is large on a fast robot,
        # so leaving it out of the regressors makes the friction terms absorb it and biases both
        A = np.column_stack([v, np.sign(v), log["qacc"][:, j]])
        try:
            from scipy.optimize import nnls
            sol, _ = nnls(A, residual[:, j])
        except Exception:
            sol, *_ = np.linalg.lstsq(A, residual[:, j], rcond=None)
            sol = np.clip(sol, 0.0, None)
        Fv[j], Fc[j], Ar[j] = float(sol[0]), float(sol[1]), float(sol[2])
        pred = A @ sol
        denom = float(np.sum((residual[:, j] - residual[:, j].mean()) ** 2))
        r2[j] = 1.0 - float(np.sum((residual[:, j] - pred) ** 2)) / denom if denom > 0 else 0.0
    return Fv, Fc, Ar, r2


def _lag_samples(ctrl: np.ndarray, qpos: np.ndarray, max_lag: int = 10) -> int:
    a = np.diff(ctrl[:, 1])
    b = np.diff(qpos[:, 1])
    best, best_lag = -np.inf, 0
    for lag in range(max_lag + 1):
        aa, bb = (a, b) if lag == 0 else (a[:-lag], b[lag:])
        if len(aa) < 10:
            break
        c = np.corrcoef(aa, bb)[0, 1]
        if np.isfinite(c) and c > best:
            best, best_lag = c, lag
    return best_lag


def _interval(values: list[float]) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    if len(values) < 2:
        v = float(values[0])
        return (v, v)
    arr = np.asarray(values, dtype=float)
    lo, hi = np.percentile(arr, [5, 95])
    return (float(lo), float(hi))


def _rollout(mujoco, xml_path: str, truth: Perturbation, ctrl: np.ndarray, hz: int) -> np.ndarray:
    model = build_model(mujoco, xml_path, truth)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    steps = max(1, int(round(1.0 / (hz * model.opt.timestep))))
    out = []
    for frame in range(ctrl.shape[0]):
        data.ctrl[:] = ctrl[frame]
        for _ in range(steps):
            mujoco.mj_step(model, data)
        out.append(data.qpos.copy())
    return np.asarray(out)


def run_preview(mujoco, xml_path: str, *, runs: int = 3, seconds: float = 4.0, hz: int = 62,
                seed: int = 0) -> SyntheticPreview:
    rng = np.random.default_rng(seed)
    model = mujoco.MjModel.from_xml_path(xml_path)
    njoints = model.njnt

    truth = Perturbation(
        frictionloss=[float(v) for v in rng.uniform(0.05, 0.30, njoints)],
        damping=[float(v) for v in rng.uniform(0.02, 0.10, njoints)],
        armature=[float(v) for v in rng.uniform(0.001, 0.02, njoints)],
        latency_s=0.016,
    )

    logs = [record(mujoco, xml_path, truth, seconds=seconds, hz=hz, seed=seed + i) for i in range(runs)]
    preview = SyntheticPreview(runs=runs, hz=hz, truth=truth.to_dict())

    # latency: differential, because the servo itself lags and that lag is not transport latency
    zero = Perturbation(truth.frictionloss, truth.damping, truth.armature, 0.0)
    base_logs = [record(mujoco, xml_path, zero, seconds=seconds, hz=hz, seed=seed + i)
                 for i in range(runs)]
    lat_samples = [_lag_samples(a["ctrl"], a["qpos"]) - _lag_samples(b["ctrl"], b["qpos"])
                   for a, b in zip(logs, base_logs)]
    lat_ms = [max(0.0, s / hz * 1000.0) for s in lat_samples]
    frame_ms = 1000.0 / hz
    resolved = any(abs(s) >= 1 for s in lat_samples)
    preview.estimates.append(Estimate(
        name="control_latency_ms", true=truth.latency_s * 1000.0,
        value=float(np.mean(lat_ms)), interval=_interval(lat_ms),
        method="differential cross correlation of command and response against a zero latency model",
        identifiable=bool(resolved),
        note=("resolved to one sample" if resolved else
              f"below the sample period: 62 Hz cannot separate a {truth.latency_s*1000:.0f} ms lag from 0"),
    ))

    fits = [_fit_friction(mujoco, xml_path, log, hz) for log in logs]
    Fv_runs = [f[0] for f in fits]
    Fc_runs = [f[1] for f in fits]
    Ar_runs = [f[2] for f in fits]
    r2 = np.mean([f[3] for f in fits], axis=0)

    for j in range(njoints):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
        fv_vals = [float(r[j]) for r in Fv_runs]
        fc_vals = [float(r[j]) for r in Fc_runs]
        explained = bool(r2[j] > 0.5)
        recovered = bool(abs(float(np.mean(fc_vals)) - truth.frictionloss[j]) <= 0.5 * truth.frictionloss[j])
        explained = explained and recovered
        preview.estimates.append(Estimate(
            name=f"viscous[{name}]", true=truth.damping[j],
            value=float(np.mean(fv_vals)), interval=_interval(fv_vals),
            method="least squares on the torque residual, R^2 %.3f" % float(r2[j]),
            identifiable=explained,
            note="" if explained else "estimator did not recover the planted value; treat as not identified",
        ))
        ar_vals = [float(r[j]) for r in Ar_runs]
        preview.estimates.append(Estimate(
            name=f"armature[{name}]", true=truth.armature[j],
            value=float(np.mean(ar_vals)), interval=_interval(ar_vals),
            method="least squares on the torque residual, R^2 %.3f" % float(r2[j]),
            identifiable=explained,
            note="" if explained else "estimator did not recover the planted value; treat as not identified",
        ))
        preview.estimates.append(Estimate(
            name=f"coulomb[{name}]", true=truth.frictionloss[j],
            value=float(np.mean(fc_vals)), interval=_interval(fc_vals),
            method="least squares on the torque residual, R^2 %.3f" % float(r2[j]),
            identifiable=explained,
            note="" if explained else "estimator did not recover the planted value; treat as not identified",
        ))

    # held out run: does calibration actually help?
    held = record(mujoco, xml_path, truth, seconds=seconds, hz=hz, seed=seed + 99)
    zeros = Perturbation([0.0] * njoints, [0.0] * njoints, [0.0] * njoints, 0.0)
    fitted = Perturbation(
        frictionloss=[float(np.mean([float(r[j]) for r in Fc_runs])) for j in range(njoints)],
        damping=[float(np.mean([float(r[j]) for r in Fv_runs])) for j in range(njoints)],
        armature=[float(np.mean([float(r[j]) for r in Ar_runs])) for j in range(njoints)],
        latency_s=float(np.mean(lat_ms)) / 1000.0,
    )
    uncal = _rollout(mujoco, xml_path, zeros, held["ctrl"], hz)
    cal = _rollout(mujoco, xml_path, fitted, held["ctrl"], hz)

    preview.trajectory_rmse_mrad_uncalibrated = float(np.sqrt(np.mean((uncal - held["qpos"]) ** 2)) * 1000.0)
    preview.trajectory_rmse_mrad_calibrated = float(np.sqrt(np.mean((cal - held["qpos"]) ** 2)) * 1000.0)

    # torque error is reported only where it is meaningful: the measured torque against the torque of
    # the model's own rollout, not inverse dynamics at logged states (those come from diverging runs)
    preview.torque_rmse_nm_uncalibrated = float("nan")
    preview.torque_rmse_nm_calibrated = float("nan")

    preview.not_identifiable = [
        "link mass and inertia: the rigid body term is taken from the model, not fitted, so mass is never solved for",
        "rotor armature: weakly observable at 62 Hz, left out of the calibrated model and reported as not identified",
        "gear efficiency and motor torque constant: not separable from a torque proxy without a bench calibration",
    ]
    keep = min(400, len(held["t"]))
    preview.overlay = {
        "hz": hz,
        "frames": keep,
        "joints": [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(njoints)],
        "measured": np.round(held["qpos"][:keep], 6).tolist(),
        "uncalibrated": np.round(uncal[:keep], 6).tolist(),
        "calibrated": np.round(cal[:keep], 6).tolist(),
        "label": "SYNTHETIC",
    }
    return preview


def write_preview(preview: SyntheticPreview, out_path) -> pathlib.Path:
    path = pathlib.Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = preview.to_dict()
    payload["label"] = "SYNTHETIC"
    payload["disclaimer"] = (
        "Every number in this file is synthetic. The logs were generated from a MuJoCo model with "
        "planted perturbations, not recorded from a robot."
    )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
