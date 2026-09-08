# Phase 28 — Simulation-First Product Platform

**Date:** 2026-09-01  
**Status:** 28A/B/C/E/F complete; 28D in progress  
**Related:** `README.md`, `PLAN.md`, `.claude/plans/phase28e-real-solver-certification-plan.md`

---

## Progress log

- **2026-09-01** — 28B/28C integration checkpoint:
  - `ai_cad/marketplace.py` wired to backend endpoints; `tests/test_marketplace.py` passes.
  - Deep solver stack (`geometry_prep`, `meshing`, `calculix_adapter`, `elmerfem_adapter`, `openfoam_adapter`, `nvidia_surrogate`, `job_store`, `verification_deep`) imports and runs; all `tests/test_solver_*.py` and `tests/test_deep_verify_api.py` pass.
  - Full default pytest suite: **340 passed**; frontend `npm run build` passes with chunk-size warning only.

- **2026-09-01** — 28E real-solver certification + 28F product hardening complete:
  - Real-solver dispatch with `solver_mode` (`auto`/`real`/`surrogate`) in `verification_deep.py`.
  - Coarse analysis mesh from STL bounding box so real solvers can run without Gmsh/Netgen.
  - Scalar field extraction (`field_export.py`) and Three.js vertex-color heatmap overlay.
  - Simulation certification engine (`sim_certification.py`) with readiness score, A/B real-vs-surrogate comparison, certificate persistence.
  - Professional Markdown report export (`report_export.py`).
  - Marketplace direct archive upload (`/marketplace/upload`) wired end-to-end.
  - Solver install bootstrap (`scripts/setup_solvers.py`), `docs/SOLVER_INSTALL.md`, and health CLI install hints.
  - Onboarding smoke tests: `tests/test_onboarding.py`, `tests/test_health.py`, `tests/test_setup_solvers.py`.
  - Full default pytest suite: **366 passed**; heavy/slow/mujoco suite: **222 passed, 1 xfailed**.
  - Remaining: morphology lab (28D).

---

## 1. Why Phase 28 is being re-scoped

The original Phase 28 was only packaging, marketplace, and enterprise glue. After Phase 27A/B/C shipped, the remaining product-level limitations are:

1. Multi-physics verification uses conservative hand-calculations, not real FEA/CFD.
2. Humanoid/robot design is based on parameterized templates, not open-ended morphology search.
3. Sim-to-real requires hardware we do not have.

This plan **keeps 27D hardware-in-the-loop deferred** and instead turns Phase 28 into a **simulation-first product platform** that closes the first two gaps in software and prepares the third.

**Acceptance thesis:**
> RoboCAD generates parametric robotics designs, runs real FEA/CFD for common load cases, invents and validates novel humanoid/robot morphologies in simulation, and certifies policies against a distribution of simulated worlds. The only thing it cannot do is execute on a physical robot.

---

## 2. Phase 28 sub-phases

| Sub-phase | Goal | Depends on | Time |
|---|---|---|---|
| **28A** | Launcher + installer + dependency health checks | Phases 0–27 | 2–4 weeks |
| **28B** | Asset marketplace: verified parts, templates, policies, robot templates | 28A | 3–6 weeks |
| **28C** | Deep multi-physics engine (real FEA/CFD/thermal solvers + NVIDIA surrogate) | Phases 20, 22 | 3–5 months |
| **28D** | Morphology Co-Design Lab (brain-body co-design for humanoids/robots) | Phases 23, 25 | 3–5 months |
| **28E** | Simulation certification: sim-to-sim robustness, real-to-sim system-ID prep, readiness score | Phases 24, 25 | ✅ **Complete — 2026-09-01** |
| **28F** | Product hardening: docs, tests, onboarding funnel, quality gate | All above | ✅ **Complete — 2026-09-01** |

**Parallelizable:** 28A/B/E/F are complete; 28D can proceed independently.

---

## 3. 28A — Launcher and installer

### Deliverables

- `start.py` / `start.bat` / `start.sh` one-command launcher:
  - Checks Python version, virtualenv, Node, npm.
  - Verifies `.env` has required keys (ANTHROPIC, optional NVIDIA/LiveKit/Onshape).
  - Installs `requirements.txt` and `web/frontend` deps if missing.
  - Starts backend (`uvicorn`) and frontend (`npm run dev`) in separate processes.
  - Opens browser to `http://localhost:5173`.
- Desktop installer skeleton:
  - PyInstaller bundle of the launcher + Python runtime (Windows).
  - `build_installer.py` script to produce `dist/RoboCAD/`.
  - NSIS optional installer wrapper.
