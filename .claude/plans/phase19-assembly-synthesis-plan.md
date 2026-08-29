# Phase 19 Implementation Plan — Mechanical Assembly Synthesis

## Context

RoboCAD has completed **Batch A (Phases 16–18)**. The code can decompose multi-domain system prompts into part families, compose a `FeatureTree` with `Assembly`, `Instance`, and `Mate` objects, and export STL/STEP and simulation bundles (MJCF/URDF). All **228/228** tests pass and the live `/generate?decompose=True` path works for quadcopters, robot arms, and humanoid systems.

The next committed goal in `PLAN.md` and the end-to-end roadmap is **Phase 19: Mechanical assembly synthesis**.

## Goal

Scale the existing assembly system to multi-part mechanisms and complete mechanical subsystems. Phase 19 will:

1. Infer mates from part interfaces and intent.
2. Solve kinematic chains and closed loops.
3. Detect assembly-level collisions and clearances.
4. Export full MJCF/URDF with real joints, actuators, and sensors.
5. Replay range-of-motion in the browser.

## Design Decisions

### 1. Trigger — automatic for mechanical assemblies

When `POST /generate` receives a system prompt whose decomposition contains at least two mechanical parts with matching interfaces, or when the prompt names a mechanism (`robot arm`, `gripper`, `diff-drive chassis`, `linkage`, `gearbox`), the composer will:

- Emit `Mate` objects for every detected interface pair.
- Emit `KinematicJoint` objects connecting the affected `Instance` ids.
- Mark the assembly domain as `mechanical`.

A new `POST /designs/{id}/synthesize-assembly` endpoint will allow re-running mate inference + joint synthesis on an existing design.

*Rationale:* Keeps the current automatic decomposition path unchanged while turning fixed assemblies into articulated mechanisms when the intent clearly implies motion.

### 2. Interface library — extend part families

Extend `ai_cad/part_families.py` so every family declares one or more named `Interface` frames:

```python
@dataclass
class Interface:
    id: str
    csys: CoordinateSystem
    type: Literal["mount", "pin", "slot", "shaft", "flange"]
    mate_hint: Literal["fixed", "revolute", "prismatic"] | None = None
    mate_with: list[str] | None = None  # family/interface compatibility tags
```

Examples:
- `link` has two `pin` interfaces (`interface_a`, `interface_b`) compatible with `revolute` joints.
- `hub` has `flange` interfaces for motor arms and `shaft` interfaces for motors.
- `gripper` jaw has a `slot` interface suggesting a `prismatic` mate with the opposite jaw.

Part families already expose `interface_csys`; this plan generalizes it to a list and adds mate hints. Backward compatibility is preserved by converting a single `interface_csys` into a single `Interface` when loading older definitions.

### 3. Mate inference — rule-first, LLM-assisted

New module `ai_cad/mate_inference.py`.

Rule layer (deterministic, used in tests):
- Match interface types (`pin` ↔ `pin`, `shaft` ↔ `bore`, `flange` ↔ `flange`, `slot` ↔ `slot`).
- Respect `mate_hint`: `revolute`, `prismatic`, `fixed`.
- Avoid duplicate mates for the same instance pair.
- Order parent/child so the root instance (base/chassis/hub) is the parent.

LLM layer:
- If the rule layer returns no mates for a mechanical assembly, a short prompt asks the model to propose mates and joint types from the part list and intent.
- Output is a JSON list of mates; parsed with the same extraction helper used elsewhere.

Fallback:
- If inference fails, keep the existing `fixed` mates so the assembly still transpiles.

### 4. Kinematic loop solver

Extend `ai_cad/assembly.py`:

- Treat mates as constraints and solve them iteratively (current solver already does this for coincident/concentric/distance/parallel/perpendicular).
- Add support for `revolute` and `prismatic` mates:
  - Align Z axes and maintain a specified origin relationship.
  - Do not freeze the degree of freedom along/along the axis.
- For closed loops, run the existing iterative relaxation until convergence or a step limit; report an `overconstrained` flag if residual error is large.
- Compute a `pose_graph` (instance → world transform) and expose it for downstream export/replay.

*Rationale:* A full analytical closed-loop solver is overkill at this stage; iterative relaxation plus explicit joints in the exported physics file is enough to validate mechanisms in MuJoCo.

### 5. Collision and clearance checks

New module `ai_cad/assembly_collision.py`.

- Build a trimesh for each instance by transforming its part mesh with the solved pose.
- Pairwise minimum clearance via trimesh proximity queries.
- Optional boolean intersection to estimate overlap volume.
- Return a report listing colliding/overlapping instance pairs and the worst clearance gap.
- Add `POST /designs/{id}/assembly-collision` backend endpoint and frontend `AssemblyCollisionPanel.jsx`.

*Rationale:* Reuses the existing trimesh pipeline and existing `tolerances.py` ideas, applied at the assembly level.

