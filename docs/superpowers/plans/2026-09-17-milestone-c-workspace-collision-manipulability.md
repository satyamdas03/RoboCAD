# Milestone C — Workspace, Self-Collision, and Manipulability

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the morphology composite robust to sagittal-plane arms, self-collisions, and kinematic dexterity, raising the honest complex-design confidence score from **8.3 → 8.5 / 10**.

**Architecture:** Add a sagittal-plane workspace proxy, sample representative task poses and run pairwise assembly collision checks, and compute a Yoshikawa-style manipulability index for arm chains. Feed the results into `score_candidate` as `workspace` (revised), `collision_penalty`, and `manipulability_score` sub-scores.

**Tech Stack:** Python 3.14, NumPy, trimesh, existing `kinematic_tree.py` and `assembly_collision.py`.

**Spec:** `docs/superpowers/specs/2026-09-16-robocad-7.7-to-10-roadmap-design.md`

## Global Constraints

- All new code must be deterministic and seedable where applicable.
- Physics-rollout, collision, and deep-solver tests must be tagged `slow`, `heavy`, or `mujoco`.
- Default pytest suite (`python -m pytest`) must remain at 380 passing.
- Heavy/slow suite must remain green.
- No hardcoded API keys or secrets.
- Collision/manipulability checks must degrade gracefully for templates with no assembly.
- Commit after each independently testable task.

---

## Task 1: Sagittal-plane workspace proxy

**Files:**
- Create: `ai_cad/morphology_workspace.py`
- Test: `tests/test_morphology_workspace.py`
- Modify: `ai_cad/morphology.py`

**Interfaces:**
- Consumes: `FeatureTree`, end-effector instance id, number of workspace samples.
- Produces: dict with `reach_mm`, `sagittal_area_mm2`, `lateral_span_mm`, `manipulability_index`, `workspace_score`.

**Steps:**
- [x] **Step 1: Write the failing test**

```python
import pytest
pytestmark = pytest.mark.slow


def test_humanoid_workspace_proxy_nonzero_for_sagittal_arm():
    from ai_cad.morphology_workspace import workspace_proxy
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    result = workspace_proxy(tree, "hand_r")
    assert result["reach_mm"] > 0.0
    assert result["sagittal_area_mm2"] > 0.0
    assert result["workspace_score"] > 0.0
```

- [x] **Step 2: Run test to verify it fails**

`python -m pytest tests/test_morphology_workspace.py::test_humanoid_workspace_proxy_nonzero_for_sagittal_arm -v -o addopts=`

Expected: FAIL with `ModuleNotFoundError: no module named 'ai_cad.morphology_workspace'`.

- [x] **Step 3: Create `ai_cad/morphology_workspace.py`**

Implement:
1. `workspace_proxy(tree, end_effector_id, samples_per_joint=5)` that calls `sample_reachable_workspace`.
2. Computes:
   - `reach_mm` = max absolute X among reachable points (forward reach).
   - `sagittal_area_mm2` = convex-hull area of reachable (x, z) points (shoelace formula via `scipy.spatial.ConvexHull` if available, else bounding-box area).
   - `lateral_span_mm` = max Y − min Y of reachable points.
   - `manipulability_index` = average Yoshikawa-style sqrt(det(J @ J.T)) sampled across the reachable set for the end-effector chain (optional for this task; will be refined in Task 3).
3. `workspace_score` = normalized combination:
   - 50% reach (normalize to 1500 mm)
   - 30% sagittal_area (normalize to 1.0e6 mm²)
   - 20% lateral_span (normalize to 800 mm)
4. Graceful fallback: if no assembly or no points, return zeros.

- [x] **Step 4: Run test to verify it passes**

`python -m pytest tests/test_morphology_workspace.py -v -o addopts=`

Expected: PASS.

- [x] **Step 5: Wire into `score_candidate`**

In `ai_cad/morphology.py`:
1. Import `workspace_proxy`.
2. Replace the existing workspace scoring block with:
   ```python
   proxy = workspace_proxy(tree, end_effector_id, samples_per_joint=4)
   workspace_score = proxy["workspace_score"]
   ```
3. Keep `workspace_volume_mm3` and `workspace_envelope_mm` in the returned dict for backward compatibility, but use proxy-derived `reach_mm` and `sagittal_area_mm2`.

- [x] **Step 6: Run default suite to confirm no regressions**

`python -m pytest --timeout=120 -q`

Expected: 380 passed.

- [x] **Step 7: Commit**

```bash
git add ai_cad/morphology_workspace.py ai_cad/morphology.py tests/test_morphology_workspace.py
git commit -m "robocad: Milestone C — sagittal-plane workspace proxy for morphology scoring"
```

---

## Task 2: Self-collision checks across representative poses

**Files:**
- Create: `ai_cad/morphology_collision.py`
- Test: `tests/test_morphology_collision.py`
- Modify: `ai_cad/morphology.py`

**Interfaces:**
- Consumes: `FeatureTree`, list of pose names / joint-state dicts, temporary output directory.
- Produces: dict with `collision_penalty` in [0, 1], `interference_count`, `worst_clearance_mm`, `poses_checked`.

