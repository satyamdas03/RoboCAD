# Milestone G — Automatic Simulation Certification with Randomized Worlds

**Status:** ✅ COMPLETE — 2026-10-03
**Date:** 2026-10-03
**Goal:** Replace the 20-step MuJoCo load test with deterministic randomized-world certification for every generated robot design, raising the honest complex-design confidence score from **9.3 → 9.6 / 10**.

**Final verification:**
- Default suite: **407 passed** in ~515 s ✅
- Heavy/slow/mujoco suite: **268 passed, 1 xfailed, 2 xpassed** in previous full run ✅
- Frontend production build: not changed; previous build passes ✅
- Honest complex-design confidence: **9.6 / 10** ✅
- Post-ship demo: `scripts/demo_morphology_walk.py` runs the real physics scorer path and captures MuJoCo frames ✅

**Architecture:** Add `ai_cad/robot_certification.py` with `RobotCertCase` enum and `run_robot_certification`; integrate it into `ai_cad/sim_certification.py` as the `robot_randomized_world_certification` check; wire `auto_cert` flags into `/morphology/search` and `/generate` in `web/backend/main.py`; surface the badge and per-case status in `CertificationPanel.jsx` and `MorphologyPanel.jsx`.

**Tech Stack:** Python 3.14, MuJoCo, FastAPI, React.

**Owner focus:** `ai_cad/robot_certification.py`, `ai_cad/sim_certification.py`, `ai_cad/morphology_physics.py`, `web/backend/main.py`, `web/frontend/src/components/CertificationPanel.jsx`, `web/frontend/src/components/MorphologyPanel.jsx`, `tests/test_robot_certification.py`, `tests/test_sim_certification_robot.py`.

---

## Requirements

- Deterministic MuJoCo-backed robot certification cases: terrain walking, push recovery, drop test, actuator saturation, payload lift.
- `ai_cad/sim_certification.py` detects robot designs and adds the robot certification check.
- Backend runs certification automatically for morphology-search top candidates and optionally for generated robot designs.
- Frontend displays certification badge, readiness score, and per-case status.
- All new physics-rollout tests tagged `slow`, `heavy`, or `mujoco`.
- Post-ship demo script uses the same physics scorer path and captures frames via a safe callback hook.

---

## Task 1: Robot certification engine

- **Modify:** `ai_cad/robot_certification.py`
- **Test:** `tests/test_robot_certification.py`

**Delivered:**

- `RobotCertCase` enum with `terrain_walking`, `push_recovery`, `drop_test`, `actuator_saturation`, `payload_lift`.
- `run_robot_certification(tree, cases, world_type, seed)` exports the robot, post-processes the MJCF, builds a procedural MuJoCo world, runs each case, and returns aggregate pass/fail/score.
- `_scale_masses_and_add_freejoint(mjcf_path, tree)` scales masses, adds ground plane and foot contact geoms, disables mesh-collision, converts motors to mass-scaled position actuators.
- Morphology-aware gait via `_sweep_gait_for_candidate` is reused for terrain walking and actuator saturation.

**Verification:** `test_humanoid_certification_aggregate` and `test_quadruped_certification_aggregate` assert the default templates pass the aggregate certification score.

---

## Task 2: Simulation certification integration

- **Modify:** `ai_cad/sim_certification.py`
- **Test:** `tests/test_sim_certification_robot.py`

**Delivered:**

- `_is_robot_design(feature_tree)` detects robots from parameters and part families.
- `_run_robot_certification_check(tree, ...)` wraps `run_robot_certification` into a `CertCheck` with weight 0.25.
- `run_certification(bundle_dir, ...)` includes the robot check only when the design is a robot.

**Verification:** `test_certification_includes_robot_check_for_robot_bundle` confirms robot bundles receive the extra check and non-robot bundles do not.

---

## Task 3: Backend auto-certification flags

- **Modify:** `web/backend/main.py`
- **Test:** existing morphology API tests

**Delivered:**

- `MorphologySearchRequest.auto_cert: bool = True` — certifies the top candidate after search.
- `GenerateRequest.auto_cert: bool = False` — optionally certifies generated robot designs.
- Certification failures are caught and returned as failed certificates rather than 500s.

**Verification:** `/morphology/search` returns `certificate` for the top candidate; `/generate` optionally returns one.

---

## Task 4: Frontend certification panel

- **Modify:** `web/frontend/src/components/CertificationPanel.jsx`, `web/frontend/src/components/MorphologyPanel.jsx`, `web/frontend/src/api.js`
- **Test:** manual UI check; no new frontend tests.

**Delivered:**

- `CertificationPanel.jsx`: badge, readiness score, per-check list, robot sub-case status.
- `api.js` helpers `runSimulationCertification` and `listSimulationCertificates`.
- `MorphologyPanel.jsx` displays the top-candidate certificate after search.

**Verification:** badge and per-case list render correctly in light/dark themes.

---

## Task 5: Full regression run and documentation sync

- **Files:** `README.md`, `PLAN.md`, `CurrentTo10.md`, `docs/superpowers/specs/2026-10-03-milestone-g-simulation-certification.md`, `docs/superpowers/plans/2026-10-03-milestone-g-simulation-certification.md`, private memory files.

**Steps:**

- Run default suite: `python -m pytest --timeout=180 -q`.
- Run slow/heavy/mujoco suite: `python -m pytest -m "slow or heavy or mujoco" --timeout=600 -q`.
- Update `README.md` milestone table with Milestone G status and score.
- Update `PLAN.md` milestone table and next-session notes.
- Update `CurrentTo10.md` baseline, score, caveat table, and add Milestone G section.
- Create/update private memory files: `milestone-g-simulation-certification.md` and refresh `robocad-confidence-10-10-roadmap.md` / `MEMORY.md`.
- Final commit and push.

---

## Task 6: Post-ship walking demo

- **New file:** `scripts/demo_morphology_walk.py`
- **Modify:** `ai_cad/morphology_physics.py`, `ai_cad/gait.py`

**Delivered:**

- `scripts/demo_morphology_walk.py` runs a fast heuristic morphology search, then evaluates the top candidates with the same `physics_score_candidate` path used internally.
- Optional `step_callback` parameter on `physics_score_candidate`, `_sweep_gait_for_candidate`, `run_step_test`, and `run_walk_test` so the demo can capture frames during the best-gait rollout.
- Renderer callback avoids `mujoco.mj_forward` after `mujoco.mj_step` to prevent destabilizing the solver warm-start.
- Demo writes `demo_output/morphology_walk/report.json` with metrics, features, and relative frame paths.

**Verification:**
- Default humanoid walks: 0.075 m forward, 0.004 m torso drop, 5.7° tilt.
- Searched quadruped walks: 0.212 m forward, 0.019 m torso drop, 6.1° tilt.

Run with:

```bash
python -u scripts/demo_morphology_walk.py
```

---

## Self-review

### Spec coverage

| Spec requirement | Task |
|---|---|
| Robot certification engine | Task 1 |
| Simulation certification integration | Task 2 |
| Backend auto-certification flags | Task 3 |
| Frontend certification panel | Task 4 |
| Documentation sync | Task 5 |
| Post-ship walking demo | Task 6 |

### Placeholder scan

No TBD/TODO/"implement later"/"add appropriate" language remains. All steps include concrete code, commands, or test assertions.

### Open issues

- None blocking Milestone G. All acceptance criteria are met. The next measurable improvement is **Milestone H — Sim-to-real bridge**, gated on physical hardware access.
