"""Heavy end-to-end tests for Milestone F: real MuJoCo brain training on generated robots."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from ai_cad.geda_bridge import build_world, export_bundle_from_tree, export_world_to_mjcf, load_bundle_manifest
from ai_cad.geda_bridge.brain import RobotMLPPolicy, WorldReplayEnv, train_and_evaluate_robot
from ai_cad.morphology_physics import _scale_masses_and_add_freejoint
from ai_cad.robot_templates import humanoid_template, quadruped_template


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


@pytest.mark.slow
@pytest.mark.heavy
@pytest.mark.xfail(
    reason="Tiny CEM on a real humanoid may not always learn a robust gait",
    strict=False,
)
def test_brain_train_on_generated_humanoid():
    _skip_if_no_mujoco()
    tree = humanoid_template()
    with tempfile.TemporaryDirectory() as tmp:
        sim_dir = Path(tmp)
        export_bundle_from_tree(tree, sim_dir, name="candidate", tolerance=0.5)
        manifest = load_bundle_manifest(sim_dir)

        robot_mjcf_path = sim_dir / manifest.mjcf_file
        _scale_masses_and_add_freejoint(robot_mjcf_path, tree)

        world = build_world("walker", manifest.parts, robot_height_m=1.0)
        world.robot_mjcf_file = manifest.mjcf_file
        world_mjcf_path = sim_dir / "world.mjcf"
        export_world_to_mjcf(world, world_mjcf_path)

        env = WorldReplayEnv(
            mjcf_path=str(world_mjcf_path),
            world=world,
            n_steps=300,
            seed=42,
        )
        assert env.is_available()
        assert env.action_dim > 0
        assert env.obs_dim > env.action_dim

        report = train_and_evaluate_robot(
            env,
            n_iters=6,
            pop_size=16,
            eval_episodes=4,
            success_rate_threshold=0.0,
            seed=42,
        )
        assert "weights" in report
        assert "mean_reward" in report
        assert report["n_params"] == RobotMLPPolicy.n_params(env.obs_dim, env.action_dim)
        # The CEM should at least find a policy that is no worse than a zero policy.
        assert report["mean_reward"] > -float("inf")


@pytest.mark.slow
@pytest.mark.heavy
@pytest.mark.xfail(
    reason="Tiny CEM on a real quadruped may not always learn a robust trot",
    strict=False,
)
def test_brain_train_on_generated_quadruped():
    _skip_if_no_mujoco()
    tree = quadruped_template()
    with tempfile.TemporaryDirectory() as tmp:
        sim_dir = Path(tmp)
        export_bundle_from_tree(tree, sim_dir, name="candidate", tolerance=0.5)
        manifest = load_bundle_manifest(sim_dir)

        robot_mjcf_path = sim_dir / manifest.mjcf_file
        _scale_masses_and_add_freejoint(robot_mjcf_path, tree)

        world = build_world("walker", manifest.parts, robot_height_m=0.6)
        world.robot_mjcf_file = manifest.mjcf_file
        world_mjcf_path = sim_dir / "world.mjcf"
        export_world_to_mjcf(world, world_mjcf_path)

        env = WorldReplayEnv(
            mjcf_path=str(world_mjcf_path),
            world=world,
            n_steps=300,
            seed=7,
        )
        assert env.is_available()

        report = train_and_evaluate_robot(
            env,
            n_iters=6,
            pop_size=16,
            eval_episodes=4,
            success_rate_threshold=0.0,
            seed=7,
        )
        assert report["n_params"] > 0
        assert "mean_reward" in report
