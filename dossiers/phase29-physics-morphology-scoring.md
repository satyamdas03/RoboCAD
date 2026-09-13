# Phase 29 — Physics-Based Morphology Scoring

**Date:** 2026-09-13  
**Status:** Core delivered; walking/step test remaining before full close.  
**Score impact:** 6.8 / 10 → 7.2 / 10.  
**Related:** [`CurrentTo10.md`](../CurrentTo10.md), [`PLAN.md`](../PLAN.md), [`robocad-end-to-end-roadmap.md`](robocad-end-to-end-roadmap.md)

---

## Why Phase 29 matters

Phase 28D shipped a deterministic morphology co-design lab, but the composite score was heuristic: support-polygon stability, ZMP margin, workspace reach, static actuator sizing, and a span-ratio compactness term. The top-ranked humanoid candidate (composite ~0.80) still produced `Nan, Inf or huge value in QACC at DOF 8` when loaded into MuJoCo. The score did not predict instability.

Phase 29 replaces the heuristic stability/gait proxy with real MuJoCo rollouts so that ranked candidates correlate with actual simulation behavior.

---

## What shipped

### 1. NVIDIA NIM bug fixes

- Removed the non-existent `/video/generations` Cosmos endpoint from `ai_cad/nvidia_client.py`.
- `generate_scenario` now uses structured Nemotron Super chat completion and returns a JSON scenario description.
- `ai_cad/solvers/nvidia_surrogate.py`:
  - Default model changed to `nvidia/nemotron-3-super-120b-a12b`.
  - Added `_is_plausible` validation so zero-stress / zero-drag / zero-thermal-resistance outputs are rejected.
  - Deterministic `_fallback` uses shape-based heuristics when NIM returns implausible values.
  - Fixed thermal fallback unit bug (`mesh.area` already returns mm², so the extra `* 1e6` was removed).
- Backend `/world/scenario` and `/nvidia/models` updated.
- Test mocks in `tests/test_nvidia_client.py` updated to chat-completion-shaped responses.
- Live smoke tests confirm chat and scenario endpoints respond correctly, and surrogate stress values are now validated before use.

### 2. Physics-based morphology scoring

- New `ai_cad/morphology_physics.py`:
  - Exports a `FeatureTree` to MJCF via `export_bundle_from_tree`.
  - Post-processes the exported MJCF:
    - Scales all body masses to match the tree's `robot_mass_kg` budget.
    - Adds a `freejoint` under the first `worldbody` body so the robot is dynamically free-floating.
  - `physics_score_candidate(tree, n_steps=200)` runs two tests:
    - **Standing test:** simple PD pose controller; checks NaN/Inf, torso height drop, pitch/roll, max qacc.
    - **Sway test:** lateral push on the torso, then recovery; fails if tilt > 45° or drop > 25 cm.
  - Returns `physics_score` = 0.7 × `standing_score` + 0.3 × `sway_score`.
- Integrated into `ai_cad/morphology.py`:
  - `score_candidate(..., use_physics=True)` uses MuJoCo rollouts for the stability term.
  - `search_morphologies(..., use_physics=True)` is the new default in the module.
  - Score dict now includes `physics_standing_score`, `physics_sway_score`, and `physics_com_score`.
- Backend `/morphology/search` request model gained `use_physics: bool = False` so the web UI stays fast by default; physics validation is opt-in.

### 3. Tests

- `tests/test_morphology_physics.py` added (4 slow tests):
  - humanoid and quadruped candidates return valid physics scores in [0, 1];
  - standing metrics are populated;
  - graceful skip when MuJoCo is unavailable.
- Full suite verified:
  - **380 default tests passing**.
  - **223 heavy/slow tests passing** (1 xfailed).

---

## Files changed

| File | Change |
|------|--------|
| `ai_cad/nvidia_client.py` | Dropped Cosmos video endpoint; `generate_scenario` uses chat completion |
| `ai_cad/solvers/nvidia_surrogate.py` | Default Super model, plausibility validation, deterministic fallback, thermal unit fix |
| `web/backend/main.py` | `/world/scenario` no longer hard-codes Cosmos; `/nvidia/models` catalog updated; `use_physics` toggle on `/morphology/search` |
| `tests/test_nvidia_client.py` | Mocks updated to chat-completion responses |
| `ai_cad/morphology_physics.py` | New module: MJCF export + mass scaling + freejoint + standing/sway tests |
| `ai_cad/morphology.py` | Imports repaired; `physics_score_candidate` wired into scoring |
| `tests/test_morphology_physics.py` | New tests for physics scoring |
| `CurrentTo10.md` | Score 6.8 → 7.2; Phase 29 marked core complete |

---

## Remaining work to close Phase 29

1. Add a real **single-step / walking attempt** for biped and quadruped templates.
2. Cache MuJoCo models across candidates to amortize export cost.
3. Add 5–10 heavy tests proving high-scoring candidates do not NaN under longer rollouts.

---

## Next phase

**Phase 30 — Real gait synthesis and validation** (target ~8.0 / 10). See [`PLAN.md`](../PLAN.md) and [`CurrentTo10.md`](../CurrentTo10.md).

---

*Core acceptance verified 2026-09-13: 380 default + 223 heavy/slow tests passing.*