### 6. Full MJCF / URDF export with joints, actuators, and sensors

Extend `ai_cad/geda_bridge/exporter.py`:

- Read `FeatureTree.assemblies[].joints` (model already exists but is not consumed).
- Convert each `KinematicJoint` into:
  - URDF: `<joint>` with correct `parent`, `child`, `origin`, `axis`, and `limit`.
  - MJCF: `<joint>` inside the child `<body>` plus `<actuator>` if the joint is actuated.
- Add a simple heuristic: revolute joints between mechanical parts are actuated by default; prismatic jaws are actuated; fixed joints are not.
- Add position/velocity/force sensors in MJCF (`<sensor>`) for every actuated joint.
- Preserve the existing single-body export path when no joints are present.

### 7. Browser range-of-motion replay

Frontend:

- New `AssemblyReplayPanel.jsx` that loads the bundle MJCF, creates a lightweight viewer using the existing Three.js STL viewer approach or by parsing the MJCF and stepping joint positions.
- For Phase 19 the replay is range-of-motion only: animate each revolute/prismatic joint through its limits, render the assembled meshes at each step, and flag any collisions detected by the backend.
- Add `GET /designs/{id}/assembly-poses` endpoint returning sampled poses for each joint within its limits.

*Rationale:* True MuJoCo-in-browser requires WASM and is out of scope; a geometry-only replay driven by the backend pose graph proves the assembly moves correctly.

### 8. Integration with existing endpoints

- `POST /generate` with `decompose=True` and mechanical system prompts will now emit `joints` in the feature tree.
- `POST /designs/{id}/simulate` will export a full mechanism-aware MJCF/URDF when joints exist.
- `GET /designs/{id}/assembly` already returns the assembly; extend it to include `joints` and `collision_summary`.

### 9. Tests

New test files and additions:

- `tests/test_mate_inference.py` — rule-based mate inference for robot arm, quadcopter arms, gripper.
- `tests/test_kinematic_solver.py` — revolute/prismatic mate relaxation converges; closed-loop arm reaches a stable pose.
- `tests/test_assembly_collision.py` — collision and clearance for overlapping vs spaced instances.
- `tests/test_geda_bridge_mechanism.py` — MJCF/URDF exports contain expected joints/actuators/sensors and load in MuJoCo; arm/gripper/diff-drive chassis end-to-end.
- `tests/test_composer.py` — extend with joint assertions for mechanical systems.

Target: **at least 250 passing tests** (228 current + ~22 new). Stretch: 260.

### 10. Documentation

- Update `PLAN.md` Phase 19 section to "in progress" and add shipped date on completion.
- Update `README.md` banner and test count.
- Update `memory.md` phase table and status.
- Update `dossiers/robocad-end-to-end-roadmap.md` to mark Phase 19 in progress and list resolved caveats.
- Add `docs/assembly_synthesis.md` describing interface library, mate inference, collision checks, and replay.

## Out of scope for Phase 19

- Closed-loop analytical IK (Phase 23 / robot-brain training).
- Real-time physics-in-browser rendering (Phase 22+).
- Full electronics routing (Phase 21).
- Aerodynamics/thermal solvers (Phase 20).
- Automatic gear train / belt / chain synthesis (Phase 24).

## Implementation order

1. Extend `ai_cad/part_families.py` with `Interface` list and mate hints; keep backward compatibility.
2. Create `ai_cad/mate_inference.py` rule layer + LLM fallback.
3. Extend `ai_cad/composer.py` to call mate inference and emit `KinematicJoint` for mechanical assemblies.
4. Extend `ai_cad/assembly.py` solver with revolute/prismatic mates and pose graph.
5. Create `ai_cad/assembly_collision.py` with pairwise clearance/intersection checks.
6. Extend `ai_cad/geda_bridge/exporter.py` to write joints/actuators/sensors in MJCF/URDF.
7. Add backend endpoints: `/designs/{id}/synthesize-assembly`, `/designs/{id}/assembly-collision`, `/designs/{id}/assembly-poses`.
8. Frontend: `AssemblyReplayPanel.jsx`, extend `AssemblyPanel.jsx`, extend `api.js`.
9. Tests for each new module and end-to-end mechanisms.
10. Docs and memory sync.
11. Full pytest run, live demo, commit, push.

## Open questions

1. Do you want closed-loop mechanism support beyond simple serial chains in Phase 19 (e.g., four-bar linkages, differential drives)? The plan includes a solver that can handle loops, but detailed loop synthesis for arbitrary prompts may need to be rule-scoped.
2. Should the browser replay be a lightweight geometry viewer in this phase, or do you want to expose a MuJoCo WASM viewer (larger scope)? The plan assumes lightweight geometry replay.
3. Are there specific mechanical subsystems you want prioritized for the end-to-end demo (robot arm, gripper, diff-drive chassis)?
