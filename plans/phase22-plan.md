# Phase 22 — Multi-physics Verification Engine

**Goal:** Run structural, thermal, CFD, and dynamic checks on generated designs from a single verification layer.

**Status:** Planning  
**Target ship date:** 2026-08-29  
**Starting test count:** 299/299 passing  
**Target test count:** 325–335 passing

---

## 1. Scope & boundaries

This phase builds a *unified verification layer* and a set of deterministic, closed load-case templates. It does **not** replace commercial FEA/CFD solvers; instead it plugs into existing stubs and the GEDA Bridge and produces pass/fail/warn reports with concrete redesign suggestions.

In scope:
- Material library extended with thermal and mechanical properties.
- Solver abstraction layer with pluggable backends (structural, thermal, CFD, multibody dynamics).
- Closed load-case templates backed by NumPy / SciPy / simple mechanics formulas.
- Mesh-quality pre-checker that rejects bad LLM-generated geometry before any solver is invoked.
- Backend endpoints and a frontend `VerificationPanel` gated for every domain.
- Tests, dossiers, and memory synchronization.

Out of scope (deferred):
- Real SU2 / OpenFOAM / CalculiX / Ansys execution.
- High-fidelity fatigue or fracture mechanics.
- Real-time CFD post-processing.

---

## 2. Files to create

| File | Purpose |
|------|---------|
| `ai_cad/materials.py` | Extended material library with thermal + mechanical properties. |
| `ai_cad/verification_models.py` | Pydantic request/response models for the verification layer. |
| `ai_cad/verification_load_cases.py` | Closed load-case templates and calculators. |
| `ai_cad/mesh_quality.py` | Mesh-quality pre-checker (watertight, degenerate faces, aspect ratio). |
| `ai_cad/verification.py` | Core verification engine and solver registry. |
| `web/frontend/src/components/VerificationPanel.jsx` | React panel for running checks and viewing reports. |
| `tests/test_materials.py` | Material library unit tests. |
| `tests/test_verification_load_cases.py` | Load-case deterministic result tests. |
| `tests/test_mesh_quality.py` | Mesh-quality checks on sample STL/mesh exports. |
| `tests/test_verification_api.py` | Backend endpoint and frontend API helper tests. |

## 3. Files to modify

| File | Change |
|------|--------|
| `ai_cad/fea.py` | Wrap existing cantilever stub into the solver backend; add simple stress/displacement helpers. |
| `ai_cad/thermal.py` | Add conductivity-based fin efficiency and heat-spreader resistance checks. |
| `ai_cad/aero.py` | Add drag-force helper for wind-tunnel load case. |
| `ai_cad/cfd.py` | Add mesh-quality-aware CFD config stub generation. |
| `ai_cad/dfm.py` | Expose rule results as `VerificationResult`-compatible warnings. |
| `ai_cad/assembly_collision.py` | Export clearance/interference metrics for the verification engine. |
| `web/backend/main.py` | Add `POST /designs/{id}/verify`, `GET /designs/{id}/verify-report/{report_id}`, `POST /designs/{id}/mesh-quality-check`. |
| `web/frontend/src/api.js` | Add `runVerification`, `getVerificationReport`, `checkMeshQuality`. |
| `web/frontend/src/App.jsx` | Wire `<VerificationPanel designId={selectedId} />` for all domains (mechanical, aero, thermal, electronics, multi). |
| `PLAN.md` / `README.md` / `docs/session_recovery_guide.md` / `memory/*` | Mark Phase 22 complete, Phase 23 next, update endpoint/test lists. |

---

## 4. Work packages

### WP1 — Material library extension (`ai_cad/materials.py`)

Add a `Material` Pydantic model with at least:
- `name`, `density_kg_m3`
- `youngs_modulus_GPa`, `poisson_ratio`, `yield_strength_MPa`
- `conductivity_W_mK`, `specific_heat_J_kgK`, `emissivity`, `thermal_expansion_per_K`
- Optional notes / source

