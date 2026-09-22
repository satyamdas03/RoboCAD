# RoboCAD 7.7 → 10.0 — Milestone F: Real MuJoCo Brain Training on Generated Robots

**Date:** 2026-09-20
**Current baseline:** Milestones A, B, C, D, and **E** complete, **402 default + 261 heavy/slow/mujoco tests passing** (1 xfailed), frontend build passes, honest complex-design confidence **9.0 / 10**.
**Target:** **9.3 / 10** by replacing the 2-D `AbstractAttentionEnv` brain smoke test with a real `WorldReplayEnv` that trains policies on the generated MJCF robot model.
**Owner focus:** `ai_cad/geda_bridge/brain/envs.py`, `ai_cad/geda_bridge/brain/policies.py`, `ai_cad/geda_bridge/brain/trainer.py`, `web/backend/main.py`.
**Spec precedents:** [[milestone-e-topology-grammar]], [[milestone-d-end-effector-families]], [[phase25-attention-brain]].

---

## 1. Goal

A morphology candidate exported from RoboCAD can be loaded into a real MuJoCo environment and a closed-loop policy can be trained on it with a deterministic, NumPy-only training loop. The `/morphology/{search_id}/candidates/{candidate_id}/simulate` endpoint must run this real training instead of the 2-D attention abstraction.

The system must:

1. Load the exported world MJCF (including the included robot MJCF).
2. Discover the robot's actuators, joints, torso, and task bodies.
3. Build a robot-specific observation vector.
4. Train a small MLP policy via CEM on real MuJoCo rollouts.
5. Return measurable reward/success metrics from the real robot.

---

## 2. What 9.3/10 means here

At 9.3/10, RoboCAD's brain training smoke test is no longer a toy 2-D navigation task. It actually controls the generated robot model in simulation. This is a meaningful step toward the 10/10 vision of robots that are "born controllable."

The score moves from **9.0 → 9.3/10** because the *same generated robot model* that scores 0.8+ on morphology is now used as the plant for policy training, closing the abstraction gap between morphology search and robot control.

---

## 3. Gap this closes

| Gap | Evidence before Milestone F | Status after Milestone F |
|---|---|---|
| Brain smoke test is a 2-D abstraction | `AbstractAttentionEnv` does not touch the MuJoCo humanoid | ✅ `WorldReplayEnv` loads and rolls out the generated MJCF |
| Policy has fixed 6→12→2 shape | `AttentionMLPPolicy` only works for the toy task | ✅ `RobotMLPPolicy` adapts to the env's observation/action dimensions |
| No real training on robot MJCF | `/morphology/.../simulate` runs `train_attention_policy` on `AbstractAttentionEnv` | ✅ Endpoint trains `RobotMLPPolicy` on the actual robot model |

---

## 4. Architecture

### 4.1 Core data model

`WorldReplayEnv` in `ai_cad/geda_bridge/brain/envs.py`:

- `mjcf_path`: exported world MJCF file.
- `world`: optional `WorldDescription` for task metadata.
- Discovered at load time:
  - `action_dim = model.nu`
  - `obs_dim`: 2 * n_hinge/slide_joints + 12 (freejoint torso state) + 3 (goal delta) + optional 3 (object delta)
  - `ctrl_low`, `ctrl_high` per actuator
  - torso body id via alias resolver
  - goal position from `WorldTask.goal_regions`
  - object body id for manipulation tasks

### 4.2 Observation

Normalized, robot-specific vector:

- For each hinge/slide joint: normalized qpos + clipped qvel.
- Freejoint torso state: position (3), gravity vector from torso xmat (3), linear velocity (3), angular velocity (3).
- Task error: delta from torso to goal (3); optionally delta from object to goal (3).

### 4.3 Action

Normalized `[-1, 1]^nu` control vector, scaled per actuator to its `ctrlrange`.

### 4.4 Reward functions

Per `task.task_type`:

- `walker`: alive bonus + forward progress toward goal + upright bonus - control penalty.
- `humanoid_stand`: alive bonus + height reward - control penalty.
- `push`: negative object-to-goal distance - control penalty.
- `pick_place`: negative object-to-goal distance + lift bonus - control penalty.

### 4.5 Policy and trainer

- `RobotMLPPolicy` in `policies.py`: `[obs_dim, 32, action_dim]` ReLU MLP; flat weight vector via `n_params(obs_dim, action_dim)`.
- `train_robot_policy` in `trainer.py`: NumPy-only CEM, same pattern as `skill_smoke.py`, with inner-rollout averaging for noise robustness.

### 4.6 Backend wiring

`/morphology/{search_id}/candidates/{candidate_id}/simulate`:

1. Export bundle from candidate `FeatureTree`.
2. Build world with requested template.
3. For locomotion templates, post-process robot MJCF with `_scale_masses_and_add_freejoint`.
4. Export world MJCF.
5. Build `WorldReplayEnv` and train/evaluate `RobotMLPPolicy`.
6. Return real metrics; fallback to `AbstractAttentionEnv` if MuJoCo unavailable.

---

## 5. Detailed deliverables and acceptance

### 5.1 Module: `ai_cad/geda_bridge/brain/envs.py`

**Functions to implement / complete:**

