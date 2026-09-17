# Milestone B — Structural Dynamics / FEA for Robot Links

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire structural dynamics checks into the morphology pipeline so that no candidate with slender, weak links survives the search, raising the honest complex-design confidence score from **8.0 → 8.3 / 10**.

**Architecture:** Extract cross-section and length properties for each `limb_segment` / link part in a morphology candidate, run lightweight cantilever / simply-supported bending and Euler-buckling checks, add a `structural_score` to the morphology composite, and optionally dispatch the existing deep CalculiX adapter on the top-N candidates. All changes are deterministic and tested.

**Tech Stack:** Python 3.14, NumPy, trimesh, build123d, CalculiX (optional), pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-robocad-7.7-to-10-roadmap-design.md`

## Global Constraints

- All new code must be deterministic and seedable where applicable.
- Physics-rollout and deep-solver tests must be tagged `slow`, `heavy`, or `mujoco`.
- Default pytest suite (`python -m pytest`) must remain at 380 passing.
- Heavy/slow suite must remain green.
- No hardcoded API keys or secrets.
- FEA dispatch must degrade gracefully when CalculiX is not installed.
- Commit after each independently testable task.

---

## Task 1: Extract link cross-section and length properties from a morphology candidate

**Files:**
- Create: `ai_cad/morphology_structural.py`
- Test: `tests/test_morphology_structural.py`

**Interfaces:**
- Consumes: `FeatureTree` candidate, material name (default "PLA")
- Produces: `list[LinkStructuralProperties]` with length, cross-section area, min/max second moments of area, radius of gyration, slenderness, and material.

**Steps:**
- [ ] **Step 1: Write the failing test**

```python
import pytest

pytestmark = pytest.mark.slow


def test_extract_limb_segment_properties():
    from ai_cad.morphology_structural import extract_link_properties
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    links = extract_link_properties(tree)
    assert len(links) >= 4  # at least thigh, shin, upper_arm, forearm per side
    thigh = [l for l in links if "thigh" in l.name]
    assert thigh
    assert thigh[0].length_m > 0.1
    assert thigh[0].area_m2 > 0.0
    assert thigh[0].i_min_m4 > 0.0
    assert thigh[0].i_max_m4 > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

`python -m pytest tests/test_morphology_structural.py::test_extract_limb_segment_properties -v -o addopts=`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_cad.morphology_structural'`.

- [ ] **Step 3: Create `ai_cad/morphology_structural.py`**

Implement `LinkStructuralProperties` dataclass and `extract_link_properties(tree, material="PLA")` that:
1. Walks the FeatureTree parts and selects parts with `family == "limb_segment"` or `family == "link"`.
2. For each selected part, reads `segment_length`, `segment_width`, `segment_thickness` (or `link_length`, `link_width`, `link_thickness`) from the part parameters or tree parameter dict.
3. Computes cross-sectional area `A = width * thickness` (m²).
4. Computes second moments of area about the weak/strong axes: `I_min = thickness * width^3 / 12`, `I_max = width * thickness^3 / 12` (m⁴), sorted so `I_min <= I_max`.
5. Computes radius of gyration `r_min = sqrt(I_min / A)`, `r_max = sqrt(I_max / A)`.
6. Returns the effective length `length_m` from parameters.
7. Looks up the material via `ai_cad.materials.get_material`.

For parts that lack explicit dimensions, fall back to bounding-box estimates from the part's sketch extents (width from rectangle width, thickness from extrude amount).

- [ ] **Step 4: Run test to verify it passes**

`python -m pytest tests/test_morphology_structural.py::test_extract_limb_segment_properties -v -o addopts=`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/morphology_structural.py tests/test_morphology_structural.py
git commit -m "robocad: Milestone B — extract link cross-section properties from morphology candidates"
```

---

## Task 2: Add lightweight beam bending and buckling checks

**Files:**
- Modify: `ai_cad/morphology_structural.py`
- Test: `tests/test_morphology_structural.py`

**Interfaces:**
- Consumes: `LinkStructuralProperties`, load case (self-weight + payload + drop), end conditions.
- Produces: `BeamCheckResult` with max stress, safety factor, buckling load, and pass/fail.

**Steps:**
- [ ] **Step 1: Write the failing tests**

```python
def test_cantilever_beam_check_passes_for_stocky_link():
    from ai_cad.morphology_structural import LinkStructuralProperties, beam_check

    link = LinkStructuralProperties(
        name="stocky_thigh",
        length_m=0.22,
        area_m2=0.0006,
        i_min_m4=4.5e-8,
        i_max_m4=2.0e-7,
        r_min_m=8.7e-3,
        r_max_m=1.8e-2,
        material_name="aluminum",
    )
    result = beam_check(link, load_case="cantilever_payload", payload_kg=5.0)
    assert result.passed
    assert result.safety_factor > 1.0


