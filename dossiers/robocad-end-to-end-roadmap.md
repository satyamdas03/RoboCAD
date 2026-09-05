# RoboCAD End-to-End Vision Roadmap

**Date:** 2026-08-29  
**Horizon:** ~5–7 years  
**North Star:** voice/text/sketch → multi-domain parametric CAD → per-part multi-physics testing → assembly → world-model simulation → HERMES oversight → robot brain trained on synthetic data with retraining loops.  
**First commercial milestone:** PATH1 / GEDA Bridge (Phases 14A–15B) — complete, 187/187 tests.  
**Current milestone:** HERMES cross-domain conversational supervisor (Phase 26 foundation) — complete, 454/454 tests across default, heavy/slow, and mujoco tiers; tool registry, approval gates, plan execution, explanation engine, JSON-persisted sessions, backend endpoints, and frontend `HermesPanel` are live; Phase 27 — real-world feedback loop / sim-to-real — is next.  
**Domain tracks:** mechanical assemblies, aerodynamics / thermal / propulsion geometry, electronics / mechatronics form-factor co-design, humanoid / full-robot system synthesis, world-model simulation, robot brain training.  
**Related:** [`PLAN.md`](../PLAN.md) Sections 10–14, [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md)

---

## Cross-cutting foundation

Maintained across the entire roadmap:

- **Benchmark discipline:** keep the 30-prompt complexity suite green; publish scores after every model or prompt change.
- **Test pyramid:** unit → integration → simulation-load → end-to-end skill.
- **Model zoo:** maintain both local (Ollama) and cloud (Claude 5) generation paths.
- **Schema governance:** version feature-tree, assembly, bundle, and world-model schemas; provide migration tools.
- **Domain-aware core:** a shared parametric/feature-tree core with domain-specific extensions (solid mechanical parts, aero/thermal surfaces, PCB form factors, kinematic chains).
- **Explicit boundaries:** full silicon EDA (transistor layout, SPICE, lithography/PnR) and autonomous high-fidelity CFD remain external tools with export bridges, not in-scope replacements.
- **CI/CD + git hygiene:** every change committed, every phase demo recorded.
- **Documentation:** keep `README.md`, `PLAN.md`, `PRODUCT.md`, dossiers, and memory files in sync.

---

## Phase 13 — Robust generation + local model specialization

**Goal:** Get the Phase 8 complexity benchmark to ≥80% on T1–T4 and close extractor/self-correction edge cases.

**Status:** ✅ Complete on the T1–T4 quality gate.

**Current state:**
- 134/134 unit tests pass.
- Full 30-prompt benchmark with `claude-sonnet-5-20250501`: **21/30 (70.0%)**.
- T1–T4 aggregate: **21/24 (87.5%)**, above the ≥80% gate.
- T5 aggregate: **0/6** on targeted re-run; T5 remains genuinely hard and is not gating Phase 14A.
- Ollama fine-tuning scaffolding is in place (`robocad-ft:latest` Modelfile created).
- Latest extraction/retry fix (`06a373c`) hardens `_extract_code_block()` against nested markdown fences and increases retries to 5.

**Deliverables:**
- ✅ Claude Sonnet 5 T1–T4 run at ≥80% (achieved 87.5%).
- ✅ Root-cause report for remaining failures: token limits, nested markdown fences in self-correction, and genuine geometry complexity (assemblies/fillets).
- ✅ Aggressive nested-fence extraction in `_extract_code_block()`.
- ⏳ Clean self-correction prompt to prevent nested fences (incremental improvement).
- ⏳ Local model dataset completion and first fine-tuned checkpoint (background work; not blocking).
- ✅ Updated `PLAN.md` / `README.md` / dossiers / memory files with Phases 13–28 roadmap.

**Timeline:** 1–2 months (core gate achieved; remaining work in parallel).

---

## Phase 14A — GEDA Bridge: MuJoCo / URDF exporter

**Goal:** Convert any RoboCAD part or assembly into a simulation-ready bundle.

**Status:** ✅ Complete — 2026-08-27.

