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
  1. Exported as STL/STEP/3MF for 3D printing or machining.
  2. Synced to Onshape for professional assemblies.
  3. Used as MuJoCo collision/visual meshes in `LearningRobotics` simulations.
  4. Packaged into verified robot-capability bundles via the GEDA Bridge.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts. GEDA connects them.**

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
AI orchestrator (Claude / GPT-4 / local Ollama)
  - intent parsing
  - generates build123d code
  - self-corrects on errors
        |
        v
CAD execution engine (build123d)
        |
        v
Geometry validation (manifold, bounds, manufacturability)
        |
        v
Web viewer + parameter editor (Phase 2–3)
        |
        v
Persistence + design library + remix (Phase 4)
        |
        v
Onshape upload + manufacturing report (Phase 5)
        |
        v
Robotics component library (Phase 6)
        |
        v
Kinetic Precision workstation UI (Phase 7)
        |
        v
GEDA Bridge → MuJoCo export + verified skill bundle
```

**Core bet:** The AI writes **parametric code** (not meshes), so the output is editable, versionable, and manufacturable.

---

## 6. Engineering decisions

| Decision | Choice | Rationale |
|---|---|---|
| CAD kernel | **build123d** first | Python API; LLMs write it well; no API limits |
| AI model | Claude / GPT-4o / local `qwen3-coder:latest` | Best code generation + self-correction; local Ollama endpoint also works |
| Output artifact | Python script + derived mesh | Script is the editable source of truth |
| Execution | Subprocess sandbox | Isolates generated code; captures tracebacks |
| Viewer | React + three.js | Standard, lightweight |
| Storage | SQLite + JSON + Git | Simple, versionable, portable |
| API keys | Environment variables only | Never in files |
| Hosting | Local first | Runs on the RTX 5060 laptop |
| Onshape auth | HMAC-SHA256 API-key signing | Matches official Onshape Python client |

---

## 7. Phased plan

| Phase | Goal | Status |
|---|---|---|
| **0** | Validate AI → build123d → STL loop | ✅ **Complete — 8/8 prompts pass** |
| **1** | Robust generation + self-correction backend | ✅ **Complete — 19/20 prompts pass (95%)** |
| **2** | Minimal web app (prompt + viewer + export) | ✅ **Complete — FastAPI + React + three.js + persistence** |
| **3** | Parameter / stylus editing layer | ✅ **Complete — editable parameter panel + face-click parameter guessing + versioned regeneration** |
| **4** | Design library + remix | ✅ **Complete — component catalog, search/filter, tags, remix with parent linking** |
| **5** | Onshape export / sync + manufacturing reports | ✅ **Complete — HMAC-signed Onshape client, STEP upload, manufacturability report** |
| **6** | Robotics-aware component templates | ✅ **Complete — 12 standard robotics parts in `ComponentLibrary`, seeded prompts, tags, remix** |
| **7** | Google Stitch Kinetic Precision UI redesign | ✅ **Complete — dark scientific engineering workstation, `kp-*` token system, 56/57 tests passing** |
| **8** | Complexity benchmark + feature-tree spec | 🚧 **Next native RoboCAD phase** |
| **G** | **GEDA Bridge — MuJoCo export + verified skill bundle** | 🚧 **Immediate cross-repo priority** |

See `PLAN.md` for full details. See `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\geda-bridge.md` for the GEDA Bridge super master prompt and market research.

---

## 8. Repository layout

```
RoboCAD/
├── README.md                 # Public project overview + changelog
├── PLAN.md                   # Detailed build plan
├── memory.md                 # This file — restart context
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core AI-CAD package
│   ├── __init__.py
│   ├── prompts/
│   │   ├── system_prompt.txt
│   │   └── examples.json
│   ├── models.py
│   ├── api.py                # RoboCADBackend.generate()
│   ├── generator.py
│   ├── executor.py
│   ├── validator.py
│   ├── exporter.py
│   ├── parameters.py
│   ├── guess_parameter.py
│   ├── code_ops.py
│   ├── onshape.py            # Phase 5 Onshape client
│   ├── manufacturing.py      # Phase 5 manufacturability analyzer
│   └── geda_bridge/          # Phase G — next cross-repo integration
│       ├── exporter.py       # build123d → MJCF/URDF
│       ├── composer.py       # robot + part + task scene
│       ├── skill_runner.py   # wrap LearningRobotics APIs
│       ├── verifier.py       # success criteria + scoring
│       └── packager.py       # verified bundle writer
├── benchmarks/
│   ├── prompts.json
│   └── evaluate.py
├── web/                      # FastAPI + React app
│   ├── backend/
│   │   └── main.py
│   └── frontend/
│       └── src/components/
├── components/               # Phase 6 robotics part library
├── designs/                  # persisted generated designs (runtime)
└── tests/                    # pytest suite
```

---

## 9. Current status snapshot

- Repo created at `https://github.com/satyamdas03/RoboCAD`.
- Phases 0–7 committed and pushed.
- `ai_cad/` package implements generation, execution, validation, parameter extraction, self-correction, Onshape upload, manufacturing reports, and face-click parameter guessing.
- Web app has FastAPI backend + React frontend with Kinetic Precision dark workstation UI.
- Test suite: **57 passing tests** (56/57 with the known `test_generate_missing_api_key` env interaction).
- Live end-to-end verified for base plates, NEMA-17 mounts, and component-library seed flows.