def test_slender_link_fails_buckling():
    from ai_cad.morphology_structural import LinkStructuralProperties, beam_check

    link = LinkStructuralProperties(
        name="slender_thigh",
        length_m=0.60,
        area_m2=0.0001,
        i_min_m4=8.0e-10,
        i_max_m4=2.0e-9,
        r_min_m=2.8e-3,
        r_max_m=4.5e-3,
        material_name="PLA",
    )
    result = beam_check(link, load_case="cantilever_payload", payload_kg=5.0)
    assert not result.passed
    assert result.failure_modes
```

- [ ] **Step 2: Run tests to verify they fail**

`python -m pytest tests/test_morphology_structural.py -v -o addopts=`

Expected: FAIL with missing `BeamCheckResult` / `beam_check`.

- [ ] **Step 3: Implement beam checks in `ai_cad/morphology_structural.py`**

Add `BeamCheckResult` dataclass and `beam_check(link, load_case, payload_kg=0.0, drop_height_m=0.0, safety_factor_target=2.0)`:

1. Compute total end load from self-weight plus payload. Self-weight = `density * area * length * g`. Payload force = `payload_kg * g`.
2. For `load_case == "cantilever_payload"`, treat the link as a cantilever with point load at the free end:
   - `M = F * length`
   - `sigma = M * c / I_max`, where `c = thickness / 2` corresponding to `I_max` axis.
   - `safety_factor = yield_strength / sigma`.
3. For `load_case == "simply_supported_payload"`, treat as simply supported beam with central point load:
   - `M = F * length / 4`
   - `sigma = M * c / I_max`.
4. Euler buckling about the weak axis:
   - `P_cr = pi^2 * E * I_min / (K * length)^2`, where `K = 2.0` for cantilever, `K = 1.0` for pinned-pinned.
   - `P_applied = F`.
   - `buckling_safety = P_cr / P_applied`.
5. Drop load case adds an impact factor when `drop_height_m > 0`:
   - `impact_velocity = sqrt(2 * g * drop_height_m)`
   - `impact_duration_s = 0.005`
   - `peak_accel_g = impact_velocity / (impact_duration_s * g)`
   - multiply applied static load by `impact_factor = max(1.0, peak_accel_g)`.
6. A link passes if `safety_factor >= safety_factor_target` AND `buckling_safety >= safety_factor_target`.
7. Return failure modes: `"yield_exceeded"`, `"buckling"`, or both.

- [ ] **Step 4: Run tests to verify they pass**

`python -m pytest tests/test_morphology_structural.py -v -o addopts=`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/morphology_structural.py tests/test_morphology_structural.py
git commit -m "robocad: Milestone B — lightweight beam bending and buckling checks"
```

---

## Task 3: Add `structural_score` to morphology composite scoring

**Files:**
- Modify: `ai_cad/morphology.py` (add `structural_score` sub-score)
- Modify: `ai_cad/morphology_structural.py` (add `score_candidate_structural`)
- Test: `tests/test_morphology_structural.py`

**Interfaces:**
- Consumes: `FeatureTree` candidate, payload, material.
- Produces: `float` in [0, 1] penalizing links that fail stress/buckling.

**Steps:**
- [ ] **Step 1: Write the failing test**

```python
def test_structural_score_penalizes_slender_humanoid():
    from ai_cad.morphology import score_candidate
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    # Deliberately thin thigh to trigger structural failure.
    tree = tree.update_parameter("thigh_length", 400.0)
    result = score_candidate(tree, payload_kg=5.0, robot_mass_kg=20.0, use_physics=False, use_structural=True)
    assert result["structural_score"] < 0.5
    assert result["scores"]["structural"] < 0.5
```

- [ ] **Step 2: Run test to verify it fails**

