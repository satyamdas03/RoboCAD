"""Lightweight environments for attention-based brain training.

Two flavours are provided:

1. ``AbstractAttentionEnv`` — pure-NumPy environment built from a
   ``WorldDescription`` attention task. It is always available and is the
   target of the deterministic test suite.

2. ``WorldReplayEnv`` — optional MuJoCo-backed environment that can replay a
   generated world with a policy. It requires ``mujoco`` and is mainly a hook
   for future real-sim integration.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ai_cad.geda_bridge.brain.policies import AttentionMLPPolicy
from ai_cad.geda_bridge.brain.world_model import AttentionBudget, compute_saliency

try:
    from ai_cad.geda_bridge.world_builder import ComputeBudget, SceneGoalRegion, WorldDescription
except Exception:  # pragma: no cover - defensive import
    WorldDescription = Any  # type: ignore[misc, assignment]
    SceneGoalRegion = Any  # type: ignore[misc, assignment]
    ComputeBudget = Any  # type: ignore[misc, assignment]

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
    """Optional MuJoCo environment that runs a real generated world.

    Currently this is a thin wrapper that records whether ``mujoco`` is
    available. Future work will wire it to ``export_world_to_mjcf`` and
    ``run_world_replay`` for closed-loop policy evaluation.
    """

    def __init__(self, mjcf_path: str | None = None) -> None:
        self.mjcf_path = mjcf_path
        self.model = None
        self.data = None
        if mujoco is not None and mjcf_path:
            self.model = mujoco.MjModel.from_xml_path(str(mjcf_path))
            self.data = mujoco.MjData(self.model)

    def is_available(self) -> bool:
        return mujoco is not None and self.model is not None

    def rollout(self, policy: AttentionMLPPolicy) -> dict[str, Any]:
        if not self.is_available():
            return {
                "success": False,
                "errors": ["mujoco is not installed or model could not be loaded"],
            }
        # Placeholder: real MuJoCo rollout with a policy will be added once the
        # world description exposes a stable closed-loop control interface.
        return {"success": True, "note": "MuJoCo environment loaded; closed-loop rollout pending"}