**Deliverables:**
- `ai_cad/geda_bridge/exporter.py` with `export_to_mujoco()` and `export_to_urdf()`.
- Bundle schema v2.0.0: manifest, meshes, inertial JSON, MJCF, URDF, DFM report.
- Backend endpoints: `POST /designs/{id}/simulate`, `GET /designs/{id}/bundle`, `GET /designs/{id}/simulation`.
- Frontend "Simulate" button + download bundle panel.
- Verification: mass > 0, positive-definite inertia, CoM inside convex hull.
- Runtime validation: MuJoCo loads MJCF/URDF and simulates 20 steps for cube, cylinder, L-bracket, and 2-part assembly.
- Tests: cube, cylinder, L-bracket, 2-part assembly, gripper jaw — **152/152 passing**.

**Timeline:** 2–3 months.

---

## Phase 14B — Standard manipulation scene templates

**Goal:** Provide reusable scene templates so `LearningRobotics` can drop a RoboCAD asset into a task.

**Status:** ✅ Complete — 2026-08-27.

**Deliverables:**
- `ai_cad/geda_bridge/scene_templates.py` with `ManipulationScene` builder and `SceneDescription` / `SceneObject` / `SceneGoalRegion` models.
- Scene templates: `gripper_cube_grasp`, `bracket_hook_hang`, `wedge_push_block`, `peg_insertion`.
- Template composition API: `set_asset()`, `add_object()`, `define_goal_region()`.
- `export_scene_to_mjcf()` writes a standalone MJCF world.
- Backend endpoints: `POST /designs/{id}/scene` and `GET /designs/{id}/scene`.
- Frontend `SceneTemplatePanel.jsx` with template selector and download link.
- End-to-end tests: 8 new tests, full suite **160/160 passing**; every generated scene loads and simulates in MuJoCo.

**Timeline:** 1 month.

---

## Phase 15A — LearningRobotics handshake

**Goal:** `LearningRobotics` consumes a RoboCAD bundle, loads it into a standard scene, and runs a physics stability check.

**Status:** ✅ Complete — 2026-08-27.

**Deliverables:**
- `docs/BUNDLE_CONTRACT.md` — OpenAPI / JSON-Schema contract for bundle ingestion.
- `ai_cad/geda_bridge/loader.py` — reference MuJoCo bundle loader + Isaac Sim stub.
- `ai_cad/geda_bridge/capabilities.py` — in-code capability registry.
- Backend endpoints: `GET /capabilities`, `POST /designs/{id}/handshake`, `GET /designs/{id}/handshake`.
- Frontend `CapabilitiesPanel.jsx`.
- End-to-end test: RoboCAD exports wedge → composes `wedge_push_block` → MuJoCo 10 s rollout → stability verified.
- Full pytest suite: **170 passed**.

**Caveats resolved during acceptance:**
- Isaac Sim loader skeleton expanded with real `omni.isaac.core` imports (local/conditional so the module still imports outside Isaac Sim).
- Nightly cross-repo CI workflow `.github/workflows/learningrobotics_handshake.yml` added against `satyamdas03/LearningRobotics`.
- Backend handshake tests now seed a real build123d-scale wedge STL and assert `success is True`.
- Two exporter/loader bugs fixed: bundle meshes are written in meters; rollout metrics are cast to native Python types for FastAPI serialization.

**Timeline:** 1–2 months.

---

## Phase 15B — RoboCompiler asset pipeline

**Goal:** When a human demonstrates a skill on video, RoboCAD suggests/generates a custom end-effector and `LearningRobotics` trains on it.

**Status:** ✅ Complete — 2026-08-27.

**Deliverables:**
- Skill-to-part recommendation: `ai_cad/geda_bridge/skill_recommend.py` maps skill descriptions to scene templates + default policy configs.
- Auto-generated part variants: `ai_cad/geda_bridge/variant_sweep.py` sweeps feature-tree parameters, exports each variant as a verified bundle, and reports aggregate validity/stability.
- Batch bundle export for variant sweeps: `run_variant_sweep()` generates N bundles, verifies each, and optionally runs a 2 s MuJoCo stability check.
- Trainable push-policy smoke test: `ai_cad/geda_bridge/skill_smoke.py` implements a NumPy-only CEM-trained TinyMLP policy for a `wedge_push_block`-derived push scene. The policy is evaluated over multiple rollouts and reports success rate.
- Backend endpoints: `POST /designs/{id}/recommend-skill`, `POST /designs/{id}/train-skill`, `GET /designs/{id}/skills`, `POST /designs/{id}/variant-sweep`.
- Frontend: `SimulatePanel.jsx` now has tabs for bundle generation, skill training, and variant sweep.
- Tests: `tests/test_geda_bridge_skill.py` (7 tests) + backend endpoint tests in `tests/test_web_backend.py` (4 tests); full pytest suite **187/187 passing**.

