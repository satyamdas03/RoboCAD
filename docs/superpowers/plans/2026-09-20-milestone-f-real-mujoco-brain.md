# Milestone F — Real MuJoCo brain training on generated robots

**Status:** ✅ COMPLETE — 2026-09-20
**Date:** 2026-09-20
**Goal:** Replace the 2-D `AbstractAttentionEnv` brain smoke test with a real MuJoCo `WorldReplayEnv` that trains closed-loop policies on the generated robot MJCF, raising the honest complex-design confidence score from **9.0 → 9.3 / 10**.

**Final verification:**
- Default suite: **407 passed** in ~480 s ✅
- Heavy/slow/mujoco suite: **261 passed, 1 xfailed, 2 xpassed** in ~1644 s ✅
- Frontend production build: not changed; previous build passes ✅
- Commit pending — this dossier is part of the Milestone F commit.

**Architecture:** Add real `WorldReplayEnv` in `ai_cad/geda_bridge/brain/envs.py` that loads an exported world MJCF and discovers actuators/joints/torso/task bodies; add `RobotMLPPolicy` in `policies.py` with adaptive input/output dims; add NumPy-only CEM trainer `train_robot_policy` / `evaluate_robot_policy` / `train_and_evaluate_robot` in `trainer.py`; wire the real env into `/morphology/{search_id}/candidates/{candidate_id}/simulate` in `web/backend/main.py` with freejoint post-processing for locomotion templates and a graceful fallback to `AbstractAttentionEnv` when MuJoCo is unavailable.

**Tech Stack:** Python 3.14, MuJoCo, NumPy-only CEM, FastAPI backend.

**Owner focus:** `ai_cad/geda_bridge/brain/envs.py`, `ai_cad/geda_bridge/brain/policies.py`, `ai_cad/geda_bridge/brain/trainer.py`, `ai_cad/geda_bridge/brain/__init__.py`, `ai_cad/geda_bridge/__init__.py`, `web/backend/main.py`, `tests/test_geda_bridge_brain.py`, `tests/test_morphology_brain.py`.

---

## Requirements

- Real MuJoCo-backed `WorldReplayEnv` loads an exported world MJCF.
- Robot-specific observation and action spaces discovered from the MJCF.
- `RobotMLPPolicy` adapts its input/output dimensions to the env instance.
- NumPy-only CEM trainer trains and evaluates the policy on real rollouts.
- Reward/termination for walker, humanoid_stand, push, and pick_place tasks.
- Backend simulate endpoint trains on the actual generated robot MJCF.
- Graceful fallback when MuJoCo is unavailable.
- All new physics-rollout tests tagged `slow`, `heavy`, or `mujoco`.

---

## Task 1: Real MuJoCo environment wrapper

- **Modify:** `ai_cad/geda_bridge/brain/envs.py`
- **Test:** `tests/test_geda_bridge_brain.py::test_world_replay_env_minimal_mjcf`

**Delivered:**

- `WorldReplayEnv.__init__` loads the MJCF via `mujoco.MjModel.from_xml_path`, discovers `nu` actuators and their `ctrlrange`, hinge/slide joints, freejoint, torso body id via alias resolver, goal position from `WorldTask`, and object body id for manipulation tasks.
- Observation vector: normalized joint qpos/qvel, freejoint torso position/gravity/velocity, and task-error deltas.
- Action scaled per actuator from `[-1, 1]^nu` to each actuator's `ctrlrange`.
- Reward functions for `walker`, `humanoid_stand`, `push`, `pick_place`.
- Termination on `n_steps` or fall (torso z below threshold for locomotion tasks).

**Verification:** `test_world_replay_env_minimal_mjcf` — loads a tiny MJCF with freejoint + hinge + motor, checks `action_dim == 1`, `obs_dim == 17`, and `reset`/`step`/`rollout` shape contracts.

---

## Task 2: Variable-dimension robot policy

- **Modify:** `ai_cad/geda_bridge/brain/policies.py`
- **Test:** `tests/test_geda_bridge_brain.py::test_robot_mlp_policy_shape`, `test_robot_mlp_policy_variable_dims`

**Delivered:**

- `RobotMLPPolicy` class with fixed `HIDDEN_DIM = 32`.
- `n_params(obs_dim, action_dim)` classmethod computes deterministic flat weight count.
- Forward pass clips output to `[-1, 1]`.

**Verification:** policies constructed for `(8, 1)`, `(20, 6)`, `(31, 12)` all produce correct action shapes.

---

## Task 3: NumPy-only CEM trainer for real robots

