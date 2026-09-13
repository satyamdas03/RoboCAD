# Current RoboCAD → 10/10

**Current RoboCAD is in a solid, shippable state:** 380 default + 223 heavy/slow tests passing, frontend build passes, Phase 28A–F are complete, and the repo is clean and pushed.

My honest confidence score for **complex multi-domain robot designs, especially humanoids**, is **6.8 / 10**. Not because anything is broken, but because the pipeline’s physics judgment is still shallow. I have written a full deep-analysis memory file at:

`C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\robocad-confidence-10-10-roadmap.md`

and indexed it in `MEMORY.md`.

---

## Why 6.8 / 10 today

The score reflects that the *infrastructure* is green and deterministic, but the *reasoning* about whether a design will actually work in the real world is still heuristic.

| Subsystem | Current state | Caveat |
|---|---|---|
| Morphology search | Runs fast, deterministic, cached FK | Composite score is **heuristic**, not physics-validated |
| Stability / gait | Support-polygon + ZMP margin | Does not prove the robot can actually take a step |
| Workspace | Caps at 4096 samples | Humanoid sagittal arms report `workspace_volume = 0.0 mm³`, falls back to max reach |
| Actuator sizing | Payload × lever-arm static formulas | Not inverse-dynamics based |
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

### Phase 29 — Physics-based morphology scoring (~7.5/10)

Replace heuristic stability/gait with MuJoCo standing/sway/step tests. Cache MuJoCo models across candidates. Add `physics_score_candidate` and prove that high-scoring candidates do not NaN.

**Effort:** 3–4 weeks.

### Phase 30 — Real gait synthesis and validation (~8.0/10)

Build a trajectory-generator + IK + balance-feedback controller for biped/quadruped templates. Run 5-second flat/slope/stair walking rollouts. Score by distance, pitch/roll, energy, falls.

**Effort:** 6–8 weeks.

### Phase 31 — Structural dynamics / FEA for links (~8.3/10)

Wire the existing deep FEA dispatcher into robot-template certification. Add beam bending / buckling checks using real link cross-sections and materials.

**Effort:** 4–6 weeks.

### Phase 32 — Self-collision and manipulability (~8.5/10)

Sample task poses, run collision checks, compute manipulability index. Add `collision_penalty` and `manipulability_score` to the composite.

**Effort:** 3–4 weeks.

### Phase 33 — Real end-effector families (~8.7/10)

Add part families for parallel-jaw gripper, three-finger hand, vacuum gripper, point/compliant feet. Make `_attach_end_effector` actually change the tree and mass distribution.

**Effort:** 4–5 weeks.

### Phase 34 — Topology search beyond templates (~9.0/10)

Implement a grammar for robot topologies: base type, limb count, attachment points, joint sequences. Search the grammar and validate each with Phases 29–32.

**Effort:** 8–10 weeks. This is the hardest layer.

### Phase 35 — Brain training on actual MuJoCo models (~9.3/10)

Replace `AbstractAttentionEnv` with a `WorldReplayEnv` that rolls out the real MJCF. Train MLP/RNN policies with CEM/PPO/ES on actual robot tasks (walk, pick-place, push).

**Effort:** 8–12 weeks.

### Phase 36 — Automatic simulation certification (~9.6/10)

Extend certification with randomized terrain, payload lift, push recovery, drop test, actuator saturation. Run automatically after every complex design.

**Effort:** 4–6 weeks.

### Phase 37 — Sim-to-real bridge (~9.8/10)

System identification from real telemetry, calibrated domain randomization, safety-guarded deployment. This is Phase 27D, currently hardware-blocked.

**Effort:** 6–12 months, gated on physical hardware.

### Phase 38 — Fully automated voice-to-certified-design (~10/10)

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

## First concrete next step

If you want to start moving the score immediately, the highest-return single action is **Phase 29: physics-based morphology scoring**. It directly fixes the observed problem that a 0.80 composite candidate can still be MuJoCo-unstable.

Deliverable:

- `ai_cad/morphology_physics.py` with `physics_score_candidate`
- MuJoCo standing / sway / step tests
- Composite score updated to use physics metrics
- 5–10 new tests proving high-score candidates do not NaN

This alone would raise confidence from **6.8 to roughly 7.5 / 10**.