Provide at least 10 common materials:
PLA, ABS, PETG, Nylon 12, Aluminum 6061, Mild Steel, Copper, Brass, Titanium 6Al-4V, FR4, CopperTrace.

Expose lookup by name with case-insensitive fallback and a `get_material(name)` helper.

### WP2 — Verification models (`ai_cad/verification_models.py`)

```python
class LoadCase(str, Enum):
    STATIC_STRESS = "static_stress"
    DROP_TEST = "drop_test"
    THERMAL_EXPANSION = "thermal_expansion"
    FATIGUE_CYCLES = "fatigue_cycles"
    FASTENER_PULL_OUT = "fastener_pull_out"
    WIND_TUNNEL_DRAG = "wind_tunnel_drag"
    HEAT_SINK_THERMAL_RESISTANCE = "heat_sink_thermal_resistance"
    JOINT_TORQUE_CHECK = "joint_torque_check"
    MESH_QUALITY = "mesh_quality"
    ASSEMBLY_CLEARANCE = "assembly_clearance"

class VerificationRequest(BaseModel):
    design_id: str
    load_case: LoadCase
    materials: dict[str, str] = Field(default_factory=dict)  # part_id -> material name
    parameters: dict[str, float] = Field(default_factory=dict)

class VerificationResult(BaseModel):
    load_case: LoadCase
    passed: bool
    warnings: list[str]
    errors: list[str]
    metrics: dict[str, float]
    failure_modes: list[str]
    redesign_suggestions: list[str]
    raw_output: dict[str, Any] | None = None
```

### WP3 — Closed load-case templates (`ai_cad/verification_load_cases.py`)

Each load case is a pure function `part_or_assembly -> VerificationResult`:

1. **static_stress** — simple cantilever or axial stress: `sigma = M*y/I` or `F/A`; compare to yield with safety factor.
2. **drop_test** — peak acceleration from drop height: `a = sqrt(2*g*h)/dt` (simplified); compare to yield stress via impact factor.
3. **thermal_expansion** — `delta_L = alpha * delta_T * L`; warn if expansion exceeds clearance.
4. **fatigue_cycles** — S-N estimate for given cyclic stress amplitude; rough cycle-to-failure.
5. **fastener_pull_out** — M3/M4/M5 bolt shear/tensile capacity based on cross-section and material.
6. **wind_tunnel_drag** — `Fd = 0.5 * rho * v^2 * Cd * A` using frontal area from mesh bounding box.
7. **heat_sink_thermal_resistance** — conduction resistance through base + convection resistance `1/(h*A_fin)`; compare to target theta.
8. **joint_torque_check** — required torque to hold a load at a joint vs motor stall torque.
9. **mesh_quality** — delegate to `mesh_quality.py`.
10. **assembly_clearance** — delegate to `assembly_collision.py`.

All formulas use SI units internally and return human-readable metric labels.

### WP4 — Mesh quality pre-checker (`ai_cad/mesh_quality.py`)

Use `trimesh` / `numpy` to load an STL (exported from build123d) and report:
- Watertight / non-manifold edges
- Degenerate/zero-area triangles
- Aspect ratio outliers
- Triangle count and bounding box
- Extreme size ratios (e.g., bounding box dimension > 100 m or < 1 µm)

Return a `MeshQualityReport` Pydantic model with `is_suitable_for_solver` boolean and a list of issues.

### WP5 — Solver abstraction layer (`ai_cad/verification.py`)

```python
class SolverBackend(ABC):
    name: str
    supported_load_cases: list[LoadCase]
    def solve(self, request: VerificationRequest, design_data: dict) -> VerificationResult: ...

class StructuralFormulaBackend(SolverBackend): ...
class ThermalFormulaBackend(SolverBackend): ...
class CFDEstimateBackend(SolverBackend): ...
class MultibodyMuJoCoBackend(SolverBackend): ...
```

A `VerificationEngine` class:
- Registers backends.
- Accepts a request.
- Loads the design by `design_id` (reuses existing transpiler/build pipeline).
- Picks the appropriate backend(s).
- Returns a combined report.

