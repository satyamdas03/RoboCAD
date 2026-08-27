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
| **Mission** | AI-powered parametric CAD for robotics hardware: describe parts/assemblies in language, get editable manufacturable models and simulation-ready bundles. |
| **Owner** | Satyam Das (@satyamdas03, satyamdas03@gmail.com) |
| **Start date** | 2026-08-21 |
| **Current date** | 2026-08-27 |

---

## 2. Why this project exists

The user has deep AI/systems/research experience and is learning robotics from first principles in the `LearningRobotics` repo. The bottleneck for building real hardware is not theory but CAD: professional tools require weeks of sketch-extrude-mate muscle memory before a simple idea can be expressed.

RoboCAD removes that bottleneck by letting the user operate at the level of intent:

> *"A 120 mm × 80 mm × 3 mm base plate with four M3 mounting holes on a 100 mm × 60 mm grid and two NEMA-17 motor mounts."*

The AI writes the parametric code; the user edits parameters and exports to manufacturing or simulation.

---

## 3. Connection to LearningRobotics

- **LearningRobotics** (`https://github.com/satyamdas03/LearningRobotics`) teaches robot theory: C-space, rigid-body motions, kinematics, dynamics, control, RL, and the PIBench physical-intuition benchmark.
- **RoboCAD** designs the physical parts that those chapters eventually become.
- **GEDA Bridge** (Phases 14A–15B) connects RoboCAD to `LearningRobotics` by exporting verified MuJoCo/URDF bundles that `LearningRobotics` can load directly.
- Generated parts can be:
  1. Exported as STL/STEP/3MF for 3D printing or machining.
  2. Synced to Onshape for professional assemblies (Phase 5).
  3. Loaded into MuJoCo/Isaac Sim via the GEDA Bridge for skill training.
  4. Used as real hardware builds.

In short: **LearningRobotics teaches the robot. RoboCAD designs the parts. GEDA connects them.**

---

## 4. Hardware & Environment

| Component | Spec |
|---|---|
| Laptop | Lenovo LOQ |
| GPU | NVIDIA GeForce RTX 5060 (8 GB VRAM) |
| OS | Windows 11 Home |
| Python | 3.14 |
| Primary shell | PowerShell; Bash available |

---

## 5. Architecture

```
User prompt + voice/sketch edits + stylus edits
        |
        v
AI orchestrator (Claude 5 / local Ollama)
  - intent parsing
  - generates feature tree or build123d code
  - self-corrects on errors
        |
        v
CAD execution engine (build123d)
        |
        v
Geometry validation (manifold, bounds, manufacturability)
        |
        v
Feature tree / assembly / verification layers
        |
        v
Web viewer + parameter editor + simulation panels
        |
        v
Persistence + design library + remix
        |
        v
Exports: STL / STEP / 3MF / Onshape / MuJoCo / URDF bundle
        |
        v
LearningRobotics → world model → policy training → sim-to-real
```

**Core bet:** The AI writes **parametric code** (not meshes), so the output is editable, versionable, manufacturable, and simulation-ready.

---

## 6. Engineering decisions

