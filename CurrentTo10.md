# Current RoboCAD → 10/10

**Current RoboCAD is in a solid, shippable state:** 380 default + 241 heavy/slow tests passing, frontend build passes, Phase 28A–F complete, Phase 29 physics-based morphology scoring (standing + sway + stepping) complete, and **Milestone A (adaptive gait robustness)** complete. The humanoid and quadruped gait controllers now scale with morphology, run a deterministic per-candidate gait sweep, scale position-actuator gains by total robot mass, and use a tuned quadruped trot gait.

My honest confidence score for **complex multi-domain robot designs, especially humanoids**, is **8.0 / 10**. The pipeline validates morphology with real MuJoCo standing, sway, stepping, and walking rollouts. Default-template and near-default humanoid/quadruped candidates walk reliably; the searched grid and small mass perturbations now pass at the Milestone A acceptance thresholds (humanoid focused grid ≥40%, quadruped grid ≥75%, mass perturbations ≥50%). The remaining gap is structural dynamics, workspace/collision/manipulability, real end-effector families, topology grammar, real MuJoCo brain training, and automatic simulation certification. The full deep-analysis memory file lives at:

`C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\robocad-confidence-10-10-roadmap.md`

and is indexed in `MEMORY.md`.

---

## Why 8.0 / 10 today

The score reflects that the *infrastructure* is green and deterministic, the *physics reasoning* layer is real rather than heuristic, and **adaptive flat-ground gait synthesis is now robust enough for searched candidates and small mass perturbations**. The next jump requires structural dynamics, self-collision/manipulability, real end-effectors, topology grammar, brain training on the actual MuJoCo model, and automatic certification.

| Subsystem | Current state | Caveat |
|---|---|---|
| Morphology search | Runs fast, deterministic, cached FK, **physics-validated** for standing + sway + stepping + walking | Flat-ground walking is synthesized; slopes/stairs/push recovery remain Phase 36 |
| Stability / gait | MuJoCo standing/sway/step/walk rollouts with **morphology-aware** balance feedback and per-candidate gait sweep | Dynamic trot and rough terrain are future work |
| Workspace | Caps at 4096 samples | Humanoid sagittal arms report `workspace_volume = 0.0 mm³`, falls back to max reach |
| Actuator sizing | Payload × lever-arm static formulas; position actuators scale with total robot mass | Not inverse-dynamics based |
| Brain training | 2-D `AbstractAttentionEnv` abstraction | Does not control the actual MuJoCo humanoid |
| MuJoCo validation | 20-step load test | Catches load errors, not dynamic instability |
| Topology set | 3 templates | Anything outside biped/quadruped/manipulator falls back to LLM |
| End-effector selection | Only changes prompt string | No real morphological effect |

Concrete evidence from the current code:

- `ai_cad/morphology.py::score_candidate` weights: stability 0.30, workspace 0.25, gait 0.25, actuator 0.15, compactness 0.05 — all heuristic.
- The top-ranked humanoid in the benchmark (composite **0.804**) still produced a MuJoCo instability warning: `Nan, Inf or huge value in QACC at DOF 8`. The score did not predict it.
- `ai_cad/geda_bridge/brain/envs.py::AbstractAttentionEnv` is a toy 2-D navigation task, not a robot controller.

---

## What 10 / 10 means

At 10/10, a user can say:

> *“Design a 1.2 m humanoid that can walk on a 5° slope, pick up a 2 kg box from the floor, and survive a 10 cm drop.”*

…and RoboCAD delivers, with no caveats:

1. Parses constraints and decomposes the task correctly.
2. Proposes topology: biped + two 7-DOF arms + parallel-jaw gripper.
3. Morphology search evaluates **50+ candidates**, each validated by **real MuJoCo physics rollouts**.
4. Structural FEA confirms no link buckles under payload + drop load.
5. Exports a MuJoCo / Isaac Sim / URDF bundle that loads first time and simulates stably.
6. Trains a closed-loop brain policy **on the actual robot model**, not an abstraction.
7. Runs simulation certification over randomized worlds and passes ≥ 95%.
8. Presents one ranked result, a certification badge, and downloadable manufacturing + simulation package.

**Failure modes at 10/10:** essentially none for covered prompt classes. Out-of-scope prompts like “soft robot” or “humanoid with wings” are rejected cleanly rather than producing broken designs.

Estimated end-to-end time at 10/10 for a complex robot: **under 30 minutes**.

---

## Roadmap from 6.8 → 10 / 10

This is not one phase. It is a deliberate research-engineering program. Honest estimate: **6–12 months to reach 9/10**, and **12–24 months to reach 10/10** including true sim-to-real.