- Health endpoint and CLI:
  - `python -m robocad.health` prints solver availability (CalculiX, OpenFOAM, Gmsh, MuJoCo) and API key status.

### Tests

- Launcher smoke test on clean virtualenv.
- Health command reports all expected modules.
- Frontend `npm run build` passes after launcher setup.

---

## 4. 28B — Asset marketplace

### Deliverables

- Marketplace data model (`ai_cad/marketplace.py`):
  - `MarketplaceItem`, `AssetType` (part, scene_template, robot_template, policy_bundle, material_preset).
  - Local JSON index at `marketplace/index.json`.
- Backend endpoints:
  - `GET /marketplace/items`
  - `GET /marketplace/items/{id}`
  - `POST /marketplace/items` (upload verified asset)
  - `POST /marketplace/items/{id}/download`
  - `POST /marketplace/items/{id}/import/{design_id}`
- Verified badge: item passes DFM + mesh-quality + runtime validation before being marked `verified`.
- Frontend `MarketplacePanel.jsx`:
  - Grid of cards with preview, domain badges, verification status, download/import buttons.
  - Upload flow for users to contribute assets.
- Starter packs:
  - Robotics starter pack (base plates, brackets, motor mounts).
  - Humanoid starter pack (biped, quadruped, manipulator-on-base templates).
  - Manipulation scene pack (gripper cube, peg insertion, wedge push).

### Tests

- Marketplace CRUD tests.
- Importing a marketplace part into a design creates a valid feature tree.
- Verified badge only set after validation passes.

---

## 5. 28C — Deep multi-physics engine

### Goal

Add real solver execution as an optional “Deep Analysis” mode while keeping the existing lightweight templates as fast pre-checks.

### Architecture

```
User prompt / load case
        │
        ▼
┌─────────────────────┐
│ Geometry cleanup    │  OpenCASCADE heal + surface labeling
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ Auto-mesher         │  Gmsh/Netgen (FEA/thermal) ; blockMesh/snappyHexMesh (CFD)
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ Solver dispatcher   │  CalculiX / ElmerFEM / OpenFOAM / NVIDIA surrogate
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ Result parser + LLM │  Extract metrics, generate redesign suggestions
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ Async job store     │  FastAPI background tasks + SQLite job log
└─────────────────────┘
```

### New modules

| Module | Purpose |
|---|---|
| `ai_cad/solvers/__init__.py` | Package marker and shared utilities. |
| `ai_cad/solvers/geometry_prep.py` | STEP/STL import, OCCT healing, surface labeling by role. |
| `ai_cad/solvers/meshing.py` | Gmsh/Netgen tetrahedral mesh generation; blockMesh/snappyHexMesh stubs for OpenFOAM. |
| `ai_cad/solvers/calculix_adapter.py` | Write `.inp` files, run `ccx`, parse `.frd`/`.dat` for stress/displacement/modal. |
| `ai_cad/solvers/elmerfem_adapter.py` | Write ElmerFEM case files for thermal and coupled thermal-stress. |
| `ai_cad/solvers/openfoam_adapter.py` | Write full OpenFOAM case directory, run via subprocess or Docker, parse `forces`/field data. |
| `ai_cad/solvers/nvidia_surrogate.py` | Train/use NVIDIA Modulus/PhysicsNeMo surrogate for drag/stress/thermal on common shapes. |
| `ai_cad/solvers/job_store.py` | SQLite job queue, status polling, result caching. |
| `ai_cad/solvers/redesign.py` | Convert solver failures into feature-tree parameter updates. |
| `ai_cad/solvers/verification_deep.py` | High-level `run_deep_verification()` matching the existing `VerificationRequest` interface. |

### Backend endpoints

- `POST /designs/{id}/deep-verify` — submit deep analysis job.
- `GET /designs/{id}/deep-verify/{job_id}` — poll status / result.
- `POST /designs/{id}/deep-verify/{job_id}/cancel` — cancel running job.
- `GET /designs/{id}/solver-availability` — list installed solvers.

### Frontend

- Extend `VerificationPanel.jsx` with a “Deep Analysis” tab.
- Show job progress, solver logs, result overlays on `STLViewer` (stress heatmap, pressure field).
- AI critique button for solver results via HERMES.

### Tests

- CalculiX static stress on a cantilever bracket matches hand calculation within 10%.
- OpenFOAM case directory is valid and `blockMesh` + `snappyHexMesh` stubs are structurally correct.
- ElmerFEM thermal case runs and returns temperature field.
- NVIDIA surrogate model trains and predicts faster than the real solver.
- Job store handles submission, status, and cancellation.

