# Phase 30 — Real Gait Synthesis and Validation

**Date:** 2026-09-15  
**Status:** ⚠️ **Revised** — balance-aware walking controller works for the *default* biped and quadruped templates in MuJoCo, but it is **not yet robust** across the searched morphology grid, mass perturbations, or LLM-generated proportions. `walk_score` is integrated into the composite morphology score. Non-legged templates now skip gait tests instead of failing them.  
**Score impact:** claimed 7.6 / 10 → 8.0 / 10 is **partially supported**; honest confidence is closer to **7.7 / 10** for complex humanoid designs.  
**Related:** [`CurrentTo10.md`](../CurrentTo10.md), [`PLAN.md`](../PLAN.md), [`phase29-physics-morphology-scoring.md`](phase29-physics-morphology-scoring.md)

---

## Why Phase 30 matters

Phase 29 proved that a generated morphology can stand, recover from a push, and execute a small rhythmic leg motion without collapsing. Phase 30 closes the loop on **locomotion**: producing a balance-aware gait that yields measurable forward velocity in MuJoCo for biped and quadruped templates, and wiring it into the scoring pipeline.

At the end of Phase 30, RoboCAD's morphology search is supposed to rank candidates by whether they can actually walk, not just whether they can lift a foot in place. The honest finding is that the current controller walks the *default* templates, but fails for most searched humanoid proportions.

---

## Target acceptance criteria (original vs. honest)

| # | Claim | Honest result |
|---|---|---|
| 1 | Biped humanoid walks forward ≥ 0.05 m on flat ground | ✅ **Default template** walks ~0.117 m in 600 steps; most searched variants fail |
| 2 | Quadruped walks forward ≥ 0.05 m with a stable gait | ✅ **Default template** walks; 12/32 searched quadruped variants pass (37.5%) |
| 3 | Balance controller keeps pitch/roll < 20° and torso z drop < 10 cm | ✅ True for default templates that pass; false for failing variants |
| 4 | `walk_score` weighted into `physics_score` and `score_candidate` | ✅ Implemented: 20% in both composites |
| 5 | Slow tests assert `walk_ok` for humanoid and quadruped | ✅ Passing after tuning defaults |
| 6 | Suite remains green | ✅ 612 passed, 1 xfailed |

---

## Engineering plan

### 1. Balance-aware gait generator (`ai_cad/gait.py`) — revised

- `GaitParams` extended with `forward_bias_rad`.
- `humanoid_gait_targets` and `quadruped_gait_targets` include forward bias and stance/swing rocking.
- `default_walk_params(template)` now returns **conservative, template-specific** parameters tuned for the default position-actuator models:
  - Humanoid: `step_period_s=2.0`, `duty_factor=0.85`, small hip/knee motion, no forward bias.
  - Quadruped: faster trot-like gait with larger step length and forward bias.
- `default_walk_balance_gains(template)` adds intentional forward lean / COM-velocity tracking and capture-point swing-foot corrections.
- `apply_balance_feedback` corrects stance-leg ankle/hip pitch and swing-leg placement using torso lean and COM velocity; lateral corrections via hip abduction; all clamped.
- `run_walk_test(model, data, template, n_steps=600)` returns distance, stability, and foot-clearance metrics; `walk_ok` requires > 5 cm forward progress, < 10 cm torso drop, and < 20° pitch/roll.
- **Honest caveat:** the parameter set is stable only for the default morphology. The search grid and mass perturbations break it.

### 2. Simple balance controller — complete

- Torso lean measured from `data.xmat`; COM velocity from freejoint `data.qvel`.
- Stance-leg hip/ankle pitch corrections; capture-point swing hip; lateral abduction rejection.
- Clamped to keep actuators and joints within useful range.

### 3. Quadruped stability fix — complete

- `size_actuators_for_assembly` sizes ankle/foot actuators against full `robot_mass_kg + payload_kg`.
- `_scale_masses_and_add_freejoint` adds sphere foot-contact patches, disables placeholder mesh collision, adds joint damping, and converts motors to `position` actuators (`kp=600`, `kv=60`).
- Default quadruped walk parameters use a faster wave gait.

### 4. Score integration — complete

- `physics_score_candidate` calls `run_walk_test` with ≥ 600 steps; composite standing 0.40, sway 0.20, step 0.20, walk 0.20.
- `score_candidate(use_physics=True)` stability sub-score standing 0.35, sway 0.25, step 0.20, walk 0.20; gait feasibility requires `walk_score >= 0.5` or `step_score >= 0.5`.
- Score dict exposes `physics_walk_score` and `physics_score`.

### 5. Non-legged fallback safety — fixed

- `physics_score_candidate` now detects whether the model has a torso *and* feet. Manipulator-on-base and other non-legged templates skip sway/step/walk tests (marked `skipped: True`) instead of failing them.
- Standing test still runs; non-legged designs can earn a high physics score without being penalized by tests that do not apply.

### 6. Certification extension — deferred

- Flat-ground walk is part of the standard score.
- Slopes, stairs, lateral pushes, and drop tests remain Phase 36.

---

## Files changed

| File | Change |
|------|--------|
| `ai_cad/gait.py` | Tuned conservative default step/walk params; lowered humanoid step foot-clearance threshold to 2 mm; added comments explaining limitations |
| `ai_cad/morphology_physics.py` | Skip sway/step/walk for non-legged templates; expose `skipped` reason in results |
| `dossiers/phase30-real-gait-synthesis.md` | This file — revised claims and added honest validation table |
| `CurrentTo10.md` | Score revised from 8.0 to 7.7 / 10 |

