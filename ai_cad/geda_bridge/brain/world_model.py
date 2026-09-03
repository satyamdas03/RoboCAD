"""Lightweight world-model and attention-budget primitives.

All models are NumPy-only so the brain layer remains deterministic and
portable. The core idea is borrowed from dynamic/spiking AI systems: not every
sensor dimension needs to be processed on every step. We estimate per-body
saliency from world replay, then use a compute budget to decide how many
dimensions the policy is allowed to observe at each step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SaliencySnapshot:
    """Per-body importance scores derived from a world replay."""

    body: str
    max_velocity: float
    max_acceleration: float
    max_force: float

    def score(self, weights: tuple[float, float, float] = (0.4, 0.3, 0.3)) -> float:
        """Scalar saliency as a weighted combination of dynamic signals."""
        w_v, w_a, w_f = weights
        # Normalise each signal with a soft upper bound so one huge spike does
        # not dominate forever.
        v = _soft_norm(self.max_velocity, 5.0)
        a = _soft_norm(self.max_acceleration, 50.0)
        f = _soft_norm(self.max_force, 1000.0)
        return float(w_v * v + w_a * a + w_f * f)


def _soft_norm(value: float, cap: float) -> float:
    """Compress large magnitudes into [0, 1] with a soft cap."""
    x = float(value) / cap
    return float(x / (1.0 + abs(x)))


def compute_saliency(replay: dict[str, Any]) -> dict[str, float]:
    """Convert a world-replay saliency map into per-body attention scores.

    The replay is expected to contain a ``saliency`` mapping body names to
    ``{"max_vel": float, "max_acc": float, "max_force": float}``. Missing or
    malformed entries are skipped gracefully.
    """
    saliency: dict[str, dict[str, float]] = replay.get("saliency") or {}
    scores: dict[str, float] = {}
    for body, metrics in saliency.items():
        if not isinstance(metrics, dict):
            continue
        snap = SaliencySnapshot(
            body=body,
            max_velocity=float(metrics.get("max_vel", 0.0)),
            max_acceleration=float(metrics.get("max_acc", 0.0)),
            max_force=float(metrics.get("max_force", 0.0)),
        )
        scores[body] = snap.score()
    return scores


@dataclass(frozen=True)
class AttentionBudget:
    """Expresses the robot's on-board compute budget in human terms.

    The budget is converted into an ``active_dim`` limit using a tiny linear
    rule: 1 TOPS ~= 2 active observation dimensions under 10 ms latency. This
    makes the abstraction concrete enough to penalise the policy during
    training, while staying independent of any actual chip specification.
    """

    tops: float
    power_w: float
    latency_ms: float
    memory_mb: float

    def active_dimensions(self, obs_dim: int) -> int:
        """Return the maximum number of observation dims the policy may use."""
        if self.latency_ms <= 0:
            latency_penalty = 0.0
        else:
            latency_penalty = max(0.0, 1.0 - 10.0 / self.latency_ms)
        # Base budget: ~2 dims per TOPS, clipped by memory and latency.
        base = 2.0 * max(0.0, self.tops)
        memory_cap = self.memory_mb / 64.0
        dims = int(np.clip(base * (1.0 - latency_penalty), 1, min(obs_dim, memory_cap)))
        return max(1, min(dims, obs_dim))

    def compute_penalty(self, active_dims: int) -> float:
        """Cost of using ``active_dims`` relative to the budget."""
        allowed = max(1, self.active_dimensions(active_dims))
        overshoot = max(0, active_dims - allowed)
        return float(0.05 * overshoot)


class LinearWorldModel:
    """Simple least-squares world model: (obs, action) -> (next_obs, reward).

    This is the brain's internal simulator. It is intentionally tiny so it
    trains in milliseconds on CPU, matching the paper's emphasis on efficient
    dynamic processing.
    """

    def __init__(self, obs_dim: int, action_dim: int) -> None:
        self.obs_dim = int(obs_dim)
        self.action_dim = int(action_dim)
        self.in_dim = obs_dim + action_dim
        self._theta: np.ndarray | None = None
        self._fitted = False

    def _features(self, obs: np.ndarray, action: np.ndarray) -> np.ndarray:
        x = np.concatenate([np.asarray(obs, dtype=float), np.asarray(action, dtype=float)])
        # Add a bias term.
        return np.concatenate([x, np.ones(1)])

    def fit(self, transitions: list[tuple[np.ndarray, np.ndarray, np.ndarray, float]]) -> None:
        """Fit the model from (obs, action, next_obs, reward) tuples."""
        if not transitions:
            self._theta = np.zeros((self.in_dim + 1, self.obs_dim + 1))
            return
        X = np.stack([self._features(o, a) for o, a, _, _ in transitions])
        Y = np.stack([np.concatenate([np.asarray(no), [float(r)]]) for _, _, no, r in transitions])
        # Ridge regression with tiny regularisation for stability.
        reg = 1e-4 * np.eye(X.shape[1])
        self._theta = np.linalg.solve(X.T @ X + reg, X.T @ Y)
        self._fitted = True

    def predict(self, obs: np.ndarray, action: np.ndarray) -> tuple[np.ndarray, float]:
        """Predict next observation and scalar reward."""
        if self._theta is None:
            # Untrained model: assume identity transition and zero reward.
            return np.asarray(obs, dtype=float).copy(), 0.0
        phi = self._features(obs, action)
        y = phi @ self._theta
        next_obs = y[: self.obs_dim]
        reward = float(y[-1])
        return next_obs, reward


def split_replay_transitions(
    replay: dict[str, Any], action_dim: int
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    """Convert a world replay into world-model training transitions.

    The replay is expected to have ``steps`` as a list of dicts with keys
    ``observation``, ``action``, ``reward``. If observations are dicts they are
    flattened in sorted-key order.
    """
    steps = replay.get("steps") or []
    transitions: list[tuple[np.ndarray, np.ndarray, np.ndarray, float]] = []
    for i in range(len(steps) - 1):
        obs = _flatten_state(steps[i].get("observation", {}))
        action = _flatten_state(steps[i].get("action", np.zeros(action_dim)))
        next_obs = _flatten_state(steps[i + 1].get("observation", {}))
        reward = float(steps[i].get("reward", 0.0))
        transitions.append((obs, action, next_obs, reward))
    return transitions


def _flatten_state(state: Any) -> np.ndarray:
    """Flatten a scalar/list/dict observation into a NumPy vector."""
    if isinstance(state, dict):
        values = [float(v) for _, v in sorted(state.items())]
        return np.asarray(values, dtype=float)
    arr = np.asarray(state, dtype=float)
    return arr.ravel()