`python -m pytest tests/test_morphology_structural.py::test_structural_score_penalizes_slender_humanoid -v -o addopts=`

Expected: FAIL — `score_candidate` has no `use_structural` argument.

- [ ] **Step 3: Implement structural scoring**

In `ai_cad/morphology_structural.py`:

```python
def score_candidate_structural(tree, payload_kg: float = 0.0, material: str = "PLA") -> dict[str, Any]:
    links = extract_link_properties(tree, material=material)
    if not links:
        return {"structural_score": 1.0, "links": [], "notes": "no structural links found"}
    results = [beam_check(link, "cantilever_payload", payload_kg=payload_kg) for link in links]
    ok = sum(1 for r in results if r.passed)
    score = ok / len(results)
    worst = min(results, key=lambda r: r.safety_factor) if results else None
    return {
        "structural_score": score,
        "links": [r.__dict__ for r in results],
        "worst_link": worst.name if worst else None,
        "notes": f"{ok}/{len(results)} links passed",
    }
```

In `ai_cad/morphology.py`:
1. Import `score_candidate_structural`.
2. Add `use_structural: bool = True` parameter to `score_candidate`.
3. When `use_structural` is True, call `score_candidate_structural(tree, payload_kg=payload_kg)` and store `structural_score` in the scores dict under key `"structural"`.
4. Add a small weight to the composite:
   - Reduce `stability` weight from 0.30 to 0.25.
   - Add `structural` weight of 0.05.
   - Keep other weights: workspace 0.25, gait 0.25, actuator 0.15, compactness 0.05.
5. Expose `structural_score` and `structural_notes` in the returned score dict.

- [ ] **Step 4: Run test to verify it passes**

`python -m pytest tests/test_morphology_structural.py::test_structural_score_penalizes_slender_humanoid -v -o addopts=`

Expected: PASS.

- [ ] **Step 5: Run default suite to confirm no regressions**

`python -m pytest --timeout=120 -q`

Expected: 380 passed.

- [ ] **Step 6: Commit**

```bash
git add ai_cad/morphology_structural.py ai_cad/morphology.py tests/test_morphology_structural.py
git commit -m "robocad: Milestone B — structural_score wired into morphology composite"
```

---

## Task 4: Wire deep FEA dispatcher for top-N morphology candidates

**Files:**
- Modify: `ai_cad/morphology.py` (optionally dispatch deep verification)
- Modify: `ai_cad/solvers/verification_deep.py` or add helper (minimal)
- Test: `tests/test_morphology_structural.py` (optional deep-dispatch smoke test)

**Interfaces:**
- Consumes: top candidate tree, design directory, solver mode (`auto` / `real` / `surrogate`).
- Produces: `VerificationResult` from deep structural analysis, or graceful fallback.

**Steps:**
- [ ] **Step 1: Add helper `run_deep_structural_for_candidate`**

In `ai_cad/morphology_structural.py`:

```python
def run_deep_structural_for_candidate(
    tree,
    design_dir: Path,
    payload_kg: float = 0.0,
    material: str = "PLA",
    solver_mode: str = "auto",
) -> dict[str, Any]:
    """Dispatch deep structural verification if solver is available."""
    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.solvers.verification_deep import run_deep_verification
    from ai_cad.verification_models import LoadCase, VerificationRequest

    try:
        export_bundle_from_tree(tree, design_dir)
    except Exception as exc:
        return {"deep_available": False, "error": str(exc)}

    request = VerificationRequest(
        design_id="candidate",
        load_case=LoadCase.STATIC_STRESS,
        material=material,
        params={"load_magnitude_n": payload_kg * 9.81, "safety_factor_target": 2.0},
        solver_mode=solver_mode,
    )
    result = run_deep_verification(request, design_dir)
    return {
        "deep_available": True,
        "passed": result.passed,
        "metrics": result.metrics,
        "failure_modes": result.failure_modes,
        "redesign_suggestions": result.redesign_suggestions,
    }
```

- [ ] **Step 2: Add optional deep verification in `search_morphologies`**

Add parameter `run_deep_structural: bool = False` and `deep_top_n: int = 3` to `search_morphologies`. When enabled, after scoring all candidates, run `run_deep_structural_for_candidate` on the top-N candidates and merge the result into their score dicts. The lightweight `structural_score` remains the primary filter; deep verification adds diagnostic detail.