| Decision | Choice | Rationale |
|---|---|---|
| CAD kernel | **build123d** first | Python API; LLMs write it well; no API limits |
| AI model | Claude 5 / GPT-4o / local `qwen3-coder:latest` | Best code generation; local Ollama for cost/speed |
| Output artifact | Python script + derived mesh + feature tree | Script is the editable source of truth |
| Execution | Subprocess sandbox | Isolates generated code; captures tracebacks |
| Viewer | React + three.js | Standard, lightweight |
| Storage | SQLite + JSON + Git | Simple, versionable, portable |
| API keys | Environment variables only | Never in files |
| Hosting | Local first | Runs on the RTX 5060 laptop |
| Onshape auth | HMAC-SHA256 API-key signing | Matches official Onshape Python client |
| Claude 5 SDK | httpx2/httpcore2 → standard httpx/httpcore shim | Fixes Python 3.14 recursion bug in Anthropic SDK fork |
| Simulation bridge | MuJoCo primary + URDF fallback | MuJoCo for contact-rich RL; URDF for ROS/Gazebo |

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
| **6** | Robotics-aware component templates | ✅ **Complete — 12 standard robotics parts in `ComponentLibrary`** |
| **7** | Google Stitch Kinetic Precision UI redesign | ✅ **Complete — dark scientific engineering workstation, 56/57 tests passing** |
| **8** | Complexity benchmark + feature-tree spec | ✅ **Complete — 26/30 (86.7%) baseline; feature-tree schema v1.0.0** |
| **9** | Feature-tree backend | ✅ **Complete — structured sidecar, transpiler, store, endpoints, frontend panel; 97 tests** |
| **10** | Sketch + 2D constraint solver | ✅ **Complete — internal least-squares solver; 105 tests** |
| **11** | Assembly system | ✅ **Complete — multi-part instances + LCS mates; 112 tests** |
| **12** | Verification + physics layer | ✅ **Complete — DFM, tolerances, FEA; 125 tests** |
| **13** | Model specialization + Claude 5 integration | ✅ **Complete — dataset builder, Ollama Modelfile, QLoRA skeleton, A/B evaluator, Anthropic SDK fixes; 134 tests; Claude Sonnet 5 T1–T4 87.5% (21/24), overall 21/30 (70.0%)** |
| **14A** | **GEDA Bridge: MuJoCo / URDF exporter + bundles** | 🚧 **Next** |
| **14B** | Standard manipulation scene templates | ⏳ Planned |
| **15A** | LearningRobotics handshake | ⏳ Planned |
| **15B** | RoboCompiler asset pipeline | ⏳ Planned |
| **16** | Voice/text + sketch input | ⏳ Planned |
| **17** | Automatic part decomposition | ⏳ Planned |
| **18** | Per-part physical testing (FEA templates) | ⏳ Planned |
| **19** | Assembly synthesis + verification | ⏳ Planned |
| **20** | World-model simulation builder | ⏳ Planned |
| **21** | Robot brain training loop | ⏳ Planned |
| **22** | HERMES conversational supervisor | ⏳ Planned |
| **23** | Sim-to-real feedback loop | ⏳ Planned |
| **24** | Distribution + commercialization | ⏳ Planned |

See `PLAN.md` for full details. See `.claude/memory/robocad-path-analysis.md` and `.claude/memory/robocad-end-to-end-roadmap.md` for the PATH1/PATH2 strategic analysis.

---

## 8. Repository layout

```
RoboCAD/
├── README.md                 # Public project overview + changelog
├── PLAN.md                   # Detailed build plan (Phases 0–24)
├── PRODUCT.md                # Product definition, users, brand commitments
├── memory.md                 # This file — restart context
├── STITCH_BRIEF.md           # Original Google Stitch design brief
├── requirements.txt          # Python dependencies
├── .gitignore
├── ai_cad/                   # Core AI-CAD package
│   ├── __init__.py           # httpx2/httpcore2 shims + public exports
│   ├── prompts/
│   │   ├── system_prompt.txt
│   │   └── examples.json
│   ├── models.py
│   ├── api.py                # RoboCADBackend.generate()
│   ├── generator.py          # LLM code generation (Claude 5 + Ollama)
│   ├── executor.py
│   ├── validator.py
│   ├── exporter.py
│   ├── parameters.py
│   ├── guess_parameter.py
│   ├── code_ops.py
│   ├── feature_tree.py       # Phase 9
│   ├── transpiler.py         # Phase 9
│   ├── feature_store.py      # Phase 9
│   ├── sketch_solver.py      # Phase 10
│   ├── assembly.py           # Phase 11
│   ├── dfm.py                # Phase 12
│   ├── tolerances.py         # Phase 12
│   ├── fea.py                # Phase 12
│   ├── onshape.py            # Phase 5
│   ├── manufacturing.py      # Phase 5
│   └── geda_bridge/          # Phase 14A — next
│       ├── exporter.py
│       ├── composer.py
│       ├── skill_runner.py
│       ├── verifier.py
│       └── packager.py
├── benchmarks/
│   ├── prompts.json
│   ├── complexity_ladder.json
│   ├── evaluate.py
│   └── evaluate_complexity.py
├── scripts/                  # Phase 13 specialization scripts
│   ├── build_training_dataset.py
│   ├── build_ollama_modelfile.py
│   ├── finetune_model.py
│   └── evaluate_finetuned.py
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
- Phases 0–13 committed and pushed.
- `ai_cad/` package implements generation, execution, validation, parameter extraction, self-correction, Onshape upload, manufacturing reports, face-click parameter guessing, feature trees, sketch constraints, assemblies, DFM/tolerances/FEA, and Claude 5 compatibility.
- Latest commit `06a373c` hardens `_extract_code_block()` against nested markdown fences and increases empty-text retries from 3 to 5.
- Web app has FastAPI backend + React frontend with Kinetic Precision dark workstation UI.
- Test suite: **134/134 passing tests**.
- Live end-to-end verified for base plates, NEMA-17 mounts, component-library seed flows, feature-tree regeneration, and assembly display.
- Strategic analysis complete: PATH1 (GEDA Bridge) will be built before PATH2 (full voice-to-world-model vision).
- **Phase 13 quality gate achieved:** `claude-sonnet-5-20250501` T1–T4 **87.5% (21/24)**.

**Next work:**
1. **Phase 14A GEDA Bridge:** build `ai_cad/geda_bridge/exporter.py` to export designs to MuJoCo/URDF and verify bundles.
2. Complete cross-repo handshake with `LearningRobotics` (Phase 15A).
3. Continue local-model fine-tuning (`robocad-ft:latest`) as a background experiment.

---

## 10. Commands that work

### Install and run Phase 0 validation

```powershell
cd C:\Users\point\projects\RoboCAD
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "..."          # or key for Anthropic-compatible endpoint
$env:ROBOCAD_MODEL = "qwen3-coder:latest"  # optional override; "claude-sonnet-5-20250501" for Claude 5
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
4. **Start local, integrate later.** Prove the loop before Onshape/simulation.
5. **Document every push.** README/memory/PLAN are living logs.
6. **No API keys in files.** All keys via environment variables.
7. **Ship PATH1 before PATH2.** Validate CAD-to-physics handoff before chasing the full vision.

