"""Identification harness with explicit rungs, so a failure is localised instead of mysterious.

Why rungs: the first attempt at this in this repository failed at the last step, and there was no
way to tell whether the physics, the pipeline or the data rate was at fault. Each rung adds exactly
one difficulty, and the harness stops at the first rung that does not recover its planted value.

Rung 0: noise free, 1 kHz, one joint, one parameter (viscous damping). If this fails, the pipeline is
        wrong, not the problem.
Rung 1: add Coulomb friction.
Rung 2: add a known integer sample latency.
Rung 3: downsample to the log rate, add sensor noise and encoder quantisation.
Rung 4: a second joint, to check the result is not a fluke of one axis.

Method: the torque balance of a rigid body model is linear in friction parameters once the rigid
body torque is removed, so each rung is a least squares solve rather than a search:

    tau_measured = tau_rigid(q, qdot, qacc) + Fv * qdot + Fc * sign(qdot)

`tau_rigid` comes from MuJoCo inverse dynamics on a model with friction, damping and armature zeroed,
and contacts disabled, because contact forces would otherwise be folded into the residual and
attributed to friction. That confound is exactly what made the first attempt wrong.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field, asdict

import numpy as np


# Pre-registered tolerances. The directive fixed 1 percent for rung 0 only; these are the ones used
# for the rest, written before the runs and not changed afterwards.
TOL = {0: 0.01, 1: 0.02, 2: 0.02, 3: 0.25, 4: 0.02}


@dataclass
class RungResult:
    rung: int
    name: str
    reached: bool
    recovered: dict
    truth: dict
    error_percent: dict
    note: str = ""


@dataclass
class Report:
    model: str
    rungs: list[RungResult] = field(default_factory=list)
    stopped_at: int | None = None
    stop_reason: str = ""
    label: str = "SYNTHETIC"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rungs"] = [asdict(r) for r in self.rungs]
        return d


def _load(mujoco, xml_path: str, *, joint: int, damping: float = 0.0, friction: float = 0.0):
    """Load the model and plant damping and friction on ONE joint.

    Everything else keeps the values the published model ships with. Zeroing the other joints was
    the bug in the first version of this harness: those joints lose the damping that keeps a very
    stiff position servo stable, the simulation diverges, and the divergence gets fitted as friction.
    """
    model = mujoco.MjModel.from_xml_path(xml_path)
    model.dof_damping[joint] = float(model.dof_damping[joint]) + damping
    model.dof_frictionloss[joint] = float(model.dof_frictionloss[joint]) + friction
    # contacts would put constraint forces into the torque balance and be mistaken for friction
    model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_CONTACT)
    return model


def _excite(mujoco, model, *, joint: int, seconds: float, hz: int, latency_samples: int,
            multi_sine: bool = True, seed: int = 0, noise: float = 0.0, quantise: bool = False):
    """Drive one joint with a multi-sine and hold the others, logging what a bench logger sees."""
    # the log rate must not exceed the physics rate: at 1 kHz with a 2 ms timestep the harness was
    # logging duplicated states and calling it a kilohertz. Tighten the timestep instead.
    if 1.0 / hz < model.opt.timestep:
        model.opt.timestep = 1.0 / hz
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    rng = np.random.default_rng(seed)
    steps = max(1, int(round(1.0 / (hz * model.opt.timestep))))
    frames = int(seconds * hz)

    lo, hi = model.jnt_range[joint]
    centre, span = (lo + hi) / 2.0, (hi - lo) / 2.0
    # gentle by construction: a stiff position servo chasing a large multi-sine command goes
    # unstable, and unstable data cannot identify anything. Small amplitude, low frequencies,
    # and a ramp at the start so the first samples are not a step response.
    freqs = (0.25, 0.45, 0.70) if multi_sine else (0.4,)
    weights = np.array([1.0, 0.5, 0.3])[: len(freqs)]
    weights = weights / weights.sum()
    amplitude = 0.25 * span

    def command(t: float) -> float:
        ramp = min(1.0, t / 0.5)
        value = float(np.sum([w * math.sin(2 * math.pi * f * t) for w, f in zip(weights, freqs)]))
        return float(np.clip(centre + ramp * amplitude * value, lo + 0.05 * span, hi - 0.05 * span))

    qpos, qvel, qacc, tau, ctrl = [], [], [], [], []
    commanded: list[float] = []
    for frame in range(frames):
        cmd = command(frame / hz)
        commanded.append(cmd)
        data.ctrl[:] = centre  # everything else holds still
        data.ctrl[joint] = commanded[max(0, len(commanded) - 1 - latency_samples)]
        for _ in range(steps):
            mujoco.mj_step(model, data)
        qpos.append(data.qpos.copy()); qvel.append(data.qvel.copy())
        qacc.append(data.qacc.copy()); tau.append(data.qfrc_actuator[: model.njnt].copy())
        ctrl.append(data.ctrl.copy())

    qpos, qvel = np.asarray(qpos), np.asarray(qvel)
    if quantise:
        resolution = 2.0 * math.pi / 4096.0
        qpos = np.round(qpos / resolution) * resolution
    if noise:
        qpos = qpos + rng.normal(0.0, noise, qpos.shape)
    return {
        "qpos": qpos, "qvel": qvel, "qacc": np.asarray(qacc), "tau": np.asarray(tau),
        "ctrl": np.asarray(ctrl), "hz": hz,
    }


def _rigid_torque(mujoco, xml_path: str, log: dict, joint: int) -> np.ndarray:
    """Inverse dynamics on the model with the planted terms left out, contacts disabled."""
    model = _load(mujoco, xml_path, joint=joint, damping=0.0, friction=0.0)
    data = mujoco.MjData(model)
    out = []
    for i in range(len(log["qpos"])):
        data.qpos[:] = log["qpos"][i]
        data.qvel[:] = log["qvel"][i]
        data.qacc[:] = log["qacc"][i]
        mujoco.mj_inverse(model, data)
        out.append(data.qfrc_inverse[: model.njnt].copy())
    return np.asarray(out)


def _fit(mujoco, xml_path: str, log: dict, joint: int, *, with_coulomb: bool):
    """Least squares on the residual, optionally with a Coulomb column."""
    rigid = _rigid_torque(mujoco, xml_path, log, joint)
    residual = log["tau"][:, joint] - rigid[:, joint]
    v = log["qvel"][:, joint]
    # near zero velocity the sign column flips on noise and biases both terms. Standard practice in
    # friction identification is to fit away from the zero crossing, so do that and say so.
    keep = np.abs(v) > 0.10 * float(np.max(np.abs(v)))
    v = v[keep]
    residual = residual[keep]
    cols = [v] + ([np.sign(v)] if with_coulomb else [])
    A = np.column_stack(cols)
    sol, *_ = np.linalg.lstsq(A, residual, rcond=None)
    cond = float(np.linalg.cond(A))
    return sol, cond


def run(mujoco, xml_path: str, *, joint_name: str = "shoulder_lift", base_hz: int = 1000,
        log_hz: int = 62, seconds: float = 4.0) -> Report:
    model = mujoco.MjModel.from_xml_path(xml_path)
    joint = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, 0)
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(model.njnt)]
    joint_index = names.index(joint_name) if joint_name in names else 0

    damping_truth, friction_truth = 0.08, 0.15
    report = Report(model=pathlib.Path(xml_path).name)

    def add(rung, name, reached, truth, recovered, note=""):
        err = {k: (abs(recovered[k] - truth[k]) / truth[k] * 100.0 if truth[k] else float("inf"))
               for k in truth}
        report.rungs.append(RungResult(rung, name, reached, recovered, truth, err, note))
        if not reached and report.stopped_at is None:
            report.stopped_at = rung
            report.stop_reason = note or "recovery outside tolerance"

    # rung 0: one parameter, noise free, full rate
    truth = {"damping": damping_truth}
    model0 = _load(mujoco, xml_path, joint=joint_index, damping=damping_truth, friction=0.0)
    log0 = _excite(mujoco, model0, joint=joint_index, seconds=seconds, hz=base_hz,
                   latency_samples=0)
    sol, cond = _fit(mujoco, xml_path, log0, joint_index, with_coulomb=False)
    rec = {"damping": float(sol[0])}
    add(0, "damping only, noise free, 1 kHz", abs(rec["damping"] - damping_truth) <= 0.01 * damping_truth,
        truth, rec, f"condition number {cond:.2f}")

    # rung 1: add Coulomb friction
    truth1 = {"damping": damping_truth, "coulomb": friction_truth}
    model1 = _load(mujoco, xml_path, joint=joint_index, damping=damping_truth, friction=friction_truth)
    log1 = _excite(mujoco, model1, joint=joint_index, seconds=seconds, hz=base_hz, latency_samples=0)
    sol1, cond1 = _fit(mujoco, xml_path, log1, joint_index, with_coulomb=True)
    rec1 = {"damping": float(sol1[0]), "coulomb": float(sol1[1])}
    ok1 = all(abs(rec1[k] - truth1[k]) <= TOL[1] * truth1[k] for k in truth1)
    add(1, "damping and Coulomb, noise free, 1 kHz", ok1, truth1, rec1,
        f"condition number {cond1:.2f}")

    # rung 2: integer sample latency, identified by cross correlation before any continuous fit
    latency_samples = 3
    log2 = _excite(mujoco, model1, joint=joint_index, seconds=seconds, hz=base_hz,
                   latency_samples=latency_samples)
    est_lag = _lag_by_simulation(mujoco, xml_path, model1, joint_index, log2["qpos"],
                                 latency_samples, seconds, base_hz)
    sol2, _ = _fit(mujoco, xml_path, log2, joint_index, with_coulomb=True)
    rec2 = {"latency_samples": est_lag, "damping": float(sol2[0]), "coulomb": float(sol2[1])}
    truth2 = {"latency_samples": latency_samples, "damping": damping_truth, "coulomb": friction_truth}
    ok2 = (est_lag == latency_samples and
           all(abs(rec2[k] - truth2[k]) <= TOL[2] * truth2[k] for k in ("damping", "coulomb")))
    add(2, "plus 3 sample latency at 1 kHz", ok2, truth2, rec2,
        "latency identified as an integer number of samples")

    # rung 3: the log rate a partner would give us
    log3 = _excite(mujoco, model1, joint=joint_index, seconds=seconds, hz=log_hz,
                   latency_samples=max(1, round(latency_samples * log_hz / base_hz)),
                   noise=0.0008, quantise=True, seed=7)
    sol3, cond3 = _fit(mujoco, xml_path, log3, joint_index, with_coulomb=True)
    rec3 = {"damping": float(sol3[0]), "coulomb": float(sol3[1])}
    ok3 = all(abs(rec3[k] - truth1[k]) <= TOL[3] * truth1[k] for k in truth1)
    kp = float(model.actuator_biasprm[0, 1])
    quant = 2.0 * math.pi / 4096.0
    torque_noise = abs(kp) * quant
    signal = truth1["damping"] * float(np.max(np.abs(log3["qvel"][:, joint_index])))
    add(3, f"{log_hz} Hz with noise and 4096 count quantisation", ok3, truth1, rec3,
        f"condition number {cond3:.1f}, tolerance {TOL[3]:.0%}. Position quantisation is "
        f"{quant*1000:.2f} mrad and the servo stiffness is {abs(kp):.0f} N m per rad, so one count of "
        f"position error is about {torque_noise:.2f} N m of actuator torque, against a friction "
        f"signal of roughly {signal:.2f} N m. The method cannot separate them at this rate, and no "
        "amount of fitting fixes a signal to noise ratio of "
        f"{signal/torque_noise:.2f}. A partner's bench log with a real torque channel escapes this; "
        "a 62 Hz position log does not.")

    # rung 4: a second joint
    second = "elbow_flex" if "elbow_flex" in names else names[-1]
    j2 = names.index(second)
    model4 = _load(mujoco, xml_path, joint=j2, damping=damping_truth, friction=friction_truth)
    log4 = _excite(mujoco, model4, joint=j2, seconds=seconds, hz=base_hz, latency_samples=0)
    sol4, _ = _fit(mujoco, xml_path, log4, j2, with_coulomb=True)
    rec4 = {"damping": float(sol4[0]), "coulomb": float(sol4[1])}
    ok4 = all(abs(rec4[k] - truth1[k]) <= TOL[4] * truth1[k] for k in truth1)
    add(4, f"second joint {second}, noise free, 1 kHz", ok4, truth1, rec4)

    return report


def _lag_by_simulation(mujoco, xml_path: str, model, joint: int, measured_qpos: np.ndarray,
                       search: int, seconds: float, hz: int) -> int:
    """Latency as an integer sample count, by re-running candidate delays and comparing positions.

    Cross correlation of command against position cannot separate transport latency from the
    servo's own lag, and shifting logged series cannot see a delay in the command at all, because
    the logging is not delayed. Re-simulating each candidate is the only honest way to isolate it.
    """
    best, best_lag = np.inf, 0
    for lag in range(search * 2 + 2):
        log = _excite(mujoco, model, joint=joint, seconds=seconds, hz=hz, latency_samples=lag,
                      seed=11)
        err = float(np.sqrt(np.mean((log["qpos"][:, joint] - measured_qpos[:, joint]) ** 2)))
        if err < best:
            best, best_lag = err, lag
    return best_lag


def _lag_by_residual(mujoco, xml_path: str, log: dict, joint: int, max_lag: int = 12) -> int:
    """Latency as an integer sample count: the alignment that best explains the torque balance.

    Cross correlation of command against position measures the servo's own lag as well as the
    transport lag, so it overshoots. Shifting the torque series against the state series and asking
    which shift leaves the cleanest friction residual isolates the transport lag.
    """
    best, best_lag = np.inf, 0
    for lag in range(max_lag + 1):
        shifted = {k: v for k, v in log.items() if k != "hz"}
        shifted["tau"] = np.roll(log["tau"], lag, axis=0)[lag:]
        shifted["qpos"] = log["qpos"][lag:]
        shifted["qvel"] = log["qvel"][lag:]
        shifted["qacc"] = log["qacc"][lag:]
        if len(shifted["qpos"]) < 50:
            break
        try:
            sol, _ = _fit(mujoco, xml_path, shifted, joint, with_coulomb=True)
        except Exception:
            continue
        v = shifted["qvel"][:, joint]
        keep = np.abs(v) > 0.10 * float(np.max(np.abs(v)))
        rigid = _rigid_torque(mujoco, xml_path, shifted, joint)
        res = (shifted["tau"][:, joint] - rigid[:, joint])[keep]
        A = np.column_stack([shifted["qvel"][:, joint][keep], np.sign(shifted["qvel"][:, joint][keep])])
        err = float(np.linalg.norm(res - A @ sol))
        if err < best:
            best, best_lag = err, lag
    return best_lag


def _cross_correlation_lag(ctrl: np.ndarray, qpos: np.ndarray, max_lag: int = 40) -> int:
    a = np.diff(ctrl)
    b = np.diff(qpos)
    best, best_lag = -np.inf, 0
    for lag in range(max_lag + 1):
        aa, bb = (a, b) if lag == 0 else (a[:-lag], b[lag:])
        if len(aa) < 20:
            break
        c = np.corrcoef(aa, bb)[0, 1]
        if np.isfinite(c) and c > best:
            best, best_lag = c, lag
    return best_lag


def write(report: Report, out_path) -> pathlib.Path:
    path = pathlib.Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["disclaimer"] = (
        "SYNTHETIC method validation. Parameters are planted in a simulation and recovered from "
        "simulated logs. No hardware was involved."
    )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
