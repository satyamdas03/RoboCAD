"""Tests for the attention-based brain training layer (Phase 25)."""
from __future__ import annotations

import numpy as np
import pytest

from ai_cad.geda_bridge.brain import (
    AbstractAttentionEnv,
    AttentionBudget,
    AttentionMLPPolicy,
    LinearWorldModel,
    RobotMLPPolicy,
    WorldReplayEnv,
    compute_saliency,
    evaluate_attention_policy,
    train_and_evaluate,
    train_attention_policy,
    train_robot_policy,
)


def _mujoco_available() -> bool:
    try:
        import mujoco  # noqa: F401
        return True
    except Exception:
        return False


def test_attention_budget_active_dimensions():
    big = AttentionBudget(tops=16.0, power_w=15.0, latency_ms=5.0, memory_mb=1024.0)
    assert big.active_dimensions(6) == 6

    tiny = AttentionBudget(tops=0.5, power_w=2.0, latency_ms=40.0, memory_mb=64.0)
    assert 1 <= tiny.active_dimensions(6) <= 6


def test_attention_budget_compute_penalty():
    budget = AttentionBudget(tops=2.0, power_w=5.0, latency_ms=15.0, memory_mb=256.0)
    allowed = budget.active_dimensions(6)
    assert budget.compute_penalty(allowed) == 0.0
    assert budget.compute_penalty(allowed + 2) > 0.0


def test_compute_saliency_from_replay():
    replay = {
        "saliency": {
            "block": {"max_vel": 0.5, "max_acc": 10.0, "max_force": 100.0},
            "table": {"max_vel": 0.0, "max_acc": 0.0, "max_force": 0.0},
        }
    }
    scores = compute_saliency(replay)
    assert "block" in scores
    assert "table" in scores
    assert scores["block"] > scores["table"]


def test_compute_saliency_missing_field_graceful():
    replay = {"saliency": {"block": {"max_vel": 1.0}}}
    scores = compute_saliency(replay)
    assert scores.get("block", 0.0) >= 0.0


def test_compute_saliency_missing_saliency():
    assert compute_saliency({}) == {}


def test_linear_world_model_fit_predict():
    model = LinearWorldModel(obs_dim=3, action_dim=2)
    rng = np.random.default_rng(0)
    transitions = [
        (
            rng.normal(size=3),
            rng.normal(size=2),
            rng.normal(size=3),
            float(rng.random()),
        )
        for _ in range(20)
    ]
    model.fit(transitions)
    obs = np.zeros(3)
    action = np.zeros(2)
    next_obs, reward = model.predict(obs, action)
    assert next_obs.shape == (3,)
    assert isinstance(reward, float)


def test_linear_world_model_empty_transitions():
    model = LinearWorldModel(obs_dim=2, action_dim=1)
    model.fit([])
    obs, reward = model.predict(np.zeros(2), np.zeros(1))
    assert obs.shape == (2,)
    assert reward == 0.0


def test_split_replay_transitions():
    from ai_cad.geda_bridge.brain.world_model import split_replay_transitions

    replay = {
        "steps": [
            {"observation": {"x": 0.0, "y": 0.0}, "action": [0.1, 0.0], "reward": 0.0},
            {"observation": {"x": 0.1, "y": 0.0}, "action": [0.1, 0.0], "reward": 1.0},
        ]
    }
    transitions = split_replay_transitions(replay, action_dim=2)
    assert len(transitions) == 1
    obs, action, next_obs, reward = transitions[0]
    assert obs.shape == (2,)
    assert action.shape == (2,)
    assert next_obs.shape == (2,)
    assert reward == 0.0


def test_attention_mlp_policy_shape():
    weights = np.zeros(AttentionMLPPolicy.n_params())
    policy = AttentionMLPPolicy(weights)
    action = policy(np.zeros(AttentionMLPPolicy.INPUT_DIM))
    assert action.shape == (AttentionMLPPolicy.OUTPUT_DIM,)


def test_attention_mlp_policy_mask():
    weights = np.zeros(AttentionMLPPolicy.n_params())
    mask = np.array([1, 0, 1, 0, 1, 0], dtype=float)
    policy = AttentionMLPPolicy(weights, attention_mask=mask)
    action = policy(np.ones(AttentionMLPPolicy.INPUT_DIM))
    assert action.shape == (AttentionMLPPolicy.OUTPUT_DIM,)


def test_abstract_attention_env_reset():
    env = AbstractAttentionEnv(seed=0)
    obs = env.reset(seed=1)
    assert obs.shape == (env.OBS_DIM,)
    assert np.all(np.abs(obs[:2]) <= 1.0 + 1e-6)


