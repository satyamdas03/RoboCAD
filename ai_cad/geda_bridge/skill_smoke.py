"""Phase 15B — trainable skill smoke test for the RoboCAD GEDA Bridge.

Provides a small, dependency-light reinforcement-learning pipeline that trains a
policy for a simple manipulation skill around a RoboCAD-generated asset. The
training uses a tiny feed-forward network trained by the Cross-Entropy Method
(CEM) with NumPy only — no PyTorch/JAX dependency is required.

Example:
    from ai_cad.geda_bridge.skill_smoke import train_push_skill
    report = train_push_skill(
        asset_mesh_path=Path("designs/abc/simulation/meshes/model.stl"),
        goal_pos=(0.55, 0.0, 0.49),
    )
    print(report["success_rate"], report["final_block_distance_m"])
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

try:
    import mujoco
except Exception:  # pragma: no cover - optional dependency
    mujoco = None


MM_TO_M = 0.001


class TinyMLPPolicy:
    """Tiny ReLU MLP policy trained via CEM.

    The network maps a 3-dim observation to a scalar control. Architecture is
    fixed so hyperparameters and weight vectors are portable.
    """

    INPUT_DIM = 3
    HIDDEN_DIM = 8
    OUTPUT_DIM = 1

    @classmethod
    def n_params(cls) -> int:
        return cls.INPUT_DIM * cls.HIDDEN_DIM + cls.HIDDEN_DIM + cls.HIDDEN_DIM * cls.OUTPUT_DIM + cls.OUTPUT_DIM

    def __init__(self, weights: np.ndarray) -> None:
        if weights.shape != (self.n_params(),):
            raise ValueError(f"weights must have shape {(self.n_params(),)}, got {weights.shape}")
        self.weights = np.asarray(weights, dtype=float)
        self.W1, self.b1, self.W2, self.b2 = self._unpack(self.weights)

    @staticmethod
    def _unpack(weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        idx = 0
        W1 = weights[idx : idx + TinyMLPPolicy.INPUT_DIM * TinyMLPPolicy.HIDDEN_DIM].reshape(
            TinyMLPPolicy.INPUT_DIM, TinyMLPPolicy.HIDDEN_DIM
        )
        idx += TinyMLPPolicy.INPUT_DIM * TinyMLPPolicy.HIDDEN_DIM
        b1 = weights[idx : idx + TinyMLPPolicy.HIDDEN_DIM]
        idx += TinyMLPPolicy.HIDDEN_DIM
        W2 = weights[idx : idx + TinyMLPPolicy.HIDDEN_DIM * TinyMLPPolicy.OUTPUT_DIM].reshape(
            TinyMLPPolicy.HIDDEN_DIM, TinyMLPPolicy.OUTPUT_DIM
        )
        idx += TinyMLPPolicy.HIDDEN_DIM * TinyMLPPolicy.OUTPUT_DIM
        b2 = weights[idx : idx + TinyMLPPolicy.OUTPUT_DIM]
        return W1, b1, W2, b2

    def __call__(self, obs: np.ndarray) -> float:
        h = np.maximum(obs @ self.W1 + self.b1, 0.0)
        return float((h @ self.W2 + self.b2)[0])


class PushSkillEnv:
    """MuJoCo environment: a slide-joint pusher pushes a free block to a goal.

    The pusher body can carry an arbitrary asset mesh (the RoboCAD-generated
    wedge), but a fallback box is used if no mesh is supplied. Observations are
    (goal - block_x, block_vx, pusher_x - block_x); action is scalar force.
    """

    def __init__(
        self,
        asset_mesh_path: Path | None = None,
        pusher_start_m: tuple[float, float, float] = (0.05, 0.0, 0.49),
        block_start_m: tuple[float, float, float] = (0.25, 0.0, 0.49),
        goal_m: tuple[float, float, float] = (0.55, 0.0, 0.49),
        table_height_m: float = 0.45,
        pusher_force_limit: float = 5.0,
        timestep: float = 0.002,
        n_steps: int = 500,
        success_radius_m: float = 0.06,
        use_visual_mesh: bool = False,
    ) -> None:
        self.asset_mesh_path = Path(asset_mesh_path) if asset_mesh_path else None
        self.pusher_start = tuple(float(v) for v in pusher_start_m)
        self.block_start = tuple(float(v) for v in block_start_m)
        self.goal = tuple(float(v) for v in goal_m)
        self.table_height = float(table_height_m)
        self.pusher_force_limit = float(pusher_force_limit)
        self.timestep = float(timestep)
        self.n_steps = int(n_steps)
        self.success_radius_m = float(success_radius_m)
        self.use_visual_mesh = use_visual_mesh
        self.model, self.xml_path = self._build_model()
        self.data = mujoco.MjData(self.model) if self.model is not None else None

    def _build_model(self) -> tuple[Any, Path | None]:
        if mujoco is None:
            raise RuntimeError("mujoco is not installed")

        pusher_geom = self._pusher_geom_xml()
        block_xml = f'<body name="block" pos="{self._fmt(self.block_start)}" quat="1 0 0 0"><freejoint/><geom name="block_geom" type="box" size="0.04 0.04 0.04" density="8000" friction="0.8 0.05 0.05"/></body>'
        table_xml = (
            f'<body name="table" pos="0 0 {self.table_height - 0.025:.4f}">'
            '<geom name="table_geom" type="box" size="1.0 0.6 0.025" density="500" contype="1" conaffinity="1" friction="0.8 0.05 0.05"/>'
            "</body>"
        )

        asset_xml = ""
        if self.asset_mesh_path and self.asset_mesh_path.exists():
            # MuJoCo expects mesh files next to the MJCF or an absolute path.
            asset_xml = f'<mesh name="pusher_mesh" file="{self.asset_mesh_path.as_posix()}" scale="1 1 1"/>'

        xml = f"""<mujoco model="push_skill">
  <compiler angle="radian" meshdir="{self.asset_mesh_path.parent.as_posix() if self.asset_mesh_path else '.'}"/>
  <option timestep="{self.timestep}" integrator="RK4"/>
  <asset>
    {asset_xml}
  </asset>
  <worldbody>
    {table_xml}
    {self._pusher_body_xml(pusher_geom)}
    {block_xml}
  </worldbody>
  <actuator>
    <general name="pusher_force" joint="pusher_slide" ctrlrange="{-self.pusher_force_limit} {self.pusher_force_limit}" gear="1"/>
  </actuator>
  <contact>
    <pair geom1="pusher_geom" geom2="block_geom" friction="2 0.001 0.0001"/>
  </contact>
