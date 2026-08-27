"""Tests for Phase 15B — skill recommendation, variant sweep, and trainable policy smoke test."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import mujoco
except Exception:  # pragma: no cover - optional dependency
    mujoco = None

from ai_cad.geda_bridge.skill_recommend import list_skills, recommend_skill
from ai_cad.geda_bridge.skill_smoke import PushSkillEnv, TinyMLPPolicy, train_policy_cem, train_push_skill
from ai_cad.geda_bridge.variant_sweep import generate_variants, linear_sweep_values


class TestSkillRecommend:
    def test_recommend_push(self):
        rec = recommend_skill("push the red block to the green goal")
        assert rec.template == "wedge_push_block"
        assert rec.confidence > 0.0
        assert rec.goal_pos == (0.55, 0.0, 0.49)

    def test_recommend_grasp(self):
        rec = recommend_skill("grasp and lift the cube")
        assert rec.template == "gripper_cube_grasp"

    def test_recommend_hang(self):
        rec = recommend_skill("hang the bracket on a hook")
        assert rec.template == "bracket_hook_hang"

    def test_recommend_insert(self):
        rec = recommend_skill("insert the peg into the hole")
        assert rec.template == "peg_insertion"

    def test_list_skills(self):
        skills = list_skills()
        assert "wedge_push_block" in skills
        assert "keywords" in skills["wedge_push_block"]


@pytest.mark.skipif(mujoco is None, reason="mujoco not installed")
class TestSkillSmoke:
    def test_tiny_mlp_policy_shape(self):
        n = TinyMLPPolicy.n_params()
        weights = np.zeros(n)
        policy = TinyMLPPolicy(weights)
        obs = np.array([0.1, 0.0, -0.05])
        action = policy(obs)
        assert isinstance(action, float)

    def test_env_rollout_no_mesh(self):
        env = PushSkillEnv(n_steps=100)
        policy = TinyMLPPolicy(np.zeros(TinyMLPPolicy.n_params()))
        result = env.rollout(policy, seed=1)
        assert "final_block_x_m" in result
        assert "success" in result
        assert isinstance(result["success"], bool)

    def test_train_policy_cem_fast(self):
        env = PushSkillEnv(n_steps=100, success_radius_m=0.2)
        weights, reward = train_policy_cem(env, n_iters=3, pop_size=10, seed=7)
        assert weights.shape == (TinyMLPPolicy.n_params(),)
        assert reward > -float("inf")
        policy = TinyMLPPolicy(weights)
        eval_report = env.evaluate(policy, n_episodes=3)
        assert 0.0 <= eval_report["success_rate"] <= 1.0

    def test_train_push_skill_report(self, tmp_path):
        report = train_push_skill(
            output_dir=tmp_path,
            n_iters=3,
            pop_size=10,
            eval_episodes=3,
            success_radius_m=0.2,
        )
        assert "success" in report
        assert "success_rate" in report
        assert "weights" in report
        assert "policy_architecture" in report
        assert (tmp_path / "skill_policy.json").exists()


class TestVariantSweep:
    def test_linear_sweep_values_relative(self):
        values = linear_sweep_values("length", 100.0, {"relative_min": -0.1, "relative_max": 0.1}, 5)
        assert values[0] == pytest.approx(90.0)
        assert values[-1] == pytest.approx(110.0)
        assert len(values) == 5

    def test_linear_sweep_values_min_max(self):
        values = linear_sweep_values("width", 50.0, {"min": 10.0, "max": 20.0}, 3)
        assert values == pytest.approx([10.0, 15.0, 20.0])

    def test_linear_sweep_values_step(self):
        values = linear_sweep_values("height", 30.0, {"step": 5.0}, 3)
        assert values == pytest.approx([25.0, 30.0, 35.0])

    def test_generate_variants_from_feature_tree(self, tmp_path):
        tree = {
            "schema_version": "1.0.0",
            "design_id": "test",
            "prompt": "test part",
            "created_at": "2026-08-25T00:00:00Z",
            "name": "test",
            "parameters": [
                {"name": "length", "value": 100.0, "unit": "mm", "description": "len"}
            ],
            "features": [],
            "assemblies": [],
        }
        tree_path = tmp_path / "feature_tree.json"
        tree_path.write_text(json.dumps(tree), encoding="utf-8")
        from ai_cad.feature_tree import FeatureTree

        variants = generate_variants(tree_path, {"length": {"relative_min": -0.1, "relative_max": 0.1}}, n_variants=3)
        assert len(variants) == 3
        values = [p.value for tree in variants for p in tree.parameters if p.name == "length"]
        assert values == pytest.approx([90.0, 100.0, 110.0])
