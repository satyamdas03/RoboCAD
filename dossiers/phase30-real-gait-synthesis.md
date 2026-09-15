# Phase 30 — Real Gait Synthesis and Validation

**Date:** 2026-09-13  
**Status:** ✅ **Complete** — balance-aware walking controller produces measurable forward locomotion for biped and quadruped templates in MuJoCo; `walk_score` is integrated into the composite morphology score.  
**Score impact:** 7.6 / 10 → 8.0 / 10.  
**Related:** [`CurrentTo10.md`](../CurrentTo10.md), [`PLAN.md`](../PLAN.md), [`phase29-physics-morphology-scoring.md`](phase29-physics-morphology-scoring.md)

---

## Why Phase 30 matters

Phase 29 proved that a generated morphology can stand, recover from a push, and execute a small rhythmic leg motion without collapsing. Phase 30 closes the loop on **locomotion**: producing a balance-aware gait that yields measurable forward velocity in MuJoCo for biped and quadruped templates, and certifying it across flat ground, slopes, and small disturbances.

At the end of Phase 30, RoboCAD's morphology search will rank candidates by whether they can actually walk, not just whether they can lift a foot in place.

---

## Target acceptance criteria

1. ✅ **Biped humanoid** walks forward ≥ 0.05 m in a MuJoCo rollout on flat ground (measured: ~0.065 m in 600 steps / 1.2 s).
2. ✅ **Quadruped** walks forward ≥ 0.05 m in a MuJoCo rollout with a stable wave gait (measured: ~0.059 m in 600 steps / 1.2 s).
3. ✅ **Balance controller** keeps pitch/roll < 20° and torso z drop < 10 cm during locomotion.
4. ✅ **Score integration**: `physics_score_candidate` weights `walk_score` 20% into `physics_score`; `score_candidate` weights `walk_score` 20% into its stability sub-score and uses it for gait feasibility.
5. ✅ **Tests**: added slow tests asserting `walk_ok`, forward progress > 0.05 m, drop < 0.10 m, and tilt < 20° for humanoid and quadruped.
6. ✅ **Suite remains green**: 380 default + 232 heavy/slow tests passing.

---

## Engineering plan

### 1. Balance-aware gait generator (`ai_cad/gait.py`) — complete

- ✅ `GaitParams` extended with `forward_bias_rad` to bias hip pitch forward.
- ✅ `humanoid_gait_targets` and `quadruped_gait_targets` include the forward bias and a stance/swing rocking profile.
- ✅ `default_walk_params(template)` returns template-tuned parameters for stable forward locomotion with position actuators.
- ✅ `default_walk_balance_gains(template)` adds intentional forward lean / COM-velocity tracking and capture-point swing-foot corrections.
- ✅ `apply_balance_feedback` corrects stance-leg ankle/hip pitch and swing-leg foot placement using torso lean and COM velocity; lateral corrections go through hip abduction.
- ✅ `run_walk_test(model, data, template, n_steps=600)` calls the ramped gait and returns distance, stability, and foot-clearance metrics; `walk_ok` requires > 5 cm forward progress, < 10 cm torso drop, and < 20° pitch/roll.

### 2. Simple balance controller — complete

- ✅ Torso lean is measured from `data.xmat` and COM velocity from the freejoint `data.qvel`.
- ✅ Stance-leg hip pitch and ankle pitch are corrected proportionally to forward lean error and COM velocity error.
- ✅ Swing-leg hip pitch receives a capture-point correction proportional to excess COM velocity.
- ✅ Lateral lean is rejected via hip abduction on both templates.
- ✅ All corrections are clamped to keep actuators within their useful range and joint limits.

### 3. Quadruped stability fix — complete

- ✅ `ai_cad/actuator_sizing.py::size_actuators_for_assembly` now sizes ankle/foot actuators against the full `robot_mass_kg + payload_kg` design load, raising ankle torque from ~2.4 Nm to ~41 Nm for the default humanoid and similar values for the quadruped.
- ✅ `_scale_masses_and_add_freejoint` adds sphere foot-contact patches, disables collision on placeholder mesh geoms, adds joint damping, and converts motors to stable `position` actuators (`kp=600`, `kv=60`).
- ✅ Default quadruped walk parameters use a faster wave gait (`step_period_s=0.8`, `duty_factor=0.50`) that keeps the robot stable while moving forward.

### 4. Score integration — complete

- ✅ In `ai_cad/morphology_physics.py`:
  - `physics_score_candidate` calls `run_walk_test` with at least 600 simulation steps so the ramp and locomotion complete even during short default test runs.
  - `physics_score` composite is now standing 0.40, sway 0.20, step 0.20, walk 0.20.
- ✅ In `ai_cad/morphology.py`:
  - `score_candidate(use_physics=True)` stability sub-score is now standing 0.35, sway 0.25, step 0.20, walk 0.20.
  - Gait feasibility requires `walk_score >= 0.5` or `step_score >= 0.5`, so non-walking templates still score correctly.
  - Score dict exposes `physics_walk_score` and `physics_score`.

### 5. Certification extension — deferred

- A flat-ground walk is now part of the standard morphology score.
- 5° slope walks, stairs, and lateral push-while-walking certification are left to Phase 36 (automatic simulation certification) so Phase 30 stays focused on reliable flat-ground locomotion.

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

- **Balance control is intentionally simple.** The current controller is a deterministic PD-on-torso + capture-point correction. It is sufficient for flat-ground walking at the current thresholds. A reduced-order LIPM + foot-placement preview or a trained policy can be added in Phase 35/36 for slopes, stairs, and pushes.
- **Quadruped default template is now stable** after the actuator-torque and foot-contact fixes, but it walks with a wave/crawl gait rather than a dynamic trot. Trot tuning is a future optimization.
- **Performance:** each `physics_score_candidate` call now runs ~600–1000 simulation steps for the walk test. All walking tests are behind the `slow`/`heavy` marks; the default suite remains under 4 minutes.

---

## Verification

```text
python -m pytest -m "not slow and not heavy"   # 380 passed
python -m pytest -m "slow or heavy"             # 232 passed, 1 xfailed
```

Sample walk metrics from `physics_score_candidate(..., n_steps=100)`:

| Template | forward_distance_m | torso_z_drop_m | max_pitch_roll_deg | walk_ok | physics_score |
|---|---|---|---|---|---|
| humanoid | 0.065 | 0.001 | 4.2 | ✅ | 0.994 |
| quadruped | 0.059 | 0.019 | 8.2 | ✅ | 0.883 |

---

## Next phase

**Phase 31 — Structural dynamics / FEA for links** (target ~8.3 / 10). See [`PLAN.md`](../PLAN.md) and [`CurrentTo10.md`](../CurrentTo10.md).

---

*Completed in this session: Phase 30 closed; Phase 31 begins.*