Keep it deterministic: no LLM calls inside the calculation path. The LLM hook is reserved for generating redesign suggestions text from the structured `failure_modes` and `metrics`.

### WP6 — Backend endpoints (`web/backend/main.py`)

```python
class VerifyRequest(BaseModel):
    load_case: str
    materials: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, float] = Field(default_factory=dict)

class MeshQualityRequest(BaseModel):
    part_id: str | None = None
```

- `POST /designs/{design_id}/verify` — run one or all load cases; returns `VerificationResult`.
- `GET /designs/{design_id}/verify-report/{report_id}` — retrieve cached report.
- `POST /designs/{design_id}/mesh-quality-check` — return `MeshQualityReport`.

Store reports in memory (matching the existing design-store pattern) keyed by report ID.

### WP7 — Frontend `VerificationPanel`

- Domain-gated for every domain (reuse the badge logic).
- Load-case selector dropdown.
- Material assignment per part (auto-fill from design parts).
- "Run verification" button.
- Render pass/fail/warn cards, metrics table, failure modes, redesign suggestions.
- Mesh quality button that shows issue list.

API helpers in `api.js`:
```javascript
export async function runVerification(id, loadCase, materials = {}, parameters = {}) { ... }
export async function getVerificationReport(id, reportId) { ... }
export async function checkMeshQuality(id, partId = null) { ... }
```

### WP8 — Tests, docs, and memory sync

- Add 25–35 new tests across the files listed above.
- Target: 325–335 total passing tests.
- Update `PLAN.md`, `README.md`, `docs/session_recovery_guide.md`, and all relevant `memory/*.md` files.
- Commit with message: `robocad: Phase 22 — multi-physics verification engine, solver abstraction, load-case templates, mesh-quality gate, and VerificationPanel; 325/325 tests passing`.

---

## 5. Acceptance criteria

1. `python -m pytest` passes with no new warnings and at least 325 tests green.
2. Every `LoadCase` template returns a deterministic `VerificationResult` with SI metrics.
3. Material library exposes ≥10 materials with thermal and mechanical data.
4. Mesh-quality checker catches degenerate triangles, non-manifold edges, and watertight failures.
5. Backend endpoints return valid JSON for verify, verify-report, and mesh-quality-check.
6. `VerificationPanel` renders for all domains and exercises the API helpers.
7. `npm run build` in `web/frontend` succeeds if frontend files are modified.
8. Dossiers and private memory files are synchronized to Phase 22 complete / Phase 23 next.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Real CFD/FEA execution is too complex for one phase. | Keep solver backends as deterministic stubs/estimates; clearly label them as "pre-solver checks". |
| Mesh-quality checks need triangulated meshes; OpenCASCADE solids are not meshes. | Export STL via the existing mesh export path, then analyze with `trimesh`. |
| Backend API compatibility with existing frontend panels. | Add new endpoints without changing existing ones; reuse existing request/response shape conventions. |
| Redesign suggestions could become LLM-hallucinated safety claims. | Suggestions are generated from structured `failure_modes` + thresholds, not free-form LLM text. |

---

## 7. Test plan

1. **Unit tests**
   - `test_materials.py`: lookup, missing material fallback, property presence.
   - `test_verification_load_cases.py`: each load case returns expected pass/fail/metrics for known inputs.
   - `test_mesh_quality.py`: synthetic good/bad meshes return correct issue flags.

2. **Integration tests**
   - `test_verification_api.py`: backend endpoints return valid reports; API helpers produce correct URLs/payloads.
   - End-to-end smoke test: generate a bracket → run `static_stress` and `mesh_quality` → verify report contains `safety_factor` and `is_suitable_for_solver`.

3. **Frontend**
   - `npm run build` succeeds.
   - Manual smoke test via browser (or Playwright if available): open VerificationPanel, select load case, run check.

---

## 8. Effort estimate

3–5 focused sessions to implement, test, document, and ship. The core risk is mesh-quality integration with build123d STL export; once that is proven, the rest is additive.

---

*Plan written: 2026-08-29*  
*Next step: user approval, then implementation.*