**Notes / honest scope:** The "video" part of video → part → trained skill is not implemented; it remains future work once a video-to-skill embedding pipeline is available. The current milestone proves the part → trained-skill loop end-to-end in simulation.

**Timeline:** 2–3 months (smoke-test layer shipped; video ingestion remains future work).

---

## Phase 16 — Cross-domain input layer

**Goal:** Accept voice, text, and sketch input for any robotics domain, detect the domain, and route the intent to the right parametric representation and physics backend.

**Status:** ✅ Complete — 2026-08-29 (text + sketch input; voice/STT deferred to later phases).

**Deliverables:**
- ✅ `ai_cad/domain.py` domain classifier with keyword + optional `sentence-transformers` embedding fallback.
  - Six domains: `mechanical`, `aero`, `thermal`, `electronics`, `humanoid`, `multi`.
  - Keyword matching uses regex word-boundary patterns; embedding fallback activates when keywords are inconclusive.
- ✅ `ai_cad/intent_parser.py` per-domain LLM intent parser returning `DomainIntent`.
  - Extracts target domain, confidence, inferred parameters, constraints, feature-tree operations, and surface/PCB/kinematic hints.
- ✅ Backend integration in `web/backend/main.py`:
  - `POST /classify-domain`
  - `GET /designs/{design_id}/domain-intent`
  - `detect_domain` flag on `POST /generate` that persists `domain_intent.json` with every design.
- ✅ Frontend integration:
  - `DomainBadge.jsx` with domain-specific colors.
  - Domain badges shown in `HistorySidebar.jsx` for each persisted design.
  - Domain-intent inspector card in `App.jsx` right panel.
  - "Detect domain" checkbox in `PromptInput.jsx`.
- ⏳ Whisper/local STT integration remains future work.
- ⏳ Ambiguity-resolution clarifying-questions UI remains future work.

**Tests:**
- `tests/test_domain_classifier.py` — keyword classification + embedding fallback + tie-breaking.
- `tests/test_intent_parser.py` — mocked LLM extraction + fallback to mechanical.
- `tests/test_web_backend.py` — `/classify-domain` and `/generate?detect_domain=true` endpoints.
- Full pytest suite: **201/201 passing**.

---

## Phase 17 — Domain-aware parametric representation

**Goal:** Extend the feature tree and transpiler to represent not only solid extrusions, but also surfaces, shells, kinematic chains, and electronics form factors.

**Status:** ✅ Complete — 2026-08-29 (schema + sketch support; aero/thermal surface transpiler and kinematic-tree backend remain Phase 20/23).

**Deliverables:**
- ✅ Feature-tree schema bumped to **v2.0.0** in `ai_cad/feature_tree.py`:
  - `domain` tag added to `Feature`, `Part`, `Assembly`, and `FeatureTree` (defaults to `mechanical`).
  - Top-level `features` list supports `Feature | SurfaceFeature | PCBOutline` via discriminated union.
  - `SurfaceFeature` model for aero/thermal surfaces.
  - `KinematicJoint` model with `revolute`, `prismatic`, `spherical`, and `fixed` joint types.
  - `PCBOutline` model for board shape + mounting holes + connector keepouts.
  - `SketchEntity.type` extended with `airfoil`; added `naca` (4-digit code) and `chord` fields.
  - `Sketch.points` field to carry computed 2D profiles.
- ✅ Airfoil point generation in `ai_cad/sketch_solver.py`:
  - `_naca_4digit_points(code, chord, n=40)` computes cambered/thickness profiles.
  - `_solve_airfoils(sketch)` populates `points` on airfoil entities.
- ✅ `created_at` made optional with UTC default to keep legacy trees valid.
- ⏳ Transpiler backends: build123d for solids is unchanged; aero/thermal parametric surface geometry and kinematic-tree helpers are scaffolded in schema and will be wired in Phases 20 and 23.
- ⏳ Validation of full domain-specific artifacts (surface mesh, kinematic description) remains future work.