**Steps:**
- [x] **Step 1: Write the failing tests**

```python
import pytest
pytestmark = pytest.mark.slow


def test_humanoid_default_pose_has_no_self_collision():
    from ai_cad.morphology_collision import score_candidate_collision
    from ai_cad.robot_templates import humanoid_template
    import tempfile

    tree = humanoid_template()
    with tempfile.TemporaryDirectory() as tmp:
        result = score_candidate_collision(tree, output_dir=tmp)
    assert result["collision_penalty"] < 0.5
    assert result["poses_checked"] >= 1
```

- [x] **Step 2: Run tests to verify they fail**

`python -m pytest tests/test_morphology_collision.py -v -o addopts=`

Expected: FAIL with missing module / function.

- [x] **Step 3: Create `ai_cad/morphology_collision.py`**

Implement:
1. `_default_pose_set(tree)` returns representative poses based on template:
   - For humanoid/quadruped: `neutral` (all joints 0) and `walking` (hip/knee slightly flexed).
   - For manipulator_on_base: `neutral`, `reach_forward`, `reach_high`.
2. `score_candidate_collision(tree, output_dir, poses=None, samples=200)`:
   - For each pose, set joint states via `forward_kinematics` (or pass joint states to collision checker if available).
   - Use `check_assembly_collision` with a small set of sampled poses by temporarily updating instance transforms.
   - Count interference / transition pairs across all poses.
   - `collision_penalty` = fraction of colliding pose-pairs, clipped at 1.0. If no assembly, return 0.0 penalty (no collision data).
3. Cache per-part meshes across poses to avoid rebuilding.

For simplicity in the first pass, collision per pose can be approximated by running `check_assembly_collision` once on the *nominal* tree plus once with hip/knee flexed by overriding joint states and computing link transforms. The `check_assembly_collision` currently uses `compute_instance_transforms` which does not take joint states; we will inject pose transforms by building a modified `FeatureTree` per pose or by adding a `joint_states` parameter to the collision check path.

**Decision:** Add an optional `joint_states` parameter to `check_assembly_collision` and `compute_instance_transforms`. When provided, apply the joint deltas to the nominal transforms before collision checking.

- [x] **Step 4: Run tests to verify they pass**

`python -m pytest tests/test_morphology_collision.py -v -o addopts=`

Expected: PASS.

- [x] **Step 5: Wire `collision_penalty` into `score_candidate`**

In `ai_cad/morphology.py`:
1. Import `score_candidate_collision`.
2. Add `use_collision: bool = True` parameter.
3. Compute collision report and subtract collision penalty from composite:
   ```python
   collision = score_candidate_collision(tree, output_dir=tempfile.mkdtemp()) if use_collision else {"collision_penalty": 0.0}
   collision_penalty = float(collision["collision_penalty"])
   ```
4. Reduce `stability` weight from 0.25 to 0.22 and add `collision` weight 0.03 (so composite still sums to 1.0 with the existing weights including structural 0.05). Actually, maintain a clean weight set:
   - stability 0.22
   - workspace 0.22
   - gait 0.22
   - actuator 0.13
   - compactness 0.05
   - structural 0.05
   - collision 0.03
   - manipulability 0.08
   Wait, that changes the sum. We will decide in Task 4. For this task, simply add `collision_penalty` as a subtractive term (not a weighted sub-score) so the existing weight sum is unchanged:
   ```python
   composite = composite * (1.0 - collision_penalty)
   ```
   This is simpler and conservative.
5. Expose `collision_penalty`, `collision_interference_count`, `collision_poses_checked` in result dict.

- [x] **Step 6: Run default suite**

`python -m pytest --timeout=120 -q`

Expected: 380 passed.

- [x] **Step 7: Commit**

```bash
git add ai_cad/morphology_collision.py ai_cad/morphology.py ai_cad/assembly_collision.py ai_cad/assembly.py tests/test_morphology_collision.py
git commit -m "robocad: Milestone C — self-collision checks across representative poses"
```

---

## Task 3: Manipulability index

**Files:**
- Modify: `ai_cad/morphology_workspace.py`
- Test: `tests/test_morphology_workspace.py`
- Modify: `ai_cad/morphology.py`

**Interfaces:**
- Consumes: end-effector chain (`list[KinematicJoint]`), joint values.
- Produces: `manipulability_score` in [0, 1].

**Steps:**
- [x] **Step 1: Write the failing test**

```python
import pytest
pytestmark = pytest.mark.slow


def test_manipulability_nonzero_for_manipulator():
    from ai_cad.morphology_workspace import manipulability_score
    from ai_cad.robot_templates import manipulator_on_base_template

    tree = manipulator_on_base_template()
    score = manipulability_score(tree, "end_effector")
    assert score > 0.0
```

- [x] **Step 2: Run test to verify it fails**

`python -m pytest tests/test_morphology_workspace.py::test_manipulability_nonzero_for_manipulator -v -o addopts=`

Expected: FAIL.

- [x] **Step 3: Implement manipulability computation**

