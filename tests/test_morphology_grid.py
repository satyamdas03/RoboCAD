"""Grid regression tests for morphology gait robustness (Milestone A)."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.mujoco]


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


def test_physics_score_candidate_uses_sweep():
    _skip_if_no_mujoco()
    from ai_cad.morphology_physics import physics_score_candidate
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["mujoco_available"] is True
    assert "walk_score" in result
    assert result["walk_score"] >= 0.0
    assert result["walk_score"] <= 1.0


def test_humanoid_grid_walk_rate():
    _skip_if_no_mujoco()
    from ai_cad.morphology import MorphologyDimension, MorphologySpace, _make_tree, _attach_end_effector, _scale_joint_limits
    from ai_cad.morphology_physics import physics_score_candidate
    import numpy as np
    import itertools

    # Focus the humanoid grid tightly around the nominal 1000 mm / 220 mm
    # thigh / 240 mm shin template. Full cross-size robustness across the
    # entire default_space needs per-candidate actuator sizing (Milestone B).
    space = MorphologySpace(
        template="humanoid",
        dimensions=[
            MorphologyDimension("robot_height", 1000.0, 1000.0, 1.0),
            MorphologyDimension("thigh_length", 200.0, 240.0, 20.0),
            MorphologyDimension("shin_length", 220.0, 260.0, 20.0),
        ],
        limb_counts=[2],
        end_effectors=["default"],
        n_max=9,
        seed=0,
    )
    rng = np.random.default_rng(space.seed)
    values = [d.values() for d in space.dimensions]
    products = list(itertools.product(*values))
    if len(products) > space.n_max:
        idx = np.linspace(0, len(products) - 1, space.n_max).astype(int)
        jitter = rng.integers(-1, 2, size=len(idx))
        idx = np.clip(idx + jitter, 0, len(products) - 1)
        idx = sorted(set(int(i) for i in idx))
        products = [products[i] for i in idx]

    walk_ok_count = 0
    for combo in products:
        params: dict[str, float] = {}
        for dim, value in zip(space.dimensions, combo):
            params[dim.name] = float(value)
        tree = _make_tree("humanoid", params)
        tree = _attach_end_effector(tree, "default")
        result = physics_score_candidate(tree, n_steps=100)
        if result["walk_ok"]:
            walk_ok_count += 1

    # Milestone A target: at least 40% of focused humanoid grid candidates walk.
    assert walk_ok_count >= int(0.40 * len(products)), f"only {walk_ok_count}/{len(products)} humanoid candidates walked"


def test_quadruped_grid_walk_rate():
    _skip_if_no_mujoco()
    from ai_cad.morphology import default_space, search_morphologies

    space = default_space("quadruped")
    space.n_max = 12
    space.end_effectors = ["default"]
    candidates = search_morphologies(space, payload_kg=2.0, robot_mass_kg=12.0, use_physics=True)
    walk_ok_count = sum(1 for c in candidates if c.scores.get("physics_walk_score", 0.0) >= 0.5)
    # Milestone A target: at least 75% of quadruped grid candidates walk.
    assert walk_ok_count >= int(0.75 * len(candidates)), f"only {walk_ok_count}/{len(candidates)} quadruped candidates walked"


def test_humanoid_mass_perturbation_walk_rate():
    _skip_if_no_mujoco()
    from ai_cad.morphology_physics import physics_score_candidate
    from ai_cad.robot_templates import humanoid_template

    base_tree = humanoid_template()
    perturbations = [
        (15.0, 2.5),
        (20.0, 5.0),
        (25.0, 5.0),
        (30.0, 5.0),
    ]
    ok = 0
    for mass, payload in perturbations:
        tree = base_tree.update_parameter("robot_mass_kg", mass)
        result = physics_score_candidate(tree, n_steps=100)
        if result["walk_ok"]:
            ok += 1
    # Milestone A target: at least 50% of mass perturbations walk.
    assert ok >= 2, f"only {ok}/{len(perturbations)} mass perturbations walked"
