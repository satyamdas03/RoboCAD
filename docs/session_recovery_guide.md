# RoboCAD Session Recovery Guide

**If the conversation restarts and all context is lost, read this file first, then read every file listed below in order.**

This guide exists because RoboCAD has grown across many phases and redesigns. The conversation state is not enough; the canonical state lives in files. Read them line by line to recover the full picture before writing code.

**Last updated:** 2026-10-03 (Milestone G complete, honest score **9.6/10**).

---

## Step 1 — Read the project memory index

File: `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\MEMORY.md`

This lists all memory files. Read every linked memory file next.

---

## Step 2 — Read every memory file in order

These files are in `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\`:

1. `phase3-phase4-completion.md` — Phases 0–4 done; parameter editing, face-click guessing, design library, remix/tags.
2. `phase5-phase6-completion.md` — Onshape export/sync, manufacturing reports, 12 robotics component templates.
3. `impeccable-ui-redesign.md` — First full UI redesign (Precision Lab Instrument light theme).
4. `google-stitch-ui-redesign.md` — Second/current UI redesign (Kinetic Precision dark workstation); demo video + README walkthrough.
5. `engineer-grade-roadmap.md` — Strategic decision and Phases 8–14 roadmap for complex, high-precision, multi-part CAD.
6. `phase8-baseline-in-progress.md` — 30-prompt complexity baseline 26/30 (86.7%) with `qwen3-coder:latest`.
7. `phase9-feature-tree-backend.md` — Feature-tree sidecar, transpiler, store, endpoints, frontend panel.
8. `phase10-sketch-constraint-solver.md` — Internal 2D constraint solver.
9. `phase11-assembly-system.md` — Multi-part instances + LCS mates.
10. `phase12-verification-physics.md` — DFM, tolerance/fit, simple FEA.
11. `phase13-model-specialization.md` — Fine-tuning scaffolding + Claude 5 integration; Phase 13 green on T1–T4 gate.
12. `claude5-integration-fixes.md` — Anthropic SDK fixes and latest Claude Sonnet 5 benchmark numbers (21/30, T1–T4 87.5%).
13. `robocad-path-analysis.md` — PATH1 (GEDA Bridge) vs PATH2 (voice-to-world-model) strategic analysis; Phase 13 gate cleared.
14. `phase14a-geda-bridge.md` — Simulation-ready MJCF/URDF bundle exporter + MuJoCo runtime validation; 152/152 tests.
15. `phase14b-scene-templates.md` — Drop-in MuJoCo manipulation scene templates; 160/160 tests.
16. `phase15a-learning-robotics-handshake.md` — Cross-repo bundle ingestion contract, reference loaders, /capabilities endpoint; 170/170 tests.
17. `phase15b-robocomplier-pipeline.md` — Skill-to-scene recommendation, variant sweep, batch bundle export, NumPy-only CEM push-policy smoke test; 187/187 tests.
18. `robocad-end-to-end-roadmap.md` — Phased 13–28 plan to the full vision.
19. `multi-domain-scope-expansion.md` — Decision to expand RoboCAD's scope to aero/thermal/electronics/humanoid/multi-physics; phases re-aligned to 16–28.
20. `phase16-17-multi-domain-foundation.md` — Domain classifier, per-domain intent parser, feature-tree schema v2.0.0, airfoil sketch support, frontend domain badges; 201/201 tests.
21. `phase18-decomposition-part-families.md` — Automatic system decomposition, part families, composed FeatureTree, /decompose endpoint, DecomposePanel; 228/228 tests.
22. `phase19-assembly-synthesis.md` — Mate inference, kinematic solver, collision checks, joint-aware MJCF/URDF export, backend endpoints, browser replay; 251/251 tests.
23. `phase20-aero-thermal-propulsion.md` — NACA airfoils, wings, propeller blades, heat sinks, CFD mesh stubs, aero/thermal analysis endpoints and frontend panels; 276/276 tests.
24. `phase21-electronics-mechatronics.md` — PCB outlines, electronics part families, stack decomposition + composer layout, electronics analysis, IDF/STEP export, backend endpoints, domain-gated `ElectronicsPanel`; 299/299 tests.
25. `phase22-multi-physics-verification.md` — Closed load-case templates, solver abstraction, mesh-quality gate, material library, backend `/verify` endpoints, frontend `VerificationPanel`; 330/330 tests.
26. `phase23-hotfix-memory-cpu-hardening.md` — Eliminated RAM/CPU hotspots before continuing humanoid/robot synthesis; 125 default + 212 heavy/slow tests passing.
27. `phase23-humanoid-robot-synthesis.md` — Biped/quadruped/manipulator-on-base templates, actuator sizing, stability/workspace/gait checks, whole-system MJCF/URDF export, backend endpoints + frontend `HumanoidPanel`; 357/357 tests. Post-ship hardening fixed rule-based `robot arm with gripper` and `biped humanoid robot` layouts.
28. `phase24-world-simulation.md` — World builder API, domain templates, deterministic domain randomization, MuJoCo + Isaac Sim export, body-name alias resolver, procedural terrain, rich replay capture, backend `/world` endpoints, frontend `WorldBuilderPanel`; 376/376 tests.
29. `phase25-attention-brain.md` — Attention-based robot brain training layer, `BrainTrainingPanel`, `/train-brain` endpoints, compute/event-sensor part families, saliency replay; 414 tests.
30. `phase26-hermes-plan.md` — HERMES cross-domain conversational supervisor end-to-end: real tool executors, parameter validation, design-context builder, Anthropic/Ollama LLM caller, design-feedback loop, `HermesPanel`; 456 tests.
31. `phase27-voice-nvidia-rendering.md` — Phase 27A/B/C complete: LiveKit/NVIDIA real-time voice for HERMES, NVIDIA NIM intelligence layer (chat/vision/Cosmos), AI render critique, professional Three.js viewer hardening; 263 default + 222 heavy/slow tests. Phase 27D (sim-to-real) blocked on hardware.
32. `phase28a-launcher-health-installer.md` — `python start.py`/`start.bat`/`start.sh`, `python -m robocad.health`, PyInstaller skeleton; 13/13 tests.
33. `phase28b-asset-marketplace.md` — Verified asset marketplace backend + frontend; 5/5 tests.
34. `phase28c-deep-solver-integration.md` — CalculiX/ElmerFEM/OpenFOAM adapters, NVIDIA surrogate, SQLite job store, deep-verify endpoints + frontend "Deep Analysis" tab; 64/64 solver + marketplace tests, 340 default tests.
35. `phase28e-28f-certification-hardening.md` — Real-solver dispatch, certification scoring + reports, viewer heatmaps, marketplace archive upload, solver install bootstrap, onboarding tests; 366 default + 222 heavy/slow tests.
36. `phase28-simulation-first-product-platform.md` — Phase 28 re-scoped into 28A–F; 28A/B/C/D/E/F complete; 380 default + 223 heavy/slow tests.
37. `phase28d-morphology-co-design-lab.md` — Parametric morphology search with stability/workspace/gait/actuator scoring, world-model + brain smoke-test integration, backend endpoints, frontend panel; 380 default tests.
38. `robocad-confidence-10-10-roadmap.md` — Deep gap analysis and phased roadmap; current honest score **9.6/10** after Milestone G delivered automatic simulation certification; Phase 29–38 plan.
39. `phase29-physics-morphology-scoring.md` — MuJoCo standing/sway/step rollouts; humanoid passes end-to-end; 380 default + 229 heavy/slow tests; score 6.8 → 7.6/10.
40. `phase29-close-phase30-start.md` — Phase 29 closed with step test; Phase 30 real gait synthesis started.
41. `milestone-a-adaptive-gait.md` — Milestone A complete: morphology-aware gait scaling, per-candidate gait sweep, mass-aware actuator gains, quadruped trot gait; grid/mass regression tests pass; score 7.7 → 8.0/10.
42. `milestone-b-structural-dynamics.md` — Milestone B complete: link cross-section extraction, cantilever/simply-supported beam bending + Euler buckling, `structural_score` in morphology composite; score 8.0 → 8.3/10.
43. `milestone-c-workspace-collision-manipulability.md` — Milestone C complete: sagittal-plane workspace proxy, representative-pose self-collision checks, topology-aware Yoshikawa-style manipulability index; score 8.3 → 8.5/10.
44. `milestone-d-end-effector-families.md` — Milestone D complete: `parallel_jaw_gripper`, `three_finger_hand`, `vacuum_gripper`, `point_foot`, `compliant_foot` families; score 8.5 → 8.7/10.
45. `milestone-e-topology-grammar.md` — Milestone E complete: deterministic grammar (`Topology`, `LimbSpec`, `JointSpec`), `enumerate_topologies`, `topology_to_feature_tree` composer, topology-aware `search_morphologies`; score 8.7 → 9.0/10.
46. `milestone-f-real-mujoco-brain.md` — Milestone F complete: `WorldReplayEnv` MuJoCo wrapper, `RobotMLPPolicy` with adaptive dims, NumPy-only CEM trainer, reward functions for walker/humanoid/push tasks; score 9.0 → 9.3/10.
47. `milestone-g-simulation-certification.md` — Milestone G complete: randomized-world robot certification (terrain walking, push recovery, drop test, actuator saturation, payload lift) integrated into simulation certification; auto-cert on `/morphology/search` top candidate and optional `/generate`; `CertificationPanel.jsx`; post-ship demo `scripts/demo_morphology_walk.py` with safe `step_callback` hook; score 9.3 → 9.6/10.

---

## Step 3 — Read the canonical repo dossiers

These files are at the repo root `C:\Users\point\projects\RoboCAD\`:

1. `README.md` — Mission, architecture, tech stack, current phase table (Phases 0–28 + Milestones A–G), UI demo, quickstart, PATH1/PATH2 strategic note, Milestones A–G summary, post-ship walking demo note.
2. `PLAN.md` — Full end-to-end build plan, completed milestones, risks, and detailed Phase 8–30 + Milestone definitions plus dependency table.
3. `CurrentTo10.md` — Honest confidence score analysis, gap table, score evolution, current status **9.6/10**, next steps.
4. `PRODUCT.md` — Product definition, users, brand commitments, design context, evidence on hand, simulation-export capabilities.
5. `memory.md` — Repo-level restart context with current status and commands.
6. `STITCH_BRIEF.md` — Original brief fed to Google Stitch for the Kinetic Precision UI.

Also read the `docs/superpowers/` dossiers:

7. `docs/superpowers/specs/2026-09-16-robocad-7.7-to-10-roadmap-design.md` — Milestone A–I roadmap design, current baseline 9.6/10.
8. `docs/superpowers/plans/2026-09-16-robocad-7.7-to-10-roadmap-design.md` — Plan counterpart to the above.
9. `docs/superpowers/specs/2026-10-03-milestone-g-simulation-certification.md` — Milestone G spec.
10. `docs/superpowers/plans/2026-10-03-milestone-g-simulation-certification.md` — Milestone G plan.

---

## Step 4 — Read the core source files (line by line)

### Backend / AI-CAD pipeline (`ai_cad/`)

Read every file in this directory, especially these recent additions:

- `__init__.py` — httpx2/httpcore2 shims + public exports.
- `api.py` — `RoboCADBackend.generate()` orchestrates code gen → execution → validation.
- `code_ops.py` — Parameter replacement in generated code.
- `executor.py` — Safely runs generated build123d Python in a subprocess.
- `exporter.py` — STL/STEP/3MF export helpers.
- `generator.py` — LLM code generation (Claude 5 / local Ollama).
- `guess_parameter.py` — Face-normal → parameter heuristic.
- `manufacturing.py` — Manufacturing report generation.
- `models.py` — Pydantic models.
- `onshape.py` — HMAC-signed Onshape REST API client.
- `parameters.py` — AST-based numeric parameter extraction.
- `validator.py` — STL manifold/watertight validation.
- `feature_tree.py` — Feature-Tree JSON schema v2.0.0.
- `transpiler.py` — Feature tree → build123d.
- `feature_store.py` — Feature tree persistence.
- `sketch_solver.py` — 2D constraint solver.
- `assembly.py` — Multi-part instances + LCS mates; now supports `joint_states` for articulated poses.
- `assembly_collision.py` — Collision checking with articulated transforms; mesh cache keyed by family name.
- `dfm.py` — DFM rule engine.
- `tolerances.py` — Fit/clearance checks.
- `fea.py` — Simple static analysis.
- `domain.py`, `intent_parser.py` — Cross-domain classification and intent parsing.
- `part_families.py` — Domain part-family registry including end-effector families (`parallel_jaw_gripper`, `three_finger_hand`, `vacuum_gripper`, `point_foot`, `compliant_foot`).
- `decomposition.py`, `composer.py` — Automatic system decomposition and part families.
- `mate_inference.py` — Mechanical assembly mate inference.
- `electronics.py` — Phase 21 electronics analysis + IDF/STEP export.
- `aero.py`, `thermal.py`, `cfd.py` — Phase 20 aero/thermal/CFD stubs.
- `materials.py` — Material library.
- `verification_load_cases.py`, `verification_api.py`, `mesh_quality.py` — Phase 22 verification layer.
- `robot_templates.py` — Biped/quadruped/manipulator-on-base templates.
- `actuator_sizing.py` — Motor/actuator sizing by payload × lever arm and mass scaling.
- `stability.py` — Static stability checks.
- `kinematic_tree.py` — Robot kinematic tree helpers.
- `morphology.py` — **Core morphology search engine**: `score_candidate`, `search_morphologies`, `TopologySpace`, composite weights, end-effector attachment.
- `morphology_physics.py` — **Physics scorer**: `physics_score_candidate`, MJCF export + mass scaling + freejoint, standing/sway/step/walk tests, `_sweep_gait_for_candidate`.
- `gait.py` — **Balance-aware gait controller**: `run_walk_test`, `run_step_test`, `morphology_aware_walk_params`, `morphology_aware_balance_gains`.
- `gait_adaptation.py` — `GaitMorphologyFeatures` extraction.
- `morphology_structural.py` — Link cross-section extraction + beam/buckling checks.
- `morphology_workspace.py` — Sagittal-plane workspace proxy + Jacobian manipulability.
- `morphology_collision.py` — Representative-pose self-collision scoring.
- `topology_grammar.py` — `Topology`, `LimbSpec`, `JointSpec`, `enumerate_topologies`, physical-feasibility pruning.
- `topology_composer.py` — `topology_to_feature_tree` grammar → FeatureTree composer.
- `robot_certification.py` — **Milestone G**: `RobotCertCase`, `run_robot_certification`, randomized-world stress tests (terrain walking, push recovery, drop test, actuator saturation, payload lift).
- `sim_certification.py` — Simulation certification engine including robot design detection and `robot_randomized_world_certification` check.
- `geda_bridge/` — MuJoCo/URDF bundle export, world builder, brain training:
  - `geda_bridge/exporter.py` — Bundle export.
  - `geda_bridge/world_builder.py` — Procedural world templates + domain randomization.
  - `geda_bridge/world_loaders.py` — MuJoCo / Isaac Sim loaders.
  - `geda_bridge/brain/envs.py` — `WorldReplayEnv` MuJoCo wrapper.
  - `geda_bridge/brain/policies.py` — `RobotMLPPolicy` with adaptive dims.
  - `geda_bridge/brain/trainer.py` — NumPy-only CEM trainer.
- `hermes/` — HERMES conversational supervisor.
  - `hermes/executor.py` — Real tool executors.
  - `hermes/validation.py` — Pydantic parameter validation.
  - `hermes/context.py` — Design-context builder.
  - `hermes/llm.py` — Anthropic/Ollama LLM caller.
  - `hermes/agent.py` — HERMES agent loop.
  - `hermes/session.py` — JSON-persisted sessions.
  - `hermes/livekit_token.py`, `hermes/nvidia_voice.py`, `hermes/voice_plugins.py`, `hermes/voice_agent.py` — LiveKit/NVIDIA voice.
- `nvidia_client.py` — NVIDIA NIM client.
- `render_critique.py` — AI render critique.
- `marketplace.py` — Asset marketplace backend.
- `solvers/` — Deep multi-physics solver adapters (CalculiX, ElmerFEM, OpenFOAM, NVIDIA surrogate, job store).
- `prompts/system_prompt.txt` — System prompt the LLM sees.
- `prompts/examples.json` — Few-shot examples.

### Web backend (`web/backend/`)

- `main.py` — All FastAPI endpoints including `/generate`, `/designs/*`, `/morphology/*`, `/world/*`, `/hermes/*`, `/deep-verify/*`, `/marketplace/*`, `/nvidia/*`, `/train-brain`, `/verify`, `/simulate`.

### Frontend (`web/frontend/src/`)

- `App.jsx` — Root layout and state management.
- `api.js` — All frontend API calls.
- `styles/index.css` — `kp-*` Kinetic Precision token system.
- `index.html` — Font loading and direction contract.

### Frontend components (`web/frontend/src/components/`)

Read every component file, especially:

- `STLViewer.jsx` — 3D viewer with professional lighting, heatmaps, screenshot capture.
- `ParameterList.jsx`
- `PromptInput.jsx`
- `HistorySidebar.jsx`
- `RemixPanel.jsx`
- `ComponentLibrary.jsx`
- `ManufacturingReport.jsx`
- `OnshapeUpload.jsx`
- `DownloadLinks.jsx`
- `StatusPanel.jsx`
- `TagEditor.jsx`
- `VerificationPanel.jsx` — Deep analysis + certification UI.
- `MorphologyPanel.jsx` — Morphology search + topology mode + end-effector selector + certification display.
- `HumanoidPanel.jsx`
- `WorldBuilderPanel.jsx`
- `BrainTrainingPanel.jsx`
- `CertificationPanel.jsx` — **Milestone G certification badge + per-case list**.
- `HermesPanel.jsx`
- `VoiceControls.jsx`
- `MarketplacePanel.jsx`
- `standard_components.json` — Component library seed data.

---

## Step 5 — Read the test files

All files in `C:\Users\point\projects\RoboCAD\tests\`, especially these recent/important ones:

- `test_api.py`
- `test_code_ops.py`
- `test_design_library.py`
- `test_executor.py`
- `test_generator.py`
- `test_guess_parameter.py`
- `test_manufacturing.py`
- `test_onshape.py`
- `test_parameters.py`
- `test_validator.py`
- `test_web_backend.py`
- `test_pcb_transpiler.py`
- `test_part_families_electronics.py`
- `test_electronics_analysis.py`
- `test_idf_export.py`
- `test_materials.py`, `test_verification_load_cases.py`, `test_mesh_quality.py`, `test_verification_api.py`
- `test_phase23_humanoid.py`, `test_phase23_robot_api.py`
- `test_world_builder.py`
- `test_geda_bridge_brain.py`
- `test_morphology_brain.py` (slow/heavy/mujoco end-to-end brain training)
- `test_hermes*.py`
- `test_morphology_physics.py` (slow)
- `test_gait_adaptation.py`
- `test_morphology_grid.py` (slow/heavy grid + mass-perturbation regression)
- `test_morphology_structural.py`
- `test_morphology_workspace.py`
- `test_morphology_collision.py`
- `test_end_effector_families.py`
- `test_part_families.py`
- `test_topology_grammar.py`
- `test_topology_composer.py`
- `test_topology_morphology.py` (slow/heavy/mujoco)
- `test_morphology_api.py`
- `test_robot_certification.py` (slow — Milestone G)
- `test_sim_certification_robot.py` (slow — Milestone G)
- `test_onboarding.py`, `test_health.py`, `test_setup_solvers.py`, `test_marketplace.py`

---

## Step 6 — Read configuration and helper files

- `.env.example` — Required environment variables (no secrets).
- `.gitignore`
- `requirements.txt`
- `start.py`, `start.bat`, `start.sh` — One-command launcher.
- `web-start.ps1` — Windows backend launcher.
- `package.json` (root)
- `web/frontend/package.json`
- `web/frontend/vite.config.js`
- `scripts/demo_morphology_walk.py` — **Post-ship Milestone G walking demo**.
- `scripts/setup_solvers.py` — Solver install bootstrap.
- `scripts/build_installer.py` — PyInstaller desktop bundle.
- `docs/SOLVER_INSTALL.md`
- `robocad/health.py` — Health CLI.
- `robocad/launcher.py` — Launcher core.

---

## Step 7 — Inspect the working tree and recent git history

Run these commands before doing anything else:

```powershell
cd C:\Users\point\projects\RoboCAD
git status
git log --oneline -20
git diff HEAD~1 --stat
```

---

## Step 8 — Start the servers and verify (only when asked)

Once the files above are understood, run the smoke tests:

```powershell
# One-command start (recommended)
python start.py

# Or manually:
# Backend
python -m web.backend.main

# Frontend (second terminal)
cd web/frontend
npm run dev
```

Then:

```powershell
# Default (fast) suite — excludes heavy, slow, mujoco, benchmark, network tests
python -m pytest

# Heavy / slow / mujoco tiers
python -m pytest tests -m "heavy or slow or mujoco" --tb=short --timeout=600

# Build frontend
cd web/frontend
npm run build
```

---

## What each phase/milestone proved

| Phase/Milestone | What works now | Key files |
|---|---|---|
| 0–1 | AI → build123d → STL pipeline; self-correction; benchmark | `ai_cad/generator.py`, `ai_cad/executor.py`, `validate.py` |
| 2 | FastAPI web backend + React frontend + 3D viewer | `web/backend/main.py`, `web/frontend/src/App.jsx`, `STLViewer.jsx` |
| 3 | Editable parameters, versioned regeneration, face-click parameter guessing | `ai_cad/code_ops.py`, `ai_cad/guess_parameter.py`, `ParameterList.jsx`, `STLViewer.jsx` |
| 4 | Design library, search/filter, tags, remix | `ComponentLibrary.jsx`, `TagEditor.jsx`, `RemixPanel.jsx`, `tests/test_design_library.py` |
| 5 | Onshape export/sync, manufacturing reports | `ai_cad/onshape.py`, `ai_cad/manufacturing.py`, `ManufacturingReport.jsx`, `OnshapeUpload.jsx` |
| 6 | 12 robotics component templates | `standard_components.json`, `ComponentLibrary.jsx` |
| 7 | Kinetic Precision dark workstation UI | `web/frontend/src/styles/index.css`, `App.jsx`, all component files |
| 8 | Complexity benchmark + feature-tree schema | `benchmarks/evaluate_complexity.py`, `docs/feature_tree_schema.md` |
| 9 | Feature-tree backend + transpiler + store | `ai_cad/feature_tree.py`, `ai_cad/transpiler.py`, `ai_cad/feature_store.py` |
| 10 | 2D sketch constraint solver | `ai_cad/sketch_solver.py` |
| 11 | Multi-part assembly system | `ai_cad/assembly.py` |
| 12 | DFM / tolerance / FEA verification | `ai_cad/dfm.py`, `ai_cad/tolerances.py`, `ai_cad/fea.py` |
| 13 | Model specialization + Claude 5 integration (T1–T4 gate achieved) | `scripts/build_training_dataset.py`, `scripts/build_ollama_modelfile.py`, `ai_cad/generator.py` |
| 14A–15B | GEDA Bridge: MuJoCo/URDF bundle export, scene templates, LearningRobotics handshake, RoboCompiler pipeline | `ai_cad/geda_bridge/`, `web/backend/main.py` |
| 16–17 | Cross-domain input + domain-aware feature-tree representation | `ai_cad/domain.py`, `ai_cad/intent_parser.py`, `ai_cad/feature_tree.py` |
| 18 | Automatic decomposition + domain part families | `ai_cad/decomposition.py`, `ai_cad/part_families.py`, `ai_cad/composer.py` |
| 19 | Mechanical assembly synthesis | `ai_cad/mate_inference.py`, `ai_cad/assembly.py`, `ai_cad/assembly_collision.py` |
| 20 | Aerodynamics, thermal, and propulsion geometry | `ai_cad/aero.py`, `ai_cad/thermal.py`, `ai_cad/cfd.py` |
| 21 | Electronics and mechatronics integration | `ai_cad/electronics.py`, `web/backend/main.py` |
| 22 | Multi-physics verification engine | `ai_cad/materials.py`, `ai_cad/verification*.py`, `ai_cad/mesh_quality.py`, `VerificationPanel.jsx` |
| 23 | Humanoid and full-robot system synthesis | `ai_cad/robot_templates.py`, `ai_cad/kinematic_tree.py`, `ai_cad/actuator_sizing.py`, `ai_cad/stability.py`, `HumanoidPanel.jsx`, `tests/test_phase23_humanoid.py` |
| 24 | World-model simulation builder | `ai_cad/geda_bridge/world_builder.py`, `ai_cad/geda_bridge/world_loaders.py`, `WorldBuilderPanel.jsx` |
| 25 | Robot brain training loop (foundation) | `ai_cad/geda_bridge/brain/`, `BrainTrainingPanel.jsx` |
| 26 | HERMES cross-domain conversational supervisor | `ai_cad/hermes/`, `HermesPanel.jsx` |
| 27A–C | Voice + NVIDIA intelligence + professional rendering | `ai_cad/hermes/voice*.py`, `ai_cad/nvidia_client.py`, `VoiceControls.jsx`, `STLViewer.jsx` |
| 28A–F | Simulation-first product platform: launcher, marketplace, deep solvers, morphology lab, certification, hardening | `robocad/`, `ai_cad/marketplace.py`, `ai_cad/solvers/`, `ai_cad/morphology.py` |
| 29 | Physics-based morphology scoring | `ai_cad/morphology_physics.py` |
| 30 / Milestone A | Real gait synthesis + adaptive gait robustness | `ai_cad/gait.py`, `ai_cad/gait_adaptation.py`, `ai_cad/morphology_physics.py` |
| Milestone B | Structural dynamics / FEA for links | `ai_cad/morphology_structural.py` |
| Milestone C | Workspace / self-collision / manipulability | `ai_cad/morphology_workspace.py`, `ai_cad/morphology_collision.py` |
| Milestone D | Real end-effector families | `ai_cad/part_families.py` |
| Milestone E | Topology grammar beyond templates | `ai_cad/topology_grammar.py`, `ai_cad/topology_composer.py` |
| Milestone F | Real MuJoCo brain training on generated robots | `ai_cad/geda_bridge/brain/envs.py`, `policies.py`, `trainer.py` |
| **Milestone G** | **Automatic randomized-world simulation certification** | **`ai_cad/robot_certification.py`, `ai_cad/sim_certification.py`, `CertificationPanel.jsx`** |

---

## If you are resuming after a crash

1. Read `MEMORY.md`.
2. Read every memory file linked from it.
3. Read `README.md`, `PLAN.md`, `CurrentTo10.md`, and this file fully.
4. Run `git status` and `git log --oneline -20`.
5. Run the pytest suite and the frontend build **when asked**; do not run heavy tests unless explicitly requested.
6. Only then continue the current phase/milestone.

---

# 📝 NOTE TO THE NEXT SESSION'S MODEL

**Read this section first if you are a new Claude session resuming RoboCAD work.**

## Where we are right now

- **Current state:** RoboCAD is at **Milestone G complete**. Honest complex-design confidence score: **9.6 / 10**.
- **Latest commit on `origin/master`:** `9297800` — "robocad: sync dossiers and memory for Milestone G demo".
- **Test status:** **407 default + 263 heavy/slow/mujoco tests passing** (1 xfailed, 2 xpassed). Frontend production build passes. **Do not run the heavy test suite unless explicitly asked.**
- **Open hardware blocker:** Phase 27D / Milestone H (sim-to-real bridge) is blocked on physical hardware access.

## What was just completed (most recent work)

1. **Milestone G shipped:** `ai_cad/robot_certification.py` with deterministic randomized-world MuJoCo stress tests (terrain walking, push recovery, drop test, actuator saturation, payload lift); integrated into `ai_cad/sim_certification.py`; auto-cert on `/morphology/search` top candidate and optional `/generate` for robots; surfaced in `CertificationPanel.jsx`.
2. **Post-ship walking demo added:** `scripts/demo_morphology_walk.py` runs a fast heuristic morphology search and scores top humanoid/quadruped candidates via the same `physics_score_candidate` path used internally. It captures MuJoCo frames through a safe `step_callback` hook.
3. **`step_callback` hook wired through the gait pipeline:** `physics_score_candidate`, `_sweep_gait_for_candidate`, `run_step_test`, and `run_walk_test` all accept an optional `step_callback`.
4. **Critical stability fix discovered and applied:** Frame-capture callbacks must **not** call `mujoco.mj_forward()` after `mujoco.mj_step()` because it overwrites the solver warm-start (`qacc_warmstart`) and destabilizes walking.
5. **Dossiers and memory synced end-to-end:** `README.md`, `CurrentTo10.md`, `PLAN.md`, `docs/superpowers/specs/2026-09-16-robocad-7.7-to-10-roadmap-design.md`, new `docs/superpowers/specs/2026-10-03-milestone-g-simulation-certification.md`, new `docs/superpowers/plans/2026-10-03-milestone-g-simulation-certification.md`, private memory files (`milestone-g-simulation-certification.md`, `robocad-confidence-10-10-roadmap.md`, `MEMORY.md`), and `.gitignore` (`demo_output/`, `*.log`).
6. **Everything committed and pushed** to `origin/master`.

## Where to work next

1. **Immediate next milestone:** **Milestone H / Phase 37 — Sim-to-real bridge**. This is blocked on physical hardware access. Do **not** start it until the user confirms they have hardware.
2. **Until hardware is available, the highest-value follow-ups are:**
   - **Product hardening:** onboarding polish, demo reliability, error messages, timeout creep monitoring on slower CI runners.
   - **Certification maintenance:** keep the randomized-world cases deterministic and green; watch `tests/test_robot_certification.py` and `tests/test_morphology_grid.py` for timeout creep.
   - **Demo reliability:** `scripts/demo_morphology_walk.py` should remain a one-command visible proof of walking robots; ensure `demo_output/` stays gitignored.
   - **Robot arm cosmetic refinement:** fillets, chamfers, joint bosses, tapered links, shaped jaws — this was queued earlier and is safe independent work.
3. **If the user asks for a specific next feature, defer to `PLAN.md` and `robocad-confidence-10-10-roadmap.md` for scope and acceptance criteria.**

## Critical things to remember

- **Secrets:** all API keys live in the repo-root `.env` file (gitignored). Never hardcode keys.
- **Git:** keep `master` clean; stage with `git add -A`; commit with `robocad: <phase> — <what changed>`; end commit messages with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
- **Tests:** run `python -m pytest` before/after non-trivial changes. Run `python -m pytest -m "heavy or slow or mujoco" --timeout=600` only when asked. Frontend changes need `cd web/frontend && npm run build`.
- **Demo output:** `demo_output/` is gitignored. Do not commit generated frames/logs.
- **MuJoCo renderer callback rule:** when capturing frames during a rollout, call `renderer.update_scene(data)` and `renderer.render()` **after** `mujoco.mj_step()`. Do **not** call `mujoco.mj_forward()` inside the callback.

## First commands to run on restart

```powershell
cd C:\Users\point\projects\RoboCAD
git status
git log --oneline -10
```

Then read `MEMORY.md`, this file, `README.md`, `PLAN.md`, and `CurrentTo10.md` in that order.
