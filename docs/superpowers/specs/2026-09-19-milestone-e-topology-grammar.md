# RoboCAD 7.7 → 10.0 — Milestone E: Topology Grammar Beyond Templates

**Date:** 2026-09-19
**Current baseline:** Milestones A, B, C, and D complete, 385 default + 256 heavy/slow tests passing (1 xfailed), frontend build passes, honest complex-design confidence **8.7 / 10**.
**Target:** **9.0 / 10** by giving RoboCAD the ability to invent robot topology, not just sweep parameters within three fixed templates.
**Owner focus:** `ai_cad/topology_grammar.py`, `ai_cad/topology_composer.py`, `ai_cad/morphology.py`, `web/backend/main.py`, `web/frontend/src/components/MorphologyPanel.jsx`.
**Spec precedents:** [[milestone-a-adaptive-gait]], [[milestone-b-structural-dynamics]], [[milestone-c-workspace-collision-manipulability]], [[milestone-d-end-effector-families]].

---

## 1. Goal

A user can describe a robot in natural language and RoboCAD can propose and evaluate **multiple topologies** — not just parameter variations of `humanoid`, `quadruped`, or `manipulator_on_base`. Examples:

- *“a hexapod walker with a gripper head”*
- *“a wheeled humanoid with two arms”*
- *“a quadruped with a tail”*
- *“a fixed-base delta arm on a mobile base”*

The system must:

1. Define a deterministic grammar for robot topologies.
2. Search / enumerate topology candidates with physical-feasibility pruning.
3. Map each valid topology to a real `FeatureTree` assembly using existing part families.
4. Run the existing morphology scoring pipeline (stability, gait, workspace, structural, collision, manipulability, actuator).
5. Surface ranked topology choices in the frontend.

---

## 2. What 9.0/10 means here

At 9.0/10, RoboCAD no longer has a hard template ceiling. It can reason about:

- How many limbs a walker needs.
- Where limbs attach on the base.
- What joint sequence each limb has.
- What end-effector family terminates each limb.
- Whether a prompt is physically plausible (e.g., reject a one-legged walker cleanly).

The score moves from **8.7 → 9.0/10** because the *invented topology* is validated by the same physics pipeline that made Milestones A–D meaningful.

---

## 3. Gap this closes

| Gap | Evidence before Milestone E | Status after Milestone E |
|---|---|---|
| Only 3 fixed topologies exist | humanoid / quadruped / manipulator_on_base | ✅ Deterministic grammar generates ≥5 topologies |
| Out-of-template prompts fall back to LLM | hexapod, wheeled-base, tailed robot not first-class | ✅ Grammar maps prompt constraints to topology |
| Topology choice is not physics-validated | Best template picked by keyword, not by score | ✅ Each topology gets full morphology composite score |

---

## 4. Architecture

### 4.1 Core data model

New module `ai_cad/topology_grammar.py` defines:

```python
from dataclasses import dataclass
from typing import Literal

JointType = Literal["revolute", "prismatic", "spherical", "fixed"]
LimbRole = Literal["leg", "arm", "tail", "head", "wheel"]
BaseType = Literal["biped", "quadruped", "hexapod", "wheeled", "tracked", "fixed"]

@dataclass(frozen=True)
class JointSpec:
    type: JointType
    axis: tuple[float, float, float]  # primary axis in base frame
    range_deg: tuple[float, float]
    name: str | None = None

@dataclass(frozen=True)
class LimbSpec:
    role: LimbRole
    side: str  # "left", "right", "front", "rear", "center", etc.
    index: int
    attachment: tuple[float, float, float]  # position on base in mm
    joints: list[JointSpec]
    end_effector_family: str  # e.g., "point_foot", "parallel_jaw_gripper"
    length_schedule: list[float] | None = None  # optional per-segment length hint

@dataclass(frozen=True)
class Topology:
    base_type: BaseType
    base_dimensions: tuple[float, float, float]  # L, W, H in mm
    mass_budget_kg: float
    payload_kg: float
    limbs: list[LimbSpec]
    tags: list[str]  # e.g., "walker", "manipulator", "tail"
```