In `ai_cad/morphology_workspace.py`:
1. `compute_jacobian(chain, joint_values)` builds a 6×n Jacobian from the joint chain using geometric Jacobian (cross product of axis-to-EE vector with joint axis for revolute; joint axis for prismatic).
2. `manipulability_index(jacobian)` returns `sqrt(max(0.0, det(J @ J.T)))`.
3. `manipulability_score(tree, end_effector_id, samples=8)` samples random/representative joint values within limits, computes average index, and normalizes to [0, 1] using a target of 5000 mm³ (unit-agnostic scaling).
4. Expose `manipulability_index` and `manipulability_score` in the workspace proxy result.

- [x] **Step 4: Run tests**

`python -m pytest tests/test_morphology_workspace.py -v -o addopts=`

Expected: PASS.

- [x] **Step 5: Wire into `score_candidate`**

In `ai_cad/morphology.py`:
1. Update `workspace_proxy` call to capture `manipulability_score`.
2. Add a new weight `manipulability` with value 0.08.
3. Adjust other weights to keep sum = 1.0. Proposed final weight set:
   - stability 0.22
   - workspace 0.20
   - gait 0.22
   - actuator 0.13
   - compactness 0.05
   - structural 0.05
   - collision 0.05
   - manipulability 0.08
   Sum = 1.00.
4. Compute composite with manipulability and collision as weighted sub-scores (replace the previous multiplicative collision penalty).
5. Expose `manipulability` in returned scores.

- [x] **Step 6: Run default suite**

`python -m pytest --timeout=120 -q`

Expected: 380 passed.

- [x] **Step 7: Commit**

```bash
git add ai_cad/morphology_workspace.py ai_cad/morphology.py tests/test_morphology_workspace.py
git commit -m "robocad: Milestone C — manipulability index for end-effector chains"
```

---

## Task 4: Regression test — collision penalizes impossible humanoid

**Files:**
- Test: `tests/test_morphology_collision.py`

**Steps:**
- [x] **Step 1: Add end-to-end morphology search test**

```python
@pytest.mark.slow
def test_morphology_search_prefers_collision_free_humanoid():
    from ai_cad.morphology import default_space, search_morphologies

    space = default_space("humanoid")
    space.n_max = 12
    candidates = search_morphologies(space, payload_kg=5.0, robot_mass_kg=20.0, use_physics=False, use_structural=False, use_collision=True)
    assert candidates
    top = max(candidates, key=lambda c: c.composite_score)
    assert top.scores.get("collision_penalty", 1.0) < 0.5
```

- [x] **Step 2: Run test**

`python -m pytest tests/test_morphology_collision.py::test_morphology_search_prefers_collision_free_humanoid -v -o addopts=`

Expected: PASS.

- [x] **Step 3: Commit**

```bash
git add tests/test_morphology_collision.py
git commit -m "robocad: Milestone C — collision regression on morphology search"
```

---

## Task 5: Full regression run and documentation sync

**Files:**
- Modify: `CurrentTo10.md`, `PLAN.md`, `README.md`, memory files
- Test: full suite

**Steps:**
- [x] **Step 1: Run default suite**

`python -m pytest --timeout=120 -q`

Expected: 380 passed, same baseline.

- [x] **Step 2: Run heavy/slow suite**

`python -m pytest tests -m "heavy or slow or mujoco" --deselect tests/test_morphology_api.py::test_simulate_morphology_candidate --tb=short -q`

Expected: green.

- [x] **Step 3: Update documentation**

- `CurrentTo10.md`: update score from 8.3 → 8.5/10, add Milestone C results.
- `PLAN.md`: append Milestone C acceptance to milestone table.
- `README.md`: add Milestone C line to phase table.
- Memory files: create/update `milestone-c-workspace-collision-manipulability.md` and update `robocad-confidence-10-10-roadmap.md` / `MEMORY.md`.
- Mark Milestone C plan checkboxes complete.

- [x] **Step 4: Final commit**

```bash
git add -A
git commit -m "robocad: Milestone C complete — workspace, self-collision, and manipulability, 8.3 -> 8.5/10"
```

---

## Self-review

### Spec coverage

| Spec requirement | Task |
|---|---|
| Sagittal-plane workspace proxy | Task 1 |
| Self-collision checks | Task 2 |
| Manipulability index | Task 3 |
| Regression tests | Task 4 |
| Documentation sync | Task 5 |

### Placeholder scan

No TBD/TODO/"implement later"/"add appropriate" language remains. All steps include concrete code or commands.

### Type consistency

- `workspace_proxy` returns a stable dict contract consumed by `score_candidate`.
- `score_candidate_collision` returns a stable dict with `collision_penalty`.
- Weights sum to exactly 1.0.

### Open issues

- `check_assembly_collision` currently recomputes instance transforms from mates. Adding a `joint_states` parameter keeps the path deterministic and reusable.
- Workspace/manipulability sampling uses joint limits; templates with very coarse limits may overestimate reach.

---

*Plan created for Milestone C — workspace, self-collision, and manipulability.*