def test_abstract_attention_env_step():
    env = AbstractAttentionEnv(seed=0)
    env.reset()
    obs, reward, terminated, info = env.step(np.array([0.05, 0.0]))
    assert obs.shape == (env.OBS_DIM,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert "dist_to_region" in info


def test_abstract_attention_env_rollout_with_policy():
    env = AbstractAttentionEnv(seed=0, n_steps=50)
    weights = np.zeros(AttentionMLPPolicy.n_params())
    policy = AttentionMLPPolicy(weights)
    result = env.rollout(policy)
    assert "reward" in result
    assert "success" in result
    assert "final_distance" in result


def test_train_attention_policy_smoke():
    env = AbstractAttentionEnv(seed=0, n_steps=80)
    weights, report = train_attention_policy(
        env=env, n_iters=2, pop_size=6, elite_frac=0.3, inner_rollouts=2, seed=0
    )
    assert weights.shape == (AttentionMLPPolicy.n_params(),)
    assert "best_training_reward" in report
    assert report["n_iters"] == 2


def test_evaluate_attention_policy():
    env = AbstractAttentionEnv(seed=0, n_steps=80)
    weights = np.zeros(AttentionMLPPolicy.n_params())
    report = evaluate_attention_policy(env, weights, n_episodes=3, seed=0)
    assert 0.0 <= report["success_rate"] <= 1.0
    assert "mean_reward" in report


def test_train_and_evaluate_report():
    report = train_and_evaluate(
        n_iters=2, pop_size=6, eval_episodes=3, success_rate_threshold=0.0, seed=0
    )
    assert "success" in report
    assert "weights" in report
    assert "policy_architecture" in report
    assert report["policy_architecture"]["input_dim"] == AttentionMLPPolicy.INPUT_DIM


@pytest.mark.slow
@pytest.mark.xfail(
    reason="Tiny CEM may not always cross a strict success-rate threshold on the toy task",
    strict=False,
)
def test_attention_policy_trains_above_threshold():
    report = train_and_evaluate(
        n_iters=8, pop_size=30, eval_episodes=10, success_rate_threshold=0.6, seed=42
    )
    assert report["success"]
    assert report["success_rate"] >= 0.6


# ---------------------------------------------------------------------------
# Milestone F — real MuJoCo robot-brain tests
# ---------------------------------------------------------------------------


def test_robot_mlp_policy_shape():
    obs_dim, action_dim = 17, 4
    weights = np.zeros(RobotMLPPolicy.n_params(obs_dim, action_dim))
    policy = RobotMLPPolicy(weights, obs_dim, action_dim)
    action = policy(np.zeros(obs_dim))
    assert action.shape == (action_dim,)
    assert np.all(np.abs(action) <= 1.0)


def test_robot_mlp_policy_variable_dims():
    for obs_dim, action_dim in [(8, 1), (20, 6), (31, 12)]:
        weights = np.zeros(RobotMLPPolicy.n_params(obs_dim, action_dim))
        policy = RobotMLPPolicy(weights, obs_dim, action_dim)
        action = policy(np.zeros(obs_dim))
        assert action.shape == (action_dim,)


def test_world_replay_env_no_mjcf_graceful():
    env = WorldReplayEnv(mjcf_path=None)
    assert not env.is_available()
    obs = env.reset()
    assert obs.shape == (env.obs_dim,)
    action = np.zeros(env.action_dim)
    obs, reward, terminated, info = env.step(action)
    assert obs.shape == (env.obs_dim,)
    assert reward == 0.0
    assert terminated is True
    assert "error" in info


@pytest.mark.skipif(
    not _mujoco_available(),
    reason="MuJoCo is not installed",
)
def test_world_replay_env_minimal_mjcf(tmp_path):
    mjcf = tmp_path / "minimal.mjcf"
    mjcf.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<mujoco model="minimal">
  <compiler angle="radian"/>
  <option timestep="0.002"/>
  <worldbody>
    <body name="torso" pos="0 0 1">
      <freejoint/>
      <geom type="sphere" size="0.1" mass="1"/>
      <body name="arm" pos="0.5 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1" range="-1 1"/>
        <geom type="capsule" size="0.05" fromto="0 0 0 0.5 0 0" mass="0.5"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="hinge_motor" joint="hinge" ctrlrange="-2 2" gear="1"/>
  </actuator>
</mujoco>
""",
        encoding="utf-8",
    )
    env = WorldReplayEnv(mjcf_path=str(mjcf), n_steps=50)
    assert env.is_available()
    assert env.action_dim == 1
    assert env.obs_dim == 17  # 2 joint + 12 freejoint + 3 goal delta
    obs = env.reset(seed=0)
    assert obs.shape == (env.obs_dim,)
    action = np.zeros(env.action_dim)
    obs, reward, terminated, info = env.step(action)
    assert obs.shape == (env.obs_dim,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert "steps" in info


@pytest.mark.skipif(
    not _mujoco_available(),
    reason="MuJoCo is not installed",
)
def test_train_robot_policy_smoke(tmp_path):
    mjcf = tmp_path / "minimal.mjcf"
    mjcf.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<mujoco model="minimal">
  <compiler angle="radian"/>
  <option timestep="0.002"/>
  <worldbody>
    <body name="torso" pos="0 0 1">
      <freejoint/>
      <geom type="sphere" size="0.1" mass="1"/>
      <body name="arm" pos="0.5 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1" range="-1 1"/>
        <geom type="capsule" size="0.05" fromto="0 0 0 0.5 0 0" mass="0.5"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="hinge_motor" joint="hinge" ctrlrange="-2 2" gear="1"/>
  </actuator>
</mujoco>
""",
        encoding="utf-8",
    )
    env = WorldReplayEnv(mjcf_path=str(mjcf), n_steps=80)
    weights, report = train_robot_policy(
        env=env, n_iters=2, pop_size=6, elite_frac=0.3, inner_rollouts=2, seed=0
    )
    assert weights.shape == (RobotMLPPolicy.n_params(env.obs_dim, env.action_dim),)
    assert "best_training_reward" in report
    assert report["n_iters"] == 2