- `WorldReplayEnv.__init__`: load MJCF, discover structure, resolve task, compute obs_dim.
- `WorldReplayEnv.reset`: reset MuJoCo data with optional state noise.
- `WorldReplayEnv.step`: scale action, step physics, compute reward, check termination.
- `WorldReplayEnv.rollout`: run one episode with a policy and return reward/success/distance.

**Acceptance:**
- Loads a minimal MJCF with freejoint + hinge joint + actuator.
- `reset()` and `step()` return correct observation shapes.
- `rollout()` returns a dict with `reward`, `success`, `final_distance`, `steps`, `task_type`.

### 5.2 Module: `ai_cad/geda_bridge/brain/policies.py`

**Functions to implement:**

- `RobotMLPPolicy.n_params(obs_dim, action_dim)` classmethod.
- `RobotMLPPolicy.__call__(obs)` forward pass with output clipped to `[-1, 1]`.

**Acceptance:**
- Policy works for multiple `(obs_dim, action_dim)` pairs.
- Weight vector shape matches `n_params`.

### 5.3 Module: `ai_cad/geda_bridge/brain/trainer.py`

**Functions to implement:**

- `train_robot_policy(env, n_iters, pop_size, elite_frac, inner_rollouts, seed)`.
- `evaluate_robot_policy(env, weights, n_episodes, seed)`.
- `train_and_evaluate_robot(env, ...)` high-level entry point.

**Acceptance:**
- Trains a policy on a minimal MJCF in a tiny CEM run.
- Returns JSON-serializable report with weights and metrics.

### 5.4 Backend: `web/backend/main.py`

**Changes:**

- Import `WorldReplayEnv`, `RobotMLPPolicy`, `train_robot_policy`, `evaluate_robot_policy`, `train_and_evaluate_robot`.
- In `/morphology/{search_id}/candidates/{candidate_id}/simulate`, export world MJCF, add freejoint, build `WorldReplayEnv`, train real policy, evaluate, return metrics.
- Keep `AbstractAttentionEnv` fallback for non-MuJoCo environments.

**Acceptance:**
- Endpoint returns a `brain_smoke_test` report with real reward/success/obs_dim/action_dim when MuJoCo is available.
- Does not raise 500 if MuJoCo is absent (graceful fallback).

### 5.5 Tests

**New test files / additions:**

- `tests/test_geda_bridge_brain.py`
  - `test_robot_mlp_policy_shape`
  - `test_world_replay_env_no_mjcf_graceful`
  - `test_world_replay_env_minimal_mjcf`
  - `test_train_robot_policy_smoke`
- `tests/test_morphology_brain.py` (slow/heavy)
  - `test_brain_train_on_generated_humanoid`
  - `test_brain_train_on_generated_quadruped`

**Acceptance:**
- Default suite passes.
- Heavy/slow tests pass under `--timeout=600`.

---

## 6. Roadmap integration

| Milestone | Target score | Status |
|---|---|---|
| A — Adaptive gait | 7.7 → 8.0 | ✅ Complete |
| B — Structural dynamics | 8.0 → 8.3 | ✅ Complete |
| C — Workspace / collision / manipulability | 8.3 → 8.5 | ✅ Complete |
| D — Real end-effector families | 8.5 → 8.7 | ✅ Complete |
| E — Topology grammar | 8.7 → 9.0 | ✅ Complete |
| **F — Real MuJoCo brain training** | **9.0 → 9.3** | **✅ Complete** |
| G — Automatic certification | 9.3 → 9.6 | Planned |
| H — Sim-to-real | 9.6 → 9.8 | Hardware-gated |
| I — Fully automated voice-to-certified-design | 9.8 → 10.0 | Planned |

---

## 7. Final verification

- `python -m pytest -q` → **407 passed, 261 deselected, 3 warnings in ~480 s** ✅
- `python -m pytest -m "slow or heavy or mujoco" -q` → **261 passed, 407 deselected, 1 xfailed, 2 xpassed in ~1644 s** ✅
- Frontend production build not changed; previous build passes ✅
- Honest complex-design confidence: **9.3 / 10** ✅

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Variable action space across robots | Discover actuators from MJCF at load time; policy dims set per env instance. |
| Training instability on real robots | Small `n_steps`, conservative control scaling, alive bonus, domain randomization only for seeds. |
| MuJoCo not installed | `WorldReplayEnv.is_available()` returns false; tests skip; backend falls back to abstract env. |
| Backend timeouts | Endpoint supports tuning `n_iters`/`pop_size`; heavy tests use `--timeout=600`. |
| Generated robot lacks freejoint | Post-process locomotion templates with `_scale_masses_and_add_freejoint`; skip for fixed-base templates. |

---

## 9. First three concrete actions (Milestone G)

1. **Design randomized certification load cases** — extend `ai_cad/sim_certification.py` with terrain, payload, push, drop, actuator-saturation tests.
2. **Wire certification into the design flow** — run certification automatically after morphology search / brain training.
3. **Score and badge designs** — present pass/fail per load case and an overall readiness score.

---

*Spec written and committed to `docs/superpowers/specs/2026-09-20-milestone-f-real-mujoco-brain.md`.*
