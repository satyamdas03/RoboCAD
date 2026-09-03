# RoboCAD Session Recovery Guide

**If the conversation restarts and all context is lost, read this file first, then read every file listed below in order.**

This guide exists because RoboCAD has grown across many phases and redesigns. The conversation state is not enough; the canonical state lives in files. Read them line by line to recover the full picture before writing code.

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
14. `robocad-end-to-end-roadmap.md` — Phased 13–28 plan to the full vision.
15. `phase19-assembly-synthesis.md` — Mate inference, kinematic solver, collision checks, joint-aware MJCF/URDF export, browser replay; 251/251 tests passing (Phase 19 complete; Phases 20–22 now complete; Phase 23 next).
16. `phase20-aero-thermal-propulsion.md` — NACA airfoils, wings, propeller blades, heat sinks, CFD mesh stubs, aero/thermal analysis endpoints and frontend panels; 276/276 tests passing (Phase 20 complete).
17. `phase21-electronics-mechatronics.md` — PCB outlines, electronics part families, stack decomposition + composer layout, electronics analysis, IDF/STEP export, backend endpoints, domain-gated `ElectronicsPanel`; 299/299 tests passing (Phase 21 complete).
18. `phase22-multi-physics-verification.md` — Closed load-case templates, solver abstraction, mesh-quality gate, material library, backend `/verify` endpoints, frontend `VerificationPanel`; 330/330 tests passing (Phase 22 complete).
19. `phase23-hotfix-memory-cpu-hardening.md` — Eliminated RAM/CPU hotspots before continuing humanoid/robot synthesis; 125 default + 212 heavy/slow tests passing; frontend build passes.
20. `phase23-humanoid-robot-synthesis.md` — Biped/quadruped/manipulator-on-base templates, actuator sizing, stability/workspace/gait checks, whole-system MJCF/URDF export, backend endpoints + frontend `HumanoidPanel`; 357/357 tests passing (Phase 23 complete; Phase 24 next). Post-ship hardening (commits `87c8f7b`, `980482b`, `174df8c`, `4de18d8`, `1b83561`, `69367a1`, `6a9faf4`) fixed the rule-based `robot arm with gripper` and `biped humanoid robot` layouts: mapped upper/forearm/gripper to `limb_segment`/`end_effector` families, aligned limb pin interfaces, corrected jaw mirroring, fixed assembly solver part-family csys lookup, corrected sketch entity placement in BuildSketch via `Locations`, added subtractive joint/pivot holes, fixed sketch-ID / parameter-name collisions in humanoid hip/shoulder hubs, and corrected misleading assembly validation reporting / frontend collision API method.
21. `phase24-world-simulation.md` — World-model simulation builder: `WorldDescription`, `WorldBuilder`, domain templates (pick-place, push, walker, drone hover, humanoid stand), domain randomization, MuJoCo MJCF + Isaac Sim JSON export + schema validation, body-name alias resolver, procedural terrain variants (stairs/ramp/uneven), rich replay capture (contacts/actuators/sensors), backend `/world` endpoints, frontend `WorldBuilderPanel`; 376/376 tests passing (Phase 24 complete; Phase 25 next).

---

## Step 3 — Read the canonical repo dossiers