**Tests:**
- `tests/test_feature_tree_v2.py` — domain tags, surface features, kinematic joints, PCB outlines.
- `tests/test_sketch_airfoil.py` — NACA 4-digit airfoil point generation.
- Full pytest suite: **201/201 passing**.

**Notes / honest scope:** The Phase 17 milestone intentionally stopped at the *representation* layer. It gives downstream phases a typed, versioned schema and a concrete airfoil sketch example, without over-generalizing the transpiler before domain-specific geometry requirements are proven.

---

## Phase 18 — Automatic decomposition and domain part families

**Goal:** Split complex system intents into parts and choose domain-specific part families/templates.

**Status:** ✅ Complete — 2026-08-29.

**Deliverables:**
- ✅ `ai_cad/decomposition.py` — rule-based system decomposer for quadcopter, robot arm, humanoid, fixed-wing, with LLM hook and single-part fallback.
- ✅ `ai_cad/part_families.py` — `PartFamily` registry of 12 families across mechanical, aero, thermal, electronics, and humanoid domains.
- ✅ `ai_cad/composer.py` — `compose_feature_tree()` builds a complete `FeatureTree` with global parameters, per-domain parts, assembly, instances, and inferred mates.
- ✅ Backend: `POST /decompose` and `decompose=True` flag on `POST /generate`.
- ✅ Frontend: `DecomposePanel.jsx` + auto-decompose checkbox in `PromptInput.jsx`.
- ⏳ Interface library per domain: mechanical mates, wing spar joints, PCB mounting patterns, humanoid joint limits — partially scaffolded via mates in `composer.py`; full library in Phase 19/20/21.
- ⏳ Assembly-level collision/intersection checks remain Phase 19 scope.

**Tests:**
- `tests/test_decomposition.py` — rule-based decomposition for standard systems.
- `tests/test_part_families.py` — registry, parameter merging, interface frames.
- `tests/test_composer.py` — compose + transpile + execute assemblies.
- Full pytest suite: **228/228 passing**.

**Timeline:** 3–4 months. **Risk:** fully open-ended decomposition is unsolved; start with parameterized part families.

---

## Phase 19 — Mechanical assembly synthesis

**Goal:** Scale the existing assembly system to multi-part mechanisms and complete mechanical subsystems.

**Status:** ✅ Complete — 2026-08-29.

**Deliverables:**
- ✅ `ai_cad/part_families.py` `Interface` library with type and `mate_hint` metadata.
- ✅ `ai_cad/mate_inference.py` rule-first mate/joint inference from part interfaces.
- ✅ `ai_cad/assembly.py` revolute/prismatic mate relaxation, overconstrained detection, and range-of-motion pose sampling.
- ✅ `ai_cad/assembly_collision.py` pairwise trimesh clearance/interference checks.
- ✅ `ai_cad/geda_bridge/exporter.py` hierarchy-aware MJCF/URDF with joints, actuators, and sensors.
- ✅ Backend endpoints: `POST /designs/{id}/synthesize-assembly`, `POST /designs/{id}/assembly-collision`, `GET /designs/{id}/assembly-poses`.
- ✅ Frontend `AssemblyReplayPanel.jsx` and `AssemblyCollisionPanel.jsx`.
- ✅ Default `robot arm with gripper` layout synthesizes a true parallel-jaw **prismatic gripper** on the forearm.

**Tests:** arm, parallel-jaw prismatic gripper, and fixed-only assemblies load in MuJoCo; full pytest suite **251/251 passing**.

**Timeline:** 3–4 months.

---

## Phase 20 — Aerodynamics, thermal, and propulsion geometry

**Goal:** Generate parametric airfoils, wings, ducts, heat sinks, and propeller blades, and export CFD-ready surfaces/meshes.

**Status:** ✅ Complete — 2026-08-29.