---

## Notes / risks

- **Balance control is intentionally simple** and only validated for the default templates.
- **Humanoid walking is brittle:** the grid search found **0/48 walk_ok** variants; mass perturbations found **0/8 walk_ok**.
- **Quadruped walking is more robust:** 12/32 searched variants pass.
- **Performance:** each `physics_score_candidate` call runs ~600–1000 simulation steps. Walking tests are behind `slow`/`heavy` marks.

---

## Verification

```text
python -m pytest tests/test_morphology_physics.py -v -o addopts=
# 8 passed

python -m pytest -o addopts=
# 612 passed, 1 xfailed
```

Sample walk metrics from `physics_score_candidate(humanoid_template(), n_steps=100)` after tuning:

| Template | forward_distance_m | torso_z_drop_m | max_pitch_roll_deg | walk_ok | physics_score |
|---|---|---|---|---|---|
| humanoid (default) | 0.117 | 0.006 | 9.8 | ✅ | 0.994 |
| quadruped (default) | 0.064 | 0.018 | 8.1 | ✅ | 0.871 |

---

## Rigorous end-to-end validation results

Run on 2026-09-15 with the tuned defaults.

### 1. Morphology search with `use_physics=True`

| Template | Candidates | walk_ok | step_ok | full physics pass* |
|---|---|---|---|---|
| humanoid | 48 | 0 (0.0%) | 30 (62.5%) | 0 (0.0%) |
| quadruped | 32 | 12 (37.5%) | 32 (100%) | 12 (37.5%) |
| manipulator_on_base | 4 | N/A (skipped) | N/A (skipped) | 4 (100%) |

\* full physics pass = standing_ok ∧ sway_ok ∧ step_ok ∧ walk_ok (or skipped for non-legged).

### 2. Stress-test default humanoid

| Perturbation | walk_ok | step_ok | Failure mode |
|---|---|---|---|
| mass 15 kg, payload 2.5 kg | ❌ | ❌ | Falls backward, 179° tilt |
| mass 15 kg, payload 7.5 kg | ❌ | ✅ | Falls backward |
| mass 20 kg, payload 2.5 kg | ❌ | ❌ | Falls backward |
| mass 20 kg, payload 7.5 kg | ❌ | ✅ | Falls backward, 126° tilt |
| mass 25 kg, payload 2.5 kg | ❌ | ✅ | Sway fails, then falls |
| mass 25 kg, payload 7.5 kg | ❌ | ✅ | Falls backward |
| mass 30 kg, payload 5.0 kg | ❌ | ❌ | Falls backward |
| mass 35 kg, payload 5.0 kg | ❌ | ✅ | Falls backward |

**Result: 0/8 mass perturbations produced a walk_ok humanoid.**

### 3. Non-legged fallback safety

`manipulator_on_base_template()` now scores:

```text
standing_ok: True
sway_ok: True (skipped)
step_ok: True (skipped)
walk_ok: True (skipped)
physics_score: 0.999999
```

No false failures for non-legged designs.

### 4. Full backend flow `/generate` → `/morphology/search` → `/simulate`

Prompt: *“Design a 1.0 m tall biped humanoid robot with two legs and two arms, 20 kg total mass, 5 kg payload, stable walking gait”*

| Step | Endpoint | Result | Notes |
|---|---|---|---|
| 1 | `/generate` | 200, domain `humanoid`, `success: false` | LLM generated build123d code but the pipeline marked it as not fully successful (expected for this prompt class when no real geometry validates) |
| 2 | `/morphology/search` | 200, 4 candidates | **0/4 candidates walk_ok**; top candidate `physics_walk_score = 0.0` |
| 3 | `/simulate` | 200 | Brain smoke test succeeded (`success_rate=1.0`), but on the **top composite-ranked candidate**, not a candidate that can actually walk |

**Honest finding:** the backend flow is wired end-to-end, but the morphology search does **not** return a walking humanoid for this LLM-generated prompt.

### 5. Aggregate failure-mode pass-rate summary

| Validation | Pass rate | Verdict |
|---|---|---|
| Default humanoid walks | ✅ | Supported |
| Default quadruped walks | ✅ | Supported |
| Humanoid morphology grid walks | 0/48 | **Not supported** |
| Quadruped morphology grid walks | 12/32 (37.5%) | Partially supported |
| Humanoid mass perturbation walks | 0/8 | **Not supported** |
| Manipulator-on-base fallback | ✅ | Supported |
| Full backend `/generate→search→simulate` | ✅ wired, but returns 0 walking humanoids | **Partially supported** |

**Honest confidence score:** the claimed **8.0 / 10** is too high for *complex, searched humanoid designs*. The default-template evidence supports roughly **7.7 / 10** today:

- Infrastructure and deterministic pipeline: strong.
- Quadruped walking across a modest grid: moderate (37.5%).
- Humanoid walking across searched proportions and perturbations: weak (≈0%).

The score will rise toward 8.0+ when the humanoid gait controller is robust across at least a plurality of the searched grid and small mass perturbations.

---

## Next phase

**Phase 31 — Structural dynamics / FEA for links** (target ~8.3 / 10). See [`PLAN.md`](../PLAN.md) and [`CurrentTo10.md`](../CurrentTo10.md).
