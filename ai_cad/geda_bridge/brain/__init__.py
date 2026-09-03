"""Phase 25 — lightweight attention-based robot-brain training layer.

The ``brain`` package maps concepts from high-performance / neuromorphic AI
co-design (event-driven sensing, compute budgets, dynamic attention) into a
deterministic, NumPy-only training loop for policies that act on RoboCAD
worlds. It is intentionally dependency-light so it can run end-to-end on the
same machines that already verify the GEDA bridge.

Public exports:
    * ``AttentionWorldModel`` — small linear world model trained from replay.
    * ``AttentionMLPPolicy`` — MLP policy with optional attention masking.
    * ``AbstractAttentionEnv`` — pure-NumPy environment built from a
      ``WorldDescription`` attention task.
    * ``WorldReplayEnv`` — optional MuJoCo-backed environment for real
      generated worlds.
    * ``train_attention_policy`` — CEM trainer with compute-budget regularizer.
    * ``evaluate_attention_policy`` — evaluation harness.
"""
from __future__ import annotations

from ai_cad.geda_bridge.brain.world_model import (
    AttentionBudget,
    LinearWorldModel,
    SaliencySnapshot,
    compute_saliency,
    split_replay_transitions,
)
from ai_cad.geda_bridge.brain.policies import AttentionMLPPolicy
from ai_cad.geda_bridge.brain.envs import AbstractAttentionEnv, WorldReplayEnv
from ai_cad.geda_bridge.brain.trainer import (
    evaluate_attention_policy,
    train_attention_policy,
    train_and_evaluate,
)

__all__ = [
    "AttentionBudget",
    "LinearWorldModel",
    "SaliencySnapshot",
    "compute_saliency",
    "split_replay_transitions",
    "AttentionMLPPolicy",
    "AbstractAttentionEnv",
    "WorldReplayEnv",
    "train_attention_policy",
    "evaluate_attention_policy",
    "train_and_evaluate",
]
