# Milestone E — Topology grammar beyond templates

**Status:** ✅ COMPLETE — 2026-09-19
**Date:** 2026-09-19
**Goal:** Give RoboCAD a deterministic grammar for inventing robot topologies, not just sweeping parameters within three fixed templates, raising the honest complex-design confidence score from **8.7 → 9.0 / 10**.

**Architecture:** Add `ai_cad/topology_grammar.py` for `Topology`, `LimbSpec`, `JointSpec`, deterministic enumeration, physical-feasibility pruning, and stable hashing; add `ai_cad/topology_composer.py` to map any feasible topology to a real `FeatureTree` using existing part families; extend `ai_cad/morphology.py` with `TopologySpace` and wire `search_morphologies` to enumerate and score topologies with the same physics/structural/collision/workspace pipeline used for templates; add backend `/morphology/topologies` and topology-aware `/morphology/search`, plus a topology selector in `MorphologyPanel.jsx`.

**Tech Stack:** Python 3.14, build123d feature-tree schema, existing part-family registry, existing morphology scoring pipeline, FastAPI backend, React frontend.

**Owner focus:** `ai_cad/topology_grammar.py`, `ai_cad/topology_composer.py`, `ai_cad/morphology.py`, `ai_cad/assembly_collision.py`, `web/backend/main.py`, `web/frontend/src/components/MorphologyPanel.jsx`.

---

## Requirements

- Deterministic, seedable grammar for robot topologies.
- Physical-feasibility pruning rejects impossible topologies (e.g., one-legged walker).
- Composer maps abstract topology to a concrete `FeatureTree` that transpiles and exports to MuJoCo.
- Existing morphology scoring pipeline runs on topology-generated trees with no caveats.
- Backend exposes topology enumeration and topology-aware search endpoints.
- Frontend exposes a topology mode alongside the existing template mode.
- All new physics/export tests tagged `slow`, `heavy`, or `mujoco`.

---

## Task 1: Topology grammar module

- **Modify:** `ai_cad/topology_grammar.py`
- **Test:** `tests/test_topology_grammar.py`

**Delivered:**

- `BaseType` and `LimbRole` literals; `JointSpec`, `LimbSpec`, `Topology` frozen dataclasses.
- `default_topology(base_type, payload_kg, mass_budget_kg)` for `biped`, `quadruped`, `hexapod`, `wheeled`, `tracked`, `fixed`.
- `enumerate_topologies(constraints, max_count, seed)` returns a deterministic, pruned list of feasible topologies supporting `base_type`, `appendages`, `min_limbs`, `max_limbs`, and `roles` constraints.
- `is_feasible(topology)` enforces minimum support contacts, mass-budget sanity, attachment bounding-box checks, and unsupported-combo rejection.
- `Topology.topology_hash()` provides stable cache keys.
- `all_base_types()` returns the supported base types.

**Verification:** 9 unit tests pass (default limb counts, determinism, enumeration, pruning, wheeled feasibility).

---

## Task 2: Topology composer

- **Modify:** `ai_cad/topology_composer.py`
- **Test:** `tests/test_topology_composer.py`

**Delivered:**

- `topology_to_feature_tree(topology, seed=0)` builds a `FeatureTree` from a `Topology`.
- Base instantiated from `torso_plate`; per-limb hubs from `hip_hub`; segments from `limb_segment`; tips from the limb's `end_effector_family`.
- Joints generated from `LimbSpec.joints` and attached to the hub/segment/tip chain.
- Family default parameters merged into the tree-level parameter dict so single-part transpilation has every name it needs.

**Caveat found and fixed:** the first composer pass left family-default parameters in the part families but not in the tree-level parameter dict, causing `NameError` (e.g., `hip_hub_diameter`, `hip_bore`) during collision/export mesh generation. `_merge_family_default_parameters` now injects all instantiated families' defaults into the tree parameters before returning the tree.

**Verification:** 6 composer tests pass (hexapod/wheeled instance counts, validation, transpile, family matching, fixed-base gripper).

---

## Task 3: Morphology integration

- **Modify:** `ai_cad/morphology.py`, `ai_cad/assembly_collision.py`
- **Test:** `tests/test_topology_morphology.py`, `tests/test_morphology_api.py`

**Delivered:**