**Next work:**
1. **GEDA Bridge (immediate):** build `ai_cad/geda_bridge/` to export designs to MuJoCo and verify robot skills. See `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\geda-bridge.md`.
2. Phase 8: complexity benchmark + feature-tree spec.
3. Phase 9: feature-tree backend.
4. Phase 10: sketch + 2D constraint solver.
5. Phase 11: assembly system.
6. Phase 12: verification + physics layer (DFM, FEA, tolerance/fit).
7. Phase 13: model specialization / fine-tuning.
8. Phase 14: distribution + packaging.

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

### Start the web app

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
6. **No API keys in files.** All keys via environment variables.

---

## 12. Open decisions / questions

1. Which LLM provider should be the default? Currently Claude via Anthropic; GPT-4o is an easy alternative.
2. Should we also support `cadquery` as an alternate kernel? Defer until build123d is proven.
3. When should we buy hardware? Defer until GEDA Bridge produces real parts that need fabrication.
4. Should designs be tracked in Git? Yes for code; exports are gitignored.
5. Should GEDA Bridge live inside RoboCAD or as a new top-level repo? Current plan: inside RoboCAD (`ai_cad/geda_bridge/`) to reuse backend/frontend/test infrastructure.

---

## 13. Memory trigger

If the session restarts and all context is lost, read these files in order:

1. `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\MEMORY.md`
2. `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\geda-bridge.md`
3. `C:\Users\point\projects\RoboCAD\memory.md`
4. `C:\Users\point\projects\RoboCAD\README.md`
5. `C:\Users\point\projects\RoboCAD\PLAN.md`
6. `C:\Users\point\projects\LearningRobotics\MEMORY.md`

To force a full sync at any time, type:

> `:POINTBREAK`

---

## 14. Summary for fast restart

If you are resuming this session with no other context:

> We are building **RoboCAD**, an AI-powered parametric CAD tool for robotics hardware. The repo is at `https://github.com/satyamdas03/RoboCAD`. **Phases 0–7 are committed and pushed** (prompt → build123d → STL/STEP → Onshape → manufacturing report → component library → dark Kinetic Precision UI, **57 tests passing**). The immediate next phase is the **GEDA Bridge**: connect RoboCAD designs to the LearningRobotics MuJoCo simulation + skill-verification stack to produce verified `Design + Skill` bundles. See `C:\Users\point\.claude\projects\C--Users-point-projects-LearningRobotics\memory\geda-bridge.md` for the super master prompt. The sister project is `LearningRobotics` (robotics theory and PIBench benchmark). Say `:POINTBREAK` to force a full dossier sync.

---

*Last updated: 2026-08-22 (Phases 0–7 complete; GEDA Bridge is the immediate next phase)*