### Phase 29 — Physics-based morphology scoring (~7.5/10) ✅ COMPLETE

- Replaced heuristic stability/gait with MuJoCo **standing + sway + stepping** PD-controller rollouts.
- Added `ai_cad/morphology_physics.py` with `physics_score_candidate`, MJCF export + mass scaling + freejoint post-processing.
- Added `ai_cad/gait.py` with deterministic open-loop gait targets and `run_step_test`.
- Wired `physics_score_candidate` into `ai_cad/morphology.py::score_candidate` and `search_morphologies` via `use_physics=True` default.
- Added `tests/test_morphology_physics.py` (6 slow tests, passing; humanoid step pass asserted).
- Full suite: **380 default + 229 heavy/slow passing**.

**Effort:** 3–4 weeks total; closed in prior session.

### Phase 30 — Real gait synthesis and validation ✅ COMPLETE (honest validation revised score 7.7/10)

Built a deterministic balance-feedback gait controller for biped/quadruped templates and integrated walking into the morphology score. Honest end-to-end validation showed default-template walking passes, but the humanoid controller was not yet robust across searched morphologies or mass perturbations.

**Delivered in this session:**
- `ai_cad/gait.py`: balance-aware `run_walk_test`, `default_walk_params`, `default_walk_balance_gains`, stance/swing detection, capture-point swing-foot corrections, and safe clamped feedback.
- `ai_cad/actuator_sizing.py`: ankle/foot actuators sized against full `robot_mass_kg + payload_kg`, fixing single-leg stance collapse.
- `ai_cad/morphology_physics.py`: `physics_score_candidate` runs a ≥600-step walk test and weights `walk_score` 20% into `physics_score`.
- `ai_cad/morphology.py`: stability sub-score now includes 20% `walk_score`; gait feasibility requires walking (or stepping fallback).
- `tests/test_morphology_physics.py`: added `humanoid_walk_ok` and `quadruped_walk_ok` slow tests.
- Full suite verified: **380 default + 232 heavy/slow passing**.

**Effort:** ~2 sessions on top of the scaffold.

### Milestone A — Adaptive gait robustness (7.7 → 8.0/10) ✅ COMPLETE

Closed the humanoid/quadruped gait generalization gap with morphology-aware controllers, per-candidate gait sweeps, mass-aware actuator gains, and a tuned quadruped trot gait.

**Delivered in this session:**
- `ai_cad/gait_adaptation.py`: extracts `GaitMorphologyFeatures` (COM height, leg length, mass, foot size, template) from MuJoCo model + FeatureTree.
- `ai_cad/gait.py`: `morphology_aware_walk_params` and `morphology_aware_balance_gains` scale gait period, step length, duty factor, hip/knee motion, and balance gains to the candidate. Humanoid gait includes a small `forward_bias_rad=0.03` for deterministic forward motion; quadruped uses a dynamic trot gait when forward bias is requested.
- `ai_cad/morphology_physics.py`: `_sweep_gait_for_candidate` tries 6 deterministic gait variants and keeps the best `walk_score`; position-actuator `kp`/`kv` are scaled by total robot mass (`sqrt(total_budget / 20.0)`) so light and heavy candidates both track well.
- `tests/test_gait_adaptation.py`: feature extraction and morphology-aware param tests.
- `tests/test_morphology_grid.py`: grid pass-rate regression tests (humanoid ≥40%, quadruped ≥75%) and mass-perturbation regression test (≥50%).
- `tests/test_morphology_physics.py`: asserts position-actuator gains scale with mass.
- Full suite verified: **380 default + 241 heavy/slow passing** (1 xfailed).

**Score impact:** 7.7 → **8.0 / 10** for complex multi-domain robot designs.

### Phase 31 / Milestone B — Structural dynamics / FEA for links (~8.3/10)

Wire the existing deep FEA dispatcher into robot-template certification. Add beam bending / buckling checks using real link cross-sections and materials.

**Effort:** 4–6 weeks.

### Phase 32 / Milestone C — Self-collision and manipulability (~8.5/10)

Sample task poses, run collision checks, compute manipulability index. Add `collision_penalty` and `manipulability_score` to the composite.

**Effort:** 3–4 weeks.

### Phase 33 / Milestone D — Real end-effector families (~8.7/10)

Add part families for parallel-jaw gripper, three-finger hand, vacuum gripper, point/compliant feet. Make `_attach_end_effector` actually change the tree and mass distribution.

**Effort:** 4–5 weeks.

### Phase 34 / Milestone E — Topology search beyond templates (~9.0/10)

Implement a grammar for robot topologies: base type, limb count, attachment points, joint sequences. Search the grammar and validate each with Phases 29–32.