### 4.2 Grammar productions

A grammar production is a function `produce(base_type, constraints) -> list[Topology]`.

Rules per base type:

| Base type | Min support contacts | Default limb count | Default limb role |
|---|---|---|---|
| `biped` | 2 | 2 | legs |
| `quadruped` | 3 | 4 | legs |
| `hexapod` | 4 | 6 | legs |
| `wheeled` | ≥3 (static polygon) | 2–4 | wheels + optional arms |
| `tracked` | continuous | 2 tracks | no legs |
| `fixed` | N/A | 1–4 | arms |

Optional appendages:

- `tail`: 1 limb with 2–3 revolute joints.
- `head`: 1 limb with pan/tilt joints and a sensor/EE mount.
- `arm`: 1–2 limbs on torso/base with a gripper end-effector.
- `wheel`: rolling contact limb, treated as fixed joint in the first pass.

### 4.3 Physical-feasibility pruning

A topology is rejected before FeatureTree generation if:

1. A walker has fewer than the minimum support contacts in static stance.
2. The base is too small to fit the requested limb attachments without overlap.
3. The total limb mass estimate exceeds the mass budget.
4. An unsupported combination is requested (e.g., `tracked` + `leg`).

### 4.4 Composer mapping

New module `ai_cad/topology_composer.py`:

- `topology_to_feature_tree(topology, seed=0) -> FeatureTree`
- Chooses part families:
  - base: `torso_plate` or a new `mobile_base` family
  - leg: `limb_segment` with 2–3 segments
  - arm: `limb_segment` + end-effector family
  - tail: small `limb_segment` chain
  - head: sensor/EE mount via existing families
- Computes default dimensions from mass budget and topology role.
- Reuses the same mate logic as `ai_cad/composer.py`.

### 4.5 Morphology integration

- `ai_cad/morphology.py` gains a `TopologySpace` (or `MorphologySpace` extended with `topologies: list[Topology]`).
- `search_morphologies` enumerates topologies first, then sweeps parameter dimensions per topology.
- Scoring uses existing `score_candidate` with `use_physics=True`, `use_structural=True`, `use_collision=True`.
- Cache MuJoCo models across variants of the same topology.

### 4.6 Frontend / backend

- Backend:
  - `GET /morphology/topologies` returns available grammar productions constrained by template keywords.
  - `POST /morphology/search` accepts `topologies: list[str]` or `topology_constraints` dict.
- Frontend:
  - `MorphologyPanel.jsx` adds a topology chooser (e.g., dropdown + constraint chips: “biped”, “quadruped”, “hexapod”, “wheeled”, “tail”, “arms”).
  - Search results show the topology tag per candidate.

---

## 5. Detailed deliverables and acceptance

### 5.1 Module: `ai_cad/topology_grammar.py`

**Functions to implement:**

- `all_base_types() -> list[BaseType]`
- `default_topology(base_type: BaseType, payload_kg: float, mass_budget_kg: float) -> Topology`
- `enumerate_topologies(constraints: dict, max_count: int = 12, seed: int = 0) -> list[Topology]`
- `is_feasible(topology: Topology) -> bool`
- `topology_hash(topology: Topology) -> str` for deterministic cache keys

**Acceptance:**
- Deterministic with seed: same constraints + seed produce identical topologies.
- At least 5 distinct feasible topologies can be enumerated.
- Infeasible topologies are pruned (unit tests prove rejection).

### 5.2 Module: `ai_cad/topology_composer.py`

**Functions to implement:**

- `topology_to_feature_tree(topology: Topology, seed: int = 0) -> FeatureTree`
- `_build_base_part(base_type, dims)`
- `_build_limb(limb, base_part_id, base_interface)`
- `_choose_end_effector(family_name) -> Part`

**Acceptance:**
- Generated FeatureTree transpiles and executes via existing build123d executor.
- All limb instances have valid mates.
- At least `hexapod` and `wheeled` topologies produce valid trees.