These files are at the repo root `C:\Users\point\projects\RoboCAD\`:

1. `README.md` — Mission, architecture, tech stack, current phase table (Phases 0–28), UI demo, quickstart, PATH1/PATH2 strategic note.
2. `PLAN.md` — Full end-to-end build plan, completed milestones, risks, and detailed Phase 8–24 definitions plus dependency table.
3. `PRODUCT.md` — Product definition, users, brand commitments, design context, evidence on hand, simulation-export capabilities.
4. `memory.md` — Repo-level restart context with current status and commands.
5. `STITCH_BRIEF.md` — Original brief fed to Google Stitch for the Kinetic Precision UI.

---

## Step 4 — Read the core source files (line by line)

### Backend / AI-CAD pipeline (`ai_cad/`)

Read every file in this directory:

- `__init__.py` — httpx2/httpcore2 shims + public exports.
- `api.py` — `RoboCADBackend.generate()` orchestrates code gen → execution → validation.
- `code_ops.py` — Parameter replacement in generated code.
- `executor.py` — Safely runs generated build123d Python in a subprocess.
- `exporter.py` — STL/STEP/3MF export helpers.
- `generator.py` — LLM code generation (Claude 5 / local Ollama).
- `guess_parameter.py` — Face-normal → parameter heuristic.
- `manufacturing.py` — Manufacturing report generation.
- `models.py` — Pydantic models: `CADParameter`, `ExportPaths`, `ValidationReport`, `ManufacturingReport`, `GenerationResult`.
- `onshape.py` — HMAC-signed Onshape REST API client.
- `parameters.py` — AST-based numeric parameter extraction from generated code.
- `validator.py` — STL manifold/watertight validation.
- `feature_tree.py` — Feature-Tree JSON schema (Phase 9, extended to v2.0.0 in Phases 17/21).
- `transpiler.py` — Feature tree → build123d (Phase 9, extended for SurfaceFeature and PCBOutline in Phases 20/21).
- `feature_store.py` — Feature tree persistence (Phase 9).
- `sketch_solver.py` — 2D constraint solver (Phase 10).
- `assembly.py` — Multi-part instances + LCS mates (Phase 11).
- `dfm.py` — DFM rule engine (Phase 12).
- `tolerances.py` — Fit/clearance checks (Phase 12).
- `fea.py` — Simple static analysis (Phase 12).
- `geda_bridge/exporter.py` — MuJoCo/URDF bundle exporter (Phase 14A–15B complete).
- `domain.py`, `intent_parser.py` — Cross-domain classification and intent parsing (Phases 16–17, electronics parameters extended in Phase 21).
- `part_families.py`, `decomposition.py`, `composer.py` — Automatic system decomposition and part families (Phase 18, electronics families added in Phase 21).
- `mate_inference.py`, `assembly.py`, `assembly_collision.py` — Mechanical assembly synthesis: mates, kinematic solver, collision checks (Phase 19).
- `electronics.py` — Phase 21 electronics analysis + IDF/STEP export.
- `aero.py`, `thermal.py`, `cfd.py` — Phase 20 aero/thermal/CFD stubs.
- `prompts/system_prompt.txt` — System prompt the LLM sees.
- `prompts/examples.json` — Few-shot examples.

### Web backend (`web/backend/`)

- `main.py` — All FastAPI endpoints: `/generate`, `/designs`, `/designs/{id}`, `/regenerate`, `/remix`, `/guess-parameter`, `/manufacturing-report`, `/electronics-report`, `/idf-export`, `/verify`, `/mesh-quality-check`, `/onshape/*`, `/exports/*`.

### Frontend (`web/frontend/src/`)

- `App.jsx` — Root layout and state management.
- `api.js` — All frontend API calls.
- `styles/index.css` — `kp-*` Kinetic Precision token system.
- `index.html` — Font loading and direction contract.

### Frontend components (`web/frontend/src/components/`)

Read every component file:

- `ComponentLibrary.jsx`
- `DownloadLinks.jsx`
- `HistorySidebar.jsx`
- `ManufacturingReport.jsx`
- `OnshapeUpload.jsx`
- `ParameterList.jsx`
- `PromptInput.jsx`
- `RemixPanel.jsx`
- `STLViewer.jsx`
- `StatusPanel.jsx`
- `TagEditor.jsx`
- `standard_components.json` — Component library seed data.

---

## Step 5 — Read the test files

All files in `C:\Users\point\projects\RoboCAD\tests\`:

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
- `test_pcb_transpiler.py` — Phase 21 PCB outline transpilation.
- `test_part_families_electronics.py` — Phase 21 electronics part families.
- `test_electronics_analysis.py` — Phase 21 electronics analysis.
- `test_idf_export.py` — Phase 21 IDF/STEP export.
- `test_materials.py`, `test_verification_load_cases.py`, `test_mesh_quality.py`, `test_verification_api.py` — Phase 22 verification layer.

---

## Step 6 — Read configuration and helper files

- `.env.example` — Required environment variables (no secrets).
- `.gitignore`
- `requirements.txt`
- `web-start.ps1` — Windows backend launcher.
- `package.json` (root)
- `web/frontend/package.json`
- `web/frontend/vite.config.js`

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

## Step 8 — Start the servers and verify

Once the files above are understood, run the smoke tests:

```powershell
# Backend
"/c/Users/point/AppData/Local/hermes/hermes-agent/venv/Scripts/python" -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8000

# Frontend (second terminal)
cd web/frontend
npm run dev
```

Then:

```powershell
# Run tests
"/c/Users/point/AppData/Local/hermes/hermes-agent/venv/Scripts/python" -m pytest tests -q

# Build frontend
cd web/frontend
npm run build
```

---

## What each phase proved

| Phase | What works now | Key files |
|---|---|---|
| 0–1 | AI → build123d → STL pipeline; self-correction; benchmark | `ai_cad/generator.py`, `ai_cad/executor.py`, `validate.py` |
| 2 | FastAPI web backend + React frontend + 3D viewer | `web/backend/main.py`, `web/frontend/src/App.jsx`, `web/frontend/src/components/STLViewer.jsx` |
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
| 22 | Multi-physics verification engine | `ai_cad/materials.py`, `ai_cad/verification*.py`, `ai_cad/mesh_quality.py`, `web/frontend/src/components/VerificationPanel.jsx` |
| 23 | Humanoid and full-robot system synthesis | `ai_cad/robot_templates.py`, `ai_cad/kinematic_tree.py`, `ai_cad/actuator_sizing.py`, `ai_cad/stability.py`, `ai_cad/verification_load_cases.py`, `web/backend/main.py`, `web/frontend/src/components/HumanoidPanel.jsx`, `tests/test_phase23_humanoid.py`, `tests/test_phase23_robot_api.py` |
| 24 | World-model simulation builder | `ai_cad/geda_bridge/world_builder.py`, `ai_cad/geda_bridge/world_loaders.py`, `web/backend/main.py`, `web/frontend/src/components/WorldBuilderPanel.jsx`, `tests/test_world_builder.py` |
| 25–28 | End-to-end vision roadmap (Phase 25 robot brain training loop next) | `PLAN.md`, `.claude/memory/robocad-end-to-end-roadmap.md` |

---

## If you are resuming after a crash

1. Read `MEMORY.md`.
2. Read every memory file linked from it.
3. Read `README.md` and `PLAN.md` fully.
4. Run `git status` and `git log --oneline -20`.
5. Run the pytest suite and the frontend build.
6. Only then continue the current phase.

**Current active phase:** Phase 24 complete (376/376 tests passing; world-model simulation builder shipped and hardened with body-name alias resolution, procedural terrain variants, Isaac JSON schema validation, and rich replay capture). Phase 25 — robot brain training loop — is next. Robot arm cosmetic/mechanical refinement (fillets, chamfers, joint bosses, tapered links, shaped jaws) is also queued.
