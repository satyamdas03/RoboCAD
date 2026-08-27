# Phase 14A — GEDA Bridge: MuJoCo / URDF Exporter

## Goal

Convert any RoboCAD part or assembly into a simulation-ready asset bundle containing watertight meshes, inertial data, an MJCF file for MuJoCo, and a URDF file. This is PATH1: the first commercial milestone that lets LearningRobotics (and other simulators) consume RoboCAD designs directly.

## Scope decisions (already approved)

- **Multi-part assemblies are in scope.** We export each part instance as a separate mesh + inertial body placed at its assembled transform.
- **`mujoco` is an optional dependency.** Core bridge uses only `build123d`, `trimesh`, and `numpy`. Tests that import `mujoco` use `pytest.importorskip`. Add `mujoco>=3.0.0` to a new `requirements-dev.txt` or as an optional extra; do not block the main pytest suite if it is absent.
- **Synchronous frontend export.** `POST /designs/{id}/simulate` runs the export synchronously; large assemblies can move async later. The frontend shows a spinner and a download link.
- **Assembly duplicate-child fix is required.** `transpile_assembly` currently reuses the same `Part` object in `Compound(children=[...])`, which triggers an anytree `TreeError`. We will fix this by producing distinct moved/copied instances.

## Proposed file changes

### 1. New `ai_cad/geda_bridge/` package

- `ai_cad/geda_bridge/__init__.py` — public API: `export_bundle`, `SimulationBundle`.
- `ai_cad/geda_bridge/exporter.py` — core conversion logic:
  - `shape_to_mesh(shape, tolerance=0.1)` → `trimesh.Trimesh` via `Shape.tessellate()`.
  - `material_density(material_name)` → kg/m³ lookup with sane defaults (PLA, PETG, ABS, aluminum, steel, titanium, wood, generic 1000).
  - `compute_inertial(mesh, density)` → mass, center of mass, principal moments, principal axes.
  - `build_urdf(parts, output_dir)` → per-part link + visual + collision + inertial.
  - `build_mjcf(parts, output_dir)` → MuJoCo MJCF `<worldbody>` with `<body>` + `<geom mesh="..."/>` + `<inertial .../>`.
  - `export_bundle(shape_or_tree, output_dir, name, format="mjcf+urdf")` → returns `BundlePaths`.
- `ai_cad/geda_bridge/packager.py` — `package_bundle(bundle_dir, output_zip)` to zip manifest, meshes, MJCF, URDF, inertial JSON, and DFM report into a single downloadable asset.
- `ai_cad/geda_bridge/verifier.py` — `verify_bundle(bundle_dir)` checks:
  - every mesh is watertight,
  - every part mass > 0,
  - inertia tensor is positive-definite,
  - CoM lies inside the convex hull.
- `ai_cad/geda_bridge/models.py` — Pydantic models: `BundlePaths`, `InertialData`, `BundleManifest`, `BundleVerification`.

### 2. Assembly fixes

- `ai_cad/assembly.py`: change `transpile_assembly` to emit moved copies for each instance so the same `Part` object is never inserted twice into a `Compound`. Add regression test.

### 3. Core model updates

- `ai_cad/models.py`: add `bundle: Path | None = None` to `ExportPaths` and a `simulation_bundle: Path | None = None` convenience accessor on `GenerationResult`.

### 4. Backend endpoints

- `web/backend/main.py`:
  - `POST /designs/{design_id}/simulate` — load design, run `export_bundle`, persist bundle under `designs/{id}/simulation/`, write `manifest.json`, return bundle metadata + URLs.
  - `GET /designs/{design_id}/bundle` — stream the zip bundle via `FileResponse` (fallback 404 if not generated yet).
  - `GET /designs/{design_id}/simulation` — return persisted `manifest.json` as simulation report.
  - Update `_run_generation` to include `bundle` export URL when a simulation bundle exists.

### 5. Frontend

- `web/frontend/src/api.js`: add `simulateDesign(id)`, `getSimulationReport(id)`, `getBundleUrl(id)`.
- `web/frontend/src/components/SimulatePanel.jsx`: new panel in the Kinetic Precision style — button to generate simulation bundle, loading state, error display, report readouts (mass, inertia, watertight count, verifier status), and a download link.
- `web/frontend/src/App.jsx`: import `SimulatePanel` and render it inside `kp-panels-grid`.

### 6. Tests

- `tests/test_geda_bridge.py`:
  - cube single part → verify mass, watertight, URDF/MJCF written.
  - cylinder → verify CoM near origin.
  - L-bracket via feature tree → verify non-trivial inertia.
  - 2-part assembly → two distinct meshes, two bodies, no duplicate-child error.
  - gripper jaw → watertight mesh, positive mass.
- `tests/test_assembly.py`: add regression test for duplicate-child error.
- `tests/test_web_backend.py`: add endpoint tests for `/simulate`, `/bundle`, `/simulation` using the `clean_designs` fixture and a fake STL/STEP design.

### 7. Dependencies / tooling

- Add `mujoco>=3.0.0` to `requirements-dev.txt` (new file) and note it in `README.md`.
- Do NOT add it to `requirements.txt`; keep the main CI path lightweight.

### 8. Acceptance criteria

- `pytest tests/test_geda_bridge.py tests/test_assembly.py tests/test_web_backend.py -q` passes locally when `mujoco` is installed; skips MuJoCo-specific assertions otherwise.
- A single-part cube and a two-part assembly both produce valid MJCF and URDF files.
- The frontend Simulate panel can generate and download a bundle for a loaded design.
- README/PLAN/memory updated: Phase 14A marked in progress with new file map and acceptance criteria.

## Order of implementation

1. Fix `transpile_assembly` duplicate-child issue + regression test.
2. Create `ai_cad/geda_bridge/exporter.py` with shape→mesh, inertial, URDF, MJCF builders.
3. Create `ai_cad/geda_bridge/packager.py` + `verifier.py` + `models.py`.
4. Wire backend endpoints in `main.py`.
5. Add frontend `SimulatePanel` and `api.js` helpers.
6. Write `tests/test_geda_bridge.py` and backend endpoint tests.
7. Run full pytest suite, fix regressions.
8. Update README/PLAN/memory and commit.

## Risks / mitigations

- `build123d` tessellation tolerance choice affects mesh quality and file size. Default 0.1 mm; expose override in API later.
- Part names/IDs may contain characters unsafe for URDF/MJCF. Sanitize to `[A-Za-z0-9_]`.
- Assembly transforms are in mm; URDF/MJCF expect meters and kg. Convert all lengths by 0.001 and densities by 1e-9.
- `mujoco` may not install cleanly on all platforms. Keep it optional; core tests use trimesh only.