**Deliverables:**
- ✅ Parametric airfoil / wing builder: NACA 4-digit airfoil via `ai_cad/sketch_solver.py`, extruded wings via `SurfaceFeature(type="wing")`.
- ✅ Surface / shell geometry for wings and heat-sink fins; `heat_sink` family uses base plate + `GridLocations` fin array.
- ✅ Propeller blade geometry from chord/twist parameters via `SurfaceFeature(type="propeller_blade")` and `propeller_blade` part family.
- ✅ CFD mesh export in `ai_cad/cfd.py`: SU2 config stub and OpenFOAM `blockMeshDict` / `snappyHexMeshDict` stubs from any STL.
- ✅ Thermal fin templates via `SurfaceFeature(type="heat_sink")`; duct family remains solid-feature based with thin-walled fallback.
- ✅ Lightweight analysis stubs: `ai_cad/aero.py` (Cl/Cd/stall lookup) and `ai_cad/thermal.py` (surface area, fin count, thermal resistance, max temp).
- ✅ Backend endpoints: `POST/GET /designs/{id}/aero-report`, `POST/GET /designs/{id}/thermal-report`, `POST /designs/{id}/cfd-mesh`.
- ✅ Frontend panels: `AeroPanel.jsx` (domain-gated for aero/multi) and `ThermalPanel.jsx` (domain-gated for thermal/multi); API helpers in `api.js`.

**Tests:** `tests/test_surface_geometry.py`, `tests/test_transpiler_surface.py`, `tests/test_part_families_aero_thermal.py`, `tests/test_cfd_export.py`; full pytest suite **276/276 passing**.

**Caveats / deferred:**
- Only NACA 4-digit symmetric/cambered thickness form is implemented; full 5-digit and custom camber lines are deferred to Phase 22.
- CFD export is intentionally a stub: it writes surface meshes and solver config skeletons, not solved flow fields. Real SU2/OpenFOAM execution belongs to Phase 22.
- `run_aero_analysis` uses a rough lookup-table/polar estimate, not a panel or RANS solver.
- `run_thermal_analysis` estimates thermal resistance from surface area; it does not run conduction/convection FEA.
- Heat-sink fin count is inferred from connected-component geometry and may miscount on complex fin geometries.

**Timeline:** 3–4 months. **Risk:** accurate CFD automation is hard; scope is geometry + template generation, not autonomous high-fidelity analysis.

---

## Phase 21 — Electronics and mechatronics integration

**Goal:** Design PCB form factors, enclosures, connectors, cable routing, and thermal management hardware that integrate with external EDA tools — *not* to replace full silicon EDA, but to close the mechanical-electrical co-design loop.

**Status:** ✅ Complete — 2026-08-29.

**Deliverables:**
- ✅ `ai_cad/electronics.py` — stack layout, footprint / connector registry, cable-channel routing, and heat-spreader/fan-mount geometry.
- ✅ Electronics part families in `ai_cad/part_families.py` (`pcb`, `enclosure`, `motor_driver`, `raspberry_pi`, `connector`, `fan`, `heat_spreader`).
- ✅ `PCBOutline` transpilation in `ai_cad/transpiler.py` — board outline, mounting holes, connector keepouts, and component placements.
- ✅ Stack decomposition + composer layout in `ai_cad/composer.py` for electronics systems.
- ✅ Lightweight analysis: board area, component count, estimated cable length, and enclosure volume.
- ✅ IDF v3.0 `.emn` / `.emp` export plus STEP placeholder for board-level EDA ingestion.
- ✅ Backend endpoints: `POST /designs/{id}/electronics-report` and `POST /designs/{id}/export-idf`.
- ✅ Frontend `ElectronicsPanel.jsx` (domain-gated for `electronics` / `multi` domains) with stack visualization and IDF download.
- ✅ **Explicit out-of-scope maintained:** transistor-level IC design, SPICE simulation, and lithography/PnR remain external EDA domains.

**Tests:** `tests/test_pcb_transpiler.py`, `tests/test_part_families_electronics.py`, `tests/test_electronics_analysis.py`, `tests/test_idf_export.py`; full pytest suite **299/299 passing**.

**Caveats / deferred:**
- IDF export writes a textual board outline and package library plus a minimal STEP placeholder. Component pin/pad geometries and copper nets live in external ECAD.
- Cable-length estimate is a simple 2-D centroid distance heuristic; real wire routing remains a Phase 22+ multi-physics / path-planning task.
- Electronics stack layout uses fixed mates; sliding/docking connectors are future work once kinematic mate inference covers small-form-factor connectors.

**Timeline:** 2–3 months.

---

## Phase 22 — Multi-physics verification engine

**Goal:** Run structural, thermal, CFD, and dynamic checks on generated designs from a single verification layer.

**Status:** ✅ Complete — 2026-08-29.

