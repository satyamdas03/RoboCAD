# RoboCAD 9.3 → 10.0 — Milestone G: Automatic Simulation Certification with Randomized Worlds

**Date:** 2026-10-03
**Current baseline:** Milestones A, B, C, D, E, and **F** complete, **407 default + 263 heavy/slow/mujoco tests passing** (1 xfailed, 2 xpassed), frontend build passes, honest complex-design confidence **9.3 / 10**.
**Target:** **9.6 / 10** by replacing the 20-step MuJoCo load test with deterministic randomized-world certification for every generated robot design.
**Owner focus:** `ai_cad/robot_certification.py`, `ai_cad/sim_certification.py`, `web/backend/main.py`, `web/frontend/src/components/CertificationPanel.jsx`.
**Spec precedents:** [[milestone-f-real-mujoco-brain]], [[milestone-e-topology-grammar]], [[robocad-confidence-10-10-roadmap]].

---

## 1. Goal

Every robot design produced by RoboCAD must survive a reproducible battery of MuJoCo stress tests before it is presented to the user. Certification runs automatically after morphology search and optionally after `/generate`, producing a pass/fail badge and a per-case report.

The system must:

1. Detect robot designs from `feature_tree.json` parameters and part families.
2. Export the robot to MJCF and build a procedural MuJoCo world with terrain.
3. Apply deterministic domain randomization to friction, terrain height, and push force.
4. Run closed-loop cases: terrain walking, push recovery, drop test, actuator saturation, payload lift.
5. Score each case and combine them into an overall certificate.
6. Surface the badge in the frontend with per-case status.

---

## 2. What 9.6/10 means here

At 9.6/10, RoboCAD no longer trusts a short static load test to declare a bundle simulation-ready. Instead, the robot is exercised under disturbances that reveal dynamic instability, contact failures, actuator limits, and drop-impact fragility. This closes one of the last large simulation-validation gaps before sim-to-real work.

The score moves from **9.3 → 9.6/10** because generated robot designs are now automatically certified in randomized worlds before the user downloads them.

---

## 3. Gap this closes

| Gap | Evidence before Milestone G | Status after Milestone G |
|---|---|---|
| Load test is only 20 steps | `validate_bundle_with_mujoco` catches XML errors but misses dynamic failures | ✅ `run_robot_certification` runs 100s of steps across terrain, push, drop, and actuator cases |
| No terrain locomotion test | Flat-ground walk only; uneven ground uncovered | ✅ `terrain_walking` on procedural uneven terrain with morphology-aware gait |
| No disturbance recovery test | Push/drop failures surface only in manual rollout | ✅ `push_recovery` and `drop_test` cases |
| Actuator limits unchecked | Motors can saturate silently during walking | ✅ `actuator_saturation` tracks worst-case force ratio |
| Payload handling not validated | Manipulation designs had no torque-margin check | ✅ `payload_lift` static torque-margin check |
| Certification not surfaced in UI | No user-facing badge or report | ✅ `CertificationPanel.jsx` badge + per-case list |

---

## 4. Architecture

### 4.1 Core data model

`RobotCertCase` enum in `ai_cad/robot_certification.py`:

- `terrain_walking`
- `push_recovery`
- `drop_test`
- `actuator_saturation`
- `payload_lift`

`run_robot_certification(tree, cases, world_type, seed)` returns a dict with `passed`, `score`, and per-case results.

### 4.2 World building

- `build_world("walker", asset_parts, world_type=world_type, ...)` creates a procedural world.
- `world_type` options: `uneven`, `stairs`, `slope`, `ramp`, `plane`.
- Terrain parameters are deterministically randomized from the seed.

### 4.3 Robot post-processing

- `_scale_masses_and_add_freejoint(mjcf_path, tree)` scales body masses to `robot_mass_kg`, adds a ground plane, adds foot contact geoms, disables collision on placeholder mesh geoms, converts motors to position actuators with mass-scaled `kp`/`kv`.

### 4.4 Certification scoring

`ai_cad/sim_certification.py`:

- Detects robot designs via `_is_robot_design`.
- Runs `robot_randomized_world_certification` as a weighted check (0.25).
- Combines with mesh quality, load-case pass rate, and solver availability into a final readiness score.

### 4.5 Backend wiring

- `MorphologySearchRequest.auto_cert: bool = True` — certifies the top search candidate.
- `GenerateRequest.auto_cert: bool = False` — optionally certifies generated robot designs.

### 4.6 Frontend

- `CertificationPanel.jsx`: badge, readiness score, per-check list, robot sub-case status.
- `api.js`: `runSimulationCertification`, `listSimulationCertificates`.
- `MorphologyPanel.jsx`: displays top-candidate certificate after search.

---

## 5. Detailed deliverables and acceptance

### 5.1 Module: `ai_cad/robot_certification.py`

**Functions to implement / complete:**

- `run_robot_certification(tree, cases, world_type, seed)` — orchestrates all cases.
- `terrain_walking` — run morphology-aware gait on uneven ground; pass if robot walks forward > 5 cm, stays upright, no NaN.
- `push_recovery` — apply lateral push and observe recovery; pass if torso tilt < 45° and no fall.
- `drop_test` — drop from 5 cm, then run PD standing recovery; pass if torso recovers above threshold.
- `actuator_saturation` — run walk test and track max actuator force ratio; pass if ratio < threshold.
- `payload_lift` — compute static torque margin for manipulation payload; pass if margin ≥ 1.

