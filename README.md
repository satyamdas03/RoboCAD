# 🤖 RoboCAD — AI-Powered Parametric CAD for Robotics

> **Mission:** Let robotics builders design real, editable, manufacturable hardware parts by describing them in plain language — no months of sketch-extrude-mate training required.
>
> **Core bet:** The AI writes **parametric CAD code** (build123d / FeatureScript), not throwaway meshes. The model you get is editable, versionable, and exportable for 3D printing, machining, or Onshape.
>
> **Latest milestone:** Phase 5 Onshape export/sync + manufacturing reports and Phase 6 robotics-aware component templates complete. End-to-end web app supports prompt-to-CAD, parameter editing, design library/remix, manufacturability analysis, and one-click STEP upload to Onshape. **57 passing tests**.

---

## 🧑‍💻 Author

**Satyam Das** — CS grad, quant/AI engineer, aspiring roboticist.

* GitHub: [@satyamdas03](https://github.com/satyamdas03)
* Sister project: [LearningRobotics](https://github.com/satyamdas03/LearningRobotics) — where the theory behind these parts is learned chapter by chapter.
* Motto: *"Think in systems, design in language, build in hardware."*

---

## 🔗 Why this exists / connection to LearningRobotics

`LearningRobotics` is a public learning journal that walks through robotics fundamentals — C-space, rigid-body motions, kinematics, dynamics, and eventually control + RL. The natural next step after *understanding* a robot is to *build* it. But professional CAD has a steep activation energy: weeks of UI muscle memory before you can express a simple idea like:

> *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid and two NEMA-17 motor mounts."*

RoboCAD closes that gap. It lets me (and anyone else) operate at the level of intent, not clicks. Designs produced here can be:

1. Printed or machined directly (STL / STEP / 3MF export).
2. Synced to Onshape later for professional assemblies and mates (Phase 5).
3. Reused as parts in `LearningRobotics` simulations and hardware builds.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts.**

---

## ✨ What makes this different

| Tool category | Examples | Output | Editable? | Manufacturable? |
|---|---|---|---|---|
| Text-to-mesh | Meshy, Shap-E | mesh (STL-like) | ❌ no | ⚠️ limited |
| Text-to-SDF/voxel | research demos | implicit field | ❌ no | ❌ no |
| Parametric template filling | Onshape configs | existing parametric model | ✅ yes | ✅ yes |
| **RoboCAD (this repo)** | **LLM → build123d code → feature tree** | **parametric CAD script** | **✅ yes** | **✅ yes** |

The key insight: **CAD is code.** Modern parametric kernels (OpenCASCADE via build123d/CADQuery, Onshape's FeatureScript) are programming environments. LLMs are already excellent at code generation. RoboCAD turns hardware design into a code-generation + execution problem, which is exactly the right shape for an AI researcher.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User layer                                                 │
│  • natural-language prompt                                  │
│  • parameter sliders / stylus reference points              │
│  • design history + remix                                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  AI orchestrator (Claude / GPT-4 + structured output)       │
│  • intent parsing (chassis, bracket, gripper, pulley...)    │
│  • emits parametric build123d / FeatureScript code          │
│  • self-corrects on execution / validation failures         │
│  • explains what it built and why                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  CAD execution engine                                       │
│  • build123d / CADQuery (local, Phase 0–4)                │
│  • optional Onshape REST API + FeatureScript (Phase 5)    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Geometry validation layer                                  │
│  • build success / traceback capture                        │
│  • watertight / manifold check (manifold3d / trimesh)       │
│  • bounding-box, mass, CoM sanity                            │
│  • manufacturability hints (overhangs, fastener clearances) │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Viewer + edit layer                                        │
│  • web-based 3D viewer (three.js / react-three-fiber)       │
│  • expose named parameters from generated code              │
│  • point-and-type dimension editing (v1)                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence + reuse                                          │
│  • design = {prompt, code, parameters, exports, versions}   │
│  • searchable library                                         │
│  • remix: old design becomes seed for new prompt              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech stack

| Layer | Technology | Rationale |
|---|---|---|
| CAD kernel | **build123d** | Clean Python API on OpenCASCADE; LLMs write it well; open-source |
| Mesh validation | `trimesh`, `manifold3d` | Watertight checks, mass properties |
| AI model | Claude / GPT-4 via API | Best-in-class code generation and self-correction |
| Backend (Phase 2+) | FastAPI | Python-native, easy to invoke build123d |
| Frontend (Phase 2+) | React + three.js / react-three-fiber | Standard web 3D viewer |
| Storage | SQLite + JSON files + Git | Simple, versioned, portable |
| Export formats | STL, STEP, 3MF | 3D printing + machining + Onshape |
| Onshape sync (Phase 5) | Onshape REST API + FeatureScript | Professional assemblies and mates |

---

## 🚀 Current phase

| Phase | Goal | Status |
|---|---|---|
| **0** | Validate the AI → parametric-code loop in Python | ✅ **Complete — 8/8 prompts pass** |
| **1** | Robust generation + self-correction backend | ✅ **Complete — 19/20 prompts pass (95%)** |
| **2** | Minimal web app (prompt + viewer + export) | ✅ **Complete — FastAPI + React + three.js viewer + persistence** |
| **3** | Parameter / stylus editing layer | ✅ **Complete — editable parameter panel + face-click parameter guessing + versioned regeneration** |
| **4** | Design library + remix | ✅ **Complete — component catalog, search/filter, tags, remix with parent linking** |
| **5** | Onshape export / sync + manufacturing reports | ✅ **Complete — HMAC-signed Onshape API client, STEP upload, manufacturability report (volume, overhangs, hole diameter, print-time heuristic)** |
| **6** | Robotics-aware component templates | ✅ **Complete — 12 standard robotics parts in `ComponentLibrary`, seeded prompts, tags, remix** |

See [`PLAN.md`](PLAN.md) for the complete end-to-end build plan.

---

## 🧪 Phase 0 quickstart

```bash
cd RoboCAD
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...  # Windows: $env:ANTHROPIC_API_KEY=...
python validate.py
```

`validate.py` runs a small benchmark of prompts through the AI → build123d → STL pipeline and reports which ones succeed. It is the riskiest-assumption test for the whole project.

---

## 🧪 Phase 1 quickstart — structured backend + 20-prompt benchmark

```bash
cd RoboCAD
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...  # Windows: $env:ANTHROPIC_API_KEY=...
export ROBOCAD_MODEL=qwen3-coder:latest  # optional; defaults to Claude

# Run the pytest suite
python -m pytest tests -q

# Run the 20-prompt Phase 1 benchmark
python benchmarks/evaluate.py
```

## 🌐 Phase 2 quickstart — web app

```bash
cd RoboCAD

# 1. Start the FastAPI backend
.venv\Scripts\Activate.ps1  # or: source .venv/bin/activate
$env:ANTHROPIC_API_KEY=...   # or: export ANTHROPIC_API_KEY=...
$env:ROBOCAD_MODEL="qwen3-coder:latest"  # optional: use local Ollama model
# Optional Onshape credentials for Phase 5 upload:
$env:ONSHAPE_ACCESS_KEY=...   # or ONSHAPE_API_KEY
$env:ONSHAPE_SECRET_KEY=...   # or ONSHAPE_API_SECRET
python -m uvicorn web.backend.main:app --reload --port 8000

# 2. In a second terminal, start the React frontend
cd web/frontend
npm install
npm run dev

# 3. Open http://localhost:5173
```

The web app lets you type a prompt, click **Generate**, and view the resulting STL in a `react-three-fiber` viewer. Every successful (and failed) generation is persisted under `designs/{uuid}/` with `prompt.txt`, `code.py`, `parameters.json`, `metadata.json`, and `exports/`.

`ai_cad.api.generate()` returns a structured `GenerationResult` with:
- `code` — the generated build123d script,
- `parameters` — editable named numeric parameters extracted from the code,
- `exports` — paths to STEP + STL files,
- `validation` — watertight/manifold/bounds report,
- `attempts_used` — how many LLM calls were needed.

---

## 🧱 Repository layout

```
RoboCAD/
├── README.md                 # This file — project overview + changelog
├── PLAN.md                   # Detailed build plan
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core AI-CAD package
│   ├── __init__.py           # Public exports
│   ├── prompts/
│   │   ├── system_prompt.txt # LLM system prompt
│   │   └── examples.json     # Few-shot build123d examples
│   ├── models.py             # Pydantic response models
│   ├── api.py                # Unified RoboCADBackend.generate()
│   ├── generator.py          # prompt → code
│   ├── executor.py           # run build123d safely
│   ├── validator.py          # geometry sanity checks
│   ├── exporter.py           # STL / STEP / 3MF export
│   ├── parameters.py         # AST-based parameter extraction
│   └── guess_parameter.py    # face-normal -> parameter heuristic
├── benchmarks/               # Phase 1 curated prompt set + runner
│   ├── prompts.json          # 20 robotics prompts
│   └── evaluate.py           # python benchmarks/evaluate.py
├── web/                      # Phase 2 FastAPI + React app
│   ├── backend/
│   │   ├── main.py           # FastAPI endpoints
│   │   └── __init__.py
│   └── frontend/             # Vite + React + react-three-fiber
│       ├── src/
│       │   ├── App.jsx
│       │   ├── api.js
│       │   └── components/
│       ├── index.html
│       ├── package.json
│       └── vite.config.js
├── components/               # (Phase 6) robotics part library
├── designs/                  # persisted generated designs (created at runtime)
└── tests/                    # pytest suite
```

---

## 🧠 Design principles

1. **Parametric code is the source of truth.** The prompt and generated script are saved; the mesh is a derived artifact.
2. **Fail visibly and correct.** Every generated script is executed; tracebacks are fed back to the LLM for self-repair.
3. **No mesh dead-ends.** Always produce an editable model, even if simple.
4. **Start local, integrate later.** Prove the loop with build123d before wrestling with Onshape API limits.
5. **Document every push.** The README is a living project log; each commit syncs the current phase and decisions.

---

## 🗺️ Roadmap to "extraordinary"

The long-term vision is not a chatbot that draws shapes. It is a **robotics design companion** that understands:

- Standard robot components (NEMA-17/23, bearings, belts, pulleys, fasteners).
- Kinematic constraints (motor shaft spacing, pulley ratios, link lengths).
- Manufacturability (print orientation, tolerance, material).
- Assembly intent (mates, constraints, BOM).

A user should eventually be able to say:

> *"Design a 2-DOF robot arm: shoulder NEMA-17, elbow NEMA-17, 200 mm link, belt drive, base mountable on 2040 aluminum extrusion."*

and receive a folder of editable parts ready for printing, assembly in Onshape, and simulation export to `LearningRobotics` / MuJoCo.

---

## 🤝 Relationship to other work

* **LearningRobotics** ([repo](https://github.com/satyamdas03/LearningRobotics)) — theory, kinematics, dynamics, and the PIBench physical-intuition benchmark. RoboCAD designs parts that can be loaded there.
* **PIBench** — physical common-sense benchmark. RoboCAD could generate the 3D assets for new PIBench scenes from prompts.
* **Hardware BOM** from LearningRobotics — will be imported as the component library so RoboCAD designs are cost-aware.

---

## 📝 Changelog

### 2026-08-22 — Phase 5 complete: Onshape export/sync + manufacturing reports

* Added `ai_cad/onshape.py` Onshape REST API client with HMAC-SHA256 API-key authentication, exact signing matching the official Python client:
  * `list_documents`, `create_document`, `upload_step`, and `upload_step_to_new_document`.
  * Free Onshape accounts require public documents; `create_document` sets `isPublic: True` and reports the 409 limitation clearly.
* Added `ai_cad/manufacturing.py` manufacturability analyzer:
  * Bounding box, volume, surface area, estimated FDM print time heuristic.
  * Overhang detection with build-plate filtering.
  * Hole-diameter estimation via horizontal cross-sections (area-equivalent circle).
* Extended Pydantic models in `ai_cad/models.py` with `ManufacturingReport` and `GenerationResult.manufacturing`.
* Added backend endpoints:
  * `GET /onshape/documents` — list/search accessible Onshape documents.
  * `POST /designs/{id}/onshape` — upload a design's STEP to new or existing Onshape document.
  * `GET /designs/{id}/manufacturing-report` — return the manufacturability report.
* Added React components:
  * `ManufacturingReport.jsx` — live report panel with warnings.
  * `OnshapeUpload.jsx` — upload STEP to a new public document or pick an existing one.
* Extended `web/frontend/vite.config.js` with `/onshape` proxy.
* Added `tests/test_onshape.py` (mocked auth + upload tests) and `tests/test_manufacturing.py` (cube, overhang, hole detection tests).
* Full pytest suite now **57 passing tests**.

### 2026-08-22 — Phase 6 complete: robotics-aware component templates

* Added `web/frontend/src/components/standard_components.json` with 12 curated robotics parts across Structural, Motion, Electronics, and Robotics categories.
* Added `ComponentLibrary.jsx` — collapsible catalog that loads seed prompts into the generator.
* Added `TagEditor.jsx` for comma-separated tag editing and `RemixPanel.jsx` for child-design generation.
* Backend already supports `PUT /designs/{id}` tags/prompt updates, `POST /designs/{id}/remix`, and `GET /designs?search=...&tag=...`.
* Verified Phase 6 library/remix/tag flows with existing `tests/test_design_library.py` and `tests/test_code_ops.py`.

### 2026-08-22 — Phase 3 stylus complete: face-click parameter guessing in the STL viewer

* Added `ai_cad/guess_parameter.py` heuristic that maps a clicked face's dominant-axis normal and object bounding box to the most likely editable parameter.
* Added `POST /designs/{id}/guess-parameter` endpoint; falls back to measuring the STL via `trimesh` if validation bounds are missing.
* Updated `STLViewer.jsx`:
  * Raycasts on pointer down to capture `faceIndex`, world-space face normal, and triangle centroid.
  * Overlays a translucent highlight mesh on the selected triangle.
  * Shows a transient hint banner naming the guessed parameter.
* Updated `ParameterList.jsx` to scroll to, focus, and highlight the parameter row selected from a face click.
* Wired face selection through `App.jsx` so clicking a face auto-selects the matching parameter input.
* Added `tests/test_guess_parameter.py` with 7 axis-mapping tests.
* Full pytest suite now **47 passing tests**.
* Verified end-to-end with Playwright: clicking a face in the viewer focuses the `thickness` parameter and highlights its row.

### 2026-08-22 — Phase 3 + Phase 4 complete: editable parameters, design library, remix, and tags

* Added safe code-level parameter rewriting in `ai_cad/code_ops.py`:
  * `update_parameter` and `update_parameters` preserve comments and only edit module-level numeric assignments.
* Added `POST /designs/{id}/regenerate` endpoint:
  * Rewrites generated code with new parameter values, re-executes it, and persists the result under `designs/{id}/versions/{version_id}/`.
  * Updates parent metadata so the latest version is reflected in history and downloads.
* Added `PUT /designs/{id}` endpoint for updating tags and prompt text.
* Added `GET /designs?search=...&tag=...` for free-text and tag filtering.
* Added `POST /designs/{parent_id}/remix` endpoint:
  * Enriches the prompt with the original design prompt, generates a child design, and links it via `parent_id`.
* Extended design metadata schema with `parent_id` and `tags`.
* Added React components in `web/frontend/src/components/`:
  * `ParameterList` — editable number inputs per parameter with **Regenerate from parameters** button.
  * `TagEditor` — comma-separated tag editing.
  * `RemixPanel` — prompt input for generating a child based on the selected design.
  * `ComponentLibrary` — collapsible catalog seeded from `standard_components.json` with 12 standard robotics parts.
* Updated `HistorySidebar` with search box, tag filter dropdown, tag chips, and remix-of indicator.
* Added `tests/test_code_ops.py` (7 tests) and `tests/test_design_library.py` (6 tests).
* Total test suite: **40 passing tests**.

### 2026-08-22 — Phase 2 complete: minimal web app (FastAPI + React + three.js viewer) + live Ollama support

* Added local model support in `ai_cad/generator.py`:
  * Detects Ollama-style model names (e.g. `qwen3-coder:latest`, `mistral:latest`).
  * Routes those models to an OpenAI-compatible local endpoint (`http://localhost:11434/v1` by default, override with `OLLAMA_BASE_URL`).
  * Anthropic path remains for `claude-*` / `gpt-*` models; supports `ANTHROPIC_BASE_URL` override.
* Added FastAPI backend in `web/backend/main.py`:
  * `POST /generate` — prompt → `RoboCADBackend.generate()` → persisted design.
  * `GET /designs` — list generation history.
  * `GET /designs/{id}` — load a persisted design with code + parameters.
  * `GET /exports/{id}/{filename}` — serve STL / STEP / Python script files.
  * CORS enabled for the Vite dev server.
* Added React frontend in `web/frontend/` using Vite + `react-three-fiber` + `@react-three/drei`:
  * Prompt input with retry/model controls and suggestion chips.
  * Status panel showing success/failure, attempts, latency, validation summary.
  * `STLViewer` rendering generated STL with orbit controls.
  * `ParameterList` (read-only preview for Phase 3 editing).
  * Download links for STL, STEP, and generated Python code.
  * History sidebar to reload past designs.
* Added design persistence under `designs/{uuid}/`:
  * `prompt.txt`, `code.py`, `parameters.json`, `metadata.json`, `exports/model.stl`, `exports/model.step`.
* Added `tests/test_web_backend.py` covering `/health`, `/generate`, `/designs`, and `/exports`.
* Total test suite: **26 passing tests**.
* Verified live end-to-end run 2026-08-22 with `qwen3-coder:latest` via Ollama:
  * Prompt: *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid."*
  * Result: success, manifold, watertight, 6 parameters extracted, STL served through `/exports/{id}/model.stl`.

### 2026-08-22 — Phase 1 complete: robust backend + 20-prompt benchmark (19/20 = 95%)

* Added structured response models in `ai_cad/models.py` (`GenerationResult`, `CADParameter`, `ValidationReport`, `ExportPaths`).
* Added AST-based parameter extraction in `ai_cad/parameters.py` so generated dimensions can be edited later.
* Added unified `ai_cad/api.py` with `RoboCADBackend.generate()` and `generate()` convenience function.
  * Orchestrates `generate_model → execute_code → validate_model → extract_parameters`.
  * Self-corrects on both execution/runtime failures and geometry validation failures, up to `max_retries`.
* Hardened `ai_cad/executor.py` to write metadata as JSON (no stdout parsing), include `script_path` in results, and improve error capture.
* Added `benchmarks/prompts.json` with 20 curated robotics prompts and `benchmarks/evaluate.py` runner.
* Phase 1 benchmark result: **19/20 prompts passed (95.0%)** within two retries.
  * 7/8 easy, 9/9 medium, 3/3 hard.
  * Known failure: `pendulum_bob` (sphere with a blind threaded-insert hole) remains non-watertight after two self-correction retries.
* Added pytest tests: `test_executor.py`, `test_validator.py`, `test_parameters.py`, `test_api.py`.
* Total test suite: **18 passing tests**.

### 2026-08-22 — Phase 0 validation complete (8/8 pass)

* Ran `validate.py` against 8 robotics-flavored prompts; **100% produced valid STL/STEP** on first attempt.
* Fixed runtime issues discovered during validation:
  * `ai_cad/generator.py` — added Anthropic Python SDK ≥1.0 compatibility (`temperature` via `extra_body`) and `ROBOCAD_MODEL` env override.
  * `ai_cad/executor.py` — fixed f-string escaping for volume metadata in generated scripts.
  * `validate.py` — fixed error-message extraction when validation returns empty warnings.
* Rewrote `ai_cad/prompts/system_prompt.txt` and `ai_cad/prompts/examples.json` with working build123d patterns:
  * Pattern A: `Locations`/`GridLocations`/`PolarLocations` + `Cylinder(..., mode=Mode.SUBTRACT)` inside one `BuildPart`.
  * Pattern B: `BuildSketch(face)` + `Circle` + `extrude(amount=-depth, mode=Mode.SUBTRACT)` for side-face holes.
  * Pattern C: explicit solid subtraction (`part.part = part.part - bore`) for central bores.
  * Pattern D: raised bosses/mounts to avoid coplanar non-manifold geometry.
* Phase 0 success criteria exceeded: target was ≥90% after self-correction; achieved 100% on first attempt.

### 2026-08-21 — Repo created, Phase 0 scaffold

* Created `satyamdas03/RoboCAD` repository.
* Wrote `README.md` and `PLAN.md` capturing the full project context, architecture, and connection to `LearningRobotics`.
* Scaffolded the `ai_cad/` package:
  * `generator.py` — prompt → LLM → build123d code extraction.
  * `executor.py` — safe subprocess execution of generated code.
  * `validator.py` — manifold / bounding-box sanity checks.
  * `exporter.py` — STL / STEP export.
  * `prompts/system_prompt.txt` and `prompts/examples.json` — few-shot examples.
* Added `validate.py` for the first riskiest-assumption test.
* Committed and pushed to GitHub.

---

## 📬 Contact & follow along

* GitHub: [@satyamdas03](https://github.com/satyamdas03)
* Project updates will be pushed to this repo as phases are completed.

---

**License:** MIT — use it, fork it, improve it.

> *"The goal is not to replace CAD experts. The goal is to let people who understand systems and robotics express hardware ideas without fighting a sketcher."*