**Deliverables:**
- ✅ `ai_cad/materials.py` — shared 11-material library (`PLA`, `PETG`, `ABS`, `Nylon 12`, `Aluminum 6061`, `Mild Steel`, `Copper`, `Brass`, `Titanium 6Al-4V`, `FR4`, `CopperTrace`) with density, Young’s modulus, Poisson ratio, yield strength, conductivity, specific heat, emissivity, and thermal expansion.
- ✅ `ai_cad/verification_models.py` — Pydantic models for load cases and reports.
- ✅ `ai_cad/verification_load_cases.py` — deterministic closed templates: static stress, drop test, thermal expansion, fatigue cycles, fastener pull-out, wind-tunnel drag, heat-sink thermal resistance, and joint torque check.
- ✅ `ai_cad/mesh_quality.py` — STL pre-checker for watertightness, non-manifold edges, degenerate faces, aspect ratio, and bounding-box sanity.
- ✅ `ai_cad/verification.py` — pluggable `SolverBackend` registry and `VerificationEngine`.
- ✅ `ai_cad/fea.py` updated to consume the shared material library.
- ✅ Backend endpoints: `POST /designs/{id}/verify`, `GET /designs/{id}/verify-report/{report_id}`, `POST /designs/{id}/mesh-quality-check`.
- ✅ Frontend `VerificationPanel.jsx` with load-case selector, material picker, JSON parameter editor, pass/fail display, metrics, failure modes, and redesign suggestions.
- ✅ Failure reports include redesign suggestions: increase thickness, add ribs, raise fin count, enlarge duct, etc.

**Tests:** `tests/test_materials.py`, `tests/test_verification_load_cases.py`, `tests/test_mesh_quality.py`, `tests/test_verification_api.py`; full pytest suite **330/330 passing**.

**Caveats / deferred:**
- Solver backends are deterministic pre-solver checks and conservative hand-calculations, not replacements for commercial FEA/CFD execution. Real SU2/OpenFOAM/CalculiX integration remains external-tool or later-phase work.
- Per-part material assignment in multi-part assemblies is accepted by the API, but only the primary STL (`exports/model.stl`) is analyzed today.
- Dynamic interference across articulated joint trajectories is deferred to Phase 23.

**Timeline:** 4–6 months. **Risk:** arbitrary multi-physics automation is brittle; mitigated by closed templates and graceful degradation.

---

## Phase 23 — Humanoid and full-robot system synthesis ✅ COMPLETE

**Goal:** Generate complete humanoid / robot kinematics, actuator layouts, and stability estimates from high-level descriptions.

**Status:** ✅ Complete — 2026-09-01 (shipped before Phase 24).

**Deliverables:**
- ✅ Kinematic tree builder with revolute/prismatic/spherical joints.
- ✅ Actuator sizing from payload, speed, and safety-factor requirements.
- ✅ Humanoid / legged robot template library (biped, quadruped, manipulator-on-base).
- ✅ Dynamic stability checks: support polygon, ZMP estimate, reachable workspace.
- ✅ Whole-system MJCF / URDF export with sensors and actuators.
- ✅ Basic gait / motion feasibility checks via simple dynamics templates.
- ✅ Backend endpoints + frontend `HumanoidPanel`.

**Tests:** `tests/test_phase23_humanoid.py`, `tests/test_phase23_robot_api.py`; full pytest suite **357/357 passing**.

**Timeline:** 4–6 months. **Risk:** humanoid design is a research area; start with templates and parameterized scaling, not open-ended morphology.

---

## Phase 24 — World-model simulation ✅ COMPLETE

**Goal:** Drop the assembled system into a parameterized scene with objects, sensors, and domain randomization, ready for policy training across manipulation, locomotion, aerial, and humanoid tasks.

**Status:** ✅ Complete — 2026-09-01.

**Deliverables:**
- ✅ World builder API: `WorldDescription`, `WorldBuilder`, `WorldTerrain`, `WorldSensor`, `WorldTask`, `DomainRandomization`.
- ✅ Domain-specific templates: `pick_place`, `push`, `walker`, `drone_hover`, `humanoid_stand`.
- ✅ Domain randomization for mass, friction, actuator gains, sensor noise, wind, thermal loads.
- ✅ Export to MuJoCo MJCF and Isaac Sim JSON from the same world description.
- ✅ Body-name alias resolver, procedural terrain variants (stairs/ramp/uneven), Isaac JSON schema validation.
- ✅ Rich replay capture (contacts/actuators/sensors/orientations/linear velocities) in `world_loaders.py`.
- ✅ Backend `/world` endpoints and frontend `WorldBuilderPanel`.