---

## 12. Open decisions / questions

1. Which LLM provider should be the default for T4/T5? Currently Claude 5 for cloud; `qwen3-coder:latest` for local.
2. Should we also support `cadquery` as an alternate kernel? Defer until build123d is proven.
3. When should we buy hardware? Defer until GEDA Bridge produces real parts that need fabrication.
4. Should designs be tracked in Git? Yes for code; exports are gitignored.
5. Should GEDA Bridge live inside RoboCAD or as a new top-level repo? Current plan: inside RoboCAD (`ai_cad/geda_bridge/`) to reuse backend/frontend/test infrastructure.

---

## 13. Memory trigger

If the session restarts and all context is lost, read these files in order:

1. `C:\Users\point\.claude\projects\C--Users-point-projects-RoboCAD\memory\MEMORY.md`
2. Every memory file linked from it, especially:
   - `robocad-path-analysis.md`
   - `robocad-end-to-end-roadmap.md`
   - `claude5-integration-fixes.md`
   - `phase13-model-specialization.md`
3. `C:\Users\point\projects\RoboCAD\memory.md` (this file)
4. `C:\Users\point\projects\RoboCAD\README.md`
5. `C:\Users\point\projects\RoboCAD\PLAN.md`
6. `C:\Users\point\projects\RoboCAD\PRODUCT.md`

For the most recent state, also check:
- Latest commit hash (`git log --oneline -5`)
- `.claude/memory/robocad-path-analysis.md` for PATH1/PATH2 status
- `.claude/memory/claude5-integration-fixes.md` for latest benchmark numbers

To force a full sync at any time, type:

> `:POINTBREAK`

---

## 14. Summary for fast restart

If you are resuming this session with no other context:

> We are building **RoboCAD**, an AI-powered parametric CAD tool for robotics hardware. The repo is at `https://github.com/satyamdas03/RoboCAD`. **Phases 0–13 are committed and pushed** (prompt → build123d → STL/STEP → Onshape → manufacturing report → component library → dark Kinetic Precision UI → feature tree → sketch constraints → assemblies → DFM/tolerances/FEA → model specialization → Claude 5 integration, **134 tests passing**). **Phase 13 is green on the T1–T4 ≥80% gate** (87.5% with `claude-sonnet-5-20250501`). The immediate next phase is **Phase 14A GEDA Bridge**: connect RoboCAD designs to the `LearningRobotics` MuJoCo simulation + skill-verification stack via verified MuJoCo/URDF bundles. Strategic decision: ship PATH1 (GEDA Bridge) before PATH2 (voice-to-CAD-to-world-model). See `.claude/memory/robocad-path-analysis.md` and `.claude/memory/robocad-end-to-end-roadmap.md`. Say `:POINTBREAK` to force a full dossier sync.

---

*Last updated: 2026-08-27 (Phases 0–13 complete; Phase 13 T1–T4 gate achieved; PATH1/PATH2 analysis done; Phase 14A GEDA Bridge is next)*
