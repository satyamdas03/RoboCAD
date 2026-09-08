# Phase 28E + 28F Addendum — Real-Solver Integration, Certification, and Product Hardening

**Date:** 2026-09-01
**Status:** ✅ COMPLETE
**Scope:** Closed the remaining Phase 28C caveats and shipped the simulation-first certification layer. This addendum is now a shipped completion record for `phase28-simulation-first-product-platform.md`.

## 1. Goal

Make RoboCAD run **real FEA/CFD/thermal solvers end-to-end** when the user installs them, and produce a trusted **simulation certification** artifact. Also fix the two UX caveats left from 28B/28C.

## 2. What gets solved

| Caveat | Solution | Phase |
|---|---|---|
| Real CalculiX/ElmerFEM/OpenFOAM are optional and only write input decks | Detect installed solvers, dispatch real jobs, parse real results, fall back gracefully | 28E |
| Deep solver result overlays (stress heatmap, pressure field) not implemented | Export per-node/per-element scalar fields; render them as vertex colors on the STL viewer | 28E |
| Marketplace upload is source-path based | Add multipart file upload endpoint and UI | 28F |
| No guided install path for external solvers | Add `scripts/setup_solvers.py`, WSL/Docker bootstrap, and documentation | 28F |

## 3. Sub-phase work breakdown

### 3.1 Phase 28E — Real-solver certification engine

#### 3.1.1 Auto-detection + real dispatch

- Extend `ai_cad/solvers/verification_deep.py` so `CalculiXAdapter`, `ElmerAdapter`, and `OpenFOAMAdapter` call the real adapter functions in `ai_cad/solvers/calculix_adapter.py`, `elmerfem_adapter.py`, `openfoam_adapter.py` instead of the lightweight stubs.
- Add `solver_availability()` versions and path reporting.
- Add a `solver_mode` parameter: `auto` (real if available, else surrogate), `real` (fail if not installed), `surrogate`.

#### 3.1.2 Mesh generation for real solvers

- Wire `ai_cad/solvers/meshing.py` `tetrahedral_mesh()` into the dispatcher.
- Generate a `Mesh` model with node sets from `geometry_prep.py` `label_surfaces_trimesh()` so boundary conditions land on the correct nodes/faces.
- Add a coarse fallback (already exists) for when Gmsh/Netgen are missing.

#### 3.1.3 Result field export + viewer overlay

- Parse CalculiX `.frd` (or `.dat`) nodal stress/displacement.
- Parse ElmerFEM `.ep` nodal temperature.
- Parse OpenFOAM `postProcessing/` surface field data or VTK.
- Add `ai_cad/solvers/field_export.py` to write a JSON/VTK scalar field file under `designs/{id}/deep_results/{job_id}/`.
- Add backend endpoint `GET /designs/{id}/deep-verify/{job_id}/field`.
- Extend `STLViewer.jsx` to color vertices by a scalar field (heatmap mode) with a legend.

#### 3.1.4 Simulation certification

- New module `ai_cad/sim_certification.py`.
- Run a suite of load cases across real/surrogate solvers and domain-randomized MuJoCo rollouts.
- Compute a **readiness score** (0–100) from pass rate, safety factor margin, policy success rate, and mesh quality.
- Persist a signed-ish certificate JSON: `designs/{id}/certificates/{cert_id}.json`.
- Backend endpoints:
  - `POST /designs/{id}/sim-cert`
  - `GET /designs/{id}/sim-cert/{cert_id}`
  - `GET /designs/{id}/sim-certs`
- Frontend: extend `VerificationPanel.jsx` with a **Certify** tab showing score, per-check status, and download link.

#### 3.1.5 Surrogate ↔ real-solver A/B mode

- When both surrogate and real solver are available, run both and compare metrics in the certificate.
- Flag large discrepancies and suggest recalibration.

#### 3.1.6 Professional physics report export

- New module `ai_cad/solvers/report_export.py`.
- Generate a Markdown/PDF report from a verification job:
  - Design summary, material, mesh stats.
  - Boundary-condition diagram text.
  - Solver log excerpts and convergence info.
  - Result table + safety-factor conclusion.
  - Redesign suggestions.
- Backend endpoint `GET /designs/{id}/deep-verify/{job_id}/report.md`.

### 3.2 Phase 28F — Product hardening + final docs

#### 3.2.1 Marketplace direct file upload

- Extend `ai_cad/marketplace.py` `create_item()` path to accept an optional extracted archive directory.
- Add backend endpoint `POST /marketplace/upload` that accepts multipart file upload, extracts `.zip`/`.tar.gz` into `marketplace/uploads/{uuid}/`, validates structure, and creates a `MarketplaceItem` pointing at it.
- Update `MarketplacePanel.jsx` upload form to use a file input and the new endpoint.

#### 3.2.2 Solver install bootstrap

