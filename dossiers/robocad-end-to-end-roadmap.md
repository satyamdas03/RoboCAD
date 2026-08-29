# RoboCAD End-to-End Vision Roadmap

**Date:** 2026-08-29  
**Horizon:** ~5–7 years  
**North Star:** voice/text/sketch → multi-domain parametric CAD → per-part multi-physics testing → assembly → world-model simulation → HERMES oversight → robot brain trained on synthetic data with retraining loops.  
**First commercial milestone:** PATH1 / GEDA Bridge (Phases 14A–15B).  
**Current milestone:** Batch A multi-domain foundation (Phases 16–18) complete; Phase 19 mechanical assembly synthesis is next.  
**Domain tracks:** mechanical assemblies, aerodynamics / thermal / propulsion geometry, electronics / mechatronics form-factor co-design, humanoid / full-robot system synthesis.  
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

**Deliverables:**
- Mate inference from part interfaces and intent.
- Kinematic loop solver for closed chains.
- Assembly-level collision and clearance checks.
- Full-subsystem MJCF / URDF export with joints, actuators, and sensors.
- Assembly replay: step through range-of-motion in the browser.

**Tests:** 2–3 full mechanical assemblies (arm, gripper, diff-drive chassis) transpile and load in MuJoCo.

**Timeline:** 3–4 months.

---

## Phase 20 — Aerodynamics, thermal, and propulsion geometry

**Goal:** Generate parametric airfoils, wings, ducts, heat sinks, and propeller blades, and export CFD-ready surfaces/meshes.

**Deliverables:**
- Parametric airfoil / wing builder (NACA 4/5-digit, custom camber, sweep, twist).
- Surface / shell geometry for wings, ducts, and heat-sink fins.
- Propeller blade geometry from chord/twist/pitch parameters.
- CFD mesh export (SU2 / OpenFOAM surface mesh and config stubs).
- Thermal fin / duct templates and heat-spreader geometry.

**Tests:** generated airfoil, wing, and heat sink produce valid surface meshes; simple 2D CFD template runs without errors.

**Timeline:** 3–4 months. **Risk:** accurate CFD automation is hard; scope is geometry + template generation, not autonomous high-fidelity analysis.

---

## Phase 21 — Electronics and mechatronics integration

**Goal:** Design PCB form factors, enclosures, connectors, cable routing, and thermal management hardware that integrate with external EDA tools — *not* to replace full silicon EDA, but to close the mechanical-electrical co-design loop.

**Deliverables:**
- Component footprint / connector library (KiCad-standard and generic).
- PCB outline + mounting holes + keepout generation.
- Connector and cable-channel routing geometry.
- Heat sink / spreader / fan-mount geometry tied to thermal loads.
- Export IDF / STEP for board-level EDA tools.
- **Explicit out-of-scope:** transistor-level IC design, SPICE simulation, and lithography/PnR. These remain external EDA domains; RoboCAD handles packages, boards, and mounts.

**Tests:** generate an electronics enclosure + mounting bracket for a Raspberry Pi / motor-driver stack; export loads in KiCad or FreeCAD.

**Timeline:** 2–3 months.

---

## Phase 22 — Multi-physics verification engine

**Goal:** Run structural, thermal, CFD, and dynamic checks on generated designs from a single verification layer.

**Deliverables:**
- Solver abstraction layer: plug-in FEA, CFD, thermal, and multibody-dynamics backends.
- Closed load-case templates: static stress, drop test, thermal expansion, fatigue cycles, fastener pull-out, wind-tunnel drag, heat-sink thermal resistance, joint torque check.
- Material library extended with conductivity, specific heat, emissivity, and thermal expansion.
- Failure report with redesign suggestions (thickness, ribs, fin count, duct size).
- Mesh-quality pre-checker to avoid solver crashes on bad LLM geometry.

**Tests:** each load-case template runs on at least one standard part family per domain.

**Timeline:** 4–6 months. **Risk:** arbitrary multi-physics automation is brittle; start with closed templates and graceful degradation.

---

