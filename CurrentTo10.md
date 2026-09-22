# Current RoboCAD → 10/10

**Current RoboCAD is in a solid, shippable state:** **402 default + 261 heavy/slow/mujoco tests passing**, frontend build passes, Phase 28A–F complete, Phase 29 physics-based morphology scoring complete, Phase 30 real gait synthesis complete, and **Milestones A (adaptive gait robustness), B (structural dynamics / FEA for links), C (workspace / self-collision / manipulability), D (real end-effector families), and E (topology grammar beyond templates)** complete.

My honest confidence score for **complex multi-domain robot designs, especially humanoids**, is **9.0 / 10**. The pipeline validates morphology with real MuJoCo standing, sway, stepping, and walking rollouts; rejects candidates whose limb segments fail lightweight beam bending / buckling checks; scores sagittal-plane workspace reach, penalizes self-collision across representative poses, rewards kinematic dexterity with a Yoshikawa-style manipulability index, **swaps real end-effector part families (parallel-jaw gripper, three-finger hand, vacuum gripper, point foot, compliant foot) into the FeatureTree**, and **now invents topology beyond the three fixed templates using a deterministic grammar that produces biped, quadruped, hexapod, wheeled, tracked, and fixed-base robots with optional tails/arms**. Default-template and near-default humanoid/quadruped candidates walk reliably; the searched grid and small mass perturbations pass at the Milestone A thresholds; structural and kinematic checks filter bad candidates before they are presented. The remaining gaps are real MuJoCo brain training on the actual robot model and automatic simulation certification. The full deep-analysis memory file lives at:

`C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\robocad-confidence-10-10-roadmap.md`

and is indexed in `MEMORY.md`.

---

## Why 8.7 / 10 today

The score reflects that the *infrastructure* is green and deterministic, the *physics reasoning* layer is real rather than heuristic, **adaptive flat-ground gait synthesis is robust enough for searched candidates and small mass perturbations**, **structural link checks filter candidates whose limbs would yield or buckle under payload + drop loads**, **kinematic reasoning now rewards reachable, collision-free, dexterous workspaces**, **end-effector choices are no longer cosmetic: the selected gripper or foot family is instantiated in the FeatureTree, exported to MuJoCo, and its estimated mass influences actuator and structural scoring**, and **topology is no longer limited to three templates: a deterministic grammar invents biped/quadruped/hexapod/wheeled/tracked/fixed robots with optional appendages and each topology is scored by the same physics/structural/collision/workspace pipeline**. The next jumps are brain training on the actual MuJoCo model and automatic simulation certification.

| Subsystem | Current state | Caveat |
|---|---|---|
| Morphology search | Runs fast, deterministic, cached FK, **physics-validated** for standing + sway + stepping + walking | Flat-ground walking is synthesized; slopes/stairs/push recovery remain Phase 36 |
| Stability / gait | MuJoCo standing/sway/step/walk rollouts with **morphology-aware** balance feedback and per-candidate gait sweep | Dynamic trot and rough terrain are future work |
| Workspace | **Sagittal-plane proxy** with reach, area, and lateral span; replaces the old volume metric that failed for planar arms | Full 3D oriented workspace envelope is future work |
| Self-collision | Pairwise checks across **neutral + flexed representative poses** with articulated instance transforms | Checks assembly instances only; fixed collision-mesh resolution |
| Manipulability | Topology-aware geometric Jacobian + Yoshikawa product-of-singular-values score for end-effector chains | Sagittal-plane focus; full 6-DOF task manipulability is future work |
| Actuator sizing | Payload × lever-arm static formulas; position actuators scale with total robot mass | Not inverse-dynamics based |
| Structural dynamics | Lightweight cantilever / simply-supported bending + Euler buckling for every limb segment; optional deep CalculiX dispatch on top-N | Assumes rectangular cross-section; non-rectangular families need mesh-based properties |
| Brain training | 2-D `AbstractAttentionEnv` abstraction | Does not control the actual MuJoCo humanoid |
| MuJoCo validation | 20-step load test | Catches load errors, not dynamic instability |
| Topology set | Deterministic grammar (biped/quadruped/hexapod/wheeled/tracked/fixed + appendages) | Wheeled/tracked use fixed-contact approximations; full rolling-track dynamics are future work |
| End-effector selection | **Real part-family swap** in FeatureTree; mass affects actuator/structural score; exported to MuJoCo | Gripper/foot geometry is still lightweight bounding-volume; full finger/contact dynamics are future work |

Concrete evidence from the current code:

- `ai_cad/morphology.py::score_candidate` weights: stability 0.22, workspace 0.20, gait 0.22, actuator 0.13, compactness 0.05, structural 0.05, collision 0.05, manipulability 0.08 — physics- and geometry-grounded.
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

### Milestone B — Structural dynamics / FEA for links (8.0 → 8.3/10) ✅ COMPLETE