### Caveats managed

- Solvers are optional dependencies; missing solvers are detected and reported.
- Long jobs run async with progress polling.
- Geometry that fails meshing falls back to lightweight templates with a warning.
- Safety-critical parts still require human sign-off.

### Real-solver + certification additions (28E)

- `solver_mode` controls dispatch: `auto` uses real solvers when installed, else surrogate; `real` fails if missing; `surrogate` never requires binaries.
- Coarse hexahedral box mesh covers the STL bounding box for CalculiX/Elmer inputs.
- `field_export.py` parses CalculiX `.dat`, Elmer `.ep`, and OpenFOAM coefficients.
- `sim_certification.py` runs a suite of load cases and computes a weighted readiness score.
- `report_export.py` writes professional Markdown reports from job results.
- Backend endpoints: `GET /designs/{id}/deep-verify/{job_id}/field`, `GET /designs/{id}/deep-verify/{job_id}/report.md`, `POST /designs/{id}/sim-cert`, `GET /designs/{id}/sim-cert/{cert_id}`, `GET /designs/{id}/sim-certs`.
- Frontend `VerificationPanel.jsx` solver-mode selector, heatmap overlay buttons, and certification-ready wiring.

---

## 6. 28D — Morphology Co-Design Lab

### Goal

Move humanoid/robot design from “scale a template” to “search morphology + validate in simulation.”

### Architecture

```
User task + constraints
        │
        ▼
┌──────────────────────────────┐
│ Robot grammar / genome       │  topology, DOF, actuator placement, link dims
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Candidate generator          │  grammar expansion + LLM diversity
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ CAD → sim pipeline           │  build123d parts, MJCF/URDF export
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Policy training loop         │  CEM/PPO on MuJoCo/Isaac task
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Multi-objective score        │  success, energy, torque, cost, manufacturability
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Surrogate + search           │  NSGA-II / CMA-ES over morphology space
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Top-N designs + videos       │  Present to user, human picks + refines
└──────────────────────────────┘
```

### New modules

| Module | Purpose |
|---|---|
| `ai_cad/morphology/__init__.py` | Package marker. |
| `ai_cad/morphology/genome.py` | Robot genome: topology, joint types, link parameters, actuator catalog refs. |
| `ai_cad/morphology/generator.py` | Generate diverse candidates from grammar + LLM. |
| `ai_cad/morphology/cad_sim_bridge.py` | Convert genome → build123d parts → FeatureTree → MJCF/URDF. |
| `ai_cad/morphology/fitness.py` | Evaluate candidate: run MuJoCo rollout, compute success/energy/torque/cost. |
| `ai_cad/morphology/surrogate.py` | Train surrogate to predict fitness without full RL. |
| `ai_cad/morphology/search.py` | NSGA-II / CMA-ES search over genome space. |
| `ai_cad/morphology/manufacturability.py` | Cost/manufacturability score from BOM + geometry complexity. |
| `ai_cad/morphology/topology_opt.py` | SIMP-based link topology optimization for mass reduction. |

### Backend endpoints

- `POST /morphology/search` — submit morphology search job.
- `GET /morphology/search/{job_id}` — poll progress.
- `GET /morphology/search/{job_id}/candidates` — list top candidates.
- `POST /morphology/candidate/{candidate_id}/export` — export selected candidate to a design.
- `POST /morphology/candidate/{candidate_id}/train-policy` — train/retune policy for one candidate.

### Frontend

- New `MorphologyLabPanel.jsx`:
  - Task picker (locomotion, manipulation, aerial, humanoid stand).
  - Constraint form (payload, DOF budget, height, cost budget, actuator catalog).
  - Live search progress with Pareto front visualization.
  - Candidate gallery with simulation videos, metrics, and one-click refine.
- Integration into `HumanoidPanel.jsx` as an “Invent morphology” mode.

### Tests

- Genome encoding/decoding round-trip preserves kinematics.
- Candidate generation produces valid build123d code.
- MuJoCo loads generated MJCF and simulates without explosion.
- Search improves average fitness over random baseline.
- Surrogate predicts fitness rank correlation > 0.7.

### Caveats managed

- Search is constrained to a grammar so outputs are manufacturable.
- Human approval required before exporting a candidate to a design.
- Simulation-only validation is clearly labeled.

---

## 7. 28E — Simulation certification

### Goal

Build the sim-to-real bridge in software, stopping just before physical execution.

### New modules

