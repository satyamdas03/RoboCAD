# Phase 18 Implementation Plan — Automatic Decomposition and Domain Part Families

## Context

RoboCAD has completed **Batch A (Phases 16–17)**. The classifier, per-domain intent parser, and feature-tree schema v2.0.0 are in place and all 201 tests pass. The next committed goal in `PLAN.md` is **Phase 18: Automatic decomposition and domain part families**.

## Goal

Enable RoboCAD to take a system-level prompt such as *“450 mm quadcopter frame with four motor arms and aerodynamic shell”* and automatically:

1. Detect that it is a **multi-domain system** intent.
2. Decompose it into named sub-parts mapped to domains and part families.
3. Fill each sub-part from a reusable **part-family template** with default parameters and interface geometry.
4. Compose the sub-parts into a single `FeatureTree` with an `Assembly`, `Instances`, and inferred `Mates`.
5. Transpile and validate the assembly end-to-end.

## Design Decisions

### 1. Trigger mode — **automatic when multi-domain, with opt-out**

When `POST /generate` receives a prompt, the backend already classifies the domain. If `classify_domain` reports `multi_domain=True`, or the prompt contains known system nouns (`drone`, `quadcopter`, `robot arm`, `chassis`), the backend enters the decomposition path. A new `decompose=False` flag on `/generate` lets the caller disable this and get a single-part result as before.

*Rationale:* This keeps the existing single-part flow unchanged while giving system prompts a first-class path. It matches the “automatic decomposition and domain part families” wording in `PLAN.md`.

### 2. Decomposition engine — **rule + lightweight LLM**

New module `ai_cad/decomposition.py`.

- **Rule layer:** A small domain-to-part-family map and system noun lexicon.
  - `mechanical`: bracket, link, hub, mount, pulley.
  - `aero/thermal`: airfoil, wing, duct, heat_sink, propeller_blade.
  - `electronics`: pcb_bracket, enclosure, connector_mount, cable_guide.
  - `humanoid`: limb_segment, torso_plate, end_effector, foot.
- **LLM layer:** If the rule layer is ambiguous, a short system prompt asks the configured model for a JSON list of sub-parts with domain and family.
- **Fallback:** Return a single mechanical part if decomposition fails.

*Rationale:* Rules give deterministic, testable behavior for the standard examples required by `PLAN.md`; the LLM extends coverage gracefully.

### 3. Part-family library — `ai_cad/part_families.py`

A registry of dataclasses:

```python
@dataclass
class PartFamily:
    name: str
    domain: str
    default_parameters: list[Parameter]
    default_features: list[dict]
    interface_csys: CoordinateSystem | None  # e.g., motor mount hole pattern
    mates: list[Mate] | None  # default mates when placed in an assembly
```

Part families are **symbolic** — they produce feature-tree snippets, not hardcoded meshes. They integrate with the existing feature-tree + transpiler stack.

### 4. Composition into assembly

New module `ai_cad/composer.py`:

- Takes the decomposition result.
- Generates each sub-part by calling `parse_domain_intent` for the sub-prompt, then merging the intent with the part-family defaults.
- Produces a `FeatureTree` with:
  - One `Part` per sub-part (domain-tagged).
  - One `Assembly` with `Instance` placements.
  - Inferred `Mate` relationships from interface tags (e.g., motor mount → arm tube concentric + coincident).
- Delegates transpilation to the existing `transpile_assembly` in `ai_cad/assembly.py`.

### 5. Validation

- Structural validation via `FeatureTree.validate_tree()`.
- Per-part validation via existing transpile/execute loop.
- New simple assembly-level checks:
  - No duplicate instance IDs.
  - Every instance references an existing `part_id`.
  - Mate entities reference existing instances.
- Collision/intersection check is explicitly **deferred to Phase 19** (`PLAN.md` line 686). Phase 18 only verifies that the composed assembly transpiles and executes.

### 6. Backend integration

`web/backend/main.py`:
- Add `decompose: bool = True` to `GenerateRequest`.
- In `POST /generate`, if `detect_domain` and decomposition conditions are met, call the composer instead of the single-part feature-tree path.
- Persist `decomposition.json` alongside `domain_intent.json` and `feature_tree.json`.
- New endpoint `POST /decompose` returns the decomposition plan without generating geometry (useful for UI preview).

### 7. Frontend integration

`web/frontend/src/`:
- Add a `DecomposePanel.jsx` that shows the decomposition plan (sub-parts, domains, families, parameters) when a system prompt is processed.
- Add a “Auto-decompose system prompts” toggle in `PromptInput.jsx` (default on when detect-domain is on).
- Extend `api.js` with `decomposePrompt(prompt)` and pass `decompose` to `generateDesign`.

### 8. Tests

New test files:

- `tests/test_decomposition.py` — deterministic rule-based decomposition for quadcopter, robot arm, drone, heat-sink + bracket.
- `tests/test_part_families.py` — registry contents, default parameter merging, feature-tree snippet validity.
- `tests/test_composer.py` — compose a 2-part assembly from a decomposition result and validate it.
- `tests/test_web_backend.py` (extend) — `/decompose` endpoint, `/generate` with `decompose=True`.

Target: **at least 210 passing tests** (201 current + ~9 new).

### 9. Documentation

- Update `PLAN.md` status line to Phase 18 in progress.
- Add `docs/decomposition.md` with the decomposition format and part-family registry.
- Update `memory.md` phase table and test count on completion.
- Update `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/progress.md` to mark Phase 18 started.

## Out of scope for Phase 18

- Full kinematic-loop solver (Phase 19).
- Assembly-level collision detection (Phase 19).
- CFD/thermal solver integration (Phase 20).
- Full electronics EDA integration (Phase 21).
- Voice / STT integration (deferred post-Batch A).

## Implementation order

1. `ai_cad/part_families.py` — registry + default snippets.
2. `ai_cad/decomposition.py` — rule + LLM decomposition.
3. `ai_cad/composer.py` — compose decomposition into a `FeatureTree` assembly.
4. Tests for (1–3).
5. `web/backend/main.py` — `/decompose` endpoint and `decompose` flag on `/generate`.
6. Frontend `DecomposePanel.jsx`, `api.js`, `App.jsx` wiring.
7. Frontend + backend integration tests.
8. Docs and memory updates.
9. Full pytest run, commit, push.

## Open question

The recommended trigger is **automatic when multi-domain/system noun detected, with a `decompose=False` opt-out**. Does this match the user experience you want, or would you prefer decomposition to be an explicit checkbox in the prompt UI?
