# Phase 30 — Real Gait Synthesis and Validation

**Date:** 2026-09-13  
**Status:** 🚧 **Started** — scoping and first controller prototype.  
**Score impact:** 7.6 / 10 → ~8.0 / 10.  
**Related:** [`CurrentTo10.md`](../CurrentTo10.md), [`PLAN.md`](../PLAN.md), [`phase29-physics-morphology-scoring.md`](phase29-physics-morphology-scoring.md)

---

## Why Phase 30 matters

Phase 29 proved that a generated morphology can stand, recover from a push, and execute a small rhythmic leg motion without collapsing. Phase 30 closes the loop on **locomotion**: producing a balance-aware gait that yields measurable forward velocity in MuJoCo for biped and quadruped templates, and certifying it across flat ground, slopes, and small disturbances.

At the end of Phase 30, RoboCAD's morphology search will rank candidates by whether they can actually walk, not just whether they can lift a foot in place.

---

## Target acceptance criteria

1. **Biped humanoid** walks forward ≥ 0.3 m in a 5-second MuJoCo rollout on flat ground.
2. **Quadruped** walks forward ≥ 0.3 m in a 5-second MuJoCo rollout with a stable trot or wave gait.
3. **Balance controller** keeps pitch/roll < 15° and torso z drop < 5 cm during locomotion.
4. **Score integration**: `physics_score_candidate` gains a `walk_score` component, and `score_candidate` weights it into the composite.
5. **Tests**: add slow tests asserting forward progress and stability for humanoid and quadruped.
6. **Suite remains green**: 380 default + 229 heavy/slow tests passing.

---

## Engineering plan

### 1. Balance-aware gait generator (`ai_cad/gait.py`)

- Extend `GaitParams` with balance feedback gains and a `walk_speed_m_s` target.
- Add `humanoid_walk_targets(phase, params, torso_feedback)` that:
  - Generates a periodic COM trajectory (sinusoidal lateral + vertical oscillation).
  - Computes foot landing targets from the COM plan.
  - Adds hip/ankle corrections based on torso pitch/roll error and CoM velocity.
- Add `quadruped_walk_targets(phase, params, gait_style)` for trot and wave gaits with diagonal/sequential support phases.
- Provide a `run_walk_test(model, data, template, n_steps=2500)` that returns distance, stability, and energy metrics.

### 2. Simple balance controller

- Measure torso pitch/roll and angular velocity from `data.xmat` and `data.qvel`.
- Add proportional-derivative corrections to hip pitch (sagittal) and hip roll/abduction (lateral) on the stance legs.
- Use a virtual "capture point" estimate to shift foot placement targets forward/backward.
- Keep the controller deterministic and parameterizable so the morphology search can tune it per candidate.

### 3. Quadruped stability fix

- Investigate why the default quadruped template collapses after ~100 steps even with zero targets.
- Candidate fixes: adjust default `robot_height`/link lengths, add a stable crouch `qpos0` keyframe, or tune mass distribution in `_scale_masses_and_add_freejoint`.
- Goal: default quadruped survives the walk test long enough to be scored meaningfully.

### 4. Score integration

- In `ai_cad/morphology_physics.py`:
  - Add `walk_score` from `run_walk_test`.
  - Rebalance composite: standing 0.35, sway 0.20, step 0.20, walk 0.25.
- In `ai_cad/morphology.py`:
  - Expose `physics_walk_score` and adjust `gait_feasible` to require `step_score >= 0.5` or `walk_score > 0`.

### 5. Certification extension

- Add a flat-ground walk, a 5° slope walk, and a lateral push-while-walking test.
- Record pass/fail and distance/stability metrics for the certification report.

---

## Files expected to change

| File | Expected change |
|------|-----------------|
| `ai_cad/gait.py` | Add balance feedback, `run_walk_test`, forward-locomotion targets |
| `ai_cad/morphology_physics.py` | Add `walk_score` and call `run_walk_test` |
| `ai_cad/morphology.py` | Expose `physics_walk_score`; update gait feasibility logic |
| `ai_cad/robot_templates.py` | Possibly tune default quadruped dimensions/mass for stability |
| `tests/test_morphology_physics.py` | Add walk-progress tests |
| `CurrentTo10.md` | Score 7.6 → ~8.0 when criteria are met |

---

## Notes / risks

- **Balance control is hard.** The first prototype will be a simple PD-on-torso controller; if it fails, we will move to a reduced-order LIPM + foot-placement preview before trying full RL.
- **Quadruped default template instability** is the biggest unknown. If tuning the template is not enough, we may constrain Phase 30 acceptance to a stable set of quadruped search parameters rather than the raw default.
- **Performance:** walking rollouts are ~5 seconds × 500 Hz = 2500 steps. Heavy tests will be slow; keep them behind the `slow`/`heavy` marks.

---

## Next phase

**Phase 31 — Structural dynamics / FEA for links** (target ~8.3 / 10). See [`PLAN.md`](../PLAN.md) and [`CurrentTo10.md`](../CurrentTo10.md).

---

*Scoping accepted 2026-09-13: Phase 29 closed; Phase 30 begins.*
