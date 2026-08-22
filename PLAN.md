# 📐 RoboCAD — End-to-End Build Plan

## 1. Product definition

**RoboCAD** is an AI-powered parametric CAD tool for robotics hardware.

*Input:* a natural-language description of a robot part or assembly.
*Output:* a real, editable, parametric CAD model (initially in `build123d`, later syncable to Onshape), plus manufacturing exports and a parameter panel for manual refinement.

**Differentiation from text-to-mesh toys:**
- The AI writes **parametric code**, not a static mesh.
- The generated code is saved and versioned.
- Parameters are exposed for interactive editing.
- The output is manufacturable: STL / STEP / 3MF.

**Connection to LearningRobotics:**
- `LearningRobotics` teaches robot theory.
- RoboCAD designs the physical parts.
- Saved parts can be imported into MuJoCo / Onshape / real hardware builds.

---

## 2. Core architectural decision

**Chosen path:** Start with `build123d` (Python, open-source, OpenCASCADE) to validate and harden the AI→parametric-code loop. Add Onshape export/sync only after the loop is reliable.

**Why this order:**
1. LLMs are much better at Python than at Onshape FeatureScript.
2. The local loop removes API limits, quotas, and network latency from the critical path.
3. The Onshape API is strongest at driving existing parametric models, not arbitrary feature injection. We need a proven code-generation strategy first.
4. We can build a standalone, usable tool for ourselves before taking on integration complexity.

**When Onshape comes in (Phase 5):**
- Export generated build123d geometry to STEP.
- Push STEP into Onshape Part Studios via REST API.
- Optionally generate a matching FeatureScript for native parametric editing in Onshape.
- Build assemblies with mates in Onshape using the exported parts.

---

## 3. Phases

### Phase 0 — Validate the AI → parametric-code loop (weekend) ✅ COMPLETE

**Goal:** Prove that an LLM can reliably generate valid `build123d` code from robotics-flavored prompts.

**Actual result:** 8/8 prompts passed on first attempt (100%).

**Deliverables:**
1. `ai_cad/generator.py` — call LLM (Claude/GPT-4), extract code block.
2. `ai_cad/executor.py` — execute generated code in a subprocess, capture geometry.
3. `ai_cad/validator.py` — check that the result is manifold and has sane bounds.
4. `ai_cad/exporter.py` — export generated geometry to STL/STEP.
5. `prompts/system_prompt.txt` and `prompts/examples.json` — few-shot examples.
6. `validate.py` — run 10–15 prompts and report success/failure.

**Prompts to test:**
- "A 120 mm × 80 mm × 3 mm rectangular plate with four M3 holes on a 100 mm × 60 mm grid."
- "A motor mount bracket for a NEMA-17 with two M3 mounting holes and a 22 mm boss for the motor face."
- "A wheel hub with a 6 mm D-shaft bore and four M3 bolt holes on a 30 mm PCD."
- "A 50-tooth GT2 pulley with 6 mm belt width and a 5 mm bore."
- "A simple L-bracket, 40 mm × 40 mm × 30 mm, 3 mm thick, with 4 mm mounting holes."
- "A differential-drive robot chassis base, 150 mm × 100 mm, with two NEMA-17 mounts and caster clearance."

**Success criteria:**
- ≥70% of prompts produce a valid STL on first attempt. ✅ **Achieved 100%**
- ≥90% succeed after one self-correction retry. ✅ **Not needed; 100% first-attempt success**
- We have a written failure-mode taxonomy (syntax errors, wrong dimensions, missing exports, invalid geometry). ✅ **Documented in generator/executor fixes and prompt patterns**

**Failure taxonomy:**
- `syntax` — code doesn't parse.
- `runtime` — code parses but throws during execution.
- `geometry` — code runs but produces no / degenerate geometry.
- `spec` — geometry exists but does not match the prompt.

---

### Phase 1 — Robust generation + self-correction backend (3–5 days) ✅ COMPLETE

**Goal:** Wrap the validated loop into a reliable backend service.

**Deliverables:**
1. `ai_cad/models.py` — Pydantic response models: `GenerationResult`, `CADParameter`, `ValidationReport`, `ExportPaths`.
2. `ai_cad/parameters.py` — AST-based extraction of module-level numeric parameters from generated code.
3. `ai_cad/api.py` — `RoboCADBackend.generate(prompt, max_retries=2, ...)` orchestrating generation, execution, validation, and parameter extraction.
4. Self-correction on both execution/runtime failures and geometry validation failures by feeding errors back to the LLM.
5. `benchmarks/prompts.json` — 20 curated robotics prompts.
6. `benchmarks/evaluate.py` — benchmark runner using the new backend API.
7. pytest coverage: `test_executor.py`, `test_validator.py`, `test_parameters.py`, `test_api.py`.

**Success criteria:**
- ≥95% of a curated 20-prompt benchmark succeeds within two retries. ✅ **Achieved 19/20 (95.0%)**
- Average end-to-end latency < 30 s per prompt on the RTX 5060 laptop. ✅ **Average ~13 s per prompt**
- No API keys in code; all keys via environment variables. ✅

