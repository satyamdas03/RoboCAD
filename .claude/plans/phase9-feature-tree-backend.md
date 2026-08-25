# Phase 9 Plan — Feature-Tree Backend

## Goal
Replace the monolithic `code.py` artifact with a structured, versioned, editable feature tree that transpiles to `build123d`, while keeping `code.py` as a fallback.

## Current state
- Pipeline: `prompt → code.py → execute → STL/STEP`
- Parameters are extracted from code via AST and edited by regex replacement.
- Phase 8 approved schema: `docs/feature_tree_schema.md` v1.0.0.
- Phase 8 baseline: 86.7% pass rate on code-only generation.

## Proposed architecture

```text
prompt
  ↓
[LLM path A] generate code.py (existing, reliable)
  ↓
[optional LLM path B] generate feature_tree.json
  ↓
transpiler → build123d code
  ↓
executor → STL/STEP
  ↓
feature_store persists tree + code + exports side-by-side
```

For Phase 9, the feature tree is a **first-class sidecar**, not a replacement. The existing code path remains the default. A new `generate_feature_tree()` path asks the LLM to emit a feature tree JSON, transpiles it, validates it, and uses it when successful. If it fails, we fall back to code.py. This protects the 86.7% baseline while building the new infrastructure.

## Files to create / modify

### New files
1. `ai_cad/feature_tree.py` — Pydantic models for `FeatureTree`, `Part`, `Sketch`, `Feature`, `Parameter`, `Constraint`, `Dimension`, `CoordinateSystem`.
2. `ai_cad/transpiler.py` — Walk a feature tree and emit build123d Python code.
3. `ai_cad/feature_store.py` — Save/load feature trees to `designs/{id}/feature_tree.json`; version management.
4. `web/frontend/src/components/FeatureTreePanel.jsx` — Read-only tree viewer (parts → sketches → features).
5. `web/frontend/src/components/FeatureParameterEdit.jsx` — Edit a parameter in the feature tree and regenerate.
6. `tests/test_feature_tree.py` — Model validation and transpiler tests.
7. `tests/test_transpiler.py` — STL equivalence tests against canonical designs.
8. `tests/test_feature_store.py` — Persistence round-trip.

### Modified files
1. `ai_cad/models.py` — Add optional `feature_tree: FeatureTree | None` to `GenerationResult`.
2. `ai_cad/api.py` — Add `generate_feature_tree()` method; optionally call it inside `generate()` when a flag is enabled; persist the tree via `FeatureStore`.
3. `ai_cad/generator.py` — Add `generate_feature_tree(prompt, ...)` LLM call that returns JSON using the schema as system prompt.
4. `web/backend/main.py` — Add endpoints:
   - `GET /designs/{id}/feature-tree`
   - `POST /designs/{id}/regenerate-from-feature-tree`
   - update `GenerateResponse` to include `feature_tree`
5. `web/frontend/src/api.js` — Add `loadFeatureTree(id)`, `regenerateFromFeatureTree(id, updates)`.
6. `web/frontend/src/App.jsx` — Render `FeatureTreePanel` in the inspector when a feature tree exists.
7. `README.md` / `PLAN.md` / memory — Mark Phase 9 complete after implementation and tests pass.

## Scope for Phase 9

**In scope:**
- Single-part designs only.
- Parameter table, coordinate systems, sketches on XY/YZ/ZX planes.
- Sketch entities: rectangle, circle, line, arc.
- Features: extrude (add/subtract), revolve, fillet, chamfer, shell, mirror, linear_pattern, circular_pattern.
- Feature-tree persistence and versioning.
- Transpiler validation and STL equivalence for at least the canonical base plate.
- Optional LLM feature-tree generation with fallback to code.

**Out of scope (Phases 10–11):**
- 2D constraint solver (constraints stored but not solved; dimensions drive coordinates directly).
- Assemblies and mates.
- Face/edge selectors beyond `all`, `feature_edges`, `last_feature`.
- Sketch on offset/face planes beyond semantic `top`/`bottom`.

## LLM prompt strategy

`generate_feature_tree` will use a system prompt that contains:
1. The feature-tree schema summary.
2. A canonical base-plate example.
3. Strict instructions: emit only a JSON block matching the schema, then the transpiler handles build123d.

Self-correction will feed transpiler/executor errors back to the LLM to fix the JSON. `max_retries=2`.

## Acceptance criteria

1. `tests/test_transpiler.py` proves the feature-tree path produces an STL identical (within mesh tolerance) to the existing code.py path for the canonical base plate.
2. Editing a parameter through the feature-tree path regenerates only affected downstream features (verified by comparing execution time or by inspecting the regenerated tree).
3. `tests/test_feature_tree.py` and `tests/test_feature_store.py` pass.
4. Full `pytest` suite still has only the pre-existing `test_generate_missing_api_key` quirk; no new failures.
5. Frontend renders the feature tree in the inspector panel for designs that have one.
6. README/PLAN/memory updated; all changes committed and pushed.

## Implementation order

1. `ai_cad/feature_tree.py` — data models.
2. `ai_cad/transpiler.py` — base plate transpiler proof of concept.
3. `ai_cad/feature_store.py` — persistence.
4. Tests: transpiler equivalence, persistence round-trip.
5. `ai_cad/generator.py` — `generate_feature_tree()`.
6. `ai_cad/api.py` — integrate optional feature-tree generation.
7. `web/backend/main.py` — new endpoints and persistence.
8. Frontend: `FeatureTreePanel.jsx`, `FeatureParameterEdit.jsx`, `api.js`, `App.jsx`.
9. Run full test suite, update docs/memory, commit/push.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM feature-tree pass rate is low | Keep code.py as default; feature tree is optional sidecar. |
| Transpiler cannot express some generated patterns | Transpiler starts simple; unsupported features fall back to code.py. |
| Frontend becomes cluttered | Feature tree panel only appears when tree exists; read-only v1. |
| Persistence schema changes | Feature tree is sidecar; metadata.json unchanged except optional `feature_tree_path`. |

## Success by end of Phase 9

- A user can generate a base plate and see its feature tree in the UI.
- A user can edit `plate_length` in the feature tree and get a regenerated STL.
- The feature tree path and code.py path produce the same base-plate STL.
- All new tests pass and the repo is committed/pushed.
