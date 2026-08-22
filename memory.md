# 🧠 Project Memory — RoboCAD

> **Purpose:** This file is the single source of truth for session restart. Read it first if you have no other context. It records everything we have done, decided, researched, and planned — line by line — so work can resume without loss.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project name** | RoboCAD |
| **GitHub repository** | https://github.com/satyamdas03/RoboCAD |
| **Branch** | `master` |
| **Visibility** | Public |
| **Mission** | AI-powered parametric CAD for robotics hardware: describe parts in language, get editable manufacturable models. |
| **Owner** | Satyam Das (@satyamdas03, satyamdas03@gmail.com) |
| **Start date** | 2026-08-21 |
| **Current date** | 2026-08-22 |

---

## 2. Why this project exists

The user has deep AI/systems/research experience and is learning robotics from first principles in the `LearningRobotics` repo. The bottleneck for building real hardware is not theory but CAD: professional tools like Onshape require weeks of sketch-extrude-mate muscle memory before a simple idea can be expressed.

RoboCAD removes that bottleneck by letting the user operate at the level of intent:

> *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid and two NEMA-17 motor mounts."*

The AI writes the parametric code; the user edits parameters and exports to manufacturing.

---

## 3. Connection to LearningRobotics

- **LearningRobotics** (`https://github.com/satyamdas03/LearningRobotics`) teaches robot theory: C-space, rigid-body motions, kinematics, dynamics, control, and the PIBench physical-intuition benchmark.
- **RoboCAD** designs the physical parts that those chapters eventually become.
- Generated parts can be:
  1. Exported as STL/STEP for 3D printing or machining.
  2. Synced to Onshape later for professional assemblies.
  3. Used as MuJoCo collision/visual meshes in `LearningRobotics` simulations.
  4. Linked to the `LearningRobotics` hardware BOM so designs are cost-aware.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts.**

---

## 4. Hardware & Environment

| Component | Spec |
|---|---|
| Laptop | Lenovo LOQ |
| GPU | NVIDIA GeForce RTX 5060 (8 GB VRAM) |
| OS | Windows 11 Home |
| Python | 3.11 |
| Primary shell | PowerShell; Bash available |

---

## 5. Architecture

```
User prompt + stylus edits
        |
        v
AI orchestrator (Claude / GPT-4)
  - intent parsing
  - generates build123d code
  - self-corrects on errors
        |
        v
CAD execution engine (build123d / CADQuery)
        |
        v
Geometry validation (manifold, bounds, manufacturability)
        |
        v
Web viewer + parameter editor (Phase 2+)
        |
        v
Persistence + design library (Phase 4+)
        |
        v
Onshape export / sync (Phase 5)
```

**Core bet:** The AI writes **parametric code** (not meshes), so the output is editable, versionable, and manufacturable.

---

## 6. Engineering decisions

| Decision | Choice | Rationale |
|---|---|---|
| CAD kernel | **build123d** first | Python API; LLMs write it well; no API limits |
| AI model | Claude 3.5 Sonnet / GPT-4o / local `qwen3-coder:latest` | Best code generation + self-correction; local Ollama endpoint also works |
| Output artifact | Python script + derived mesh | Script is the editable source of truth |
| Execution | Subprocess sandbox | Isolates generated code; captures tracebacks |
| Viewer (Phase 2) | React + three.js | Standard web 3D stack |
| Storage | SQLite + JSON + Git | Simple and versionable |
| API keys | Environment variables only | Never in files |
| Hosting | Local first | Runs on the RTX 5060 laptop |

---

## 7. Phased plan

| Phase | Goal | Status |
|---|---|---|
| **0** | Validate AI → build123d → STL loop | ✅ **Complete — 8/8 (100%)** |
| **1** | Robust generation + self-correction backend | ✅ **Complete — 19/20 (95%)** |
| **2** | Minimal web app (prompt + viewer + export) | ✅ **Complete — FastAPI + React + three.js + persistence** |
| 3 | Parameter / stylus editing layer | ⏳ Planned |
| 4 | Design library + remix | ⏳ Planned |
| 5 | Onshape export / sync + manufacturing reports | ⏳ Planned |
| 6 | Robotics-aware component templates | ⏳ Planned |

See `PLAN.md` for full details.

---

## 8. Repository layout

```
RoboCAD/
├── README.md                 # Public project overview + changelog
├── PLAN.md                   # Detailed build plan
├── memory.md                 # This file — restart context
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core package
│   ├── __init__.py           # Public exports
│   ├── models.py             # Pydantic response models
│   ├── api.py                # Unified RoboCADBackend.generate()
│   ├── generator.py          # prompt → code
│   ├── executor.py           # run build123d safely
│   ├── validator.py          # geometry sanity checks
│   ├── exporter.py           # STL / STEP export
│   ├── parameters.py         # AST-based parameter extraction
│   └── prompts/              # system prompt + examples
├── benchmarks/               # Phase 1 curated prompt set + runner
│   ├── prompts.json
│   └── evaluate.py
├── web/                      # Phase 2 FastAPI + React
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
├── designs/                  # persisted generated designs (runtime)
└── tests/                    # pytest suite
```