**Tests:** `tests/test_world_builder.py`; full pytest suite **376/376 passing**.

**Timeline:** 3–4 months.

---

## Phase 25 — Robot brain training loop ✅ FOUNDATION COMPLETE

**Goal:** Generate training data from the simulated world, train a policy, evaluate it in sim, and feed performance back into design.

**Status:** ✅ Foundation complete — 2026-09-01.

**Deliverables:**
- ✅ Deterministic NumPy-only attention-aware training layer in `ai_cad/geda_bridge/brain/`:
  - `world_model.py` — per-body saliency from replay, `AttentionBudget`, tiny ridge-regression world model.
  - `policies.py` — `AttentionMLPPolicy` with hard input masking.
  - `envs.py` — `AbstractAttentionEnv` built from `WorldDescription`; `WorldReplayEnv` MuJoCo hook stub.
  - `trainer.py` — CEM trainer + evaluation + `train_and_evaluate`.
- ✅ World-builder attention/compute extensions: `ComputeBudget`, `attention_regions`, `event_camera` sensor, `actuator_noise_std` / `sensor_dropout_prob`, replay saliency, Isaac JSON coverage.
- ✅ Compute/event-sensor part families: `compute_module`, `event_camera_mount`.
- ✅ Backend endpoints: `/designs/{id}/train-brain`, `/designs/{id}/brain`, `/designs/{id}/brain-replay-attention`.
- ✅ Frontend: `BrainTrainingPanel.jsx` + extended `WorldBuilderPanel.jsx`.
- 🔄 Remaining: synthetic dataset generator (RGB/depth/segmentation), real MuJoCo closed-loop policy rollout harness, design-feedback redesign loop, full cross-domain closed-loop demos.

**Tests:** `tests/test_geda_bridge_brain.py` (16 tests); full suite **414/414 passing** (170 default + 222 heavy/slow + 22 mujoco).

**Timeline:** 4–6 months total; foundation delivered. **Risk:** RL training is its own discipline; mitigated by starting with deterministic CEM on a toy attention environment.

---

## Phase 26 — HERMES cross-domain conversational supervisor ✅ FOUNDATION COMPLETE

**Goal:** A user can talk to RoboCAD like a colleague across all domains: ask status, request design changes, approve simulations, and get explanations — without becoming a black-box controller.

**Status:** ✅ Foundation complete — 2026-09-01.

**Deliverables:**
- ✅ `ai_cad/hermes/` package:
  - `models.py` — `Session`, `Plan`, `PlanStep`, `Message`, `ToolCall`, `ToolResult`.
  - `tools.py` — `HermesToolRegistry` with ~14 tools wrapping existing backend APIs.
  - `gate.py` — `ApprovalGate` classifying read-only vs. expensive operations.
  - `planner.py` — dependency-aware plan execution with approval, rejection, and cascading skip.
  - `session.py` — JSON-persisted `HermesSession` under `designs/{id}/hermes_session.json`.
  - `agent.py` — deterministic JSON-in-text parser + stub LLM fallback for tests.
  - `explain.py` — plain-language summaries of DFM, verification, brain, and world-replay reports.
- ✅ Backend endpoints: `/hermes/session`, `/hermes/session/{id}`, `/hermes/session/{id}/message`, `/hermes/session/{id}/approve`, `/hermes/session/{id}/explain`, `/hermes/session/{id}/status`.
- ✅ Frontend: `HermesPanel.jsx` (chat thread, plan viewer, approval cards, quick explain, status badge), API helpers in `api.js`, integrated in `App.jsx`.
- ✅ `geda_bridge/capabilities.py` exposes the new HERMES endpoints.
- 🔄 Remaining: wire tool executors to real backend functions (`generate_design`, `regenerate_parameters`, `synthesize_assembly`, `build_world`, `train_brain`, etc.); native Anthropic tool-use integration; real LLM end-to-end tests with a mocked generator; strict parameter validation hooks; deeper `/generate`/`/train-brain`/`/world` integration; design-feedback loop.

**Tests:** `tests/test_hermes.py` (30 unit tests), `tests/test_hermes_backend.py` (10 FastAPI endpoint tests); full suite **454/454 passing**.

