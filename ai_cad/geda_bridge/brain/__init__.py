"""Phase 25 — lightweight attention-based robot-brain training layer.

The ``brain`` package maps concepts from high-performance / neuromorphic AI
co-design (event-driven sensing, compute budgets, dynamic attention) into a
deterministic, NumPy-only training loop for policies that act on RoboCAD
worlds. It is intentionally dependency-light so it can run end-to-end on the
same machines that already verify the GEDA bridge.

Public exports:
    * ``AttentionWorldModel`` — small linear world model trained from replay.
    * ``AttentionMLPPolicy`` — fixed 6->12->2 MLP for the abstract attention
      task; kept for backward compatibility.
    * ``RobotMLPPolicy`` — variable-dimension MLP for real MuJoCo robots.
    * ``AbstractAttentionEnv`` — pure-NumPy environment built from a
      ``WorldDescription`` attention task.
    * ``WorldReplayEnv`` — MuJoCo-backed environment for real generated worlds.
    * ``train_attention_policy`` — CEM trainer for the abstract env.
    * ``evaluate_attention_policy`` — evaluation harness for the abstract env.
    * ``train_robot_policy`` / ``evaluate_robot_policy`` / ``train_and_evaluate_robot``
      — CEM trainer + evaluation for real MuJoCo robots.
"""
from __future__ import annotations

from ai_cad.geda_bridge.brain.world_model import (
    AttentionBudget,
    LinearWorldModel,
    SaliencySnapshot,
    compute_saliency,
    split_replay_transitions,
)
from ai_cad.geda_bridge.brain.policies import AttentionMLPPolicy, RobotMLPPolicy
from ai_cad.geda_bridge.brain.envs import AbstractAttentionEnv, WorldReplayEnv
from ai_cad.geda_bridge.brain.trainer import (
    evaluate_attention_policy,
    evaluate_robot_policy,
    train_and_evaluate,
    train_and_evaluate_robot,
    train_attention_policy,
    train_robot_policy,
)

__all__ = [
    "AttentionBudget",
    "LinearWorldModel",
    "SaliencySnapshot",
    "compute_saliency",
    "split_replay_transitions",
    "AttentionMLPPolicy",
    "RobotMLPPolicy",
    "AbstractAttentionEnv",
    "WorldReplayEnv",
    "train_attention_policy",
    "evaluate_attention_policy",
    "train_and_evaluate",
    "train_robot_policy",
    "evaluate_robot_policy",
    "train_and_evaluate_robot",
]