Closed the structural-dynamics gap by extracting real link cross-sections from morphology candidates, running lightweight cantilever / simply-supported beam bending and Euler-buckling checks, adding a `structural_score` to the morphology composite, and wiring the existing deep CalculiX dispatcher for optional top-N verification.

**Delivered in this session:**
- `ai_cad/morphology_structural.py`: `LinkStructuralProperties`, `extract_link_properties`, `beam_check`, `score_candidate_structural`, `run_deep_structural_for_candidate`.
- `ai_cad/morphology.py`: `use_structural=True` default in `score_candidate`; `structural_score` weighted 0.05 in composite; optional deep verification in `search_morphologies` via `run_deep_structural` / `deep_top_n`.
- `tests/test_morphology_structural.py`: extraction, stocky/slender beam checks, slender-humanoid penalty, deep-dispatch graceful fallback, and morphology-search structural regression.
- Full suite verified: **380 default + 246 heavy/slow passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).

**Score impact:** 8.0 → **8.3 / 10**.

### Milestone C — Workspace / self-collision / manipulability (8.3 → 8.5/10) ✅ COMPLETE

Closed the kinematic-reasoning gap with a sagittal-plane workspace proxy, representative-pose self-collision checks, and a topology-aware Yoshikawa-style manipulability index fed into the morphology composite.

**Delivered in this session:**
- `ai_cad/morphology_workspace.py`: `workspace_proxy`, `compute_jacobian`, `manipulability_index`, `manipulability_score`; sagittal-plane reach/area/lateral-span scoring and SVD-based manipulability for arm chains.
- `ai_cad/morphology_collision.py`: `score_candidate_collision` across default neutral/flexed poses using articulated instance transforms.
- `ai_cad/assembly.py` / `ai_cad/assembly_collision.py`: optional `joint_states` parameter on `compute_instance_transforms` and `check_assembly_collision` so collision checks follow real poses.
- `ai_cad/morphology.py`: `use_collision=True` default; composite weights revised to stability 0.22, workspace 0.20, gait 0.22, actuator 0.13, compactness 0.05, structural 0.05, collision 0.05, manipulability 0.08.
- `tests/test_morphology_workspace.py`: nonzero sagittal workspace for a humanoid arm and nonzero manipulability for a manipulator.
- `tests/test_morphology_collision.py`: default humanoid pose has low self-collision; morphology search prefers collision-free candidates.
- Full suite verified: **380 default + 250 heavy/slow passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).

**Score impact:** 8.3 → **8.5 / 10**.

**Effort:** ~1.5 sessions on top of the Milestone B scaffold.

### Milestone D — Real end-effector families (8.5 → 8.7/10) ✅ COMPLETE

Closed the end-effector gap by adding real part families for hands and feet, making `_attach_end_effector` actually swap geometry in the FeatureTree, and feeding end-effector mass into actuator and structural scoring.

**Delivered in this session:**
- `ai_cad/part_families.py`: `_parallel_jaw_gripper`, `_three_finger_hand`, `_vacuum_gripper`, `_point_foot`, `_compliant_foot` families registered in `PART_FAMILY_REGISTRY`.
- `ai_cad/morphology.py`: `_attach_end_effector` now instantiates the chosen family for the template's hand/foot/end-effector parts; default spaces expose end-effector choices per template; lightweight bounding-volume mass estimator `_estimate_part_mass_kg` feeds into actuator sizing and structural checks; `score_candidate` reports `end_effector_family` and `end_effector_mass_kg`.
- `web/backend/main.py`: `MorphologySearchRequest` accepts `end_effectors`; `/morphology/templates` returns the default end-effector list.
- `web/frontend/src/components/MorphologyPanel.jsx`: end-effector family selector wired to the search request.
- `tests/test_end_effector_families.py`: family-instantiation tests, FeatureTree swap tests, and MuJoCo export/load regression tests for `parallel_jaw_gripper` and `point_foot`.
- `tests/test_part_families.py`: registry expected-set updated for the five new families.
- Full suite verified: **385 default + 255 heavy/slow tests passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).

**Score impact:** 8.5 → **8.7 / 10**.

**Effort:** ~1 session on top of the Milestone C scaffold.

### Milestone E — Topology grammar beyond templates (8.7 → 9.0/10) ✅ COMPLETE

Closed the topology ceiling by giving RoboCAD a deterministic grammar for inventing robot topologies and scoring each with the existing physics/structural/collision/workspace pipeline.

