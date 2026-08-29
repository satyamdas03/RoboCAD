> Task 3 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

### Task 3: Extend feature tree to schema v2 with domain tags

**Files:**
- Modify: `ai_cad/feature_tree.py`
- Create: `tests/test_feature_tree_v2.py`

**Interfaces:**
- Consumes: existing v1 schema and models
- Produces: backward-compatible v2 models with `domain`, `KinematicJoint`, `SurfaceFeature`, `PCBOutline`

- [ ] **Step 1: Write failing test**

In `tests/test_feature_tree_v2.py`:

```python
from ai_cad.feature_tree import FeatureTree, Feature, Part, Assembly, KinematicJoint, SurfaceFeature, PCBOutline


def test_default_domain_is_mechanical():
    tree = FeatureTree(
        design_id="d1",
        prompt="bracket",
        parameters=[{"name": "thickness", "value": 3.0}],
        features=[{"type": "extrude", "id": "f1", "sketch_id": "s1", "depth": 10.0}],
    )
    assert tree.features[0].domain == "mechanical"


def test_aero_surface_feature():
    tree = FeatureTree(
        design_id="d2",
        prompt="airfoil",
        parameters=[{"name": "chord", "value": 200.0}],
        features=[SurfaceFeature(id="af1", type="airfoil", profile={"naca": "2412", "chord_param": "chord"}).model_dump()],
    )
    assert tree.features[0].domain == "aero"


def test_kinematic_joint_in_assembly():
    asm = Assembly(
        id="a1",
        name="arm",
        parts=[],
        mates=[],
        joints=[KinematicJoint(id="j1", type="revolute", parent_link="base", child_link="link1", origin=(0, 0, 0), axis=(0, 0, 1))],
    )
    assert asm.joints[0].type == "revolute"


def test_pcb_outline():
    pcb = PCBOutline(id="pcb1", board_shape=[(0, 0), (85, 0), (85, 56), (0, 56)], mounting_holes=[(3.5, 3.5, 3.0)])
    assert pcb.domain == "electronics"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_feature_tree_v2.py -v
```

Expected: failures due to missing `domain`, `SurfaceFeature`, `KinematicJoint`, `PCBOutline`.

- [ ] **Step 3: Extend models**

Modify `ai_cad/feature_tree.py`:

1. Add to imports: `Literal` already imported; no change needed.
2. Add after `Parameter`:

```python
class KinematicJoint(BaseModel):
    id: str
    type: Literal["revolute", "prismatic", "spherical", "fixed"]
    parent_link: str
    child_link: str
    origin: tuple[float, float, float]
    axis: tuple[float, float, float] | None = None
    limits: tuple[float, float] | None = None


class SurfaceFeature(BaseModel):
    id: str
    type: Literal["airfoil", "wing", "duct", "heat_sink", "propeller_blade"]
    profile: dict[str, Any]
    domain: str = "aero"


class PCBOutline(BaseModel):
    id: str
    board_shape: list[tuple[float, float]]
    mounting_holes: list[tuple[float, float, float]] = Field(default_factory=list)
    keepouts: list[dict[str, Any]] = Field(default_factory=list)
    domain: str = "electronics"
```

3. Add `domain: str = "mechanical"` to `Feature`, `Part`, and `Assembly`.

4. Add `joints: list[KinematicJoint] = Field(default_factory=list)` to `Assembly`.

5. Add `domain: str = "mechanical"` to `FeatureTree`.

6. Bump docstring to reference schema v2.0.0.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_feature_tree_v2.py tests/test_feature_tree.py tests/test_transpiler.py -v
```

Expected: all pass with no regressions.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/feature_tree.py tests/test_feature_tree_v2.py
git commit -m "feat(feature-tree): schema v2 with domain tags, aero surfaces, joints, PCB outlines"
```

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-3-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
