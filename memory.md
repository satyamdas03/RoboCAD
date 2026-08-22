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
| 1 | Robust generation + self-correction backend | 🔄 In progress |
| 2 | Minimal web app (prompt + viewer + export) | ⏳ Planned |
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
├── requirements.txt          # Phase 0 dependencies
├── .gitignore
├── ai_cad/                   # Core package
│   ├── generator.py          # prompt → code
│   ├── executor.py           # run build123d safely
│   ├── validator.py          # geometry sanity checks
│   ├── exporter.py           # STL / STEP export
│   └── prompts/              # system prompt + examples
├── web/                      # (Phase 2) FastAPI + React
├── components/               # (Phase 6) robotics part library
├── designs/                  # (Phase 4) saved designs
└── tests/                    # pytest suite
```

---

## 9. Current status snapshot

- Repo created at `https://github.com/satyamdas03/RoboCAD`.
- Phase 0 committed and pushed.
- `ai_cad/` package implements: generator, executor, validator, exporter, few-shot prompts.
- `validate.py` runs 8 prompts and reports pass/fail.
- **Phase 0 result: 8/8 prompts passed (100%)** using local `qwen3-coder:latest` via an Anthropic-compatible Ollama endpoint.
- Key fixes landed:
  - `generator.py` — Anthropic SDK 1.0 compatibility (`temperature` via `extra_body`) + `ROBOCAD_MODEL` env override.
  - `executor.py` — fixed f-string escaping for volume metadata.
  - `validate.py` — robust error extraction.
  - `prompts/system_prompt.txt` + `examples.json` — working build123d patterns A/B/C/D.
- Unit tests for generator utilities in `tests/test_generator.py`.

**Next work (Phase 1):**
1. Wrap generator/executor/validator into a single `generate(prompt)` Pydantic response.
2. Extract named parameters from generated code for later editing.
3. Expand benchmark to 20 prompts; confirm ≥95% pass rate within two retries.
4. Add pytest tests for executor and validator.
5. Commit and push progress.

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