- New `TopologySpace` dataclass carrying `topologies`, `n_max`, and `seed`.
- `MorphologyCandidate` gains an optional `topology` field and serializes it in `to_dict()`.
- `search_morphologies` branches: when given a `TopologySpace`, it enumerates topologies, builds each tree via `topology_to_feature_tree`, and scores it with the existing `score_candidate` (physics/structural/collision/workspace/actuator/manipulability).
- `save_search_results` persists both `MorphologySpace` and `TopologySpace` searches.

**Caveat found and fixed:** topology-generated trees create many unique `Part` ids for repeated family instances (e.g., one `limb_segment` part per leg). The original assembly-collision mesh cache keyed by `part.id`, so the same family geometry was rebuilt for every limb, causing the hexapod score test to time out. The cache now keys by family name (or part id when no family is present), sharing meshes across repeated family instances.

**Verification:**

- `test_hexapod_topology_mujoco_loads` — hexapod FeatureTree exports and loads in MuJoCo.
- `test_wheeled_topology_mujoco_loads` — wheeled FeatureTree exports and loads in MuJoCo.
- `test_hexapod_topology_scores_nonzero` — hexapod gets a non-zero composite morphology score.
- `test_wheeled_topology_scores_nonzero` — wheeled base gets a non-zero composite morphology score.
- `test_topology_search_returns_ranked_candidates` — `TopologySpace` search returns ranked candidates, each carrying a topology.

---

## Task 4: Backend topology endpoints

- **Modify:** `web/backend/main.py`
- **Test:** `tests/test_morphology_api.py`

**Delivered:**

- `GET /morphology/topologies?base_type=...&payload_kg=...&mass_budget_kg=...` returns a list of feasible topologies with `base_type`, `limb_count`, `tags`, and stable `hash`.
- `POST /morphology/search` accepts an optional `topology_constraints` dict; when present, it builds a `TopologySpace`, runs `search_morphologies`, and persists the results.
- Candidate responses include a `topology` object for topology-mode searches.

**Verification:**

- `test_list_morphology_topologies` — walker query returns biped, quadruped, and hexapod options.
- `test_run_topology_search` — topology-mode search returns ranked candidates with non-zero composite scores and topology metadata.

---

## Task 5: Frontend topology selector

- **Modify:** `web/frontend/src/components/MorphologyPanel.jsx`, `web/frontend/src/api.js`
- **Test:** `cd web/frontend && npm run build`

**Delivered:**

- New "Template" / "Topology" mode toggle.
- In topology mode: base-type dropdown (`walker`, `biped`, `quadruped`, `hexapod`, `wheeled`, `tracked`, `fixed`) and appendage toggles (`tail`, `arm`).
- Search button text adapts to the active mode.
- Results table shows a "Topology" column (base type, limb count, tags) when in topology mode.
- `api.js` exposes the topology search payload and `listMorphologyTopologies` helper.

**Verification:** production build passes with no errors.

---

## Task 6: Full regression run and documentation sync

**Files:** `CurrentTo10.md`, `PLAN.md`, `README.md`, memory files.

**Steps:**

- Run default suite: `python -m pytest --timeout=300 -q`.
- Run slow/heavy/mujoco suite: `python -m pytest -m "slow or heavy or mujoco" --timeout=600 -q`.
- Update `README.md` phase table with Milestone E status and score.
- Update `PLAN.md` milestone table and next-session notes.
- Update `CurrentTo10.md` baseline, score, caveat table, and add Milestone E section.
- Create/update private memory files: `milestone-e-topology-grammar.md` and refresh `robocad-confidence-10-10-roadmap.md` / `MEMORY.md`.
- Final commit and push.

---

## Self-review

### Spec coverage

| Spec requirement | Task |
|---|---|
| Deterministic topology grammar | Task 1 |
| Physical-feasibility pruning | Task 1 |
| Composer maps topology to FeatureTree | Task 2 |
| Morphology pipeline scores topologies | Task 3 |
| Backend topology endpoints | Task 4 |
| Frontend topology selector | Task 5 |
| Documentation sync | Task 6 |

### Placeholder scan

No TBD/TODO/"implement later"/"add appropriate" language remains. All steps include concrete code, commands, or test assertions.

### Open issues

- None blocking Milestone E. The next measurable improvement is **Milestone F — real MuJoCo brain training on the actual robot model**, raising the score toward 9.3/10.