## Phase 23 — Humanoid and full-robot system synthesis

**Goal:** Generate complete humanoid / robot kinematics, actuator layouts, and stability estimates from high-level descriptions.

**Deliverables:**
- Kinematic tree builder with revolute/prismatic/spherical joints.
- Actuator sizing from payload, speed, and safety-factor requirements.
- Humanoid / legged robot template library (biped, quadruped, manipulator-on-base).
- Dynamic stability checks: support polygon, ZMP estimate, reachable workspace.
- Whole-system MJCF / URDF export with sensors and actuators.
- Basic gait / motion feasibility checks via simple dynamics templates.

**Tests:** generate and load a biped or quadruped assembly in MuJoCo; verify static stability in a standing pose.

**Timeline:** 4–6 months. **Risk:** humanoid design is a research area; start with templates and parameterized scaling, not open-ended morphology.

---

## Phase 24 — World-model simulation

**Goal:** Drop the assembled system into a parameterized scene with objects, sensors, and domain randomization, ready for policy training across manipulation, locomotion, aerial, and humanoid tasks.

**Deliverables:**
- World builder API: robot + objects + terrain + sensors + task.
- Domain-specific scene templates (pick-place, push, walker, drone hover, humanoid stand).
- Domain randomization for mass, friction, actuator gains, sensor noise, wind/thermal loads.
- Export to MuJoCo and Isaac Sim from the same world description.
- Replay and inspection tools in the frontend.

**Tests:** each scene template exports to both simulators and loads without errors.

**Timeline:** 3–4 months.

---

## Phase 25 — Robot brain training loop

**Goal:** Generate training data from the simulated world, train a policy, evaluate it in sim, and feed performance back into design.

**Deliverables:**
- Synthetic dataset generator: RGB, depth, segmentation, state, action.
- RL / IL training harness (Isaac Lab / rl-zoo / custom) with standard algorithms.
- Evaluation metrics: success rate, energy, cycle time, robustness.
- Design feedback loop: if the policy fails due to geometry, flag the part for redesign.
- First closed-loop demo: design → train → evaluate → redesign → retrain.

**Tests:** closed-loop demo passes on one simple task per domain class (push, hover, stand).

**Timeline:** 4–6 months. **Risk:** RL training is its own discipline; start with imitation learning and simple tasks.

---

## Phase 26 — HERMES cross-domain conversational supervisor

**Goal:** A user can talk to RoboCAD like a colleague across all domains: ask status, request design changes, approve simulations, and get explanations — without becoming a black-box controller.

**Deliverables:**
- HERMES agent with tool use across design, simulation, and training APIs.
- Status dashboard: current phase, failures, suggested next actions.
- Approval gates: HERMES proposes, human confirms for expensive operations (training, large redesigns).
- Explanation engine: why a part failed a test, why a policy succeeded/failed, why an airfoil/heat sink was shaped a certain way.
- Memory of project context across sessions.

**Tests:** HERMES correctly explains a DFM failure and proposes a redesign; explains a CFD/thermal result in plain language.

**Timeline:** 3–4 months. **Risk:** agent hallucinations in safety-critical commands; mitigate with hard approval gates.

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
| 21 | 17, 18 | 22 |
| 22 | 19, 20, 21 | 23, 24 |
| 23 | 19, 22 | 24, 25 |
| 24 | 15A, 19, 23 | 25 |
| 25 | 24 | 27 |
| 26 | 16, 19, 22, 24 | Full UX layer |
| 27 | 25, hardware access | Commercial deployment |
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

Start **Phase 19 — Mechanical assembly synthesis**: mate inference from part interfaces and intent, kinematic-loop solver for closed chains, assembly-level collision/clearance checks, full-subsystem MJCF/URDF export with joints/actuators/sensors, and browser range-of-motion replay. Keep Batch A (Phases 16–18) under maintenance and the 228-test suite green as assembly synthesis lands.

---

*See also: [`PATH1_PATH2_analysis.md`](PATH1_PATH2_analysis.md) for the market and technical rationale.*