### 5.3 Integration: `ai_cad/morphology.py`

**Changes:**

- Add `TopologySpace` dataclass with `topologies: list[Topology]` and `dimensions: list[MorphologyDimension]`.
- Add `search_topologies(space, payload_kg, robot_mass_kg, ...)`.
- Reuse `score_candidate` for each `(topology, parameter_set)` combination.
- Cache MuJoCo model per topology hash.

**Acceptance:**
- A `TopologySpace` search returns candidates with distinct topologies.
- Top candidate has composite score > 0.0.
- Heavy/slow suite stays green.

### 5.4 Backend: `web/backend/main.py`

**Changes:**

- `GET /morphology/topologies?template=...&payload=...&mass=...` returns a JSON list of topologies.
- `MorphologySearchRequest` gains optional `topology_constraints: dict` field.
- `/morphology/search` routes to `search_topologies` when topology constraints are present.

**Acceptance:**
- `/morphology/topologies` returns ≥3 options for a generic walker prompt.
- `/morphology/search` with constraints returns ranked candidates with topology tags.

### 5.5 Frontend: `MorphologyPanel.jsx`

**Changes:**

- Add topology selector next to template dropdown.
- Add constraint chips: base type, limb count, tail, arms, wheels.
- Display topology tag per candidate in results.

**Acceptance:**
- Frontend build passes.
- Manual / automated smoke test confirms search request includes topology constraints.

### 5.6 Tests

**New test files:**

- `tests/test_topology_grammar.py`
  - Deterministic enumeration with seed.
  - Pruning of infeasible topologies.
  - ≥5 distinct feasible topologies.
- `tests/test_topology_composer.py`
  - Hexapod FeatureTree has 6 legs.
  - Wheeled topology has ≥2 wheels and a base.
  - Tree transpiles without errors.
- `tests/test_topology_morphology.py` (slow/heavy)
  - Hexapod topology passes MuJoCo load.
  - Wheeled topology passes MuJoCo load.
  - Search over multiple topologies returns non-empty ranked list.

---

## 6. Roadmap integration

| Milestone | Target score | Status |
|---|---|---|
| A — Adaptive gait | 7.7 → 8.0 | ✅ Complete |
| B — Structural dynamics | 8.0 → 8.3 | ✅ Complete |
| C — Workspace / collision / manipulability | 8.3 → 8.5 | ✅ Complete |
| D — Real end-effector families | 8.5 → 8.7 | ✅ Complete |
| **E — Topology grammar** | **8.7 → 9.0** | **🔄 This milestone** |
| F — Real MuJoCo brain training | 9.0 → 9.3 | Planned |
| G — Automatic certification | 9.3 → 9.6 | Planned |
| H — Sim-to-real | 9.6 → 9.8 | Hardware-gated |
| I — Fully automated voice-to-certified-design | 9.8 → 10.0 | Planned |

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Topology grammar explosion | Cap `max_count`, prune by physical feasibility, require prompt constraints. |
| New topologies fail MuJoCo load | Keep default parameters conservative; reuse existing validated part families. |
| Composer duplicates logic | Factor shared base/limb building into helpers called by both composers. |
| Test suite becomes too slow | Cache MuJoCo models per topology hash; tag new physics tests `slow`/`heavy`. |
| Wheeled / tracked contact models are immature | First pass treats wheels as fixed-contact approximations; full rolling contact is future work. |

---

## 8. First three concrete actions

1. **Create `tests/test_topology_grammar.py`** with a failing test for deterministic hexapod enumeration.
2. **Implement `ai_cad/topology_grammar.py`** with `Topology`, `LimbSpec`, `JointSpec`, `enumerate_topologies`, and `is_feasible`.
3. **Implement `ai_cad/topology_composer.py::topology_to_feature_tree`** for hexapod and wheeled topologies, then make the failing tests pass.

---

*Spec written and committed to `docs/superpowers/specs/2026-09-19-milestone-e-topology-grammar.md`.*