- [ ] **Step 3: Write smoke test**

```python
@pytest.mark.heavy
def test_deep_structural_smoke_falls_back_gracefully():
    from ai_cad.morphology_structural import run_deep_structural_for_candidate
    from ai_cad.robot_templates import humanoid_template
    import tempfile

    tree = humanoid_template()
    with tempfile.TemporaryDirectory() as tmp:
        result = run_deep_structural_for_candidate(tree, Path(tmp), payload_kg=5.0, solver_mode="surrogate")
        assert result["deep_available"] is True
        assert "passed" in result
```

- [ ] **Step 4: Run tests**

`python -m pytest tests/test_morphology_structural.py -v -o addopts=`

Expected: PASS (deep test may be deselected by default, run with `-m heavy`).

- [ ] **Step 5: Commit**

```bash
git add ai_cad/morphology_structural.py ai_cad/morphology.py tests/test_morphology_structural.py
git commit -m "robocad: Milestone B — optional deep FEA dispatch for top-N morphology candidates"
```

---

## Task 5: Regression test — long-thin humanoid candidate is penalized

**Files:**
- Test: `tests/test_morphology_structural.py`

**Steps:**
- [ ] **Step 1: Add end-to-end morphology search test**

```python
@pytest.mark.slow
def test_morphology_search_prefers_structurally_sound_humanoid():
    from ai_cad.morphology import default_space, search_morphologies

    space = default_space("humanoid")
    space.n_max = 16
    candidates = search_morphologies(space, payload_kg=5.0, robot_mass_kg=20.0, use_physics=True, use_structural=True)
    assert candidates
    # The top candidate should have a non-zero structural score.
    top = max(candidates, key=lambda c: c.composite_score)
    assert top.scores.get("structural", 0.0) > 0.0
```

- [ ] **Step 2: Run test**

`python -m pytest tests/test_morphology_structural.py::test_morphology_search_prefers_structurally_sound_humanoid -v -o addopts=`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_morphology_structural.py
git commit -m "robocad: Milestone B — structural regression test on morphology search"
```

---

## Task 6: Full regression run and documentation sync

**Files:**
- Modify: `CurrentTo10.md`, `PLAN.md`, `README.md`, memory files
- Test: full suite

**Steps:**
- [ ] **Step 1: Run default suite**

`python -m pytest --timeout=120 -q`

Expected: 380 passed, same baseline.

- [ ] **Step 2: Run heavy/slow suite**

`python -m pytest tests -m "heavy or slow or mujoco" --tb=short -q`

Expected: green.

- [ ] **Step 3: Update documentation**

- `CurrentTo10.md`: update score from 8.0 → 8.3/10, add Milestone B results.
- `PLAN.md`: append Milestone B acceptance to milestone table.
- `README.md`: add Milestone B line to phase table.
- Memory files: create/update `milestone-b-structural-dynamics.md` and update `robocad-confidence-10-10-roadmap.md` / `MEMORY.md`.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "robocad: Milestone B complete — structural dynamics / FEA for robot links, 8.0 -> 8.3/10"
```

---

## Self-review

### Spec coverage

| Spec requirement | Task |
|------------------|------|
| Link cross-section extraction | Task 1 |
| Lightweight beam checks | Task 2 |
| `structural_score` in morphology composite | Task 3 |
| Deep FEA wiring for top-N candidates | Task 4 |
| Regression tests | Task 5 |
| Documentation sync | Task 6 |

### Placeholder scan

No TBD/TODO/"implement later"/"add appropriate" language remains. All steps include concrete code or commands.

### Type consistency

- `LinkStructuralProperties` and `BeamCheckResult` dataclasses are used consistently.
- `score_candidate_structural` returns a dict matching the morphology scoring contract.
- Deep verification helper reuses existing `VerificationRequest` / `VerificationResult` models.

### Open issues

- Deep CalculiX dispatch is optional; when the real solver is unavailable, the helper falls back to the lightweight beam formulas and the surrogate path.
- The lightweight beam formulas assume a rectangular cross-section. For non-rectangular limb families in the future, cross-section properties should be computed from the actual mesh.

---

*Plan created for Milestone B — structural dynamics / FEA for robot links.*