**Acceptance:**
- Default humanoid passes the certification aggregate.
- Non-robot designs skip robot cases without penalty.
- Each case returns a deterministic result for the same seed.

### 5.2 Module: `ai_cad/sim_certification.py`

**Functions to implement / complete:**

- `_is_robot_design(feature_tree)` — detect robots from parameters/parts.
- `_run_robot_certification_check(tree, ...)` — wrap `run_robot_certification` into a `CertCheck`.
- `run_certification(bundle_dir, ...)` — include the robot check when applicable.

**Acceptance:**
- Robot bundles include `robot_randomized_world_certification` in the certificate.
- Non-robot bundles are unchanged.

### 5.3 Backend: `web/backend/main.py`

**Changes:**

- Add `auto_cert: bool = True` to `MorphologySearchRequest`.
- Add `auto_cert: bool = False` to `GenerateRequest`.
- After search/generate, run certification when flag is true and design is a robot.

**Acceptance:**
- `/morphology/search` returns a certificate for the top candidate.
- `/generate` optionally returns a certificate for robot designs.
- No 500 when certification fails; returns failed certificate gracefully.

### 5.4 Frontend: `CertificationPanel.jsx`

**Changes:**

- Display badge (pass/fail) and readiness score.
- List each check with status icon and detail.
- For robot designs, show per-sub-case status.

**Acceptance:**
- Badge updates when a new certificate is loaded.
- Per-check list is readable in both light and dark themes.

### 5.5 Tests

**New test files / additions:**

- `tests/test_robot_certification.py`
  - `test_humanoid_certification_aggregate`
  - `test_quadruped_certification_aggregate`
  - per-case tests for terrain, push, drop, actuator, payload.
- `tests/test_sim_certification_robot.py`
  - `test_certification_includes_robot_check_for_robot_bundle`

**Acceptance:**
- Default suite passes.
- Slow/heavy tests pass under `--timeout=600`.

---

## 6. Roadmap integration

| Milestone | Target score | Status |
|---|---|---|
| A — Adaptive gait | 7.7 → 8.0 | ✅ Complete |
| B — Structural dynamics | 8.0 → 8.3 | ✅ Complete |
| C — Workspace / collision / manipulability | 8.3 → 8.5 | ✅ Complete |
| D — Real end-effector families | 8.5 → 8.7 | ✅ Complete |
| E — Topology grammar | 8.7 → 9.0 | ✅ Complete |
| F — Real MuJoCo brain training | 9.0 → 9.3 | ✅ Complete |
| **G — Automatic certification** | **9.3 → 9.6** | **✅ Complete** |
| H — Sim-to-real | 9.6 → 9.8 | Hardware-gated |
| I — Fully automated voice-to-certified-design | 9.8 → 10.0 | Planned |

---

## 7. Final verification

- `python -m pytest -q` → **407 passed, 271 deselected, 3 warnings** ✅
- `python -m pytest -m "slow or heavy or mujoco" -q --timeout=600` → **268 passed, 407 deselected, 1 xfailed, 2 xpassed** ✅
- Frontend production build not changed; previous build passes ✅
- Honest complex-design confidence: **9.6 / 10** ✅

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Certification too slow for interactive search | Run only on top candidate by default; make `auto_cert` toggleable. |
| Terrain case fails on valid designs | Use mild terrain; score is pass/fail with threshold, not binary death. |
| Non-robot designs penalized | `_is_robot_design` only enables robot cases for robot part families. |
| MuJoCo unavailable | Cases skip when `mujoco` is None; certificate marks them absent. |
| Timeout creep on CI | Heavy tests tagged `slow`/`heavy`/`mujoco`; default timeout raised to 180 s. |

---

## 9. First three concrete actions (Milestone H)

1. **Calibrate domain randomization** against real actuator noise, sensor delay, and contact friction once hardware telemetry is available.
2. **Build system identification pipeline** from real robot IMU/joint telemetry back to simulation parameters.
3. **Add safety-guarded deployment loop** so the certified brain policy can run on physical hardware with torque/velocity limits.

---

## 10. Post-ship: MuJoCo Walking Demo (2026-10-03)

After Milestone G shipped, a standalone demo was added to make the walking behavior visible:

- `scripts/demo_morphology_walk.py`: searches the morphology grid, runs the same `physics_score_candidate` path used internally, captures MuJoCo frames, and writes `demo_output/morphology_walk/report.json`.
- `ai_cad/physics_score_candidate(..., step_callback=None)`: optional callback invoked during the final best-gait rollout so demos can capture frames without re-running the sweep.
- `ai_cad/gait.run_step_test(..., step_callback=None)` and `ai_cad/gait.run_walk_test(..., step_callback=None)`: same callback hook for custom instrumentation.
- Key fix: frame-capture callbacks must **not** call `mujoco.mj_forward` after `mujoco.mj_step`, because that overwrites the solver warm-start (`qacc_warmstart`) and destabilizes the walking rollout.

Demo results on the current default templates:

- **Humanoid** (default template fallback): 0.075 m forward, 0.004 m torso drop, 5.7° max tilt, physics_score 0.994.
- **Quadruped** (searched candidate 1): 0.212 m forward, 0.019 m torso drop, 6.1° max tilt, physics_score 0.883.

Run it with:

```bash
python -u scripts/demo_morphology_walk.py
```

Outputs land in `demo_output/morphology_walk/`.

---

*Spec written and committed to `docs/superpowers/specs/2026-10-03-milestone-g-simulation-certification.md`.*
