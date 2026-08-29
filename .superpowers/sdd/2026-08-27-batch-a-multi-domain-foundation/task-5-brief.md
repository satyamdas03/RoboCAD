> Task 5 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

### Task 5: Add airfoil sketch entity

**Files:**
- Modify: `ai_cad/sketch.py`
- Modify: `ai_cad/sketch_solver.py`
- Create: `tests/test_sketch_airfoil.py`

**Interfaces:**
- Consumes: existing sketch solver framework
- Produces: `airfoil` entity type that yields a set of points and a thickness parameter

- [ ] **Step 1: Write failing test**

In `tests/test_sketch_airfoil.py`:

```python
from ai_cad.sketch import SketchEntity
from ai_cad.sketch_solver import solve_sketch


def test_airfoil_entity():
    entities = [
        SketchEntity(type="airfoil", id="af1", naca="2412", chord=200.0)
    ]
    result = solve_sketch(entities, [])
    assert "af1" in result.points
    assert len(result.points["af1"]) > 10
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_sketch_airfoil.py -v
```

Expected: failure because `airfoil` is not handled.

- [ ] **Step 3: Implement airfoil entity**

In `ai_cad/sketch.py` add `airfoil` to `SketchEntity.type` Literal and add fields:

```python
naca: str | None = None
chord: NumericOrString | None = None
```

In `ai_cad/sketch_solver.py`, in the solver loop, add handling for `type == "airfoil"`:

```python
def _naca_4digit_points(code: str, chord: float, n: int = 40) -> list[tuple[float, float]]:
    # Simplified NACA 4-digit thickness form
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    tt = int(code[2:4]) / 100.0
    pts = []
    for i in range(n + 1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (0.2969 * xc**0.5 - 0.1260 * xc - 0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        pts.append((x, yt))
    for i in range(n, -1, -1):
        x = (i / n) * chord
        xc = x / chord
        yt = 5 * tt * (0.2969 * xc**0.5 - 0.1260 * xc - 0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        pts.append((x, -yt))
    return pts
```

Store the resulting points in the solver state under the entity id.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_sketch_airfoil.py tests/test_sketch_solver.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add ai_cad/sketch.py ai_cad/sketch_solver.py tests/test_sketch_airfoil.py
git commit -m "feat(sketch): add NACA 4-digit airfoil sketch entity"
```

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-5-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
