"""Cross-Entropy Method trainer for attention-aware robot-brain policies.

Keeps the same deterministic NumPy-only approach used in
``ai_cad.geda_bridge.skill_smoke`` so the brain layer can be tested and
shipped without installing PyTorch or JAX.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ai_cad.geda_bridge.brain.envs import AbstractAttentionEnv
from ai_cad.geda_bridge.brain.policies import AttentionMLPPolicy
from ai_cad.geda_bridge.brain.world_model import AttentionBudget


def train_attention_policy(
    env: AbstractAttentionEnv | None = None,
    budget: AttentionBudget | None = None,
    n_iters: int = 15,
    pop_size: int = 40,
    elite_frac: float = 0.2,
    inner_rollouts: int = 3,
    seed: int = 0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Train an ``AttentionMLPPolicy`` via CEM.

    The reward used during evolution is the mean episode return across a small
    handful of seeds, which reduces the noise inherent in a single rollout.
    """
    if env is None:
        env = AbstractAttentionEnv(budget=budget, seed=seed)

    rng = np.random.default_rng(seed)
    n_params = AttentionMLPPolicy.n_params()
    mean = np.zeros(n_params)
    std = np.ones(n_params)
    best_weights = mean.copy()
    best_reward = -float("inf")
    history: list[float] = []

    for it in range(n_iters):
        samples = [rng.normal(mean, std) for _ in range(pop_size)]
        rewards: list[float] = []
        for s in samples:
            policy = AttentionMLPPolicy(s)
            rew = 0.0
            for k in range(inner_rollouts):
                result = env.rollout(policy, seed=it * pop_size + k)
                rew += result["reward"]
            rewards.append(rew / inner_rollouts)
        rewards = np.asarray(rewards)
        elite_count = max(1, int(round(pop_size * elite_frac)))
        elite_idx = np.argsort(rewards)[::-1][:elite_count]
        elite = np.array([samples[i] for i in elite_idx])
        mean = elite.mean(axis=0)
        std = elite.std(axis=0) + 1e-3
        history.append(float(rewards[elite_idx[0]]))
        if rewards[elite_idx[0]] > best_reward:
            best_reward = float(rewards[elite_idx[0]])
            best_weights = elite[0].copy()

    report = {
        "best_training_reward": best_reward,
        "final_mean_reward": float(np.mean(history[-5:])) if history else 0.0,
        "n_iters": n_iters,
        "pop_size": pop_size,
        "elite_frac": elite_frac,
        "history": history,
    }
    return best_weights, report


def evaluate_attention_policy(
    env: AbstractAttentionEnv,
    weights: np.ndarray,
    n_episodes: int = 10,
    seed: int = 0,
) -> dict[str, Any]:
    """Evaluate a trained policy over several episodes."""
    policy = AttentionMLPPolicy(weights)
    results = [env.rollout(policy, seed=seed + i) for i in range(n_episodes)]
    success_rate = (
        float(sum(1 for r in results if r["success"]) / len(results))
        if results
        else 0.0
    )
    return {
        "n_episodes": n_episodes,
        "success_rate": success_rate,
        "mean_reward": float(np.mean([r["reward"] for r in results])) if results else 0.0,
        "mean_final_distance": float(
            np.mean([r["final_distance"] for r in results])
        )
        if results
        else 0.0,
        "rollouts": results,
    }


def train_and_evaluate(
    n_iters: int = 15,
    pop_size: int = 40,
    eval_episodes: int = 10,
    success_rate_threshold: float = 0.7,
    seed: int = 42,
) -> dict[str, Any]:
    """High-level entry point: train + evaluate a default attention brain.

    Returns a JSON-serialisable report with weights and metrics.
    """
    env = AbstractAttentionEnv(seed=seed)
    best_weights, train_report = train_attention_policy(
        env=env, n_iters=n_iters, pop_size=pop_size, seed=seed
    )
    eval_report = evaluate_attention_policy(
        env, best_weights, n_episodes=eval_episodes, seed=seed
    )
    report = {
        "success": bool(eval_report["success_rate"] >= success_rate_threshold),
        "success_rate": eval_report["success_rate"],
        "mean_reward": eval_report["mean_reward"],
        "mean_final_distance": eval_report["mean_final_distance"],
        "best_training_reward": train_report["best_training_reward"],
        "weights": best_weights.tolist(),
        "n_params": int(AttentionMLPPolicy.n_params()),
        "policy_architecture": {
            "input_dim": AttentionMLPPolicy.INPUT_DIM,
            "hidden_dim": AttentionMLPPolicy.HIDDEN_DIM,
            "output_dim": AttentionMLPPolicy.OUTPUT_DIM,
        },
        "train_report": train_report,
        "eval_report": {
            "n_episodes": eval_report["n_episodes"],
            "success_rate": eval_report["success_rate"],
            "mean_reward": eval_report["mean_reward"],
            "mean_final_distance": eval_report["mean_final_distance"],
        },
    }
    return report