- Add `scripts/setup_solvers.py`:
  - Detect OS.
  - Print/install instructions for CalculiX (Windows binary download), ElmerFEM (Windows installer), OpenFOAM (WSL2/Ubuntu or Docker).
  - Optional `--wsl` flag to run `wsl --install -d Ubuntu` and `sudo apt install ...`.
- Add `docs/SOLVER_INSTALL.md` with per-platform steps and verification commands.
- Update `robocad/health.py` to report solver version strings and install hints when missing.

#### 3.2.3 Docs + onboarding test

- Refresh `README.md` with real-solver install section.
- Add an onboarding test script: `python -m pytest tests/test_onboarding.py` that verifies:
  - backend starts,
  - health CLI passes,
  - a generated bracket can be deep-verified with surrogate,
  - marketplace round-trip works.

## 4. Files to create / modify

### New files
- `ai_cad/solvers/field_export.py`
- `ai_cad/sim_certification.py`
- `ai_cad/solvers/report_export.py`
- `scripts/setup_solvers.py`
- `docs/SOLVER_INSTALL.md`
- `tests/test_real_solver_dispatch.py`
- `tests/test_sim_certification.py`
- `tests/test_onboarding.py`

### Modified files
- `ai_cad/solvers/verification_deep.py` — real-dispatch wiring.
- `ai_cad/solvers/calculix_adapter.py` — minor: expose mesh-from-STL helper.
- `ai_cad/solvers/elmerfem_adapter.py` — minor: expose mesh-from-STL helper.
- `ai_cad/solvers/openfoam_adapter.py` — minor: expose surface-label-to-patch mapping.
- `ai_cad/solvers/geometry_prep.py` — node-set extraction for volume meshers.
- `web/backend/main.py` — new endpoints.
- `web/frontend/src/api.js` — new helpers.
- `web/frontend/src/components/VerificationPanel.jsx` — overlays + certify tab.
- `web/frontend/src/components/STLViewer.jsx` — scalar-field heatmap mode.
- `ai_cad/marketplace.py` — upload archive handling.
- `web/backend/main.py` — `/marketplace/upload` endpoint.
- `web/frontend/src/components/MarketplacePanel.jsx` — file upload form.
- `robocad/health.py` — solver version + install hints.
- `README.md`, `PLAN.md`, dossiers, memory files.

## 5. Test plan

- Unit tests for field export, report export, and certification scoring.
- Integration tests that mock real solver binaries (monkeypatch `shutil.which`) and assert the dispatch path runs subprocess commands.
- Frontend build passes.
- Full pytest suite remains green (target: 340 default + 222 heavy/slow passing).
- Manual end-to-end: install CalculiX on Windows, run `python -m robocad.health`, submit a real static-stress deep-verify job, verify the result differs from the surrogate estimate.

## 6. Acceptance criteria

- [x] With CalculiX installed, `POST /designs/{id}/deep-verify` for `static_stress` produces a real CalculiX-based result.
- [x] With ElmerFEM installed, thermal conduction returns actual max/min temperature.
- [x] With OpenFOAM available (WSL/Docker), drag/lift coefficients come from parsed solver output.
- [x] Without any solver installed, the system still degrades to surrogate/estimate and never crashes.
- [x] `VerificationPanel.jsx` can toggle a heatmap overlay on the model for any scalar result field.
- [x] `POST /designs/{id}/sim-cert` returns a readiness score and a downloadable certificate JSON.
- [x] Marketplace supports direct `.zip` upload from the browser.
- [x] `python -m robocad.health` reports solver versions and install hints.
- [x] All tests pass and all code is committed/pushed.

## 7. Shipped files

- New: `ai_cad/sim_certification.py`, `ai_cad/solvers/field_export.py`, `ai_cad/solvers/report_export.py`, `scripts/setup_solvers.py`, `docs/SOLVER_INSTALL.md`, `tests/test_real_solver_dispatch.py`, `tests/test_sim_certification.py`, `tests/test_report_export.py`, `tests/test_onboarding.py`, `tests/test_health.py`, `tests/test_setup_solvers.py`.
- Modified: `ai_cad/solvers/verification_deep.py`, `ai_cad/marketplace.py`, `robocad/health.py`, `web/backend/main.py`, `web/frontend/src/api.js`, `web/frontend/src/App.jsx`, `web/frontend/src/components/VerificationPanel.jsx`, `web/frontend/src/components/STLViewer.jsx`, `web/frontend/src/components/MarketplacePanel.jsx`.
- Test results: 366 default + 222 heavy/slow tests passing; frontend build passes.

## 8. Honest residual caveats after this work

- RoboCAD still does not bundle the solvers; the user must install them.
- Very large meshes (millions of cells) will still need a workstation or cloud tier; the laptop is fine for demo-scale parts.
- OpenFOAM on Windows remains best via WSL2/Docker, not a native install.

## 9. Sequencing note

28E/F shipped in a single session. The next major body of work is 28D morphology lab.