---

## 9. Current status snapshot

- Repo created at `https://github.com/satyamdas03/RoboCAD`.
- Phase 0 committed and pushed (8/8 prompts passed).
- Phase 1 committed and pushed (19/20 prompts passed = 95%, commit `08c3b60`).
- Phase 2 committed and pushed (FastAPI + React + three.js viewer, commit to be recorded).
- `ai_cad/` package implements:
  - `models.py` — Pydantic `GenerationResult`, `CADParameter`, `ValidationReport`, `ExportPaths`.
  - `api.py` — `RoboCADBackend.generate()` orchestrating generation, execution, validation, parameter extraction, and self-correction.
  - `parameters.py` — AST-based extraction of editable numeric parameters from generated code.
  - `generator.py` — Anthropic SDK 1.0 compatibility + `ROBOCAD_MODEL` override.
  - `executor.py` — subprocess sandbox with JSON metadata, script path tracking.
  - `validator.py` — manifold/watertight/bounds checks via `trimesh`.
  - `exporter.py` — STEP/STL export wrapper.
  - `prompts/system_prompt.txt` + `examples.json` — working build123d patterns A/B/C/D.
- `web/backend/main.py` — FastAPI app with `/generate`, `/designs`, `/designs/{id}`, `/exports/{id}/{file}`.
- `web/frontend/` — Vite + React + `react-three-fiber` STL viewer + history sidebar + download links.
- `benchmarks/prompts.json` + `benchmarks/evaluate.py` — 20-prompt Phase 1 benchmark.
- Test suite: **25 passing tests** across generator, executor, validator, parameters, API orchestration, and web backend.

**Next work (Phase 3):**
1. Interactive parameter editing: sliders/inputs update generated code and re-run build123d.
2. Click-to-edit in the viewer (face/point → nearest parameter guess).
3. Save parameter edits as new design versions.
4. Commit and push Phase 3.

---

## 10. Commands that work

### Install and run Phase 0 validation

```powershell
cd C:\Users\point\projects\RoboCAD
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "..."          # or key for Anthropic-compatible endpoint
$env:ROBOCAD_MODEL = "qwen3-coder:latest"  # optional override
python validate.py
```

### Run tests

```powershell
$env:PYTHONPATH = "C:\Users\point\projects\RoboCAD"
python -m pytest tests -q
```

### Start the Phase 2 web app

```powershell
cd C:\Users\point\projects\RoboCAD
.venv\Scripts\Activate.ps1
$env:ANTHROPIC_API_KEY = "..."
python -m uvicorn web.backend.main:app --reload --port 8000

# Second terminal:
cd C:\Users\point\projects\RoboCAD\web\frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Commit and push

```powershell
cd C:\Users\point\projects\RoboCAD
git add .
git commit -m "robocad: descriptive message"
git push origin master
```

---

## 11. Design principles

1. **Parametric code is the source of truth.** Mesh is a derived artifact.
2. **Fail visibly and correct.** Tracebacks are fed back to the LLM.
3. **No mesh dead-ends.** Always produce an editable model.
4. **Start local, integrate later.** Prove the loop before Onshape.
5. **Document every push.** README/memory/PLAN are living logs.

---

## 12. Open decisions / questions

1. Which LLM provider should be the default? Currently Claude via Anthropic; GPT-4o is an easy alternative.
2. Should we also support `cadquery` as an alternate kernel? Defer until build123d is proven.
3. When should we buy hardware? Defer until Phase 5/6 when real parts are designed.
4. Should designs be tracked in Git? Yes for code; exports are gitignored.

---

## 13. Memory trigger

If the session restarts and all context is lost, read these files in order:

1. `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\MEMORY.md`
2. `C:\Users\point\projects\RoboCAD\memory.md`
3. `C:\Users\point\projects\RoboCAD\README.md`
4. `C:\Users\point\projects\RoboCAD\PLAN.md`

Then read `C:\Users\point\projects\LearningRobotics\MEMORY.md` for the sister-project context.

To force a full sync at any time, type:

> `:POINTBREAK`

---

## 14. Summary for fast restart

If you are resuming this session with no other context:

> We are building **RoboCAD**, an AI-powered parametric CAD tool for robotics hardware. The repo is at `https://github.com/satyamdas03/RoboCAD`. The core loop is prompt → LLM → `build123d` Python code → execution → STL/STEP export. **Phase 0 (validation) is complete at 8/8 (100%).** Phase 1 (robust backend + expanded benchmark) is in progress. The sister project is `LearningRobotics` (robotics theory and PIBench benchmark). Say `:POINTBREAK` to force a full dossier sync.

---

*Last updated: 2026-08-22*