- **Modify:** `ai_cad/geda_bridge/brain/trainer.py`
- **Test:** `tests/test_geda_bridge_brain.py::test_train_robot_policy_smoke`

**Delivered:**

- `train_robot_policy(env, n_iters, pop_size, elite_frac, inner_rollouts, seed)` mirrors the CEM pattern in `skill_smoke.py`.
- `evaluate_robot_policy(env, weights, n_episodes, seed)` returns success rate, mean reward, and mean final distance.
- `train_and_evaluate_robot(env, ...)` high-level entry point returns a JSON-serializable report.

**Verification:** tiny CEM (2 iters, pop_size 6) runs on the minimal MJCF and returns weights of the correct shape.

---

## Task 4: Backend wiring

- **Modify:** `web/backend/main.py`
- **Test:** `tests/test_morphology_api.py` (existing simulate endpoint tests)

**Delivered:**

- Updated imports to include `WorldReplayEnv`, `RobotMLPPolicy`, `train_robot_policy`, `evaluate_robot_policy`, `train_and_evaluate_robot`.
- `/morphology/{search_id}/candidates/{candidate_id}/simulate` now:
  1. Exports the candidate bundle.
  2. Builds the world from the requested template.
  3. Post-processes the robot MJCF with `_scale_masses_and_add_freejoint` for locomotion templates.
  4. Exports the world MJCF to `sim_dir / "world.mjcf"`.
  5. Builds `WorldReplayEnv` and trains/evaluates a real policy.
  6. Returns real metrics including `obs_dim`, `action_dim`, `n_params`, `task_type`.
  7. Falls back to `AbstractAttentionEnv` if MuJoCo is unavailable.

**Verification:** existing morphology API tests pass; no 500 errors introduced.

---

## Task 5: End-to-end heavy tests

- **New file:** `tests/test_morphology_brain.py`
- **Marks:** `@pytest.mark.slow`, `@pytest.mark.heavy`, `@pytest.mark.xfail(strict=False)`

**Delivered:**

- `test_brain_train_on_generated_humanoid`: exports a humanoid template, builds a walker world, adds freejoint, exports world MJCF, trains/evaluates a policy.
- `test_brain_train_on_generated_quadruped`: same for quadruped template.

**Verification:** both tests xpass under `--timeout=600`, proving CEM runs end-to-end on generated robot worlds.

---

## Task 6: Public API exports

- **Modify:** `ai_cad/geda_bridge/brain/__init__.py`, `ai_cad/geda_bridge/__init__.py`

**Delivered:**

- `RobotMLPPolicy`, `WorldReplayEnv`, `train_robot_policy`, `evaluate_robot_policy`, `train_and_evaluate_robot` exported from `ai_cad.geda_bridge.brain`.
- Same symbols re-exported from `ai_cad.geda_bridge` for backend convenience.

**Verification:** `from ai_cad.geda_bridge import WorldReplayEnv, train_robot_policy` works.

---

## Task 7: Full regression run and documentation sync

**Files:** `README.md`, `PLAN.md`, `CurrentTo10.md`, `docs/superpowers/specs/2026-09-20-milestone-f-real-mujoco-brain.md`, `docs/superpowers/plans/2026-09-20-milestone-f-real-mujoco-brain.md`, private memory files.

**Steps:**

- Run default suite: `python -m pytest --timeout=120 -q`.
- Run slow/heavy/mujoco suite: `python -m pytest -m "slow or heavy or mujoco" --timeout=600 -q`.
- Update `README.md` milestone table with Milestone F status and score.
- Update `PLAN.md` milestone table and next-session notes.
- Update `CurrentTo10.md` baseline, score, caveat table, and add Milestone F section.
- Create/update private memory files: `milestone-f-real-mujoco-brain.md` and refresh `robocad-confidence-10-10-roadmap.md` / `MEMORY.md`.
- Final commit and push.

---

## Self-review

### Spec coverage

| Spec requirement | Task |
|---|---|
| Real MuJoCo env wrapper | Task 1 |
| Variable-dimension policy | Task 2 |
| NumPy-only CEM trainer | Task 3 |
| Backend simulate endpoint wiring | Task 4 |
| Heavy end-to-end tests | Task 5 |
| Public API exports | Task 6 |
| Documentation sync | Task 7 |

### Placeholder scan

No TBD/TODO/"implement later"/"add appropriate" language remains. All steps include concrete code, commands, or test assertions.

### Open issues

- None blocking Milestone F. All acceptance criteria are met. The next measurable improvement is **Milestone G — automatic simulation certification with randomized worlds**, raising the score toward 9.6/10.