**Effort:** 8–10 weeks. This is the hardest layer.

### Phase 35 / Milestone F — Brain training on actual MuJoCo models (~9.3/10)

Replace `AbstractAttentionEnv` with a `WorldReplayEnv` that rolls out the real MJCF. Train MLP/RNN policies with CEM/PPO/ES on actual robot tasks (walk, pick-place, push).

**Effort:** 8–12 weeks.

### Phase 36 / Milestone G — Automatic simulation certification (~9.6/10)

Extend certification with randomized terrain, payload lift, push recovery, drop test, actuator saturation. Run automatically after every complex design.

**Effort:** 4–6 weeks.

### Phase 37 / Milestone H — Sim-to-real bridge (~9.8/10)

System identification from real telemetry, calibrated domain randomization, safety-guarded deployment. This is Phase 27D, currently hardware-blocked.

**Effort:** 6–12 months, gated on physical hardware.

### Phase 38 / Milestone I — Fully automated voice-to-certified-design (~10/10)

HERMES orchestrates decomposition, topology search, physics validation, brain training, and certification. Automatic retry-on-failure. Complete audit trail.

**Effort:** 3–6 months after Phase 37.

---

## Expected RoboCAD performance at 10/10

At 10/10 RoboCAD behaves like a senior mechatronics engineer + simulation analyst + controls engineer working in parallel:

- **Input:** voice, text, or sketch of a complex robot.
- **Output:** certified, manufacturable, sim-ready design with a working controller.
- **Guarantee:** the design passes a distribution of physics tests, not just heuristics.
- **Speed:** complex humanoid in under 30 minutes.
- **Reliability:** deterministic, reproducible, auditable.
- **Scope:** any robot topology the grammar supports; graceful rejection of unsupported concepts.

The “superpowers” are:

1. **Physics oracle** — every candidate is evaluated by real simulation before being presented.
2. **Self-designing topology** — RoboCAD invents structure, not just parameters.
3. **Born controllable** — the robot ships with a policy that works in simulation.
4. **Certified by default** — random-world stress tests are part of normal output.
5. **One-shot end-to-end** — prompt → certified bundle with no manual CAD fixes.

---

## Completed in this session

1. **Phase 29 core — physics-based morphology scoring**
   - `ai_cad/morphology_physics.py`: FeatureTree → MJCF, mass scaling, freejoint, standing + sway + step PD rollouts.
   - Integrated into `ai_cad/morphology.py`: `score_candidate(..., use_physics=True)` and `search_morphologies(..., use_physics=True)`.
   - Added `tests/test_morphology_physics.py`; all slow tests pass.

2. **Phase 30 — real gait synthesis and validation**
   - `ai_cad/gait.py`: balance-aware `run_walk_test`, `default_walk_params`, `default_walk_balance_gains`, stance/swing detection, capture-point corrections.
   - `ai_cad/actuator_sizing.py`: ankle/foot actuators sized against full robot mass + payload, fixing stance collapse.
   - `ai_cad/morphology_physics.py`: walk test runs ≥600 steps and `walk_score` is weighted 20% into `physics_score`.
   - `ai_cad/morphology.py`: `walk_score` contributes 20% to stability sub-score and gait feasibility.
   - Added humanoid and quadruped walk-progress slow tests.
   - Full suite verified: **380 default + 232 heavy/slow passing**.

3. **Milestone A — adaptive gait robustness (7.7 → 8.0/10)**
   - `ai_cad/gait_adaptation.py`: `GaitMorphologyFeatures` extraction from MuJoCo + FeatureTree.
   - `ai_cad/gait.py`: `morphology_aware_walk_params` / `morphology_aware_balance_gains`; humanoid `forward_bias_rad=0.03`; quadruped trot selection in `run_step_test`.
   - `ai_cad/morphology_physics.py`: deterministic 6-config per-candidate gait sweep (`_sweep_gait_for_candidate`); total-mass-aware position-actuator gain scaling.
   - `tests/test_gait_adaptation.py`, `tests/test_morphology_grid.py`, `tests/test_morphology_physics.py`: morphology features, grid pass-rate, mass-perturbation, and actuator-gain tests.
   - `scripts/progress_report.py`: dynamic milestone detection from plan checkbox state.
   - Full suite verified: **380 default + 241 heavy/slow passing** (1 xfailed).

Score moved from **7.7 → 8.0 / 10** after adaptive gait robustness delivered the targeted grid and mass-perturbation pass rates.

## First concrete next step

Milestone A is closed. Move into **Milestone B (Phase 31) — Structural dynamics / FEA for links** to raise the score toward 8.3/10.