**Timeline:** 3–4 months total; foundation delivered. **Risk:** agent hallucinations in safety-critical commands; mitigated by hard approval gates and deterministic tool registry.

---

## Phase 27 — Real-world feedback loop and sim-to-real

**Goal:** Deploy trained policies and hardware designs on real robots, collect failure data, and close the loop back into simulation and design.

**Deliverables:**
- Real robot deployment harness (ROS 2 / micro-ROS / hardware bridge).
- Data logger for real-world failures and telemetry.
- Automatic sim parameter calibration from real trajectories.
- Retraining pipeline: real data → fine-tune policy → re-deploy.
- Safety monitoring: detect out-of-distribution states and halt.

**Tests:** one real robot skill works after sim-to-real iteration.

**Timeline:** 6–12 months.

---

## Phase 28 — Distribution, ecosystem, and advanced co-design

**Goal:** Product packaging, marketplace, and optional advanced co-design with external EDA / CFD tools.

**Deliverables:**
- One-command launcher (`start.bat` / `start.sh`).
- Optional desktop installer (PyInstaller/NSIS or Tauri).
- Open-source core with paid cloud simulation/training tier.
- Asset marketplace: verified parts, scene templates, trained policies, aero/thermal templates, robot templates.
- Enterprise features: private model training, PLM integrations, audit logs.
- Community benchmarks and competitions.
- Advanced co-design plugins for package/heat-spreader integration with external EDA (not silicon layout).

**Tests:** launcher smoke test; manual clean-Windows VM test; marketplace upload/download round trip.

**Acceptance criteria:** new user from installer to first generated base plate or airfoil in under 10 minutes.

**Timeline:** 2–3 months core packaging; ongoing for marketplace/enterprise.

---

## Dependencies and critical path

| Phase | Hard dependencies | Unlocks |
|---|---|---|
| 13 | Phases 0–12 | Confidence to build bridge |
| 14A | Phase 13 | 14B, 15A |
| 14B | 14A | 15A |
| 15A | 14A, 14B | 15B, revenue/validation |
| 15B | 15A | ✅ Complete — 187/187 tests; PATH1 monetization |
| 16 | Phase 13 | 17, 22 |
| 17 | Phase 13, 16 | 18 |
| 18 | Phase 17 | 19, 20, 21 |
| 19 | 14A, 17, 18 | 23, 24 |
| 20 | 17, 18 | 22 |
| 21 | 17, 18 | 22 ✅ Complete — 299/299 tests; electronics co-design |
| 22 | 19, 20, 21 | 23, 24 ✅ Complete — 330/330 tests; multi-physics verification gate |
| 23 | 19, 22 | ✅ Complete — 357/357 tests; 24, 25 |
| 24 | 15A, 19, 23 | ✅ Complete — 376/376 tests; 25 |
| 25 | 24 | ✅ Foundation complete — 414 tests; 26, 27 |
| 26 | 16, 19, 22, 24, 25 | ✅ Foundation complete — 454 tests; full UX layer; 27 |
| 27 | 25, hardware access | Commercial deployment (next) |
| 28 | PATH1 proven, 27 | SaaS + marketplace |

---

## Why this plan is realistic

- **Ship-first milestones:** every phase produces something runnable.
- **PATH1 funds PATH2:** bridge is marketable in 6–9 months.
- **Domain tracks on a shared core:** aero/thermal/electronics/humanoid features extend the same feature-tree and bundle infrastructure, not parallel unrelated products.
- **Explicit boundaries:** silicon EDA and autonomous CFD stay external; RoboCAD owns form-factor co-design and export bridges.
- **Risks front-loaded:** high-risk layers get conservative timelines and mitigations.
- **Human in the loop:** HERMES proposes/explains; humans approve safety-critical actions.

---

## Immediate next action

Start **Phase 26 — HERMES cross-domain conversational supervisor**: an LLM-driven orchestrator with tool use across design, simulation, and training APIs; status dashboard; explanation engine; and hard approval gates for expensive operations. Keep Phases 14A–25 under maintenance and the 414-test suite green as HERMES lands. Remaining Phase 25 closed-loop work (real MuJoCo policy rollout, synthetic dataset generator, design-feedback loop) can continue in parallel under HERMES supervision.

---

*See also: [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md) for the market and technical rationale.*