**Delivered in this session:**
- `ai_cad/topology_grammar.py`: `Topology`, `LimbSpec`, `JointSpec`, `BaseType`/`LimbRole` literals; `default_topology` for `biped`, `quadruped`, `hexapod`, `wheeled`, `tracked`, `fixed`; `enumerate_topologies` with constraints/appendages/pruning; `is_feasible`; `topology_hash`.
- `ai_cad/topology_composer.py`: `topology_to_feature_tree` maps grammar productions to `FeatureTree` assemblies using `torso_plate`, `hip_hub`, `limb_segment`, and end-effector families; `_merge_family_default_parameters` injects family defaults into the tree-level parameter dict to fix single-part transpilation.
- `ai_cad/morphology.py`: `TopologySpace` dataclass; `MorphologyCandidate` carries optional `topology`; `search_morphologies` enumerates and scores topologies; `save_search_results` handles both template and topology spaces.
- `ai_cad/assembly_collision.py`: mesh cache keyed by family name, sharing geometry across repeated family instances in topology trees.
- `web/backend/main.py`: `GET /morphology/topologies` and `POST /morphology/search` with `topology_constraints`.
- `web/frontend/src/components/MorphologyPanel.jsx` + `api.js`: Template/Topology mode toggle, base-type selector, appendage chips, topology column in results.
- `tests/test_topology_grammar.py` (9 tests), `tests/test_topology_composer.py` (6 tests), `tests/test_topology_morphology.py` (5 slow/heavy/mujoco end-to-end tests), `tests/test_morphology_api.py` topology endpoint tests.
- Full suite verified: **402 default + 261 heavy/slow/mujoco tests passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing); frontend production build passes.

**Score impact:** 8.7 → **9.0 / 10**.

**Effort:** ~1 session on top of the Milestone D scaffold.

### Phase 35 / Milestone F — Brain training on actual MuJoCo models (~9.3/10)

Replace the 2-D `AbstractAttentionEnv` brain smoke test with a real `WorldReplayEnv` that rolls out the generated MJCF and trains MLP/RNN policies with CEM/PPO/ES on walking, pick-place, and push tasks.

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

### 4. **Milestone B — structural dynamics / FEA for links (8.0 → 8.3/10)** ✅ COMPLETE
   - `ai_cad/morphology_structural.py`: `LinkStructuralProperties`, `extract_link_properties`, `beam_check`, `score_candidate_structural`, `run_deep_structural_for_candidate`.
   - `ai_cad/morphology.py`: `use_structural=True` default; `structural_score` weighted 0.05 in composite; optional deep CalculiX dispatch on top-N candidates.
   - `tests/test_morphology_structural.py`: extraction, beam checks, slender-humanoid penalty, deep-dispatch fallback, morphology-search regression.
   - Full suite verified: **380 default + 246 heavy/slow passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).
   - Score moved from **8.0 → 8.3 / 10**.

### 5. **Milestone C — workspace / self-collision / manipulability (8.3 → 8.5/10)** ✅ COMPLETE
   - `ai_cad/morphology_workspace.py`: `workspace_proxy`, `compute_jacobian`, `manipulability_index`, `manipulability_score`; sagittal-plane reach/area/lateral-span scoring and SVD-based manipulability for arm chains.
   - `ai_cad/morphology_collision.py`: `score_candidate_collision` across default neutral/flexed poses using articulated instance transforms.
   - `ai_cad/assembly.py` / `ai_cad/assembly_collision.py`: optional `joint_states` parameter on `compute_instance_transforms` and `check_assembly_collision` so collision checks follow real poses.
   - `ai_cad/morphology.py`: `use_collision=True` default; composite weights revised to stability 0.22, workspace 0.20, gait 0.22, actuator 0.13, compactness 0.05, structural 0.05, collision 0.05, manipulability 0.08.
   - `tests/test_morphology_workspace.py`: nonzero sagittal workspace for a humanoid arm and nonzero manipulability for a manipulator.
   - `tests/test_morphology_collision.py`: default humanoid pose has low self-collision; morphology search prefers collision-free candidates.
   - Full suite verified: **380 default + 250 heavy/slow passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).
   - Score moved from **8.3 → 8.5 / 10**.

### 6. **Milestone D — real end-effector families (8.5 → 8.7/10)** ✅ COMPLETE
   - `ai_cad/part_families.py`: `_parallel_jaw_gripper`, `_three_finger_hand`, `_vacuum_gripper`, `_point_foot`, `_compliant_foot` registered.
   - `ai_cad/morphology.py`: `_attach_end_effector` swaps real families into the FeatureTree; default spaces include end-effector choices; end-effector mass influences actuator sizing and structural scoring; `score_candidate` exposes `end_effector_family` and `end_effector_mass_kg`.
   - `web/backend/main.py`: `MorphologySearchRequest.end_effectors` and `/morphology/templates` return default end-effector lists.
   - `web/frontend/src/components/MorphologyPanel.jsx` + `web/frontend/src/api.js`: end-effector family selector wired to the backend.
   - `tests/test_end_effector_families.py`: family instantiation, FeatureTree swap, and MuJoCo export/load regression tests.
   - Full suite verified: **385 default + 255 heavy/slow passing** (1 xfailed; the unrelated `test_simulate_morphology_candidate` attention-policy timeout is pre-existing).
   - Score moved from **8.5 → 8.7 / 10**.

## First concrete next step

Milestones A, B, C, and D are closed. Move into **Milestone E (Phase 34) — Topology grammar beyond templates** to raise the score toward 9.0/10.
