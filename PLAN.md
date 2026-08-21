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

### Phase 0 — Validate the AI → parametric-code loop (weekend)

**Goal:** Prove that an LLM can reliably generate valid `build123d` code from robotics-flavored prompts.

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
- ≥70% of prompts produce a valid STL on first attempt.
- ≥90% succeed after one self-correction retry.
- We have a written failure-mode taxonomy (syntax errors, wrong dimensions, missing exports, invalid geometry).

**Failure taxonomy:**
- `syntax` — code doesn't parse.
- `runtime` — code parses but throws during execution.
- `geometry` — code runs but produces no / degenerate geometry.
- `spec` — geometry exists but does not match the prompt.

---

### Phase 1 — Robust generation + self-correction backend (3–5 days)

**Goal:** Wrap the validated loop into a reliable backend service.

**Deliverables:**
1. `generate(prompt, retry=3, model=...)` function.
2. Self-correction: on error, send the traceback + partial code back to the LLM, ask for a fix, retry.
3. Structured output: return a Pydantic object containing:
   - generated code
   - named parameters and their default values
   - export file paths (STL, STEP)
   - a short human-readable explanation
   - build status / error log
4. `ai_cad/prompts/system_prompt.txt` refined based on Phase 0 failures.
5. Add more few-shot examples for the common failure modes.
6. Unit tests for generator + executor.

**Success criteria:**
- ≥95% of a curated 20-prompt benchmark succeeds within two retries.
- Average end-to-end latency < 30 s per prompt on the RTX 5060 laptop.
- No API keys in code; all keys via environment variables.

---

### Phase 2 — Minimal web app (1 week)

**Goal:** Make the tool usable in a browser.

**Deliverables:**
1. FastAPI backend:
   - `POST /generate` — accept prompt, return model URLs + metadata.
   - `GET /models/{id}` — download STL/STEP.
   - `GET /designs` — list history.
2. React frontend:
   - Prompt input.
   - 3D viewer using `react-three-fiber` with STL loading.
   - Download buttons.
   - Simple history sidebar.
3. Keep the UI intentionally minimal and ugly. The round trip is what matters.

**Success criteria:**
- User can type a prompt, click generate, and see the rendered model in < 45 s.
- User can download the generated STL.
- Generated designs are persisted to `designs/`.

---

### Phase 3 — Parameter + stylus editing layer (1.5–2 weeks)

**Goal:** The central interactive feature — edit generated models without retyping code.

**Deliverables:**
1. LLM exposes named, typed parameters in generated code, e.g.:
   ```python
   plate_length = 120.0  # param: plate_length
   plate_width = 80.0    # param: plate_width
   hole_spacing_x = 100.0 # param: hole_spacing_x
   ```
2. Parser extracts these parameters and their current values.
3. Frontend renders sliders/inputs for each parameter.
4. Changing a parameter regenerates the model by re-running the code with the new value.
5. **Stylus / pointer interaction v1:**
   - Click a face/point in the viewer.
   - The system guesses the nearest parameter (e.g., width if you clicked the side face).
   - Edit the value with a draggable handle or number input.
6. Save edited parameter set as a new version.

**Success criteria:**
- 5 common parameters (length, width, thickness, hole spacing, hole diameter) are editable interactively.
- Regeneration after parameter change takes < 10 s.
- No code editing required for simple dimensional changes.

**Honest scope note:** Freeform sculpting (push/pull mesh vertices) is deliberately out of scope for v1. This is *parametric* editing, not mesh sculpting.

---

### Phase 4 — Design library + remix (1 week)

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
     "created_at": "..."
   }
   ```
2. SQLite store for metadata + filesystem for exports.
3. Web UI:
   - Search by text / tags.
   - Filter by parameter ranges.
   - "Remix" button: prefill prompt with "Based on design X, make it ...".
4. Component library skeleton: import the hardware BOM from LearningRobotics as a JSON catalog.

**Success criteria:**
- Any generated design can be saved, found, and remixed.
- Remixing produces a new design linked to its parent.
- Component library has ≥10 standard robotics parts (fasteners, motors, bearings).

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

If resuming work on RoboCAD, the next tasks are:

1. Run `python validate.py` and log results in `phase0_results.md`.
2. Categorize failures using the taxonomy in Phase 0.
3. Update `prompts/system_prompt.txt` and `prompts/examples.json` based on failures.
4. Repeat until ≥90% pass rate.
5. Commit progress with message: `robocad: Phase 0 validation, X/Y prompts pass`.
6. Update this `PLAN.md` and `README.md` with Phase 0 results.

---

*Last updated: 2026-08-21*
