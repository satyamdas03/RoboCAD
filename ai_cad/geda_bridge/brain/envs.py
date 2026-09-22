"""Lightweight environments for attention-based brain training.

Two flavours are provided:

1. ``AbstractAttentionEnv`` — pure-NumPy environment built from a
   ``WorldDescription`` attention task. It is always available and is the
   target of the deterministic test suite.

2. ``WorldReplayEnv`` — MuJoCo-backed environment that runs a real generated
   world with a policy. It requires ``mujoco`` and an exported world MJCF.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ai_cad.geda_bridge.brain.policies import AttentionMLPPolicy
from ai_cad.geda_bridge.brain.world_model import AttentionBudget, compute_saliency

try:
    from ai_cad.geda_bridge.world_builder import (
        ComputeBudget,
        DomainRandomization,
        SceneGoalRegion,
        SceneObject,
        WorldDescription,
        resolve_body_alias,
    )
except Exception:  # pragma: no cover - defensive import
    WorldDescription = Any  # type: ignore[misc, assignment]
    SceneGoalRegion = Any  # type: ignore[misc, assignment]
    SceneObject = Any  # type: ignore[misc, assignment]
    ComputeBudget = Any  # type: ignore[misc, assignment]
    DomainRandomization = Any  # type: ignore[misc, assignment]
    resolve_body_alias = None  # type: ignore[misc, assignment]

try:
    import mujoco
except Exception:  # pragma: no cover - optional dependency
    mujoco = None


class AbstractAttentionEnv:
    """2-D attention navigation task derived from a ``WorldDescription``.

    The agent controls a 2-D velocity. Reward is positive for reaching attention
    regions, negative for compute over-budget. The observation dimension is
    fixed at 6 to match ``AttentionMLPPolicy``.

    Observation layout (dim 6):
        [0] agent x normalised to [-1, 1]
        [1] agent y normalised to [-1, 1]
        [2] delta x to nearest attention region centre
        [3] delta y to nearest attention region centre
        [4] compute budget active dim ratio (active / max_dim)
        [5] event-trigger flag (1.0 if any body saliency is high, else 0.0)
    """

    OBS_DIM = 6
    ACTION_DIM = 2
    ARENA_SIZE = 2.0

    def __init__(
        self,
        world: WorldDescription | None = None,
        budget: AttentionBudget | None = None,
        n_steps: int = 200,
        dt: float = 0.05,
        success_radius: float = 0.12,
        max_speed: float = 0.2,
        seed: int = 0,
    ) -> None:
        self.rng = np.random.default_rng(seed)
        self.n_steps = int(n_steps)
        self.dt = float(dt)
        self.success_radius = float(success_radius)
        self.max_speed = float(max_speed)
        self.regions: list[tuple[float, float]] = []
        self.budget = budget or AttentionBudget(
            tops=2.0, power_w=5.0, latency_ms=15.0, memory_mb=256.0
        )
        self.state = np.zeros(2, dtype=float)
        self.step_count = 0
        self.active_dims_used = 0
        if world is not None:
            self._load_world(world)
        if not self.regions:
            # Default attention region straight ahead.
            self.regions.append((0.6, 0.0))
        self.reset()

    def _load_world(self, world: WorldDescription) -> None:
        # Try modern attribute access.
        for attr in ("attention_regions", "regions", "task", "goals"):
            obj = getattr(world, attr, None)
            if obj is None:
                continue
            if isinstance(obj, list):
                self.regions.extend(self._region_centres(obj))
            elif hasattr(obj, "attention_regions"):
                self.regions.extend(self._region_centres(obj.attention_regions))
        budget_obj = getattr(world, "compute_budget", None)
        if budget_obj is not None:
            try:
                self.budget = AttentionBudget(
                    tops=float(getattr(budget_obj, "tops", 2.0)),
                    power_w=float(getattr(budget_obj, "power_w", 5.0)),
                    latency_ms=float(getattr(budget_obj, "latency_ms", 15.0)),
                    memory_mb=float(getattr(budget_obj, "memory_mb", 256.0)),
                )
            except Exception:
                pass

    @staticmethod
    def _region_centres(regions: list[Any]) -> list[tuple[float, float]]:
        centres: list[tuple[float, float]] = []
        for r in regions:
            if isinstance(r, tuple):
                centres.append((float(r[0]), float(r[1])))
            elif hasattr(r, "centre"):
                c = r.centre
                centres.append((float(c[0]), float(c[1])))
            elif hasattr(r, "center"):
                c = r.center
                centres.append((float(c[0]), float(c[1])))
            elif isinstance(r, dict):
                c = r.get("centre") or r.get("center") or (0.0, 0.0)
                centres.append((float(c[0]), float(c[1])))
        return centres

    def reset(self, seed: int | None = None) -> np.ndarray:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        # Random start in left half of arena.
        self.state = self.rng.uniform([-0.9, -0.4], [-0.3, 0.4]).astype(float)
        self.step_count = 0
        self.active_dims_used = 0
        return self._observe()

    def _nearest_region(self) -> tuple[float, float]:
        best = self.regions[0]
        best_d = float("inf")
        for r in self.regions:
            d = math.hypot(self.state[0] - r[0], self.state[1] - r[1])
            if d < best_d:
                best_d = d
                best = r
        return best

    def _observe(self) -> np.ndarray:
        r = self._nearest_region()
        max_dim = self.budget.active_dimensions(self.OBS_DIM)
        ratio = min(self.active_dims_used, max_dim) / max(1, max_dim)
        obs = np.array(
            [
                self.state[0] / (self.ARENA_SIZE * 0.5),
                self.state[1] / (self.ARENA_SIZE * 0.5),
                r[0] - self.state[0],
                r[1] - self.state[1],
                ratio,
                1.0 if ratio > 0.5 else 0.0,
            ],
            dtype=float,
        )
        return obs

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, dict[str, Any]]:
        action = np.clip(np.asarray(action, dtype=float), -self.max_speed, self.max_speed)
        self.state += action * self.dt
        self.state = np.clip(self.state, -self.ARENA_SIZE / 2, self.ARENA_SIZE / 2)
        self.step_count += 1

        r = self._nearest_region()
        dist = math.hypot(self.state[0] - r[0], self.state[1] - r[1])
        reached = dist <= self.success_radius
        reward = -0.01 * dist
        if reached:
            reward += 1.0
        reward -= self.budget.compute_penalty(self.active_dims_used)

        terminated = bool(reached or self.step_count >= self.n_steps)
        info = {"dist_to_region": dist, "reached": reached, "steps": self.step_count}
        return self._observe(), float(reward), terminated, info

    def rollout(self, policy: AttentionMLPPolicy, seed: int | None = None) -> dict[str, Any]:
        """Run one episode with the given policy."""
        obs = self.reset(seed=seed)
        total_reward = 0.0
        reached = False
        for _ in range(self.n_steps):
            # Attention mask: drop the least salient dims when compute is tight.
            obs, active_dims = self._apply_attention(obs)
            action = policy(obs)
            obs, reward, terminated, info = self.step(action)
            total_reward += reward
            reached = reached or bool(info.get("reached"))
            if terminated:
                break
        final_r = self._nearest_region()
        final_dist = math.hypot(self.state[0] - final_r[0], self.state[1] - final_r[1])
        return {
            "reward": float(total_reward),
            "success": bool(reached),
            "final_distance": float(final_dist),
            "steps": self.step_count,
        }

    def _apply_attention(self, obs: np.ndarray) -> tuple[np.ndarray, int]:
        """Hard attention: keep only the top-k salient observation dimensions."""
        max_dim = self.budget.active_dimensions(self.OBS_DIM)
        saliency = np.abs(obs)
        keep_idx = np.argsort(saliency)[::-1][:max_dim]
        mask = np.zeros(self.OBS_DIM, dtype=float)
        mask[keep_idx] = 1.0
        self.active_dims_used = int(mask.sum())
        return obs * mask, self.active_dims_used


class WorldReplayEnv:
    """Real MuJoCo environment that runs a generated world with a policy.

    The environment discovers the robot's actuator count, joint structure, and
    task definition from the loaded MJCF and an optional ``WorldDescription``.
    Observations and actions are therefore robot-specific, and the companion
    ``RobotMLPPolicy`` adapts its dimensions to the env instance.
    """

    DEFAULT_N_STEPS = 500
    DEFAULT_TIMESTEP = 0.002

    def __init__(
        self,
        mjcf_path: str | None = None,
        world: WorldDescription | None = None,
        n_steps: int = DEFAULT_N_STEPS,
        timestep: float | None = None,
        seed: int = 0,
        domain_randomization: DomainRandomization | None = None,
    ) -> None:
        self.mjcf_path = str(mjcf_path) if mjcf_path else None
        self.world = world
        self.n_steps = int(n_steps)
        self.seed = int(seed)
        self.rng = np.random.default_rng(seed)
        self.domain_randomization = domain_randomization

        self.model: Any = None
        self.data: Any = None
        self._error: list[str] = []

        # Discovered robot structure.
        self.action_dim: int = 0
        self.obs_dim: int = 0
        self.actuator_names: list[str] = []
        self.ctrl_low: np.ndarray = np.zeros(0)
        self.ctrl_high: np.ndarray = np.zeros(0)
        self.actuator_joint_ids: list[int] = []
        self.hinge_joint_ids: list[int] = []
        self.freejoint_id: int | None = None
        self.torso_body_id: int | None = None
        self.goal_pos: np.ndarray = np.zeros(3)
        self.object_body_id: int | None = None
        self.task_type: str = "walker"
        self.success_tolerance_m: float = 0.2
        self.fall_height_threshold_m: float = 0.25
        self._step_count: int = 0

        if mujoco is not None and self.mjcf_path:
            self._load_model(timestep)

    def _load_model(self, timestep: float | None) -> None:
        try:
            self.model = mujoco.MjModel.from_xml_path(str(self.mjcf_path))
        except Exception as exc:
            self._error.append(f"failed to load MJCF: {exc}")
            return

        if timestep is not None:
            self.model.opt.timestep = float(timestep)
        self.data = mujoco.MjData(self.model)

        self._discover_structure()
        self._resolve_task()
        self._compute_obs_dim()
        self.reset()

    def _discover_structure(self) -> None:
        model = self.model
        self.action_dim = int(model.nu)

        self.ctrl_low = np.array([model.actuator_ctrlrange[i, 0] for i in range(model.nu)], dtype=float)
        self.ctrl_high = np.array([model.actuator_ctrlrange[i, 1] for i in range(model.nu)], dtype=float)

        for i in range(model.nu):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) or f"actuator_{i}"
            self.actuator_names.append(str(name))
            trn_id = int(model.actuator_trnid[i, 0])
            self.actuator_joint_ids.append(trn_id)

        self.hinge_joint_ids = []
        self.freejoint_id = None
        for j in range(model.njnt):
            jnt_type = int(model.jnt_type[j])
            if jnt_type == mujoco.mjtJoint.mjJNT_FREE:
                self.freejoint_id = j
            elif jnt_type in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE):
                self.hinge_joint_ids.append(j)

        available_bodies = {
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or ""
            for i in range(model.nbody)
        }
        available_bodies.discard("")
        if resolve_body_alias is not None:
            torso_name = resolve_body_alias("torso", available_bodies)
        else:
            torso_name = None
        if torso_name:
            self.torso_body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, torso_name)
        else:
            # Fallback: first non-world body (body 0 is world).
            self.torso_body_id = 1 if model.nbody > 1 else None

    def _resolve_task(self) -> None:
        if self.world is None or not hasattr(self.world, "task") or self.world.task is None:
            self.task_type = "walker"
            self.goal_pos = np.array([2.0, 0.0, 0.0], dtype=float)
            return

        task = self.world.task
        self.task_type = str(getattr(task, "task_type", "walker"))

        goals: list[Any] = getattr(task, "goal_regions", None) or []
        if goals:
            goal = goals[0]
            self.goal_pos = np.asarray(getattr(goal, "pos", (2.0, 0.0, 0.0)), dtype=float)
        else:
            self.goal_pos = np.array([2.0, 0.0, 0.0], dtype=float)

        criteria = getattr(task, "success_criteria", {}) or {}
        self.success_tolerance_m = float(criteria.get("tolerance_m", 0.2))
        self.fall_height_threshold_m = float(criteria.get("fall_height_threshold_m", 0.25))

        # Resolve object body for manipulation tasks.
        obj_name = None
        if self.task_type in ("push", "pick_place"):
            obj_name = criteria.get("object")
        if obj_name is None and self.world is not None and hasattr(self.world, "scene"):
            scene = self.world.scene
            objects = getattr(scene, "objects", None) or []
            if objects:
                # Prefer the first non-goal object; for push templates this is the block.
                obj_name = getattr(objects[0], "name", None)
        if obj_name and self.model is not None:
            safe_name = self._sanitize(obj_name)
            try:
                bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, safe_name)
                if bid >= 0:
                    self.object_body_id = bid
            except Exception:
                pass

    def _compute_obs_dim(self) -> None:
        # 2 values per hinge/slide joint (qpos + qvel).
        joint_obs_dim = 2 * len(self.hinge_joint_ids)
        # Freejoint torso state: pos(3) + gravity(3) + linvel(3) + angvel(3).
        freejoint_obs_dim = 12 if self.freejoint_id is not None else 0
        # Task error terms.
        task_obs_dim = 3 + (3 if self.object_body_id is not None else 0)
        self.obs_dim = joint_obs_dim + freejoint_obs_dim + task_obs_dim

    def is_available(self) -> bool:
        return mujoco is not None and self.model is not None and self.data is not None

    def get_error(self) -> list[str]:
        return list(self._error)

    @staticmethod
    def _sanitize(name: str) -> str:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if safe and safe[0].isdigit():
            safe = "_" + safe
        return safe or "obj"

    def reset(self, seed: int | None = None) -> np.ndarray:
        if seed is not None:
            self.seed = int(seed)
            self.rng = np.random.default_rng(seed)
        if not self.is_available():
            return np.zeros(self.obs_dim, dtype=float)

        mujoco.mj_resetData(self.model, self.data)
        # Tiny state noise for training robustness.
        noise_std = 0.0
        if self.domain_randomization is not None:
            noise_std = float(getattr(self.domain_randomization, "actuator_noise_std", 0.0)) * 0.01
        if noise_std > 0:
            self.data.qpos[:] += self.rng.normal(0.0, noise_std, size=self.data.qpos.shape)
            self.data.qvel[:] += self.rng.normal(0.0, noise_std, size=self.data.qvel.shape)
        mujoco.mj_forward(self.model, self.data)
        self._step_count = 0
        return self._observe()

    def _body_pos(self, body_id: int | None) -> np.ndarray:
        if body_id is None or not self.is_available():
            return np.zeros(3, dtype=float)
        return np.asarray(self.data.xpos[body_id], dtype=float)

    def _joint_observations(self) -> np.ndarray:
        if not self.is_available():
            return np.zeros(0, dtype=float)
        model = self.model
        data = self.data
        values: list[float] = []
        for jid in self.hinge_joint_ids:
            qadr = int(model.jnt_qposadr[jid])
            vadr = int(model.jnt_dofadr[jid])
            qpos = float(data.qpos[qadr])
            qvel = float(data.qvel[vadr])
            lo, hi = float(model.jnt_range[jid, 0]), float(model.jnt_range[jid, 1])
            if hi > lo:
                norm_q = (2.0 * (qpos - lo) / (hi - lo)) - 1.0
            else:
                norm_q = qpos
            # Velocity roughly normalized to ~[-1, 1] for typical robot joints.
            norm_v = np.clip(qvel / 10.0, -1.0, 1.0)
            values.extend([float(np.clip(norm_q, -1.0, 1.0)), float(norm_v)])
        return np.asarray(values, dtype=float)

    def _freejoint_observations(self) -> np.ndarray:
        if not self.is_available() or self.freejoint_id is None or self.torso_body_id is None:
            return np.zeros(0, dtype=float)
        model = self.model
        data = self.data
        qadr = int(model.jnt_qposadr[self.freejoint_id])
        vadr = int(model.jnt_dofadr[self.freejoint_id])
        pos = np.asarray(data.qpos[qadr : qadr + 3], dtype=float)
        xmat = data.xmat[self.torso_body_id].reshape(3, 3)
        gravity = xmat[:, 2]  # world z-axis expressed in body frame
        linvel = np.asarray(data.qvel[vadr : vadr + 3], dtype=float)
        angvel = np.asarray(data.qvel[vadr + 3 : vadr + 6], dtype=float)
        return np.concatenate(
            [
                pos,
                gravity,
                np.clip(linvel / 5.0, -1.0, 1.0),
                np.clip(angvel / 10.0, -1.0, 1.0),
            ]
        )

    def _task_observations(self) -> np.ndarray:
        torso_pos = self._body_pos(self.torso_body_id)
        goal_delta = self.goal_pos - torso_pos
        parts = [goal_delta]
        if self.object_body_id is not None:
            obj_pos = self._body_pos(self.object_body_id)
            parts.append(self.goal_pos - obj_pos)
        return np.concatenate(parts).astype(float)

    def _observe(self) -> np.ndarray:
        obs = np.concatenate(
            [
                self._joint_observations(),
                self._freejoint_observations(),
                self._task_observations(),
            ]
        )
        return obs.astype(float)

    def _scale_action(self, action: np.ndarray) -> np.ndarray:
        action = np.clip(np.asarray(action, dtype=float), -1.0, 1.0)
        mid = 0.5 * (self.ctrl_high + self.ctrl_low)
        half = 0.5 * (self.ctrl_high - self.ctrl_low)
        return mid + half * action

    def _compute_reward(self, ctrl: np.ndarray) -> tuple[float, dict[str, Any]]:
        if not self.is_available():
            return 0.0, {}
        torso_pos = self._body_pos(self.torso_body_id)
        goal_delta = self.goal_pos - torso_pos
        dist_to_goal = float(np.linalg.norm(goal_delta[:2]))  # planar distance

        ctrl_penalty = float(np.sum(ctrl ** 2)) * 1e-5
        alive_bonus = 0.05
        reward = alive_bonus - ctrl_penalty
        info: dict[str, Any] = {
            "dist_to_goal": dist_to_goal,
            "torso_z": float(torso_pos[2]) if torso_pos is not None else 0.0,
        }

        if self.task_type == "walker":
            # Reward forward progress toward the goal.
            reward += -0.01 * dist_to_goal
            # Small bonus for being upright and not fallen.
            if torso_pos[2] > self.fall_height_threshold_m:
                reward += 0.02
        elif self.task_type == "humanoid_stand":
            # Reward staying upright near the origin height.
            reward += 0.05 * torso_pos[2]
            reward += -0.01 * dist_to_goal
        elif self.task_type == "push":
            # Reward object closeness to goal.
            if self.object_body_id is not None:
                obj_pos = self._body_pos(self.object_body_id)
                obj_dist = float(np.linalg.norm((self.goal_pos - obj_pos)[:2]))
                reward += -0.02 * obj_dist
                info["object_dist_to_goal"] = obj_dist
        elif self.task_type == "pick_place":
            if self.object_body_id is not None:
                obj_pos = self._body_pos(self.object_body_id)
                obj_goal_dist = float(np.linalg.norm(self.goal_pos - obj_pos))
                lift = max(0.0, obj_pos[2] - 0.45)  # crude table height assumption
                reward += -0.01 * obj_goal_dist + 0.05 * lift
                info["object_dist_to_goal"] = obj_goal_dist
                info["object_lift_m"] = float(lift)
        else:
            reward += -0.01 * dist_to_goal

        return reward, info

    def _is_terminated(self, info: dict[str, Any]) -> bool:
        if self._step_count >= self.n_steps:
            return True
        if self.task_type in ("walker", "humanoid_stand"):
            torso_z = float(info.get("torso_z", 1.0))
            if torso_z < self.fall_height_threshold_m:
                return True
        return False

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, dict[str, Any]]:
        if not self.is_available():
            return (
                np.zeros(self.obs_dim, dtype=float),
                0.0,
                True,
                {"error": "MuJoCo not available"},
            )
        ctrl = self._scale_action(action)
        self.data.ctrl[:] = ctrl
        mujoco.mj_step(self.model, self.data)
        self._step_count += 1
        reward, info = self._compute_reward(ctrl)
        terminated = self._is_terminated(info)
        info["steps"] = self._step_count
        return self._observe(), float(reward), bool(terminated), info

    def rollout(self, policy: Any, seed: int | None = None) -> dict[str, Any]:
        """Run one episode with the given policy."""
        obs = self.reset(seed=seed)
        total_reward = 0.0
        for _ in range(self.n_steps):
            action = policy(obs)
            obs, reward, terminated, info = self.step(action)
            total_reward += reward
            if terminated:
                break

        success = False
        if self.task_type in ("walker", "push", "pick_place"):
            dist_key = "object_dist_to_goal" if self.object_body_id is not None else "dist_to_goal"
            final_dist = float(info.get(dist_key, float("inf")))
            success = final_dist <= self.success_tolerance_m
        elif self.task_type == "humanoid_stand":
            success = float(info.get("torso_z", 0.0)) >= self.fall_height_threshold_m

        return {
            "reward": float(total_reward),
            "success": bool(success),
            "final_distance": float(info.get("dist_to_goal", float("inf"))),
            "steps": self._step_count,
            "task_type": self.task_type,
        }