| Module | Purpose |
|---|---|
| `ai_cad/sim_cert/__init__.py` | Package marker. |
| `ai_cad/sim_cert/sysid.py` | Fit simulator parameters (friction, damping, actuator gains, mass offsets) from video or telemetry logs. |
| `ai_cad/sim_cert/robustness.py` | Domain-randomize a trained policy across mass, friction, sensor noise, actuator delay; report readiness score. |
| `ai_cad/sim_cert/digital_twin.py` | Architecture for simulator-in-the-loop deployment corrected by RGB/IMU streams. |
| `ai_cad/sim_cert/ros2_bridge.py` | ROS 2 / micro-ROS / serial abstraction with mock and real driver slots. |
| `ai_cad/sim_cert/readiness.py` | Aggregate readiness score from SysID fit, robustness cert, and design margins. |

### Backend endpoints

- `POST /designs/{id}/sim-cert` — run certification suite.
- `POST /designs/{id}/sim-cert/sysid` — upload video/log for parameter fitting.
- `GET /designs/{id}/sim-cert/{cert_id}` — get readiness report.

### Frontend

- Extend `BrainTrainingPanel.jsx` / `WorldBuilderPanel.jsx` with certification results.
- Show readiness score, failure modes, and recommended design changes.

### Tests

- SysID recovers known parameters from synthetic logs within 10%.
- Robustness score decreases monotonically with larger perturbations.
- Mock ROS 2 bridge publishes/subscribes to dummy topics.

---

## 8. 28F — Product hardening and quality gate ✅ COMPLETE

### Deliverables

- ✅ End-to-end onboarding tests: `tests/test_onboarding.py`, `tests/test_health.py`, `tests/test_setup_solvers.py`.
- ✅ Full test suite:
  - Default suite: **366 passing**.
  - Heavy/slow suite: **222 passing, 1 xfailed**.
  - MuJoCo tier included in heavy/slow run.
  - Frontend `npm run build` passes.
- ✅ Documentation refresh:
  - `README.md` updated with Phase 28 scope.
  - `PLAN.md` Phase 28 rewritten.
  - Dossiers `.claude/plans/phase28-simulation-first-product-platform.md` and `.claude/plans/phase28e-real-solver-certification-plan.md` updated.
  - Memory files synced.
- ✅ Marketplace direct archive upload backend + frontend.
- ✅ Solver install bootstrap: `scripts/setup_solvers.py` + `docs/SOLVER_INSTALL.md`.
- ✅ `robocad/health.py` reports solver versions + install hints.

---

## 9. Dependencies to add

### Python

```text
gmsh>=4.12.0
meshio>=5.3.0
scipy>=1.12.0          # optimization / gaussian processes
DEAP>=1.4.0            # evolutionary algorithms
cma>=3.3.0             # CMA-ES
h5py>=3.10.0           # surrogate model weights
# Optional, detect at runtime:
# calculix
# elmerfem
# openfoam
# nvidia-modulus  (requires CUDA, optional)
```

### Frontend

No major new dependencies beyond React visualization libraries for Pareto front (e.g., `recharts` or `plotly.js` optionally).

---

## 10. Current state

28A/B/C/E/F are shipped and passing tests. 28D (morphology co-design lab) is the active remaining sub-phase and can proceed independently.

---

## 11. Acceptance criteria

- [x] One-command launcher starts backend and frontend on Windows, macOS, and Linux.
- [x] Marketplace supports upload/download/import of verified parts, scene templates, robot templates, and policy bundles.
- [x] Marketplace supports direct `.zip`/`.tar.gz` archive upload.
- [x] Deep analysis dispatches to real CalculiX/ElmerFEM/OpenFOAM when installed and degrades to surrogate otherwise.
- [x] Deep analysis generates scalar field overlays on the viewer.
- [x] Simulation certification reports a readiness score and persists a certificate.
- [x] `python -m robocad.health` reports solver versions and install hints.
- [x] Full test suite passes: 366 default + 222 heavy/slow.
- [x] Documentation (README, PLAN, dossiers, memory) reflects the Phase 28 scope.
- [ ] Morphology Lab generates ≥ 10 valid humanoid/quadruped candidates and ranks them by simulation performance. *(28D in progress)*

---

## 12. Honest residual caveats

Even after all of Phase 28:

- **Hardware execution remains unvalidated.** Phase 27D/29 is still required for final sim-to-real proof.
- **Safety-critical parts need human engineering review.** Automated solvers are advisory, not certifying.
- **CFD/FEA on arbitrary LLM-generated shapes remains brittle.** Bounded load-case templates are the reliable path.
- **Novel morphology is grammar-bounded, not fully open-ended.** The system explores within a user-constrained design language.

These are **managed caveats**, not product blockers.