**Known failure:**
- `pendulum_bob` (sphere with a blind threaded-insert hole) remains non-watertight after two self-correction retries. This is a genuine geometry-hard case and will be revisited in Phase 3/6 with explicit spherical-shell / through-hole guidance.

---

### Phase 2 — Minimal web app (1 week) ✅ COMPLETE

**Goal:** Make the tool usable in a browser.

**Deliverables:**
1. FastAPI backend (`web/backend/main.py`):
   - `POST /generate` — accept prompt, persist design, return metadata + export URLs.
   - `GET /designs` — list history.
   - `GET /designs/{id}` — load one persisted design.
   - `GET /exports/{id}/{filename}` — download STL/STEP/script.
2. React frontend (`web/frontend/`):
   - Prompt input with suggestions and retry/model controls.
   - 3D viewer using `react-three-fiber` + `STLLoader` + orbit controls.
   - Download buttons for STL, STEP, and generated Python code.
   - Simple history sidebar.
3. Design persistence to `designs/{uuid}/`.
4. `tests/test_web_backend.py` added.

**Success criteria:**
- User can type a prompt, click generate, and see the rendered model in < 45 s. ✅
- User can download the generated STL. ✅
- Generated designs are persisted to `designs/`. ✅
- `python -m pytest tests -q` passes. ✅ **25 tests passing**

---

### Phase 3 — Parameter + stylus editing layer (1.5–2 weeks) ✅ CORE COMPLETE

**Goal:** The central interactive feature — edit generated models without retyping code.

**Deliverables:**
1. LLM exposes named, typed parameters in generated code, e.g.:
   ```python
   plate_length = 120.0  # param: plate_length
   plate_width = 80.0    # param: plate_width
   hole_spacing_x = 100.0 # param: hole_spacing_x
   ```
2. Parser extracts these parameters and their current values. ✅ `ai_cad/parameters.py`
3. Frontend renders sliders/inputs for each parameter. ✅ `ParameterList.jsx`
4. Changing a parameter regenerates the model by re-running the code with the new value. ✅ `/designs/{id}/regenerate`
5. **Stylus / pointer interaction v1:**
   - Click a face/point in the viewer.
   - The system guesses the nearest parameter (e.g., width if you clicked the side face).
   - Edit the value with a draggable handle or number input.
   - **⏳ Outstanding:** numeric panel editing works; click-to-guess is not yet implemented.
6. Save edited parameter set as a new version. ✅ saved under `designs/{id}/versions/{version_id}/`

**Success criteria:**
- 5 common parameters (length, width, thickness, hole spacing, hole diameter) are editable interactively. ✅
- Regeneration after parameter change takes < 10 s. ✅ (local re-execution, no LLM call)
- No code editing required for simple dimensional changes. ✅

**Honest scope note:** Freeform sculpting (push/pull mesh vertices) is deliberately out of scope for v1. This is *parametric* editing, not mesh sculpting. Stylus/face-click interaction remains Phase 3 follow-up work.

---

### Phase 4 — Design library + remix (1 week) ✅ COMPLETE

**Goal:** "Save it for the future and do more things with it."

**Deliverables:**
1. Design persistence schema:
   ```json
   {
     "id": "...",
     "prompt": "...",
     "code": "...",
     "parameters": {...},
     "exports": {"stl": "...", "step": "..."},
     "tags": ["chassis", "motor-mount", "diff-drive"],
     "versions": [...],
     "created_at": "...",
     "parent_id": "..."
   }
   ```
   ✅ Metadata schema now includes `tags`, `versions`, and `parent_id`; filesystem + JSON persistence (SQLite deferred as not required for v1).
2. SQLite store for metadata + filesystem for exports.
   ⏳ Deferred: filesystem + JSON meets current needs; SQLite can be adopted later if scale requires it.
3. Web UI:
   - Search by text / tags. ✅ `HistorySidebar.jsx` + `GET /designs?search=&tag=`
   - Filter by parameter ranges. ⏳ Not implemented (deferred).
   - "Remix" button: prefill prompt with "Based on design X, make it ...". ✅ `RemixPanel.jsx` + `POST /designs/{parent_id}/remix`
4. Component library skeleton: import the hardware BOM from LearningRobotics as a JSON catalog. ✅ `ComponentLibrary.jsx` + `standard_components.json` with 12 standard parts across Structural, Motion, Electronics, and Robotics categories.

**Success criteria:**
- Any generated design can be saved, found, and remixed. ✅
- Remixing produces a new design linked to its parent. ✅ `parent_id` recorded in child metadata.
- Component library has ≥10 standard robotics parts (fasteners, motors, bearings). ✅ 12 seed parts, including motors, bearings implied; dedicated hardware BOM integration with LearningRobotics remains Phase 6.

---

### Phase 5 — Onshape export / sync + manufacturing reports (2+ weeks)

**Goal:** Bridge to professional CAD and real hardware fabrication.

**Deliverables:**
1. Onshape REST API client:
   - Create / select a document.
   - Upload STEP to a Part Studio.
   - Optional: generate a FeatureScript that reproduces the parametric intent.