</mujoco>
"""
        # Write to a temporary MJCF so mesh paths resolve cleanly.
        tmp = Path(tempfile.gettempdir()) / f"robocad_push_skill_{id(self)}.mjcf"
        tmp.write_text(xml, encoding="utf-8")
        model = mujoco.MjModel.from_xml_path(str(tmp))
        return model, tmp

    def _pusher_geom_xml(self) -> str:
        if self.asset_mesh_path and self.asset_mesh_path.exists() and self.use_visual_mesh:
            # Use the asset mesh as the actual collision geometry. For most
            # generated STLs this is fine; for very high-poly meshes it can be
            # slower, so callers can opt for the box approximation instead.
            return (
                f'<geom name="pusher_geom" type="mesh" mesh="pusher_mesh" '
                f'contype="1" conaffinity="1" friction="2 0.001 0.0001" density="1000"/>'
            )
        return '<geom name="pusher_geom" type="box" size="0.02 0.04 0.04" density="1000" friction="2 0.001 0.0001"/>'

    def _pusher_body_xml(self, pusher_geom: str) -> str:
        return (
            f'<body name="pusher" pos="{self._fmt(self.pusher_start)}">'
            f'<joint name="pusher_slide" type="slide" axis="1 0 0" range="0.0 0.6" damping="0.5"/>'
            f'{pusher_geom}'
            "</body>"
        )

    @staticmethod
    def _fmt(t: tuple[float, ...]) -> str:
        return " ".join(f"{v:.6f}" for v in t)

    def rollout(self, policy: TinyMLPPolicy, seed: int = 0, verbose: bool = False) -> dict[str, Any]:
        if self.model is None or self.data is None or mujoco is None:
            raise RuntimeError("mujoco is not installed")
        data = mujoco.MjData(self.model)
        rng = np.random.default_rng(seed)
        # Add tiny state noise so the policy is robust.
        data.qpos[:] += rng.normal(0.0, 0.002, size=data.qpos.shape)
        total_reward = 0.0
        for _ in range(self.n_steps):
            obs = self._observe(data)
            u = policy(obs)
            data.ctrl[:] = [float(np.clip(u, -self.pusher_force_limit, self.pusher_force_limit))]
            mujoco.mj_step(self.model, data)
            # Reward: negative squared distance to goal plus small ctrl penalty.
            total_reward -= (data.qpos[1] - self.goal[0]) ** 2 + 0.001 * (data.ctrl[0] ** 2)
        final_dist = math.hypot(data.qpos[1] - self.goal[0], 0.0)
        if verbose:
            print(f"final block x={data.qpos[1]:.4f} goal={self.goal[0]:.4f} dist={final_dist:.4f}")
        return {
            "final_block_x_m": float(data.qpos[1]),
            "final_distance_m": float(final_dist),
            "reward": float(total_reward),
            "success": bool(final_dist <= self.success_radius_m),
        }

    def _observe(self, data: Any) -> np.ndarray:
        return np.array(
            [
                self.goal[0] - data.qpos[1],  # goal - block_x
                data.qvel[1],  # block velocity
                data.qpos[0] - data.qpos[1],  # pusher - block
            ],
            dtype=float,
        )

    def evaluate(self, policy: TinyMLPPolicy, n_episodes: int = 10) -> dict[str, Any]:
        results = [self.rollout(policy, seed=i) for i in range(n_episodes)]
        successes = [r["success"] for r in results]
        return {
            "n_episodes": n_episodes,
            "success_rate": float(sum(successes) / len(successes)) if successes else 0.0,
            "mean_final_distance_m": float(np.mean([r["final_distance_m"] for r in results])),
            "mean_reward": float(np.mean([r["reward"] for r in results])),
            "rollouts": results,
        }


def train_policy_cem(
    env: PushSkillEnv,
    n_iters: int = 20,
    pop_size: int = 50,
    elite_frac: float = 0.2,
    seed: int = 0,
) -> tuple[np.ndarray, float]:
    """Train a TinyMLPPolicy via CEM. Returns best weights and best reward."""
    rng = np.random.default_rng(seed)
    n_params = TinyMLPPolicy.n_params()
    mean = np.zeros(n_params)
    std = np.ones(n_params)
    best_weights = mean.copy()
    best_reward = -float("inf")
    for it in range(n_iters):
        samples = [rng.normal(mean, std) for _ in range(pop_size)]
        rewards = []
        for s in samples:
            policy = TinyMLPPolicy(s)
            # Single rollout reward is noisy; average over a few seeds.
            rew = np.mean([env.rollout(policy, seed=it * pop_size + i)["reward"] for i in range(3)])
            rewards.append(rew)
        rewards = np.asarray(rewards)
        elite_count = max(1, int(round(pop_size * elite_frac)))
        elite_idx = np.argsort(rewards)[::-1][:elite_count]
        elite = np.array([samples[i] for i in elite_idx])
        mean = elite.mean(axis=0)
        std = elite.std(axis=0) + 0.001
        if rewards[elite_idx[0]] > best_reward:
            best_reward = float(rewards[elite_idx[0]])
            best_weights = elite[0].copy()
    return best_weights, best_reward


def train_push_skill(
    asset_mesh_path: Path | None = None,
    output_dir: Path | None = None,
    goal_m: tuple[float, float, float] = (0.55, 0.0, 0.49),
    block_start_m: tuple[float, float, float] = (0.25, 0.0, 0.49),
    pusher_start_m: tuple[float, float, float] = (0.05, 0.0, 0.49),
    n_iters: int = 20,
    pop_size: int = 50,
    eval_episodes: int = 10,
    success_rate_threshold: float = 0.8,
    success_radius_m: float = 0.06,
) -> dict[str, Any]:
    """End-to-end Phase 15B smoke test: train + evaluate a push policy.

    Returns a JSON-serializable report containing the trained weights, training
    metrics, evaluation success rate, and asset path used.
    """
    if mujoco is None:
        return {
            "success": False,
            "errors": ["mujoco is not installed"],
            "weights": None,
        }

    env = PushSkillEnv(
        asset_mesh_path=asset_mesh_path,
        pusher_start_m=pusher_start_m,
        block_start_m=block_start_m,
        goal_m=goal_m,
        success_radius_m=success_radius_m,
    )

    try:
        best_weights, best_reward = train_policy_cem(
            env, n_iters=n_iters, pop_size=pop_size, seed=42
        )
        policy = TinyMLPPolicy(best_weights)
        eval_report = env.evaluate(policy, n_episodes=eval_episodes)
    except Exception as exc:
        return {
            "success": False,
            "errors": [f"Training failed: {exc}"],
            "weights": None,
        }

    report = {
        "success": bool(eval_report["success_rate"] >= success_rate_threshold),
        "success_rate": float(eval_report["success_rate"]),
        "mean_final_distance_m": float(eval_report["mean_final_distance_m"]),
        "mean_reward": float(eval_report["mean_reward"]),
        "best_training_reward": float(best_reward),
        "weights": best_weights.tolist(),
        "n_params": int(TinyMLPPolicy.n_params()),
        "policy_architecture": {
            "input_dim": TinyMLPPolicy.INPUT_DIM,
            "hidden_dim": TinyMLPPolicy.HIDDEN_DIM,
            "output_dim": TinyMLPPolicy.OUTPUT_DIM,
        },
        "asset_mesh_path": str(asset_mesh_path) if asset_mesh_path else None,
        "scene_xml_path": str(env.xml_path) if env.xml_path else None,
        "eval_report": {
            "n_episodes": eval_report["n_episodes"],
            "success_rate": eval_report["success_rate"],
            "mean_final_distance_m": eval_report["mean_final_distance_m"],
            "mean_reward": eval_report["mean_reward"],
        },
        "errors": [],
    }

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "skill_policy.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        report["policy_file"] = str(output_dir / "skill_policy.json")

    return report
