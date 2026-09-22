# Milestone F — Real MuJoCo Brain Training on Generated Robot Models

## Objective
Replace the 2-D `AbstractAttentionEnv` brain smoke test with a real MuJoCo `WorldReplayEnv` that trains NumPy-only MLP policies on the generated MJCF robot models produced by morphology search. This is the honest next step from score 9.0 → 9.3.

## Design

### 1. `WorldReplayEnv` (real MuJoCo wrapper)
- Load the combined world MJCF exported by `export_world_to_mjcf`.
- Inspect the model to discover:
  - `nu` actuators → action dimension.
  - Joint DOFs and freejoint pose → observation dimension.
  - Body names via `resolve_body_alias` to find torso/goal/object references.
- Observation (fixed schema, variable size):
  - Normalized joint positions/velocities for all non-free joints.
  - Free-joint torso pose/orientation/velocity if present.
  - Goal/error terms from `WorldTask` (delta to goal position, object-to-goal delta).
  - Optional IMU accelerometer/gyro readings if sensors exist.
- Action: normalized `[-1, 1]^nu` control vector, scaled to each actuator's `ctrlrange`.
- Reward functions per `task.task_type`:
  - `walker`: forward progress toward goal + upright torso reward + control penalty + alive bonus.
  - `humanoid_stand`: upright torso reward + small height bonus + control penalty + alive bonus.
  - `push`: negative object-to-goal distance + control penalty.
  - `pick_place`: object-lift + object-to-goal distance reward.
- Domain randomization support via `apply_domain_randomization` for training robustness.

### 2. Generalized NumPy MLP policy
- New `RobotMLPPolicy` in `ai_cad/geda_bridge/brain/policies.py`.
- Architecture: `[obs_dim, hidden_dim, action_dim]` with fixed `hidden_dim=32`.
- `n_params(obs_dim, action_dim)` classmethod computes deterministic flat weight count.
- Policy instance stores `obs_dim`/`action_dim` and unpacks weights accordingly.
- Keep `AttentionMLPPolicy` unchanged for backward compatibility with existing tests.

### 3. Generalized CEM trainer
- New `train_robot_policy` and `evaluate_robot_policy` in `ai_cad/geda_bridge/brain/trainer.py`.
- Mirror `train_policy_cem` from `skill_smoke.py`:
  - population sampling, elite selection, mean/std update.
  - inner_rollouts for noise robustness.
  - seed control.
- Support both `AbstractAttentionEnv` (legacy) and `WorldReplayEnv` via duck typing.

### 4. Backend wiring
- Update `/morphology/{search_id}/candidates/{candidate_id}/simulate` in `web/backend/main.py`:
  - Export the world MJCF to `sim_dir / "world.mjcf"` using `export_world_to_mjcf`.
  - Instantiate `WorldReplayEnv(mjcf_path=..., world=world)`.
  - Train with `train_robot_policy`.
  - Evaluate with `evaluate_robot_policy`.
  - Keep `AbstractAttentionEnv` fallback path behind a feature flag / graceful degrade if MuJoCo unavailable.

### 5. Public API surface
- `ai_cad/geda_bridge/brain/__init__.py` exports `RobotMLPPolicy`, `train_robot_policy`, `evaluate_robot_policy`, `WorldReplayEnv`.
- Keep all existing exports for backward compatibility.

### 6. Tests
- **Default suite** (`tests/test_geda_bridge_brain.py` additions):
  - `test_world_replay_env_available` — loads simple world, checks shape/availability.
  - `test_world_replay_env_reset_step` — reset/step shape contracts.
  - `test_robot_mlp_policy_shape` — variable-dim policy forward pass.
  - `test_train_robot_policy_smoke` — tiny CEM on a lightweight env/robot.
- **Heavy/slow suite** (`tests/test_geda_bridge_brain.py` or new `tests/test_morphology_brain.py`):
  - End-to-end train a real generated humanoid/quadruped world and verify mean reward improves or a non-zero success signal is achieved.
  - Mark with `@pytest.mark.slow` / `@pytest.mark.heavy` and optional `@pytest.mark.xfail` if tiny CEM cannot guarantee a strict threshold on a real robot.

### 7. Risks & mitigation
- **Variable action space across robots**: discover actuators from MJCF at load time; policy dims set per env instance.
- **Training instability on real robots**: use small `n_steps`, conservative control scaling, alive bonus, and domain randomization only during evaluation seeds.
- **MuJoCo not installed**: env returns `is_available=False`; tests skip gracefully; backend still returns a report.
- **Backend timeouts**: morphology simulate endpoint already supports tuning `n_iters`/`pop_size`; heavy tests use `--timeout=300/600`.

## Files to change
1. `ai_cad/geda_bridge/brain/envs.py` — implement real `WorldReplayEnv`.
2. `ai_cad/geda_bridge/brain/policies.py` — add `RobotMLPPolicy`.
3. `ai_cad/geda_bridge/brain/trainer.py` — add `train_robot_policy` / `evaluate_robot_policy`.
4. `ai_cad/geda_bridge/brain/__init__.py` — export new symbols.
5. `web/backend/main.py` — wire real env into morphology simulate endpoint.
6. `tests/test_geda_bridge_brain.py` — add default smoke tests.
7. `tests/test_morphology_brain.py` — add slow/heavy end-to-end tests.
8. Memory/dossier updates after verification.

## Acceptance criteria
- `WorldReplayEnv` can load an exported world MJCF and run a closed-loop rollout.
- `RobotMLPPolicy` adapts its input/output dimensions to the env's discovered observation/action size.
- A real generated walker/humanoid world can be trained end-to-end via CEM and produce measurable reward/success metrics.
- Default pytest suite passes (existing tests unchanged).
- Heavy/slow tests pass under `--timeout=300/600`.
- Frontend build passes if no frontend changes are made.
- Score revised 9.0 → 9.3 in memory and dossiers.