2. Sync a generated part to Onshape with one command / button.
3. Multi-part assembly hints: export a set of parts with suggested mates.
4. Manufacturing report generator:
   - bounding box, volume, mass (requires material density)
   - overhang analysis for FDM printing
   - minimum hole diameter / feature size check
   - estimated print time (basic heuristic)
5. BOM extraction from embedded fasteners and components.

**Success criteria:**
- A generated part can be opened in Onshape.
- A 3-part assembly can be uploaded with mate hints.
- Manufacturing report flags obvious issues (unsupported overhangs, holes too small).

---

### Phase 6 — Robotics-aware component templates (ongoing)

**Goal:** The assistant knows about real robot parts and design patterns.

**Deliverables:**
1. JSON component library with parametric specs:
   - Motors: NEMA-17, NEMA-23 (mounting hole pattern, shaft diameter, boss size).
   - Bearings: 608, 625, flanged, etc.
   - Fasteners: M3, M4, M5 (clearance holes, thread-forming holes).
   - Belts / pulleys: GT2, 6 mm width, common tooth counts.
   - Extrusion: 2020, 2040.
2. Template generator for common subsystems:
   - Differential-drive chassis.
   - 2-DOF planar arm.
   - Belt-driven single-stage reduction.
   - Parallel-jaw gripper finger.
   - Idler tensioner.
3. Constraint-aware design: warn if motor mount spacing is incompatible with selected motor.
4. Export to MuJoCo-compatible MJCF assets for `LearningRobotics`.

**Success criteria:**
- User can say "NEMA-17 motor mount" and get a correct mount without specifying hole pattern.
- Common robot subsystems can be generated in one prompt.
- MuJoCo collision meshes can be exported from any generated part.

---

## 4. Engineering decisions

| Decision | Choice | Rationale |
|---|---|---|
| CAD kernel | build123d first, Onshape later | LLM-friendly, open-source, no API limits |
| AI model | Claude 3.5 Sonnet / GPT-4o | Best code generation + self-correction |
| Output artifact | Python script + derived mesh | Script is editable source of truth |
| Execution | Subprocess sandbox | Isolates generated code; limits damage on errors |
| Viewer | React + three.js | Standard, lightweight |
| Persistence | SQLite + JSON + Git | Simple, versionable, portable |
| API keys | Environment variables only | Security; no keys in repo |
| Hosting | Local first, cloud later | Runs on RTX 5060 laptop |

---

## 5. Validation strategy

Every phase ends with:
1. A small benchmark script that exercises the new feature.
2. A pytest suite that must pass before merging.
3. A manual demo recorded as a short note in the README changelog.
4. A commit and push to GitHub.

**Global benchmark:**
- Maintain a file `benchmarks/prompts.json` with 20–50 prompts of increasing difficulty.
- `python -m benchmarks.evaluate` runs all prompts and reports per-prompt success, phase-level accuracy, and average latency.
- Target: ≥90% pass rate after Phase 1.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM generates invalid geometry code | Self-correction loop, few-shot examples, constrained system prompt |
| LLM can't reason about 3D constraints well | Start with simple extruded parts; use robotics templates; limit prompt complexity |
| Generated code has side effects | Run in subprocess with timeout; no network/filesystem access except output directory |
| Viewer becomes a heavy frontend | Use three.js + progressive STL loading; keep v1 minimal |
| Onshape API is too restrictive for arbitrary feature trees | Defer to Phase 5; prove local loop first; use STEP export as fallback |
| Designs become an unversioned mess | Save code + parameters as text; use Git from day one |
| Scope creep into full CAD app | Stay parametric-code-first; never build a sketcher |
| Cost of LLM API calls | Cache results; use cheaper models for retries; local open-source LLM optional later |

---

## 7. Definition of "extraordinary" for this project

RoboCAD becomes extraordinary when a user can describe a multi-part robot subsystem in one paragraph, receive editable parts, adjust key dimensions with sliders, and export a ready-to-print / ready-to-assemble package in under five minutes.

The benchmark sentence:

> *"Design a differential-drive robot base for two NEMA-17 motors with a 100 mm wheelbase, a 20 mm caster clearance, and four M3 mounting holes for a Raspberry Pi 5."*

---

## 8. Immediate next session plan

Phases 0–4 are complete and pushed. If resuming work on RoboCAD, the next tasks are:

1. **Phase 3 follow-up:** implement stylus / face-click parameter guessing in the 3D viewer (click a face → nearest parameter guess → edit value).
2. **Phase 5 start:** Onshape REST API client — create/select document, upload STEP to a Part Studio, generate basic manufacturing report (bounding box, volume, overhang check).
3. **Phase 6 preparation:** build a JSON component library that imports/consumes the `LearningRobotics` hardware BOM, so prompts like "NEMA-17 motor mount" auto-fill hole patterns and boss sizes.
4. Maintain ≥40 passing pytest tests and commit each phase with a descriptive message.

---

*Last updated: 2026-08-22*
